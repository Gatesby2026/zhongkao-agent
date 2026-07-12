"""阿里云邮件推送(DirectMail)发送验证码。与短信共用一把 AK。

env(复用短信那套):
  ALI_SMS_AK_ID / ALI_SMS_AK_SECRET   阿里云 AK(需 dm:SingleSendMail 权限)
  ALI_MAIL_FROM   发信地址,默认 no-reply@gatesby.xyz(DirectMail 控制台已验证)
  ALI_MAIL_FROM_ALIAS  发件人昵称,默认「中考助手」
  SMS_DEV_MODE=1  不真发,验证码打到服务日志(本地开发)

发信地址 no-reply@gatesby.xyz 为触发型(trigger),域名已验证,适合验证码。
"""
from __future__ import annotations

import os
import re
from html import unescape

FROM_ADDR = os.environ.get("ALI_MAIL_FROM", "no-reply@gatesby.xyz")
FROM_ALIAS = os.environ.get("ALI_MAIL_FROM_ALIAS", "中考助手")
CODE_TTL_MIN = 5


def _dev_mode() -> bool:
    return (
        os.environ.get("SMS_DEV_MODE") == "1"
        or not os.environ.get("ALI_SMS_AK_ID")
        or not os.environ.get("ALI_SMS_AK_SECRET")
    )


def _html_to_text(html_body: str) -> str:
    """给验证码邮件补纯文本正文，提升部分邮箱的可读性/投递友好度。"""
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_body or "")
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def send_mail(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    """通用单发邮件(阿里云 DirectMail)。返回 (ok, message)。
    dev 模式(无 AK 或 SMS_DEV_MODE=1)只打日志不真发。验证码/盯哨告警等都复用本函数。"""
    if _dev_mode():
        print(f"[MAIL-DEV] to={to_email} subj={subject}（dev 模式未真实发送）", flush=True)
        return True, "dev"
    try:
        from alibabacloud_dm20151123.client import Client
        from alibabacloud_dm20151123 import models as m
        from alibabacloud_tea_openapi import models as openapi
    except ImportError:
        return False, "邮件 SDK 未安装(alibabacloud_dm20151123)"
    cfg = openapi.Config(
        access_key_id=os.environ["ALI_SMS_AK_ID"],
        access_key_secret=os.environ["ALI_SMS_AK_SECRET"],
    )
    cfg.endpoint = "dm.aliyuncs.com"
    try:
        resp = Client(cfg).single_send_mail(m.SingleSendMailRequest(
            account_name=FROM_ADDR, address_type=1, reply_to_address=False,
            to_address=to_email, from_alias=FROM_ALIAS,
            subject=subject, html_body=html_body, text_body=_html_to_text(html_body),
        ))
        # 成功返回含 EnvId/RequestId;无异常即视为已提交
        return True, getattr(resp.body, "request_id", "OK")
    except Exception as e:   # noqa: BLE001  阿里云 SDK 抛各类异常,统一兜底
        return False, str(e)


def send_code(to_email: str, code: str) -> tuple[bool, str]:
    """发送验证码邮件。返回 (ok, message)。"""
    html = (
        f'<div style="font-family:sans-serif;font-size:15px;color:#222">'
        f'<p>您的验证码是：</p>'
        f'<p style="font-size:28px;font-weight:700;letter-spacing:4px;color:#2563eb">{code}</p>'
        f'<p style="color:#888;font-size:13px">{CODE_TTL_MIN} 分钟内有效，请勿泄露于他人。'
        f'若非本人操作请忽略本邮件。</p></div>'
    )
    return send_mail(to_email, "【中考助手】登录验证码", html)
