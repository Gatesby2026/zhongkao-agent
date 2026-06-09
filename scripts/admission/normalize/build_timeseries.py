#!/usr/bin/env python3
"""把已结构化的当年快照(chaoyang.yaml 等)拍平进跨年长表 ts/*，供趋势/预测/增值分析。

产出(均在 knowledge-base/admission/beijing/ts/):
  schools.yaml   学校主表(uid 主键)
  lines.jsonl    录取线时序(一行=学校×年×批次×来源)  ← 分析主表

数据源(本脚本): chaoyang.yaml 的 scores(2023-2025 统招线+区位次,原始 bjeea 录取线,项目已核)。
后续: 网采的录取线/高考喜报 normalize 后 append 到同表(带各自 source/tier/confidence)。
幂等:每次重新生成 lines.jsonl 中 source=chaoyang.yaml 的部分 + schools.yaml。
"""
import json
import sys
from pathlib import Path

import yaml

KB = Path(__file__).resolve().parents[3] / "knowledge-base/admission/beijing"
TS = KB / "ts"
TS.mkdir(parents=True, exist_ok=True)


def load():
    cy = yaml.safe_load(open(KB / "chaoyang.yaml", encoding="utf-8"))
    codes = json.load(open(KB / "chaoyang_admission_codes.json", encoding="utf-8")).get("schools", {})
    coords = json.load(open(KB / "chaoyang_coords.json", encoding="utf-8")).get("schools", {})
    return cy, codes, coords


def uid_of(name, code):
    return code if code else f"统招:{name}"


def first_coord(coords, name):
    e = coords.get(name) or {}
    camps = e.get("campuses") or []
    if camps:
        return camps[0].get("lat"), camps[0].get("lon"), camps[0].get("campus")
    return None, None, None


def main():
    cy, codes, coords = load()
    schools_master, lines = [], []
    for s in cy.get("schools", []):
        name = s.get("name")
        if not name:
            continue
        code = (codes.get(name) or {}).get("school_code")
        uid = uid_of(name, code)
        lat, lon, campus = first_coord(coords, name)
        schools_master.append({
            "uid": uid, "name": name, "school_code": code,
            "type": "公办普高", "district": "朝阳", "campus": campus,
            "lat": lat, "lon": lon,
        })
        for year, rec in (s.get("scores") or {}).items():
            if not isinstance(rec, dict):
                continue
            lines.append({
                "uid": uid, "name": name, "year": int(year), "batch": "统招",
                "campus": campus, "major_code": None, "major_name": None,
                "score": rec.get("score"), "score_total": rec.get("total"),
                "rank": rec.get("rank"), "rank_scope": "区",
                "plan": None,
                "source_url": "knowledge-base/admission/beijing/chaoyang.yaml",
                "source_tier": "T1", "collected": "2026-06",
                "confidence": "high" if rec.get("rank") is not None else "low",
                "note": "原始 bjeea 录取线，项目已结构化",
            })

    name2uid = {s["name"]: s["uid"] for s in schools_master}

    # ② 多源录取线:raw_extracts/*lines*.json(T3 平台抽取)— 与 T1 并存,供对账/趋势,不覆盖 T1
    TOTALS = {2022: 660, 2023: 660, 2024: 670}
    for ex in sorted((KB / "raw_extracts").glob("*lines*.json")) if (KB / "raw_extracts").exists() else []:
        e = json.load(open(ex, encoding="utf-8"))
        alias = e.get("alias_to_name", {})
        for row in e.get("rows", []):
            cn = alias.get(row["abbr"])
            uid = name2uid.get(cn)
            if not uid:
                print(f"  ⚠️ 未映射: {row['abbr']} → {cn}(跳过)")
                continue
            for yk, yr in (("y2022", 2022), ("y2023", 2023), ("y2024", 2024)):
                v = row.get(yk) or [None, None]
                if v[1] is None:
                    continue
                lines.append({
                    "uid": uid, "name": cn, "year": yr, "batch": "统招",
                    "campus": None, "major_code": None, "major_name": None,
                    "score": v[0], "score_total": TOTALS.get(yr), "rank": v[1], "rank_scope": "区",
                    "plan": None, "source_url": e.get("source_url"),
                    "source_tier": e.get("source_tier", "T3"), "collected": e.get("collected"),
                    "confidence": "low", "note": e.get("source_name", ""),
                })

    # ③ 高考出口(U 轴):raw_extracts/*gaokao*.json → gaokao.jsonl(均 T3·民间·低置信)
    GK_METRIC = {"tk": "特控率(一本)", "bk": "本科率", "avg": "年级平均分",
                 "top": "最高分", "n600": "600分以上人数", "n680": "680分以上人数", "np": "参加高考人数"}
    gaokao = []
    for ex in sorted((KB / "raw_extracts").glob("*gaokao*.json")) if (KB / "raw_extracts").exists() else []:
        e = json.load(open(ex, encoding="utf-8"))
        alias, yr = e.get("alias_to_name", {}), e.get("year")
        for row in e.get("rows", []):
            cn = alias.get(row["abbr"]); uid = name2uid.get(cn)
            if not uid:
                print(f"  ⚠️ 高考未映射: {row['abbr']} → {cn}(跳过)"); continue
            for mk, mname in GK_METRIC.items():
                if row.get(mk) is None:
                    continue
                gaokao.append({
                    "uid": uid, "name": cn, "year": yr, "metric": mname,
                    "value": row[mk], "qualifier": row.get(mk + "_qual", "="),
                    "source_url": e.get("source_url"), "source_tier": e.get("source_tier", "T3"),
                    "collected": e.get("collected"), "confidence": "low",
                    "note": "民间·非官方·喜报口径不一" + (("；" + row["note"]) if row.get("note") else ""),
                })
    gaokao.sort(key=lambda r: (r["uid"], r["year"], r["metric"]))
    with open(TS / "gaokao.jsonl", "w", encoding="utf-8") as f:
        for r in gaokao:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 对账:同 uid×year 的 T1 vs T3 区排冲突
    by_key = {}
    for r in lines:
        by_key.setdefault((r["uid"], r["year"]), []).append(r)
    conflicts = []
    for (uid, yr), rs in by_key.items():
        # T1 取"本部"(campus 不含校区)避免同代码多校区误判为源冲突
        t1 = next((r["rank"] for r in rs if r["source_tier"] == "T1" and r["rank"] is not None
                   and "（" not in r["name"]), None)   # 本部=校名不带(…校区)后缀
        t3 = next((r["rank"] for r in rs if r["source_tier"] == "T3" and r["rank"] is not None), None)
        if t1 is not None and t3 is not None and abs(t1 - t3) > 150:
            conflicts.append((rs[0]["name"], yr, t1, t3))

    # schools.yaml(主表)
    with open(TS / "schools.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(schools_master, f, allow_unicode=True, sort_keys=False)
    # lines.jsonl(长表,按 uid,year 排序)
    lines.sort(key=lambda r: (r["uid"], r["year"]))
    with open(TS / "lines.jsonl", "w", encoding="utf-8") as f:
        for r in lines:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    yrs = sorted({r["year"] for r in lines})
    bytier = {}
    for r in lines:
        bytier[r["source_tier"]] = bytier.get(r["source_tier"], 0) + 1
    print(f"schools.yaml: {len(schools_master)} 校")
    print(f"lines.jsonl: {len(lines)} 条, 年份 {yrs}, 信源 {bytier}")
    print(f"gaokao.jsonl: {len(gaokao)} 条")
    # 捡漏线索:特控率 vs 录取位次(高产出/相对易进)
    tk = {r["uid"]: r["value"] for r in gaokao if r["metric"].startswith("特控率")}
    rk25 = {r["uid"]: r["rank"] for r in lines if r["year"] == 2025 and r["source_tier"] == "T1" and "（" not in r["name"]}
    nm = {s["uid"]: s["name"] for s in schools_master}
    cand = sorted([(uid, tk[uid], rk25[uid], nm.get(uid, uid)) for uid in tk if uid in rk25],
                  key=lambda x: -x[1])
    print("  特控率 vs 2025录取位次(高产出+位次靠后=潜在捡漏):")
    for uid, t, r, n in cand:
        print(f"    {n[:14]:<14} 特控率≈{t:.0%}  2025位次={r}")
    if conflicts:
        print("⚠️ T1/T3 区排冲突(差>150,需人工复核,均保留不覆盖):")
        for n, yr, t1, t3 in conflicts:
            print(f"    {n} {yr}: T1={t1} vs T3={t3}")
    # 趋势抽样
    for kw in ["中科院附属", "中国传媒", "和平街一中"]:
        seq = sorted([r for r in lines if kw in r["name"] and "校区" not in r["name"]], key=lambda r: r["year"])
        if seq:
            print(f"  {seq[0]['name']}: " + " → ".join(f"{r['year']}:{r['rank']}" for r in seq))


if __name__ == "__main__":
    sys.exit(main())
