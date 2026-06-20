"""zhongkao 项目级统一鉴权包。

两个 FastAPI 服务(学情 main.py / 志愿 zhiyuan_app.py)共用:
  - 同一用户库 accounts.sqlite3(users / login_codes / app_profiles)
  - 同一 JWT 密钥(AUTH_JWT_SECRET)→ 同域 Cookie 一处登录两端通用
  - 同一阿里云短信发送(签名/模板走 env)

用法(两服务各一行)::

    from auth import router as auth_router
    app.include_router(auth_router.router)

保护某个路由::

    from auth.deps import get_current_user
    @app.get("/x")
    def x(user = Depends(get_current_user)): ...
"""
from . import store, jwt_util, sms, deps, router  # noqa: F401
