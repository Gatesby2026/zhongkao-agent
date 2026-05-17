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


def submit(aid: str, student_dir: Path, ocr_photos: bool = False):
    t = threading.Thread(target=_run, args=(aid, student_dir, ocr_photos),
                         daemon=True)
    t.start()


def _ocr_answer_card(aid: str, student_dir: Path) -> Path:
    """真实涂卡识别 + 考试自动识别。

    1. OCR 首图表头 → 识别考试身份（区/科/年/模）+ 学生
    2. 按识别到的 exam_slug 重命名学生目录（infer_standard 靠 dir 名找 yaml）
    3. detect.py 全图涂卡 → answer-card.json
    返回（可能已重命名的）student_dir。
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

    # 1. 表头 OCR → 考试识别
    head_lines = detect.ocr_one_image(imgs[0])
    idy = exam_match.detect_exam(head_lines)
    if not idy["matched"]:
        raise RuntimeError(
            f"无法识别考试（区/科/年/模）：识别到 "
            f"{idy.get('district','?')}/{idy.get('subject','?')}/"
            f"{idy.get('year','?')}/{idy.get('exam_type','?')}。"
            f"请确认上传的是完整答题卡（含顶部考试名称）。")

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
    """build_report 需 scores.json。优先用家长上传并解析好的小分；
    限时等待其到位；超时则回退 reference（仅当识别到的考试==朝阳物理演示卷）。
    """
    target = student_dir / "scores.json"
    uploaded = UPLOAD_ROOT / aid / "scores.json"

    waited = 0
    while waited < wait_s:
        if uploaded.exists():
            target.write_bytes(uploaded.read_bytes())
            return
        if target.exists():        # 已有（极少：之前流程写过）
            return
        time.sleep(3)
        waited += 3

    # 超时无小分：朝阳物理演示卷回退 reference，其余明确报错
    if student_dir.name == REF_STUDENT_DIR.name and \
       (REF_STUDENT_DIR / "scores.json").exists():
        target.write_bytes((REF_STUDENT_DIR / "scores.json").read_bytes())
        return
    raise RuntimeError(
        "未收到小分表。请在「上传小分」步骤上传班小二导出的 xlsx "
        "（主观题得分需小分表才能分析）。")


def _run(aid: str, student_dir: Path, ocr_photos: bool):
    with _lock:
        try:
            db.update_stage(aid, 1, "识别考试信息")
            db.update_stage(aid, 2, "识别答题卡作答")
            if ocr_photos:
                student_dir = _ocr_answer_card(aid, student_dir)
                _ensure_scores(aid, student_dir)

            def on_stage(idx: int, name: str):
                db.update_stage(aid, idx, name)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")
