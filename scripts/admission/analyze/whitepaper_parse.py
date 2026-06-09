#!/usr/bin/env python3
"""解析白皮书 OCR(whitepaper_ocr_raw.json)→ 结构化录取线 + 高考成绩。
- 录取线:正则解析 markdown 表(专业×25/24/23 线+排名)→ whitepaper_lines.json
- 高考成绩:LLM(qwen-max)从'往年出口高考成绩'自由文本**仅抽取已写明的数字**(文本已提供,
  不靠模型记忆=安全),逐年逐指标 → chaoyang_gaokao_<year>_whitepaper.json(priority=3 覆盖旧源)
- 新校(暂无毕业生)标记,跳过高考,交 compute 标'新校·暂无出口'
"""
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "knowledge-base/admission/beijing/raw_extracts"
OCR = RAW / "whitepaper_ocr_raw.json"
KEY = os.environ.get("DASHSCOPE_API_KEY", "")
YEARS = [2022, 2023, 2024, 2025]

# 新校/暂无高考出口(白皮书明示首届未毕业);compute 据此标记,不估算高考
NEW_NO_OUTPUT = ["清华附中广华学校", "中国传媒大学附属中学", "八十中睿德分校",
                 "北京中学科技分校", "首师大附中朝阳学校"]

EXTRACT_PROMPT = """下面是某北京高中"往年出口高考成绩"的原始文字。**只从这段文字里抽取明确写出的数字**,
没写的填 null,**不要用你自己的知识补充或推算**。按年份(2022/2023/2024/2025)整理为:
- yiben: 一本率/特控率(小数, 文中"一本率80%"→0.8; 注意区分"实验班/普通班/艺术班"——优先整体/全校口径, 无整体再用普通班)
- benke: 本科率/本科上线率(小数)
- qingbei: 清华+北大人数(整数; "N人考入清华北大""清北录取N人""裸分清北N人"都算; "清北上线20%"这类比例不算人数填null)
- top: 最高分(整数)
- n700: 700分以上人数  n685: 685分及以上人数  n680: 680分以上人数  n650: 650分以上人数
- avg: 全校年级平均分(整数; "实验班均分"不算全校)
- np: 参加高考人数(整数)
只输出 JSON: {{"2022":{{...}},"2023":{{...}},"2024":{{...}},"2025":{{...}}}}，无数据的指标省略或null。

原始文字:
---
{text}
---"""


def qwen(text):
    body = json.dumps({"model": "qwen-max", "temperature": 0,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": EXTRACT_PROMPT.format(text=text)}]}).encode()
    req = urllib.request.Request("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                                 data=body, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    raw = json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else {}


def parse_lines_table(full, name):
    """从含'录取分数线及对应排名'的 markdown 表抽 (专业,25线,25排,24线,24排,23线,23排)。"""
    rows = []
    # 找表头后到下一个空行/'四、'的区块
    m = re.search(r"录取分数线及对应排名.*?\n(.*?)(?:\n\s*\n|四、|往年出口|$)", full, re.S)
    if not m:
        return rows
    for ln in m.group(1).splitlines():
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        major = cells[0]
        if major in ("专业名称", "") or "分数线" in major or "----" in major or set(major) <= {"-"}:
            continue

        def num(x):
            x = x.replace("——", "").replace("—", "").replace("·", "").strip()
            mm = re.search(r"\d+", x)
            return int(mm.group()) if mm else None
        rows.append({"major": major,
                     "y2025": [num(cells[1]), num(cells[2])],
                     "y2024": [num(cells[3]), num(cells[4])],
                     "y2023": [num(cells[5]), num(cells[6])]})
    return rows


def gaokao_segment(full):
    m = re.search(r"往年出口高考成绩[：:]?(.*?)(?:\n四、|班级介绍|·\d+·|\Z)", full, re.S)
    return (m.group(1).strip() if m else "")


def main():
    assert KEY, "需 DASHSCOPE_API_KEY"
    data = json.load(open(OCR, encoding="utf-8"))
    lines_out = []
    gk_per_year = {y: [] for y in YEARS}
    summary = {}

    for name, info in data.items():
        full = "\n".join(p["text"] for p in info["pages"])
        # ① 录取线
        for r in parse_lines_table(full, name):
            lines_out.append({"name": name, **r})
        # ② 高考
        if name in NEW_NO_OUTPUT:
            summary[name] = "新校·暂无高考出口(跳过)"
            continue
        seg = gaokao_segment(full)
        if not seg or "暂无出口" in seg or "三年后体现" in seg:
            summary[name] = "无高考段或暂无出口"
            continue
        ext = qwen(seg)
        cnt = 0
        for y in YEARS:
            cell = ext.get(str(y)) or {}
            if not isinstance(cell, dict):
                continue
            row = {"abbr": name}
            for k in ("yiben", "benke", "qingbei", "top", "n700", "n685", "n680", "n650", "avg", "np"):
                v = cell.get(k)
                if v is not None:
                    km = {"yiben": "tk", "benke": "bk", "qingbei": "qb", "top": "top",
                          "n700": "n700", "n685": "n685", "n680": "n680", "n650": "n600",  # n650→近似归 600+档? 单列
                          "avg": "avg", "np": "np"}[k]
                    row[km] = v
                    cnt += 1
            if len(row) > 1:
                row["note"] = "白皮书·学校公布/机构汇编"
                gk_per_year[y].append(row)
        summary[name] = f"高考抽取 {cnt} 项"

    # 写录取线
    json.dump({"source_name": "2026朝阳高中指南白皮书·往年录取线(网传版)", "source_tier": "T3",
               "source_url": "白皮书 第三章", "collected": "2026-06", "priority": 2,
               "rows": lines_out},
              open(RAW / "whitepaper_luxian_raw.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 写高考(每年一文件,priority=3 覆盖旧源)
    for y in YEARS:
        rows = gk_per_year[y]
        if not rows:
            continue
        names = {r["abbr"]: r["abbr"] for r in rows}
        json.dump({"year": y, "source_name": "2026朝阳高中指南白皮书·往年高考(学校公布/机构汇编)",
                   "source_tier": "T3", "source_url": "白皮书 第三章", "collected": "2026-06",
                   "priority": 3, "alias_to_name": names, "rows": rows},
                  open(RAW / f"chaoyang_gaokao_{y}_zwhitepaper.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"写 chaoyang_gaokao_{y}_zwhitepaper.json: {len(rows)} 校")
    print(f"写 whitepaper_lines.json: {len(lines_out)} 行")
    print("\n=== 各校处理结果 ===")
    for n, s in summary.items():
        print(f"  {n[:18]:<18} {s}")
    print("\n新校(暂无出口):", "、".join(NEW_NO_OUTPUT))


if __name__ == "__main__":
    main()
