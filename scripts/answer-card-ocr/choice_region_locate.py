#!/usr/bin/env python3
"""选择题填涂区**裁切器**（仅定位 bbox，不做填涂识别）。

跟下游"识别"完全解耦：
  Crop 层（本模块）  → 给出 choice_region_bbox + 旋转角度 + 行列估计
  Detect 层（独立）  → 在 cropped 区域内用 Path B 像素/Path C 缺字母法等识别填涂

实现方法 v1：
  1. 腾讯 GeneralAccurateOCR 跑全图（带 Angle 自动识别）
  2. 过滤所有含 A/B/C/D 字符的 token（含合并 token "[B][C][D]" / "8.[A][B][C]"）
  3. 聚类成行（y_tol）
  4. 涂卡区候选行 = 含 4+ 字母 + distinct >= 2 的行
  5. 包络候选行的 bbox = 涂卡区 bbox
  6. 输出：bbox + angle + n_rows + n_questions_per_row 估计

外部 API 候选（已测）：
  - 腾讯 QuestionSplitLayoutOCR — 给 Angle，但只标 problem-solving 没选择题
  - 腾讯 EduPaperOCR — 主要识别公式
  - 腾讯 QuestionOCR — 全部当 problem-solving 处理
  - 阿里云 ScannedFormRecognition — 待测
  - 自训 YOLO — 后续大数据时考虑

→ 当前最优 = GeneralAccurateOCR + 字符级聚类（精度足够，无需自训）

成本：每张卡 1 个腾讯 API 调用（~RMB 0.05）
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print("pip install pillow", file=sys.stderr); sys.exit(1)

import base64
import io

from tencent_choice_grid import (
    _ocr_letters, _cluster_rows, _filter_choice_rows, _img_to_b64,
    _get_client, _split_compound_token, _LETTER_CHAR_RE
)


def _ocr_with_angle(image_path: Path) -> tuple[list[dict], float]:
    """跑 GeneralAccurateOCR，返回 (letters, angle)。"""
    from tencentcloud.ocr.v20181119 import models
    client = _get_client()
    req = models.GeneralAccurateOCRRequest()
    req.ImageBase64 = _img_to_b64(image_path)
    resp = client.GeneralAccurateOCR(req)
    angle = float(getattr(resp, "Angle", 0) or 0)

    letters = []
    for det in resp.TextDetections:
        text = (det.DetectedText or "").strip()
        if not _LETTER_CHAR_RE.search(text):
            continue
        if len(text) > 16 or any(c in text for c in "=∵∴∠△⌐≠≡"):
            continue
        poly = det.ItemPolygon
        x1, y1 = poly.X, poly.Y
        x2, y2 = poly.X + poly.Width, poly.Y + poly.Height
        letters.extend(_split_compound_token(text, x1, y1, x2, y2))
    return letters, angle


def _ocr_on_image(im: Image.Image) -> list[dict]:
    """对已加载 PIL 图（已旋正）跑 OCR 取字母。"""
    from tencentcloud.ocr.v20181119 import models
    if im.mode != "RGB":
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    client = _get_client()
    req = models.GeneralAccurateOCRRequest()
    req.ImageBase64 = b64
    resp = client.GeneralAccurateOCR(req)
    letters = []
    for det in resp.TextDetections:
        text = (det.DetectedText or "").strip()
        if not _LETTER_CHAR_RE.search(text):
            continue
        if len(text) > 16 or any(c in text for c in "=∵∴∠△⌐≠≡"):
            continue
        poly = det.ItemPolygon
        x1, y1 = poly.X, poly.Y
        x2, y2 = poly.X + poly.Width, poly.Y + poly.Height
        letters.extend(_split_compound_token(text, x1, y1, x2, y2))
    return letters


def _round_angle_to_quarter(angle: float) -> int:
    """把腾讯返回的浮点 angle 归一到 0/90/180/270 整数。"""
    # 腾讯 angle 是"需要旋转的角度"
    # angle ~89.4 → 90°（顺时针旋转 90°）
    a = (round(angle / 90) * 90) % 360
    return int(a)


def locate_choice_region(image_path: Path) -> dict:
    """定位涂卡区 bbox（不做填涂识别）。

    流程：
      1. 第一次 OCR 拿 angle
      2. 按 angle 旋转图（PIL 逆时针 +angle → 显示正立）
      3. 在旋正图上重新 OCR，拿字母 bbox（坐标系跟图像素对齐）
      4. 聚类成行 + 过滤 + 包络 = 涂卡区 bbox

    Returns:
        {
            "found": bool,
            "bbox": (x1, y1, x2, y2),  # 涂卡区在**旋正后**图中的 bbox
            "angle": int,                # 实际应用的旋转角度（0/90/180/270）
            "uplifted_image": PIL.Image, # 旋正后的图（供后续裁切/识别用）
            "n_rows": int,
            "n_questions_per_row": int,
            "n_questions": int,
            "row_bands": list[tuple],
        }
    """
    # Step 1: 拿 angle
    _, raw_angle = _ocr_with_angle(image_path)
    angle = _round_angle_to_quarter(raw_angle)

    # Step 2: 旋正图
    im = Image.open(image_path)
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    if angle != 0:
        # 腾讯 Angle = "图像当前相对正立旋转的角度，需逆时针旋转该角度恢复正立"
        # PIL rotate(angle) = 逆时针 angle°，正好对应
        im_upright = im.rotate(angle, expand=True)
    else:
        im_upright = im

    # Step 3: 在旋正图上重新 OCR
    letters = _ocr_on_image(im_upright)
    if not letters:
        return {"found": False, "reason": "no A/B/C/D letters detected",
                "angle": angle, "uplifted_image": im_upright}

    rows = _cluster_rows(letters)
    choice_rows = _filter_choice_rows(rows)
    if not choice_rows:
        return {"found": False, "reason": "no row contains 4+ choice letters",
                "angle": angle, "uplifted_image": im_upright}

    all_x = [L["x1"] for r in choice_rows for L in r] + \
            [L["x2"] for r in choice_rows for L in r]
    all_y = [L["y1"] for r in choice_rows for L in r] + \
            [L["y2"] for r in choice_rows for L in r]
    bbox = (min(all_x), min(all_y), max(all_x), max(all_y))

    row_bands = []
    for r in choice_rows:
        ys1 = min(L["y1"] for L in r)
        ys2 = max(L["y2"] for L in r)
        row_bands.append((ys1, ys2))

    max_letters = max(len(r) for r in choice_rows)
    n_q_per_row = max(1, max_letters // 4 + (1 if max_letters % 4 else 0))

    return {
        "found": True,
        "bbox": bbox,
        "angle": angle,
        "uplifted_image": im_upright,
        "n_rows": len(choice_rows),
        "n_questions_per_row": n_q_per_row,
        "n_questions": sum(len(r) // 4 + (1 if len(r) % 4 else 0)
                            for r in choice_rows),
        "row_bands": row_bands,
        "n_letters_total": sum(len(r) for r in choice_rows),
    }


def crop_choice_region(image_path: Path, margin: int = 50) -> tuple[Image.Image, dict]:
    """根据 locate_choice_region 返回的 bbox 裁切**旋正后**的图。

    Returns:
        (cropped_image, info)  # info 含 uplifted_image (旋正后整张) + bbox 等
    """
    info = locate_choice_region(image_path)
    if not info.get("found"):
        return None, info

    im = info["uplifted_image"]
    x1, y1, x2, y2 = info["bbox"]
    W, H = im.size
    crop_x1 = max(0, x1 - margin)
    crop_y1 = max(0, y1 - margin)
    crop_x2 = min(W, x2 + margin)
    crop_y2 = min(H, y2 + margin)
    cropped = im.crop((crop_x1, crop_y1, crop_x2, crop_y2))
    info["crop_bbox"] = (crop_x1, crop_y1, crop_x2, crop_y2)
    return cropped, info


def _main():
    if len(sys.argv) < 2:
        print("用法: python3 choice_region_locate.py <image.jpg> [out.png]",
              file=sys.stderr)
        sys.exit(1)
    p = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else \
          Path(f"/tmp/{p.stem}_choice_region.png")

    cropped, info = crop_choice_region(p)
    if not info.get("found"):
        print(f"❌ 未找到涂卡区: {info.get('reason')}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ found choice region")
    print(f"  bbox: {info['bbox']}")
    print(f"  crop bbox (含 margin): {info['crop_bbox']}")
    print(f"  rows: {info['n_rows']}")
    print(f"  questions/row: {info['n_questions_per_row']}")
    print(f"  total questions (估): {info['n_questions']}")
    print(f"  letters detected: {info['n_letters_total']}")
    cropped.save(out)
    print(f"  saved: {out}")


if __name__ == "__main__":
    _main()
