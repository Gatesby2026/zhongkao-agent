#!/usr/bin/env python3
"""按高考成绩给朝阳学校打分排名(供人工审核)。
主分=特控率(一本率,最新年);缺特控率的列出高分段/本科率证据,由人工判定置顶。
全部 T3·民间·非官方·低置信——仅作参考,不作录取依据。
"""
import json
from collections import defaultdict
from pathlib import Path

KB = Path(__file__).resolve().parents[3] / "knowledge-base/admission/beijing"
TS = KB / "ts"


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


def main():
    gk = load_jsonl(TS / "gaokao.jsonl")
    lines = load_jsonl(TS / "lines.jsonl")
    schools = {s["uid"]: s for s in __import__("yaml").safe_load(open(TS / "schools.yaml", encoding="utf-8"))}

    # 每校最新一年的各 metric
    by_school = defaultdict(dict)   # uid -> {metric: (value, year, qual, note)}
    for r in gk:
        m = by_school[r["uid"]]
        prev = m.get(r["metric"])
        if prev is None or r["year"] >= prev[1]:
            m[r["metric"]] = (r["value"], r["year"], r.get("qualifier", "="), r.get("note", ""))

    # 2025 录取位次(本部 T1)
    rk = {}
    for r in lines:
        if r["year"] == 2025 and r["source_tier"] == "T1" and "（" not in r["name"]:
            rk[r["uid"]] = r["rank"]

    rows = []
    for uid, m in by_school.items():
        name = schools.get(uid, {}).get("name", uid)
        tk = m.get("特控率(一本)")
        bk = m.get("本科率")
        rows.append({
            "uid": uid, "name": name,
            "tk": tk[0] if tk else None, "tk_year": tk[1] if tk else None, "tk_qual": tk[2] if tk else "",
            "bk": bk[0] if bk else None,
            "top": (m.get("最高分") or (None,))[0],
            "avg": (m.get("年级平均分") or (None,))[0],
            "n600": (m.get("600分以上人数") or (None,))[0],
            "rank2025": rk.get(uid),
            "note": (tk[3] if tk else "") or (bk[3] if bk else ""),
        })

    withtk = sorted([r for r in rows if r["tk"] is not None], key=lambda r: -r["tk"])
    notk = [r for r in rows if r["tk"] is None]

    def fmt(r):
        u = f"{r['tk']:.0%}{r['tk_qual'] if r['tk_qual'] in '+~?' else ''}" if r["tk"] is not None else "—"
        extras = []
        if r["bk"] is not None: extras.append(f"本科{r['bk']:.0%}")
        if r["avg"]: extras.append(f"均分{r['avg']}")
        if r["top"]: extras.append(f"最高{r['top']}")
        if r["n600"]: extras.append(f"600+{r['n600']}人")
        return (f"{r['name'][:16]:<16} 特控率={u:<6} 2025位次={r['rank2025'] or '—'}  "
                f"{' '.join(extras)}  {('⚠️'+r['note'][:18]) if '存疑' in (r['note'] or '') else ''}")

    print("=== 按特控率(一本率)排名 [T3·民间·低置信] ===")
    for i, r in enumerate(withtk, 1):
        print(f"{i:>2}. {fmt(r)}")
    print("\n=== 缺特控率、需按高分段/口碑人工置顶的(多为头部校) ===")
    for r in notk:
        print(f"  - {fmt(r)}")


if __name__ == "__main__":
    main()
