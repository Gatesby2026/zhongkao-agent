#!/usr/bin/env python3
"""逐校录取位次趋势 + 波动 + 2026 预测 → ts/line_trend.json(uid 主键)。
取每校"本部·普通班/主专业"的区位次 23/24/25(优先 T1 官方,缺则 T3 网传/白皮书),
算 volatility(极差/均值,>0.40 标波动大)+ 2026 保守预测区间(线性外推±波动半幅,夹紧)。
全 T3 口径(2025/2026 含网传),仅辅助研判,面板标待核。
"""
import json
from collections import defaultdict
from pathlib import Path

TS = Path(__file__).resolve().parents[3] / "knowledge-base/admission/beijing/ts"
VOL_TH = 0.40


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


lines = jl(TS / "lines.jsonl")
# uid -> year -> rank(优先 T1;同年多专业取"本部/普通班"≈最小 major 行,用最低位次=最高分代表校线)
by = defaultdict(lambda: defaultdict(lambda: {"T1": None, "T3": None}))
for r in lines:
    if r.get("rank") is None or "（" in r["name"]:   # 跳过分校区记录,用本部
        continue
    mj = r.get("major_name") or ""
    if mj and ("实验" in mj or "贯通" in mj or "美术" in mj or "科创" in mj):
        continue   # 趋势用普通班/统招主线,排除实验/贯通/美术等特殊班
    slot = by[r["uid"]][r["year"]]
    tier = "T1" if r["source_tier"] == "T1" else "T3"
    # 同源同年取更小 rank(代表统招主线/本部)
    if slot[tier] is None or r["rank"] < slot[tier]:
        slot[tier] = r["rank"]


def pick(slot):
    return slot["T1"] if slot["T1"] is not None else slot["T3"]


out = {}
for uid, yrs in by.items():
    ranks = {y: pick(yrs[y]) for y in (2023, 2024, 2025) if pick(yrs[y]) is not None}
    if not ranks:
        continue
    vals = [ranks[y] for y in sorted(ranks)]
    mean = sum(vals) / len(vals)
    vol = (max(vals) - min(vals)) / mean if mean else 0
    ys = sorted(ranks)
    # 2026 参考:不做趋势外推(位次单年波动大,外推会放大噪声)。
    # 中央=最近年位次;区间=三年历史包络(波动大→区间自然变宽,如实反映不确定)。
    latest = ranks[ys[-1]]
    lo, hi = min(vals), max(vals)
    # 包络太窄(稳定校)时给最小 ±5% 容差
    pad = max(int(mean * 0.05), 1)
    lo, hi = min(lo, latest - pad), max(hi, latest + pad)
    out[uid] = {
        "ranks": ranks,                       # {2023:..,2024:..,2025:..}
        "latest": latest, "latest_year": ys[-1],
        "volatility": round(vol, 2), "volatile": vol > VOL_TH,
        "ref_2026": latest, "ref_2026_lo": max(1, lo), "ref_2026_hi": hi,
        "note": "T3·含网传线·非外推;中央取最近年、区间取三年历史包络;波动大者区间更宽",
    }

json.dump({"_meta": {"warning": "录取位次趋势/2026预测·T3·网传+外推·仅辅助研判", "count": len(out), "vol_threshold": VOL_TH},
           "trend": out}, open(TS / "line_trend.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 打印抽样(按 2025 位次)
import yaml
nm = {s["uid"]: s["name"] for s in yaml.safe_load(open(TS / "schools.yaml", encoding="utf-8"))}
ranked = sorted(out.items(), key=lambda kv: kv[1]["latest"])
print(f"固化 {len(out)} 校位次趋势 → ts/line_trend.json\n")
print(f"{'学校':<16}{'2023':>6}{'2024':>6}{'2025':>6}{'波动':>6}  2026预测(区间)")
for uid, t in ranked:
    r = t["ranks"]
    flag = " ⚠波动大" if t["volatile"] else ""
    print(f"{nm.get(uid, uid)[:16]:<16}{r.get(2023, '—'):>6}{r.get(2024, '—'):>6}{r.get(2025, '—'):>6}{t['volatility']:>6}  {t['ref_2026']}({t['ref_2026_lo']}~{t['ref_2026_hi']}){flag}")
