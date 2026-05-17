"""FastAPI 后端 — 学情分析 H5 支撑接口（Phase 1：纯打通四屏）。

启动：
  cd server && DASHSCOPE_API_KEY=$KEY uvicorn main:app --host 0.0.0.0 --port 8000

Phase 1 约定：
  上传的答题卡照片会存盘但分析走 reference 数据
  （students/jiaxiaoqi/2026-chaoyang-yi-physics）以快速打通四屏。
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db                       # noqa: E402
import tasks                    # noqa: E402
import pipeline_adapter as pa   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Phase 1 reference 数据
REF_STUDENT_DIR = ROOT / "students" / "jiaxiaoqi" / "2026-chaoyang-yi-physics"
REF_EXAM_SLUG = "2026-chaoyang-yi-physics"
UPLOAD_ROOT = ROOT / "server" / "uploads"
WEB_STUDENTS = ROOT / "students" / "_web"   # H5 上传产生的学生目录
PAPER_OUT = ROOT / "out" / "papers"

app = FastAPI(title="中考一模学情分析 API", version="0.1")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_db()
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health():
    return {"ok": True, "ts": time.time()}


# ---------- 1. 创建分析（上传答题卡）----------

@app.post("/api/analyses")
async def create_analysis(files: list[UploadFile] = File(default=[])):
    aid = uuid.uuid4().hex[:12]

    if files:
        sdir = WEB_STUDENTS / aid / REF_EXAM_SLUG
        photos = sdir / "answer-card-photos"
        photos.mkdir(parents=True, exist_ok=True)
        saved = 0
        for f in files:
            data = await f.read()
            if len(data) < 1024:
                continue
            ext = (Path(f.filename or "").suffix or ".jpg").lower()
            if ext not in (".jpg", ".jpeg", ".png", ".heic"):
                ext = ".jpg"
            saved += 1
            (photos / f"page-{saved:02d}{ext}").write_bytes(data)
        if saved == 0:
            raise HTTPException(400, "未收到有效答题卡图片")
        db.create_analysis(aid, "（识别中）", REF_EXAM_SLUG, str(sdir))
        # 仅做检测（card_meta 读表头），不跑重流水线；前端轮询 /detect
        tasks.submit_detect(aid, sdir)
        return {"id": aid, "status": "detecting",
                "uploaded": saved, "mode": "real-ocr"}

    # 无上传：纯 reference 演示
    db.create_analysis(aid, "贾小淇", REF_EXAM_SLUG, str(REF_STUDENT_DIR))
    tasks.submit_reference(aid, REF_STUDENT_DIR)
    return {"id": aid, "status": "queued",
            "exam_slug": REF_EXAM_SLUG, "uploaded": 0, "mode": "reference"}


# ---------- 1b. 检测结果（答题卡页轮询）----------

@app.get("/api/analyses/{aid}/detect")
def get_detect(aid: str):
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    det = {}
    if a["detected"]:
        try:
            det = __import__("json").loads(a["detected"])
        except Exception:
            det = {}
    return {
        "id": aid, "status": a["status"],          # detecting|ready_confirm|need_manual|failed
        "error": a["error"],
        "detected": det,                            # exam_slug/district/subject/year/exam_type/student_name/pages_complete/completeness_note/matched
    }


# ---------- 1c. 确认无误，开始分析 ----------

@app.post("/api/analyses/{aid}/start")
def start_pipeline(aid: str):
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    if a["status"] != "ready_confirm":
        raise HTTPException(409, "考试未识别/未确认，无法开始分析")
    db.update_stage(aid, 2, "识别答题卡作答", status="running")
    tasks.submit_pipeline(aid, Path(a["student_dir"]))
    return {"id": aid, "status": "running"}


# ---------- 2. 上传小分表（可选）----------

@app.post("/api/analyses/{aid}/scores")
async def upload_scores(aid: str, file: UploadFile = File(...)):
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    updir = UPLOAD_ROOT / aid
    updir.mkdir(parents=True, exist_ok=True)
    ext = (Path(file.filename or "").suffix or ".xlsx").lower()
    raw = updir / f"scores_raw{ext}"
    raw.write_bytes(await file.read())

    # 班小二 xlsx → 解析为标准 scores.json，落到 aid 稳定位置
    # （task 完成 OCR/识别/重命名后会取这份并放进学生目录）
    import parse_scores
    try:
        data = parse_scores.parse_scores_xlsx(raw)
    except Exception as e:
        raise HTTPException(400, f"小分表解析失败：{e}")
    out = {k: v for k, v in data.items() if not k.startswith("_")}
    (updir / "scores.json").write_text(
        __import__("json").dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {
        "ok": True,
        "student_name": data.get("_student_name", ""),
        "exam_total": out["examTotal"],
        "n_questions": len(out["questions"]),
    }


# ---------- 3. 状态轮询 ----------

@app.get("/api/analyses/{aid}/status")
def status(aid: str):
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    return {
        "id": a["id"], "status": a["status"],
        "stage": a["stage"], "stage_name": a["stage_name"],
        "total_stages": 5, "error": a["error"],
    }


# ---------- 4. 报告 JSON ----------

@app.get("/api/analyses/{aid}/report")
def report(aid: str):
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    if a["status"] != "done":
        raise HTTPException(409, f"分析未完成（{a['status']}）")
    try:
        return pa.report_json(Path(a["student_dir"]))
    except Exception as e:
        raise HTTPException(500, f"报告生成失败: {e}")


# ---------- 5. 报告 PDF ----------

@app.get("/api/analyses/{aid}/report.pdf")
def report_pdf(aid: str):
    a = db.get_analysis(aid)
    if not a or not a["report_pdf"]:
        raise HTTPException(404, "报告 PDF 未就绪")
    p = Path(a["report_pdf"])
    if not p.exists():
        raise HTTPException(404, "报告 PDF 文件丢失")
    if p.suffix.lower() != ".pdf":
        raise HTTPException(503, "PDF 生成环境未就绪（缺 Chrome），报告内容请看页面")
    return FileResponse(p, media_type="application/pdf",
                        filename=p.name)


# ---------- 6. 试卷原卷 PDF ----------

@app.get("/api/analyses/{aid}/paper.pdf")
def paper_pdf(aid: str):
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    try:
        p = pa.paper_pdf(a["exam_slug"], PAPER_OUT)
    except Exception as e:
        raise HTTPException(500, f"试卷 PDF 失败: {e}")
    return FileResponse(p, media_type="application/pdf", filename=p.name)


# ---------- 7. 历史报告列表 ----------

@app.get("/api/analyses")
def list_all():
    return {"items": db.list_analyses()}


# ---------- 静态前端（web 构建产物）----------

WEB_DIST = ROOT / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True),
              name="web")
