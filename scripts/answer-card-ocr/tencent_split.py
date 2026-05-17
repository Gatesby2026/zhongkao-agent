#!/usr/bin/env python3
"""腾讯云 QuestionSplitLayoutOCR 封装：从答题卡图直接拿每题方框 bbox。

API 文档: https://cloud.tencent.com/document/product/866/124456

凭据存在 ~/.claude/projects/.../memory/api-keys.md。
建议环境变量：
  TENCENT_OCR_SECRET_ID
  TENCENT_OCR_SECRET_KEY
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

try:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.ocr.v20181119 import ocr_client, models
except ImportError:
    print("pip install tencentcloud-sdk-python-ocr", file=sys.stderr); sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("pip install pillow", file=sys.stderr); sys.exit(1)


DEFAULT_SECRET_ID = ""   # 凭据走环境变量 TENCENT_OCR_SECRET_ID
DEFAULT_SECRET_KEY = ""  # 凭据走环境变量 TENCENT_OCR_SECRET_KEY

_client_cache = None


def _get_client(secret_id: str | None = None, secret_key: str | None = None,
                  region: str = "ap-guangzhou"):
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    sid = secret_id or os.environ.get("TENCENT_OCR_SECRET_ID", DEFAULT_SECRET_ID)
    skey = secret_key or os.environ.get("TENCENT_OCR_SECRET_KEY", DEFAULT_SECRET_KEY)
    cred = credential.Credential(sid, skey)
    http_p = HttpProfile(); http_p.endpoint = "ocr.tencentcloudapi.com"
    _client_cache = ocr_client.OcrClient(cred, region,
                                            ClientProfile(httpProfile=http_p))
    return _client_cache


def _img_to_b64(image_path: Path, max_dim: int = 3000,
                  max_bytes: int = 9_000_000) -> tuple[str, tuple[int, int]]:
    """读图转 base64（API ≤ 10MB），返回 (b64, (width, height) 缩放后)。"""
    img = Image.open(image_path)
    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    img = img.convert("RGB")
    for quality in (88, 75, 60):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        if len(buf.getvalue()) <= max_bytes:
            break
    return base64.b64encode(buf.getvalue()).decode(), img.size


def split_question_regions(image_path: Path,
                             use_new_model: bool = True) -> list[dict]:
    """对一张答题卡/试卷图，调腾讯云 QuestionSplitLayoutOCR 拿每题方框 bbox。

    Returns:
        [{"bbox": [x1,y1,x2,y2], "y_center": int,
          "size_returned": (w_returned, h_returned)}, ...]
        按 y_center 升序。bbox 已转回**输入图原始像素坐标**（自动按缩放比补偿）。
    """
    orig_img = Image.open(image_path)
    orig_w, orig_h = orig_img.size

    b64, sent_size = _img_to_b64(image_path)
    sent_w, sent_h = sent_size

    client = _get_client()
    req = models.QuestionSplitLayoutOCRRequest()
    req.ImageBase64 = b64
    req.UseNewModel = use_new_model
    resp = client.QuestionSplitLayoutOCR(req)
    data = json.loads(resp.to_json_string())

    # 缩放比：API 返回的坐标在 sent_size 空间，转回原图
    scale_x = orig_w / sent_w
    scale_y = orig_h / sent_h

    regions = []
    for qinfo in data.get("QuestionInfo", []):
        for item in qinfo.get("ResultList", []):
            for coord in item.get("Coord", []):  # 注意 Coord 是 list
                xs = [coord["LeftTop"]["X"], coord["RightTop"]["X"],
                      coord["RightBottom"]["X"], coord["LeftBottom"]["X"]]
                ys = [coord["LeftTop"]["Y"], coord["RightTop"]["Y"],
                      coord["RightBottom"]["Y"], coord["LeftBottom"]["Y"]]
                x1 = int(min(xs) * scale_x)
                y1 = int(min(ys) * scale_y)
                x2 = int(max(xs) * scale_x)
                y2 = int(max(ys) * scale_y)
                regions.append({
                    "bbox": [x1, y1, x2, y2],
                    "y_center": (y1 + y2) // 2,
                })
    regions.sort(key=lambda r: r["y_center"])
    return regions


def _main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    args = ap.parse_args()
    regions = split_question_regions(args.image)
    print(f"找到 {len(regions)} 个方框:")
    for i, r in enumerate(regions):
        x1, y1, x2, y2 = r["bbox"]
        print(f"  [{i}] bbox=({x1},{y1},{x2},{y2})  {x2-x1}×{y2-y1}px  yc={r['y_center']}")


if __name__ == "__main__":
    _main()
