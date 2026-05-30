#!/usr/bin/env python3
"""把 knowledge-base/exams/_patches/ 下的修正层 merge 进对应 mock yaml。

为啥要有：
- _patches/<subject>/<slug>.yaml 是人工对 mock yaml 的字段修正（如 OCR 错读、分值识别错等）
- 早期设计：parser 重跑 mock 时自动 apply 一次。但 patches 字段（如 solution）不一定全被烘进 mock
- 生产链路只读 mock，看不到 _patches → 报告/原题展示用了未修正版本

为啥不用运行时 merge：保持生产端零额外加载逻辑。烘合在部署前一次性完成。

工作流：
  parser 重跑 mock yaml → 跑本脚本 → mock 含全部修正 → commit + 同步生产

使用：
  python3 scripts/exam-docx/bake_patches.py [--dry] [--subject chinese] [--slug 2026-chaoyang-er]

  --dry         只打印 diff 不写回
  --subject     仅处理指定学科（chinese/math/english/physics/politics）
  --slug        仅处理指定 slug
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from copy import deepcopy

import yaml


ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "knowledge-base" / "exams"
PATCHES_ROOT = KB / "_patches"
MOCK_ROOT = KB / "mock"


def _load(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _dump(p: Path, data: dict):
    p.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8",
    )


def _qid_to_int(qid) -> int | None:
    if isinstance(qid, int):
        return qid
    s = str(qid).strip().upper().lstrip("Q")
    return int(s) if s.isdigit() else None


def merge_questions(mock_qs: list[dict], patch_qs: dict) -> int:
    """patch_qs: {qid_int_or_str: {field: value, ...}}. 原地改 mock_qs。返回应用数。"""
    by_id: dict[int, dict] = {}
    for q in mock_qs:
        i = _qid_to_int(q.get("id") or q.get("qId") or q.get("num"))
        if i is not None:
            by_id[i] = q

    applied = 0
    for raw_qid, fields in patch_qs.items():
        i = _qid_to_int(raw_qid)
        if i is None or not isinstance(fields, dict):
            continue
        q = by_id.get(i)
        if q is None:
            print(f"      ⚠️ Q{i} 在 mock 中不存在，patch 字段跳过: {list(fields)}",
                  file=sys.stderr)
            continue
        for k, v in fields.items():
            # 简单覆盖语义：patch 字段直接替换 mock 字段
            # （未来若需 dict merge / list append，可扩展）
            q[k] = v
        applied += 1
    return applied


def merge_passages(mock_ps: list[dict] | None, patch_ps: dict) -> tuple[list[dict], int]:
    """passages 是 list[dict]，patch 用 id 索引。返回 (新 list, 应用数)。"""
    mock_ps = mock_ps or []
    by_id: dict[str, dict] = {}
    for p in mock_ps:
        pid = str(p.get("id") or "")
        if pid:
            by_id[pid] = p

    applied = 0
    for pid, fields in patch_ps.items():
        if not isinstance(fields, dict):
            continue
        pid_s = str(pid)
        if pid_s in by_id:
            for k, v in fields.items():
                by_id[pid_s][k] = v
        else:
            # 新建 passage（patch 用 create 语义）
            new_p = {"id": pid_s, **fields}
            mock_ps.append(new_p)
            by_id[pid_s] = new_p
        applied += 1
    return mock_ps, applied


def bake_one(patch_path: Path, subject: str, slug: str,
              dry: bool = False) -> tuple[bool, int, int]:
    """处理一份 patch → mock。返回 (是否动了 mock, Q 应用数, passage 应用数)。"""
    mock_path = MOCK_ROOT / subject / "beijing" / f"{slug}.yaml"
    if not mock_path.exists():
        print(f"  ⚠️ mock 文件不存在: {mock_path}", file=sys.stderr)
        return False, 0, 0

    patch = _load(patch_path)
    mock = _load(mock_path)
    mock_before = deepcopy(mock)

    q_applied = 0
    p_applied = 0

    if isinstance(patch.get("questions"), dict):
        if not isinstance(mock.get("questions"), list):
            print(f"  ⚠️ mock.questions 不是 list，跳过: {mock_path}", file=sys.stderr)
        else:
            q_applied = merge_questions(mock["questions"], patch["questions"])

    if isinstance(patch.get("passages"), dict):
        mock["passages"], p_applied = merge_passages(
            mock.get("passages"), patch["passages"])

    if mock == mock_before:
        return False, 0, 0

    if not dry:
        _dump(mock_path, mock)
    return True, q_applied, p_applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只打印 diff 不写回")
    ap.add_argument("--subject", help="仅处理指定学科")
    ap.add_argument("--slug", help="仅处理指定 slug（如 2026-chaoyang-er）")
    args = ap.parse_args()

    targets: list[tuple[Path, str, str]] = []
    for subject_dir in sorted(PATCHES_ROOT.iterdir()):
        if not subject_dir.is_dir():
            continue
        subject = subject_dir.name
        if args.subject and subject != args.subject:
            continue
        for patch_file in sorted(subject_dir.glob("*.yaml")):
            slug = patch_file.stem
            if args.slug and slug != args.slug:
                continue
            targets.append((patch_file, subject, slug))

    if not targets:
        print("无匹配 patch")
        return 0

    print(f"扫到 {len(targets)} 份 patches{' [dry-run]' if args.dry else ''}\n")
    total_changed = 0
    total_q = 0
    total_p = 0
    for patch_path, subject, slug in targets:
        print(f"📝 {subject}/{slug}")
        changed, qn, pn = bake_one(patch_path, subject, slug, dry=args.dry)
        if changed:
            total_changed += 1
            total_q += qn
            total_p += pn
            print(f"   ✓ Q×{qn} P×{pn}")
        else:
            print(f"   = 无变化（已合并/字段完全相同）")

    print()
    print(f"汇总：{total_changed}/{len(targets)} 份 mock yaml 被修改，"
          f"应用 Q×{total_q} P×{total_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
