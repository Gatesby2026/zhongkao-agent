#!/usr/bin/env python3
"""
中考志愿填报 · 冲稳保推荐引擎（Phase 1 · CLI 验证版）

核心思路：录取按"区排名/位次"决定，位次跨年可比（见 scoring-system.yaml）。
家长手里有的是孩子一模/二模的区排名 —— 直接用位次做 rank-to-rank 匹配，
无需一分一段表（一分一段表只在中考真实出分后把分数换算成位次时才需要）。

约定：rank 越小越好；学校 scores[year].rank = 该校最后一名被录取者的区位次。
      学生位次 R ≤ 学校录取位次 C 即可录取。

用法：
  python scripts/admission/recommend.py --rank 2500
  python scripts/admission/recommend.py --district chaoyang --rank 2500 --all
"""
import argparse
import sys
from pathlib import Path

import yaml

import distance as dist_mod

ADMISSION_DIR = Path(__file__).resolve().parents[2] / "knowledge-base" / "admission" / "beijing"

# 分档阈值（基于 margin = (录取位次 - 学生位次) / 录取位次，正值=学生比录取线更靠前）
SAFETY_MARGIN = 0.15   # 比录取线靠前 15%+ → 保底
REACH_MARGIN = -0.12   # 比录取线落后 12% 以内 → 可冲
# 介于两者之间(0 ~ -0.12 不含、0~0.15) → 稳；落后超 12% → 够不上

# 录取位次三年极差 / 均值 超过此比例 → 标注"波动大"
VOLATILITY_THRESHOLD = 0.40


def load_district(district: str) -> dict:
    path = ADMISSION_DIR / f"{district}.yaml"
    if not path.exists():
        avail = sorted(
            p.stem for p in ADMISSION_DIR.glob("*.yaml")
            if p.stem not in {"scoring-system", "math-target-mapping"}
        )
        sys.exit(f"找不到区数据：{path}\n已有区：{', '.join(avail)}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def school_rank_history(school: dict) -> list[tuple[int, int]]:
    """返回 [(年份, 录取位次), ...]，按年份升序，过滤无 rank 的年份。"""
    out = []
    for year, rec in sorted((school.get("scores") or {}).items()):
        rank = rec.get("rank") if isinstance(rec, dict) else None
        if rank is not None:
            out.append((int(year), int(rank)))
    return out


def classify(student_rank: int, school: dict):
    """返回 (档位, margin, 参考位次C, 历史, 波动比) 或 None（数据缺失）。"""
    history = school_rank_history(school)
    if not history:
        return None
    # 参考位次：取最新一年（位次跨年可比，新口径更贴近当下竞争格局）
    ref_year, ref_rank = history[-1]
    margin = (ref_rank - student_rank) / ref_rank

    ranks = [r for _, r in history]
    volatility = (max(ranks) - min(ranks)) / (sum(ranks) / len(ranks))

    if margin >= SAFETY_MARGIN:
        band = "保"
    elif margin >= 0:
        band = "稳"
    elif margin >= REACH_MARGIN:
        band = "冲"
    else:
        band = "够不上"
    return band, margin, ref_rank, history, volatility


def fmt_dist(rd, mode_label: str, max_km) -> str:
    """rd = (距离米, 时长秒) 或 None。"""
    if rd is None:
        return "  📍距离未知"
    dist_m, dur_s = rd
    km = dist_m / 1000
    mins = round(dur_s / 60)
    far = "  ⚠️偏远" if (max_km is not None and km > max_km) else ""
    return f"  📍{mode_label}{km:.1f}km/{mins}分钟{far}"


def fmt_history(history: list[tuple[int, int]], school: dict) -> str:
    parts = []
    for year, rank in history:
        score = (school.get("scores") or {}).get(year, {}).get("score")
        parts.append(f"{year}:{score}分/{rank}名" if score else f"{year}:{rank}名")
    return "  ".join(parts)


BAND_COLOR = {"冲": "#e74c3c", "稳": "#f1c40f", "保": "#2ecc71"}


def generate_map(out_path, district_name, student_rank, home_addr, home_coord,
                 mode_label, buckets, coord_map, dist_map):
    """生成自包含交互式地图 HTML（Leaflet + 高德底图，GCJ-02 坐标一致）。"""
    import json as _json

    points = []
    for band in ("冲", "稳", "保"):
        for s, margin, ref_rank, history, vol in buckets[band]:
            c = coord_map.get(s["name"])
            if not c:
                continue
            rd = dist_map.get(s["name"])
            dist_txt = (f"{mode_label} {rd[0]/1000:.1f}km / {round(rd[1]/60)}分钟"
                        if rd else "距离未知")
            hist_txt = "  ".join(
                f"{y}年:{(s.get('scores') or {}).get(y, {}).get('score','?')}分(位次{r})"
                for y, r in history)
            points.append({
                "name": s["name"], "lat": c[0], "lon": c[1], "band": band,
                "color": BAND_COLOR[band], "level": s.get("level", ""),
                "rank": ref_rank, "margin": f"{margin:+.0%}",
                "dist": dist_txt, "hist": hist_txt, "note": s.get("note", ""),
            })

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:-apple-system,"PingFang SC",sans-serif}
  #map{height:100%}
  .hdr{position:absolute;top:10px;left:10px;z-index:1000;background:#fff;
       padding:10px 14px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.3);font-size:14px}
  .hdr b{font-size:15px}
  .legend{position:absolute;bottom:18px;left:10px;z-index:1000;background:#fff;
          padding:8px 12px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.3);font-size:13px}
  .dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
  .lbl{font-size:11px;font-weight:bold;color:#fff;text-align:center;line-height:1.1;
       text-shadow:0 0 2px rgba(0,0,0,.6)}
  .pop b{font-size:14px} .pop .meta{color:#555;font-size:12px;margin-top:4px}
</style></head><body>
<div class="hdr"><b>__DISTRICT__ 志愿地图</b><br>孩子区排名 第 __RANK__ 名 ｜ 家：__HOME__<br>
  通勤：__MODE__（路网距离）</div>
<div class="legend">
  <div><span class="dot" style="background:#e74c3c"></span>冲（略低于录取线）</div>
  <div><span class="dot" style="background:#f1c40f"></span>稳（略高于录取线）</div>
  <div><span class="dot" style="background:#2ecc71"></span>保（明显高于录取线）</div>
  <div><span class="dot" style="background:#2c3e50"></span>家</div>
</div>
<div id="map"></div>
<script>
var HOME=__HOME_COORD__, PTS=__POINTS__;
var map=L.map('map',{zoomControl:false}).setView(HOME,12);
L.control.zoom({position:'topright'}).addTo(map);
L.tileLayer('https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}',
  {subdomains:['1','2','3','4'],maxZoom:18,attribution:'高德地图'}).addTo(map);

function pin(color,txt){return L.divIcon({className:'',iconSize:[34,34],
  html:'<div style="background:'+color+';width:34px;height:34px;border-radius:50% 50% 50% 0;'+
  'transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);'+
  'display:flex;align-items:center;justify-content:center;">'+
  '<span class="lbl" style="transform:rotate(45deg)">'+txt+'</span></div>'});}

L.marker(HOME,{icon:pin('#2c3e50','家'),zIndexOffset:1000}).addTo(map)
  .bindPopup('<div class="pop"><b>家</b><br>__HOME__</div>');

var bounds=[HOME];
PTS.forEach(function(p){
  bounds.push([p.lat,p.lon]);
  var html='<div class="pop"><b>'+p.name+'</b> <span style="color:'+p.color+'">['+p.band+']</span>'+
    '<div class="meta">'+p.level+' ｜ 录取位次≈'+p.rank+'名 (margin '+p.margin+')<br>'+
    '通勤 '+p.dist+'<br>'+p.hist+(p.note?'<br>'+p.note:'')+'</div></div>';
  L.marker([p.lat,p.lon],{icon:pin(p.color,p.band)}).addTo(map).bindPopup(html);
});
map.fitBounds(bounds,{padding:[50,50]});
</script></body></html>"""

    repl = {
        "__TITLE__": f"{district_name}志愿地图",
        "__DISTRICT__": district_name,
        "__RANK__": str(student_rank),
        "__HOME__": home_addr,
        "__MODE__": mode_label,
        "__HOME_COORD__": _json.dumps([home_coord[0], home_coord[1]]),
        "__POINTS__": _json.dumps(points, ensure_ascii=False),
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    Path(out_path).write_text(html, encoding="utf-8")
    return len(points)


def main():
    ap = argparse.ArgumentParser(description="中考志愿冲稳保推荐（位次匹配）")
    ap.add_argument("--district", default="chaoyang", help="区拼音（默认 chaoyang）")
    ap.add_argument("--rank", type=int, required=True, help="孩子的区排名/位次（来自一模或二模）")
    ap.add_argument("--all", action="store_true", help="同时列出'够不上'的学校")
    ap.add_argument("--home", help="家庭住址（小区名/地铁站/街道即可），给了就算通勤距离")
    ap.add_argument("--mode", default="driving", choices=list(dist_mod.MODES),
                    help="通勤方式：driving驾车/walking步行/bicycling骑行/transit公交（默认driving）")
    ap.add_argument("--max-distance", type=float, metavar="KM",
                    help="超过该公里数的学校标注为'偏远'")
    ap.add_argument("--map", metavar="OUT.html", help="同时生成交互式地图 HTML（需配合 --home）")
    args = ap.parse_args()

    data = load_district(args.district)
    district_name = data.get("district", args.district)
    schools = data.get("schools", [])

    # 通勤距离（路网，非直线）
    dist_map = {}
    coord_map = {}
    home_coord = None
    if args.home:
        mode_label = dist_mod.MODES[args.mode][1]
        print(f"\n正在用高德算 [{mode_label}] 路网距离：{args.home} → 各校 …", file=sys.stderr)
        home_coord, dist_map, coord_map = dist_mod.attach_distances(
            [s["name"] for s in schools], args.home, district_name, args.mode)
        if home_coord is None:
            sys.exit(f"无法定位家庭住址：{args.home}（换个更具体的小区名/地铁站试试）")

    buckets = {"冲": [], "稳": [], "保": [], "够不上": []}
    for s in schools:
        res = classify(args.rank, s)
        if res is None:
            continue
        band, margin, ref_rank, history, vol = res
        buckets[band].append((s, margin, ref_rank, history, vol))

    # 每档内按录取位次升序（更好的学校在前）
    for band in buckets:
        buckets[band].sort(key=lambda t: t[2])

    print(f"\n{'='*60}")
    print(f"  {district_name} · 中考志愿推荐  |  孩子区排名：第 {args.rank} 名")
    print(f"{'='*60}")
    print("  分档依据：你的位次 vs 各校最近一年录取位次")
    print("  保=稳进 / 稳=略高于线 / 冲=略低于线可博 / 够不上=差距较大\n")

    band_labels = {
        "冲": "🔴 冲（略低于录取线，可博但风险高）",
        "稳": "🟡 稳（已高于录取线，较有把握）",
        "保": "🟢 保（明显高于录取线，基本稳进）",
    }
    order = ["冲", "稳", "保"]
    if args.all:
        order.append("够不上")
        band_labels["够不上"] = "⚫ 够不上（位次差距 >12%，仅供参考）"

    for band in order:
        items = buckets[band]
        print(f"{band_labels[band]}  —— {len(items)} 所")
        if not items:
            print("    （无）\n")
            continue
        for s, margin, ref_rank, history, vol in items:
            level = s.get("level", "")
            note = s.get("note", "")
            vol_flag = "  ⚠️录取位次年际波动大" if vol > VOLATILITY_THRESHOLD else ""
            mode_label = dist_mod.MODES[args.mode][1]
            dist_str = fmt_dist(dist_map.get(s["name"]), mode_label, args.max_distance) if args.home else ""
            print(f"    • {s['name']}  [{level}]  录取位次≈{ref_rank}名 (margin {margin:+.0%}){dist_str}{vol_flag}")
            print(f"        历年：{fmt_history(history, s)}")
            if note:
                print(f"        备注：{note}")
        print()

    # 校额到校提示（数据里有就提示）
    quota = data.get("quota_allocation")
    if quota and quota.get("policy_summary"):
        print(f"{'-'*60}")
        print("📌 校额到校提示（可能是普通初中孩子进好高中的最佳机会）：")
        for line in quota["policy_summary"].strip().splitlines():
            print(f"    {line.strip()}")
        print("    ⚠️ 校额到校看的是【本校内排名】而非全区排名，本工具暂不计算。\n")

    print(f"{'-'*60}")
    print("⚠️ 重要说明：")
    print("  1. 假设一模/二模区排名 ≈ 中考录取区排名（位次相对稳定，但非绝对）。")
    print("  2. 录取位次每年有波动，标⚠️的学校尤其需谨慎，多看历年区间。")
    print("  3. 本结果仅辅助参考，最终志愿请结合官方招生简章与学校老师建议。")
    print(f"{'='*60}\n")

    # 交互式地图
    if args.map:
        if not args.home:
            sys.exit("生成地图需要 --home（家庭住址）")
        n = generate_map(args.map, district_name, args.rank, args.home, home_coord,
                         dist_mod.MODES[args.mode][1], buckets, coord_map, dist_map)
        print(f"🗺️  地图已生成：{args.map}（{n} 所学校 + 家）")


if __name__ == "__main__":
    main()
