#!/usr/bin/env python3
"""[一次性] KB-LAYOUT 阶段4：知识层注入结构化 meta.quality_status 块。

把埋在注释头里的「状态/来源/更新」自由文本 → 可查询可门禁的 meta 块。
范围：pedagogy + prep(排除 question-banks，其自带 meta) + policies + admission。
已有 ^meta: 的文件跳过（不覆盖）。注释头保留（含更丰富 prose）。

quality_status 取值（KB-LAYOUT §3 enum）：
  llm_draft       注释含「LLM生成初稿/待(教师)审核」→ 机器生成待审
  curated         注释含「数据来源/来源」权威源、无 LLM 标记 → 人工据权威源整理、未经本系统复核
  （teacher_reviewed/verified 只能人工提升，脚本不臆造）
无任何信息 → 保守 llm_draft。

用法： python3 kb_add_meta.py [--dry]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "knowledge-base"
DOMAINS = [KB / "pedagogy", KB / "prep", KB / "policies", KB / "admission"]
DRY = "--dry" in sys.argv

LLM_RE = re.compile(r"LLM\s*生成初稿|待教师审核|待审核|LLM\s*初稿")
SRC_RE = re.compile(r"^#\s*(?:数据来源|来源)\s*[:：]\s*(.+?)\s*$")
UPD_RE = re.compile(r"^#\s*(?:最后更新|更新)\s*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")


def classify(text: str) -> tuple[str, str, str]:
    head = "\n".join(text.splitlines()[:15])
    status = "llm_draft" if LLM_RE.search(head) else None
    src, upd = "", ""
    for ln in text.splitlines()[:15]:
        m = SRC_RE.match(ln)
        if m and not src:
            src = m.group(1)
        m = UPD_RE.match(ln)
        if m and not upd:
            upd = m.group(1)
    if status is None:
        status = "curated" if src else "llm_draft"
    return status, src, upd


def meta_block(status: str, src: str, upd: str) -> list[str]:
    s = src.replace('"', "'")
    return [
        "meta:",
        f"  quality_status: {status}   # llm_draft|curated|teacher_reviewed|verified",
        f'  source: "{s}"' if s else "  source: \"\"",
        f"  updated: {upd}" if upd else '  updated: ""',
        "  reviewed_by: null",
        "",
    ]


def first_top_key_idx(lines: list[str]) -> int:
    for i, ln in enumerate(lines):
        if ln[:1].isalpha():           # 首个顶层键（注释/空行之后）
            return i
    return len(lines)


def main() -> None:
    n_skip = n_done = 0
    stat = {"llm_draft": 0, "curated": 0}
    for dom in DOMAINS:
        if not dom.is_dir():
            continue
        for f in sorted(dom.rglob("*.yaml")):
            if "question-banks" in f.parts:        # 自带 meta，不碰
                continue
            txt = f.read_text(encoding="utf-8")
            if re.search(r"(?m)^meta:", txt):
                n_skip += 1
                continue
            status, src, upd = classify(txt)
            stat[status] = stat.get(status, 0) + 1
            lines = txt.splitlines()
            k = first_top_key_idx(lines)
            block = meta_block(status, src, upd)
            new = lines[:k] + block + lines[k:]
            if not DRY:
                f.write_text("\n".join(new) + "\n", encoding="utf-8")
            n_done += 1
    print(f"注入 {n_done}（llm_draft={stat['llm_draft']} "
          f"curated={stat['curated']}），跳过已有 meta {n_skip}"
          f"{' [dry]' if DRY else ''}")


if __name__ == "__main__":
    main()
