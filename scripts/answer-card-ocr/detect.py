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


# ============== Path B：纯像素 blob 检测（无 API） ==============
# 选择题填涂区是规则网格。学生涂卡 = 黑色实心矩形 50×30 px、密度 ~50%。
#   1. y 直方图找涂卡行：每行黑像素 100-800（< 100=空白；> 800=印刷 banner/线）
#   2. 每行内 x 直方图找连续黑块（涂卡 blob，宽 20-80）
#   3. blob 中心 x → 反推 qid + 字母（列步长 345、字母步长 70）
# 不依赖 OCR/视觉模型，对 海淀方括号格式 + 朝阳裸字母格式 都准。
# 关丽涵 海淀二模卡 13/13 命中已知真实作答（包括 Q11/12/13/14/15 难判）。
#
# 当前 hardcode 海淀/朝阳布局（5×3 单选 + 1 多选行）；后续可探测自适应。

# 海淀/朝阳标准物理答题卡布局
_LAYOUT_5x3 = {
    "col_step": 345,    # 题间距（Q1→Q2）
    "letter_step": 70,  # 字母间距（A→B）
    "rows": [
        {"qids": [1, 2, 3, 4, 5], "multi": False},
        {"qids": [6, 7, 8, 9, 10], "multi": False},
        {"qids": [11, 12], "multi": False},
        {"qids": [13, 14, 15], "multi": True},
    ],
    "n_pos_per_row": 5,
}


def detect_choices_by_blob(image_paths: list[Path],
                            layout: dict | None = None
                            ) -> dict[int, dict]:
    """纯像素 blob 检测：找黑色填涂块 + 反推字母。

    无 API 调用。对学生涂卡的位置/形状极宽容。

    Returns:
        {qid: {"filled": "B"|"AC"|"", "confidence": 0.95}}
    """
    try:
        import numpy as np  # type: ignore
        from PIL import Image as _Image
        import io as _io
    except ImportError:
        return {}

    layout = layout or _LAYOUT_5x3
    col_step = layout["col_step"]
    letter_step = layout["letter_step"]
    rows_spec = layout["rows"]
    n_pos = layout["n_pos_per_row"]

    img_bytes = _upright_jpeg_bytes(image_paths[0])
    arr = np.array(_Image.open(_io.BytesIO(img_bytes)).convert("L"))
    H, W = arr.shape

    # 步骤 1：扫 y 找涂卡行 band
    SCAN_X1, SCAN_X2 = 300, min(W, 2250)
    Y_START, Y_END = int(H * 0.30), int(H * 0.50)
    bands: list[tuple[int, int]] = []
    in_band = False
    s = 0
    for y in range(Y_START, Y_END):
        n = (arr[y, SCAN_X1:SCAN_X2] < 100).sum()
        is_choice = 100 < n < 800
        if is_choice and not in_band:
            in_band = True
            s = y
        elif not is_choice and in_band:
            in_band = False
            if y - s >= 24:
                bands.append((s, y))
    if in_band and Y_END - s >= 24:
        bands.append((s, Y_END))

    # 期望 4 个 band，对应 layout 的 4 行；少了则跳过
    if len(bands) < len(rows_spec):
        return {}

    # 步骤 2：每行内扫 x 找 blob
    def _row_blobs(y1: int, y2: int) -> list[int]:
        strip = arr[y1:y2, SCAN_X1:SCAN_X2]
        col_black = (strip < 100).sum(axis=0).astype(float)
        smooth = np.convolve(col_black, np.ones(15) / 15, mode="same")
        threshold = (y2 - y1) * 0.5
        out = []
        in_p = False
        start = 0
        for x, v in enumerate(smooth):
            if v >= threshold and not in_p:
                in_p = True
                start = x
            elif v < threshold and in_p:
                in_p = False
                w = x - start
                if 20 <= w <= 80:
                    out.append(start + SCAN_X1 + w // 2)
        return out

    # 步骤 3：用第一行（单选 5 题，最规则）反推 base_x
    row0_y1, row0_y2 = bands[0]
    row0_blobs = sorted(_row_blobs(row0_y1, row0_y2))
    if len(row0_blobs) < 3:
        return {}

    # 反推 base_x：每个 blob 假设是某列某字母 → 候选 = blob - col*345 - letter*70
    # 字母步长 70 是因子，多 blob 反推会聚集到真 base_x 附近 ± 5 px。
    # 用 bin=10 直方图找最高峰（聚类），避开 median 撞到伪峰。
    candidates: list[int] = []
    for bx in row0_blobs:
        for col in range(n_pos):
            for li in range(4):
                bx_candidate = bx - col * col_step - li * letter_step
                if 400 < bx_candidate < 700:
                    candidates.append(bx_candidate)
    if not candidates:
        return {}
    # 投票：每个候选给 ±10 px 邻域 +1
    BIN = 5
    hist: dict[int, int] = {}
    for c in candidates:
        for off in range(-15, 16, 1):
            hist[(c + off) // BIN] = hist.get((c + off) // BIN, 0) + 1
    best_bin = max(hist, key=hist.get)
    base_x = best_bin * BIN
    # 用基准 ± 25 内的候选取均值精炼
    refined = [c for c in candidates if abs(c - base_x) < 25]
    if refined:
        base_x = int(round(sum(refined) / len(refined)))

    # 步骤 4：每行按 base_x 反推 blob → (qi, letter)
    def _blob_to_letter(cx: int) -> tuple[int, str] | None:
        for qi in range(n_pos):
            qx = base_x + qi * col_step
            for li, L in enumerate("ABCD"):
                lx = qx + li * letter_step
                if abs(cx - lx) <= 18:
                    return qi, L
        return None

    out: dict[int, dict] = {}
    for ri, row in enumerate(rows_spec):
        if ri >= len(bands):
            continue
        y1, y2 = bands[ri]
        qids = row["qids"]
        blobs = _row_blobs(y1, y2)
        by_q: dict[int, list[str]] = {q: [] for q in qids}
        for cx in blobs:
            r = _blob_to_letter(cx)
            if r is None:
                continue
            qi, L = r
            if qi < len(qids):
                by_q[qids[qi]].append(L)
        for qid in qids:
            letters = sorted(set(by_q[qid]))
            filled = "".join(letters)
            if filled:
                # 单选 vs 多选根据 row.multi
                conf = 0.95 if not row["multi"] else 0.92
            else:
                conf = 0.4
            out[qid] = {"filled": filled, "confidence": conf}
    return out


# ============== Path A：vl-max 给 bbox + 本地像素密度 ==============
# 缺字母法/vl-max 都依赖模型"读字母"，海淀方括号格式上模型把涂黑当 token
# 噪声补全 → 假报 ABCD。Path A 让 vl-max 只**定位**每个 [X] 方框的 bbox
# （这是模型擅长的视觉接地任务），然后本地 numpy 算每个 bbox 内黑像素占
# 比 — 涂卡 ≈ 0.1+，未涂 ≈ 0。完全脱离模型对字母 token 的先验。

_BBOX_PROMPT = """这是答题卡选择题填涂区照片。请逐题返回每个选项方框 [A] [B] [C] [D]
的**像素坐标 bbox**（左上原点 0,0；右下 W,H；整数像素）。

输出严格 JSON（不要 markdown）：
{{
  "image_width": <实际图宽 px>,
  "image_height": <实际图高 px>,
  "questions": [
    {{"qid": 1, "cells": {{"A":[x1,y1,x2,y2], "B":[..], "C":[..], "D":[..]}}}}
  ]
}}

约束：
- 只看选择题区，跳过表头/姓名/主观题
- cells 是该字母方框 [X] 的精确像素矩形（含方括号字符的完整矩形）
- 即使该格被学生涂黑，也返回原方框 bbox（位置由其他未涂格推断）
- qid 严格按答题卡印刷数字
- 只输出 Q{qmin}-Q{qmax}"""


def _read_bboxes_vlmax(image_path: Path, qid_range: tuple[int, int],
                        model: str = "qwen-vl-max") -> dict:
    """qwen-vl-max 接地：返回 {qid: {letter: bbox}} + 模型坐标系尺寸。"""
    client = _client()
    img_bytes = _upright_jpeg_bytes(image_path)
    b64 = base64.b64encode(img_bytes).decode()
    content = [
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text",
         "text": _BBOX_PROMPT.format(qmin=qid_range[0], qmax=qid_range[1])},
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=0.0, max_tokens=4096,
        response_format={"type": "json_object"}, timeout=120,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    return json.loads(raw)


def detect_choices_by_density(image_paths: list[Path],
                               qid_range: tuple[int, int]
                               ) -> dict[int, dict]:
    """Path A 主流程：vl-max 找 bbox + 本地像素密度判涂卡。

    Returns:
        {qid: {"filled": "B" | "AC" | "", "confidence": 0..1,
               "densities": {"A":0.18, "B":0.0, ...}}}
    """
    try:
        import numpy as np  # type: ignore
        from PIL import Image as _Image
        import io as _io
    except ImportError:
        print("  ⚠️ Path A 缺 numpy/PIL，跳过", file=sys.stderr)
        return {}

    # 选择题区一般在 page-01；多 page 时也只看 page-01
    page = image_paths[0]
    try:
        data = _read_bboxes_vlmax(page, qid_range)
    except Exception as e:
        print(f"  ⚠️ Path A bbox 接地失败: {e}", file=sys.stderr)
        return {}

    img_bytes = _upright_jpeg_bytes(page)
    im = _Image.open(_io.BytesIO(img_bytes)).convert("L")
    arr = np.array(im)
    H, W = arr.shape

    # 模型坐标系可能 ≠ 实图尺寸（qwen 常自标 950x1280），按比例缩放
    mw = data.get("image_width") or W
    mh = data.get("image_height") or H
    sx, sy = W / float(mw), H / float(mh)

    def _density(bbox, inner=0.85) -> float:
        if not bbox or len(bbox) != 4:
            return 0.0
        x1, y1, x2, y2 = [c * (sx if i % 2 == 0 else sy)
                          for i, c in enumerate(bbox)]
        x1, x2 = max(0, int(x1)), max(0, int(x2))
        y1, y2 = max(0, int(y1)), max(0, int(y2))
        if x2 <= x1 or y2 <= y1:
            return 0.0
        w, h = x2 - x1, y2 - y1
        mx = int(w * (1 - inner) / 2)
        my = int(h * (1 - inner) / 2)
        region = arr[y1 + my:y2 - my, x1 + mx:x2 - mx]
        if region.size == 0:
            return 0.0
        return float((region < 100).sum()) / region.size

    out: dict[int, dict] = {}
    for q in (data.get("questions") or []):
        try:
            qid = int(q.get("qid") or 0)
        except (TypeError, ValueError):
            continue
        if qid < qid_range[0] or qid > qid_range[1]:
            continue
        cells = q.get("cells") or {}
        ds = {L: _density(cells.get(L)) for L in ("A", "B", "C", "D")
              if cells.get(L)}
        if not ds:
            continue
        sorted_ds = sorted(ds.items(), key=lambda x: -x[1])
        max_d = sorted_ds[0][1]
        second_d = sorted_ds[1][1] if len(sorted_ds) > 1 else 0.0
        min_d = sorted_ds[-1][1]
        # spread = max-min；spread 小说明 bbox 落到文本噪声区（4 cell
        # 同色），不可信，标 no_answer 让上层 fallback
        spread = max_d - min_d

        # 判定（阈值经 关丽涵 / 朝阳 卡校准）：
        # - spread < 0.02 ：4 cell 密度雷同 → bbox 落噪声区，弃用
        # - max < 0.02 ：信号弱 → no_answer
        # - max/second > 2.5 且 max >= 0.03 ：单选（取 top）
        # - 否则若多个 cell >= max*0.55 且 >= 0.04 且 max >= 0.06 ：多选
        # - 兜底：max 最大那个
        if spread < 0.02:
            filled = ""
            conf = 0.3
        elif max_d < 0.02:
            filled = ""
            conf = 0.4
        else:
            ratio = max_d / max(second_d, 0.001)
            if ratio >= 2.5 and max_d >= 0.03:
                filled = sorted_ds[0][0]
                conf = 0.9
            else:
                # 多选候选：要求 max >= 0.06 才允许多选，避免噪声放大成 ABCD
                multi = [L for L, d in sorted_ds
                         if d >= max(max_d * 0.55, 0.04)]
                if len(multi) >= 2 and len(multi) <= 3 and max_d >= 0.06:
                    filled = "".join(sorted(multi))
                    conf = 0.75
                elif max_d >= 0.04:
                    filled = sorted_ds[0][0]
                    conf = 0.7
                else:
                    filled = ""
                    conf = 0.4

        out[qid] = {"filled": filled, "confidence": conf,
                    "densities": {L: round(d, 3) for L, d in ds.items()}}
    return out


# ============== Phase A 主路径：整页 vl-max 直接看图给答案 ==============
# 缺字母法只在「学生规范涂黑 + 题号印 `1. A B C D`」时稳定。海淀等区用
# 方括号 `1.[A][B][C][D]` + 学生用划线/勾选，缺字母法 0% 命中。
# vl-max 看图判定不依赖作答方式 / 题号印刷格式，跨区稳定。

_VLMAX_CHOICE_PROMPT = """这是一名学生中考答题卡的照片（可能多张，选择题
填涂区通常在第一张）。请逐题识别**学生实际作答**的字母。

候选题号：{qid_range}（按答题卡上印刷的题号顺序）
选项：A B C D（部分题为多选，可能选 2-4 个字母）

判定规则：
- 任何形式的作答标记都算"已选"：涂黑、打勾√、打叉×、划线、方框、圈选 …
- 多个标记时取**最显著、最完整**的那个
- 完全没有任何标记 → filled=""
- 题号必须从题目板**抄读**，宁可漏一题也不要题号错位
- 多选题选了多个字母 → 字母按 A→D 顺序拼接，如 "ABD"
- 单选题学生涂了 2 个 → 仍按多选 "AB"（评分时按 0 分处理）

严格输出 JSON（不要 markdown 围栏，不要解释）：
{{
  "answers": [
    {{"qid": 1, "filled": "C", "confidence": 0.95}},
    {{"qid": 2, "filled": "AB", "confidence": 0.9}},
    {{"qid": 13, "filled": "", "confidence": 0.5}}
  ]
}}

confidence 给 0-1 之间的数值，自评对识别结果的信心。"""


def read_choices_vlmax(image_paths: list[Path],
                       qid_range: tuple[int, int],
                       model: str = "qwen-vl-max",
                       max_imgs: int = 6) -> dict[int, dict]:
    """整页 vl-max 看图判定每题学生作答。

    Args:
        qid_range: (min_qid, max_qid)，如 (1, 15)
    Returns:
        {qid: {"filled": "C"|"AB"|"", "confidence": 0.95}}
    """
    client = _client()
    content = []
    for p in image_paths[:max_imgs]:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,"
                          f"{base64.b64encode(_upright_jpeg_bytes(p)).decode()}"},
        })
    content.append({
        "type": "text",
        "text": _VLMAX_CHOICE_PROMPT.format(
            qid_range=f"Q{qid_range[0]}-Q{qid_range[1]}"),
    })
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=0.0, max_tokens=2048,
        response_format={"type": "json_object"}, timeout=120,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    out: dict[int, dict] = {}
    for it in (data.get("answers") or []):
        if not isinstance(it, dict):
            continue
        try:
            qid = int(it.get("qid") or it.get("qId") or 0)
        except (TypeError, ValueError):
            continue
        if qid < qid_range[0] or qid > qid_range[1]:
            continue
        filled = str(it.get("filled") or "").strip().upper()
        # 只保留 ABCDE
        filled = "".join(c for c in filled if c in "ABCDE")
        try:
            conf = float(it.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        out[qid] = {"filled": filled, "confidence": round(conf, 2)}
    return out


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
    r"(\d{1,3})\s*[.．、]\s*"
    r"((?:\[\s*\]\s*)*\[?\s*[A-E]\s*\]?"
    r"(?:\s*(?:\[\s*\]\s*)*\[?\s*[A-E]\s*\]?){0,4}"
    r"(?:\s*\[\s*\])*)"
)


def parse_choices(lines: list[str]) -> dict[int, str]:
    """从 OCR 行里抽 题号 → OCR 看到的字母序列。

    支持两种格式：
      "1. A B C D"（常规）
      "1.[A][B][C][D]" / "1. [A] [B] [C] [D]"（海淀方括号格式）
    """
    results: dict[int, str] = {}
    text = " ".join(lines)
    for m in QUESTION_PATTERN.finditer(text):
        qid = int(m.group(1))
        # 去掉方括号、空白
        letters = re.sub(r"[\s\[\]]+", "", m.group(2))
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

    # Phase A 策略：**缺字母法为主**（朝阳一模实测 59 分准），vl-max 仅在
    # 缺字母法对该题完全没识别到时启用兜底（海淀二模方括号格式即使加了
    # bracket 适配仍可能漏题）。**绝不让 vl-max 覆盖缺字母法的结果** —
    # 早期"vl-max 主路径"实验在朝阳卡上回归 -15 分。
    choices_map = parse_choices(all_lines)
    if subjective_qnums:
        max_choice_qid = max(min(subjective_qnums) - 1, 15)
    else:
        max_choice_qid = 30

    # ============== Phase A0：Path B 纯像素 blob（首选，零 API） ==============
    # 关丽涵 海淀二模卡 13/13 真值命中，零 API 调用，几毫秒。
    blob_choices: dict[int, dict] = {}
    try:
        print(f"\n  🎯 Path B: 纯像素 blob 检测（零 API）…", file=sys.stderr)
        blob_choices = detect_choices_by_blob(image_paths)
        if blob_choices:
            real = sum(1 for v in blob_choices.values() if v.get("filled"))
            print(f"     Path B 识别 {real}/{len(blob_choices)} 题: " +
                  ", ".join(f"Q{q}={blob_choices[q].get('filled')!r}"
                            for q in sorted(blob_choices)),
                  file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️ Path B 失败: {e}", file=sys.stderr)

    # ============== Phase A1：Path A 像素密度（次选，vl-max bbox） ==============
    density_choices: dict[int, dict] = {}
    if not blob_choices or sum(1 for v in blob_choices.values()
                                 if v.get("filled")) < 10:
        try:
            print(f"\n  📐 Path A: vl-max bbox 接地 + 本地像素密度（兜底）…",
                  file=sys.stderr)
            density_choices = detect_choices_by_density(image_paths, (1, 15))
            if density_choices:
                real = sum(1 for v in density_choices.values() if v.get("filled"))
                print(f"     Path A 识别 {real}/{len(density_choices)} 题",
                      file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️ Path A 失败: {e}", file=sys.stderr)

    # 先把缺字母法的结果推断出来，分两类：
    #   real_hits = 真识别到涂卡（filled 非空，即 choice/multi_choice）
    #   no_answer = OCR 看到全 ABCD（涂黑后字母仍可读 / 学生没涂）
    # 海淀方括号格式典型坑：涂黑后 [B] 仍被 OCR 读出 → 全 4 字母 → no_answer
    # 这种 qid 不算"已知"，需要 vl-max 兜底。
    pre_inf: dict[int, dict] = {}
    real_hits: set[int] = set()
    for qid, seen in choices_map.items():
        if not (1 <= qid <= max_choice_qid):
            continue
        inf = infer_filled(seen, options)
        pre_inf[qid] = inf
        if inf["filled"] and inf["type"] in ("choice", "multi_choice"):
            real_hits.add(qid)

    vlmax_choices: dict[int, dict] = {}
    if len(real_hits) < max_choice_qid * 0.8:
        try:
            print(f"\n  🔎 缺字母法真识别 {len(real_hits)}/{max_choice_qid} 题"
                  f"（其余 OCR 看到全 ABCD），启用 vl-max 兜底…",
                  file=sys.stderr)
            vlmax_choices = read_choices_vlmax(image_paths, (1, max_choice_qid))
            print(f"     vl-max 识别 {len(vlmax_choices)} 题: " + ", ".join(
                f"Q{q}={vlmax_choices[q].get('filled')!r}"
                for q in sorted(vlmax_choices)),
                file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️ vl-max 选择题识别失败: {e}", file=sys.stderr)
    else:
        print(f"\n  ✓ 缺字母法真识别 {len(real_hits)}/{max_choice_qid} 题，跳过 vl-max",
              file=sys.stderr)

    # 合并优先级（v3）：
    #   0. Path B 纯像素 blob（13/13 真值 + 零 API + 几毫秒）—— 首选
    #   1. 缺字母法 real_hits（OCR 真看到缺字母，朝阳格式 99% 准）
    #   2. Path A 强信号（vl-max bbox + 像素，conf >= 0.85）
    #   3. Path A 弱信号
    #   4. vl-max 选择识别
    #   5. 缺字母法 no_answer 兜底
    merged_qids = (set(blob_choices.keys()) | set(density_choices.keys())
                   | set(choices_map.keys()) | set(vlmax_choices.keys()))
    answers = []
    for qid in sorted(merged_qids):
        seen = choices_map.get(qid, "")
        bm = blob_choices.get(qid) or {}
        bfilled = bm.get("filled") or ""
        bconf = bm.get("confidence", 0.0)
        dm = density_choices.get(qid) or {}
        dfilled = dm.get("filled") or ""
        dconf = dm.get("confidence", 0.0)
        source = ""

        if bfilled and bconf >= 0.9:
            filled_val: str | list[str] = (list(bfilled) if len(bfilled) > 1
                                            else bfilled)
            atype = "multi_choice" if len(bfilled) > 1 else "choice"
            conf = bconf
            source = "blob"
        elif qid in real_hits:
            inf = pre_inf[qid]
            filled = inf["filled"]
            if inf["type"] == "choice":
                filled_val: str | list[str] = filled[0] if filled else ""
            else:
                filled_val = filled
            atype = "multi_choice" if inf["type"] == "multi_choice" else "choice"
            conf = inf["confidence"]
            source = "缺字母"
        elif dfilled and dconf >= 0.85:
            # Path A 强信号（缺字母法 no_answer/缺位的题号）
            filled_val = list(dfilled) if len(dfilled) > 1 else dfilled
            atype = "multi_choice" if len(dfilled) > 1 else "choice"
            conf = dconf
            source = "density"
        elif dfilled:
            # Path A 弱信号
            filled_val = list(dfilled) if len(dfilled) > 1 else dfilled
            atype = "multi_choice" if len(dfilled) > 1 else "choice"
            conf = dconf
            source = "density-weak"
        else:
            vlm = vlmax_choices.get(qid) or {}
            vfilled = vlm.get("filled") or []
            if vfilled:
                filled_val = list(vfilled) if len(vfilled) > 1 else vfilled[0]
                atype = "multi_choice" if len(vfilled) > 1 else "choice"
                conf = vlm.get("confidence", 0.85)
                source = "vl-max"
            elif vlm:
                filled_val = []
                atype = "choice"
                conf = vlm.get("confidence", 0.5)
                source = "vl-max-empty"
            else:
                inf = pre_inf.get(qid) or infer_filled(seen, options)
                filled = inf["filled"]
                filled_val = (filled[0] if filled else "") if inf["type"] == "choice" else filled
                atype = "multi_choice" if inf["type"] == "multi_choice" else "choice"
                conf = inf["confidence"]
                source = "no_answer"
        answers.append({
            "qId": f"Q{qid}",
            "type": atype,
            "filled": filled_val,
            "confidence": conf,
            "ocrSeen": seen,
            "source": source,
        })

    # Phase A 识别到的选择题 qids（用于报告 missing 追踪）
    # 双引擎下：以 vl-max ∪ 缺字母法的并集为准
    choice_qids_parsed = sorted(set(choices_map.keys())
                                 | set(vlmax_choices.keys())
                                 | set(density_choices.keys())
                                 | set(blob_choices.keys()))
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

                # 兜底：腾讯云方框 + 严格 fallback 命中率 < 50% → 整页 vl-max
                # 看剩余题（不依赖框检测/印刷题号 OCR，跨区稳定）
                cropped_n = len(subjective_qids_cropped)
                need = len(subjective_qnums)
                if need >= 3 and cropped_n / need < 0.5:
                    missing_qids = sorted(
                        set(subjective_qnums) - set(subjective_qids_cropped))
                    miss_qs = [paper[q] for q in missing_qids if q in paper]
                    print(f"\n  🛟 Phase B 兜底：整页 vl-max 看 {len(miss_qs)} 道"
                          f"未识别主观题（cropped {cropped_n}/{need}）...",
                          file=sys.stderr)
                    try:
                        from subjective_grade import batch_grade_full_pages
                        fb = batch_grade_full_pages(image_paths, miss_qs)
                        for q, g in fb.items():
                            if q not in grade_b_results and g:
                                grade_b_results[q] = g
                                if q not in subjective_qids_cropped:
                                    subjective_qids_cropped.append(q)
                                sug = g.get('suggestedScore')
                                print(f"    Q{q}(兜底): 建议 {sug} 分",
                                      file=sys.stderr)
                        subjective_qids_cropped = sorted(set(subjective_qids_cropped))
                    except Exception as e:
                        print(f"  ⚠️ vl-max 整页兜底失败: {e}",
                              file=sys.stderr)
                        import traceback; traceback.print_exc(file=sys.stderr)

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
