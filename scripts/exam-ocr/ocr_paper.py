#!/usr/bin/env python3
"""单卷 OCR：images/*.png → structured-cloud/final.json

两步走（替代 ECS 上的 3 引擎融合流水线）：
  1. 逐页 Qwen-VL-OCR：试卷扫描页 → 原始 OCR 文本（保留题号 + 选项 + 答案页）
  2. 整卷 qwen-max：所有页文本 → 结构化 questions[] + answer_pages[]

输出 schema 跟 Codex `structured-cloud/final.json` 兼容：

    {
      "subject": "physics", "exam": "<exam name>",
      "page_count": 10,
      "questions": [
        {"id": "physics-q01", "number": 1, "type": "choice",
         "text": "1. ...", "options": [...], "source_page": 1},
        ...
      ],
      "answer_pages": [9, 10]
    }

CLI:
    python3 ocr_paper.py <paper-dir> --subject physics

    Reads:  <paper-dir>/images/page-*.png
    Writes: <paper-dir>/pages/page-NN.ocr.txt        (逐页 OCR 缓存)
            <paper-dir>/structured-cloud/final.json  (主成品)
            <paper-dir>/structured-cloud/final.md    (人看版)

需 DASHSCOPE_API_KEY。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import openai
except ImportError:
    print("pip install openai", file=sys.stderr); sys.exit(1)


SUBJECT_LABEL_CN = {
    "physics": "物理", "math": "数学", "chinese": "语文",
    "english": "英语", "politics": "道德与法治",
    "chemistry": "化学", "history": "历史", "biology": "生物", "geography": "地理",
}


# ============== client ==============

def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY 环境变量")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def _img_to_data_url(p: Path) -> str:
    b = base64.b64encode(p.read_bytes()).decode("ascii")
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b}"


# ============== step 1: per-page Qwen-VL-OCR ==============

OCR_SYS_PROMPT = (
    "你是 OCR 引擎，不是排版器。严格按图片所见逐字识别这页试卷。要求：\n"
    "1. 必须以原始阿拉伯数字保留题号（如 16. 17. 18. 19. 20. ...），逐题独占一行。\n"
    "2. 严禁把题目转成 LaTeX \\begin{enumerate} / \\item 这种环境，必须保留视觉编号。\n"
    "3. 选项标签（A. B. C. D.）每个独占一行。\n"
    "4. 公式用行内 LaTeX（如 $x^2$）；表格用 Markdown 表格。\n"
    "5. 图片/电路图/光路图/几何图等用 [图] 占位，不要描述图形内容。\n"
    "6. 不要改写题面、不要补答案、不要重新编号。\n"
    "7. 「答案及评分参考」/「参考答案」页：照样如实转录。\n"
    "8. 直接输出纯文本，不要 ```latex / ```markdown / ```json 代码围栏。"
)


def _is_garbage_ocr(text: str) -> bool:
    """检测 Qwen-VL-OCR 失败模式：
    1) 退化为目标检测（吐 pos_list / rotate_rect JSON）
    2) 把题号转换成 LaTeX enumerate 环境（吃掉视觉编号）
    """
    if not text or len(text.strip()) < 30:
        return True
    sample = text[:500]
    bad_markers = ("pos_list", "rotate_rect", '"polygons"', '"detection_result"',
                   r"\begin{enumerate}", r"\begin{itemize}")
    return any(m in sample for m in bad_markers)


def ocr_page(client, image_path: Path, retries: int = 3) -> str:
    """单页 OCR；若 qwen-vl-ocr-latest 退化（吐坐标 JSON），fallback 到 qwen-vl-max。"""
    data_url = _img_to_data_url(image_path)
    last_err = None
    # 先用 qwen-vl-ocr-latest（专 OCR 模型，质量高但偶尔退化）
    for i in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-vl-ocr-latest",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": OCR_SYS_PROMPT},
                    ],
                }],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            if not _is_garbage_ocr(text):
                return text
            print(f"    ⚠️ qwen-vl-ocr 退化（坐标 JSON），fallback qwen-vl-max", file=sys.stderr)
            break
        except Exception as e:
            last_err = e
            print(f"    ⚠️ retry {i+1}/{retries}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))

    # fallback：qwen-vl-max（通用多模态，不会输出 detection 模式）
    for i in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-vl-max",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": OCR_SYS_PROMPT},
                    ],
                }],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            if not _is_garbage_ocr(text):
                return text
            print(f"    ⚠️ qwen-vl-max 也退化，{i+1}/{retries}", file=sys.stderr)
        except Exception as e:
            last_err = e
            print(f"    ⚠️ vl-max retry {i+1}/{retries}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))

    raise RuntimeError(f"OCR failed (both vl-ocr 和 vl-max 退化): {image_path}: {last_err}")


# ============== step 2: structure via qwen-max ==============

STRUCT_PROMPT_TEMPLATE = """以下是一份{subject_cn}试卷的逐页 OCR 文本（每页用 ## page-NN 标头分隔）。
请整理为结构化 JSON：

{{
  "subject": "{subject_en}",
  "exam": "<试卷标题，如「2026 北京XX区初三一模 物理」>",
  "page_count": <总页数>,
  "questions": [
    {{
      "id": "{subject_en}-q01",
      "number": 1,
      "type": "choice",
      "text": "1. 完整题干\\n\\nA. 选项A\\nB. 选项B\\nC. 选项C\\nD. 选项D",
      "source_page": 1
    }},
    ...
  ],
  "answer_pages": [<答案/评分参考所在页号列表，如 [9,10]，没有则 []>]
}}

要求：
1. 每道题保留原始题号（题号一定要单调递增，覆盖 1..N 不要漏题）。
2. text 字段：含题号前缀；选项放进 text，每个选项独占一行，用 \\n 分隔。**不要单独输出 options 字段。**
3. type 严格在以下枚举之一：choice / multi_choice / fill_blank / essay / experiment / calculation。
4. 答案页内容**不要混入 questions**，仅把页号填到 answer_pages。
5. 直接输出 JSON，不要加代码块或解释。"""


def structure_pages(client, pages_text: list[str], subject_en: str,
                     retries: int = 3) -> dict:
    """整卷文本 → 结构化 JSON。带重试 + 完整性检验。"""
    subject_cn = SUBJECT_LABEL_CN.get(subject_en, subject_en)
    full_text = "\n\n".join(f"## page-{i+1:02d}\n{t}" for i, t in enumerate(pages_text))
    prompt = STRUCT_PROMPT_TEMPLATE.format(subject_cn=subject_cn, subject_en=subject_en)

    last_err = None
    last_result = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": full_text},
                ],
                temperature=0.0,
                max_tokens=8192,
                response_format={"type": "json_object"},
                timeout=180,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
            result = json.loads(raw)
            qs = result.get("questions", [])
            # 试卷一般 ≥10 题；少于此视为截断
            if len(qs) < 10:
                print(f"    ⚠️ struct attempt {attempt+1}: 只 {len(qs)} 题，可能截断，重试", file=sys.stderr)
                last_result = result  # 保留以便最终 fallback
                time.sleep(3 * (attempt + 1))
                continue
            return result
        except Exception as e:
            last_err = e
            print(f"    ⚠️ struct attempt {attempt+1}/{retries}: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))

    # 全部尝试失败 → 用最后一次成功 parse 的（哪怕题少），或抛
    if last_result is not None:
        print(f"    ⚠️ 用最后一次结果（{len(last_result.get('questions', []))} 题）", file=sys.stderr)
        return last_result
    raise RuntimeError(f"structure failed after {retries} tries: {last_err}")


# ============== 题面文本归一化 ==============

_OPT_LABEL_RE = re.compile(r"(?<![A-Za-z])([A-E])\.\s*")


def _normalize_question_text(text: str) -> str:
    """把选项规范成独立行 + 去 LaTeX/反斜杠 artifacts。

    输入示例：'1. 题干 \\[A. xxx \\\\B. yyy C. zzz D. www]'
    输出示例：'1. 题干\\nA. xxx\\nB. yyy\\nC. zzz\\nD. www'
    """
    t = text
    # 1. 去 LaTeX `\[` `\]` 包裹
    t = re.sub(r"\\\[|\\\]|^\[|\]$", "", t, flags=re.M).replace("\\[", "").replace("\\]", "")
    # 2. 去 qwen-max 加的多余反斜杠（\\B. → B.；\B. → B.）
    t = re.sub(r"\\+([A-E]\.)", r"\1", t)
    # 3. 把 `A. xxx B. yyy ...` 拆成多行：空格 + 字母. → 换行 + 字母.
    t = re.sub(r"\s+(?=[A-E]\.\s)", "\n", t)
    # 4. 题号(N.)后接空格再跟选项，先空开
    t = re.sub(r"^(\d+\.\s*[^\n]+?)(\n[A-E]\.)", r"\1\n\2", t)
    # 5. 合并多余空白
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    # 6. 末尾孤儿 `]`
    t = re.sub(r"\s*\]\s*$", "", t)
    return t.strip()


# ============== 主入口 ==============

def ocr_one_paper(paper_dir: Path, subject_en: str, force: bool = False) -> Path:
    images_dir = paper_dir / "images"
    pages_cache = paper_dir / "pages"
    out_dir = paper_dir / "structured-cloud"
    out_json = out_dir / "final.json"

    if out_json.exists() and not force:
        print(f"  ⏭  缓存命中：{out_json}")
        return out_json

    images = sorted(images_dir.glob("page-*.png"))
    if not images:
        raise FileNotFoundError(f"无 page-*.png：{images_dir}")
    print(f"  📷 {len(images)} 张页面")

    client = _client()

    # Step 1: per-page OCR (cached by file)
    pages_cache.mkdir(parents=True, exist_ok=True)
    pages_text = []
    for i, img in enumerate(images, 1):
        cache = pages_cache / f"page-{i:02d}.ocr.txt"
        if cache.exists() and not force:
            text = cache.read_text(encoding="utf-8")
            print(f"  ⏭  page-{i:02d} 缓存命中")
        else:
            print(f"  🔍 page-{i:02d} OCR ...", flush=True)
            text = ocr_page(client, img)
            cache.write_text(text, encoding="utf-8")
        pages_text.append(text)

    # Step 2: structure
    print(f"  🧱 整卷结构化 (qwen-max) ...")
    result = structure_pages(client, pages_text, subject_en)

    # ensure required fields + scrub malformed entries
    result.setdefault("subject", subject_en)
    result.setdefault("page_count", len(images))
    result.setdefault("answer_pages", [])
    qs_in = result.get("questions", [])
    qs = []
    for q in qs_in:
        if not isinstance(q, dict):
            print(f"  ⚠️ skip non-dict question: {repr(q)[:80]}", file=sys.stderr)
            continue
        # 丢弃误生成的 options/选项键（模型有时把 'B. xxx' 当作 key）
        q = {k: v for k, v in q.items() if k in ("id", "number", "type", "text", "source_page")}
        if "number" not in q or "text" not in q:
            print(f"  ⚠️ skip incomplete question: {list(q.keys())}", file=sys.stderr)
            continue
        q.setdefault("id", f"{subject_en}-q{q['number']:02d}")
        q["text"] = _normalize_question_text(q["text"])
        qs.append(q)
    result["questions"] = qs

    out_dir.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # human-readable
    md_lines = [f"# {result.get('exam', '')}", "", f"科目: {subject_en} · {len(qs)} 题", ""]
    for q in qs:
        md_lines.append(f"## Q{q.get('number')} ({q.get('type','?')}) · page-{q.get('source_page','?')}")
        md_lines.append(q.get("text", ""))
        md_lines.append("")
    (out_dir / "final.md").write_text("\n".join(md_lines), encoding="utf-8")

    print(f"  ✅ {out_json.relative_to(paper_dir.parent.parent) if paper_dir.parent.parent in out_json.parents else out_json}")
    print(f"     {len(qs)} 题, answer_pages={result.get('answer_pages')}")
    return out_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("paper_dir", type=Path,
                   help="单卷目录，包含 images/page-*.png")
    p.add_argument("--subject", required=True,
                   choices=list(SUBJECT_LABEL_CN.keys()))
    p.add_argument("--force", action="store_true",
                   help="强制重 OCR（跳过缓存）")
    args = p.parse_args()
    ocr_one_paper(args.paper_dir, args.subject, force=args.force)


if __name__ == "__main__":
    main()
