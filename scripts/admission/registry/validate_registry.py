#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建期校验:扫所有数据文件里出现的每个学校名/代码,必须能 resolve 到注册表。
未 resolve 的 → 列出(= 待补别名 或 该文件名字写错)。退出码非零 = 有未覆盖项。

用法: python3 scripts/admission/registry/validate_registry.py
P1 后接入 CI / 构建前置;现阶段先看覆盖率。
"""
import os, json, sys
import yaml
from collections import defaultdict
from resolve import resolve  # 同目录

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
KB = os.path.join(ROOT, "knowledge-base", "admission", "beijing")

def J(p): return json.load(open(os.path.join(KB, p), encoding="utf-8"))
def Y(p): return yaml.safe_load(open(os.path.join(KB, p), encoding="utf-8"))

# 各文件 → 该文件里引用的学校"名字/代码"清单(district=chaoyang 范围)
def refs():
    out = defaultdict(list)  # file -> [ref,...]
    for s in Y("chaoyang.yaml")["schools"]:
        out["chaoyang.yaml"].append(s["name"])
    for nm, rec in J("chaoyang_admission_codes.json")["schools"].items():
        out["admission_codes"].append(nm)
    for nm in J("chaoyang_coords.json")["schools"]:
        out["coords"].append(nm)
    for s in Y("chaoyang_private.yaml")["schools"]:
        out["private"].append(s["name"])
    for s in Y("chaoyang_vocational.yaml")["schools"]:
        out["vocational"].append(s["name"])
    for s in Y("chaoyang_new2026.yaml")["schools"]:
        out["new2026"].append(s["name"])
    for k in J("ts/pred_2026.json")["pred"]:
        out["pred_2026"].append(k.split(":", 1)[-1])
    # 校额到校:by_school 是缩写(已知缺口,重点观察)
    try:
        xed = Y("chaoyang_xeddx.yaml")
        seen = set()
        for r in xed.get("rows", []):
            for hs in (r.get("by_school") or {}):
                if hs not in seen:
                    seen.add(hs); out["xeddx(缩写)"].append(hs)
    except Exception:
        pass
    # 市级统筹
    try:
        tc = J("2025_sjtongchou_chaoyang.json")
        for key in ("tongchou_yi", "tongchou_er"):
            for r in tc.get(key, []):
                out["sjtongchou"].append(r.get("name"))
    except Exception:
        pass
    return out

def main():
    data = refs()
    total_unres = 0
    print("# 注册表 resolve 覆盖率\n")
    print(f"{'文件':<16} {'总数':>5} {'命中':>5} {'未命中':>6}  覆盖率")
    print("-" * 52)
    unresolved = defaultdict(list)
    for fname, items in data.items():
        uniq = [x for x in dict.fromkeys(items) if x]
        hit = [x for x in uniq if resolve(x)]
        miss = [x for x in uniq if not resolve(x)]
        total_unres += len(miss)
        unresolved[fname] = miss
        rate = f"{len(hit)/len(uniq)*100:4.0f}%" if uniq else "  - "
        print(f"{fname:<16} {len(uniq):>5} {len(hit):>5} {len(miss):>6}  {rate}")
    print()
    for fname, miss in unresolved.items():
        if miss:
            print(f"## 未命中 · {fname}（{len(miss)}）")
            for m in miss:
                print(f"  - {m}")
            print()
    print(f"合计未命中: {total_unres}")

    # 当前年度硬门禁：运行时 registry 不得混用旧计划、重复实体或错误合计。
    errors = []
    regdir = os.path.join(KB, "registry", "cy")
    entities = []
    for fn in sorted(os.listdir(regdir)):
        if fn.startswith("_") or not fn.endswith(".yaml"):
            continue
        entities.append(Y(os.path.join("registry", "cy", fn)))
    ids = [e.get("id") for e in entities]
    names = [e.get("canonical_name") for e in entities]
    if len(ids) != len(set(ids)):
        errors.append("registry/cy 存在重复 id")
    if len(names) != len(set(names)):
        errors.append("registry/cy 存在重复 canonical_name")

    code_owners = defaultdict(set)
    for e in entities:
        for a in e.get("admissions") or []:
            if a.get("code"):
                code_owners[str(a["code"])].add(e.get("id"))
    dup_codes = {c: sorted(v) for c, v in code_owners.items() if len(v) > 1}
    if dup_codes:
        errors.append(f"招生代码跨实体重复: {dup_codes}")

    overlay = Y("2026_sjtongchou_chaoyang.yaml")
    tc = overlay
    xed = Y("chaoyang_xeddx.yaml")
    if int(tc.get("year") or 0) != 2026:
        errors.append(f"市级统筹运行时年份不是2026: {tc.get('year')}")
    if int(xed.get("year") or 0) != 2026:
        errors.append(f"校额到校运行时年份不是2026: {xed.get('year')}")
    expected = {"tongchou_yi": 51, "tongchou_er": 94}
    expected_codes = {
        "tongchou_yi": {
            "101002", "101010", "102001", "102002", "102013", "102014", "102015",
            "105001", "105002", "106001", "108001", "108002", "108003", "108005", "113001",
        },
        "tongchou_er": {
            "205022", "205023", "206020", "207005", "108001", "108003",
            "209003", "212006", "212008", "214012", "216007",
        },
    }
    for key, want in expected.items():
        got = sum(int(r.get("quota_chaoyang") or 0) for r in tc.get(key, []))
        if got != want:
            errors.append(f"{key} 朝阳名额合计={got}, 应为{want}")
        got_codes = {str(r.get("school_code")) for r in tc.get(key, [])}
        if got_codes != expected_codes[key]:
            errors.append(
                f"{key} 学校代码集合不符: 缺{sorted(expected_codes[key] - got_codes)},"
                f" 多{sorted(got_codes - expected_codes[key])}")
    for r in xed.get("rows") or []:
        got = sum(int(v or 0) for v in (r.get("by_school") or {}).values())
        if got != int(r.get("total") or 0):
            errors.append(f"校额行合计不符: {r.get('code')} {r.get('name')} {got}!={r.get('total')}")

    promoted = {"205021", "205022", "205023"}
    found = {}
    for e in entities:
        codes = {str(a.get("code")) for a in e.get("admissions") or [] if a.get("code")}
        for code in promoted & codes:
            found[code] = e
    for code in sorted(promoted):
        e = found.get(code)
        if not e:
            errors.append(f"2026首年招生学校未进入registry: {code}")
        elif e.get("type") != "公办普高":
            errors.append(f"{code} 尚未转正为公办普高: {e.get('type')}")

    print("\n# 当前年度硬门禁")
    if errors:
        for e in errors:
            print(f"  - FAIL: {e}")
    else:
        print("  PASS: 2026年份、统筹合计、校额checksum、实体唯一性、新校转正")
    return 1 if total_unres or errors else 0

if __name__ == "__main__":
    sys.exit(main())
