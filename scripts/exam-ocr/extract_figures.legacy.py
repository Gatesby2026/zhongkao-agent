#!/usr/bin/env python3
"""从整页试卷图中裁剪出各题的图片区域。

流程：
  1. 读取 <paper_dir>/structured-cloud/final.json，找出所有含图的题目
     （stem 含 "[图]" 或 "如图"，或 options 有 "[图]"）
  2. 按 source_page 分组；source_page 为 None 时先用 qwen-vl-max 推断页码
  3. 对每页：发整页图 + 该页所有含图题目编号，让 qwen-vl-max 返回各题的图片区域
     （一页一次 API 调用）
  4. 用 PIL 裁剪并保存到 <paper_dir>/figures/q{num:02d}.png
  5. 更新 final.json，给每道题加 figure_path 字段（相对路径或 null）

CLI:
    python3 extract_figures.py <paper_dir> --subject physics

需 DASHSCOPE_API_KEY 环境变量，或脚本内硬编码（--api-key 参数）。
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

try:
    from PIL import Image
except ImportError:
    print("pip install pillow", file=sys.stderr); sys.exit(1)


# ========================= client =========================

def _client(api_key: str | None = None):
    key = api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY：设环境变量或传 --api-key")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def _img_to_data_url(p: Path) -> str:
    b = base64.b64encode(p.read_bytes()).decode("ascii")
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b}"


# ========================= 题目过滤 =========================

def _has_figure(q: dict) -> bool:
    """判断题目是否含图（stem 含 [图]/如图，或任何选项是 [图]）。"""
    stem = q.get("stem", "") or ""
    if "[图]" in stem or "如图" in stem:
        return True
    opts = q.get("options") or {}
    if isinstance(opts, dict):
        return any("[图]" in str(v) for v in opts.values())
    return False


# ========================= 页码推断 =========================

INFER_PAGE_PROMPT = """以下是一份试卷的各页 OCR 文本（每页用 ## page-NN 标头分隔）。
根据内容，判断每道指定题目最可能在哪页（即题干主体所在页）。

题目列表（题号）: {numbers}

输出 JSON，schema:
{{
  "pages": [
    {{"question": 2, "source_page": 1}},
    {{"question": 7, "source_page": 2}}
  ]
}}

只输出 JSON，不要加说明。"""


def infer_source_pages(client, questions_no_page: list[dict],
                        pages_text: list[str], retries: int = 3) -> dict[int, int]:
    """对 source_page 为 None 的题目，用 qwen-max 推断页码。
    返回 {question_number: page_number} 字典。
    """
    if not questions_no_page:
        return {}

    numbers = [q["number"] for q in questions_no_page]
    full_text = "\n\n".join(f"## page-{i+1:02d}\n{t}" for i, t in enumerate(pages_text))
    prompt = INFER_PAGE_PROMPT.format(numbers=", ".join(str(n) for n in numbers))

    print(f"  推断 {len(numbers)} 道题的页码：{numbers}", file=sys.stderr)
    last_err = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": "你是试卷分析助手，只输出 JSON。"},
                    {"role": "user", "content": prompt + "\n\n" + full_text},
                ],
                temperature=0.0,
                max_tokens=1024,
                response_format={"type": "json_object"},
                timeout=120,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
            data = json.loads(raw)
            result = {}
            for item in data.get("pages", []):
                q_num = item.get("question")
                page = item.get("source_page")
                if q_num is not None and page is not None:
                    result[int(q_num)] = int(page)
            print(f"  推断结果: {result}", file=sys.stderr)
            return result
        except Exception as e:
            last_err = e
            print(f"  ⚠️ 页码推断 attempt {attempt+1}/{retries}: {e}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    print(f"  ⚠️ 页码推断失败，将跳过这些题: {last_err}", file=sys.stderr)
    return {}


# ========================= 图片定位 =========================

LOCATE_FIGURES_PROMPT = """这是一张试卷页面图片。请精确定位以下各题的插图区域。

待定位的题目：
{questions_desc}

规则：
1. 坐标为百分比（0–100），以图片左上角为原点，x 向右，y 向下。
2. x1_pct/y1_pct 为区域左上角，x2_pct/y2_pct 为右下角。
3. 只框选图形本身（电路图/光路图/实物图/函数图象/表格等），不包含题目的文字题干。
4. 若某题的图由多个分散小图构成，返回包含所有小图的最小外接矩形。
5. 若某题在本页找不到图，将该题排除在输出之外，不要猜测。
6. 务必根据题干关键词找到正确位置，不要把相邻题目的图混淆。

输出 JSON，schema:
{{
  "figures": [
    {{"question": 6, "x1_pct": 10.5, "y1_pct": 25.3, "x2_pct": 48.0, "y2_pct": 42.1}},
    {{"question": 7, "x1_pct": 55.0, "y1_pct": 12.0, "x2_pct": 95.0, "y2_pct": 38.0}}
  ]
}}

只输出 JSON，不要加说明或代码块。"""


def locate_figures_on_page(client, page_img: Path, question_numbers: list[int],
                            question_stems: dict[int, str] | None = None,
                            retries: int = 3) -> list[dict]:
    """用 qwen-vl-max 定位一页上多道题的图片区域。
    question_stems: {题号: 题干文字摘要} 用于帮助模型精确匹配位置。
    返回 [{"question": N, "x1_pct": ..., ...}, ...]，坐标为百分比。
    """
    data_url = _img_to_data_url(page_img)
    # 构造题目描述：题号 + 题干关键词
    lines = []
    for n in question_numbers:
        stem_hint = ""
        if question_stems and n in question_stems:
            # 取前60字符作为定位线索
            raw = (question_stems[n] or "").strip()
            stem_hint = f"（题干开头：{raw[:60]}）"
        lines.append(f"- 第{n}题{stem_hint}")
    questions_desc = "\n".join(lines)
    prompt = LOCATE_FIGURES_PROMPT.format(questions_desc=questions_desc)

    last_err = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-vl-max",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                temperature=0.0,
                max_tokens=1024,
                timeout=120,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
            data = json.loads(raw)
            figures = data.get("figures", [])
            if not isinstance(figures, list):
                raise ValueError(f"figures 不是 list: {type(figures)}")
            return figures
        except Exception as e:
            last_err = e
            print(f"  ⚠️ locate attempt {attempt+1}/{retries} ({page_img.name}): {e}",
                  file=sys.stderr)
            time.sleep(3 * (attempt + 1))

    print(f"  ⚠️ 定位失败 {page_img.name}，跳过该页: {last_err}", file=sys.stderr)
    return []


# ========================= 坐标校验 =========================

def _validate_bbox(fig: dict, img_w: int, img_h: int, padding: int = 8) -> tuple | None:
    """校验并转换百分比坐标为像素坐标（含 padding）。
    返回 (x1, y1, x2, y2) 或 None（坐标异常则跳过）。

    异常条件：
    - x1 >= x2 或 y1 >= y2
    - 区域面积占整图面积 < 0.5%（过小，说明坐标错误）
    - 区域面积占整图面积 > 80%（过大，说明定位失败）
    - 任意坐标超出 0–100 范围
    """
    try:
        x1p = float(fig["x1_pct"])
        y1p = float(fig["y1_pct"])
        x2p = float(fig["x2_pct"])
        y2p = float(fig["y2_pct"])
    except (KeyError, TypeError, ValueError) as e:
        print(f"    ⚠️ Q{fig.get('question')}: 坐标字段缺失/格式错误: {e}", file=sys.stderr)
        return None

    # 自动归一化：若坐标值超出 0-100，判断是否为像素坐标，尝试除以图片尺寸转换
    if any(v > 100.0 for v in [x1p, y1p, x2p, y2p]):
        # 若 x 坐标大于 100，用图片宽度归一化；y 坐标用高度归一化
        if img_w > 0 and img_h > 0:
            x1p_norm = x1p / img_w * 100.0
            y1p_norm = y1p / img_h * 100.0
            x2p_norm = x2p / img_w * 100.0
            y2p_norm = y2p / img_h * 100.0
            if all(0.0 <= v <= 100.0 for v in [x1p_norm, y1p_norm, x2p_norm, y2p_norm]):
                print(f"    ℹ️ Q{fig.get('question')}: 坐标超出 0-100，检测为像素坐标，"
                      f"自动归一化 ({x1p:.0f},{y1p:.0f},{x2p:.0f},{y2p:.0f})px "
                      f"→ ({x1p_norm:.1f},{y1p_norm:.1f},{x2p_norm:.1f},{y2p_norm:.1f})%",
                      file=sys.stderr)
                x1p, y1p, x2p, y2p = x1p_norm, y1p_norm, x2p_norm, y2p_norm
            else:
                print(f"    ⚠️ Q{fig.get('question')}: 坐标超出 0-100 且归一化后仍超出，跳过: "
                      f"({x1p},{y1p},{x2p},{y2p})", file=sys.stderr)
                return None
        else:
            print(f"    ⚠️ Q{fig.get('question')}: 坐标超出 0-100 但图片尺寸为0，跳过", file=sys.stderr)
            return None

    # 范围检查
    for name, val in [("x1_pct", x1p), ("y1_pct", y1p), ("x2_pct", x2p), ("y2_pct", y2p)]:
        if not (0.0 <= val <= 100.0):
            print(f"    ⚠️ Q{fig.get('question')}: {name}={val} 超出 0-100，跳过", file=sys.stderr)
            return None

    if x1p >= x2p:
        print(f"    ⚠️ Q{fig.get('question')}: x1_pct({x1p}) >= x2_pct({x2p})，跳过", file=sys.stderr)
        return None
    if y1p >= y2p:
        print(f"    ⚠️ Q{fig.get('question')}: y1_pct({y1p}) >= y2_pct({y2p})，跳过", file=sys.stderr)
        return None

    area_pct = (x2p - x1p) * (y2p - y1p) / 100.0  # 占图面积百分比
    if area_pct < 0.5:
        print(f"    ⚠️ Q{fig.get('question')}: 区域面积 {area_pct:.2f}% 过小，跳过", file=sys.stderr)
        return None
    if area_pct > 80.0:
        print(f"    ⚠️ Q{fig.get('question')}: 区域面积 {area_pct:.2f}% 过大（可能定位失败），跳过", file=sys.stderr)
        return None

    # 转换为像素坐标并加 padding
    x1 = max(0, int(x1p / 100.0 * img_w) - padding)
    y1 = max(0, int(y1p / 100.0 * img_h) - padding)
    x2 = min(img_w, int(x2p / 100.0 * img_w) + padding)
    y2 = min(img_h, int(y2p / 100.0 * img_h) + padding)

    if x2 <= x1 or y2 <= y1:
        print(f"    ⚠️ Q{fig.get('question')}: padding 后区域无效，跳过", file=sys.stderr)
        return None

    return (x1, y1, x2, y2)


# ========================= 裁剪保存 =========================

def _expand_bbox(bbox, img_size, pct=10, min_px=15):
    """向外扩张 bbox（按 bbox 自身边长的百分比，至少 min_px 像素）。

    qwen-vl 给的 bbox 经常切掉图形边缘 → 先扩张再 CV 精修。

    返回 (expanded_bbox, expansion_amounts)：
      expansion_amounts = (top_pad, left_pad, bot_pad, right_pad)
      表示实际向各方向扩张的像素数（边界处可能小于 ex/ey）。
    """
    x1, y1, x2, y2 = bbox
    img_w, img_h = img_size
    bw, bh = x2 - x1, y2 - y1
    ex = max(min_px, int(bw * pct / 100))
    ey = max(min_px, int(bh * pct / 100))
    x1e = max(0, x1 - ex)
    y1e = max(0, y1 - ey)
    x2e = min(img_w, x2 + ex)
    y2e = min(img_h, y2 + ey)
    pad = (y1 - y1e, x1 - x1e, y2e - y2, x2e - x2)  # (top, left, bot, right)
    return (x1e, y1e, x2e, y2e), pad


def _find_blank_bands(is_blank, min_band: int) -> list[tuple[int, int]]:
    """在 1D 布尔向量上找连续 ≥ min_band 的 True 段。返回 [(start, end), ...] end 不含。"""
    bands = []
    in_b = False; start = 0
    n = len(is_blank)
    for i in range(n):
        if is_blank[i]:
            if not in_b:
                start = i; in_b = True
        else:
            if in_b:
                if i - start >= min_band:
                    bands.append((start, i))
                in_b = False
    if in_b and n - start >= min_band:
        bands.append((start, n))
    return bands


def _trim_one_axis(is_blank, axis_len: int,
                    bbox_lo: int, bbox_hi: int,
                    min_blank_band: int) -> tuple[int, int]:
    """在 1D 上做边缘剥离。bbox_lo/bbox_hi 是原 bbox 在该轴上的范围（end 不含）。

    规则：
    - 剥离只发生在 bbox 外的扩张区（即 [0, bbox_lo) 和 [bbox_hi, axis_len)）
    - 原 bbox 内部 [bbox_lo, bbox_hi) 永远保留（保护多子图组合，如甲/乙之间空白）
    - 低侧：从 0 扫到 bbox_lo，若中间有空白带，trim 到最靠近 bbox 的那个带的尾部
    - 高侧：对称处理

    返回 (new_lo, new_hi)。
    """
    new_lo = 0
    new_hi = axis_len

    # 低侧（top / left）：在 [0, bbox_lo) 找最后一个完整空白带，剥到其尾部
    bands = _find_blank_bands(is_blank[:bbox_lo], min_blank_band)
    if bands:
        new_lo = bands[-1][1]  # 最后一个空白带的尾（剥除该带之前的所有内容）

    # 高侧（bottom / right）：在 [bbox_hi, axis_len) 找第一个完整空白带，剥到其头部
    if bbox_hi < axis_len:
        bands = _find_blank_bands(is_blank[bbox_hi:], min_blank_band)
        if bands:
            new_hi = bbox_hi + bands[0][0]

    return new_lo, new_hi


def _trim_text_edges(crop_img: "Image.Image",
                     bbox_pad: tuple[int, int, int, int],
                     threshold: int = 140,
                     min_blank_band: int = 4):
    """从裁剪图的四周剥离文字行/列（无关文字泄漏）。

    核心原则：**剥离只在原 bbox 外的扩张区内进行，不侵入原 bbox**。
    bbox 内部的小空白带（如多子图组合甲/乙之间）会被完整保留。

    Args:
        bbox_pad: (top, left, bot, right) — _expand_bbox 返回的扩张像素数。
                  原 bbox 在当前 crop 内的位置 = (left, top, w-right, h-bot)
        threshold: 灰度二值化阈值
        min_blank_band: 连续 ≥ 这么多行/列的"软空白"才算分隔带

    返回 (cropped_img, top_offset_trimmed, bot_offset_trimmed)。
    """
    try:
        import numpy as np
    except ImportError:
        return crop_img, 0, 0

    arr = np.array(crop_img.convert("L"))
    h, w = arr.shape
    if h < 30 or w < 30:
        return crop_img, 0, 0

    top_pad, left_pad, bot_pad, right_pad = bbox_pad
    # 若该方向没扩张（pad=0），就不在那侧剥离
    bbox_top = top_pad
    bbox_bot = h - bot_pad
    bbox_left = left_pad
    bbox_right = w - right_pad

    binary = arr < threshold
    # "软空白"阈值：< 该方向长度 * 1.5%（最少 3），容忍轻微干扰/anti-aliasing
    row_blank_thresh = max(3, int(w * 0.015))
    col_blank_thresh = max(3, int(h * 0.015))
    is_blank_row = (binary.sum(axis=1) < row_blank_thresh)
    is_blank_col = (binary.sum(axis=0) < col_blank_thresh)

    top, bottom = _trim_one_axis(is_blank_row, h, bbox_top, bbox_bot, min_blank_band)
    left, right = _trim_one_axis(is_blank_col, w, bbox_left, bbox_right, min_blank_band)

    # 保护：剥过头 → 回退
    if bottom - top < max(30, h // 4) or right - left < max(30, w // 4):
        return crop_img, 0, 0

    return crop_img.crop((left, top, right, bottom)), top, h - bottom


def crop_and_save(page_img: Path, bbox: tuple, out_path: Path,
                  refine: bool = True, expand_pct: int = 10) -> bool:
    """裁剪页面图片并保存。

    refine=True 时启用 CV 精修：扩张 bbox + 剥离顶/底文字行。
    """
    try:
        img = Image.open(page_img)

        if refine:
            # 1. 向外扩张，捕获 qwen-vl 切掉的边缘
            expanded, pad = _expand_bbox(bbox, img.size, pct=expand_pct)
            cropped = img.crop(expanded)
            orig_size = cropped.size
            # 2. 边缘文字剥离（只剥扩张区，不侵入原 bbox 内部）
            cropped, top_trim, bot_trim = _trim_text_edges(cropped, pad)
            if cropped.size != orig_size:
                print(f"    ✂️ 边缘剥离 {orig_size} → {cropped.size}",
                      file=sys.stderr)
        else:
            cropped = img.crop(bbox)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(out_path, "PNG")
        return True
    except Exception as e:
        print(f"    ⚠️ 裁剪保存失败 {out_path.name}: {e}", file=sys.stderr)
        return False


# ========================= 读取 OCR 页文本 =========================

def _load_pages_text(paper_dir: Path) -> list[str]:
    """读取 pages/ 目录下的 OCR 缓存文本，按页码排序。"""
    pages_dir = paper_dir / "pages"
    if not pages_dir.exists():
        return []
    files = sorted(pages_dir.glob("page-*.ocr.txt"))
    return [f.read_text(encoding="utf-8") for f in files]


# ========================= 主流程 =========================

def extract_figures(paper_dir: Path, subject: str, api_key: str | None = None,
                    padding: int = 8, dry_run: bool = False) -> None:
    """主入口：从 final.json 读取题目，裁剪图片，更新 final.json。"""
    final_json = paper_dir / "structured-cloud" / "final.json"
    images_dir = paper_dir / "images"
    figures_dir = paper_dir / "figures"

    if not final_json.exists():
        raise FileNotFoundError(f"找不到 final.json: {final_json}")

    data = json.loads(final_json.read_text(encoding="utf-8"))
    questions = data.get("questions", [])

    # 找出含图的题目
    fig_questions = [q for q in questions if _has_figure(q)]
    print(f"共 {len(questions)} 题，其中 {len(fig_questions)} 道含图")

    if not fig_questions:
        print("无含图题目，退出。")
        return

    client = _client(api_key)

    # 处理 source_page 为 None 的题目
    no_page_qs = [q for q in fig_questions if q.get("source_page") is None]
    if no_page_qs:
        print(f"  {len(no_page_qs)} 道题缺 source_page，尝试从 OCR 缓存推断...")
        pages_text = _load_pages_text(paper_dir)
        if pages_text:
            inferred = infer_source_pages(client, no_page_qs, pages_text)
            for q in no_page_qs:
                pg = inferred.get(q["number"])
                if pg:
                    q["source_page"] = pg
                    print(f"    Q{q['number']}: 推断 source_page={pg}")
                else:
                    print(f"    ⚠️ Q{q['number']}: 无法推断页码，将跳过")
        else:
            print("  ⚠️ 无 pages/ OCR 缓存，无法推断页码，source_page=None 的题目将跳过")

    # 按页分组（排除仍无页码的）
    page_to_questions: dict[int, list[dict]] = {}
    skipped_no_page = []
    for q in fig_questions:
        pg = q.get("source_page")
        if pg is None:
            skipped_no_page.append(q["number"])
            continue
        page_to_questions.setdefault(int(pg), []).append(q)

    if skipped_no_page:
        print(f"  ⚠️ 跳过无页码题目: {skipped_no_page}")

    # 确认图片文件存在
    all_images = sorted(images_dir.glob("page-*.png"))
    if not all_images:
        raise FileNotFoundError(f"images/ 目录无 page-*.png: {images_dir}")
    # 建立 page_num → file 映射
    page_img_map: dict[int, Path] = {}
    for img in all_images:
        m = re.search(r"page-(\d+)", img.stem)
        if m:
            page_img_map[int(m.group(1))] = img

    # 逐页定位图片
    figure_paths: dict[int, str] = {}  # question_number → relative_path or None

    for page_num in sorted(page_to_questions.keys()):
        qs_on_page = page_to_questions[page_num]
        q_numbers = [q["number"] for q in qs_on_page]

        if page_num not in page_img_map:
            print(f"  ⚠️ page-{page_num:02d}.png 不存在，跳过题目 {q_numbers}")
            continue

        page_img = page_img_map[page_num]
        print(f"\n  处理 page-{page_num:02d} (题目 {q_numbers}) ...")

        if dry_run:
            print(f"    [dry-run] 跳过 API 调用")
            continue

        # 构造题干摘要 {题号: 题干前60字}，帮助模型精确定位
        stems_hint = {q["number"]: (q.get("stem") or "")[:60] for q in qs_on_page}

        # 调用 qwen-vl-max 定位
        figures = locate_figures_on_page(client, page_img, q_numbers,
                                         question_stems=stems_hint)
        print(f"    qwen-vl-max 返回 {len(figures)} 个区域")

        if not figures:
            print(f"    ⚠️ 该页无有效定位结果")
            continue

        # 打开图片获取尺寸（只打开一次）
        with Image.open(page_img) as img:
            img_w, img_h = img.size

        # 按题号分组：同一题可能有多个区域（图甲、图乙等），合并为外接矩形
        from collections import defaultdict
        figs_by_q: dict[int, list[dict]] = defaultdict(list)
        for fig in figures:
            q_num = fig.get("question")
            if q_num is None:
                print(f"    ⚠️ 缺 question 字段: {fig}", file=sys.stderr)
                continue
            figs_by_q[int(q_num)].append(fig)

        for q_num, q_figs in sorted(figs_by_q.items()):
            # 先单独归一化每个 bbox，再合并
            valid_bboxes = []
            for fig in q_figs:
                print(f"    Q{q_num}: bbox=({fig.get('x1_pct')},{fig.get('y1_pct')})"
                      f"-({fig.get('x2_pct')},{fig.get('y2_pct')})")
                bbox = _validate_bbox(fig, img_w, img_h, padding=0)
                if bbox is not None:
                    valid_bboxes.append(bbox)

            if not valid_bboxes:
                continue

            # 合并所有有效 bbox（外接矩形）；不在此加 padding，
            # 由 crop_and_save() 内的 _expand_bbox + _trim_text_edges 统一处理
            x1 = min(b[0] for b in valid_bboxes)
            y1 = min(b[1] for b in valid_bboxes)
            x2 = max(b[2] for b in valid_bboxes)
            y2 = max(b[3] for b in valid_bboxes)

            if len(q_figs) > 1:
                print(f"    Q{q_num}: {len(q_figs)} 个区域合并为外接矩形")

            out_name = f"q{q_num:02d}.png"
            out_path = figures_dir / out_name

            if crop_and_save(page_img, (x1, y1, x2, y2), out_path):
                rel_path = f"figures/{out_name}"
                figure_paths[q_num] = rel_path
                print(f"    ✅ Q{q_num} → {rel_path}  ({x2-x1}×{y2-y1}px)")
            else:
                print(f"    ❌ Q{q_num} 裁剪失败")

    # 更新 final.json：给每道题加 figure_path 字段
    for q in questions:
        num = q.get("number")
        if num in figure_paths:
            q["figure_path"] = figure_paths[num]
        elif _has_figure(q):
            # 含图但未成功裁剪 → 置 null
            q.setdefault("figure_path", None)
        else:
            q.setdefault("figure_path", None)

    if not dry_run:
        final_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n  ✅ final.json 已更新，{len(figure_paths)} 道题添加了 figure_path")
    else:
        print(f"\n  [dry-run] 不写入 final.json")

    # 汇总
    print("\n=== 汇总 ===")
    print(f"  含图题目总数: {len(fig_questions)}")
    print(f"  成功裁剪: {len(figure_paths)}")
    no_crop = [q['number'] for q in fig_questions if q['number'] not in figure_paths]
    if no_crop:
        print(f"  未裁剪题目: {no_crop}")


# ========================= CLI =========================

def main():
    p = argparse.ArgumentParser(
        description="从整页试卷图中裁剪题目图片，更新 final.json"
    )
    p.add_argument("paper_dir", type=Path,
                   help="单卷目录，包含 images/、structured-cloud/final.json")
    p.add_argument("--subject", required=True,
                   help="科目（physics/math/chinese 等），目前仅用于日志")
    p.add_argument("--api-key", default=None,
                   help="DashScope API Key（也可用 DASHSCOPE_API_KEY 环境变量）")
    p.add_argument("--padding", type=int, default=8,
                   help="裁剪时额外加的像素 padding（默认 8）")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印定位结果，不裁剪也不写 final.json")
    args = p.parse_args()

    paper_dir = args.paper_dir.resolve()
    if not paper_dir.is_dir():
        print(f"目录不存在: {paper_dir}", file=sys.stderr)
        sys.exit(1)

    extract_figures(
        paper_dir=paper_dir,
        subject=args.subject,
        api_key=args.api_key,
        padding=args.padding,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
