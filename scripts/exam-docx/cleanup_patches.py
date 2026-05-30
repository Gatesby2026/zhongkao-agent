#!/usr/bin/env python3
"""清理 _patches/<subject>/<slug>.yaml 中的冗余 / 退化字段。

清理规则（A 档 — 0 风险自动清）：
  1. REDUNDANT：patch.value == mock.value（标准化后）→ 删
  2. CONFLICT 中明显退化的：
     - patch.value 是 "[图]" 占位符 → 删（mock 是 docx 抽的真文本，更可信）
     - patch.value 是无 LaTeX 的纯文本 + mock.value 是 LaTeX（含 $） → 删
     - patch.value 是 ASCII 标点替代版 + mock.value 是 Unicode 标点 → 留（不动）

保留：
  - FILL-IN：mock 字段空 + patch 有值 → 保留（docx 抓不到的字段补漏）
  - 真冲突：score 数字、长 solution、关键 answer → 保留人工 review

使用：
  python3 scripts/exam-docx/cleanup_patches.py [--dry]
"""
from __future__ import annotations
import argparse
import re
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "knowledge-base" / "exams"
PATCHES_ROOT = KB / "_patches"
PRE_BAKE_REV = "HEAD~1"

yaml_rw = YAML()
yaml_rw.preserve_quotes = True
yaml_rw.indent(mapping=2, sequence=4, offset=2)
yaml_rw.width = 4096


def _load_mock_pre_bake(subject: str, slug: str) -> dict:
    rel = f"knowledge-base/exams/mock/{subject}/beijing/{slug}.yaml"
    try:
        out = subprocess.run(
            ["git", "show", f"{PRE_BAKE_REV}:{rel}"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        import yaml as pyyaml
        return pyyaml.safe_load(out.stdout) or {}
    except subprocess.CalledProcessError:
        return {}


def _norm(v):
    if v is None: return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, list) and not v: return None
    if isinstance(v, dict) and not v: return None
    return v


def _qid_to_int(qid):
    if isinstance(qid, int): return qid
    s = str(qid).strip().upper().lstrip("Q")
    return int(s) if s.isdigit() else None


def _has_latex(v) -> bool:
    """值含 LaTeX 公式（含 $...$ 或常见 LaTeX 控制序列）。"""
    if not isinstance(v, str):
        if isinstance(v, dict):
            return any(_has_latex(x) for x in v.values())
        if isinstance(v, list):
            return any(_has_latex(x) for x in v)
        return False
    return "$" in v or "\\" in v


def _is_image_placeholder(v) -> bool:
    """值是 '[图]' 占位符（或全是 [图]）。"""
    if isinstance(v, str):
        return v.strip() == "[图]"
    if isinstance(v, dict):
        return all(_is_image_placeholder(x) for x in v.values())
    if isinstance(v, list):
        return all(_is_image_placeholder(x) for x in v)
    return False


def _is_degraded_text_vs_latex(p_val, m_val) -> bool:
    """patch 是无 LaTeX 的纯文本 + mock 含 LaTeX → degraded。"""
    if not _has_latex(m_val):
        return False
    if _has_latex(p_val):
        return False
    return True


def classify(p_val, m_val) -> str:
    """返回 'redundant' / 'degraded' / 'keep'。"""
    n_p = _norm(p_val)
    n_m = _norm(m_val)
    if n_m is None and n_p is not None:
        return "keep"  # FILL-IN
    if n_m == n_p:
        return "redundant"
    # CONFLICT 子分类
    if _is_image_placeholder(p_val) and not _is_image_placeholder(m_val):
        return "degraded"
    if _is_degraded_text_vs_latex(p_val, m_val):
        return "degraded"
    return "keep"  # 真冲突，留人工 review


def cleanup_one(patch_path: Path, subject: str, slug: str, dry: bool):
    """处理一份 patch。返回 (删 redundant 数, 删 degraded 数, 保留数)。"""
    mock_pre = _load_mock_pre_bake(subject, slug)
    if not mock_pre:
        return 0, 0, 0

    by_id = {}
    for q in (mock_pre.get("questions") or []):
        i = _qid_to_int(q.get("id") or q.get("qId") or q.get("num"))
        if i is not None:
            by_id[i] = q

    with patch_path.open(encoding="utf-8") as f:
        data = yaml_rw.load(f)

    if data is None or "questions" not in data:
        return 0, 0, 0

    n_red = 0
    n_deg = 0
    n_keep = 0

    qs_to_del = []
    for raw_qid in list(data["questions"].keys()):
        i = _qid_to_int(raw_qid)
        fields = data["questions"][raw_qid]
        if i is None or not isinstance(fields, dict):
            continue
        mock_q = by_id.get(i)
        if mock_q is None:
            continue

        fields_to_del = []
        for fname in list(fields.keys()):
            p_val = fields[fname]
            m_val = mock_q.get(fname)
            cls = classify(p_val, m_val)
            if cls == "redundant":
                fields_to_del.append(fname)
                n_red += 1
            elif cls == "degraded":
                fields_to_del.append(fname)
                n_deg += 1
            else:
                n_keep += 1

        for fname in fields_to_del:
            del fields[fname]
        if not fields:
            qs_to_del.append(raw_qid)

    for qid in qs_to_del:
        del data["questions"][qid]

    if not data["questions"]:
        # 全空了 → 不删文件（保留头部注释），仅留空 questions 字典
        data["questions"] = {}

    if not dry and (n_red + n_deg) > 0:
        with patch_path.open("w", encoding="utf-8") as f:
            yaml_rw.dump(data, f)

    return n_red, n_deg, n_keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只统计不写")
    args = ap.parse_args()

    targets = []
    for subj_dir in sorted(PATCHES_ROOT.iterdir()):
        if not subj_dir.is_dir(): continue
        for f in sorted(subj_dir.glob("*.yaml")):
            targets.append((f, subj_dir.name, f.stem))

    print(f"{'subject/slug':<45}  删冗余  删退化  保留")
    print("-" * 78)
    tot_r = tot_d = tot_k = 0
    for path, subj, slug in targets:
        nr, nd, nk = cleanup_one(path, subj, slug, dry=args.dry)
        tot_r += nr; tot_d += nd; tot_k += nk
        if nr + nd > 0:
            print(f"{subj}/{slug:<37}  {nr:>6}  {nd:>6}  {nk:>4}")
    print("-" * 78)
    print(f"{'合计':<45}  {tot_r:>6}  {tot_d:>6}  {tot_k:>4}")
    print()
    print(f"删除 REDUNDANT  {tot_r:4d} 条（patch == mock 冗余）")
    print(f"删除 DEGRADED   {tot_d:4d} 条（patch 是 [图]/无 LaTeX 退化版）")
    print(f"保留           {tot_k:4d} 条（FILL-IN + 真冲突，人工 review）")
    if args.dry:
        print("\n[dry-run] 未修改文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())
