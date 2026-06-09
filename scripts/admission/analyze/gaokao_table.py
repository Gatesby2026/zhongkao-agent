#!/usr/bin/env python3
"""朝阳高中·按高考成绩排名 + 历年明细表(供人工审核)。
排名主分=特控率(一本率,优先非存疑、取最可信年);全 T3·民间·非官方·低置信。
"""
import json
from collections import defaultdict
from pathlib import Path

import yaml

TS = Path(__file__).resolve().parents[3] / "knowledge-base/admission/beijing/ts"


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


gk = jl(TS / "gaokao.jsonl")
lines = jl(TS / "lines.jsonl")
schools = {s["uid"]: s for s in yaml.safe_load(open(TS / "schools.yaml", encoding="utf-8"))}

# uid -> metric -> {year: (value,qual,note)}
M = defaultdict(lambda: defaultdict(dict))
for r in gk:
    M[r["uid"]][r["metric"]][r["year"]] = (r["value"], r.get("qualifier", "="), r.get("note", ""))

rk25 = {r["uid"]: r["rank"] for r in lines
        if r["year"] == 2025 and r["source_tier"] == "T1" and "（" not in r["name"]}


def tk_best(d):
    """特控率取最可信:优先非存疑(qual!='?'),再取最新年。返回(value,year,susp)。"""
    if not d:
        return None
    items = sorted(d.items(), key=lambda kv: (0 if kv[1][1] == "?" else 1, kv[0]))
    y, (v, q, n) = items[-1]
    return v, y, (q == "?")


def pct(d, y):
    e = d.get(y)
    return f"{e[0]:.0%}{e[1] if e[1] in '+~?' else ''}" if e else ""


rows = []
for uid, mm in M.items():
    tk = mm.get("特控率(一本)", {})
    best = tk_best(tk)
    name = schools.get(uid, {}).get("name", uid)
    rows.append({
        "uid": uid, "name": name,
        "tk_best": best[0] if best else None, "tk_year": best[1] if best else None, "susp": best[2] if best else False,
        "tk22": pct(tk, 2022), "tk23": pct(tk, 2023), "tk24": pct(tk, 2024), "tk25": pct(tk, 2025),
        "bk": next((f"{v:.0%}{q if q in '+~' else ''}" for y in (2024, 2025, 2023)
                    for (v, q, n) in [mm.get("本科率", {}).get(y, (None, "", ""))] if v is not None), ""),
        "top": next((str(int(v)) + f"({y})" for y in (2025, 2024, 2023)
                     for (v, _q, _n) in [mm.get("最高分", {}).get(y, (None, "", ""))] if v is not None), ""),
        "qb": next((f"{int(v)}{q if q in '+~' else ''}({y})" for y in (2025, 2024, 2023, 2022) for (v, q, _n) in [mm.get("清北人数", {}).get(y, (None, "", ""))] if v is not None), ""),
        "n700": next((f"{int(v)}({y})" for y in (2025, 2024, 2023) for (v, _q, _n) in [mm.get("700分以上人数", {}).get(y, (None, "", ""))] if v is not None), ""),
        "n685": next((f"{int(v)}({y})" for y in (2025, 2024, 2023, 2022) for (v, _q, _n) in [mm.get("685分以上人数(裸分清北线)", {}).get(y, (None, "", ""))] if v is not None), ""),
        "n600": next((str(int(v)) for y in (2025, 2024, 2023) for (v, _q, _n) in [mm.get("600分以上人数", {}).get(y, (None, "", ""))] if v is not None), ""),
        "avg": next((str(v) for y in (2024, 2023) for (v, _q, _n) in [mm.get("年级平均分", {}).get(y, (None, "", ""))] if v is not None), ""),
        "rk25": rk25.get(uid),
    })

def qbnum(r):
    return int(r["qb"].split("(")[0].rstrip("+~")) if r["qb"] else -1

withtk = sorted([r for r in rows if r["tk_best"] is not None], key=lambda r: -r["tk_best"])
notk = sorted([r for r in rows if r["tk_best"] is None], key=lambda r: (-qbnum(r), r["rk25"] or 9e9))

H = f"{'#':>2} {'学校':<14}{'一本23':>7}{'一本24':>7}{'本科':>6}{'清北':>9}{'700+':>8}{'最高分':>9}{'25位次':>7}  备注"
print("=== 朝阳高中 按高考排名 · 历年明细 [T3·民间·非官方·低置信] ===")
print(H)
for i, r in enumerate(withtk, 1):
    note = ("⚠️存疑(用" + str(r["tk_year"]) + "年值)" if r["susp"] else "")
    print(f"{i:>2} {r['name'][:14]:<14}{r['tk23']:>7}{r['tk24']:>7}{r['bk']:>6}{(r['qb'] or ''):>9}{(r['n700'] or r['n685'] or ''):>8}{r['top']:>9}{str(r['rk25'] or '—'):>7}  {note}")
print("\n=== 头部校:不报一本率(均≈100%),按 清北/高分段 置顶 ===")
print(H)
for r in notk:
    print(f" * {r['name'][:14]:<14}{r['tk23']:>7}{r['tk24']:>7}{r['bk']:>6}{(r['qb'] or ''):>9}{(r['n700'] or r['n685'] or ''):>8}{r['top']:>9}{str(r['rk25'] or '—'):>7}  {('600+'+r['n600']+'人') if r['n600'] else ''}")
