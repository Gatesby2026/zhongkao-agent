#!/usr/bin/env python3
"""run_paper — 单卷端到端固化编排器（图片试卷 → 知识库 YAML）v2 腾讯路线。

唯一可执行物：S0 源核验 → S1 腾讯切题（题号+stem+options+figures+answers+
表格 markdown 一次出全）→ S2 入库 enrich。每步后置门禁；幂等 + 缓存感知；
状态机 QUARANTINE / INCOMPLETE / NEEDS_REVIEW / DONE-auto；产出
<staging>/status.json 供 batch 聚合。

S1 = scripts/exam-ocr/physics_image_paper.py（腾讯 QuestionSplitOCR + GeneralAccurate
OCR + RecognizeTableAccurateOCR + paddle layout 五层 fallback；细节见
SKILL skill_exam_image_to_kb_yaml.md「v2 腾讯路线」节）。

已决参数：
  - 含图命中 ≥0.85 才算 auto-clean，余转人工 (NEEDS_REVIEW)
  - S0 页数 / S1 题数偏离同科目中位 ±30% → QUARANTINE（不进自动批）
  - 旧脏 yaml/figures 直接删除后重建（git 历史留底，磁盘不留副本）
  - 答案页判定：标准 marker + 题号倒退（min(nums)<max_seen-3）双闸

用法：
  DASHSCOPE_API_KEY=$KEY \
  TENCENT_OCR_SECRET_ID=$SID TENCENT_OCR_SECRET_KEY=$SK \
    python3 scripts/exam-ocr/run_paper.py \
      knowledge-original/<series>/<round>/<region>/<subject> --subject physics
  [--force] [--from s1|s2]  [--dry-run]
退出码：0=DONE-auto；2=NEEDS_REVIEW；3=INCOMPLETE；4=QUARANTINE；1=用法/异常
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import derive_out_dir, repo_root  # noqa: E402

PY = sys.executable
SELF_DIR = Path(__file__).resolve().parent
DEV_RATIO = 0.30          # S0 偏离同科目中位 ±30% → QUARANTINE
FIG_MIN = 0.85            # S3 含图命中率 ≥ 此值才 auto-clean
QC_BLOCKING = ("题号断号", "≠ full_score", "缺 source_page")  # 卷级硬错→INCOMPLETE


def _final_yaml_path(staging: Path) -> Path:
    """staging=exams/_staging/<subject>/<slug> → exams/mock/<subject>/beijing/<slug>.yaml"""
    subject = staging.parent.name
    slug = staging.name
    root = repo_root(staging)
    return (root / "knowledge-base" / "exams" / "mock"
            / subject / "beijing" / f"{slug}.yaml")


def _sibling_median(staging: Path) -> tuple[float | None, float | None]:
    """同科目已结构化卷的 page_count / question 数中位（S0/S2 基线）。"""
    base = staging.parent  # exams/_staging/<subject>
    pages, qs = [], []
    for fj in base.glob("*/structured-cloud/final.json"):
        if fj.parents[1] == staging:
            continue
        try:
            d = json.loads(fj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("page_count"):
            pages.append(d["page_count"])
        if d.get("questions"):
            qs.append(len(d["questions"]))
    return (statistics.median(pages) if pages else None,
            statistics.median(qs) if qs else None)


def _deviates(val: float, med: float | None) -> bool:
    return med is not None and med > 0 and abs(val - med) / med > DEV_RATIO


def _run(cmd: list[str], env: dict | None = None) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _qc_classify(staging: Path) -> tuple[str, list[str], list[str]]:
    """跑 qc_report，分流：blocking(卷级硬错) vs needs_review(可带病交付)。"""
    rc, out = _run([PY, str(SELF_DIR / "qc_report.py"), str(staging)])
    blocking = [ln.strip() for ln in out.splitlines()
                if any(k in ln for k in QC_BLOCKING)]
    nr = [ln.strip() for ln in out.splitlines()
          if ("options 不全" in ln or "缺 solution" in ln
              or "needs_review" in ln)]
    return ("blocking" if blocking else "ok"), blocking, nr


def _figure_hit_rate(staging: Path) -> tuple[float, int, int]:
    fj = staging / "structured-cloud" / "final.json"
    if not fj.exists():
        return 1.0, 0, 0
    d = json.loads(fj.read_text(encoding="utf-8"))
    # 宽匹配：覆盖"如图N"/"图N所示"/"[图]"/"示意图"/"如下图"——
    # 任何题干提到"图"的都计入分母，避免假高基线
    fig_ref = re.compile(r"图\s*\d|如图|\[图\]|如下图|示意图")
    figq = [q for q in d.get("questions", [])
            if fig_ref.search(q.get("stem") or "")]
    if not figq:
        return 1.0, 0, 0
    # 精准到题：分子改为「题号对得上磁盘文件 qNN.png」的题数，
    # 而非旧版「文件数与题数取 min」的覆盖度近似
    seen: set[str] = set()
    for d2 in (staging / "figures",
               _final_yaml_path(staging).with_suffix("") / "figures"):
        if d2.is_dir():
            seen |= {p.name for p in d2.glob("q*.png")}
    def _qnum(qid):
        m = re.search(r"(\d+)$", str(qid or ""))
        return int(m.group(1)) if m else 0
    cut = sum(1 for q in figq if f"q{_qnum(q.get('id')):02d}.png" in seen)
    return (cut / len(figq)), cut, len(figq)


def _write_status(staging: Path, st: dict) -> None:
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "status.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", type=Path)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--from", dest="from_step", default="s1",
                    choices=["s1", "s2"])
    ap.add_argument("--dry-run", action="store_true",
                    help="只跑 S0 + 读现有产物判状态，不调 OCR/LLM")
    a = ap.parse_args()

    src = a.src_dir.resolve()
    if not (src / "images").is_dir():
        print(f"[run_paper] 无 images/：{src}", file=sys.stderr); sys.exit(1)
    staging = derive_out_dir(src)
    slug = staging.name
    final_yaml = _final_yaml_path(staging)
    st: dict = {"slug": slug, "subject": a.subject, "src": str(src),
                "staging": str(staging), "final_yaml": str(final_yaml),
                "state": None, "steps": {}, "needs_review": [], "reasons": []}

    env = dict(os.environ)
    need_key = not a.dry_run
    if need_key:
        for k in ("DASHSCOPE_API_KEY", "TENCENT_OCR_SECRET_ID",
                  "TENCENT_OCR_SECRET_KEY"):
            if not env.get(k):
                print(f"[run_paper] 缺 {k}", file=sys.stderr); sys.exit(1)

    # 立即作废旧 status.json（防陈旧终态被 run_batch/Monitor 误读）；
    # 进程中途崩溃则停在 RUNNING，读者据此判"未完成"而非旧 DONE。
    st["state"] = "RUNNING"
    _write_status(staging, st)

    # ---- S0 源核验 ----
    n_img = len(list((src / "images").glob("page-*.png")))
    med_p, med_q = _sibling_median(staging)
    st["steps"]["s0"] = {"images": n_img, "median_pages": med_p}
    if _deviates(n_img, med_p):
        st["state"] = "QUARANTINE"
        st["reasons"].append(
            f"S0 页数 {n_img} 偏离同科目中位 {med_p} 超 ±{int(DEV_RATIO*100)}%"
            "（疑双卷/混答题卡，需人工核源）")
        _write_status(staging, st); print(json.dumps(st, ensure_ascii=False))
        sys.exit(4)

    order = ["s1", "s2"]
    start = order.index(a.from_step)

    # ---- S1 腾讯切题（题号+stem+options+figures+answers+表格 markdown 一次出）
    if start <= 0 and not a.dry_run:
        cmd = [PY, str(SELF_DIR / "physics_image_paper.py"), str(src),
               "--subject", a.subject]
        if a.force:
            cmd.append("--force")
        rc, out = _run(cmd, env)
        st["steps"]["s1"] = {"rc": rc, "tail": out.strip().splitlines()[-3:]}
        if rc != 0 or not (staging / "structured-cloud" / "final.json").exists():
            st["state"] = "INCOMPLETE"
            st["reasons"].append(f"S1 physics_image_paper 失败 rc={rc}")
            _write_status(staging, st); print(json.dumps(st, ensure_ascii=False))
            sys.exit(3)

    # ---- S1 门禁 ----
    verdict, blocking, nr = _qc_classify(staging)
    st["steps"]["s1_qc"] = {"verdict": verdict, "blocking": blocking}
    st["needs_review"] += nr
    if verdict == "blocking":
        st["state"] = "INCOMPLETE"
        st["reasons"] += [f"S1 卷级硬错（回源 OCR/重切，不打补丁）：{b}"
                          for b in blocking]
        _write_status(staging, st); print(json.dumps(st, ensure_ascii=False))
        sys.exit(3)
    fj = json.loads((staging / "structured-cloud" / "final.json")
                     .read_text(encoding="utf-8"))
    nq = len(fj.get("questions", []))
    if _deviates(nq, med_q):
        st["state"] = "QUARANTINE"
        st["reasons"].append(
            f"S1 题数 {nq} 偏离同科目中位 {med_q} 超 ±{int(DEV_RATIO*100)}%")
        _write_status(staging, st); print(json.dumps(st, ensure_ascii=False))
        sys.exit(4)
    rate, cut, tot = _figure_hit_rate(staging)
    st["steps"]["s1_fig_hit"] = {"rate": round(rate, 3), "cut": cut, "total": tot}
    if rate < FIG_MIN:
        st["needs_review"].append(
            f"含图命中 {cut}/{tot}={rate:.0%} < {FIG_MIN:.0%}（剩余转人工裁图）")
    # 分值校验：full_score vs 各题 score 合计
    fs = fj.get("full_score")
    sc_sum = sum(q.get("score", 0) for q in fj.get("questions", []))
    st["steps"]["s1_score"] = {"full_score": fs, "sum": sc_sum}
    if fs and sc_sum and abs(fs - sc_sum) > 2:
        st["needs_review"].append(f"分值合计 {sc_sum} ≠ full_score {fs}")

    # ---- S2 入库（先删旧脏件再重建；幂等覆盖）----
    if start <= 1 and not a.dry_run:
        if final_yaml.exists():
            final_yaml.unlink()
        old_fig = final_yaml.with_suffix("")
        if old_fig.is_dir():
            import shutil
            shutil.rmtree(old_fig)
        final_yaml.parent.mkdir(parents=True, exist_ok=True)
        cmd = [PY, str(repo_root(src) / "scripts" / "knowledge-base"
                       / "enrich_to_mock_exam.py"),
               "--input", str(staging / "structured-cloud" / "final.json"),
               "--output", str(final_yaml), "--subject", a.subject,
               "--cache-prefix", slug]
        rc, out = _run(cmd, env)
        st["steps"]["s2"] = {"rc": rc, "tail": out.strip().splitlines()[-2:]}
        if rc != 0 or not final_yaml.exists():
            st["state"] = "INCOMPLETE"
            st["reasons"].append(f"S2 enrich 失败 rc={rc}")
            _write_status(staging, st); print(json.dumps(st, ensure_ascii=False))
            sys.exit(3)

    # ---- 终态判定（双基线：自动 vs 人工终审）----
    if a.dry_run and not final_yaml.exists():
        st["state"] = "DRY"
    elif st["needs_review"]:
        st["state"] = "NEEDS_REVIEW"     # 产物已出，进 S5 人工终审
    else:
        st["state"] = "DONE-auto"        # 自动产出基线达标
    _write_status(staging, st)
    print(json.dumps(st, ensure_ascii=False))
    sys.exit({"DONE-auto": 0, "NEEDS_REVIEW": 2,
              "INCOMPLETE": 3, "QUARANTINE": 4}.get(st["state"], 0))


if __name__ == "__main__":
    main()
