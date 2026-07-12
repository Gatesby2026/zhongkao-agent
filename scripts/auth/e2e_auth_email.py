#!/usr/bin/env python3
"""注册/登录邮件验证码端到端测试。

默认只测试发送接口是否返回成功；如果配置了 IMAP 测试邮箱，则会继续：
1. 轮询真实收件箱；
2. 提取验证码；
3. 调用 /api/auth/code/verify 完成登录闭环。

环境变量（真实收件箱检查需要）：
  AUTH_E2E_ACCOUNT        收件邮箱，例如 test@example.com
  AUTH_E2E_IMAP_HOST      IMAP 主机，例如 imap.gmail.com
  AUTH_E2E_IMAP_PORT      IMAP SSL 端口，默认 993
  AUTH_E2E_IMAP_USER      IMAP 用户名，默认同 AUTH_E2E_ACCOUNT
  AUTH_E2E_IMAP_PASSWORD  IMAP 密码/应用专用密码
  AUTH_E2E_IMAP_MAILBOX   邮箱目录，默认 INBOX

示例：
  AUTH_E2E_ACCOUNT=xxx@gmail.com \
  AUTH_E2E_IMAP_HOST=imap.gmail.com \
  AUTH_E2E_IMAP_PASSWORD='应用专用密码' \
  python scripts/auth/e2e_auth_email.py --base-url https://zhongkao.gatesby.xyz
"""
from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, build_opener


SENDER = "no-reply@gatesby.xyz"
SUBJECT_KEYWORD = "登录验证码"
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")


@dataclass
class HttpResult:
    status: int
    body: dict
    raw: str


def _post_json(opener, base_url: str, path: str, payload: dict) -> HttpResult:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return HttpResult(resp.status, json.loads(raw or "{}"), raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            body = {"detail": raw}
        return HttpResult(e.code, body, raw)


def _message_text(msg: Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
    return "\n".join(chunks)


def _message_ts(msg: Message) -> float:
    parsed = email.utils.parsedate_to_datetime(msg.get("Date", ""))
    if parsed is None:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _extract_code(msg: Message) -> str | None:
    subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))
    if SUBJECT_KEYWORD not in subject:
        return None
    text = _message_text(msg)
    # 优先找“验证码”附近的 6 位数字；兜底找正文里第一段 6 位数字。
    near = re.search(r"验证码.{0,80}?(\d{6})", text, re.S)
    if near:
        return near.group(1)
    found = CODE_RE.search(text)
    return found.group(1) if found else None


def poll_imap_for_code(account: str, since_ts: float, timeout_sec: int) -> str:
    host = os.environ.get("AUTH_E2E_IMAP_HOST")
    password = os.environ.get("AUTH_E2E_IMAP_PASSWORD")
    if not host or not password:
        raise RuntimeError("未配置 AUTH_E2E_IMAP_HOST / AUTH_E2E_IMAP_PASSWORD，无法检查真实收件箱")

    port = int(os.environ.get("AUTH_E2E_IMAP_PORT", "993"))
    user = os.environ.get("AUTH_E2E_IMAP_USER") or account
    mailbox = os.environ.get("AUTH_E2E_IMAP_MAILBOX", "INBOX")
    deadline = time.time() + timeout_sec
    context = ssl.create_default_context()

    while time.time() < deadline:
        with imaplib.IMAP4_SSL(host, port, ssl_context=context) as conn:
            conn.login(user, password)
            typ, _ = conn.select(mailbox, readonly=True)
            if typ != "OK":
                raise RuntimeError(f"无法打开邮箱目录：{mailbox}")
            # 只按发件人缩小范围，避免 IMAP 服务器对中文 subject 搜索支持不一致。
            typ, data = conn.search(None, "FROM", f'"{SENDER}"')
            if typ != "OK":
                raise RuntimeError("IMAP 搜索失败")
            ids = data[0].split()[-20:]
            for mid in reversed(ids):
                typ, msg_data = conn.fetch(mid, "(RFC822)")
                if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                if _message_ts(msg) + 30 < since_ts:
                    continue
                code = _extract_code(msg)
                if code:
                    return code
        time.sleep(5)

    raise TimeoutError(f"{timeout_sec} 秒内未在真实收件箱中收到验证码邮件")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://zhongkao.gatesby.xyz")
    parser.add_argument("--account", default=os.environ.get("AUTH_E2E_ACCOUNT"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--send-only", action="store_true", help="只检查发送接口，不检查收件箱/登录")
    args = parser.parse_args()

    if not args.account:
        print("ERROR: 请通过 --account 或 AUTH_E2E_ACCOUNT 指定测试邮箱", file=sys.stderr)
        return 2

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    started = time.time()

    print(f"[1/3] send code -> {args.account}")
    sent = _post_json(opener, args.base_url, "/api/auth/code/send", {"account": args.account})
    print(f"      HTTP {sent.status} {sent.body}")
    if sent.status != 200 or sent.body.get("channel") != "email":
        return 1
    if args.send_only:
        print("PASS: 发送接口成功（send-only，未检查真实收件箱）")
        return 0

    print("[2/3] poll real mailbox")
    try:
        code = poll_imap_for_code(args.account, started, args.timeout)
    except Exception as e:  # noqa: BLE001  测试脚本需要把失败原因直接打印出来
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("      received code: ******")

    print("[3/3] verify code / login")
    verified = _post_json(opener, args.base_url, "/api/auth/code/verify", {
        "account": args.account,
        "code": code,
    })
    safe_body = dict(verified.body)
    if isinstance(safe_body.get("user"), dict):
        safe_body["user"] = {"id": safe_body["user"].get("id"), "email": safe_body["user"].get("email")}
    print(f"      HTTP {verified.status} {safe_body}")
    if verified.status != 200 or not verified.body.get("ok"):
        return 1

    print("PASS: 真实收件箱收到验证码，并完成登录闭环")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
