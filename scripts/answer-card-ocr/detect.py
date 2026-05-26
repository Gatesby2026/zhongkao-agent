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

try:
    from PIL import Image, ImageOps
    try:
        import pillow_heif  # noqa
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


def _upright_jpeg_bytes(src: Path, max_dim: int = 3000) -> bytes:
    """按 EXIF 旋转到位、去 EXIF，返回正立 JPEG 字节。

    手机照片像素横置 + EXIF 方向标记，qwen-vl-ocr 看歪图 → 涂卡识别错。
    OCR 前必须先把方向烘焙进像素。幂等：已正立图原样重编码。
    """
    if not _PIL_OK:
        return src.read_bytes()
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > max_dim:
        s = max_dim / float(max(w, h))
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    import io as _io
    buf = _io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


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
    b64 = base64.b64encode(_upright_jpeg_bytes(image_path)).decode()
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
    # 检测覆盖追踪（用于报告 data_quality.answer_card_missing_qids）
    choice_qids_parsed: list[int] = None      # Phase A 真正识别到的 qids
    subjective_qids_cropped: list[int] = None  # Phase B 真正裁切到的 qids


def detect_card(
    image_paths: list[Path],
    student_name: Optional[str] = None,
    student_id: Optional[str] = None,
    options_per_question: int = 4,
    subjective_qnums: Optional[list[int]] = None,
    photos_dir: Optional[Path] = None,
    standard_yaml: Optional[Path] = None,
) -> CardDetectionResult:
    """对一组答题卡照片做涂卡识别 + 主观题区裁切。

    多张照片视为同一份卷子（不同区域 / 不同页），结果合并。

    Args:
        subjective_qnums: 主观题题号列表（如 [16,17,...,26]）。如果传入，
            自动调 crop_subjective.py 裁切主观题作答区到
            photos_dir/cropped/q{NN}.png，并在结果里加占位条目。
        photos_dir: 用于存放 cropped/ 子目录的路径（默认取 image_paths[0] 父目录）

    Returns:
        CardDetectionResult，含 student + answers 列表
    """
    options = tuple("ABCDE"[:options_per_question])

    all_lines: list[str] = []
    for img in image_paths:
        if img.suffix.lower() == ".heic":
            try:
                img = heic_to_jpg(img)        # macOS sips（若可用）
            except Exception:
                pass                          # 无 sips：交给 PIL+pillow_heif
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

    # Phase A 识别到的选择题 qids（用于报告 missing 追踪）
    choice_qids_parsed = sorted(choices_map.keys())
    subjective_qids_cropped: list[int] = []

    # 主观题区裁切 + 手写 OCR（如果传入了 subjective_qnums）
    if subjective_qnums:
        pd = photos_dir or image_paths[0].parent
        cropped_dir = pd / "cropped"
        cropped_dir.mkdir(parents=True, exist_ok=True)
        try:
            from crop_subjective import crop_subjective
            print(f"\n  🖼️  裁切主观题作答区（共 {len(subjective_qnums)} 题）...",
                  file=sys.stderr)
            crop_result = crop_subjective(image_paths, subjective_qnums, cropped_dir)
            subjective_qids_cropped = sorted(crop_result.keys())

            # 对每张裁切好的图调讯飞手写识别（并发）
            print(f"\n  ✍️  讯飞手写 OCR 识别（并发）...", file=sys.stderr)
            from xfyun_ocr import recognize_handwriting
            from concurrent.futures import ThreadPoolExecutor, as_completed

            hw_results: dict[int, dict] = {}

            def _hw_one(qid):
                meta = crop_result.get(qid)
                if not meta:
                    return qid, None
                img_path = cropped_dir / Path(meta["image_path"]).name
                try:
                    r = recognize_handwriting(img_path)
                    return qid, r
                except Exception as e:
                    print(f"    ⚠️ Q{qid} 手写 OCR 失败: {e}", file=sys.stderr)
                    return qid, {"text": "", "confidence_avg": None, "error": str(e)}

            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = [ex.submit(_hw_one, q) for q in subjective_qnums
                        if q in crop_result]
                for fut in as_completed(futs):
                    qid, r = fut.result()
                    hw_results[qid] = r
                    if r and r.get("text"):
                        preview = r["text"][:40].replace("\n", " | ")
                        print(f"    Q{qid}: {preview}", file=sys.stderr)

            # 辅助评分（方案 B：直接看图），仅当传入 standard_yaml
            grade_b_results: dict[int, dict] = {}
            if standard_yaml:
                # 采纳方案 B：qwen-vl-max 直接看裁切图 + 题干 + 标准答案辅助评分。
                # （方案 A 即 OCR 后处理已废弃——易被标准答案带偏过度修正；
                #  subjective_grade.correct_with_context 保留作 fallback/对照）
                print(f"\n  🧠 辅助评分（方案 B：直接看图，qwen-vl-max 并发）...",
                      file=sys.stderr)
                from subjective_grade import load_paper_questions, read_and_grade
                paper = load_paper_questions(standard_yaml)

                def _grade_one(qid):
                    q = paper.get(qid)
                    meta = crop_result.get(qid, {})
                    if not q or not meta:
                        return qid, None
                    img_path = cropped_dir / Path(meta["image_path"]).name
                    try:
                        return qid, read_and_grade(
                            image_path=img_path,
                            stem=q.get("stem", ""),
                            std_answer=str(q.get("answer", "")),
                            solution=q.get("solution", ""),
                            full_score=q.get("score", 4),
                            qtype=q.get("type", "解答"),
                        )
                    except Exception as e:
                        return qid, {"error": str(e)}

                with ThreadPoolExecutor(max_workers=4) as ex:
                    futs = [ex.submit(_grade_one, q) for q in subjective_qnums
                            if q in crop_result]
                    for fut in as_completed(futs):
                        qid, g = fut.result()
                        if g:
                            grade_b_results[qid] = g
                        print(f"    Q{qid}: 建议 {(g or {}).get('suggestedScore','—')} 分",
                              file=sys.stderr)

            # 加到 answers
            for qid in subjective_qnums:
                meta = crop_result.get(qid, {})
                hw = hw_results.get(qid) or {}
                answers.append({
                    "qId": f"Q{qid}",
                    "type": "subjective",
                    "filled": None,
                    "handwritingText": hw.get("text") or None,
                    "confidence": hw.get("confidence_avg"),
                    "regionImage": meta.get("image_path"),
                    "pageImage": meta.get("page_image"),
                    "needsReview": True,
                    "grade": grade_b_results.get(qid),  # 方案 B：看图辅助评分
                })
            answers.sort(key=lambda a: int(a["qId"][1:]))
        except Exception as e:
            print(f"  ⚠️ 主观题流水线失败：{e}", file=sys.stderr)
            import traceback; traceback.print_exc(file=sys.stderr)

        # P0.3 阈值：主观题裁切覆盖率过低（<30%）→ 让 _pipeline mark_failed
        # 提示重传更清晰的主观题作答页（在 try/except 之外，绕过吞错）
        if (len(subjective_qnums) >= 3
                and len(subjective_qids_cropped) / len(subjective_qnums) < 0.30):
            raise RuntimeError(
                f"答题卡主观题作答区识别覆盖过低："
                f"成功 {len(subjective_qids_cropped)}/{len(subjective_qnums)} 题"
                "。请重新拍摄主观题作答页（光线均匀、整页入框、字迹清晰）")

    return CardDetectionResult(
        student={"name": student_name or "", "examId": student_id or ""},
        answers=answers,
        raw_ocr_lines=all_lines,
        matched_questions=len(choices_map),
        choice_qids_parsed=choice_qids_parsed,
        subjective_qids_cropped=subjective_qids_cropped,
    )


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(description="答题卡涂卡识别（缺字母法）")
    parser.add_argument("images", nargs="+", help="答题卡照片（JPG/PNG/HEIC）")
    parser.add_argument("--student-name", default="")
    parser.add_argument("--student-id", default="")
    parser.add_argument("--options-per-question", type=int, default=4,
                        help="每题选项数（4=ABCD 默认；5=ABCDE）")
    parser.add_argument("--subjective-qnums", default="",
                        help="主观题题号列表（逗号分隔），如 16,17,...,26。"
                             "传入则自动裁切主观题作答区到 cropped/q{NN}.png")
    parser.add_argument("--standard-yaml", type=Path,
                        help="试卷标准答案 yaml 路径。传入则自动跑辅助评分"
                             "（方案 A: OCR 后处理 + 方案 B: 看图阅卷）")
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
    subjective_qnums = None
    if args.subjective_qnums:
        subjective_qnums = [int(x) for x in args.subjective_qnums.split(",")]
    result = detect_card(
        image_paths,
        student_name=args.student_name,
        student_id=args.student_id,
        options_per_question=args.options_per_question,
        subjective_qnums=subjective_qnums,
        standard_yaml=args.standard_yaml,
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
        t_map = {"multi_choice": "多选", "subjective": "主观", "choice": "单选"}
        t = t_map.get(a["type"], a["type"])
        f = a.get("filled")
        if f is None:
            f_str = "—"
        elif isinstance(f, list):
            f_str = "".join(f)
        else:
            f_str = str(f)
        conf = a.get("confidence")
        conf_str = f"{conf:.2f}" if conf is not None else "—"
        region = a.get("regionImage", "")
        print(f"  {a['qId']:<6} {t}  涂卡={f_str:<6}  conf={conf_str}  {region}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
