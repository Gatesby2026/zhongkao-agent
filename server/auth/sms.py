"""阿里云短信发送 + 限流配置。

env(两服务共享的 EnvironmentFile):
  ALI_SMS_AK_ID / ALI_SMS_AK_SECRET   阿里云 AK(需 dysmsapi:SendSms 权限)
  ALI_SMS_SIGN_NAME      签名,默认「北京黑帝斯」
  ALI_SMS_TEMPLATE_CODE  模板,默认 SMS_334705080(正文 ${code})
  SMS_DEV_MODE=1         不真发,验证码打到服务日志(本地开发用,省钱)

限流(防刷,短信 ~¥0.045/条):
  同手机号 60s 内 1 条、24h 内 ≤5 条;同 IP 24h 内 ≤20 条;码 5 分钟过期、错 5 次作废。
"""
from __future__ import annotations

import json
import os

CODE_TTL_SEC = 5 * 60
RESEND_COOLDOWN_SEC = 60
MAX_PER_PHONE_PER_DAY = 5
MAX_PER_IP_PER_DAY = 20
MAX_VERIFY_ATTEMPTS = 5

SIGN_NAME = os.environ.get("ALI_SMS_SIGN_NAME", "北京黑帝斯")
TEMPLATE_CODE = os.environ.get("ALI_SMS_TEMPLATE_CODE", "SMS_334705080")


def _dev_mode() -> bool:
    return os.environ.get("SMS_DEV_MODE") == "1" or not os.environ.get("ALI_SMS_AK_ID")


def send_code(phone: str, code: str) -> tuple[bool, str]:
    """发送验证码。返回 (ok, message)。dev 模式只打日志不真发。"""
    if _dev_mode():
        print(f"[SMS-DEV] {phone} 验证码 {code}（dev 模式未真实发送）", flush=True)
        return True, "dev"
    try:
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_dysmsapi20170525 import models as m
        from alibabacloud_tea_openapi import models as openapi
    except ImportError:
        return False, "短信 SDK 未安装(alibabacloud_dysmsapi20170525)"
    cfg = openapi.Config(
        access_key_id=os.environ["ALI_SMS_AK_ID"],
        access_key_secret=os.environ["ALI_SMS_AK_SECRET"],
    )
    cfg.endpoint = "dysmsapi.aliyuncs.com"
    try:
        resp = Client(cfg).send_sms(m.SendSmsRequest(
            phone_numbers=phone, sign_name=SIGN_NAME,
            template_code=TEMPLATE_CODE,
            template_param=json.dumps({"code": code}),
        ))
        body = resp.body
        if body.code == "OK":
            return True, "OK"
        return False, f"{body.code}: {body.message}"
    except Exception as e:   # noqa: BLE001  阿里云 SDK 抛各类异常,统一兜底
        return False, str(e)
