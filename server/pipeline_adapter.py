"""把 scripts/ 的三段流水线包装成后端可调用的函数。

不重写算法，只做：
  - 路径解析（exam_slug → KB yaml / 试卷 PNG 目录）
  - run_report：跑 build_report.build() 出 PDF（子进程，便于解析阶段）
  - report_json：复用 lib.schemas + lib.aggregate + .cache 产结构化 JSON
  - paper_pdf：跑 mock_exam_to_pdf 出试卷原卷 PDF
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SR_DIR = ROOT / "scripts" / "student-report"
KB_ROOT = ROOT / "knowledge-base" / "exams"   # 下含 mock/ zhenti/ analysis/

SUBJECT_EN2DIR = {  # exam_slug 末段 → exams/<kind>/ 下科目子目录
    "physics": "physics", "math": "math", "chinese": "chinese",
    "english": "english", "politics": "politics",
}


def kb_yaml_for(exam_slug: str) -> Path | None:
    """2026-chaoyang-yi-physics → exams/{mock,zhenti}/physics/beijing/2026-chaoyang-yi.yaml

    搜 mock/ 与 zhenti/；兼容两种命名：
      新：<dir=subject>/beijing/2026-chaoyang-yi.yaml（科目由目录隐含）
      旧：<dir=subject>/beijing/2026-chaoyang-yi-physics.yaml
    """
    parts = exam_slug.split("-")
    if len(parts) < 4:
        return None
    subj = parts[-1]
    slug_no_subj = "-".join(parts[:-1])  # 2026-chaoyang-yi
    for kind in ("mock", "zhenti"):
        base = KB_ROOT / kind / SUBJECT_EN2DIR.get(subj, subj) / "beijing"
        for cand in (base / f"{slug_no_subj}.yaml", base / f"{exam_slug}.yaml"):
            if cand.exists():
                return cand
    return None


# ---------- 跑完整报告（PDF）----------

# build_report.py stdout 标记 → (stage_idx, 阶段名)
STAGE_MARKERS = [
    ("📄 试卷:",            (1, "识别考试信息")),
    ("👤 学生目录:",        (2, "识别答题卡作答")),
    ("逐失分题归因",        (3, "对照标准答案")),
    ("整卷综合诊断",        (4, "AI 分析失分主因")),
    ("Markdown →",          (5, "生成提分建议")),
]


def run_report(student_dir: Path, on_stage=None) -> Path:
    """跑 build_report.build()（子进程），解析 stdout 推进阶段。返回 PDF 路径。"""
    env = dict(os.environ)
    env.setdefault("DASHSCOPE_API_KEY",
                   os.environ.get("DASHSCOPE_API_KEY", ""))
    cmd = [sys.executable, str(SR_DIR / "build_report.py"),
           "--student-dir", str(student_dir)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            env=env, cwd=str(ROOT), bufsize=1)
    pdf_path = None
    md_path = None
    for line in proc.stdout:
        line = line.rstrip()
        for marker, (idx, name) in STAGE_MARKERS:
            if marker in line and on_stage:
                on_stage(idx, name)
        mp = re.search(r"Markdown → (.+\.md)", line)
        if mp:
            md_path = Path(mp.group(1).strip())
        m = re.search(r"PDF → (.+\.pdf)", line)
        if m:
            pdf_path = Path(m.group(1).strip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"build_report 退出码 {proc.returncode}")

    slug = student_dir.name
    ls_dir = ROOT / "learning situation"
    if pdf_path is None:
        for p in ls_dir.glob(f"*_{slug}_学情报告.pdf"):
            pdf_path = p
            break
    if md_path is None:
        for p in ls_dir.glob(f"*_{slug}_学情报告.md"):
            md_path = p
            break

    # PDF 优先；无 Chrome 时降级返回 MD（report JSON 仍可用，仅 PDF 下载缺）
    if pdf_path and pdf_path.exists():
        return pdf_path
    if md_path and md_path.exists():
        return md_path
    raise RuntimeError("未找到生成的报告（PDF/MD 均缺）")


# ---------- 结构化报告 JSON（报告屏渲染用）----------

def report_json(student_dir: Path) -> dict:
    """复用 lib 产结构化数据；LLM 部分走 .cache（build 跑过即命中）。"""
    sys.path.insert(0, str(SR_DIR))
    from lib import aggregate as agg              # noqa
    from lib import analyze                        # noqa
    from lib.schemas import load_exam_view         # noqa
    from lib.textfmt import fix_latex_escape      # noqa
    import build_report as br                      # noqa

    standard = br.infer_standard(student_dir)
    if not standard or not Path(standard).exists():
        raise RuntimeError("找不到标准答案 yaml")

    exam = load_exam_view(Path(standard), student_dir)
    st = agg.overall_stats(exam)
    mods = agg.module_mastery(exam)
    lost = agg.lost_questions(exam)

    # v4：fix_latex_escape 扩 \[<cmd>{...}]→\<cmd>{...} + max_tokens 8192
    cache_prefix = f"report-v4-{exam.student_name}-{student_dir.name}"

    wrong = []
    for q in lost:
        per = analyze.analyze_question(q, cache_key=f"{cache_prefix}-{q.qid}")
        wrong.append({
            "qid": q.qid,
            "type_cn": q.type_cn,
            "module_cn": q.module_cn,
            "lost": q.lost,
            "score": q.score,
            "knowledge_points": q.knowledge_points,
            "error_type": per.get("errorType", ""),
            # LLM 输出含 LaTeX，必经 fix_latex_escape 规范化转义
            "why_wrong": [fix_latex_escape(x) for x in (per.get("whyWrong") or [])],
            "fix": [fix_latex_escape(x) for x in (
                per.get("solveCorrectly") or per.get("howToFix")
                or per.get("fix") or [])],
        })

    return {
        "student_name": exam.student_name,
        "exam_title": exam.exam_title,
        "subject": exam.subject,
        "exam_slug": exam.exam_slug,
        "total_scored": st["total_scored"],
        "full_score": st["full_score"],
        "rate": st["rate"],
        "n_questions": st["n_questions"],
        "n_lost": st["n_lost"],
        "lost_total": st["lost_total"],
        "modules": [
            {"name": m["module_cn"], "scored": m["scored"],
             "full": m["full"], "rate": m["rate"],
             "lost_qs": m["lost_qs"]}
            for m in mods
        ],
        "wrong_questions": wrong,
        "score_source": _score_source(student_dir),
    }


def _score_source(student_dir: Path) -> str:
    """teacher=老师小分（精确） / auto=系统自动判分（估算）。
    无标记（reference 演示用真实小分）按 teacher。"""
    m = student_dir / ".score_source"
    if m.exists():
        return m.read_text(encoding="utf-8").strip() or "teacher"
    return "teacher"


# ---------- 试卷原卷 PDF ----------

def _images_dir_for(exam_slug: str) -> Path | None:
    """2026-chaoyang-yi-physics → knowledge-original/.../yimo/chaoyang/physics/images"""
    parts = exam_slug.split("-")
    if len(parts) < 4:
        return None
    year, district, exam_t, subj = parts[0], parts[1], parts[2], parts[-1]
    folder = {"yi": "yimo", "er": "ermo", "san": "sanmo"}.get(exam_t, "yimo")
    d = (ROOT / "knowledge-original" / f"beijing-mock-{year}" / folder /
         district / subj / "images")
    return d if d.exists() else None


def paper_pdf(exam_slug: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = out_dir / f"{exam_slug}.pdf"
    if out_pdf.exists():
        return out_pdf
    images_dir = _images_dir_for(exam_slug)
    if not images_dir:
        raise RuntimeError(f"找不到试卷原图目录: {exam_slug}")
    sys.path.insert(0, str(ROOT / "scripts" / "knowledge-base"))
    from mock_exam_to_pdf import stitch_paper_pdf   # noqa
    stitch_paper_pdf(images_dir, out_pdf)
    return out_pdf
