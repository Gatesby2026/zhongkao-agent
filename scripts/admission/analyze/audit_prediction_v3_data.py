#!/usr/bin/env python3
"""Audit hard data gates for Chaoyang rank prediction V3 (stdlib only)."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "knowledge-base/admission/beijing"


def main():
    rows = [json.loads(x) for x in (BASE / "ts/lines.jsonl").read_text().splitlines()]
    coded = {}
    for year in (2023, 2024, 2025):
        coded_text = (
            BASE / f"evidence/chaoyang-lines-{year}-professional-coded.evidence.yaml"
        ).read_text()
        coded[year] = {
            "records": int(
                re.search(r"^\s*line_records:\s*(\d+)", coded_text, re.M).group(1)
            ),
            "exact": int(
                re.search(
                    r"^\s*exact_major_code_records:\s*(\d+)", coded_text, re.M
                ).group(1)
            ),
        }
    print("# 朝阳位次预测 V3 数据审计\n")
    print("| 年份 | T1校线记录 | T1学校/校区单元 | T1带专业代码 | T3专业映射记录 |")
    print("|---:|---:|---:|---:|---:|")
    blocked = False
    for year in (2023, 2024, 2025):
        cur = [r for r in rows if r.get("year") == year and r.get("source_tier") == "T1"]
        units = {(r.get("uid"), r.get("campus")) for r in cur}
        majors = sum(bool(r.get("major_code")) for r in cur)
        t3_coded = coded.get(year, {}).get("records", 0)
        print(f"| {year} | {len(cur)} | {len(units)} | {majors} | {t3_coded} |")
        blocked |= majors == 0
    manifest = (BASE / "prediction_v3_requirements.yaml").read_text()
    print("\n## 数据集状态")
    for status in ("available", "partial", "missing", "waiting_official"):
        print(f"- `{status}`: {manifest.count('status: ' + status)}")
    print("\n## 门禁结论")
    if blocked:
        print("- **BLOCKED**：历史 T1 学校最低线不存在，禁止专业级精确点预测。")
    for year in (2023, 2024, 2025):
        code_tier = "T2官方原图镜像" if year == 2023 else "T1官方目录"
        print(
            f"- {year} 已有 {coded[year]['records']} 条 T3 专业映射记录，其中"
            f" {coded[year]['exact']} 条可连接唯一{code_tier}专业代码；"
            "校线仍为 T3。"
        )
    actual_text = (
        BASE / "evidence/chaoyang-actual-admits-2025.evidence.yaml"
    ).read_text()
    actual_samples = len(re.findall(r"^\s+- school_code:", actual_text, re.M))
    direct_text = (
        BASE / "evidence/chaoyang-group-direct-2025.evidence.yaml"
    ).read_text()
    direct_total = int(
        re.search(r"^\s*group_direct_total:\s*(\d+)", direct_text, re.M).group(1)
    )
    direct_t1 = int(
        re.search(r"^\s*official_t1_subtotal:\s*(\d+)", direct_text, re.M).group(1)
    )
    direct_2026_text = (
        BASE / "evidence/chaoyang-group-direct-2026.evidence.yaml"
    ).read_text()
    direct_2026_total = int(
        re.search(
            r"^total_group_direct_plan:\s*(\d+)", direct_2026_text, re.M
        ).group(1)
    )
    direct_2026_schools = int(
        re.search(r"^school_count:\s*(\d+)", direct_2026_text, re.M).group(1)
    )
    print(
        f"- 历史实际录取分渠道样本：{actual_samples} 校；"
        "目前仅陈经纶中学2025完整分项达到T2。"
    )
    print(
        f"- 2025集团直升逐校基准共{direct_total}人，其中{direct_t1}人有考试院T1原表；"
        f"其余{direct_total - direct_t1}人仍为T3转录。"
    )
    print(
        f"- 2026集团直升官方计划：{direct_2026_schools}校/{direct_2026_total}人，"
        "已达T1；这是计划上界，不等于最终实际录取数。"
    )
    score_band = BASE / "score_bands/chaoyang_2026.yaml"
    if score_band.exists():
        print("- 2026朝阳官方分数段已入库，可把预测位次折算为2026参考分数。")
    else:
        print("- 2026 一分一段和竞争池发布前，只能运行 V3-alpha 宽区间。")
    print("- `ts/pred_2026.json` 是旧模型结果，不视为 V3。")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
