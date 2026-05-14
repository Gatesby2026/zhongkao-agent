#!/usr/bin/env python3
"""答题卡涂卡识别 — production 版（缺字母法）。

核心思路：用 Qwen-VL-OCR 读出印刷字符，涂黑的字母 OCR 读不到，缺哪个 = 涂哪个。
无需 template、无需 bubble 检测、无需透视矫正。

CLI:
    python detect.py photo1.jpg photo2.jpg \\
        --student-name "贾小淇" --student-id 17020950 \\
        --output answer-card.json

Module:
    from scripts.answer_card_ocr.detect import detect_card
    result = detect_card([Path("photo1.jpg"), ...], student_name="...")
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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import openai
except ImportError:
    print("pip install openai", file=sys.stderr); sys.exit(1)


# ============== HEIC 转换 ==============

def heic_to_jpg(heic: Path, max_dim: int = 2400) -> Path:
    """用 macOS sips 把 HEIC 转 JPG，返回临时文件路径。"""
    if heic.suffix.lower() != ".heic":
        return heic
    out = Path(tempfile.gettempdir()) / f"answercard-{heic.stem}.jpg"
    subprocess.run(
        ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88",
         "-Z", str(max_dim), str(heic), "--out", str(out)],
        check=True, capture_output=True,
    )
    return out


# ============== OCR 调用 ==============

OCR_PROMPT = """你是 OCR 转录器。把图中**所有印刷文字**逐行抄录下来，纯文本输出。

涂卡选择题部分必须**逐字符抄录所有可见的 A B C D 字母**——
**如果某个字母被涂黑/遮挡看不见，直接跳过不写**。
不要"猜测"或"补全"。

示例：如果图里写着 "2. A▓ C D"（B 被涂黑），抄录为：
2. A C D

如果是多选题，多个字母被涂黑，全部跳过：
"13. A▓ ▓ D" → 抄录 "13. A D"

不要 markdown，不要 JSON，不要解释，直接纯文本逐行输出。"""


def _client():
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "缺 DASHSCOPE_API_KEY 环境变量。\n"
            "见 ~/.claude/projects/.../memory/api-keys.md"
        )
    return openai.OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def ocr_one_image(image_path: Path, model: str = "qwen-vl-ocr-latest") -> list[str]:
    """单张图 OCR，返回行列表。"""
    client = _client()
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": OCR_PROMPT},
        ]}],
        temperature=0.0,
        max_tokens=8192,
    )
    raw = resp.choices[0].message.content
    return [l.strip() for l in raw.split("\n") if l.strip()]


# ============== 解析逻辑 ==============

# 匹配 "数字. 字母组合"（容许中文括号"（一）11. ABC"等前缀）
# 题号: 1-3 位数字; 字母组合: 1-5 个 ABCDE 字母（贪婪，用空格隔开）
QUESTION_PATTERN = re.compile(
    r"(\d{1,3})\s*[.．、]\s*([A-E](?:\s+[A-E]){0,4})"
)


def parse_choices(lines: list[str]) -> dict[int, str]:
    """从 OCR 行里抽 题号 → OCR 看到的字母序列。"""
    results: dict[int, str] = {}
    text = " ".join(lines)
    for m in QUESTION_PATTERN.finditer(text):
        qid = int(m.group(1))
        letters = re.sub(r"\s+", "", m.group(2))
        # 严格：1-5 个字母，纯 ABCDE
        if 1 <= len(letters) <= 5 and all(c in "ABCDE" for c in letters):
            results[qid] = letters
    return results


def infer_filled(seen: str, options: tuple[str, ...] = ("A", "B", "C", "D")) -> dict:
    """OCR 看到 vs 完整选项 → 推断涂卡。"""
    seen_set = set(seen)
    missing = [c for c in options if c not in seen_set]
    n_missing = len(missing)

    if n_missing == 0:
        return {"filled": [], "type": "no_answer", "confidence": 0.5}
    if n_missing == 1:
        return {"filled": missing, "type": "choice", "confidence": 0.95}
    if n_missing <= 3:
        return {"filled": missing, "type": "multi_choice", "confidence": 0.9}
    # 4 个都缺，可能 OCR 失败 / 整行都涂了，标低置信
    return {"filled": missing, "type": "unknown", "confidence": 0.3}


# ============== 主接口 ==============

@dataclass
class CardDetectionResult:
    student: dict
    answers: list[dict]
    raw_ocr_lines: list[str]
    matched_questions: int


def detect_card(
    image_paths: list[Path],
    student_name: Optional[str] = None,
    student_id: Optional[str] = None,
    options_per_question: int = 4,
) -> CardDetectionResult:
    """对一组答题卡照片做涂卡识别。

    多张照片视为同一份卷子（不同区域 / 不同页），结果合并。

    Returns:
        CardDetectionResult，含 student + answers 列表（answer-card.json 标准结构）
    """
    options = tuple("ABCDE"[:options_per_question])

    all_lines: list[str] = []
    for img in image_paths:
        # HEIC 自动转
        if img.suffix.lower() == ".heic":
            img = heic_to_jpg(img)
        print(f"  OCR: {img.name} ...", file=sys.stderr, flush=True)
        lines = ocr_one_image(img)
        all_lines.extend(lines)

    choices_map = parse_choices(all_lines)
    answers = []
    for qid in sorted(choices_map.keys()):
        seen = choices_map[qid]
        inf = infer_filled(seen, options)
        filled = inf["filled"]
        # 标准 schema 输出
        if inf["type"] == "choice":
            filled_val: str | list[str] = filled[0]
        elif inf["type"] in ("multi_choice", "no_answer", "unknown"):
            filled_val = filled
        else:
            filled_val = filled
        answers.append({
            "qId": f"Q{qid}",
            "type": "multi_choice" if inf["type"] == "multi_choice" else "choice",
            "filled": filled_val,
            "confidence": inf["confidence"],
            "ocrSeen": seen,
        })

    return CardDetectionResult(
        student={"name": student_name or "", "examId": student_id or ""},
        answers=answers,
        raw_ocr_lines=all_lines,
        matched_questions=len(choices_map),
    )


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(description="答题卡涂卡识别（缺字母法）")
    parser.add_argument("images", nargs="+", help="答题卡照片（JPG/PNG/HEIC）")
    parser.add_argument("--student-name", default="")
    parser.add_argument("--student-id", default="")
    parser.add_argument("--options-per-question", type=int, default=4,
                        help="每题选项数（4=ABCD 默认；5=ABCDE）")
    parser.add_argument("--output", "-o", type=Path,
                        help="输出 answer-card.json 路径")
    parser.add_argument("--save-ocr-raw", type=Path,
                        help="可选：保存 OCR 原始行（debug 用）")
    args = parser.parse_args()

    image_paths = [Path(p) for p in args.images]
    for p in image_paths:
        if not p.exists():
            print(f"❌ 找不到 {p}", file=sys.stderr); sys.exit(1)

    print(f"📷 输入 {len(image_paths)} 张照片", file=sys.stderr)
    result = detect_card(
        image_paths,
        student_name=args.student_name,
        student_id=args.student_id,
        options_per_question=args.options_per_question,
    )

    out_json = {
        "student": result.student,
        "answers": result.answers,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✅ 已写 {args.output}", file=sys.stderr)
    else:
        print(json.dumps(out_json, ensure_ascii=False, indent=2))

    if args.save_ocr_raw:
        args.save_ocr_raw.write_text(
            "\n".join(result.raw_ocr_lines), encoding="utf-8"
        )

    # stderr 输出摘要
    print(f"\n📊 识别 {result.matched_questions} 题：", file=sys.stderr)
    for a in result.answers:
        t = "多选" if a["type"] == "multi_choice" else "单选"
        f = a["filled"]
        f_str = "".join(f) if isinstance(f, list) else f
        print(f"  {a['qId']:<6} {t}  涂卡={f_str:<6}  conf={a['confidence']:.2f}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
