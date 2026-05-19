#!/usr/bin/env python3
"""run_batch — 批量编排（退化为「循环调 run_paper + 聚合」，无任何步骤逻辑）。

遍历 <src_parent> 下各区 <region>/<subject>，逐卷调 run_paper，收集
<staging>/status.json，汇总到 knowledge-base/exams/mock/<subject>/beijing/
QC_SUMMARY_<subject>.md（DONE-auto / NEEDS_REVIEW / INCOMPLETE / QUARANTINE
分类 + 待人工清单）。

用法：
  DASHSCOPE_API_KEY=$KEY python3 scripts/exam-ocr/run_batch.py \
      knowledge-original/<series>/<round> --subject physics [--dry-run] [--force]
  # 自动遍历 <round>/<region>/<subject>/
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import repo_root  # noqa: E402

PY = sys.executable
SELF = Path(__file__).resolve().parent / "run_paper.py"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src_parent", type=Path, help="如 knowledge-original/<series>/<round>")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    parent = a.src_parent.resolve()
    srcs = sorted(p for p in parent.glob(f"*/{a.subject}") if (p / "images").is_dir())
    if not srcs:
        print(f"[run_batch] {parent} 下无 */{a.subject}/images", file=sys.stderr)
        sys.exit(1)

    rows = []
    for src in srcs:
        region = src.parent.name
        cmd = [PY, str(SELF), str(src), "--subject", a.subject]
        if a.dry_run:
            cmd.append("--dry-run")
        if a.force:
            cmd.append("--force")
        print(f"\n######## {region} ########", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        try:
            st = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            st = {"slug": region, "state": "ERROR",
                  "reasons": [r.stderr.strip()[-300:] or "无 status 输出"]}
        rows.append(st)
        print(f"  {st.get('state')}  {st.get('slug')}"
              f"  needs_review={len(st.get('needs_review', []))}", flush=True)

    # 汇总
    by = {}
    for s in rows:
        by.setdefault(s.get("state", "ERROR"), []).append(s)
    out_dir = (repo_root(parent) / "knowledge-base" / "exams" / "mock"
               / a.subject / "beijing")
    out_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# 批量结构化汇总 · {a.subject}", "",
          f"源：`{parent}`　共 {len(rows)} 卷", ""]
    for state in ["DONE-auto", "NEEDS_REVIEW", "INCOMPLETE",
                  "QUARANTINE", "DRY", "ERROR"]:
        g = by.get(state, [])
        if not g:
            continue
        md.append(f"## {state}（{len(g)}）")
        for s in g:
            md.append(f"- **{s.get('slug')}**"
                      + (f" — needs_review {len(s.get('needs_review', []))}"
                         if s.get("needs_review") else "")
                      + (f" — {'; '.join(s.get('reasons', []))}"
                         if s.get("reasons") else ""))
            for nr in s.get("needs_review", []):
                md.append(f"  - {nr}")
        md.append("")
    summary = out_dir / f"QC_SUMMARY_{a.subject}.md"
    summary.write_text("\n".join(md), encoding="utf-8")

    counts = {k: len(v) for k, v in by.items()}
    print(f"\nALL DONE → {summary}")
    print("  " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    sys.exit(0 if not (by.get("INCOMPLETE") or by.get("ERROR")) else 2)


if __name__ == "__main__":
    main()
