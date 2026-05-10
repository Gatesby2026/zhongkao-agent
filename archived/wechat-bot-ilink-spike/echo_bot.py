#!/usr/bin/env python3
"""
微信 ClawBot iLink 最小回声机器人

用途：验证 iLink Bot API 收发消息链路是否打通
功能：
  1. 启动后获取登录二维码并在终端显示
  2. 用启用了 ClawBot 插件的微信扫码绑定
  3. 长轮询接收所有发给该账号的消息
  4. 收到文字消息后原样回显（前缀 [ECHO]）

后续扩展方向：
  - 接入 LLM 替换 echo 逻辑
  - 区分私聊/群聊、根据群ID路由到学生档案
  - 支持图片/语音消息
"""

from __future__ import annotations

import base64
import json
import secrets
import sys
import time
from pathlib import Path

import requests
import qrcode

BASE_URL = "https://ilinkai.weixin.qq.com"
TOKEN_FILE = Path(__file__).parent / "bot_token.json"
CHANNEL_VERSION = "1.0.2"
LONG_POLL_TIMEOUT = 40  # 服务端 hold 35 秒，客户端给点余量


def gen_uin() -> str:
    """生成 X-WECHAT-UIN 防重放 header（4字节随机数 base64）"""
    return base64.b64encode(secrets.token_bytes(4)).decode()


def base_info() -> dict:
    return {"channel_version": CHANNEL_VERSION}


# ==================== 登录 ====================

def ilink_headers(token: str | None = None) -> dict:
    """构建 iLink 标准请求头（所有接口通用）"""
    h = {
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": "65536",
        "X-WECHAT-UIN": gen_uin(),
        "Content-Type": "application/json",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
        h["AuthorizationType"] = "ilink_bot_token"
    return h


def request_qrcode() -> dict:
    """请求登录二维码"""
    url = f"{BASE_URL}/ilink/bot/get_bot_qrcode?bot_type=3"
    resp = requests.get(url, headers=ilink_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def poll_qrcode_status(qrcode_key: str, max_wait: int = 300) -> dict:
    """轮询扫码状态，等待用户在微信里扫码确认"""
    url = f"{BASE_URL}/ilink/bot/get_qrcode_status"
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(
                url,
                params={"qrcode": qrcode_key},
                headers=ilink_headers(),
                timeout=LONG_POLL_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("bot_token"):
                    return data
        except requests.exceptions.RequestException as e:
            print(f"  [警告] 轮询错误: {e}, 1 秒后重试")
        time.sleep(1)
    raise TimeoutError("扫码超时（5 分钟未确认）")


def render_qr_to_terminal(content: str) -> None:
    """在终端打印 ASCII 二维码"""
    qr = qrcode.QRCode(border=1)
    qr.add_data(content)
    qr.make()
    qr.print_ascii(invert=True)


def login() -> dict:
    """完整登录流程：请求二维码 → 终端显示 → 等待扫码确认"""
    print("📱 正在请求登录二维码...")
    qr_resp = request_qrcode()

    qr_url = qr_resp.get("qrcode_img_content") or qr_resp.get("qrcode_url")
    qr_key = qr_resp.get("qrcode") or qr_resp.get("qrcode_key")

    if not qr_url or not qr_key:
        print(f"❌ 二维码响应格式异常: {qr_resp}")
        sys.exit(1)

    print(f"\n二维码 URL: {qr_url}\n")
    print("请用启用了 ClawBot 插件的微信扫描以下二维码：\n")
    render_qr_to_terminal(qr_url)

    print("\n⏳ 等待扫码确认（5 分钟内）...")
    auth = poll_qrcode_status(qr_key)

    TOKEN_FILE.write_text(json.dumps(auth, indent=2, ensure_ascii=False))
    print(f"\n✅ 登录成功！token 已保存到 {TOKEN_FILE.name}")
    return auth


def load_or_login() -> dict:
    """优先复用本地 token，否则走完整登录流程"""
    if TOKEN_FILE.exists():
        try:
            auth = json.loads(TOKEN_FILE.read_text())
            if auth.get("bot_token"):
                print(f"✅ 复用本地 token: {TOKEN_FILE.name}")
                return auth
        except json.JSONDecodeError:
            pass
    return login()


# ==================== 消息收发 ====================

class SessionExpiredError(Exception):
    pass


def get_updates(auth: dict, cursor: str = "") -> dict:
    """长轮询接收新消息"""
    base = auth.get("baseurl") or BASE_URL
    url = f"{base}/ilink/bot/getupdates"
    headers = ilink_headers(auth["bot_token"])
    body = {"get_updates_buf": cursor, "base_info": base_info()}
    resp = requests.post(url, json=body, headers=headers, timeout=LONG_POLL_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # iLink errcode -14 = session timeout（token 失效，需重新登录）
    if data.get("errcode") == -14:
        raise SessionExpiredError(f"iLink session timeout: {data}")
    return data


def send_text(auth: dict, to_user_id: str, context_token: str, text: str) -> dict:
    """发送文字消息"""
    base = auth.get("baseurl") or BASE_URL
    url = f"{base}/ilink/bot/sendmessage"
    headers = ilink_headers(auth["bot_token"])
    body = {
        "msg": {
            "to_user_id": to_user_id,
            "context_token": context_token,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        },
        "base_info": base_info(),
    }
    resp = requests.post(url, json=body, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def extract_text(msg: dict) -> str | None:
    """从消息体中提取文字内容（type=1 是文字）"""
    for item in msg.get("item_list", []):
        if item.get("type") == 1:
            return item.get("text_item", {}).get("text")
    return None


# ==================== 主循环 ====================

def main() -> None:
    auth = load_or_login()
    cursor = ""
    print("\n👂 开始监听消息（Ctrl+C 退出）...\n")

    while True:
        try:
            data = get_updates(auth, cursor)
            cursor = data.get("get_updates_buf", cursor)

            for msg in data.get("msgs", []):
                from_user = msg.get("from_user_id", "<unknown>")
                ctx_token = msg.get("context_token", "")
                msg_type = msg.get("message_type", "?")
                text = extract_text(msg)

                if text is None:
                    print(f"[{msg_type}] from={from_user}: <非文字消息，跳过>")
                    print(f"        原始数据: {json.dumps(msg, ensure_ascii=False)[:200]}")
                    continue

                print(f"[{msg_type}] from={from_user}: {text}")

                reply = f"[ECHO] {text}"
                try:
                    send_text(auth, from_user, ctx_token, reply)
                    print(f"        → 已回复: {reply}")
                except Exception as e:
                    print(f"        ❌ 回复失败: {e}")

        except KeyboardInterrupt:
            print("\n\n👋 停止监听")
            break
        except SessionExpiredError:
            print("🔄 Session 过期，重新登录...")
            TOKEN_FILE.unlink(missing_ok=True)
            auth = login()
            cursor = ""
        except requests.exceptions.HTTPError as e:
            print(f"⚠️  HTTP 错误: {e.response.status_code} {e.response.text[:200]}")
            if e.response.status_code in (401, 403):
                print("   token 可能失效，删除 bot_token.json 重新扫码登录")
                break
            time.sleep(5)
        except Exception as e:
            print(f"⚠️  错误: {type(e).__name__}: {e}, 5 秒后重试...")
            time.sleep(5)


if __name__ == "__main__":
    main()
