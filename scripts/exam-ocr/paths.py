"""原始件 ↔ 派生件 路径约定（单一真相，避免各脚本各自硬编码）。

设计：
  - knowledge-original/ 只放**原始件**（images/page-*.png、source.html、urls.txt）
  - 结构化/派生件（pages OCR、layout-cache、structured-cloud、figures）
    全部落 knowledge-base/ 的 per-卷 staging 目录
  - enrich 最终 yaml 是 staging 目录的同名兄弟文件（既有约定，未变）

映射：
  knowledge-original/<set>/<type>/<region>/<subject>
    → knowledge-base/mock-exams/<subject>/beijing/<year>-<region>-<typ>/
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
    """原始卷目录 → 派生 staging 目录（knowledge-base 下）。

    src_dir 形如 .../knowledge-original/beijing-mock-2026/yimo/daxing/physics
    返回   .../knowledge-base/mock-exams/physics/beijing/2026-daxing-yi
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
    return (repo_root(src) / "knowledge-base" / "mock-exams"
            / subject / "beijing" / slug)
