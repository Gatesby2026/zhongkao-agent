#!/usr/bin/env python3
"""解析白皮书民办档案 OCR → 升学出口(留学走向/高考/暂无)+课程+招生人数,合并进 chaoyang_private.yaml。
LLM 仅从已给 OCR 文本抽取(不靠记忆=安全)。国际校单列 study_abroad 留学走向字段。
"""
import json
import os
import re
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
KB = ROOT / "knowledge-base/admission/beijing"
OCR = KB / "raw_extracts/whitepaper_minban_ocr.json"
PRIV = KB / "chaoyang_private.yaml"
KEY = os.environ.get("DASHSCOPE_API_KEY", "")

PROMPT = """下面是某北京民办/国际高中在《2026朝阳高中指南白皮书》里的档案原文。**只依据这段文字**抽取,
没写的填 null,不要用你自己的知识补充。输出 JSON:
- exit_type: 升学出口类型,取值之一: "留学"(主要出国/海外大学offer) / "高考"(参加国内高考) / "混合" / "暂无毕业生"(首届未毕业) / "未公布"
- study_abroad: 若有海外升学走向,用一句话概括(国家方向 + 名校/G5/前30/前50比例 + 代表offer数),否则 null
- exit_domestic: 若有国内高考成绩,一句话概括(本科率/特控率/最高分等),否则 null
- curriculum: 课程体系数组(从文中提到的: 国内普高/A-Level/IB/AP/美高/加拿大OSSD 等),无则 []
- enroll_2025: 2025年统一招生批次招生人数(整数),无则 null
- class_info: 班型/年级规模一句话(如"高一6-8个班,含航空实验班"),无则 null
- line_note: 录取线/门槛说明(民办多为"建议电话咨询"),照抄要点

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
    return (s or "").replace("北京市", "").replace("朝阳区", "").replace("北京", "").strip()


def main():
    assert KEY, "需 DASHSCOPE_API_KEY"
    ocr = json.load(open(OCR, encoding="utf-8"))
    doc = yaml.safe_load(open(PRIV, encoding="utf-8"))
    schools = doc.get("schools", [])
    # 名/别名 → record
    idx = {}
    for s in schools:
        idx[norm(s["name"])] = s
        for a in (s.get("aliases") or []):
            idx.setdefault(norm(a), s)

    enriched, added, report = 0, 0, []
    for wp_name, info in ocr.items():
        full = "\n".join(p["text"] for p in info["pages"])
        ext = qwen(full)
        rec = idx.get(norm(wp_name))
        payload = {
            "exit_type": ext.get("exit_type"),
            "study_abroad": ext.get("study_abroad"),
            "exit_domestic": ext.get("exit_domestic"),
            "enroll_2025": ext.get("enroll_2025"),
            "class_info": ext.get("class_info"),
            "wp_curriculum": ext.get("curriculum") or [],
            "wp_line_note": ext.get("line_note"),
            "wp_source": "2026朝阳高中指南白皮书·机构汇编(T3,待核)",
        }
        if rec:
            rec.update({k: v for k, v in payload.items() if v not in (None, [], "")})
            enriched += 1
        else:
            # 白皮书有、yaml 无 → 新增最小记录(待补编码/坐标)
            schools.append({
                "name": wp_name, "code": None, "nature": "民办",
                "in_minban_list": payload["exit_type"] != "留学",
                "in_intl_list": payload["exit_type"] == "留学",
                "location": {"address": None, "confidence": "low"},
                "note": "白皮书补充·待补 bjeea 编码/坐标",
                **{k: v for k, v in payload.items() if v not in (None, [], "")},
            })
            added += 1
        report.append(f"{'＋新增' if not rec else '已合并'} {wp_name[:18]:<18} 出口={payload['exit_type']} 留学={'有' if payload['study_abroad'] else '—'} 招{payload['enroll_2025'] or '?'}")

    doc["schools"] = schools
    yaml.safe_dump(doc, open(PRIV, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    print(f"合并 {enriched} 校 / 新增 {added} 校 → chaoyang_private.yaml\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
