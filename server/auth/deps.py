"""FastAPI 依赖:从 Cookie 取登录态。两服务共用。"""
from __future__ import annotations

from typing import Optional

from fastapi import Cookie, HTTPException

from . import jwt_util, store

COOKIE_NAME = "zk_session"


def current_user_optional(zk_session: Optional[str] = Cookie(default=None)) -> Optional[dict]:
    """有合法 Cookie 返回 user,否则 None(不报错)。用于软门槛/可选登录。"""
    if not zk_session:
        return None
    payload = jwt_util.verify(zk_session)
    if not payload:
        return None
    return store.get_user(int(payload.get("uid", 0)))


def get_current_user(zk_session: Optional[str] = Cookie(default=None)) -> dict:
    """硬门槛:未登录 401。"""
    user = current_user_optional(zk_session)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user
