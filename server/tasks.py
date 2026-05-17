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

ROOT = Path(__file__).resolve().parents[1]
SR_DIR = ROOT / "scripts" / "answer-card-ocr"

# 串行单 worker（OCR/LLM 内部已并发；任务间排队避免打爆 API 配额）
_lock = threading.Lock()


def submit(aid: str, student_dir: Path, ocr_photos: bool = False):
    t = threading.Thread(target=_run, args=(aid, student_dir, ocr_photos),
                         daemon=True)
    t.start()


def _ocr_answer_card(student_dir: Path):
    """跑 detect.py 对 answer-card-photos/ 真实涂卡识别 → answer-card.json。"""
    photos_dir = student_dir / "answer-card-photos"
    imgs = sorted(
        p for p in photos_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic")
        and p.stat().st_size > 1024  # 跳过空/损坏文件
    )
    if not imgs:
        raise RuntimeError("answer-card-photos 无有效图片（空或格式不符）")

    sys.path.insert(0, str(SR_DIR))
    import detect  # noqa

    res = detect.detect_card(imgs, photos_dir=photos_dir)
    out = {
        "student": getattr(res, "student", {}) or {},
        "answers": getattr(res, "answers", []),
    }
    (student_dir / "answer-card.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(aid: str, student_dir: Path, ocr_photos: bool):
    with _lock:
        try:
            db.update_stage(aid, 1, "识别考试信息")
            time.sleep(0.2)

            db.update_stage(aid, 2, "识别答题卡作答")
            if ocr_photos:
                _ocr_answer_card(student_dir)

            def on_stage(idx: int, name: str):
                db.update_stage(aid, idx, name)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")
