#!/usr/bin/env python3
"""
学校通勤距离模块（高德路网距离，非直线）

- 从已有坐标库（highschools_final.json + school_addresses.json）按名称（含缩写展开）匹配学校坐标
- 缺坐标的学校用高德 geocode API 现场补全并缓存
- 用高德 direction API 算 origin→学校 的真实路网距离/时长（驾车/步行/骑行/公交）
- 所有 API 结果落盘缓存，避免重复调用

被 recommend.py import；也可单独跑自测：python scripts/admission/distance.py
"""
import json
import os
import re
import subprocess
import urllib.parse
from pathlib import Path

AMAP_KEY = os.environ.get("AMAP_KEY", "25725f95f093bed58bf739e1fa289ad4")
HS_DIR = Path(__file__).resolve().parents[2] / "knowledge-original" / "beijing-highschools"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
ROUTE_CACHE = CACHE_DIR / "route_cache.json"
GEO_CACHE = CACHE_DIR / "home_geocode_cache.json"

MODES = {
    "driving": ("v3/direction/driving", "驾车"),
    "walking": ("v3/direction/walking", "步行"),
    "bicycling": ("v4/direction/bicycling", "骑行"),
    "transit": ("v3/direction/transit/integrated", "公交"),
}

# 北京校名缩写 → 全称（用于把简称对齐到坐标库里的官方全称）
ABBR = {
    "人大附中": "中国人民大学附属中学",
    "清华附中": "清华大学附属中学",
    "北大附中": "北京大学附属中学",
    "首师大附中": "首都师范大学附属中学",
    "首师大": "首都师范大学",
    "北师大附中": "北京师范大学附属中学",
    "北师大": "北京师范大学",
    "东北师大": "东北师范大学",
    "中科院": "中国科学院",
    "民大": "中央民族大学",
    "中国传媒大学附属中学": "中国传媒大学附属中学",
    "贸大": "对外经济贸易大学",
    "工大": "北京工业大学",
    "化工大学": "北京化工大学",
    "理工大学": "北京理工大学",
    "二外": "北京第二外国语学院",
    "交大": "北京交通大学",
    "农大": "中国农业大学",
}


def _curl_json(url: str):
    r = subprocess.run(["curl", "-s", "--max-time", "12", url], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def _load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_cache(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm(name: str) -> str:
    """归一化校名用于匹配：去前缀/括号、展开缩写、去装饰词。"""
    n = re.sub(r"[（(].*?[)）]", "", name)        # 去括号后缀
    n = re.sub(r"^北京市?", "", n)
    for short, full in ABBR.items():
        n = n.replace(short, full)
    n = (n.replace("学校", "")
           .replace("附属中学", "附中")
           .replace("第", "")
           .replace("中学", "中"))
    return re.sub(r"\s+", "", n)


def build_coords_index() -> dict:
    """归一化校名 → (lat, lon)。合并两个坐标库，朝阳优先全库覆盖。"""
    idx = {}
    for fn in ["highschools_final.json", "school_addresses.json"]:
        p = HS_DIR / fn
        if not p.exists():
            continue
        for a in json.loads(p.read_text(encoding="utf-8")):
            if a.get("lat") and a.get("lon"):
                idx.setdefault(_norm(a["name"]), (a["lat"], a["lon"]))
    return idx


def lookup_school_coords(name: str, district_cn: str, coords_idx: dict, geo_cache: dict):
    """返回 (lat, lon)。先查坐标库（精确+子串），未命中则高德 geocode 兜底并缓存。"""
    key = _norm(name)
    if key in coords_idx:
        return coords_idx[key]
    # 子串双向匹配（处理"科技分校"等附加成分）
    for k, v in coords_idx.items():
        if key and (key in k or k in key):
            return v
    # geocode 兜底
    cache_key = f"{district_cn}|{name}"
    if cache_key in geo_cache:
        c = geo_cache[cache_key]
        return (c["lat"], c["lon"]) if c else None
    url = (f"https://restapi.amap.com/v3/geocode/geo"
           f"?address={urllib.parse.quote(name)}&city={urllib.parse.quote('北京')}&key={AMAP_KEY}")
    data = _curl_json(url)
    res = None
    if data and data.get("status") == "1" and data.get("geocodes"):
        g = next((x for x in data["geocodes"] if district_cn in x.get("formatted_address", "")),
                 data["geocodes"][0])
        loc = g.get("location")
        if loc:
            lon, lat = loc.split(",")
            res = {"lat": float(lat), "lon": float(lon)}
    geo_cache[cache_key] = res
    _save_cache(GEO_CACHE, geo_cache)
    return (res["lat"], res["lon"]) if res else None


def geocode_home(address: str, geo_cache: dict):
    """家庭住址 → (lat, lon)。"""
    cache_key = f"HOME|{address}"
    if cache_key in geo_cache:
        c = geo_cache[cache_key]
        return (c["lat"], c["lon"]) if c else None
    url = (f"https://restapi.amap.com/v3/geocode/geo"
           f"?address={urllib.parse.quote(address)}&city={urllib.parse.quote('北京')}&key={AMAP_KEY}")
    data = _curl_json(url)
    res = None
    if data and data.get("status") == "1" and data.get("geocodes"):
        loc = data["geocodes"][0].get("location")
        if loc:
            lon, lat = loc.split(",")
            res = {"lat": float(lat), "lon": float(lon)}
    geo_cache[cache_key] = res
    _save_cache(GEO_CACHE, geo_cache)
    return (res["lat"], res["lon"]) if res else None


def route(origin, dest, mode: str, route_cache: dict):
    """返回 (距离米, 时长秒) 或 None。origin/dest = (lat, lon)。"""
    o = f"{origin[1]:.6f},{origin[0]:.6f}"   # 高德要 lon,lat
    d = f"{dest[1]:.6f},{dest[0]:.6f}"
    ck = f"{mode}|{o}|{d}"
    if ck in route_cache:
        v = route_cache[ck]
        return tuple(v) if v else None

    path, _ = MODES[mode]
    if mode == "transit":
        url = (f"https://restapi.amap.com/{path}?origin={o}&destination={d}"
               f"&city={urllib.parse.quote('北京')}&key={AMAP_KEY}")
    else:
        url = f"https://restapi.amap.com/{path}?origin={o}&destination={d}&key={AMAP_KEY}"
    data = _curl_json(url)

    res = None
    if data:
        if mode == "bicycling":
            paths = data.get("data", {}).get("paths") or []
            if paths:
                res = (int(paths[0]["distance"]), int(paths[0]["duration"]))
        elif mode == "transit":
            transits = data.get("route", {}).get("transits") or []
            if transits:
                res = (int(transits[0]["distance"]), int(transits[0]["duration"]))
        else:
            paths = data.get("route", {}).get("paths") or []
            if paths:
                res = (int(paths[0]["distance"]), int(paths[0]["duration"]))
    route_cache[ck] = res
    _save_cache(ROUTE_CACHE, route_cache)
    return res


def get_campuses(school: dict, district_cn: str, coords_idx: dict, geo_cache: dict):
    """返回 [(校区名, (lat,lon)), ...]。yaml 有 campuses 用之，否则按校名定位单点。"""
    if school.get("campuses"):
        return [(c.get("name", ""), (c["lat"], c["lon"])) for c in school["campuses"]]
    c = lookup_school_coords(school["name"], district_cn, coords_idx, geo_cache)
    return [("", c)] if c else []


def compute_distances(schools, home_addr, district_cn, mode="driving"):
    """算各校（含多校区）到家的路网距离。
    返回 (home坐标, {校名: [(校区名, (lat,lon), (米,秒)|None), ...]})。"""
    geo_cache = _load_cache(GEO_CACHE)
    route_cache = _load_cache(ROUTE_CACHE)
    coords_idx = build_coords_index()

    home = geocode_home(home_addr, geo_cache)
    if home is None:
        return None, {}

    out = {}
    for s in schools:
        rows = []
        for cname, ccoord in get_campuses(s, district_cn, coords_idx, geo_cache):
            rd = route(home, ccoord, mode, route_cache) if ccoord else None
            rows.append((cname, ccoord, rd))
        out[s["name"]] = rows
    return home, out


def private_schools(district_cn: str, public_names: set):
    """坐标库里属于该区、但不在统招公办名单里的学校（民办/国际等）。
    返回 [{name, lat, lon}, ...]。"""
    pub_norm = {_norm(n) for n in public_names}
    out, seen = [], set()
    for fn in ["highschools_final.json", "school_addresses.json"]:
        p = HS_DIR / fn
        if not p.exists():
            continue
        for a in json.loads(p.read_text(encoding="utf-8")):
            if a.get("district") != district_cn or not a.get("lat"):
                continue
            key = _norm(a["name"])
            if key in pub_norm or key in seen:
                continue
            # 跳过明显的分校区重复（子串命中已收录的）
            if any(key in s or s in key for s in pub_norm if s):
                continue
            seen.add(key)
            out.append({"name": a["name"], "lat": a["lat"], "lon": a["lon"]})
    return out


if __name__ == "__main__":
    import yaml
    cy = yaml.safe_load(open(HS_DIR.parent / "../knowledge-base/admission/beijing/chaoyang.yaml"))
    idx = build_coords_index()
    geo = _load_cache(GEO_CACHE)
    matched = miss = 0
    for s in cy["schools"]:
        c = lookup_school_coords(s["name"], "朝阳区", idx, geo)
        if c:
            matched += 1
        else:
            miss += 1
            print("  仍缺:", s["name"])
    print(f"匹配 {matched}/{len(cy['schools'])}")
