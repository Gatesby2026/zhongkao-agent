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

def submit_detect(aid: str, student_dir: Path):
    threading.Thread(target=_detect, args=(aid, student_dir),
                     daemon=True).start()


def _detect(aid: str, student_dir: Path):
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
            # 识别不到考试 → 失败（让用户重拍含顶部标题行的照片重传）
            db.mark_failed(
                aid,
                "没能从答题卡识别出考试信息。请重新拍照上传——"
                "务必拍清「考生须知页」最顶部的标题行"
                "（如「北京市朝阳区九年级综合练习（一）物理答题卡」）。")
            return

        slug = idy["exam_slug"]
        name = idy.get("student_name") or "考生"

        # 按 slug 重命名目录（infer_standard 靠 dir 名找 yaml）
        if slug and student_dir.name != slug:
            new_dir = student_dir.parent / slug
            if new_dir.exists():
                import shutil
                shutil.rmtree(new_dir)
            student_dir.rename(new_dir)
            student_dir = new_dir
        (student_dir / "student.json").write_text(
            json.dumps({"name": name,
                        "examId": idy.get("student_id", "")},
                       ensure_ascii=False), encoding="utf-8")
        db.set_exam_info(aid, name, slug, str(student_dir))

        idy["student_dir"] = str(student_dir)
        db.set_detected(aid, json.dumps(idy, ensure_ascii=False),
                        "ready_confirm", "待确认")
    except Exception as e:
        traceback.print_exc()
        db.mark_failed(aid, f"{type(e).__name__}: {e}")


# ============== B. 流水线 ==============

def submit_pipeline(aid: str, student_dir: Path):
    threading.Thread(target=_pipeline, args=(aid, student_dir),
                     daemon=True).start()


def _ensure_scores(aid: str, student_dir: Path, wait_s: int = 25):
    """小分可选：
    - 家长上传了班小二小分 → 用它（老师阅卷分，权威）
    - 没上传 → 系统自动判分（选择题确定性 + 主观题 qwen-vl-max 看图估分）
    短暂等待上传到位（家长可能正传）；超时则自动判分，不再失败。
    """
    target = student_dir / "scores.json"
    src_marker = student_dir / ".score_source"
    uploaded = UPLOAD_ROOT / aid / "scores.json"
    waited = 0
    while waited < wait_s:
        if uploaded.exists():
            target.write_bytes(uploaded.read_bytes())
            src_marker.write_text("teacher", encoding="utf-8")
            return
        time.sleep(3)
        waited += 3

    # 无小分 → 自动判分
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    import auto_grade, exam_match  # noqa
    yaml_path = exam_match.kb_yaml_for_slug(student_dir.name)
    if not yaml_path:
        raise RuntimeError(f"找不到试卷标准答案：{student_dir.name}")
    db.update_stage(aid, 3, "无小分，系统自动判分中")
    auto_grade.write_auto_scores(student_dir, Path(yaml_path))
    src_marker.write_text("auto", encoding="utf-8")


def _pipeline(aid: str, student_dir: Path):
    with _lock:
        try:
            db.update_stage(aid, 2, "识别答题卡作答")
            sys.path.insert(0, str(SR_DIR))
            import detect  # noqa

            photos_dir = student_dir / "answer-card-photos"
            imgs = _imgs(photos_dir)
            res = detect.detect_card(imgs, photos_dir=photos_dir)

            # 学生名以 student.json 为准（card_meta 表头识别 / 家长确认页纠正，
            # 均比答题卡涂卡区 OCR 可靠），始终覆盖 detect 结果
            sj = student_dir / "student.json"
            known = json.loads(sj.read_text()) if sj.exists() else {}
            stu = dict(getattr(res, "student", {}) or {})
            if known.get("name"):
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
