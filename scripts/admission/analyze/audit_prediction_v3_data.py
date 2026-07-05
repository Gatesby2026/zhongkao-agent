#!/usr/bin/env python3
"""Audit hard data gates for Chaoyang rank prediction V3 (stdlib only)."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "knowledge-base/admission/beijing"


def main():
    rows = [json.loads(x) for x in (BASE / "ts/lines.jsonl").read_text().splitlines()]
    coded_text = (
        BASE / "evidence/chaoyang-lines-2025-professional-coded.evidence.yaml"
    ).read_text()
    coded_records = int(re.search(r"^\s*line_records:\s*(\d+)", coded_text, re.M).group(1))
    exact_coded = int(
        re.search(r"^\s*exact_major_code_records:\s*(\d+)", coded_text, re.M).group(1)
    )
    print("# 朝阳位次预测 V3 数据审计\n")
    print("| 年份 | T1校线记录 | T1学校/校区单元 | T1带专业代码 | T3专业映射记录 |")
    print("|---:|---:|---:|---:|---:|")
    blocked = False
    for year in (2023, 2024, 2025):
        cur = [r for r in rows if r.get("year") == year and r.get("source_tier") == "T1"]
        units = {(r.get("uid"), r.get("campus")) for r in cur}
        majors = sum(bool(r.get("major_code")) for r in cur)
        t3_coded = coded_records if year == 2025 else 0
        print(f"| {year} | {len(cur)} | {len(units)} | {majors} | {t3_coded} |")
        blocked |= majors == 0
    manifest = (BASE / "prediction_v3_requirements.yaml").read_text()
    print("\n## 数据集状态")
    for status in ("available", "partial", "missing", "waiting_official"):
        print(f"- `{status}`: {manifest.count('status: ' + status)}")
    print("\n## 门禁结论")
    if blocked:
        print("- **BLOCKED**：历史 T1 学校最低线不存在，禁止专业级精确点预测。")
    print(
        f"- 2025 已有 {coded_records} 条 T3 专业映射记录，其中 {exact_coded} 条"
        "可连接唯一官方专业代码；代码为 T1，但校线仍为 T3。"
    )
    print("- 2026 一分一段和竞争池发布前，只能运行 V3-alpha 宽区间。")
    print("- `ts/pred_2026.json` 是旧模型结果，不视为 V3。")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
