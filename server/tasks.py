"""后台任务：两段式。

A. 检测（detect_only，上传后立即跑，~10s）：
   card_meta(qwen-vl-max) 读表头 → 考试身份 + 学生 + 卷面完整性
   → 按 slug 重命名学生目录 + 写 student.json → status='ready_confirm'
   家长在「答题卡页」看到识别结果 + 可下载试卷原卷确认。

B. 流水线（run_pipeline，家长确认 + 传小分后由 /start 触发）：
   detect.detect_card 真实涂卡 → answer-card.json
   → 等上传小分 → build_report → done

阶段（status/stage_name）：
  detecting → ready_confirm →(/start)→ running(识别作答/对照标答/AI分析/提分建议) → done|failed
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path

import db
import pipeline_adapter as pa
import exam_match

ROOT = Path(__file__).resolve().parents[1]
SR_DIR = ROOT / "scripts" / "answer-card-ocr"
UPLOAD_ROOT = ROOT / "server" / "uploads"

_lock = threading.Lock()


def _imgs(photos_dir: Path) -> list[Path]:
    return sorted(
        p for p in photos_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic")
        and p.stat().st_size > 1024
    )


# ============== A. 检测 ==============

def submit_detect(aid: str, student_dir: Path, manual_slug: str = ""):
    threading.Thread(target=_detect, args=(aid, student_dir, manual_slug),
                     daemon=True).start()


def _detect(aid: str, student_dir: Path, manual_slug: str = ""):
    try:
        db.set_detected(aid, "", "detecting", "识别考试信息")
        photos_dir = student_dir / "answer-card-photos"
        imgs = _imgs(photos_dir)
        if not imgs:
            raise RuntimeError("无有效答题卡图片")

        sys.path.insert(0, str(SR_DIR))
        import card_meta  # noqa

        meta = card_meta.extract_card_meta(imgs)
        idy = exam_match.slug_from_meta(meta)
        idy["exam_title"] = meta.get("exam_title", "")
        idy["completeness_note"] = meta.get("completeness_note", "")
        idy["pages_complete"] = bool(meta.get("pages_complete", False))

        if not idy["matched"]:
            if manual_slug and exam_match.kb_yaml_for_slug(manual_slug):
                idy["exam_slug"] = manual_slug
                idy["matched"] = True
                idy["manual"] = True
            # 未匹配也回传，让前端引导手动选；不直接 fail

        slug = idy["exam_slug"] or ""
        name = idy.get("student_name") or "考生"

        # 匹配到才重命名目录 + 落 student.json（infer_standard 靠 dir 名）
        if idy["matched"] and slug and student_dir.name != slug:
            new_dir = student_dir.parent / slug
            if new_dir.exists():
                import shutil
                shutil.rmtree(new_dir)
            student_dir.rename(new_dir)
            student_dir = new_dir
        if idy["matched"]:
            (student_dir / "student.json").write_text(
                json.dumps({"name": name,
                            "examId": idy.get("student_id", "")},
                           ensure_ascii=False), encoding="utf-8")
            db.set_exam_info(aid, name, slug, str(student_dir))

        idy["student_dir"] = str(student_dir)
        st = "ready_confirm" if idy["matched"] else "need_manual"
        db.set_detected(aid, json.dumps(idy, ensure_ascii=False), st,
                        "待确认" if idy["matched"] else "需手动选择考试")
    except Exception as e:
        traceback.print_exc()
        db.mark_failed(aid, f"{type(e).__name__}: {e}")


# ============== B. 流水线 ==============

def submit_pipeline(aid: str, student_dir: Path):
    threading.Thread(target=_pipeline, args=(aid, student_dir),
                     daemon=True).start()


def _ensure_scores(aid: str, student_dir: Path, wait_s: int = 150):
    target = student_dir / "scores.json"
    uploaded = UPLOAD_ROOT / aid / "scores.json"
    waited = 0
    while waited < wait_s:
        if uploaded.exists():
            target.write_bytes(uploaded.read_bytes())
            return
        if target.exists():
            return
        time.sleep(3)
        waited += 3
    raise RuntimeError(
        "未收到小分表。主观题得分需班小二导出的小分 xlsx 才能分析——"
        "请在「上传小分」步骤上传后重试。")


def _pipeline(aid: str, student_dir: Path):
    with _lock:
        try:
            db.update_stage(aid, 2, "识别答题卡作答")
            sys.path.insert(0, str(SR_DIR))
            import detect  # noqa

            photos_dir = student_dir / "answer-card-photos"
            imgs = _imgs(photos_dir)
            res = detect.detect_card(imgs, photos_dir=photos_dir)

            # 学生名优先用已识别的（student.json 比涂卡区可靠）
            sj = student_dir / "student.json"
            known = json.loads(sj.read_text()) if sj.exists() else {}
            stu = dict(getattr(res, "student", {}) or {})
            if known.get("name") and not stu.get("name"):
                stu["name"] = known["name"]
            if known.get("examId") and not stu.get("examId"):
                stu["examId"] = known["examId"]
            (student_dir / "answer-card.json").write_text(
                json.dumps({"student": stu or known,
                            "answers": getattr(res, "answers", [])},
                           ensure_ascii=False, indent=2), encoding="utf-8")

            db.update_stage(aid, 3, "对照标准答案")
            _ensure_scores(aid, student_dir)

            def on_stage(idx, n):
                db.update_stage(aid, idx, n)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")


# ---- Phase 1 纯 reference 演示（无上传）----

def submit_reference(aid: str, student_dir: Path):
    threading.Thread(target=_reference, args=(aid, student_dir),
                     daemon=True).start()


def _reference(aid: str, student_dir: Path):
    with _lock:
        try:
            for i, n in [(1, "识别考试信息"), (2, "识别答题卡作答")]:
                db.update_stage(aid, i, n)

            def on_stage(idx, nm):
                db.update_stage(aid, idx, nm)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")
