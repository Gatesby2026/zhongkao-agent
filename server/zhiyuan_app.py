"""志愿填报推荐 — 独立 FastAPI 服务（与"学情分析"服务解耦，B 档：同仓双服务）。

只承载志愿功能：冲稳保推荐 API + 志愿页 + 其静态资源。
依赖很轻（fastapi / uvicorn / pyyaml / requests），不需要学情那套 OCR/重依赖。

启动：
  cd server && AMAP_KEY=$KEY uvicorn zhiyuan_app:app --host 0.0.0.0 --port 8201

路由（nginx 把 /zhiyuan、/api/zhiyuan/* 反代到本服务）：
  GET  /api/health
  POST /api/zhiyuan/recommend
  GET  /zhiyuan                （志愿页 HTML）
  /assets/*                     （志愿页用到的构建产物，自带一份以便独立运行）
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))            # 项目级 auth 包
sys.path.insert(0, str(ROOT / "scripts" / "admission"))
import recommend as zhiyuan   # noqa: E402
import llm_report             # noqa: E402  大模型志愿顾问(P1)
from auth import router as auth_router, store as auth_store   # noqa: E402
from auth.deps import get_current_user                       # noqa: E402
from fastapi import Depends                                  # noqa: E402

WEB_DIST = ROOT / "web" / "dist"

app = FastAPI(title="中考志愿填报推荐 API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router.router)               # /api/auth/* 项目级统一鉴权


@app.on_event("startup")
def _startup():
    auth_store.init_db()


class ZhiyuanReq(BaseModel):
    rank: int
    home: Optional[str] = None
    mode: str = "driving"
    max_km: Optional[float] = None
    interests: Optional[List[str]] = None
    boarding: bool = False
    identity: str = "jjyj"   # 京籍应届 jjyj / 非京籍 feijing / 往届回京 wangjie


@app.get("/api/health")
def health():
    return {"ok": True, "svc": "zhiyuan"}


class ReportReq(BaseModel):
    rank: int
    home: Optional[str] = None
    mode: str = "bicycling"
    max_km: Optional[float] = 8
    boarding: bool = True
    identity: str = "jjyj"
    profile: dict = {}            # 孩子画像(P1 先复用 form 字段;P2 上问卷)


@app.post("/api/zhiyuan/report")
def zhiyuan_report(req: ReportReq, user: dict = Depends(get_current_user)):
    """大模型志愿深度报告(P1·登录即可·暂不收费灰度)。provider 由 LLM_PROVIDER 配置。"""
    import os
    provider = os.environ.get("LLM_PROVIDER", "qwen")
    try:
        out = llm_report.generate_report(
            rank=req.rank, home=req.home, mode=req.mode, max_km=req.max_km,
            boarding=req.boarding, identity=req.identity,
            profile=req.profile or {}, provider=provider)
    except ValueError as e:           # 住址无法定位等
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:            # LLM/网络失败 → 让前端回落规则版
        raise HTTPException(status_code=502, detail=f"AI 报告生成失败,请稍后重试:{e}")
    import json as _json
    warns = llm_report.validate(out["report"], _json.dumps(out["context"], ensure_ascii=False))
    return {"report": out["report"], "provider": out["provider"], "warnings": warns}


@app.post("/api/zhiyuan/recommend")
def zhiyuan_recommend(req: ZhiyuanReq):
    try:
        result = zhiyuan.build_result(
            rank=req.rank, home=req.home, mode=req.mode,
            max_km=req.max_km, interests=req.interests, district="chaoyang",
            boarding=req.boarding, identity=req.identity,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 去掉给 CLI/地图复用的内部字段（下划线开头）
    return {k: v for k, v in result.items() if not k.startswith("_")}


@app.get("/zhiyuan")
def zhiyuan_page():
    f = WEB_DIST / "zhiyuan.html"
    if not f.exists():
        raise HTTPException(status_code=404, detail="zhiyuan page not built")
    return FileResponse(str(f))


# 自带一份静态资源（nginx 也可直接从磁盘 dist/ 提供 /assets，二者其一即可）
if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")),
              name="zhiyuan-assets")
