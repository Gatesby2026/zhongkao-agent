#!/usr/bin/env python3
"""KB pedagogy 域质量门禁 + 模块覆盖矩阵（复用 qc_report 模式）。

校验（对照 KB-MODULE-ID-SPEC）：
  - diagnostics/mistakes/learning-paths 每文件 module_id 存在、== 文件名、∈ spec[subject]
  - quick-tests 每题 module ∈ spec[subject]
  - 跨层覆盖：每个 spec (subject, module) 在三层是否齐全
退出码：0=无 error，1=有 error（违规/非法 id）。覆盖缺口为 warn 不阻断。

用法： python3 kb_lint.py [--matrix]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_module_ids import MODULE_IDS, is_valid  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "knowledge-base"
PED = KB / "pedagogy"
QT = KB / "prep" / "quick-tests"
LAYERS = ("diagnostics", "mistakes", "learning-paths")
META_DOMAINS = [KB / "pedagogy", KB / "prep", KB / "policies", KB / "admission"]
QUALITY = {"llm_draft", "curated", "teacher_reviewed", "verified"}


def _meta(f: Path) -> dict:
    """轻量取 meta 块（顶层 `meta:` 下两空格缩进键）。"""
    out, inb = {}, False
    for ln in f.read_text(encoding="utf-8").splitlines():
        if ln.rstrip() == "meta:":
            inb = True
            continue
        if inb:
            if ln.startswith("  ") and ":" in ln:
                k, v = ln.strip().split(":", 1)
                out[k.strip()] = v.split("#")[0].strip().strip('"')
            elif ln.strip() and not ln.startswith("  "):
                break
    return out


def _mid(f: Path) -> str | None:
    for ln in f.read_text(encoding="utf-8").splitlines():
        if ln.startswith("module_id:"):
            return ln.split(":", 1)[1].strip()
    return None


def main() -> None:
    errs: list[str] = []
    # subject -> module -> set(layers present)
    cov: dict[str, dict[str, set]] = {
        s: {m: set() for m in ms} for s, ms in MODULE_IDS.items()}

    for layer in LAYERS:
        base = PED / layer
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.yaml")):
            subject = f.relative_to(base).parts[0]
            stem = f.stem
            mid = _mid(f)
            rel = f.relative_to(ROOT)
            if mid is None:
                errs.append(f"{rel}: 缺 module_id")
            elif mid != stem:
                errs.append(f"{rel}: module_id '{mid}' ≠ 文件名 '{stem}'")
            elif not is_valid(subject, mid):
                errs.append(f"{rel}: '{mid}' 不在 spec[{subject}]")
            else:
                cov[subject][mid].add(layer)

    for f in sorted(QT.rglob("*.yaml")):
        subject = f.relative_to(QT).parts[0]
        for ln in f.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s.startswith("module:"):
                v = s.split(":", 1)[1].strip()
                if not is_valid(subject, v):
                    errs.append(f"{f.relative_to(ROOT)}: quick-test module "
                                f"'{v}' 不在 spec[{subject}]")

    # —— 知识层 meta.quality_status 校验 + 待审分布 ——
    qdist: dict[str, int] = {}
    for dom in META_DOMAINS:
        if not dom.is_dir():
            continue
        for f in sorted(dom.rglob("*.yaml")):
            if "question-banks" in f.parts:        # 自带 meta schema
                continue
            rel = f.relative_to(ROOT)
            m = _meta(f)
            qs = m.get("quality_status")
            if not m or qs is None:
                errs.append(f"{rel}: 缺 meta.quality_status")
            elif qs not in QUALITY:
                errs.append(f"{rel}: quality_status '{qs}' 非法")
            else:
                qdist[qs] = qdist.get(qs, 0) + 1
                if qs in ("teacher_reviewed", "verified") \
                        and not m.get("reviewed_by"):
                    errs.append(f"{rel}: {qs} 必须有 reviewed_by")

    gaps = [(s, m, sorted(set(LAYERS) - ls))
            for s, mm in cov.items() for m, ls in mm.items()
            if 0 < len(ls) < 3]
    missing = [(s, m) for s, mm in cov.items()
               for m, ls in mm.items() if not ls]

    print(f"{'='*56}\nKB pedagogy lint")
    if errs:
        print(f"  ❌ error ({len(errs)}):")
        for e in errs:
            print(f"     - {e}")
    if gaps:
        print(f"  ⚠️  三层覆盖不全 ({len(gaps)}):")
        for s, m, miss in gaps:
            print(f"     - {s}/{m}：缺 {','.join(miss)}")
    if missing:
        print(f"  ⚠️  三层全缺 ({len(missing)}):")
        for s, m in missing:
            print(f"     - {s}/{m}")
    if qdist:
        tot = sum(qdist.values())
        order = ["llm_draft", "curated", "teacher_reviewed", "verified"]
        dist = "  ".join(f"{k}={qdist[k]}" for k in order if k in qdist)
        print(f"  📊 知识层质量分布（{tot}）：{dist}")
        pend = qdist.get("llm_draft", 0) + qdist.get("curated", 0)
        if pend:
            print(f"     待人工复核（llm_draft+curated）：{pend}")
    if not errs and not gaps and not missing:
        print("  🎉 全模块三层齐全、id 合规、meta 完整")

    if "--matrix" in sys.argv:
        print(f"\n{'='*56}\n覆盖矩阵 (D=diagnostics M=mistakes L=learning-paths)")
        for s, mm in MODULE_IDS.items():
            print(f"\n[{s}]")
            for m in sorted(mm):
                ls = cov[s][m]
                tag = "".join(c if l in ls else "·" for c, l in
                              zip("DML", LAYERS))
                print(f"  {tag}  {m}")

    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
