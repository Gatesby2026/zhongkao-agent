"""原始件 ↔ 派生件 路径约定（单一真相，避免各脚本各自硬编码）。

设计（见 docs/specs/KB-LAYOUT.md 五域结构）：
  - knowledge-original/ 只放**原始件**（images/page-*.png、source.html、urls.txt）
  - 结构化派生中间件（pages OCR、layout-cache、structured-cloud）落
    knowledge-base/exams/_staging/<subject>/<slug>/
  - enrich 最终 yaml → knowledge-base/exams/mock/<subject>/beijing/<slug>.yaml
    （figures 由 enrich 从 _staging 复制到最终 yaml 旁，非本函数职责）

映射：
  knowledge-original/<set>/<type>/<region>/<subject>
    → knowledge-base/exams/_staging/<subject>/<year>-<region>-<typ>/
"""
from __future__ import annotations

import re
from pathlib import Path

_TYPE = {"yimo": "yi", "ermo": "er", "sanmo": "san", "zhenti": "zhen"}


def repo_root(start: Path) -> Path:
    """从 start 向上找含 knowledge-base 的仓库根。"""
    cur = start.resolve()
    while cur.parent != cur:
        if (cur / "knowledge-base").is_dir():
            return cur
        cur = cur.parent
    raise FileNotFoundError(f"未找到含 knowledge-base 的仓库根（从 {start}）")


def derive_out_dir(src_dir: Path) -> Path:
    """原始卷目录 → 派生 staging 目录（knowledge-base/exams/_staging 下）。

    src_dir 形如 .../knowledge-original/beijing-mock-2026/yimo/daxing/physics
    返回   .../knowledge-base/exams/_staging/physics/2026-daxing-yi
    """
    src = src_dir.resolve()
    subject = src.name                        # physics
    region = src.parent.name                  # daxing
    type_dir = src.parent.parent.name         # yimo
    set_dir = src.parent.parent.parent.name   # beijing-mock-2026
    m = re.search(r"(\d{4})", set_dir)
    year = m.group(1) if m else "0000"
    typ = _TYPE.get(type_dir, type_dir)
    slug = f"{year}-{region}-{typ}"
    return (repo_root(src) / "knowledge-base" / "exams" / "_staging"
            / subject / slug)
