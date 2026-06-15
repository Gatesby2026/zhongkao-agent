#!/usr/bin/env python3
"""增值(value-added):入口位次→出口的 residual → ts/value_added.json(uid 主键)。
对"有真实一本率 + 有入口位次"的公办校,用 log 线性拟合 期望一本率 = a + b·ln(入口区位次),
residual = 实际一本率 − 期望。residual 高 = 同等入口下产出更好(带得动/捡漏);低 = 入口贵产出低。
全 T3 口径(民间一本率 + 网传位次),仅辅助。新校/估算校不算(无真实出口或无真实入口)。
"""
import json
import math
from collections import defaultdict
from pathlib import Path

TS = Path(__file__).resolve().parents[3] / "knowledge-base/admission/beijing/ts"


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


gk = jl(TS / "gaokao.jsonl")
trend = json.load(open(TS / "line_trend.json", encoding="utf-8")).get("trend", {}) if (TS / "line_trend.json").exists() else {}

# uid -> 真实一本率(非存疑,取最可信年)
tk = defaultdict(dict)
for r in gk:
    if r["metric"] == "特控率(一本)":
        tk[r["uid"]][r["year"]] = (r["value"], r.get("qualifier", "="))


def best_tk(d):
    if not d:
        return None
    it = sorted(d.items(), key=lambda kv: (0 if kv[1][1] == "?" else 1, kv[0]))
    v, q = it[-1][1]
    return None if q == "?" else v   # 存疑值不参与增值


# 样本:有真实一本率 + 有入口位次。SAT=一本率饱和阈值(到顶不再区分,改看清北)
SAT = 0.95
pts = []        # 全部(含顶部)
for uid, d in tk.items():
    v = best_tk(d)
    t = trend.get(uid)
    if v is None or not t:
        continue
    pts.append((uid, t["latest"], v))

# 仅用非饱和区(一本率<SAT)拟合 log 线性 v = a + b*ln(rank),避免顶部饱和把线拉歪
fit = [p for p in pts if p[2] < SAT]
n = len(fit)
xs = [math.log(p[1]) for p in fit]
ys = [p[2] for p in fit]
mx, my = sum(xs) / n, sum(ys) / n
b = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / sum((x - mx) ** 2 for x in xs)
a = my - b * mx


def expected(rank):
    return min(0.99, a + b * math.log(rank))   # 期望夹到≤99%(一本率上限)


HI, LO = 0.08, -0.08   # residual 阈值(一本率百分点)
out = {}
for uid, rank, v in pts:
    if v >= SAT:
        # 顶部校:一本率近满,不区分;增值看清北/高分段,这里只标识
        out[uid] = {
            "entrance_rank": rank, "yiben_real": round(v, 3), "yiben_expected": None,
            "residual": None, "label": "顶部饱和",
            "basis": f"一本率{v:.0%}已近满,一本率不再区分;高端增值看清北/高分段",
            "note": "T3·一本率饱和区·增值参考清北而非一本率",
        }
        continue
    exp = expected(rank)
    res = v - exp
    label = "高增值" if res >= HI else "偏低" if res <= LO else "符合预期"
    out[uid] = {
        "entrance_rank": rank, "yiben_real": round(v, 3), "yiben_expected": round(exp, 3),
        "residual": round(res, 3), "label": label,
        "basis": f"入口位次≈{rank}→同档期望一本率{exp:.0%},实际{v:.0%},{'+' if res>=0 else ''}{res*100:.0f}pp",
        "note": "T3·民间一本率+网传位次·log拟合residual·仅辅助(捡漏/性价比参考)",
    }

json.dump({"_meta": {"warning": "增值=入口位次→出口一本率的residual·T3·仅辅助", "count": len(out),
                     "fit": f"一本率 ≈ {a:.3f} + ({b:.3f})·ln(位次)", "hi": HI, "lo": LO},
           "value_added": out}, open(TS / "value_added.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

import yaml
nm = {s["uid"]: s["name"] for s in yaml.safe_load(open(TS / "schools.yaml", encoding="utf-8"))}
ranked = sorted(out.items(), key=lambda kv: (kv[1]["residual"] is None, -(kv[1]["residual"] or 0)))
print(f"固化 {len(out)} 校增值 → ts/value_added.json (拟合 一本率≈{a:.2f}+({b:.3f})·ln位次, 仅非饱和区)\n")
print(f"{'学校':<16}{'入口位次':>7}{'实际一本':>8}{'期望':>7}{'增值':>7}  标签")
for uid, t in ranked:
    exp = f"{t['yiben_expected']*100:>5.0f}%" if t['yiben_expected'] is not None else "    —"
    res = f"{t['residual']*100:>+5.0f}pp" if t['residual'] is not None else "     —"
    print(f"{nm.get(uid, uid)[:16]:<16}{t['entrance_rank']:>7}{t['yiben_real']*100:>7.0f}%{exp:>7}{res:>7}  {t['label']}")
