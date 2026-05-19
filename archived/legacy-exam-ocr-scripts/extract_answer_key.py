#!/usr/bin/env python3
"""从试卷扫描页里自动提取「答案及评分标准」→ 标准 answer-key.json。

两阶段流水线：
1. 用 qwen-vl-ocr-latest 找答案页 + OCR 转录
2. 用 qwen-max (文本) 把 OCR 文本对齐到 paper.json 里的每道题

CLI:
    python extract-answer-key.py \
        --paper paper.json \
        --pages physics-images/page-*.png \
        --output answer-key.json

输入：paper.json + 试卷扫描页（含答案页）
输出：answer-key.json 匹配 schemas.py:AnswerKey

依赖：openai + DASHSCOPE_API_KEY
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import openai
except ImportError:
    print("pip install openai", file=sys.stderr); sys.exit(1)


# ============== 客户端 ==============

def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY 环境变量")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def heic_to_jpg(heic: Path, max_dim: int = 2400) -> Path:
    if heic.suffix.lower() != ".heic":
        return heic
    out = Path(tempfile.gettempdir()) / f"ans-{heic.stem}.jpg"
    subprocess.run(
        ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88",
         "-Z", str(max_dim), str(heic), "--out", str(out)],
        check=True, capture_output=True,
    )
    return out


# ============== 1. 答案页识别 + OCR ==============

OCR_PROMPT = """你是 OCR 转录器。把图中所有印刷文字逐行抄录，纯文本输出。

**重要**：
- 选择题答案表（"1 2 3 ... | A B C D ..."）必须完整抄录每个题号对应的字母
- 评分标准、给分要点、解题步骤要尽量完整保留
- 数学公式用 LaTeX 行内 $...$ 或独立 $$...$$
- 不要加任何评论、解释、JSON 包裹"""


ANSWER_PAGE_KEYWORDS = ["答案", "评分标准", "评分参考", "参考答案"]


def is_answer_page(text: str) -> bool:
    """是否含答案页关键字。"""
    return any(kw in text for kw in ANSWER_PAGE_KEYWORDS)


def ocr_page(image_path: Path) -> str:
    """OCR 单页，返回纯文本。"""
    client = _client()
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    resp = client.chat.completions.create(
        model="qwen-vl-ocr-latest",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": OCR_PROMPT},
        ]}],
        temperature=0.0,
        max_tokens=8192,
    )
    return resp.choices[0].message.content


# ============== 2. LLM 文本对齐 → 结构化 ==============

EXTRACT_SYSTEM = """你是中考试卷的答案结构化专家。
任务：把试卷答案页的 OCR 转录文本，按题号对齐到给定的题目列表，输出标准 JSON。
风格：忠实于原文，不发明答案，不解释，不评价。"""


EXTRACT_USER_TEMPLATE = """# 任务

下面是某份试卷的答案页 OCR 转录文本，以及该试卷的题目结构（题号 + 题型 + 满分）。请把每道题的标准答案从 OCR 文本里抽出来，输出 JSON。

# 题目结构（来自 paper.json）

{questions_brief}

# 答案页 OCR 转录

```
{answer_ocr}
```

# 输出 JSON（严格格式）

```json
{{
  "answers": [
    {{"id": "Q1", "correct": "C", "score": 2}},
    {{"id": "Q15", "correct": ["A","B","D"], "score": 2, "partialCreditRule": "全选对得2分，选对但不全得1分，有错选不得分"}},
    {{"id": "Q16", "correct": ["不变","晶体","引力"], "score": 3}},
    {{"id": "Q25", "correctSolution": "(1) U_R=U-U_D=220-2=218 V；R=21800Ω\\n(2) P=UI=2200W；P余=1400W", "keySteps": ["(1) 串联分压：U_R=218V, R=21800Ω", "(2) P余=1400W"], "score": 4}}
  ]
}}
```

字段规则：
- **选择题**（type=choice）：`correct` 为单个字母字符串
- **多选题**（type=multi_choice）：`correct` 为字母列表；附 `partialCreditRule` 描述部分给分规则（如有）
- **填空题**（type=fill_blank）：`correct` 为每空答案的列表
- **大题**（type=calculation/experiment/essay）：用 `correctSolution`（完整解答过程）+ `keySteps`（给分要点列表）
- 所有题都必须有 `score`

注意：
- 题号严格按 paper.json 给定（如 Q1, Q12, Q15）
- 找不到答案就跳过该题（不要瞎编）
- LaTeX 公式保留原样
- 不要 markdown 代码块包裹 JSON"""


def call_extract_llm(answer_ocr: str, paper: dict) -> dict:
    """让 LLM 把 OCR 文本对齐到 paper.json。"""
    questions_brief = "\n".join(
        f"- {q['id']}（{q.get('type','?')}, {q.get('score','?')}分）"
        for q in paper["questions"]
    )
    user = EXTRACT_USER_TEMPLATE.format(
        questions_brief=questions_brief,
        answer_ocr=answer_ocr,
    )
    client = _client()
    resp = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=8192,
        response_format={"type": "json_object"},
    )
    return _normalize_escapes(json.loads(resp.choices[0].message.content))


def _normalize_escapes(data):
    """LLM 在 correctSolution 里常输出 '\\\\' 想表示换行，但其实是双反斜杠。统一变成真换行。"""
    if isinstance(data, dict):
        for k, v in data.items():
            data[k] = _normalize_escapes(v)
        return data
    if isinstance(data, list):
        return [_normalize_escapes(x) for x in data]
    if isinstance(data, str):
        # \\(空格)或\\(行首)替换为换行。LaTeX 行末换行 \\ 保留（数学环境内）。
        # 简单启发：` \\ ` (前后空格的双反斜杠) → 换行
        return data.replace(" \\\\(", "\n(").replace("\\\\(", "\n(").replace(" \\\\ ", "\n").replace(" \\\\", "\n")
    return data


# ============== 主流程 ==============

def extract_answer_key(
    paper_path: Path,
    page_images: list[Path],
    output_path: Path,
    save_intermediate: Path | None = None,
) -> dict:
    """端到端：试卷扫描 + paper.json → answer-key.json。"""
    paper = json.loads(paper_path.read_text(encoding="utf-8"))
    print(f"📄 paper.json: {len(paper['questions'])} 题", file=sys.stderr)

    # 1. OCR 全部页，找答案页
    answer_pages_text = []
    for i, img in enumerate(page_images):
        if img.suffix.lower() == ".heic":
            img = heic_to_jpg(img)
        print(f"  [{i+1}/{len(page_images)}] OCR {img.name} ...",
              file=sys.stderr, flush=True)
        text = ocr_page(img)
        if is_answer_page(text):
            print(f"      ⭐ 答案页（含「{[kw for kw in ANSWER_PAGE_KEYWORDS if kw in text][0]}」关键字）",
                  file=sys.stderr)
            answer_pages_text.append((img.name, text))
        else:
            print(f"      普通题目页", file=sys.stderr)

    if not answer_pages_text:
        raise RuntimeError("没找到答案页（含「答案/评分标准/参考答案」关键字的页）")

    print(f"\n🔍 找到 {len(answer_pages_text)} 个答案页", file=sys.stderr)
    combined = "\n\n--- PAGE BREAK ---\n\n".join(t for _, t in answer_pages_text)

    if save_intermediate:
        save_intermediate.write_text(combined, encoding="utf-8")
        print(f"  → OCR 中间结果保存到 {save_intermediate}", file=sys.stderr)

    # 2. LLM 对齐
    print("\n🤖 调 qwen-max 对齐到 paper.json ...", file=sys.stderr)
    result = call_extract_llm(combined, paper)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ 已写 {output_path}", file=sys.stderr)

    # 摘要
    answers = result.get("answers", [])
    print(f"\n📊 抽取到 {len(answers)} 题的答案：", file=sys.stderr)
    for a in answers[:15]:
        qid = a.get("id", "?")
        correct = a.get("correct") or a.get("correctSolution", "")[:50]
        if isinstance(correct, list):
            correct = "/".join(str(c) for c in correct)
        print(f"  {qid:<6} {correct}", file=sys.stderr)
    if len(answers) > 15:
        print(f"  ... 还有 {len(answers) - 15} 题", file=sys.stderr)
    return result


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(description="从试卷扫描页提取标准答案 → answer-key.json")
    parser.add_argument("--paper", type=Path, required=True, help="paper.json")
    parser.add_argument("--pages", nargs="+", required=True,
                        help="试卷扫描页（PNG/JPG/HEIC），含答案页")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="输出 answer-key.json")
    parser.add_argument("--save-ocr-raw", type=Path,
                        help="可选：保存答案页 OCR 原始文本（debug）")
    args = parser.parse_args()

    page_paths = [Path(p) for p in args.pages]
    for p in page_paths:
        if not p.exists():
            print(f"❌ {p} 不存在", file=sys.stderr); sys.exit(1)

    extract_answer_key(
        paper_path=args.paper,
        page_images=page_paths,
        output_path=args.output,
        save_intermediate=args.save_ocr_raw,
    )


if __name__ == "__main__":
    main()
