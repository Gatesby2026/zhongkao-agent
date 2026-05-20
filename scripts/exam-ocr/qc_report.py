#!/usr/bin/env python3
"""单卷结构化质量评估（对照 skill 质量基线）。

质量基线（skill_exam_image_to_kb_yaml.md）：
  - 题数完整、题号连续无断号
  - 选择题 options 必须 A/B/C/D 4 个齐全
  - 非选择题不应误带 options
  - stem 无 LaTeX `\\` / 末尾孤立 `\\` 残留
  - source_page 全覆盖
  - 分值合计 == full_score
  - 非选择题 solution 覆盖
  - 含图题 figure_path 命中率

用法:
  python3 qc_report.py <staging_dir>          # 评 <staging>/structured-cloud/final.json
                                              # （staging = knowledge-base/.../<slug>/）
  python3 qc_report.py --yaml <kb_yaml>       # 评最终 yaml
退出码：0=达标(无 error)，1=有 error 级问题
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

CHOICE = {"choice", "multi_choice", "单选", "多选"}


def _qnum(qid):
    m = re.search(r"(\d+)", str(qid))
    return int(m.group(1)) if m else 0


def eval_final(paper_dir: Path) -> dict:
    """评 final.json（exam-ocr 中间产物）。"""
    fj = paper_dir / "structured-cloud" / "final.json"
    d = json.loads(fj.read_text(encoding="utf-8"))
    qs = d.get("questions", [])
    ans = {a["number"]: a for a in d.get("answers", [])}
    errs, warns = [], []

    nums = sorted(q["number"] for q in qs)
    # 题号连续
    if nums:
        gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
        if gaps:
            errs.append(f"题号断号: {gaps}")
    # 选择题 options（has_image_options=True 时 options 可缺—图选项题）
    for q in qs:
        n, t = q["number"], q.get("type", "")
        opts = q.get("options")
        if t in CHOICE:
            has_img = q.get("has_image_options")
            if not opts and not has_img:
                errs.append(f"Q{n} 选择题 options 不全: {sorted((opts or {}).keys())}")
            elif opts and not has_img and set(opts) != {"A", "B", "C", "D"}:
                errs.append(f"Q{n} 选择题 options 不全: {sorted((opts or {}).keys())}")
        else:
            if opts:
                warns.append(f"Q{n} 非选择题({t})误带 options")
        # stem 残留
        st = q.get("stem", "")
        if re.search(r"\\\\(?![a-z]{2,})", st) or st.rstrip().endswith("\\"):
            warns.append(f"Q{n} stem 疑似 LaTeX `\\\\` 残留")
        if "\\[" in st and "pt]" in st:
            warns.append(f"Q{n} stem 含 `\\[Npt]` 排版残留")
        # source_page
        if not q.get("source_page"):
            errs.append(f"Q{n} 缺 source_page")
    # 分值
    fs = d.get("full_score")
    tot = sum(q.get("score", 0) for q in qs)
    if fs and tot != fs:
        errs.append(f"分值合计 {tot} ≠ full_score {fs}")
    # solution 覆盖（非选择题）
    nosol = [q["number"] for q in qs
             if q.get("type") not in CHOICE
             and not (ans.get(q["number"], {}).get("solution") or "").strip()]
    if nosol:
        warns.append(f"非选择题缺 solution: {nosol}")
    # 含图命中
    figq = [q["number"] for q in qs
            if ("如图" in (q.get("stem") or "") or "[图]" in (q.get("stem") or ""))]
    nofig = [n for n in figq
             if not next((q for q in qs if q["number"] == n), {}).get("figure_path")]
    fig_line = (f"含图题 {len(figq)}，已裁切 {len(figq)-len(nofig)}"
                + (f"，未裁: {nofig}" if nofig else ""))

    return {
        "name": paper_dir.name, "src": str(fj),
        "n_q": len(qs), "full_score": fs, "score_sum": tot,
        "errs": errs, "warns": warns, "fig": fig_line,
    }


def eval_yaml(yp: Path) -> dict:
    """评最终 knowledge-base yaml。"""
    d = yaml.safe_load(yp.read_text(encoding="utf-8"))
    qs = d.get("questions", [])
    errs, warns = [], []
    nums = sorted(_qnum(q.get("id")) for q in qs)
    if nums:
        gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
        if gaps:
            errs.append(f"题号断号: {gaps}")
    for q in qs:
        n = _qnum(q.get("id")); t = q.get("type", "")
        if t in CHOICE:
            o = q.get("options")
            if not o or set(o) != {"A", "B", "C", "D"}:
                errs.append(f"Q{n} options 不全")
        if not str(q.get("answer", "")).strip():
            errs.append(f"Q{n} answer 空")
        if t in {"实验探究", "解答", "计算", "填空"} and \
           not str(q.get("solution", "")).strip():
            warns.append(f"Q{n} {t} solution 空")
        if not q.get("knowledge_points"):
            warns.append(f"Q{n} knowledge_points 空")
        if q.get("qc_status") == "needs_review":
            warns.append(f"Q{n} needs_review: {q.get('qc_note','')}")
    fs = d.get("full_score")
    tot = sum(q.get("score", 0) for q in qs)
    if fs and tot != fs:
        errs.append(f"分值合计 {tot} ≠ full_score {fs}")
    return {
        "name": yp.stem, "src": str(yp),
        "n_q": len(qs), "full_score": fs, "score_sum": tot,
        "errs": errs, "warns": warns, "fig": "",
    }


def _print(r: dict) -> bool:
    ok = not r["errs"]
    badge = "✅ 达标" if ok else "❌ 不达标"
    print(f"\n{'='*54}")
    print(f"[{r['name']}] {badge}")
    print(f"  题数={r['n_q']}  分值合计={r['score_sum']}/{r['full_score']}")
    if r["fig"]:
        print(f"  {r['fig']}")
    if r["errs"]:
        print(f"  ❌ error ({len(r['errs'])}):")
        for e in r["errs"]:
            print(f"     - {e}")
    if r["warns"]:
        print(f"  ⚠️  warn ({len(r['warns'])}):")
        for w in r["warns"][:10]:
            print(f"     - {w}")
    if ok and not r["warns"]:
        print("  🎉 零问题")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper_dir", nargs="?", type=Path)
    ap.add_argument("--yaml", type=Path)
    args = ap.parse_args()
    if args.yaml:
        r = eval_yaml(args.yaml)
    elif args.paper_dir:
        r = eval_final(args.paper_dir)
    else:
        ap.error("需 paper_dir 或 --yaml")
    sys.exit(0 if _print(r) else 1)


if __name__ == "__main__":
    main()
