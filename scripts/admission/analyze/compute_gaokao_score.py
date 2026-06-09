#!/usr/bin/env python3
"""把高考数据综合成每校 U 分(gaokao_score)并固化到 ts/gaokao_score.json。
U = 一本率为底(0~88) + 清北/高分段加成(0~12),头部校(只报清北不报一本率)按"≈100%一本"托底。
全 T3·民间·非官方 → 每校带 confidence + basis,供产品按置信度弱化展示、供人工审核。
"""
import json
from collections import defaultdict
from pathlib import Path

TS = Path(__file__).resolve().parents[3] / "knowledge-base/admission/beijing/ts"


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


gk = jl(TS / "gaokao.jsonl")
import yaml
schools = {s["uid"]: s for s in yaml.safe_load(open(TS / "schools.yaml", encoding="utf-8"))}

# uid -> metric -> {year:(value,qual,note)}
M = defaultdict(lambda: defaultdict(dict))
for r in gk:
    M[r["uid"]][r["metric"]][r["year"]] = (r["value"], r.get("qualifier", "="), r.get("note", ""))


def best_tk(d):
    if not d:
        return None, None, False
    it = sorted(d.items(), key=lambda kv: (0 if kv[1][1] == "?" else 1, kv[0]))
    y, (v, q, _n) = it[-1]
    return v, y, q == "?"


def latest(d):
    if not d:
        return None, None
    y = max(d)
    return d[y][0], y


def tier_of(s):
    return "顶尖" if s >= 93 else "优质" if s >= 85 else "中上" if s >= 72 else "中等" if s >= 58 else "一般"


out = {}
for uid, mm in M.items():
    name = schools.get(uid, {}).get("name", uid)
    tk, tk_y, susp = best_tk(mm.get("特控率(一本)", {}))
    qb, qb_y = latest(mm.get("清北人数", {}))
    n685, _ = latest(mm.get("685分以上人数(裸分清北线)", {}))
    n700, _ = latest(mm.get("700分以上人数", {}))
    bk, bk_y = latest(mm.get("本科率", {}))
    # 声望分(清北级人数):清北 / 685+ / 700+×1.5 取最大
    prestige = max([x for x in [qb or 0, n685 or 0, round((n700 or 0) * 1.5)]])
    # 一本率底:有则用;无但声望≥5(头部校)按≈100%托底;否则用本科率折算或缺省
    if tk is not None:
        ybase = tk
        tk_src = f"一本率{tk:.0%}({tk_y})" + ("·存疑改用旧年" if susp else "")
    elif prestige >= 5:
        ybase = 0.90   # 头部校未单列一本率,按≈90%保守托底(真实接近100%,但留出空间给有硬一本率的校),靠清北加成区分
        tk_src = "一本率未单列(头部校),按≈90%保守托底"
    elif bk is not None:
        ybase = max(0.0, bk - 0.55)   # 仅本科率→粗略折算一本率
        tk_src = f"无一本率;按本科率{bk:.0%}粗估"
    else:
        ybase = 0.55
        tk_src = "高考数据极少,缺省档"
    score = round(min(100, ybase * 88 + min(prestige, 24) * 0.5))
    # 置信度
    yrs = len(mm.get("特控率(一本)", {})) + (1 if prestige else 0)
    conf = "low"
    if (tk is not None and not susp) and (qb or n685 or n700 or bk):
        conf = "medium"
    if susp or (tk is None and prestige < 5 and bk is None):
        conf = "very_low"
    basis = [tk_src]
    if prestige:
        basis.append((f"清北{qb}" if qb else f"685+{n685}" if n685 else f"700+{n700}"))
    out[uid] = {
        "name": name, "gaokao_score": score, "tier": tier_of(score),
        "yiben": tk, "qingbei": qb, "n685": n685, "n700": n700, "benke": bk,
        "confidence": conf, "basis": "；".join(b for b in basis if b),
        "source_tier": "T3", "note": "民间·非官方·多源/多年交叉;仅参考",
    }

ranked = sorted(out.values(), key=lambda r: -r["gaokao_score"])
json.dump({"_meta": {"warning": "T3民间·非官方·低置信;U=一本率底+清北/高分段加成;供审核与产品弱化展示", "count": len(out)},
           "scores": out}, open(TS / "gaokao_score.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"固化 {len(out)} 校 → ts/gaokao_score.json\n")
print(f"{'#':>2} {'学校':<14}{'U分':>4} {'档次':<5}{'依据':<28} 置信")
for i, r in enumerate(ranked, 1):
    print(f"{i:>2} {r['name'][:14]:<14}{r['gaokao_score']:>4} {r['tier']:<5}{r['basis'][:28]:<28} {r['confidence']}")
