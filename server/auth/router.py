"""项目级鉴权路由 /api/auth/*。两服务各 include_router 一次即可。"""
from __future__ import annotations

import os
import random
import re
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from . import jwt_util, sms, store
from .deps import COOKIE_NAME, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
COOKIE_TTL = 30 * 24 * 3600


def _client_ip(req: Request) -> str | None:
    return (req.headers.get("x-real-ip")
            or (req.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (req.client.host if req.client else None))


def _set_session_cookie(resp: Response, uid: int, phone: str) -> None:
    token = jwt_util.issue({"uid": uid, "phone": phone}, ttl=COOKIE_TTL)
    resp.set_cookie(
        COOKIE_NAME, token, max_age=COOKIE_TTL, httponly=True, samesite="lax",
        secure=os.environ.get("AUTH_COOKIE_SECURE", "1") == "1", path="/",
    )


def _user_public(u: dict) -> dict:
    return {"id": u["id"], "phone": u["phone"], "nickname": u.get("nickname")}


@router.post("/sms/send")
def sms_send(req: Request, phone: str = Body(..., embed=True)):
    phone = (phone or "").strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    now = time.time()
    if now - store.last_code_ts(phone) < sms.RESEND_COOLDOWN_SEC:
        raise HTTPException(status_code=429, detail="发送过于频繁,请 60 秒后再试")
    ip = _client_ip(req)
    n_phone, n_ip = store.count_codes_since(phone, ip, now - 86400)
    if n_phone >= sms.MAX_PER_PHONE_PER_DAY:
        raise HTTPException(status_code=429, detail="该号码今日验证码次数已达上限")
    if n_ip >= sms.MAX_PER_IP_PER_DAY:
        raise HTTPException(status_code=429, detail="操作过于频繁,请稍后再试")
    code = f"{random.randint(0, 999999):06d}"
    store.save_code(phone, code, sms.CODE_TTL_SEC, ip)
    ok, msg = sms.send_code(phone, code)
    if not ok:
        raise HTTPException(status_code=502, detail=f"短信发送失败:{msg}")
    return {"ok": True, "cooldown": sms.RESEND_COOLDOWN_SEC}


@router.post("/sms/verify")
def sms_verify(resp: Response,
               phone: str = Body(...), code: str = Body(...)):
    phone, code = (phone or "").strip(), (code or "").strip()
    if not PHONE_RE.match(phone) or not code.isdigit():
        raise HTTPException(status_code=400, detail="参数不正确")
    if not store.verify_code(phone, code, sms.MAX_VERIFY_ATTEMPTS):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    user = store.upsert_user_by_phone(phone)
    _set_session_cookie(resp, user["id"], phone)
    return {"ok": True, "user": _user_public(user)}


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
