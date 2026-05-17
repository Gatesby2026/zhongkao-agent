"""后台任务：5 阶段状态机。

阶段（与 H5 #stages 对齐）：
  1 识别考试信息   2 识别答题卡作答   3 对照标准答案
  4 AI 分析失分主因  5 生成提分建议

ocr_photos=True（Phase 2 真实流）：
  阶段 2 真跑 detect.py，对上传照片做涂卡 OCR → answer-card.json
ocr_photos=False（Phase 1 reference 演示）：
  阶段 1-2 占位推进，answer-card.json 用 reference 现成的
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
REF_STUDENT_DIR = ROOT / "students" / "jiaxiaoqi" / "2026-chaoyang-yi-physics"

# 串行单 worker（OCR/LLM 内部已并发；任务间排队避免打爆 API 配额）
_lock = threading.Lock()


def submit(aid: str, student_dir: Path, ocr_photos: bool = False,
           manual_slug: str = ""):
    t = threading.Thread(target=_run,
                         args=(aid, student_dir, ocr_photos, manual_slug),
                         daemon=True)
    t.start()


def _ocr_answer_card(aid: str, student_dir: Path,
                     manual_slug: str = "") -> Path:
    """真实涂卡识别 + 考试识别（自动优先，失败回退手动指定）。

    1. OCR 全部图片 → 合并全文 → 识别考试身份 + 学生
    2. 自动识别不到时，用前端手动选的 exam_slug 兜底
    3. 按 slug 重命名学生目录（infer_standard 靠 dir 名找 yaml）
    4. detect.py 全图涂卡 → answer-card.json
    """
    photos_dir = student_dir / "answer-card-photos"
    imgs = sorted(
        p for p in photos_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic")
        and p.stat().st_size > 1024
    )
    if not imgs:
        raise RuntimeError("answer-card-photos 无有效图片（空或格式不符）")

    sys.path.insert(0, str(SR_DIR))
    import detect  # noqa
    import card_meta  # noqa

    # 1. qwen-vl-max 视觉理解：读表头 → 考试元信息 + 学生 + 卷面完整性
    meta = card_meta.extract_card_meta(imgs)
    idy = exam_match.slug_from_meta(meta)
    idy["completeness_note"] = meta.get("completeness_note", "")
    idy["pages_complete"] = bool(meta.get("pages_complete", False))

    # 2. 自动识别不到 → 手动 slug 兜底
    if not idy["matched"]:
        if manual_slug and exam_match.kb_yaml_for_slug(manual_slug):
            idy["exam_slug"] = manual_slug
            idy["matched"] = True
        else:
            note = idy.get("completeness_note") or ""
            raise RuntimeError(
                f"无法识别考试（区={idy.get('district') or '?'} "
                f"科={idy.get('subject') or '?'} 年={idy.get('year') or '?'} "
                f"模={idy.get('exam_type') or '?'}）。"
                f"{('卷面：' + note) if note else ''} "
                f"请在上传页选「区/科目」后重试。")

    slug = idy["exam_slug"]
    name = idy["student_name"] or "考生"
    # 2. 重命名目录到识别 slug（若不同）
    if student_dir.name != slug:
        new_dir = student_dir.parent / slug
        if new_dir.exists():
            import shutil
            shutil.rmtree(new_dir)
        student_dir.rename(new_dir)
        student_dir = new_dir
        photos_dir = student_dir / "answer-card-photos"
        imgs = sorted(photos_dir.glob("*"))
        imgs = [p for p in imgs if p.is_file()
                and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic")]

    (student_dir / "student.json").write_text(
        json.dumps({"name": name, "examId": idy["student_id"]},
                   ensure_ascii=False), encoding="utf-8")
    db.set_exam_info(aid, name, slug, str(student_dir))

    # 3. 全图涂卡识别
    res = detect.detect_card(imgs, photos_dir=photos_dir)
    stu = dict(getattr(res, "student", {}) or {})
    # 用识别到的真实姓名/考号覆盖空值（OCR 表头比涂卡区可靠）
    if name and not stu.get("name"):
        stu["name"] = name
    if idy["student_id"] and not stu.get("examId"):
        stu["examId"] = idy["student_id"]
    out = {
        "student": stu or {"name": name, "examId": idy["student_id"]},
        "answers": getattr(res, "answers", []),
    }
    (student_dir / "answer-card.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return student_dir


def _ensure_scores(aid: str, student_dir: Path, wait_s: int = 150):
    """真实上传流程：build_report 需 scores.json，必须用家长上传并解析的小分。
    限时等待其到位；超时报错（绝不套用他人 reference 小分——会张冠李戴）。
    """
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


def _run(aid: str, student_dir: Path, ocr_photos: bool,
         manual_slug: str = ""):
    with _lock:
        try:
            db.update_stage(aid, 1, "识别考试信息")
            db.update_stage(aid, 2, "识别答题卡作答")
            if ocr_photos:
                student_dir = _ocr_answer_card(aid, student_dir, manual_slug)
                _ensure_scores(aid, student_dir)

            def on_stage(idx: int, name: str):
                db.update_stage(aid, idx, name)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")
