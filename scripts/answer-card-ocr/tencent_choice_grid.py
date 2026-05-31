#!/usr/bin/env python3
"""腾讯 GeneralAccurateOCR 找答题卡选择题填涂区 bbox grid。

思路：
  1. 腾讯 GeneralAccurateOCR 跑 page-01，拿所有文字 + bbox
  2. 找所有 [A] / [B] / [C] / [D] 字符位置（含方括号、不含、
     "A " / "B"  各种变体）
  3. 按 y 聚类成行，按 x 聚类成列
  4. 输出每个 (qid, letter) 对应的精确 bbox
  5. 后续 Path B 在 bbox 内做像素密度检测

环境变量：
  TENCENT_OCR_SECRET_ID
  TENCENT_OCR_SECRET_KEY
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
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


_client_cache = None


def _get_client(region: str = "ap-guangzhou"):
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    sid = os.environ.get("TENCENT_OCR_SECRET_ID")
    skey = os.environ.get("TENCENT_OCR_SECRET_KEY")
    if not sid or not skey:
        raise RuntimeError("缺 TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY")
    cred = credential.Credential(sid, skey)
    http_p = HttpProfile(); http_p.endpoint = "ocr.tencentcloudapi.com"
    _client_cache = ocr_client.OcrClient(cred, region,
                                          ClientProfile(httpProfile=http_p))
    return _client_cache


def _img_to_b64(image_path: Path, max_dim: int = 3000) -> str:
    """读图 + EXIF 转正 + 缩到 max_dim 内 + base64 编码。"""
    from PIL import ImageOps
    im = Image.open(image_path)
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > max_dim:
        s = max_dim / max(w, h)
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


# 匹配含 A/B/C/D 字符的 token。腾讯会把临近字符合并：
#   "[A]" / "[B][C][D]" / "6.[A]" / "8.[A][B][C]" / "A" / "ABCD"
# 需要从 token 文本里提取每个 letter，并按比例分 bbox 宽度。
_LETTER_CHAR_RE = re.compile(r"[A-D]")


def _split_compound_token(text: str, x1: int, y1: int,
                            x2: int, y2: int) -> list[dict]:
    """合并 token → 按字母位置等比例拆 bbox。

    例：'8.[A][B][C]' 宽 163 → 4 字符 letter 'A','B','C'
       位置按其在 text 中的字符 index 占比 + token 长度
    """
    letters = []
    width = x2 - x1
    text_len = len(text)
    if text_len == 0:
        return []
    for m in _LETTER_CHAR_RE.finditer(text):
        ch_idx = m.start()
        # 估算字符 bbox：占 1 / text_len 宽度
        lx1 = x1 + int(width * ch_idx / text_len)
        lx2 = x1 + int(width * (ch_idx + 1) / text_len)
        letters.append({
            "letter": m.group(0),
            "x1": lx1, "y1": y1,
            "x2": lx2, "y2": y2,
            "cx": (lx1 + lx2) // 2,
            "cy": (y1 + y2) // 2,
            "text": text,
        })
    return letters


def _ocr_letters(image_path: Path) -> list[dict]:
    """调腾讯 GeneralAccurateOCR，过滤出 A/B/C/D 字符 token。

    返回 [{"letter": "A", "x1": ..., "y1": ..., "x2": ..., "y2": ..., ...}, ...]
    """
    client = _get_client()
    req = models.GeneralAccurateOCRRequest()
    req.ImageBase64 = _img_to_b64(image_path)
    resp = client.GeneralAccurateOCR(req)

    letters = []
    for det in resp.TextDetections:
        text = (det.DetectedText or "").strip()
        # 只看含 A/B/C/D 的 token（排除答题/作答等中文）
        if not _LETTER_CHAR_RE.search(text):
            continue
        # 排除长 token（答题内容 token 通常含 = ∵ ∴ 等数学符号或超过 8 个字符）
        if len(text) > 16 or any(c in text for c in "=∵∴∠△⌐≠≡"):
            continue
        poly = det.ItemPolygon
        x1, y1 = poly.X, poly.Y
        x2, y2 = poly.X + poly.Width, poly.Y + poly.Height
        letters.extend(_split_compound_token(text, x1, y1, x2, y2))
    return letters


def _cluster_rows(letters: list[dict], y_tol: int = 25) -> list[list[dict]]:
    """按 y 坐标聚类成行。同行 cy 差 <= y_tol。"""
    if not letters:
        return []
    sorted_by_y = sorted(letters, key=lambda L: L["cy"])
    rows = []
    cur = [sorted_by_y[0]]
    for L in sorted_by_y[1:]:
        if abs(L["cy"] - cur[-1]["cy"]) <= y_tol:
            cur.append(L)
        else:
            rows.append(cur)
            cur = [L]
    rows.append(cur)
    # 每行按 x 排序
    for r in rows:
        r.sort(key=lambda L: L["cx"])
    return rows


def _filter_choice_rows(rows: list[list[dict]],
                         min_letters_per_row: int = 4) -> list[list[dict]]:
    """筛出"涂卡候选行" — 含至少 min_letters_per_row 个 A/B/C/D 的行。"""
    good = []
    for r in rows:
        # 同行内同字母多次出现 = 多道题（如 4 题/行 = AAAABBBBCCCCDDDD）
        if len(r) >= min_letters_per_row:
            # 排除全是同字母的行（误检）
            distinct = set(L["letter"] for L in r)
            if len(distinct) >= 2:
                good.append(r)
    return good


def _group_questions(row: list[dict],
                      max_intra_q_gap: int = 200) -> list[list[dict]]:
    """一行内按 x-间距分组成问题（不依赖字母连贯，因为涂黑的字母 OCR 读不到）。

    同题字母 cx 间距 < max_intra_q_gap（如 200 px）→ 同题。
    > max_intra_q_gap → 下一题。
    """
    if not row:
        return []
    groups = []
    cur = [row[0]]
    for L in row[1:]:
        gap = L["cx"] - cur[-1]["cx"]
        if gap <= max_intra_q_gap:
            cur.append(L)
        else:
            groups.append(cur)
            cur = [L]
    groups.append(cur)
    return groups


def infer_filled_from_missing(question_letters: list[dict]) -> str:
    """从 OCR 看到的字母推断"被涂的字母"（缺字母法）。

    标准选择题 4 选项 = {A, B, C, D}。OCR 看到的 = 没涂的。
    没看到的 = 涂了的。
    """
    seen = set(L["letter"] for L in question_letters)
    missing = sorted(set("ABCD") - seen)
    return "".join(missing)


def locate_choice_grid(image_path: Path) -> dict:
    """主入口：返回 layout 信息 + 每 (题号, 字母) 的 bbox。

    Returns:
        {
            "n_rows": int,
            "n_questions_per_row": int,
            "n_questions": int,
            "cells": {qid_int: {letter: (x1, y1, x2, y2)}},
            "image_size": (W, H),
        }
    """
    letters = _ocr_letters(image_path)
    if not letters:
        return {"n_rows": 0, "n_questions": 0, "cells": {}}

    rows = _cluster_rows(letters)
    choice_rows = _filter_choice_rows(rows)

    cells: dict[int, dict[str, tuple]] = {}
    filled: dict[int, str] = {}
    qid = 1
    for r in choice_rows:
        qs = _group_questions(r)
        for q_group in qs:
            cells[qid] = {
                L["letter"]: (L["x1"], L["y1"], L["x2"], L["y2"])
                for L in q_group
            }
            filled[qid] = infer_filled_from_missing(q_group)
            qid += 1

    # 拿图像尺寸
    im = Image.open(image_path)
    W, H = im.size

    return {
        "n_rows": len(choice_rows),
        "n_questions_per_row": (max(len(_group_questions(r))
                                     for r in choice_rows) if choice_rows else 0),
        "n_questions": qid - 1,
        "cells": cells,
        "filled": filled,   # 缺字母法推断的涂卡（按字典序拼接）
        "image_size": (W, H),
        "raw_letter_count": len(letters),
    }


def _main():
    if len(sys.argv) < 2:
        print("用法: python3 tencent_choice_grid.py <image.jpg>", file=sys.stderr)
        sys.exit(1)
    p = Path(sys.argv[1])
    r = locate_choice_grid(p)
    print(f"raw letters detected: {r.get('raw_letter_count', 0)}")
    print(f"choice rows: {r['n_rows']}")
    print(f"questions per row: {r.get('n_questions_per_row')}")
    print(f"total questions: {r['n_questions']}")
    print()
    print(f"\n=== 缺字母法推断（涂的字母）===")
    for qid in sorted(r["filled"]):
        f = r["filled"][qid]
        seen = sorted(r["cells"][qid].keys())
        print(f"Q{qid}: 涂={f:5s}  OCR 看到={','.join(seen)}")


if __name__ == "__main__":
    _main()
