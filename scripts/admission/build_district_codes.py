#!/usr/bin/env python3
"""全市 15 区(朝阳除外,朝阳有人工核过的 chaoyang_admission_codes.json)「可填报专业」数据。
直接从 bjeea 官方统招计划 OCR(2025_tongzhao_plan.json,全市 322 校 T1)按区(学校码 2-3 位)
抽每校 学校代码+专业(班)+学制+计划数 → districts/<拼音>_admission_codes.json。
无录取线/位次(那需各区一分一段真源,不在此),仅"可查校/看专业/看位置"用。
方法沿用朝阳:汉字间空格规范化、校名地址清洗、provenance 标注。零编造、全官方。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_plan_tencent import clean_school_name  # 复用校名地址清洗

KB = Path(__file__).resolve().parents[2] / "knowledge-base" / "admission" / "beijing"
PLAN = KB / "2025_tongzhao_plan.json"
OUTDIR = KB / "districts"

# 学校代码 2-3 位 → 区(拼音, 中文)。10燕山并入房山;30=跨区/特殊(人大附中等)单列。
ZONE = {
    "01": ("dongcheng", "东城"), "02": ("xicheng", "西城"), "06": ("fengtai", "丰台"),
    "07": ("shijingshan", "石景山"), "08": ("haidian", "海淀"), "09": ("mentougou", "门头沟"),
    "10": ("fangshan", "房山"), "11": ("fangshan", "房山"), "12": ("tongzhou", "通州"),
    "13": ("shunyi", "顺义"), "14": ("changping", "昌平"), "15": ("daxing", "大兴"),
    "16": ("huairou", "怀柔"), "17": ("pinggu", "平谷"), "28": ("miyun", "密云"),
    "29": ("yanqing", "延庆"), "30": ("kuaqu", "跨区/特殊"),
    # 05=朝阳 故意不在此:朝阳用人工核过的 chaoyang_admission_codes.json
}


def _clean_major(name):
    if not name:
        return name
    s = re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", name)
    return re.sub(r"\s{2,}", " ", s).strip()


def main():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # 按区 → code → 学校
    by_zone = {}
    skipped = []
    for r in plan["rows"]:
        sc = str(r.get("school_code") or "")
        if len(sc) != 6:
            continue
        pref = sc[1:3]
        if pref == "05":          # 朝阳:跳过(另有核过文件)
            continue
        z = ZONE.get(pref)
        if not z:
            skipped.append((sc, r.get("school_name")))
            continue
        py, cn = z
        zd = by_zone.setdefault(py, {"district": cn, "schools": {}})
        s = zd["schools"].setdefault(sc, {
            "school_code": sc, "name": clean_school_name(r.get("school_name") or "") or r.get("school_name"),
            "majors": [],
        })
        if r.get("major_code"):
            s["majors"].append({
                "major_code": str(r["major_code"]).zfill(2),
                "major_name": _clean_major(r.get("major_name") or ""),
                "xuezhi": r.get("xuezhi", ""),
                "plan_total": r.get("total", ""),
                "note": r.get("special_note", ""),
            })

    summary = []
    for py, zd in sorted(by_zone.items()):
        out = {
            "district": zd["district"], "plan_year": 2025, "source_tier": "T1",
            "source": "派生自 2025_tongzhao_plan.json(bjeea 2025 官方统招计划 OCR)",
            "warning": "仅学校代码/专业(班)/计划数(官方);无录取线/位次(需各区一分一段, 另采)。"
                       "校名/专业经清洗+空格规范化;2026 计划发布后按 MAJOR-CODES-SOP 刷新。",
            "schools": zd["schools"],
        }
        (OUTDIR / f"{py}_admission_codes.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        nmaj = sum(len(s["majors"]) for s in zd["schools"].values())
        summary.append((py, zd["district"], len(zd["schools"]), nmaj))

    print(f"{'区':<14}{'校数':>5}{'专业行':>7}")
    tot_s = tot_m = 0
    for py, cn, ns, nm in summary:
        print(f"{cn}({py}){'':<{max(0,8-len(cn))}}{ns:>5}{nm:>7}")
        tot_s += ns; tot_m += nm
    print(f"{'合计':<14}{tot_s:>5}{tot_m:>7}  → {OUTDIR}")
    if skipped:
        print(f"\n未映射区码(单列 kuaqu/特殊): {len(skipped)} 行, 例:", skipped[:5])


if __name__ == "__main__":
    main()
