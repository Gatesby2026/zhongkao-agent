#!/usr/bin/env python3
"""
招生计划册（bjeea 图片版）→ 结构化 JSON
=========================================
bjeea《普通高中学校统一招生计划》等计划册在官网以**整页表格 JPG** 发布
（如 https://www.bjeea.cn/html/zkzh/jhcx/2025/0701/87190.html 共 53 张），
文本不可直接抽取。本脚本用 qwen-vl-max 逐页做表格结构化 OCR，逐行抽出：

  学校代码 / 学校名称 / 专业代码 / 专业名称 / 学制 / 是否加试
  / 计划合计 / 分区招生人数(东城01…经开17) / 特殊学生 / 特殊说明

**铁律（涉及孩子升学，见 ADDRESS-VERIFICATION.md §0）**：代码/计划数只能来自官方计划册，
不得臆造。OCR 结果须经人工/交叉核对方可进系统；本脚本只负责把图片转成可核对的结构化文本。

用法：
  DASHSCOPE_API_KEY=... python scripts/admission/extract_plan_ocr.py \
      --images /tmp/bjeea_2025_tongzhao/p*.jpg \
      --out knowledge-base/admission/beijing/2025_tongzhao_plan.json \
      --year 2025 --plan tongzhao

每页原始 OCR 落 .cache/plan_ocr_cache.json，按 (文件名+mtime) 键，可断点续跑。
"""
import argparse
import base64
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE = CACHE_DIR / "plan_ocr_cache.json"
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)

# 表头分区列顺序（与 bjeea 普高统招计划表一致）
DISTRICTS = ["东城", "西城", "朝阳", "丰台", "石景山", "海淀", "门头沟",
             "房山", "通州", "顺义", "昌平", "大兴", "怀柔", "平谷",
             "密云", "延庆", "经开"]

PROMPT = """你是北京中考《招生计划册》表格 OCR 与结构化引擎。图片是一整页招生计划表格。

表格列依次为：学校代码 | 学校名称（地址及电话）| 专业代码 | 专业名称 | 学制(年) | 是否加试 | 计划合计 | 东城 | 西城 | 朝阳 | 丰台 | 石景山 | 海淀 | 门头沟 | 房山 | 通州 | 顺义 | 昌平 | 大兴 | 怀柔 | 平谷 | 密云 | 延庆 | 经开 | 特殊学生 | 特殊说明

每个学校占多行：第一行有学校代码/名称，后续行是该校不同专业(班)。请把**每一个专业行**输出为一条记录，并把所属学校代码/名称补全到该行。

严格要求：
1. 只抄录印刷数字与文字，看不清的字段填 null，并在该行 notes 里说明，绝不臆造代码或人数。
2. 学校代码是 6 位数字（如 101001、103xxx）。专业代码是 2 位（01/02/03/04）。
3. 分区人数：表格里空白格表示该区不招（填 0 或 null 均可，保持空白用 null）。只填表里确有数字的格。
4. 学校名称只取校名，地址电话不要混进 school_name（可放进 address 字段）。
5. 输出纯 JSON，不要 Markdown 代码块，不要解释。

JSON 结构：
{
  "rows": [
    {
      "school_code": "101001",
      "school_name": "北京市第二中学",
      "address": "东城区内务部街…（可空）",
      "major_code": "01",
      "major_name": "普通班",
      "xuezhi": "三",
      "jiashi": "否",
      "total": 406,
      "districts": {"东城": 223, "西城": 2, "朝阳": 3, "通州": 144},
      "special_student": null,
      "special_note": "该专业…说明原文",
      "confidence": 0.0,
      "notes": "可空"
    }
  ]
}
districts 只放有数字的区，没招的区不要列。"""


def load_cache():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def save_cache(c):
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def img_data_uri(path: Path) -> str:
    b = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/jpeg;base64,{b}"


def parse_json(text: str):
    body = FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        s, e = body.find("{"), body.rfind("}")
        if s >= 0 and e > s:
            return json.loads(body[s:e + 1])
        raise


def ocr_page(path: Path, model: str, max_tokens: int):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": img_data_uri(path)}},
            {"type": "text", "text": PROMPT},
        ]}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = json.loads(r.read().decode())
            return parse_json(raw["choices"][0]["message"]["content"])
        except HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}")
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            raise
    return {"rows": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--year", default="2025")
    ap.add_argument("--plan", default="tongzhao")
    ap.add_argument("--model", default="qwen-vl-max-latest")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit("缺 DASHSCOPE_API_KEY 环境变量")

    cache = load_cache()
    imgs = sorted(Path(p) for p in args.images)
    all_rows, fill_school = [], None
    for i, p in enumerate(imgs, 1):
        key = f"{args.plan}|{p.name}|{int(p.stat().st_mtime)}"
        if args.force or key not in cache:
            print(f"[{i}/{len(imgs)}] OCR {p.name} ...", flush=True)
            cache[key] = ocr_page(p, args.model, args.max_tokens)
            save_cache(cache)
        else:
            print(f"[{i}/{len(imgs)}] cached {p.name}", flush=True)
        rows = cache[key].get("rows", [])
        for r in rows:
            # 把跨行续表的学校代码/名称向下补全
            if r.get("school_code"):
                fill_school = (r["school_code"], r.get("school_name"))
            elif fill_school:
                r["school_code"], r["school_name"] = fill_school
            r["_page"] = p.name
        all_rows.extend(rows)

    out = {
        "year": args.year, "plan": args.plan,
        "source": "bjeea.cn 招生计划册 图片版 → qwen-vl-max OCR",
        "warning": "OCR 自动抽取，未逐行人工核对；代码/人数以官方计划册为准。"
                   f"{args.year} 数据，2026 计划发布后须刷新。",
        "districts_order": DISTRICTS,
        "n_rows": len(all_rows),
        "rows": all_rows,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {args.out}：{len(all_rows)} 行 / {len(imgs)} 页")


if __name__ == "__main__":
    main()
