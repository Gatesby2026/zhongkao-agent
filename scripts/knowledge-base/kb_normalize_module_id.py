#!/usr/bin/env python3
"""[一次性] KB-LAYOUT 阶段3：pedagogy 四层 module_id 归一为 kebab。

确定性规则：文件名（去 .yaml）即 canonical kebab module-id（filename 已统一）。
  - diagnostics / learning-paths：当前无 module_id → 在 `module:` 行后注入
  - mistakes：已有 module_id（多词为 camelCase）→ 改写为 kebab
  - quick-tests：target_modules 列表 + 每题 module: 的 camelCase → kebab
行级编辑，保留注释头（含 source/状态，yaml round-trip 会丢）。
用法： python3 kb_normalize_module_id.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_module_ids import camel_to_kebab, is_valid  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PED = ROOT / "knowledge-base" / "pedagogy"
QT = ROOT / "knowledge-base" / "prep" / "quick-tests"
DRY = "--dry" in sys.argv


def _subject_of(p: Path, layer: str) -> str:
    # pedagogy/<layer>/<subject>/...   返回 subject
    parts = p.relative_to(PED / layer).parts
    return parts[0]


def normalize_pedagogy() -> list[str]:
    errs = []
    for layer in ("diagnostics", "mistakes", "learning-paths"):
        base = PED / layer
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.yaml")):
            stem = f.stem                       # canonical kebab
            subject = _subject_of(f, layer)
            if not is_valid(subject, stem):
                errs.append(f"✗ {f.relative_to(ROOT)}: 文件名 '{stem}' 不在 "
                            f"spec[{subject}]，需人工核")
                continue
            lines = f.read_text(encoding="utf-8").splitlines()
            has_mid = next((i for i, ln in enumerate(lines)
                            if ln.startswith("module_id:")), None)
            mod_ln = next((i for i, ln in enumerate(lines)
                           if ln.startswith("module:")), None)
            new = f"module_id: {stem}"
            if has_mid is not None:
                if lines[has_mid].strip() == new:
                    continue
                lines[has_mid] = new
            elif mod_ln is not None:
                lines.insert(mod_ln + 1, new)
            else:                               # 无 module: → 插在首个顶层键前
                k = next((i for i, ln in enumerate(lines)
                          if ln[:1].isalpha()), 0)
                lines.insert(k, new)
            if not DRY:
                f.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"  ✓ {f.relative_to(ROOT)}  module_id={stem}")
    return errs


def normalize_quick_tests() -> list[str]:
    errs = []
    for f in sorted(QT.rglob("*.yaml")):
        subject = f.relative_to(QT).parts[0]
        out, changed = [], False
        for ln in f.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            # "  - <camel>"（target_modules 项） 或 "    module: <camel>"
            if s.startswith("module:"):
                v = s.split(":", 1)[1].strip()
                k = camel_to_kebab(v)
                if k != v:
                    ln = ln.replace(v, k); changed = True
                if not is_valid(subject, k):
                    errs.append(f"✗ {f.relative_to(ROOT)}: module '{k}' 不在 spec[{subject}]")
            elif s.startswith("- ") and s[2:] and s[2:][0].islower():
                v = s[2:].strip()
                k = camel_to_kebab(v)
                if k != v and is_valid(subject, k):
                    ln = ln.replace(v, k); changed = True
            out.append(ln)
        if changed and not DRY:
            f.write_text("\n".join(out) + "\n", encoding="utf-8")
        if changed:
            print(f"  ✓ {f.relative_to(ROOT)}  camelCase→kebab")
    return errs


def main():
    print(f"== pedagogy 三层 =={' (dry)' if DRY else ''}")
    e1 = normalize_pedagogy()
    print(f"== quick-tests =={' (dry)' if DRY else ''}")
    e2 = normalize_quick_tests()
    errs = e1 + e2
    if errs:
        print("\n需人工核：")
        for e in errs:
            print(" ", e)
        sys.exit(1)
    print("\n全部确定性归一完成。")


if __name__ == "__main__":
    main()
