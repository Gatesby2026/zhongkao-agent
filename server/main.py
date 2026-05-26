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
import imgnorm                  # noqa: E402

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

MAX_PHOTOS = 12         # 上传张数上限（P1.2 / C-选 2）
MAX_PHOTO_BYTES = 15 * 1024 * 1024   # 单张原始字节上限 15MB


@app.post("/api/analyses")
async def create_analysis(files: list[UploadFile] = File(default=[])):
    aid = uuid.uuid4().hex[:12]

    if files:
        if len(files) > MAX_PHOTOS:
            raise HTTPException(
                413, f"一次最多上传 {MAX_PHOTOS} 张照片（你传了 {len(files)} 张），请删减")
        sdir = WEB_STUDENTS / aid / REF_EXAM_SLUG
        photos = sdir / "answer-card-photos"
        photos.mkdir(parents=True, exist_ok=True)
        saved = 0
        bad = 0
        oversize = 0
        for f in files:
            data = await f.read()
            if len(data) < 1024:
                continue
            if len(data) > MAX_PHOTO_BYTES:
                oversize += 1
                continue
            saved += 1
            # 关键：手机照片带 EXIF 方向，必须先按 EXIF 旋转到位、
            # 去 EXIF、统一为正立 JPEG，否则 OCR 看歪图、裁切区域全错。
            # 统一落盘为 page-NN.jpg（含 HEIC 转码）。
            try:
                imgnorm.normalize_bytes_to_upright_jpeg(
                    data, photos / f"page-{saved:02d}.jpg")
            except Exception:
                saved -= 1
                bad += 1
        if saved == 0:
            reasons = []
            if bad: reasons.append("图片解码失败")
            if oversize: reasons.append(f"{oversize} 张单张 >15MB")
            tail = ("（" + "；".join(reasons) + "）") if reasons else ""
            raise HTTPException(400, "未收到有效答题卡图片" + tail)
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
def start_pipeline(aid: str, student_name: str = ""):
    a = db.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    if a["status"] != "ready_confirm":
        raise HTTPException(409, "考试未识别/未确认，无法开始分析")

    # 家长在确认页纠正了学生姓名 → 覆盖 OCR 结果（影响报告抬头 + 归档）
    name = (student_name or "").strip()
    if name and name != (a["student_name"] or ""):
        import json
        sdir = Path(a["student_dir"])
        sj = sdir / "student.json"
        try:
            cur = json.loads(sj.read_text(encoding="utf-8")) if sj.exists() else {}
        except Exception:
            cur = {}
        cur["name"] = name
        sj.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        db.set_exam_info(aid, name, a["exam_slug"], str(sdir))

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

    # 按扩展名分流（xlsx / csv / image）；image 失败 → 422 让前端提示
    # "换 xlsx 或转 AI 自动判分"（口径 A-选 1）
    import parse_scores
    try:
        data = parse_scores.parse_scores(raw)
    except ValueError as e:
        # image OCR 失败 / 格式不识别 / 数据全空 — 客户端可消化的失败
        is_image = ext in (".jpg", ".jpeg", ".png", ".heic", ".webp")
        raise HTTPException(422 if is_image else 400,
                            f"小分表解析失败：{e}")
    except Exception as e:
        raise HTTPException(400, f"小分表解析失败：{type(e).__name__}: {e}")
    # 落盘：保留 _source / _warnings（schemas 后续暴露给报告 data_quality）
    out = {k: v for k, v in data.items() if k != "_student_name"}
    (updir / "scores.json").write_text(
        __import__("json").dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {
        "ok": True,
        "student_name": data.get("_student_name", ""),
        "source": data.get("_source", "xlsx"),
        "warnings": data.get("_warnings", []),
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


# ---------- 6a. KB 覆盖范围（首页展示已支持哪些卷）----------

_COVERAGE_CACHE: dict | None = None
_COVERAGE_CACHE_AT: float = 0
KB_MOCK_ROOT = ROOT / "knowledge-base" / "exams" / "mock"

# 科目展示顺序（按家长心智的"中考重要度"，非字母）
SUBJECT_ORDER_CN = ["语文", "数学", "英语", "物理", "道法", "化学", "历史"]
EN2CN_SUBJECT = {"chinese": "语文", "math": "数学", "english": "英语",
                 "physics": "物理", "politics": "道法",
                 "chemistry": "化学", "history": "历史"}
# 区名展示顺序（城区→近郊→远郊，按家长习惯）
DISTRICT_ORDER_CN = [
    "海淀", "西城", "东城", "朝阳", "丰台", "石景山",
    "顺义", "门头沟", "昌平", "房山", "通州", "大兴",
    "延庆", "平谷", "怀柔", "密云", "燕山",
]
EN2CN_DISTRICT = {
    "haidian": "海淀", "xicheng": "西城", "dongcheng": "东城", "chaoyang": "朝阳",
    "fengtai": "丰台", "shijingshan": "石景山", "shunyi": "顺义",
    "mentougou": "门头沟", "changping": "昌平", "fangshan": "房山",
    "tongzhou": "通州", "daxing": "大兴", "yanqing": "延庆", "pinggu": "平谷",
    "huairou": "怀柔", "miyun": "密云", "yanshan": "燕山",
}
EXAM_TYPE_CN = {"yi": "一模", "er": "二模", "san": "三模"}


@app.get("/api/coverage")
def coverage():
    """扫 knowledge-base/exams/mock/<subject>/beijing/<year>-<district>-<type>.yaml
    聚合"已支持的科目 × 区 × 模次"。1h 内存缓存。"""
    global _COVERAGE_CACHE, _COVERAGE_CACHE_AT
    if _COVERAGE_CACHE and time.time() - _COVERAGE_CACHE_AT < 3600:
        return _COVERAGE_CACHE
    import re
    # subject_en → {exam_type_en → {year → [district_en, ...]}}
    raw: dict = {}
    for subj_dir in KB_MOCK_ROOT.iterdir() if KB_MOCK_ROOT.exists() else []:
        if not subj_dir.is_dir(): continue
        beijing = subj_dir / "beijing"
        if not beijing.is_dir(): continue
        for f in beijing.glob("*.yaml"):
            m = re.match(r"^(\d{4})-([a-z]+)-(yi|er|san)\.yaml$", f.name)
            if not m: continue
            year, district_en, et = m.group(1), m.group(2), m.group(3)
            (raw.setdefault(subj_dir.name, {})
                .setdefault(et, {})
                .setdefault(year, [])
                .append(district_en))
    # 输出 - 按学科顺序聚合
    subjects_out = []
    for cn in SUBJECT_ORDER_CN:
        en = next((k for k, v in EN2CN_SUBJECT.items() if v == cn), None)
        if not en or en not in raw: continue
        type_blocks = []
        for et_en in ("yi", "er", "san"):
            et_data = raw[en].get(et_en, {})
            if not et_data: continue
            # 聚合各年份的区,目前只 2026
            all_districts_en: set = set()
            for yr, ds in et_data.items():
                all_districts_en.update(ds)
            # 区按 DISTRICT_ORDER_CN 排
            districts_cn = [EN2CN_DISTRICT.get(d, d) for d in all_districts_en]
            districts_cn.sort(key=lambda x: DISTRICT_ORDER_CN.index(x)
                              if x in DISTRICT_ORDER_CN else 999)
            type_blocks.append({
                "exam_type_cn": EXAM_TYPE_CN.get(et_en, et_en),
                "exam_type_en": et_en,
                "n_districts": len(districts_cn),
                "districts": districts_cn,
                "years": sorted(et_data.keys()),
            })
        if type_blocks:
            subjects_out.append({
                "subject_cn": cn,
                "subject_en": en,
                "by_exam_type": type_blocks,
            })
    total_papers = sum(
        b["n_districts"]
        for s in subjects_out
        for b in s["by_exam_type"])
    _COVERAGE_CACHE = {
        "subjects": subjects_out,
        "total_papers": total_papers,
        "city": "北京",
    }
    _COVERAGE_CACHE_AT = time.time()
    return _COVERAGE_CACHE


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
