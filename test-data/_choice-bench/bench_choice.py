#!/usr/bin/env python3
"""选择题涂卡识别 benchmark。

跑 cases/<case>/page-*.jpg 通过 Path B → 跟 ground-truth.yaml 真值对比，
输出每 case + 全局命中率。

用法：
  python3 test-data/_choice-bench/bench_choice.py [--verbose] [case_name]
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "answer-card-ocr"))
from detect import detect_choices_by_blob, detect_choices_by_tencent


def _detect_combined(image_paths):
    """模拟 detect_card 的 Path B → Path C fallback。"""
    r = detect_choices_by_blob(image_paths)
    n_filled = sum(1 for v in r.values() if v.get("filled"))
    if n_filled >= 5:
        return r, "blob"
    try:
        t = detect_choices_by_tencent(image_paths)
        if t:
            return t, "tencent"
    except Exception as e:
        print(f"  [warn] tencent path failed: {e}", file=sys.stderr)
    return r, "blob-fallback"

CASES_ROOT = Path(__file__).resolve().parent / "cases"


def _qid_int(q):
    s = str(q).strip().upper().lstrip("Q")
    return int(s) if s.isdigit() else 0


def bench_one(case_dir: Path, verbose: bool = False) -> tuple[int, int, dict]:
    """跑一个 case，返回 (命中数, 总数, 详情)。"""
    gt_path = case_dir / "ground-truth.yaml"
    if not gt_path.exists():
        return 0, 0, {"error": "no ground-truth.yaml"}

    gt = yaml.safe_load(gt_path.read_text(encoding="utf-8")) or {}
    truth = {_qid_int(q): str(v).strip().upper()
             for q, v in (gt.get("answers") or {}).items()}
    if not truth:
        return 0, 0, {"error": "empty answers"}

    photos = sorted(p for p in case_dir.iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png")
                    and p.name.startswith("page-"))
    if not photos:
        return 0, 0, {"error": "no photos"}

    pred, used = _detect_combined(photos)
    if verbose:
        print(f"  [{case_dir.name}] engine={used}", file=sys.stderr)
    pred_clean = {}
    for q, v in pred.items():
        f = v.get("filled") or ""
        if isinstance(f, list):
            f = "".join(f)
        pred_clean[q] = str(f).strip().upper()

    hit = 0
    miss = []
    for qid, t in sorted(truth.items()):
        p = pred_clean.get(qid, "")
        if p == t:
            hit += 1
        else:
            miss.append((qid, t, p))

    return hit, len(truth), {
        "slug": gt.get("slug"),
        "student": gt.get("student"),
        "layout": gt.get("layout"),
        "misses": miss,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case", nargs="?", help="只跑指定 case，省略=全部")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="打印每题对比")
    args = ap.parse_args()

    if not CASES_ROOT.is_dir():
        print(f"cases 目录不存在: {CASES_ROOT}", file=sys.stderr)
        return 1

    targets = sorted(d for d in CASES_ROOT.iterdir() if d.is_dir())
    if args.case:
        targets = [d for d in targets if d.name == args.case]
        if not targets:
            print(f"未找到 case: {args.case}", file=sys.stderr)
            return 1

    print(f"{'case':<40s} {'layout':<14s} {'hit':>4s}  {'total':>5s}  {'rate':>6s}")
    print("-" * 78)
    tot_h = tot_n = 0
    for d in targets:
        try:
            h, n, info = bench_one(d, verbose=args.verbose)
        except Exception as e:
            print(f"{d.name:<40s} ERROR: {e}")
            continue
        if "error" in info:
            print(f"{d.name:<40s} ⚠️  {info['error']}")
            continue
        tot_h += h; tot_n += n
        rate = f"{100*h/n:.0f}%" if n else "0%"
        print(f"{d.name:<40s} {info['layout'] or '-':<14s} "
              f"{h:>4d}  {n:>5d}  {rate:>6s}")
        if args.verbose and info["misses"]:
            for qid, t, p in info["misses"]:
                print(f"    Q{qid}: 真值={t!r}  识别={p!r}")
    print("-" * 78)
    rate = f"{100*tot_h/tot_n:.1f}%" if tot_n else "0%"
    print(f"{'合计':<40s} {'':<14s} {tot_h:>4d}  {tot_n:>5d}  {rate:>6s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
