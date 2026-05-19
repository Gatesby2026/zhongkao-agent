#!/usr/bin/env python3
"""试卷审核工具 — Mock-exam YAML 内容检查 / 可视化 / 手工标注

加载知识库里的 mock-exam YAML，自动检测常见质量问题（缺答案、option 不全、
solution 为空等），生成自包含 HTML 在浏览器中打开。审核状态（确认/标记/备注）
保存在浏览器 localStorage，无需后端。

用法：
    # 单文件
    exam-review knowledge-base/exams/mock/physics/beijing/2026-chaoyang-yi.yaml

    # 某科目所有文件
    exam-review --subject physics

    # 全部科目
    exam-review --all
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import webbrowser
from pathlib import Path

import yaml

TOOL_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = TOOL_DIR / "templates" / "index.html"

# 知识库根目录：tools/exam-review/ → 上两级 = repo 根
REPO_ROOT = TOOL_DIR.parent.parent
DEFAULT_EXAMS_ROOT = REPO_ROOT / "knowledge-base" / "exams" / "mock"


# ─── 检测规则 ────────────────────────────────────────────────────────────────

VALID_MODULES = {
    "mechanics", "soundLightHeat", "electricity", "experiments",
    "numbersAndExpressions", "equationsAndInequalities", "functions",
    "geometryComprehensive", "triangles", "quadrilaterals", "circles",
    "statisticsAndProbability",
    "chinese", "writing", "reading", "classical",
    "vocabulary", "grammar", "listening", "speaking",
    "politics", "history", "geography", "biology", "chemistry",
}

SOLUTION_REQUIRED = {"计算", "解答", "实验探究"}
CHOICE_ANSWER_RE = re.compile(r"^[A-D]{1,4}$")
SINGLE_ANSWER_RE = re.compile(r"^[A-D]$")


def detect_issues(q: dict) -> list[dict]:
    """逐题检测：内容完整性 / 合法性。返回 [{code, level, msg}]。

    检测项与 OCR 实现无关，兼容新 schema（stem + options dict）和旧 schema。
    """
    issues = []

    stem = str(q.get("stem", "") or q.get("question", "") or "").strip()
    opts = q.get("options")
    has_img = q.get("has_image_options", False)
    ans = str(q.get("answer", "") or "").strip()
    sol = str(q.get("solution", "") or "").strip()
    qtype = q.get("type", "")
    score = q.get("score", None)
    qc = q.get("qc_status", "")

    if not stem:
        issues.append({"code": "empty_stem", "level": "error", "msg": "stem（题干）为空"})

    if score is None or score == 0:
        issues.append({"code": "zero_score", "level": "error",
                       "msg": f"score={score}，分值异常"})

    if not ans:
        issues.append({"code": "no_answer", "level": "error", "msg": "answer 为空"})

    if ans:
        if qtype == "单选" and not SINGLE_ANSWER_RE.match(ans):
            issues.append({"code": "answer_format", "level": "warn",
                           "msg": f'单选题 answer="{ans}"，应为单个字母 A-D'})
        elif qtype == "多选" and not CHOICE_ANSWER_RE.match(ans):
            issues.append({"code": "answer_format", "level": "warn",
                           "msg": f'多选题 answer="{ans}"，应为 A-D 的组合'})

    if qtype in {"单选", "多选"}:
        if opts is None and not has_img:
            if "stem" in q:  # 新 schema 才报这个
                issues.append({"code": "options_missing", "level": "error",
                               "msg": "选择题缺少 options 字段"})
        elif isinstance(opts, dict):
            missing = sorted({"A", "B", "C", "D"} - set(opts.keys()))
            if missing:
                issues.append({"code": "options_incomplete", "level": "error",
                               "msg": f'选择题缺少选项 {"/".join(missing)}'})
            elif not has_img:
                empty = [k for k, v in opts.items()
                         if not str(v).strip() or v == "[图]"]
                if empty:
                    issues.append({"code": "options_empty_content", "level": "error",
                                   "msg": f'选项 {"/".join(empty)} 内容为空或图片'})

    if qtype in SOLUTION_REQUIRED:
        if not sol or sol == "__MISSING__":
            issues.append({"code": "no_solution", "level": "warn",
                           "msg": f"{qtype}题 solution 未填写"})

    if not q.get("knowledge_points"):
        issues.append({"code": "no_kp", "level": "warn", "msg": "knowledge_points 为空"})

    mod = q.get("module", "")
    if mod and mod not in VALID_MODULES:
        issues.append({"code": "bad_module", "level": "warn",
                       "msg": f'module "{mod}" 不在已知列表'})

    if qc == "needs_review":
        note = q.get("qc_note", "")
        if note:
            issues.append({"code": "qc_flag", "level": "warn",
                           "msg": f"[生成时已标记] {note}"})

    return issues


def check_paper(data: dict) -> list[dict]:
    """卷级检查：分值合计、题数、重复 id。"""
    paper_issues = []

    full_score = data.get("full_score", 0)
    questions = data.get("questions", [])
    total_q = data.get("total_questions", 0)

    score_sum = sum(q.get("score", 0) for q in questions)
    if score_sum != full_score:
        paper_issues.append({"code": "score_mismatch",
                             "msg": f"分值合计 {score_sum} ≠ full_score {full_score}"})

    if len(questions) != total_q:
        paper_issues.append({"code": "count_mismatch",
                             "msg": f"实际题数 {len(questions)} ≠ total_questions {total_q}"})

    ids = [q.get("id") for q in questions]
    seen, dups = set(), set()
    for i in ids:
        if i in seen:
            dups.add(i)
        seen.add(i)
    if dups:
        paper_issues.append({"code": "dup_id", "msg": f"重复 id: {sorted(dups)}"})

    return paper_issues


# ─── 数据加载 ────────────────────────────────────────────────────────────────

def _load_figure_b64(yaml_path: Path, figure_rel: str):
    """题目 figure 图片读为 base64 data URL，便于内嵌到 HTML（自包含）。"""
    img_path = yaml_path.parent / figure_rel
    if not img_path.exists():
        return None
    try:
        mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


def load_file(path: Path) -> dict:
    """加载单个 YAML 文件，附加检测结果和图片 base64。"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    questions = data.get("questions", [])
    for q in questions:
        q["_issues"] = detect_issues(q)
        fig_rel = q.get("figure")
        q["_figure_b64"] = _load_figure_b64(path, fig_rel) if fig_rel else None
    data["_paper_issues"] = check_paper(data)
    data["_path"] = str(path)
    data["_filename"] = path.name
    return data


def collect_files(file_arg: str | None, subject: str | None,
                   all_subjects: bool,
                   root: Path = DEFAULT_EXAMS_ROOT) -> list[Path]:
    """根据 CLI 参数收集要审核的 YAML 文件列表。"""
    if file_arg:
        p = Path(file_arg)
        if not p.is_absolute():
            # 相对路径：先按 cwd 找，找不到再按 repo 根找
            cand = Path.cwd() / p
            if cand.exists():
                return [cand]
            cand = REPO_ROOT / p
            if cand.exists():
                return [cand]
        return [p]
    if subject:
        return sorted((root / subject).rglob("*.yaml"))
    if all_subjects:
        return sorted(root.rglob("*.yaml"))
    return []


# ─── HTML 拼装 ───────────────────────────────────────────────────────────────

def build_html(papers: list[dict]) -> str:
    """读模板文件，注入 papers JSON，返回完整 HTML 字符串。"""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"找不到模板：{TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    def clean(p):
        out = {k: v for k, v in p.items() if not k.startswith("_")}
        out["_path"] = p["_path"]
        out["_filename"] = p["_filename"]
        out["_paper_issues"] = p.get("_paper_issues", [])
        out["questions"] = []
        for q in p.get("questions", []):
            qc = dict(q)
            qc["_issues"] = q.get("_issues", [])
            qc["_figure_b64"] = q.get("_figure_b64")
            qc["id"] = str(q.get("id", ""))
            out["questions"].append(qc)
        return out

    cleaned = [clean(p) for p in papers]
    papers_json = json.dumps(cleaned, ensure_ascii=False, indent=None)
    return template.replace("__PAPERS_JSON__", papers_json)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="exam-review",
        description="Mock-exam YAML 手工审核工具（生成可视化 HTML）",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("file", nargs="?", help="单个 YAML 文件路径")
    group.add_argument("--subject", "-s",
                       help="科目目录名（如 physics）；扫描 knowledge-base/exams/mock/<subject>/")
    group.add_argument("--all", "-a", action="store_true",
                       help="扫描全部科目")
    parser.add_argument("--out", "-o", help="输出 HTML 路径（默认临时文件，自动打开浏览器）")
    parser.add_argument("--no-open", action="store_true", help="只生成 HTML，不打开浏览器")
    parser.add_argument("--exams-root", type=Path, default=DEFAULT_EXAMS_ROOT,
                       help=f"试卷库根目录（默认 {DEFAULT_EXAMS_ROOT}）")
    args = parser.parse_args()

    files = collect_files(args.file, args.subject, args.all, root=args.exams_root)
    if not files:
        print("❌ 未找到 YAML 文件，请检查路径", file=sys.stderr)
        sys.exit(1)

    print(f"📂 加载 {len(files)} 个文件…")
    papers = []
    for f in files:
        try:
            papers.append(load_file(f))
            print(f"  ✓ {f}")
        except Exception as e:
            print(f"  ✗ {f}: {e}", file=sys.stderr)

    if not papers:
        print("❌ 没有成功加载任何文件", file=sys.stderr)
        sys.exit(1)

    total_q = sum(len(p.get("questions", [])) for p in papers)
    total_issues = sum(
        sum(len(q.get("_issues", [])) for q in p.get("questions", []))
        for p in papers
    )
    print(f"\n📊 共 {len(papers)} 份试卷，{total_q} 道题，检测到 {total_issues} 处问题")

    html = build_html(papers)

    if args.out:
        out_path = args.out
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
    else:
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8",
            prefix="exam-review-",
        )
        tf.write(html)
        tf.flush()
        out_path = tf.name

    print(f"🌐 生成: {out_path}")
    if not args.no_open:
        webbrowser.open(f"file://{os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
