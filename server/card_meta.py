"""答题卡元信息提取（qwen-vl-max 视觉理解）。

不同于 detect.ocr_one_image（为涂卡「缺字母法」调的纯 OCR），这里用
qwen-vl-max 看整组照片，直接「读懂」答题卡，提取：
  考试名称 / 区 / 科目 / 年份 / 模别 / 学生姓名 / 准考证号
并判断这组照片是否构成一份完整答题卡（缺页/模糊/重拍）。

北京答题卡首页（考生须知页）顶部即印有：
  北京市朝阳区九年级综合练习（一）  物理答题卡  2026.4
  学校___ 姓名___ 准考证号___
所以信息一定在「考生须知页」上，关键是让模型把表头读出来。
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

import openai

ROOT = Path(__file__).resolve().parents[1]


def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


_PROMPT = """这是一名学生的中考模拟考试**答题卡**照片（可能多张，按顺序为答题卡的各页）。

请仔细查看（信息通常印在「考生须知」那一页的最顶部，标题行形如
「北京市朝阳区九年级综合练习（一）  物理答题卡  2026.4」），提取并判断：

严格输出 JSON（不要多余文字）：
{
  "exam_title": "完整考试名称原文（找不到填空串）",
  "district": "区名，如 朝阳 海淀 西城 …（只填两字区名，找不到空串）",
  "subject": "科目：语文/数学/英语/物理/道德与法治/化学/历史 之一（空串=未找到）",
  "year": "4位年份，如 2026（空串=未找到）",
  "exam_type": "一模/二模/三模/中考 之一。北京术语：综合练习（一）=一模，（二）=二模（空串=未找到）",
  "student_name": "学生姓名（手写或印刷，空串=未找到）",
  "student_id": "准考证号（空串=未找到）",
  "pages_complete": true/false,
  "completeness_note": "卷面完整性简评：是否含表头页、选择题填涂区、各主观题作答区；有无明显缺页/模糊/反光/拍歪导致无法识别。一句话。"
}"""


def _data_url(p: Path) -> str:
    b = base64.b64encode(p.read_bytes()).decode()
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b}"


def extract_card_meta(image_paths: list[Path], max_imgs: int = 6) -> dict:
    """qwen-vl-max 看全部（≤max_imgs）照片，提取考试元信息 + 完整性。"""
    client = _client()
    content = []
    for p in image_paths[:max_imgs]:
        content.append({"type": "image_url",
                         "image_url": {"url": _data_url(p)}})
    content.append({"type": "text", "text": _PROMPT})

    resp = client.chat.completions.create(
        model="qwen-vl-max",
        messages=[{"role": "user", "content": content}],
        temperature=0.0,
        max_tokens=1024,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise RuntimeError(f"元信息提取返回非 JSON：{raw[:200]}")
        data = json.loads(m.group(0))
    # 规整
    for k in ("exam_title", "district", "subject", "year", "exam_type",
              "student_name", "student_id", "completeness_note"):
        data.setdefault(k, "")
        data[k] = str(data[k]).strip()
    data.setdefault("pages_complete", False)
    return data


if __name__ == "__main__":
    import sys
    imgs = [Path(a) for a in sys.argv[1:]]
    print(json.dumps(extract_card_meta(imgs), ensure_ascii=False, indent=2))
