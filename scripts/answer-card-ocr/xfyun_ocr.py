#!/usr/bin/env python3
"""科大讯飞 OCR API 封装。

两个 service：
  - 手写文字识别 (v1 接口，APPID + APIKey)
    https://www.xfyun.cn/services/wordRecg
  - 公式识别 (v2 接口，APPID + APIKey + APISecret，HMAC-SHA256 签名)
    https://www.xfyun.cn/services/formula-discern

凭据在 ~/.claude/projects/.../memory/api-keys.md
建议存到环境变量：
  XFYUN_HANDWRITING_APPID
  XFYUN_HANDWRITING_APIKEY
  XFYUN_FORMULA_APPID
  XFYUN_FORMULA_APIKEY
  XFYUN_FORMULA_APISECRET
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr); sys.exit(1)

try:
    from PIL import Image
    import io
except ImportError:
    Image = None
    io = None


def _read_image_bytes(image_path: Path, max_dim: int = 1500,
                       max_bytes: int = 500_000) -> bytes:
    """读图，必要时缩小到 max_dim 边长 & max_bytes 大小（讯飞 ≤ 4096px、≤4MB）。"""
    raw = image_path.read_bytes()
    if Image is None:
        return raw
    img = Image.open(image_path)
    w, h = img.size
    if max(w, h) <= max_dim and len(raw) <= max_bytes:
        return raw
    # 缩小 + JPEG（PNG 大、上传慢、易 SSL 中断；质量降到符合 max_bytes）
    ratio = min(max_dim / max(w, h), 1.0)
    new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
    img = img.resize(new_size, Image.LANCZOS).convert("RGB")
    for quality in (85, 70, 55, 40):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        if len(buf.getvalue()) <= max_bytes:
            return buf.getvalue()
    return buf.getvalue()  # 最后一次结果（即使超 max_bytes）


# 默认凭据（fallback；优先用环境变量）
DEFAULT_HW = {
    "appid": "e4be15ac",
    "apikey": "93cde30cc742b97de5f1d68732e05962",
}
DEFAULT_FORMULA = {
    "appid": "e4be15ac",
    "apikey": "959d3d6cc35b9fc88d9f6454dab9b9a9",
    "apisecret": "OTU0NGM2Yjk0Y2E3MjZjMmNlMDNjMTZj",
}


# ─── 手写文字识别（v1 接口）────────────────────────────────────────────────

def recognize_handwriting(image_path: Path, language: str = "cn|en",
                            *, appid: str | None = None,
                            apikey: str | None = None) -> dict:
    """调讯飞手写文字识别 API。

    Returns:
        {"text": str, "confidence_avg": float, "raw": dict}
        text 为按行拼接的识别文本；raw 为完整响应。
        失败时 raise RuntimeError。
    """
    appid = appid or os.environ.get("XFYUN_HANDWRITING_APPID", DEFAULT_HW["appid"])
    apikey = apikey or os.environ.get("XFYUN_HANDWRITING_APIKEY", DEFAULT_HW["apikey"])

    url = "https://webapi.xfyun.cn/v1/service/v1/ocr/handwriting"
    param_dict = {"language": language, "location": "false"}
    x_param = base64.b64encode(json.dumps(param_dict).encode()).decode()
    x_cur_time = str(int(time.time()))
    x_checksum = hashlib.md5(
        (apikey + x_cur_time + x_param).encode()
    ).hexdigest()

    img_bytes = _read_image_bytes(image_path)
    img_b64 = base64.b64encode(img_bytes).decode()
    # ⚠️ 不要手动 quote() —— requests 自动 URL encode form data，
    # 手动 quote 会双重编码致 "illegal image format"
    headers = {
        "X-Appid": appid,
        "X-CurTime": x_cur_time,
        "X-Param": x_param,
        "X-CheckSum": x_checksum,
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }
    resp = requests.post(url, headers=headers, data={"image": img_b64},
                          timeout=60)
    raw = resp.json()
    if raw.get("code") not in (0, "0"):
        raise RuntimeError(f"讯飞手写 OCR 失败: code={raw.get('code')} "
                            f"desc={raw.get('desc')} sid={raw.get('sid')}")

    # 抽文本：data.block[*].line[*].word[*].content
    lines: list[str] = []
    confs: list[float] = []
    for block in raw.get("data", {}).get("block", []):
        for line in block.get("line", []):
            text = "".join(w.get("content", "") for w in line.get("word", []))
            if text.strip():
                lines.append(text.strip())
            if "confidence" in line:
                try:
                    confs.append(float(line["confidence"]))
                except (ValueError, TypeError):
                    pass

    return {
        "text": "\n".join(lines),
        "confidence_avg": round(sum(confs) / len(confs), 3) if confs else None,
        "raw": raw,
    }


# ─── 公式识别（v2 HMAC-SHA256 签名接口）────────────────────────────────────

def _sign_hmac_request(host: str, path: str, body: str,
                        apikey: str, apisecret: str) -> dict:
    """生成 v2 接口的 HMAC-SHA256 鉴权 headers。"""
    digest_str = "SHA-256=" + base64.b64encode(
        hashlib.sha256(body.encode()).digest()).decode()
    date = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    sig_str = (
        f"host: {host}\n"
        f"date: {date}\n"
        f"POST {path} HTTP/1.1\n"
        f"digest: {digest_str}"
    )
    signature = base64.b64encode(hmac.new(
        apisecret.encode(), sig_str.encode(), hashlib.sha256
    ).digest()).decode()
    return {
        "Host": host,
        "Date": date,
        "Digest": digest_str,
        "Authorization": (
            f'api_key="{apikey}", algorithm="hmac-sha256", '
            f'headers="host date request-line digest", '
            f'signature="{signature}"'
        ),
        "Content-Type": "application/json",
    }


def recognize_formula(image_path: Path,
                       *, appid: str | None = None,
                       apikey: str | None = None,
                       apisecret: str | None = None) -> dict:
    """调讯飞公式识别 API（中英文混合 + 公式 → LaTeX）。

    Returns:
        {"text": str (LaTeX), "raw": dict}
        失败时 raise RuntimeError。
    """
    appid = appid or os.environ.get("XFYUN_FORMULA_APPID", DEFAULT_FORMULA["appid"])
    apikey = apikey or os.environ.get("XFYUN_FORMULA_APIKEY", DEFAULT_FORMULA["apikey"])
    apisecret = apisecret or os.environ.get("XFYUN_FORMULA_APISECRET",
                                                DEFAULT_FORMULA["apisecret"])

    host = "rest-api.xfyun.cn"
    path = "/v2/itr"
    url = f"https://{host}{path}"

    img_bytes = _read_image_bytes(image_path)
    img_b64 = base64.b64encode(img_bytes).decode()
    body = json.dumps({
        "common": {"app_id": appid},
        "business": {"ent": "teach-photo-print", "aue": "raw"},
        "data": {"image": img_b64},
    })

    headers = _sign_hmac_request(host, path, body, apikey, apisecret)
    resp = requests.post(url, headers=headers, data=body, timeout=60)
    raw = resp.json()

    if raw.get("code") not in (0, "0"):
        raise RuntimeError(f"讯飞公式识别失败: code={raw.get('code')} "
                            f"message={raw.get('message')} sid={raw.get('sid')}")

    # 抽 LaTeX：data.region[*].recog.content 是纯文本
    # 公式段用 `ifly-latex-begin ... ifly-latex-end` 标记包裹
    lines: list[str] = []
    for region in raw.get("data", {}).get("region", []):
        recog = region.get("recog", {})
        content = recog.get("content", "")
        if content:
            # 把公式标记转为标准 LaTeX $...$
            content = re.sub(r"ifly-latex-begin\s*(.+?)\s*ifly-latex-end",
                             r"$\1$", content)
            lines.append(content.strip())

    return {"text": "\n".join(lines), "raw": raw}


# ─── CLI 测试 ────────────────────────────────────────────────────────────────

def _main():
    import argparse
    ap = argparse.ArgumentParser(description="讯飞 OCR API 测试 CLI")
    ap.add_argument("image", type=Path)
    ap.add_argument("--api", choices=["handwriting", "formula"],
                    default="handwriting", help="API 类型")
    args = ap.parse_args()

    if args.api == "handwriting":
        r = recognize_handwriting(args.image)
    else:
        r = recognize_formula(args.image)
    print(f"=== {args.api} ===")
    print(f"text:\n{r['text']}")
    if "confidence_avg" in r and r["confidence_avg"] is not None:
        print(f"conf: {r['confidence_avg']}")


if __name__ == "__main__":
    _main()
