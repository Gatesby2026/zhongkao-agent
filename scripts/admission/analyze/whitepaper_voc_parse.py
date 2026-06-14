#!/usr/bin/env python3
"""解析白皮书 3 所职高(综合高中班)OCR → 录取线/升学路径/综高班,合并进 chaoyang_vocational.yaml。
LLM 仅从已给文本抽取。中职这里指"综合高中班"(职普融通,办普高学籍,可参加高考/单招升本)。
"""
import json
import os
import re
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
KB = ROOT / "knowledge-base/admission/beijing"
OCR = KB / "raw_extracts/whitepaper_voc_ocr.json"
VOC = KB / "chaoyang_vocational.yaml"
KEY = os.environ.get("DASHSCOPE_API_KEY", "")

PROMPT = """下面是某北京职业高中在《2026朝阳高中指南白皮书》里的档案原文。**只依据这段文字**抽取,没写填 null。输出 JSON:
- comp_high_2025: 综合高中班2025统招招生人数(整数),无则 null
- line_note: 录取线要点(如"综合高中班2023录取线548/区排名9485;24-25未公布"),照实写,无则 null
- exit_paths: 升学路径与出口一句话(本科上线率/单招升本/可参加高考/转职高学籍等),无则 null
- comp_high_note: 综合高中班性质一句话(职普融通/普高学籍/可参加高考),无则 null
- campuses: 校区数组(如["常营","劲松","双龙","新源里"]),无则 []
原文:
---
{text}
---
只输出 JSON。"""


def qwen(text):
    body = json.dumps({"model": "qwen-max", "temperature": 0,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": PROMPT.format(text=text[:6000])}]}).encode()
    req = urllib.request.Request("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                                 data=body, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    raw = json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else {}


def norm(s):
    return (s or "").replace("北京市", "").replace("朝阳区", "").strip()


def main():
    assert KEY, "需 DASHSCOPE_API_KEY"
    ocr = json.load(open(OCR, encoding="utf-8"))
    doc = yaml.safe_load(open(VOC, encoding="utf-8"))
    schools = doc.get("schools", [])
    idx = {norm(s["name"]): s for s in schools}
    report = []
    for wp_name, info in ocr.items():
        full = "\n".join(p["text"] for p in info["pages"])
        ext = qwen(full)
        payload = {k: ext.get(k) for k in ("comp_high_2025", "line_note", "exit_paths", "comp_high_note", "campuses")}
        rec = idx.get(norm(wp_name))
        if rec:
            rec.update({k: v for k, v in payload.items() if v not in (None, [], "")})
            rec["wp_source"] = "2026朝阳高中指南白皮书(T3,待核)"
            report.append(f"已合并 {wp_name[:16]:<16} 综高招{payload['comp_high_2025'] or '?'} 线={'有' if payload['line_note'] else '—'} 出口={'有' if payload['exit_paths'] else '—'}")
        else:
            report.append(f"⚠️未匹配 {wp_name}(vocational.yaml 无此校)")
    doc["schools"] = schools
    yaml.safe_dump(doc, open(VOC, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    print("\n".join(report))


if __name__ == "__main__":
    main()
