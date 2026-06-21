#!/usr/bin/env python3
"""
朝阳 27 校 → 官方学校代码 + 专业(班)列表  ·  链接器
======================================================
把 chaoyang.yaml 的 27 校与 2025_tongzhao_plan.json（bjeea 官方计划 OCR）关联，
产出派生文件 chaoyang_admission_codes.json，供志愿草表/前端使用。

**no-fabrication**：name→school_code 是人工核对过的映射（CODE_MAP，下方逐条核到
计划册校名），专业代码/名称/计划数/学费说明等全部来自官方计划（不臆造）。
运行时打印「yaml校名 | code | 计划册校名 | 专业数」对照表，便于复核；
计划里查不到的 code 会 FLAG。

特例：
- 莲葩园中学 = 和平街一中(105004)北苑莲葩园校区，非独立法人；和平街一中 02专业
  即"在2址(北苑)上课"，故莲葩园指向 105004 并标注 campus_major=02。
用法：python scripts/admission/link_chaoyang_codes.py
"""
import json
import re
from pathlib import Path

import yaml

# OCR 常把 2 字词拆开("合作"→"合 作"、"实验"→"实 验")。规范化:去掉两个汉字之间的空白,
# 不动 拉丁字母/数字 间的空格(如 "AP 课程")。是计划→专业名的固定清洗步骤,2026 重跑自动生效。
_CJK = r"一-鿿"


def _clean_major(name: str) -> str:
    if not name:
        return name
    s = re.sub(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])", "", name)
    return re.sub(r"\s{2,}", " ", s).strip()

KB = Path(__file__).resolve().parents[2] / "knowledge-base" / "admission" / "beijing"
PLAN = KB / "2025_tongzhao_plan.json"
CY = KB / "chaoyang.yaml"
OUT = KB / "chaoyang_admission_codes.json"

# yaml 校名 → 官方学校代码（已逐条核对计划册校名）
CODE_MAP = {
    "北京中学": "205001",
    "中国传媒大学附属中学": "205019",
    "北京市第八十中学": "105001",
    "人大附中朝阳学校": "205002",
    "清华附中朝阳学校": "205009",
    "八十中睿德分校": "205020",
    "朝阳外国语学校": "205012",
    "清华附中望京学校": "205010",
    "陈经纶中学": "105002",
    "北京中学科技分校": "205016",
    "清华附中广华学校": "205017",
    "首师大附中朝阳学校": "205018",
    "二中朝阳学校": "205005",
    "北京工业大学附属中学": "105007",
    "日坛中学": "105003",
    "和平街一中": "105004",
    "和平街一中（北苑莲葩园校区）": "105004",   # 同 105004，02专业=北苑莲葩园上课（chaoyang.yaml 现用名）
    "对外经济贸易大学附属中学": "105005",
    "东北师大附中朝阳学校": "205008",
    "中科院附属实验学校": "205004",
    "三里屯一中": "205007",
    "北京十七中": "105006",
    "北京化工大学附属中学": "205011",
    "东方德才学校": "205006",
    "北京第二外国语学院附属中学": "205014",
    "陈经纶中学团结湖分校": "205015",
    "汇文中学垂杨柳分校": "205003",
}
# 同一 code 被多个 yaml 名引用时，标注各自对应的校区专业
CAMPUS_MAJOR = {"和平街一中（北苑莲葩园校区）": "02", "和平街一中": "01"}


def main():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    cy = yaml.safe_load(CY.read_text(encoding="utf-8"))

    by_code = {}
    for r in plan["rows"]:
        if r["school_code"]:
            by_code.setdefault(r["school_code"], []).append(r)

    out = {"source": f"派生自 {PLAN.name}（bjeea 2025 官方计划 OCR）",
           "plan_year": 2025, "source_tier": "T1",
           "warning": "2025 代码/计划；2026 计划 7 月初发布后须按 SOP 一次性刷新。专业数据为官方，"
                      "name→code 映射经人工核对(CODE_MAP)；专业名经汉字间空格规范化。"
                      "完整性/代码正确性仍需对官方册逐校核对(见 docs/design/MAJOR-CODES-SOP.md)。",
           "schools": {}}
    print(f"{'yaml校名':<22}{'code':<8}{'计划册校名':<22}专业")
    flags = []
    for s in cy["schools"]:
        name = s["name"]
        code = CODE_MAP.get(name)
        if not code:
            flags.append(f"{name}: 无 CODE_MAP")
            continue
        rows = by_code.get(code, [])
        if not rows:
            flags.append(f"{name}({code}): 计划册查无此 code")
            continue
        plan_name = next((r["school_name"] for r in rows if r["school_name"]), "")
        majors = []
        for r in rows:
            if not r["major_code"]:
                continue
            majors.append({
                "major_code": r["major_code"],
                "major_name": _clean_major(r["major_name"]),
                "xuezhi": r.get("xuezhi", ""),
                "jiashi": r.get("jiashi", ""),
                "plan_total": r.get("total", ""),
                "plan_chaoyang": r.get("districts", {}).get("朝阳", ""),
                "note": r.get("special_note", ""),
            })
        rec = {"school_code": code, "plan_school_name": plan_name,
               "majors": majors}
        if name in CAMPUS_MAJOR:
            rec["campus_major"] = CAMPUS_MAJOR[name]
        out["schools"][name] = rec
        print(f"{name:<22}{code:<8}{plan_name:<22}{len(majors)}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {OUT.name}：{len(out['schools'])}/{len(cy['schools'])} 校")
    if flags:
        print("⚠ FLAGS:")
        for f in flags:
            print("  -", f)


if __name__ == "__main__":
    main()
