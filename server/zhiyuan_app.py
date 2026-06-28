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

import logging
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
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
_log = logging.getLogger("zhiyuan")

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
    district: str = "chaoyang"


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
    except ValueError as e:           # 住址无法定位等(可读输入错)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:            # LLM/网络失败 → 让前端回落规则版;异常原文只记日志不回传
        _log.warning("zhiyuan report failed: %r", e)
        raise HTTPException(status_code=502, detail="AI 报告生成失败,请稍后重试")
    import json as _json
    warns = llm_report.validate(out["report"], _json.dumps(out["context"], ensure_ascii=False))
    return {"report": out["report"], "provider": out["provider"],
            "warnings": warns,                              # 幻觉:疑似编造校名
            "pitfall_warnings": out.get("pitfall_warnings", [])}  # 避坑:填报硬规则违规



@app.post("/api/zhiyuan/recommend")
def zhiyuan_recommend(req: ZhiyuanReq, request: Request):
    if req.mode not in zhiyuan.dist_mod.MODES:   # 非法通勤方式 → 400(而非 KeyError 漏成 500)
        raise HTTPException(status_code=400, detail="通勤方式不正确")
    district = req.district or "chaoyang"
    if district not in _full_set():              # 该区无完整录取数据 → 不做冲稳保
        raise HTTPException(status_code=400, detail="该区暂无完整录取数据，无法做冲稳保")
    try:
        result = zhiyuan.build_result(
            rank=req.rank, home=req.home, mode=req.mode,
            max_km=req.max_km, interests=req.interests, district=district,
            boarding=req.boarding, identity=req.identity,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:              # 脏数据/外部失败 → 通用 500,原文只记日志
        _log.warning("zhiyuan recommend failed: %r", e)
        raise HTTPException(status_code=500, detail="推荐生成失败,请稍后重试")
    # 埋点:真实使用一次冲稳保(IP 取 nginx 透传的 X-Real-IP)。失败已被 store 内部吞掉。
    auth_store.log_event("recommend",
                         ip=request.headers.get("x-real-ip") or
                            (request.client.host if request.client else None),
                         meta={"district": district, "rank": req.rank})
    # 去掉给 CLI/地图复用的内部字段（下划线开头）
    return {k: v for k, v in result.items() if not k.startswith("_")}


import json as _json2

_BJ_DIR = ROOT / "knowledge-base" / "admission" / "beijing"
_DISTRICTS_DIR = _BJ_DIR / "districts"
# 区拼音→中文。mode 不再写死:有完整 <py>.yaml(≥3 校有录取线)→ full(冲稳保+草表+全维),
# 否则 browse(校库:可查校/看专业/看位置)。随数据补齐自动从 browse 升级 full。
_DLIST = [("chaoyang", "朝阳"), ("haidian", "海淀"), ("xicheng", "西城"),
          ("dongcheng", "东城"), ("fengtai", "丰台"), ("shijingshan", "石景山"),
          ("mentougou", "门头沟"), ("fangshan", "房山"), ("tongzhou", "通州"),
          ("shunyi", "顺义"), ("changping", "昌平"), ("daxing", "大兴"),
          ("huairou", "怀柔"), ("pinggu", "平谷"), ("miyun", "密云"),
          ("yanqing", "延庆")]
_PY2CN = {py: cn for py, cn in _DLIST}

_FULL_CACHE = None


def _full_set():
    """有完整录取数据(可做冲稳保)的区集合。朝阳恒 full;其余看 <py>.yaml 是否有 ≥3 校带 scores。
    模块级缓存:数据离线装配、部署重启即刷新。"""
    global _FULL_CACHE
    if _FULL_CACHE is None:
        s = {"chaoyang"}
        for py, _ in _DLIST:
            if py == "chaoyang":
                continue
            p = _BJ_DIR / f"{py}.yaml"
            if not p.exists():
                continue
            try:
                d = zhiyuan.yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                if sum(1 for x in d.get("schools", []) if x.get("scores")) >= 3:
                    s.add(py)
            except Exception:
                pass
        _FULL_CACHE = s
    return _FULL_CACHE


@app.get("/api/zhiyuan/districts")
def zhiyuan_districts():
    """区列表:full(冲稳保+草表+全维) / browse(校库·暂无录取线)。"""
    full = _full_set()
    out = []
    for py, cn in _DLIST:
        n = None
        f = _DISTRICTS_DIR / f"{py}_admission_codes.json"
        if f.exists():
            n = len(_json2.loads(f.read_text(encoding="utf-8")).get("schools", {}))
        out.append({"py": py, "cn": cn,
                    "mode": "full" if py in full else "browse", "n_schools": n})
    return {"districts": out}


@app.get("/api/zhiyuan/district/{py}")
def zhiyuan_district(py: str):
    """某区校库:学校代码+专业(班)+坐标(GCJ-02)。无录取线 → 仅供查校/看专业/看位置。"""
    cf = _DISTRICTS_DIR / f"{py}_admission_codes.json"
    if not cf.exists():
        raise HTTPException(status_code=404, detail="该区暂无校库数据")
    d = _json2.loads(cf.read_text(encoding="utf-8"))
    cof = _DISTRICTS_DIR / f"{py}_coords.json"
    coords = (_json2.loads(cof.read_text(encoding="utf-8")).get("schools", {}) if cof.exists() else {})
    schools = []
    for code, s in d.get("schools", {}).items():
        c = coords.get(s["name"]) or {}
        schools.append({"name": s["name"], "school_code": code, "majors": s.get("majors", []),
                        "lat": c.get("lat"), "lon": c.get("lon"), "coord_conf": c.get("conf")})
    schools.sort(key=lambda x: x["school_code"])
    return {"district": d.get("district", _PY2CN.get(py, py)), "mode": "browse",
            "has_lines": False, "plan_year": d.get("plan_year"),
            "note": "该区暂无录取线/位次,无法冲稳保;仅供查校、看专业(班)、看位置。",
            "schools": schools}


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
