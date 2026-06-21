#!/usr/bin/env python3
"""给全市 15 区(districts/*_admission_codes.json)的学校批量 geocode → districts/<拼音>_coords.json。
统一走高德 GCJ-02(与朝阳口径一致,不混 WGS-84 旧库),按"北京市<区><校名>"地理编码,
落区校验 + 置信度(门牌级 high / poi 级 mid / 仅市级 low)。仅供查校上图,无录取线不算精确通勤。
  AMAP_KEY=... python scripts/admission/build_district_coords.py
"""
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geocode_addresses as G

KB = Path(__file__).resolve().parents[2] / "knowledge-base" / "admission" / "beijing"
DIR = KB / "districts"


def main():
    cache = G._load_cache(G.GEOCODE_CACHE) if hasattr(G, "_load_cache") else {}
    files = sorted(DIR.glob("*_admission_codes.json"))
    grand = {"ok": 0, "coarse": 0, "fail": 0, "wrong_zone": 0}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        cn = d["district"]
        if "/" in cn:                # kuaqu/特殊:区不明确,跳过 geocode
            continue
        coords = {}
        for s in d["schools"].values():
            name = s["name"]
            r = G.amap_geocode(f"北京市{cn}{name}", cn, cache)
            if not r:
                r = G.amap_geocode(f"北京市{name}", cn, cache)
            if not r:
                grand["fail"] += 1
                continue
            lvl = r.get("level", "")
            in_zone = cn in (r.get("formatted") or "")
            conf = ("high" if lvl in ("门牌号", "兴趣点", "POI") and in_zone
                    else "mid" if in_zone else "low")
            if conf == "high":
                grand["ok"] += 1
            elif conf == "low":
                grand["coarse"] += 1
            else:
                grand["ok"] += 1
            if not in_zone:
                grand["wrong_zone"] += 1
            coords[name] = {"lat": r["lat"], "lon": r["lon"], "level": lvl,
                            "conf": conf, "in_zone": in_zone, "formatted": r.get("formatted", "")}
            time.sleep(0.12)
        py = f.name.replace("_admission_codes.json", "")
        out = {"district": cn, "coord_system": "GCJ-02", "source": "高德 geocode(校名)",
               "warning": "校名级 geocode,门牌精度有限;仅供查校上图。", "schools": coords}
        (DIR / f"{py}_coords.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{cn:<6} {len(coords)}/{len(d['schools'])} 校出坐标")
    print("汇总:", grand)


if __name__ == "__main__":
    main()
