"""PaddleOCR LayoutDetection 封装：替代 qwen-vl-max 做图形定位。

核心理念：
- LayoutDetection 是专为文档版面训练的 CV 模型，输出像素级 bbox + 标签
- 完全离线，无 API 调用，确定性输出
- 替代之前 qwen-vl-max 的 locate_figures_on_page() 调用

接口：
    detector = LayoutDetector()
    boxes = detector.detect(page_img_path)
    # boxes = [{"label": "image", "bbox": [x1,y1,x2,y2], "score": 0.84}, ...]

标签类型（PP-DocLayout_plus-L 模型）：
    text          — 题干/选项文字段
    image         — 图形（电路图/光路图/实物图/几何图等）
    figure_title  — 图注（如"图甲"/"图乙"/"第N题图"）
    table         — 表格
    formula       — 公式
    title / number / footer — 标题/页码/页脚
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


class LayoutDetector:
    """单例 paddle LayoutDetection 包装。

    首次构造会延迟下载模型（~200MB），后续推理 < 30s/页（Intel CPU）。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_done = False
        return cls._instance

    def _ensure_init(self):
        if self._init_done:
            return
        from paddleocr import LayoutDetection
        self._det = LayoutDetection()
        self._init_done = True

    def detect(self, page_img: Path | str) -> list[dict]:
        """对一张页面图做版面检测。

        返回 [{"label": str, "bbox": [x1, y1, x2, y2], "score": float}, ...]
        bbox 是像素坐标（float）。
        """
        self._ensure_init()
        out = []
        for r in self._det.predict(str(page_img)):
            for b in r.json["res"]["boxes"]:
                out.append({
                    "label": b["label"],
                    "bbox": [float(x) for x in b["coordinate"]],
                    "score": float(b["score"]),
                })
            break
        return out


# 全局单例
_default = None
def get_detector() -> LayoutDetector:
    global _default
    if _default is None:
        _default = LayoutDetector()
    return _default
