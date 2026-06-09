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

    # schools.yaml(主表)
    with open(TS / "schools.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(schools_master, f, allow_unicode=True, sort_keys=False)
    # lines.jsonl(长表,按 uid,year 排序)
    lines.sort(key=lambda r: (r["uid"], r["year"]))
    with open(TS / "lines.jsonl", "w", encoding="utf-8") as f:
        for r in lines:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    yrs = sorted({r["year"] for r in lines})
    print(f"schools.yaml: {len(schools_master)} 校")
    print(f"lines.jsonl: {len(lines)} 条, 年份 {yrs}")
    # 趋势抽样
    for kw in ["中科院附属", "中国传媒", "和平街一中"]:
        seq = sorted([r for r in lines if kw in r["name"] and "校区" not in r["name"]], key=lambda r: r["year"])
        if seq:
            print(f"  {seq[0]['name']}: " + " → ".join(f"{r['year']}:{r['rank']}" for r in seq))


if __name__ == "__main__":
    sys.exit(main())
