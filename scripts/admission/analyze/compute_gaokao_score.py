#!/usr/bin/env python3
"""把高考数据综合成每校 U 分(gaokao_score)并固化到 ts/gaokao_score.json。
U = 一本率为底(0~88) + 清北/高分段加成(0~12),头部校(只报清北不报一本率)按"≈100%一本"托底。

覆盖保证:遍历**全部公办普高**(schools.yaml),无真实高考数据的校用
**录取位次回归估算**一本率兜底(锚定在有真实一本率+位次的样本上,分段线性插值),
确保 27 校一个不缺。估算值 confidence=very_low、basis 标"位次≈N→估算"。
全 T3·民间·非官方 → 每校带 confidence + basis,供产品按置信度弱化展示、供人工审核。
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

# uid -> metric -> {year:(value,qual,note)}
M = defaultdict(lambda: defaultdict(dict))
for r in gk:
    M[r["uid"]][r["metric"]][r["year"]] = (r["value"], r.get("qualifier", "="), r.get("note", ""))

# 位次:最新年 T1。RANK_ANCHOR 仅本部(校名不带"校区")用于回归锚点;
# RANK_EST 含校区,作各校(含分校区)回归估算的输入。
RANK_ANCHOR, RANK_EST = {}, {}
for r in sorted(lines, key=lambda r: r["year"]):
    if r["source_tier"] == "T1" and r.get("rank") is not None:
        RANK_EST[r["uid"]] = (r["rank"], r["year"])
        if "（" not in r["name"]:
            RANK_ANCHOR[r["uid"]] = (r["rank"], r["year"])


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


# ── 位次→一本率 回归锚点:有"真实非存疑一本率"且有位次的校 ──────────────────
anchors = []
for uid, mm in M.items():
    tk, _y, susp = best_tk(mm.get("特控率(一本)", {}))
    rk = RANK_ANCHOR.get(uid)
    if tk is not None and not susp and rk:
        anchors.append((rk[0], tk))
anchors.sort()


def regress_yiben(rank):
    """分段线性插值:位次 → 一本率估算。锚点外侧平推。"""
    if not anchors or rank is None:
        return None
    if rank <= anchors[0][0]:
        return anchors[0][1]
    if rank >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(1, len(anchors)):
        r0, y0 = anchors[i - 1]
        r1, y1 = anchors[i]
        if r0 <= rank <= r1:
            t = (rank - r0) / (r1 - r0) if r1 > r0 else 0
            return round(y0 + (y1 - y0) * t, 3)
    return None


# 新建高中部·首届未毕业·暂无高考出口(白皮书明示):不给 U 分、不估算,标"新校"
NEW_NO_OUTPUT = {"清华附中广华学校", "中国传媒大学附属中学", "八十中睿德分校",
                 "北京中学科技分校", "首师大附中朝阳学校"}

out = {}
# 遍历全部公办普高(含分校/校区),保证一个不缺
for uid, s in schools.items():
    if "公办" not in (s.get("type") or ""):
        continue
    mm = M.get(uid, {})
    name = s.get("name", uid)
    if name in NEW_NO_OUTPUT:
        out[uid] = {
            "name": name, "gaokao_score": None, "tier": "新校", "yiben": None,
            "yiben_est": None, "qingbei": None, "n685": None, "n700": None, "benke": None,
            "confidence": "na", "basis": "新建高中部·首届未毕业,暂无高考出口",
            "source_tier": "T2", "note": "白皮书明示首届未毕业;入口位次可参考,出口待首届高考",
        }
        continue
    tk, tk_y, susp = best_tk(mm.get("特控率(一本)", {}))
    qb, qb_y = latest(mm.get("清北人数", {}))
    n685, _ = latest(mm.get("685分以上人数(裸分清北线)", {}))
    n700, _ = latest(mm.get("700分以上人数", {}))
    bk, bk_y = latest(mm.get("本科率", {}))
    prestige = max([x for x in [qb or 0, n685 or 0, round((n700 or 0) * 1.5)]])
    rk = RANK_EST.get(uid)
    est = False
    if tk is not None:
        ybase = tk
        tk_src = f"一本率{tk:.0%}({tk_y})" + ("·存疑改用旧年" if susp else "")
    elif prestige >= 5:
        ybase = 0.90
        tk_src = "一本率未单列(头部校),按≈90%保守托底"
    elif bk is not None:
        ybase = max(0.0, bk - 0.55)
        tk_src = f"无一本率;按本科率{bk:.0%}粗估"
    else:
        # 兜底:用录取位次回归估算一本率(锚定真实样本)
        ry = regress_yiben(rk[0]) if rk else None
        if ry is not None:
            ybase = ry
            est = True
            tk_src = f"位次≈{rk[0]}({rk[1]})→一本率估算{ry:.0%}(锚定真实样本回归)"
        else:
            ybase = 0.55
            tk_src = "无一本率/无位次,缺省档"
    score = round(min(100, ybase * 88 + min(prestige, 24) * 0.5))
    # 置信度
    conf = "low"
    if (tk is not None and not susp) and (qb or n685 or n700 or bk):
        conf = "medium"
    if est:
        conf = "very_low"
    elif susp or (tk is None and prestige < 5 and bk is None):
        conf = "very_low"
    basis = [tk_src]
    if prestige:
        basis.append((f"清北{qb}" if qb else f"685+{n685}" if n685 else f"700+{n700}"))
    out[uid] = {
        "name": name, "gaokao_score": score, "tier": tier_of(score),
        "yiben": tk if not est else None, "yiben_est": round(ybase, 3) if est else None,
        "qingbei": qb, "n685": n685, "n700": n700, "benke": bk,
        "confidence": conf, "basis": "；".join(b for b in basis if b),
        "source_tier": "T3", "note": ("位次回归估算·非采集值·仅参考" if est else "民间·非官方·多源/多年交叉;仅参考"),
    }

ranked = sorted(out.values(), key=lambda r: (-(r["gaokao_score"] if r["gaokao_score"] is not None else -1)))
json.dump({"_meta": {"warning": "T3民间·非官方·低置信;U=一本率底+清北/高分段加成;无采集值的校用位次回归估算(very_low);供审核与产品弱化展示",
                     "count": len(out), "anchors": len(anchors)},
           "scores": out}, open(TS / "gaokao_score.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"固化 {len(out)} 校 → ts/gaokao_score.json (回归锚点 {len(anchors)} 个)\n")
print(f"{'#':>2} {'学校':<16}{'U分':>4} {'档次':<5}{'置信':<10}依据")
for i, r in enumerate(ranked, 1):
    sc = r["gaokao_score"] if r["gaokao_score"] is not None else "—"
    print(f"{i:>2} {r['name'][:16]:<16}{str(sc):>4} {r['tier']:<5}{r['confidence']:<10}{r['basis'][:42]}")
