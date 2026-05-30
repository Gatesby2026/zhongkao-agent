#!/usr/bin/env python3
"""审计 _patches/ 与烘合前 mock yaml 的差异，区分冗余 vs 真补丁 vs 冲突。

3 类输出：
  FILL-IN   mock 字段缺/空 + patch 有值 → docx parser 抓不到，patch 真的在补
  REDUNDANT mock 与 patch 值完全一致   → 历史包袱，可从 _patches/ 删
  CONFLICT  mock 与 patch 值不同      → 可能旧 OCR 修复覆盖了 docx 真值，要人工 review

使用：
  python3 scripts/exam-docx/audit_patches.py [--subject SUB] [--slug SLUG] [--show-conflicts]

  --show-conflicts  详细打印每条 CONFLICT 的 mock 值 vs patch 值
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "knowledge-base" / "exams"
PATCHES_ROOT = KB / "_patches"
MOCK_ROOT = KB / "mock"

# 烘合提交（bake_patches.py 第一次跑）。HEAD~1 就是烘合前 mock 状态。
PRE_BAKE_REV = "HEAD~1"


def _load_yaml_text(text: str) -> dict:
    return yaml.safe_load(text) or {}


def _load_mock_pre_bake(subject: str, slug: str) -> dict:
    """从 git 历史拿烘合前 mock yaml。"""
    rel = f"knowledge-base/exams/mock/{subject}/beijing/{slug}.yaml"
    try:
        out = subprocess.run(
            ["git", "show", f"{PRE_BAKE_REV}:{rel}"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return _load_yaml_text(out.stdout)
    except subprocess.CalledProcessError:
        return {}


def _norm(v):
    """标准化值用于对比。空白字符串/None 统一成 None。"""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, list) and len(v) == 0:
        return None
    if isinstance(v, dict) and len(v) == 0:
        return None
    return v


def _qid_to_int(qid) -> int | None:
    if isinstance(qid, int):
        return qid
    s = str(qid).strip().upper().lstrip("Q")
    return int(s) if s.isdigit() else None


def audit_one(patch_path: Path, subject: str, slug: str,
               show_conflicts: bool = False) -> dict:
    """审计一份 patch。返回 {fill_in, redundant, conflict, conflicts: [...]}。"""
    patch = _load_yaml_text(patch_path.read_text(encoding="utf-8"))
    mock_pre = _load_mock_pre_bake(subject, slug)
    if not mock_pre:
        return {"fill_in": 0, "redundant": 0, "conflict": 0, "missing_mock": True,
                "conflicts": []}

    # 把 mock_pre questions 按 id 索引
    by_id: dict[int, dict] = {}
    for q in (mock_pre.get("questions") or []):
        i = _qid_to_int(q.get("id") or q.get("qId") or q.get("num"))
        if i is not None:
            by_id[i] = q

    fill_in = redundant = conflict = 0
    conflicts: list[dict] = []

    patch_qs = patch.get("questions") or {}
    for raw_qid, fields in patch_qs.items():
        i = _qid_to_int(raw_qid)
        if i is None or not isinstance(fields, dict):
            continue
        mock_q = by_id.get(i)
        if mock_q is None:
            continue  # patch 引用了不存在的题号（已在 bake 时 warn）
        for fname, p_val in fields.items():
            m_val = mock_q.get(fname)
            n_m = _norm(m_val)
            n_p = _norm(p_val)
            if n_m is None and n_p is not None:
                fill_in += 1
            elif n_m == n_p:
                redundant += 1
            else:
                conflict += 1
                if show_conflicts:
                    conflicts.append({
                        "qid": i, "field": fname,
                        "mock": _truncate(repr(n_m), 100),
                        "patch": _truncate(repr(n_p), 100),
                    })

    return {"fill_in": fill_in, "redundant": redundant, "conflict": conflict,
            "conflicts": conflicts}


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", help="只审某科")
    ap.add_argument("--slug", help="只审某卷")
    ap.add_argument("--show-conflicts", action="store_true",
                    help="打印每条 CONFLICT 详情（mock 值 vs patch 值）")
    args = ap.parse_args()

    targets: list[tuple[Path, str, str]] = []
    for subj_dir in sorted(PATCHES_ROOT.iterdir()):
        if not subj_dir.is_dir():
            continue
        subj = subj_dir.name
        if args.subject and subj != args.subject:
            continue
        for f in sorted(subj_dir.glob("*.yaml")):
            slug = f.stem
            if args.slug and slug != args.slug:
                continue
            targets.append((f, subj, slug))

    if not targets:
        print("无匹配")
        return 0

    print(f"{'subject/slug':<45}  fill_in  redund  conflict")
    print("-" * 78)
    tot_fill = tot_red = tot_conf = 0
    all_conflicts: list[tuple[str, dict]] = []
    for path, subj, slug in targets:
        r = audit_one(path, subj, slug, show_conflicts=args.show_conflicts)
        tag = f"{subj}/{slug}"
        if r.get("missing_mock"):
            print(f"{tag:<45}  (mock pre-bake 不存在)")
            continue
        print(f"{tag:<45}  {r['fill_in']:>7}  {r['redundant']:>6}  "
              f"{r['conflict']:>8}")
        tot_fill += r["fill_in"]
        tot_red += r["redundant"]
        tot_conf += r["conflict"]
        for c in r["conflicts"]:
            all_conflicts.append((tag, c))

    print("-" * 78)
    print(f"{'合计':<45}  {tot_fill:>7}  {tot_red:>6}  {tot_conf:>8}")
    print()
    print(f"FILL-IN   {tot_fill:4d} 条 → patch 在补 docx parser 抓不到的字段，保留")
    print(f"REDUNDANT {tot_red:4d} 条 → mock 与 patch 已一致，可从 _patches 删（无害）")
    print(f"CONFLICT  {tot_conf:4d} 条 → mock 与 patch 不一致 → ⚠️ 需人工 review")

    if args.show_conflicts and all_conflicts:
        print()
        print(f"=== CONFLICT 详情（{len(all_conflicts)} 条）===")
        cur_tag = None
        for tag, c in all_conflicts:
            if tag != cur_tag:
                print(f"\n[{tag}]")
                cur_tag = tag
            print(f"  Q{c['qid']}.{c['field']}")
            print(f"    mock:  {c['mock']}")
            print(f"    patch: {c['patch']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
