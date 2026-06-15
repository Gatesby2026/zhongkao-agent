#!/usr/bin/env python3
"""把每校归类到固定"特色"标签集 → features_std.json(按校名)。供"按特长选校"筛选。
输入:campus_life.json(班型/活动/课程) + 白皮书 OCR 原文。LLM 仅据已给文本归类(安全)。
固定标签集(闭集,便于筛选):科技创新/学科竞赛/外语特色/文科人文/艺术特长/体育特长/国际方向/课程改革/综合均衡
"""
import concurrent.futures as cf
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KB = ROOT / "knowledge-base/admission/beijing"
RAW = KB / "raw_extracts"
CL = KB / "campus_life.json"
OUT = KB / "features_std.json"
KEY = os.environ.get("DASHSCOPE_API_KEY", "")
SRCS = ["whitepaper_ocr_raw.json", "whitepaper_minban_ocr.json", "whitepaper_voc_ocr.json"]
TAGSET = ["科技创新", "学科竞赛", "外语特色", "文科人文", "艺术特长", "体育特长", "国际方向", "课程改革", "综合均衡"]

PROMPT = """下面是某北京高中的档案原文(含特色/班型/社团/课程)。**只据这段文字**,从固定标签集里选出该校最突出的 1-3 个特色标签,不要选文中无依据的。
固定标签集(只能从中选):{tags}
另给一句话"特色亮点"(具体项目/班型,如"钱学森班+科技创新"/"美术+排球传统"/"A-Level国际方向"),无依据则 null。
输出 JSON: {{"tags": ["..."], "highlight": "..."}}

原文:
---
{text}
---
只输出 JSON。"""


def qwen(text):
    body = json.dumps({"model": "qwen-max", "temperature": 0,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": PROMPT.format(tags="、".join(TAGSET), text=text[:6000])}]}).encode()
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
    texts = {}
    for fn in SRCS:
        p = RAW / fn
        if p.exists():
            for name, info in json.load(open(p, encoding="utf-8")).items():
                texts[name] = "\n".join(x["text"] for x in info["pages"])
    print(f"待分类 {len(texts)} 校")

    def work(item):
        name, text = item
        try:
            ext = qwen(text)
            tags = [t for t in (ext.get("tags") or []) if t in TAGSET][:3]
            return name, {"tags": tags, "highlight": ext.get("highlight")}
        except Exception as e:
            return name, {"_err": repr(e)[:100]}

    out = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for name, data in ex.map(work, texts.items()):
            if data and "_err" not in data and (data.get("tags") or data.get("highlight")):
                data["source"] = "白皮书归类(T3)"
                out[name] = data
            print(f"  {name[:18]:<18} {data.get('tags') if data else '✗'}")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n写 features_std.json: {len(out)} 校")
    from collections import Counter
    c = Counter(t for v in out.values() for t in v.get("tags", []))
    print("标签分布:", dict(c))


if __name__ == "__main__":
    main()
