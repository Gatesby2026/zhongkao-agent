"""极简 HS256 JWT(stdlib,不引 PyJWT,保持服务依赖轻量)。

只做本项目自签自验的会话令牌,不追求 RFC 全特性。
两个服务用同一个 AUTH_JWT_SECRET → 任一服务签发的令牌,另一服务可校验。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

ALG = "HS256"
DEFAULT_TTL = 30 * 24 * 3600   # 30 天


def _secret() -> bytes:
    return os.environ.get("AUTH_JWT_SECRET", "dev-insecure-secret").encode()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(msg: bytes) -> str:
    return _b64e(hmac.new(_secret(), msg, hashlib.sha256).digest())


def issue(payload: dict, ttl: int = DEFAULT_TTL) -> str:
    now = int(time.time())
    body = {**payload, "iat": now, "exp": now + ttl}
    h = _b64e(json.dumps({"alg": ALG, "typ": "JWT"}, separators=(",", ":")).encode())
    p = _b64e(json.dumps(body, separators=(",", ":")).encode())
    return f"{h}.{p}.{_sign(f'{h}.{p}'.encode())}"


def verify(token: str) -> dict | None:
    """校验签名 + 过期,合法返回 payload,否则 None。"""
    try:
        h, p, sig = token.split(".")
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(sig, _sign(f"{h}.{p}".encode())):
        return None
    try:
        body = json.loads(_b64d(p))
    except (ValueError, json.JSONDecodeError):
        return None
    if body.get("exp", 0) < time.time():
        return None
    return body
