#!/usr/bin/env python3
"""
pdf-to-questionbank.py — 教辅扫描版 PDF → 结构化题库 YAML

流程：
  1. PDF 每页渲染为 PNG（2x 分辨率，缓存到 <out>/.cache/pages/）
  2. 每页送 Qwen-VL-Max 提取 YAML（结果缓存到 <out>/.cache/extracted/）
  3. 按章节分组，输出到 <out>/<章节>.yaml
  4. has_figure 的题目保留 figure_page_ref，供后续裁图

用法示例：
  python3 scripts/pdf-to-questionbank.py \\
    --pdf "knowledge-original/教辅材料/2026《万唯中考•试题研究》北京版/2026《万唯中考•试题研究》数学/2026《万唯中考•试题研究》数学分层作业本.pdf" \\
    --out knowledge-base/question-banks/math/wanwei-zuoye-2026-bj \\
    --book-id wanwei-zuoye-2026-bj \\
    --start-page 5

选项：
  --start-page N    从第 N 页开始（1-based，跳过封面/目录，默认 1）
  --end-page N      处理到第 N 页（默认处理到末页）
  --dry-run         只渲染图片，不调 API（用于检查分页效果）
  --force           忽略缓存，强制重新提取所有页
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import fitz  # pymupdf
import openai
import yaml

# ── 配置 ──────────────────────────────────────────────────────────────────────

DASHSCOPE_API_KEY = os.environ.get(
    "DASHSCOPE_API_KEY", "sk-269db71be27b4dcfbedb0c21c382d288"
)
QWEN_MODEL = "qwen-vl-max"
RENDER_SCALE = 2        # PDF 渲染放大倍数（2x ≈ 150dpi→300dpi）
API_INTERVAL = 0.8      # 两次 API 调用间隔（秒），避免限流
MAX_RETRIES = 3

EXTRACT_PROMPT = """\
这是一页中学数学教辅材料（万唯中考·分层作业本，北京版）的扫描图片。

请提取页面中所有题目，输出 YAML（不要用 markdown 代码块包裹）：

chapter: "单元名，如：第一单元 数与式"
section: "课时名，如：第1课时 实数（含二次根式）"
difficulty_zone: "基础巩固"   # 或 "能力提升"，若页面跨区则写主区
questions:
  - id: 1                     # 题目在本书中的编号（整数）
    type: 选择                 # 选择 / 填空 / 解答
    difficulty: 基础           # 基础 / 能力
    source: "2025海淀一模"     # 有来源标注则填，否则留空字符串 ""
    stem: "题干，公式用 $...$ 包裹"
    options:                   # 仅选择题有此字段；其他题型省略
      A: "..."
      B: "..."
      C: "..."
      D: "..."
    answer: ""                 # 本页无答案则留空
    has_figure: false          # 题干或选项中含坐标系/几何图/函数图像则为 true
    note: ""                   # 识别把握不大时填注说明，否则留空

规则：
- 所有字符串值必须用单引号 ' 包裹，不要用双引号（避免反斜杠被误解析）
- 数学公式用 $ 包裹，如 $\sqrt{2}$、$x^2+1$、$\dfrac{a}{b}$
- 图形（坐标系、几何图、函数图像）一律用 '[图]' 占位，并设 has_figure: true
- 解答题多个小问写入 stem，用换行分隔：'(1) ...\n(2) ...'
- 若本页是上一页题目的延续（题号不从1开始），正常提取，保持原题号
- 若本页是封面 / 目录 / 纯说明文字，输出一行：is_content_page: false
- 只输出 YAML，不要任何说明文字
"""


# ── 核心函数 ──────────────────────────────────────────────────────────────────

def get_client() -> openai.OpenAI:
    return openai.OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def render_page(pdf_doc, page_idx: int, out_path: Path) -> Path:
    """渲染 PDF 单页为 PNG，已存在则跳过。"""
    if out_path.exists():
        return out_path
    page = pdf_doc[page_idx]
    pix = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE))
    pix.save(str(out_path))
    return out_path


def call_qwen(client: openai.OpenAI, image_path: Path) -> str:
    """调用 Qwen-VL，返回原始文本。失败时重试，三次仍失败则抛出。"""
    with open(image_path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode()

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=QWEN_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {"type": "text", "text": EXTRACT_PROMPT},
                    ],
                }],
                max_tokens=4096,
            )
            return resp.choices[0].message.content
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** attempt
            print(f" [重试{attempt+1}/{MAX_RETRIES} 等{wait}s]", end="", flush=True)
            time.sleep(wait)


def extract_page(
    client: openai.OpenAI,
    image_path: Path,
    cache_path: Path,
    force: bool = False,
) -> dict:
    """提取单页，结果缓存到 JSON。"""
    if not force and cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    raw = call_qwen(client, image_path)
    result = {"raw": raw, "page": image_path.name}

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def fix_latex_backslashes(text: str) -> str:
    """
    Qwen 输出的 YAML 双引号字符串中，LaTeX 反斜杠（\dfrac \sqrt 等）会被
    YAML 解析器当作转义序列报错。遍历字符，将双引号字符串内的 \ 全部加倍。
    """
    result = []
    in_dq = False
    for c in text:
        if not in_dq:
            if c == '"':
                in_dq = True
            result.append(c)
        else:
            if c == '\\':
                result.append('\\\\')   # 加倍
            elif c == '"':
                in_dq = False
                result.append(c)
            else:
                result.append(c)
    return ''.join(result)


def parse_yaml_safe(raw: str):
    """从模型输出解析 YAML，容错处理 markdown 代码块和 LaTeX 反斜杠。"""
    text = re.sub(r"^```ya?ml\s*", "", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```\s*$", "", text.strip())
    # 第一次尝试
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        pass
    # 第二次：修复双引号字符串内的 LaTeX 反斜杠后重试
    try:
        return yaml.safe_load(fix_latex_backslashes(text))
    except yaml.YAMLError as e:
        return {"parse_error": str(e), "raw_snippet": raw[:300]}


def make_chapter_slug(chapter: str, section: str) -> str:
    """章节名 → 合法文件名（去除特殊字符）。"""
    raw = f"{chapter}——{section}"
    slug = re.sub(r"[^\w\u4e00-\u9fff\-]", "-", raw)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:60]


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="教辅扫描 PDF → 题库 YAML")
    parser.add_argument("--pdf", required=True, help="源 PDF 路径")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--book-id", required=True, help="教辅唯一 ID")
    parser.add_argument("--start-page", type=int, default=1, metavar="N")
    parser.add_argument("--end-page",   type=int, default=None, metavar="N")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--force",      action="store_true")
    args = parser.parse_args()

    pdf_path  = Path(args.pdf)
    out_dir   = Path(args.out)
    cache_dir = out_dir / ".cache"
    pages_dir = cache_dir / "pages"
    ext_dir   = cache_dir / "extracted"

    for d in (out_dir, pages_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    doc       = fitz.open(str(pdf_path))
    total     = len(doc)
    start_idx = args.start_page - 1          # 转 0-based
    end_idx   = min(args.end_page or total, total)

    print(f"书籍：{pdf_path.name}")
    print(f"总页：{total}　处理范围：{args.start_page}–{end_idx}")
    print(f"输出：{out_dir}\n")

    client = None if args.dry_run else get_client()

    # ── 封面：直接保存第1页 ────────────────────────────────────────────────────
    cover_png = pages_dir / "page-001.png"
    render_page(doc, 0, cover_png)
    import shutil
    shutil.copy2(cover_png, out_dir / "cover.png")
    print(f"封面已保存 → cover.png\n")

    # ── 逐页处理 ──────────────────────────────────────────────────────────────
    all_pages: list[dict] = []

    for page_idx in range(start_idx, end_idx):
        page_num = page_idx + 1
        prefix = f"  [{page_num:3d}/{end_idx}]"

        # 1. 渲染
        png_path = pages_dir / f"page-{page_num:03d}.png"
        cached_png = png_path.exists()
        render_page(doc, page_idx, png_path)
        print(f"{prefix} PNG{'(缓存)' if cached_png else ' 新建'}  ", end="", flush=True)

        if args.dry_run:
            print()
            continue

        # 2. 提取
        cache_path = ext_dir / f"page-{page_num:03d}.json"
        cached_ext = cache_path.exists() and not args.force
        try:
            result = extract_page(client, png_path, cache_path, force=args.force)
        except Exception as e:
            print(f"✗ API 失败: {e}")
            continue

        raw = result.get("raw", "")
        if not raw:
            print("✗ 空响应")
            continue

        # 3. 解析
        parsed = parse_yaml_safe(raw)
        if parsed is None:
            print("✗ YAML 解析失败（None）")
            continue
        if "parse_error" in parsed:
            print(f"✗ YAML 解析错误: {parsed['parse_error'][:60]}")
            continue
        if parsed.get("is_content_page") is False:
            print("── 非题目页，跳过")
            continue

        questions = parsed.get("questions") or []
        # 注入页面元信息
        for q in questions:
            q["_page_num"] = page_num
            if q.get("has_figure"):
                q["figure_page_ref"] = f".cache/pages/page-{page_num:03d}.png"

        all_pages.append({
            "page_num":       page_num,
            "chapter":        parsed.get("chapter", ""),
            "section":        parsed.get("section", ""),
            "difficulty_zone":parsed.get("difficulty_zone", ""),
            "questions":      questions,
            "cached":         cached_ext,
        })

        status = "(缓存)" if cached_ext else "新提取"
        section_short = (parsed.get("section") or "")[:24]
        print(f"✓ {len(questions):2d} 题 {status}  {section_short}")

        if not cached_ext:
            time.sleep(API_INTERVAL)

    if args.dry_run:
        print("\nDry-run 完成，已生成所有 PNG。")
        return

    # ── 按章节分组 ────────────────────────────────────────────────────────────
    print(f"\n整理输出…")
    grouped: dict[tuple, list] = defaultdict(list)
    for pd in all_pages:
        key = (pd["chapter"], pd["section"])
        grouped[key].extend(pd["questions"])

    # 写 meta.yaml
    meta = {
        "book_id":    args.book_id,
        "pdf_source": str(pdf_path),
        "model":      QWEN_MODEL,
        "page_range": [args.start_page, end_idx],
        "sections":   len(grouped),
        "total_questions": sum(len(qs) for qs in grouped.values()),
    }
    with open(out_dir / "meta.yaml", "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, sort_keys=False)

    # 写各章节文件
    written = 0
    for (chapter, section), questions in grouped.items():
        # 清除内部字段
        clean_qs = [
            {k: v for k, v in q.items() if not k.startswith("_")}
            for q in questions
        ]
        slug      = make_chapter_slug(chapter, section)
        out_file  = out_dir / f"{slug}.yaml"
        doc_data  = {
            "meta": {
                "book_id":  args.book_id,
                "chapter":  chapter,
                "section":  section,
            },
            "questions": clean_qs,
        }
        with open(out_file, "w", encoding="utf-8") as f:
            yaml.dump(doc_data, f, allow_unicode=True,
                      sort_keys=False, default_flow_style=False)
        written += 1
        print(f"  → {out_file.name}  ({len(clean_qs)} 题)")

    total_q = sum(len(qs) for qs in grouped.values())
    print(f"\n✅ 完成  {written} 个章节文件  共 {total_q} 道题")
    print(f"   输出目录: {out_dir}")


if __name__ == "__main__":
    main()
