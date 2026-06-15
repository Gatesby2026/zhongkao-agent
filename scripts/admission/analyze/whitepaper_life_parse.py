#!/usr/bin/env python3
"""从白皮书已 OCR 的档案(公办+民办+职高)抽"校园生活/班型"维度 → campus_life.json(按校名)。
复用 raw_extracts/whitepaper_*_ocr.json(零新增 OCR)。LLM 仅从已给文本抽取(安全)。
供 unified 按名挂载到 extra.campus_life,详情面板"校园生活"区展示。
"""
import json
import os
import re
import concurrent.futures as cf
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "knowledge-base/admission/beijing/raw_extracts"
OUT = ROOT / "knowledge-base/admission/beijing/campus_life.json"
KEY = os.environ.get("DASHSCOPE_API_KEY", "")
SRCS = ["whitepaper_ocr_raw.json", "whitepaper_minban_ocr.json", "whitepaper_voc_ocr.json"]

PROMPT = """下面是某北京高中在《2026朝阳高中指南白皮书》里的档案原文(含"班级介绍/校园生活/往届学生有话说"等节)。
**只依据这段文字**抽取,没写的填 null,不要用你自己的知识补充。输出 JSON:
- class_system: 班型与分班一句话(实验班/直升班/贯通班/钱学森班/1+3项目/平行分班;分班考科目;能否流动),无则 null
- schedule: 作息与学业一句话(晚自习到几点/周末是否补课/考试频率/作业量),无则 null
- management: 管理风格一句话(松/严、手机政策),无则 null
- boarding_detail: 住宿条件一句话(几人间/独卫/能否申请/走读),无则 null
- dining: 餐饮一句话,无则 null
- activities: 社团与特色活动一句话,无则 null
- voices: 往届学生/家长原话要点(若有"学生说/有话说"),一两句,无则 null

原文:
---
{text}
---
只输出 JSON。"""


def qwen(text):
    body = json.dumps({"model": "qwen-max", "temperature": 0,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": PROMPT.format(text=text[:6500])}]}).encode()
    import urllib.request
    req = urllib.request.Request("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                                 data=body, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    raw = json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else {}


def main():
    assert KEY, "需 DASHSCOPE_API_KEY"
    schools = {}
    for fn in SRCS:
        p = RAW / fn
        if p.exists():
            for name, info in json.load(open(p, encoding="utf-8")).items():
                schools[name] = "\n".join(x["text"] for x in info["pages"])
    print(f"待抽 {len(schools)} 校")

    def work(item):
        name, text = item
        try:
            ext = qwen(text)
            keep = {k: ext.get(k) for k in ("class_system", "schedule", "management",
                                            "boarding_detail", "dining", "activities", "voices")
                    if ext.get(k) not in (None, "", "null")}
            return name, (keep or None)
        except Exception as e:
            return name, {"_err": repr(e)[:120]}

    out = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for name, data in ex.map(work, schools.items()):
            if data:
                data["source"] = "2026朝阳高中指南白皮书(T3·机构汇编)"
                out[name] = data
            n = len(data) - 1 if data else 0
            print(f"  {'✓' if data and '_err' not in data else '✗'} {name[:20]:<20} {n}项")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n写 campus_life.json: {len(out)} 校")


if __name__ == "__main__":
    main()
