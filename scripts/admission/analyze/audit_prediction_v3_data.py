#!/usr/bin/env python3
"""Audit hard data gates for Chaoyang rank prediction V3 (stdlib only)."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "knowledge-base/admission/beijing"


def main():
    rows = [json.loads(x) for x in (BASE / "ts/lines.jsonl").read_text().splitlines()]
    print("# 朝阳位次预测 V3 数据审计\n")
    print("| 年份 | T1记录 | T1学校/校区单元 | 带专业代码 |")
    print("|---:|---:|---:|---:|")
    blocked = False
    for year in (2023, 2024, 2025):
        cur = [r for r in rows if r.get("year") == year and r.get("source_tier") == "T1"]
        units = {(r.get("uid"), r.get("campus")) for r in cur}
        majors = sum(bool(r.get("major_code")) for r in cur)
        print(f"| {year} | {len(cur)} | {len(units)} | {majors} |")
        blocked |= majors == 0
    manifest = (BASE / "prediction_v3_requirements.yaml").read_text()
    print("\n## 数据集状态")
    for status in ("available", "partial", "missing", "waiting_official"):
        print(f"- `{status}`: {manifest.count('status: ' + status)}")
    print("\n## 门禁结论")
    if blocked:
        print("- **BLOCKED**：历史 T1 数据没有专业代码，禁止专业级精确点预测。")
    print("- 2026 一分一段和竞争池发布前，只能运行 V3-alpha 宽区间。")
    print("- `ts/pred_2026.json` 是旧模型结果，不视为 V3。")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
