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
    return 1 if total_unres else 0

if __name__ == "__main__":
    sys.exit(main())
