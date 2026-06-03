#!/usr/bin/env python3
"""选择题填涂识别 — 纯 DashScope（qwen-vl-max）两段式，零腾讯依赖。

为什么两段式：
  - 整页直送 qwen-vl-max 只有 3/8（选择题区在大图里太小，模型看不清）
  - 紧致裁切后直送 = 8/8（朝阳数学实测）→ **裁切是关键**
  - 但精确裁切原来靠腾讯 OCR 字母 bbox（月度免费包会耗尽、+RMB/次）

  本模块用 qwen-vl-max **读标题行锚点** 来定位（模型读印刷标题行很稳，
  远比 region-bbox grounding 可靠）：
    Stage 1 (locate)：返回「选择题」标题行 y 和其正下方下一区域标题行 y
    Stage 2 (read)  ：裁两行之间的 band，逐题判实心涂黑，按印刷题号输出

环境变量：DASHSCOPE_API_KEY
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path

from PIL import Image, ImageOps

_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_MODEL = "qwen-vl-max"

_LOCATE_PROMPT = """返回这张答题卡上两条横向标题行的纵向位置（归一化 0-1000，图顶=0）：
- top: 「选择题」标题行的 y
- bottom: 选择题区正下方下一个区域（如「填空题」/「二、…」或第一道非选择大题）标题行的 y
若整页没有选择题区，两个都返回 -1。
严格 JSON（无解释、无 markdown）：{"top": 123, "bottom": 456}"""

_READ_PROMPT = """这是一张答题卡「选择题」填涂区的裁切图。每题前印有题号（如 1. 2.）。
逐题判断：[A][B][C][D] 四个方框里，哪个被学生用黑色**实心涂满**（涂黑的实心块才是作答；仅有印刷字母、未涂黑的不算）。
绝大多数是单选，只涂一个字母；只有确实涂了多个才输出多个（如物理多选题）。
按印刷题号输出。严格 JSON（无解释、无 markdown 围栏）：
{"answers": {"Q1": "A", "Q2": "C"}}"""


def _client():
    import openai
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY")
    return openai.OpenAI(api_key=api_key, base_url=_BASE_URL)


def _call(client, im: Image.Image, prompt: str, max_tokens: int = 1024) -> dict:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    b64 = base64.b64encode(buf.getvalue()).decode()
    resp = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]}],
        temperature=0.0, max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    return json.loads(raw)


def _load_upright(image_path: Path) -> Image.Image:
    im = Image.open(image_path)
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def locate_choice_band(client, im: Image.Image,
                       top_margin: int = 20) -> tuple[int, int] | None:
    """Stage 1：用标题行锚点定位选择题 band 的 y 范围（像素）。

    返回 (band_y1, band_y2) 或 None（无选择题区）。
    band_y1 = 选择题标题行 y + top_margin（跳过标题文字本身）。
    """
    W, H = im.size
    loc = _call(client, im, _LOCATE_PROMPT, max_tokens=128)
    top = loc.get("top", -1)
    bottom = loc.get("bottom", -1)
    if top is None or bottom is None or top < 0 or bottom < 0:
        return None
    t = int(top / 1000 * H)
    b = int(bottom / 1000 * H)
    if b <= t:
        return None
    y1 = max(0, min(H - 1, t + top_margin))
    y2 = max(y1 + 1, min(H, b))
    return y1, y2


def read_choice_band(client, band: Image.Image,
                     upscale: int = 2) -> dict[int, str]:
    """Stage 2：读裁切 band 的每题填涂，按印刷题号返回 {qid: 字母}。"""
    if upscale > 1:
        band = band.resize((band.width * upscale, band.height * upscale),
                            Image.LANCZOS)
    data = _call(client, band, _READ_PROMPT)
    ans = data.get("answers") or {}
    out: dict[int, str] = {}
    for k, v in ans.items():
        s = str(k).strip().upper().lstrip("Q")
        if s.isdigit():
            out[int(s)] = str(v).strip().upper()
    return out


def _precise_band(image_path: Path) -> Image.Image | None:
    """用腾讯 OCR 字母 bbox 精确裁紧致 band（crop_choice_band）。

    实测唯一可靠的 locate：qwen 空间输出（region grounding / 标题行锚点）
    都不稳（同图同 prompt y 会从 512 跳到 757，锚到填空区）；qwen-vl-ocr
    只回文本无坐标。腾讯字母 bbox 是精确坐标 → 紧致 band → read 8/8。
    腾讯月度免费包耗尽时返回 None，调用方降级粗裁。
    """
    try:
        sys_dir = str(Path(__file__).resolve().parent)
        import sys
        if sys_dir not in sys.path:
            sys.path.insert(0, sys_dir)
        from choice_region_locate import crop_choice_band
        cropped, info = crop_choice_band(image_path)
        if cropped is not None and info.get("found"):
            return cropped
    except Exception:
        pass
    return None


def detect_choices_vlm(image_path: Path,
                       upscale: int = 2) -> dict[int, str]:
    """主入口：定位 → 裁切 → 读。

    locate 优先级：
      1. **腾讯字母 bbox 精确裁**（crop_choice_band）→ 紧致 band，read 实测 8/8
      2. 降级 **粗裁上半区**（选择题恒在 header 之后）。固定比例无方差但偏松，
         实测全 bench ~39%。腾讯额度耗尽 / 无 key 时走这条。
    read 始终用单选约束 prompt + upscale。
    """
    client = _client()
    band = _precise_band(image_path)
    if band is None:
        im = _load_upright(image_path)
        W, H = im.size
        band = im.crop((0, int(0.25 * H), W, int(0.55 * H)))
    return read_choice_band(client, band, upscale=upscale)


def _main():
    import sys
    if len(sys.argv) < 2:
        print("用法: python3 vlm_choice.py <image.jpg>", file=sys.stderr)
        sys.exit(1)
    res = detect_choices_vlm(Path(sys.argv[1]))
    for qid in sorted(res):
        print(f"Q{qid}: {res[qid]}")


if __name__ == "__main__":
    _main()
