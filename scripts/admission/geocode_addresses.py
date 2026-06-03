#!/usr/bin/env python3
"""
坐标层：用「已核实的校区地址」做高德 geocode + 名称交叉校验
==========================================================
输入：knowledge-base/admission/<city>/<district>.yaml 每校 location{address, campuses[].address}
      —— 地址已由 ADDRESS-VERIFICATION.md 流程核实，禁止再用裸校名 geocode。
输出：同目录 <district>_coords.json（派生产物，可重生），distance.py 优先读它。

每个校区做两件事并交叉校验：
  1. geocode(address)        → 主坐标 + Amap 返回的 level + formatted_address
  2. place/text(校名)        → 名称 POI 坐标，与主坐标算直线距离 name_xcheck_km
判定 geo_status：
  ok      地址 geocode 成功、落在本区、level 精细（门牌/POI/道路）
  coarse  geocode 成功但 level 粗（道路以上/只有粗略地址 address_rough）
  review  落点不在本区，或名称交叉校验差异大（人工复核；坐标仍取地址 geocode 结果）
  failed  geocode 失败
坐标系：高德返回 GCJ-02，与 direction API、前端高德底图一致，直接用。

用法：
  AMAP_KEY=... python scripts/admission/geocode_addresses.py --district chaoyang
  加 --dry-run 只打印不写文件。
"""
import argparse
import json
import math
import os
import subprocess
import time
import urllib.parse
from datetime import date
from pathlib import Path

import yaml

AMAP_KEY = os.environ.get("AMAP_KEY", "25725f95f093bed58bf739e1fa289ad4")
KB_DIR = Path(__file__).resolve().parents[2] / "knowledge-base" / "admission"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
GEOCODE_CACHE = CACHE_DIR / "addr_geocode_cache.json"

DISTRICT_CN = {"chaoyang": "朝阳区", "haidian": "海淀区",
               "xicheng": "西城区", "dongcheng": "东城区"}
# 精细到可信的 Amap geocode level（粗于此则标 coarse）
# 注：高德对门牌返回"门址"或"门牌号"；"兴趣点/热点"为 POI；"道路/公交地铁站点"街道级亦可用。
# "住宅区/小区/村庄/小巷"为片区级，坐标够算通勤但精度标 coarse。
FINE_LEVELS = {"门牌号", "门址", "兴趣点", "热点", "道路",
               "公交站点", "地铁站", "公交地铁站点", "单元楼", "单元房", "楼层"}


def _curl_json(url: str):
    r = subprocess.run(["curl", "-s", "--max-time", "12", url],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def _load_cache(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_cache(p: Path, d: dict):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def haversine_km(a, b) -> float:
    """a,b = (lat, lon)。返回直线公里。"""
    R = 6371.0
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    s = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0]))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(s))


def amap_geocode(address: str, district_cn: str, cache: dict):
    """address → {lat, lon, level, formatted} | None（GCJ-02）。"""
    ck = f"GEO|{address}"
    if ck in cache:
        return cache[ck]
    url = (f"https://restapi.amap.com/v3/geocode/geo"
           f"?address={urllib.parse.quote(address)}"
           f"&city={urllib.parse.quote('北京')}&key={AMAP_KEY}")
    data = _curl_json(url)
    res = None
    if data and data.get("status") == "1" and data.get("geocodes"):
        codes = data["geocodes"]
        g = next((x for x in codes if district_cn in x.get("formatted_address", "")), codes[0])
        loc = g.get("location")
        if loc:
            lon, lat = loc.split(",")
            res = {"lat": float(lat), "lon": float(lon),
                   "level": g.get("level", ""),
                   "formatted": g.get("formatted_address", "")}
    cache[ck] = res
    _save_cache(GEOCODE_CACHE, cache)
    return res


def amap_place(name: str, district_cn: str, cache: dict):
    """校名 POI 搜索 → {lat, lon, name, addr} | None（GCJ-02，交叉校验用）。"""
    ck = f"POI|{name}"
    if ck in cache:
        return cache[ck]
    url = (f"https://restapi.amap.com/v3/place/text"
           f"?keywords={urllib.parse.quote(name)}"
           f"&city={urllib.parse.quote('北京')}&citylimit=true"
           f"&key={AMAP_KEY}")
    data = _curl_json(url)
    res = None
    if data and data.get("status") == "1" and data.get("pois"):
        pois = data["pois"]
        p = next((x for x in pois if district_cn in (x.get("adname", "") + x.get("address", "")
                  if isinstance(x.get("address"), str) else x.get("adname", ""))), pois[0])
        loc = p.get("location")
        if loc:
            lon, lat = loc.split(",")
            res = {"lat": float(lat), "lon": float(lon),
                   "name": p.get("name", ""), "adname": p.get("adname", "")}
    cache[ck] = res
    _save_cache(GEOCODE_CACHE, cache)
    return res


def geocode_campus(school_name, campus_name, address, addr_confidence,
                   district_cn, cache, approx=False):
    """单个校区 → 坐标记录 dict。"""
    rec = {"campus": campus_name, "address": address,
           "lat": None, "lon": None, "source": "amap/geocode",
           "level": None, "formatted": None,
           "name_xcheck_km": None, "geo_status": "failed",
           "addr_confidence": addr_confidence, "approx": approx, "flags": []}
    if not address:
        rec["geo_status"] = "failed"
        rec["flags"].append("no_address")
        return rec

    g = amap_geocode(address, district_cn, cache)
    if not g:
        rec["flags"].append("geocode_failed")
        return rec
    rec.update(lat=g["lat"], lon=g["lon"], level=g["level"], formatted=g["formatted"])

    in_district = district_cn in (g["formatted"] or "")
    fine = g["level"] in FINE_LEVELS
    if approx or not fine:
        rec["geo_status"] = "coarse"
    else:
        rec["geo_status"] = "ok"
    if not in_district:
        rec["geo_status"] = "review"
        rec["flags"].append(f"not_in_district(formatted={g['formatted']})")

    # 名称 POI 交叉校验：纯信息/flag，不改 geo_status。
    # 对"已纠正高中部地址/多校区/借址"的学校，校名POI常指向本部或另一校区，
    # 大 gap 是预期而非错误（如朝阳外国语地址=来广营 vs 校名POI=慧忠里本部 6km）。
    # 坐标始终以「核实地址」geocode 为准；gap 大只提示人工瞄一眼。
    poi = amap_place(school_name, district_cn, cache)
    if poi:
        d = haversine_km((g["lat"], g["lon"]), (poi["lat"], poi["lon"]))
        rec["name_xcheck_km"] = round(d, 2)
        if d > 2.0:
            rec["flags"].append(f"name_poi_far({d:.1f}km,POI={poi['name']})")
    else:
        rec["flags"].append("name_poi_not_found")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", default="chaoyang")
    ap.add_argument("--city", default="beijing")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    district_cn = DISTRICT_CN.get(args.district, args.district)
    yaml_path = KB_DIR / args.city / f"{args.district}.yaml"
    out_path = KB_DIR / args.city / f"{args.district}_coords.json"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    cache = _load_cache(GEOCODE_CACHE)

    out = {"generated": str(date.today()), "district": args.district,
           "source": "amap v3 geocode + place/text 名称交叉校验",
           "coord_system": "GCJ-02",
           "note": "派生产物，可由 geocode_addresses.py 重生；地址源见 "
                   f"{args.district}.yaml location；方法见 ADDRESS-VERIFICATION.md",
           "schools": {}}

    stat = {"ok": 0, "coarse": 0, "review": 0, "failed": 0}
    for s in data.get("schools", []):
        loc = s.get("location") or {}
        primary_addr = loc.get("address") or loc.get("address_rough")
        approx_primary = not loc.get("address")  # address 为 null 时用 rough，标 approx
        campuses = []
        # 主校区
        campuses.append(geocode_campus(
            s["name"], loc.get("campus", ""), primary_addr,
            loc.get("confidence", ""), district_cn, cache, approx=approx_primary))
        # 附加校区（location.campuses）
        for c in (loc.get("campuses") or []):
            campuses.append(geocode_campus(
                s["name"], c.get("name", ""), c.get("address"),
                loc.get("confidence", ""), district_cn, cache, approx=False))

        out["schools"][s["name"]] = {"campuses": campuses}
        for c in campuses:
            stat[c["geo_status"]] = stat.get(c["geo_status"], 0) + 1
            mark = {"ok": "✓", "coarse": "~", "review": "⚠", "failed": "✗"}[c["geo_status"]]
            print(f"  {mark} {s['name']}·{c['campus'][:12]:<12} "
                  f"{c['geo_status']:<6} lvl={c['level']} "
                  f"xck={c['name_xcheck_km']} {','.join(c['flags']) if c['flags'] else ''}")
        time.sleep(0.1)

    print(f"\n校区计：{stat}")
    if args.dry_run:
        print("--dry-run，未写文件")
        return
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {out_path}")


if __name__ == "__main__":
    main()
