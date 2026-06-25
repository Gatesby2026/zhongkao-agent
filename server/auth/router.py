"""项目级鉴权路由 /api/auth/*。两服务各 include_router 一次即可。"""
from __future__ import annotations

import logging
import os
import random
import re
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

_log = logging.getLogger("auth")

from . import email as mailer, jwt_util, sms, store
from .deps import COOKIE_NAME, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COOKIE_TTL = 30 * 24 * 3600


def _norm_phone(raw: str) -> str:
    """去空格/横线、去掉 +86/86 国家码 → 纯 11 位。"""
    s = re.sub(r"\D", "", raw or "")
    if len(s) == 13 and s.startswith("86"):
        s = s[2:]
    return s


def _classify(account: str):
    """识别账号类型 → ('phone'|'email'|None, 归一化 key)。"""
    a = (account or "").strip()
    if EMAIL_RE.match(a):
        return "email", a.lower()
    p = _norm_phone(a)
    if PHONE_RE.match(p):
        return "phone", p
    return None, a


def _client_ip(req: Request) -> str | None:
    """仅信任前置 nginx 用 $remote_addr 覆盖写入的 X-Real-IP(客户端无法伪造)。
    绝不读 X-Forwarded-For——其首段客户端可任意伪造,会被用来绕过 IP 频控批量刷码。
    无 X-Real-IP(直连/未走 nginx)时退回 socket peer。nginx 侧须 set_real_ip_from
    可信代理并对外部请求清掉客户端自带的 X-Real-IP/X-Forwarded-For。"""
    xri = (req.headers.get("x-real-ip") or "").strip()
    if xri:
        return xri
    return req.client.host if req.client else None


def _set_session_cookie(resp: Response, uid: int) -> None:
    token = jwt_util.issue({"uid": uid}, ttl=COOKIE_TTL)
    resp.set_cookie(
        COOKIE_NAME, token, max_age=COOKIE_TTL, httponly=True, samesite="lax",
        secure=os.environ.get("AUTH_COOKIE_SECURE", "1") == "1", path="/",
    )


def _user_public(u: dict) -> dict:
    return {"id": u["id"], "phone": u.get("phone"),
            "email": u.get("email"), "nickname": u.get("nickname")}


def _do_send(req: Request, account: str) -> dict:
    kind, key = _classify(account)
    if not kind:
        raise HTTPException(status_code=400, detail="请输入正确的手机号或邮箱")
    now = time.time()
    if now - store.last_code_ts(key) < sms.RESEND_COOLDOWN_SEC:
        raise HTTPException(status_code=429, detail="发送过于频繁,请 60 秒后再试")
    ip = _client_ip(req)
    n_acc, n_ip = store.count_codes_since(key, ip, now - 86400)
    if n_acc >= sms.MAX_PER_PHONE_PER_DAY:
        raise HTTPException(status_code=429, detail="该账号今日验证码次数已达上限")
    if n_ip >= sms.MAX_PER_IP_PER_DAY:
        raise HTTPException(status_code=429, detail="操作过于频繁,请稍后再试")
    code = f"{random.randint(0, 999999):06d}"
    store.save_code(key, code, sms.CODE_TTL_SEC, ip)
    if kind == "email":
        ok, msg = mailer.send_code(key, code)
        label = "邮件"
    else:
        ok, msg = sms.send_code(key, code)
        label = "短信"
    if not ok:
        # 不把 provider(阿里云 SDK/RequestId/AK 状态)原文回传客户端——此端点未鉴权,会被指纹识别。
        _log.warning("send code failed via %s: %s", label, msg)
        raise HTTPException(status_code=502, detail=f"{label}发送失败,请稍后重试")
    return {"ok": True, "cooldown": sms.RESEND_COOLDOWN_SEC, "channel": kind}


def _do_verify(resp: Response, account: str, code: str) -> dict:
    kind, key = _classify(account)
    code = (code or "").strip()
    if not kind or not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="参数不正确")
    if not store.verify_code(key, code, sms.MAX_VERIFY_ATTEMPTS):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    user = (store.upsert_user_by_email(key) if kind == "email"
            else store.upsert_user_by_phone(key))
    store.log_event("login", user_id=user["id"], meta={"via": kind})
    _set_session_cookie(resp, user["id"])
    return {"ok": True, "user": _user_public(user)}


# 统一端点:手机号 / 邮箱自动识别
@router.post("/code/send")
def code_send(req: Request, account: str = Body(..., embed=True)):
    return _do_send(req, account)


@router.post("/code/verify")
def code_verify(resp: Response, account: str = Body(...), code: str = Body(...)):
    return _do_verify(resp, account, code)


# 兼容旧前端(只传 phone)
@router.post("/sms/send")
def sms_send(req: Request, phone: str = Body(..., embed=True)):
    return _do_send(req, phone)


@router.post("/sms/verify")
def sms_verify(resp: Response, phone: str = Body(...), code: str = Body(...)):
    return _do_verify(resp, phone, code)


@router.get("/me")
def me(user: dict = Depends(get_current_user), app: str = "zhiyuan"):
    return {"user": _user_public(user), "profile": store.get_profile(user["id"], app)}


@router.post("/logout")
def logout(resp: Response):
    resp.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/profile")
def get_profile(user: dict = Depends(get_current_user), app: str = "zhiyuan"):
    return {"profile": store.get_profile(user["id"], app)}


@router.put("/profile")
def put_profile(data: dict = Body(...),
                user: dict = Depends(get_current_user), app: str = "zhiyuan"):
    store.put_profile(user["id"], app, data)
    return {"ok": True}
