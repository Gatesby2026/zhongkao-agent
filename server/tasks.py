"""后台任务：5 阶段状态机。

阶段（与 H5 原型 #stages 对齐）：
  1 识别考试信息   2 识别答题卡作答   3 对照标准答案
  4 AI 分析失分主因  5 生成提分建议

Phase 1（纯打通四屏，reference 数据）：
  detect/ocr/align 的产物已在 student_dir 里（answer-card.json / scores.json），
  阶段 1-3 仅作占位推进；真正耗时在 run_report（LLM 归因 + 整卷 + 渲染 PDF）。
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

import db
import pipeline_adapter as pa

ROOT = Path(__file__).resolve().parents[1]

# 串行单 worker（单 ECS，OCR/LLM 已内部并发；任务间排队避免打爆 API 配额）
_lock = threading.Lock()


def submit(aid: str, student_dir: Path):
    t = threading.Thread(target=_run, args=(aid, student_dir), daemon=True)
    t.start()


def _run(aid: str, student_dir: Path):
    with _lock:
        try:
            db.update_stage(aid, 1, "识别考试信息")
            time.sleep(0.3)
            db.update_stage(aid, 2, "识别答题卡作答")
            time.sleep(0.3)

            def on_stage(idx: int, name: str):
                db.update_stage(aid, idx, name)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")
