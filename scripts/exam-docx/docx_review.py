#!/usr/bin/env python3
"""docx_review — 数学试卷 final.json 检测 + 可视化 HTML 工具。

对偶物理 tools/exam-review/exam_review.py，但加强：
  - 数学公式专项校验：$ 配对、{} 平衡、LaTeX 命令完整
  - HTML 用 KaTeX CDN 渲染公式（视觉验证：公式是否能正确呈现）
  - 图片用 file:// 相对路径直链（不内嵌 base64，因为数学卷 50 张图体积大）

用法：
  python3 scripts/exam-docx/docx_review.py \
    knowledge-base/exams/_staging/math/2026-chaoyang-zhen/structured-cloud/final.json
"""
from __future__ import annotations
import argparse, json, re, sys, subprocess
from pathlib import Path

# ─── 检测器 ─────────────────────────────────────────────────────────────────

CHOICE = {"choice", "multi_choice", "单选", "多选"}
FILL = {"fill_blank", "填空"}
SOL_REQUIRED = {"problem_solving", "解答", "计算", "实验探究"}
LATEX_CMD_RE = re.compile(r"\\([a-zA-Z]+)(?:\{[^{}]*\})*")
FIG_REF_RE = re.compile(r"(?:如图|图)\s*\d|示意图")


def _check_dollar_balanced(text: str) -> list[str]:
    """检查 $ 配对：奇数个 → 不平衡。"""
    errs = []
    # 去掉 \$ 转义
    t = re.sub(r"\\\$", "", text)
    n = t.count("$")
    if n % 2:
        errs.append(f"$ 不配对（{n} 个，应偶数）")
    return errs


def _check_braces_balanced(text: str) -> list[str]:
    """检查 LaTeX `{` `}` 配对（仅在 $...$ 内部）。
    排除 LaTeX 转义 `\\{` `\\}`（它们是字面括号字符，不是结构定界符）。
    """
    errs = []
    for m in re.finditer(r"\$([^$]+)\$", text):
        body = re.sub(r"\\[{}]", "", m.group(1))  # 剥掉 \{ \} 转义
        depth = 0
        for ch in body:
            if ch == "{": depth += 1
            elif ch == "}": depth -= 1
            if depth < 0:
                errs.append(f"公式 `{m.group(0)[:30]}...` `{{` `}}` 不配对")
                break
        if depth > 0:
            errs.append(f"公式 `{m.group(0)[:30]}...` 多 {depth} 个 `{{`")
    return errs


def _check_frac_complete(text: str) -> list[str]:
    """检查 \\frac{x}{y} 必须带 2 个 {}。"""
    errs = []
    for m in re.finditer(r"\$([^$]+)\$", text):
        body = m.group(1)
        # 找 \frac，应跟两个 {...}
        for fm in re.finditer(r"\\frac(.{0,40})", body):
            tail = fm.group(1)
            if not re.match(r"\{[^{}]*\}\s*\{[^{}]*\}", tail) \
               and not re.match(r"\{[^{}]*\{[^{}]*\}[^{}]*\}\s*\{", tail):
                errs.append(f"\\frac 后未跟完整 {{}}{{}}: {fm.group(0)[:40]}")
    return errs


def detect_question_issues(q: dict, figures_dir: Path) -> list[dict]:
    """逐题检测。返回 [{level, code, msg}]。"""
    issues = []
    n = q.get("number")
    t = q.get("type", "")
    stem = q.get("stem") or ""
    opts = q.get("options") or {}
    has_img = q.get("has_image_options", False)
    figs = q.get("figures_all") or []

    # 题干
    if not stem.strip():
        issues.append({"level": "error", "code": "empty_stem", "msg": "题干为空"})

    # 选择题：options 完整
    if t in CHOICE:
        if not opts and not has_img:
            issues.append({"level": "error", "code": "options_missing",
                           "msg": "选择题缺 options 且非图选项"})
        elif opts and set(opts.keys()) != {"A","B","C","D"}:
            issues.append({"level": "error", "code": "options_incomplete",
                           "msg": f"选项不全: {sorted(opts.keys())}"})

    # 解答题/计算题：要 solution（在 answers 里查）— 这里只能检测 stem 是否非空
    # 公式校验：stem + options 所有 text
    full_text = stem + "\n" + "\n".join(str(v) for v in opts.values())
    for err in _check_dollar_balanced(full_text):
        issues.append({"level": "error", "code": "latex_dollar", "msg": err})
    for err in _check_braces_balanced(full_text):
        issues.append({"level": "error", "code": "latex_brace", "msg": err})
    for err in _check_frac_complete(full_text):
        issues.append({"level": "warn", "code": "latex_frac", "msg": err})

    # 题干引图 vs figures
    refs = set(re.findall(r"图\s*(\d+)", stem))
    if FIG_REF_RE.search(stem) and not figs:
        issues.append({"level": "error", "code": "missing_figure",
                       "msg": f"题干引图但 figures_all 为空"})

    # figures 文件存在性
    for fname in figs:
        if not (figures_dir / fname).exists():
            issues.append({"level": "error", "code": "figure_missing_file",
                           "msg": f"figure 文件不存在: {fname}"})

    return issues


def detect_paper_issues(d: dict, figures_dir: Path) -> dict:
    """卷级检测。"""
    qs = d.get("questions") or []
    answers = d.get("answers") or []
    out = {"errors": [], "warnings": []}

    # 题号连续
    nums = sorted(q["number"] for q in qs)
    if nums:
        gaps = [n for n in range(nums[0], nums[-1]+1) if n not in nums]
        if gaps:
            out["errors"].append(f"题号断号: {gaps}")
        dups = sorted({n for n in nums if nums.count(n) > 1})
        if dups:
            out["errors"].append(f"题号重复: {dups}")

    # 分值合计
    fs = d.get("full_score")
    sc = sum(q.get("score", 0) for q in qs)
    if fs and abs(fs - sc) > 2:
        out["errors"].append(f"分值合计 {sc} ≠ full_score {fs}")

    # 答案数 vs 题数
    if len(answers) < len(qs):
        out["warnings"].append(f"答案 {len(answers)} < 题数 {len(qs)}")

    # 选择题 correct 覆盖度
    choice_nums = {q["number"] for q in qs if q.get("type") in CHOICE}
    has_correct = {a["number"] for a in answers if a.get("correct")}
    missing = sorted(choice_nums - has_correct)
    if missing:
        out["warnings"].append(f"选择题缺 correct: {missing}")

    return out


# ─── HTML 渲染 ──────────────────────────────────────────────────────────────

HTML_HEAD = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body, {{
    delimiters: [
      {{left:'$$', right:'$$', display:true}},
      {{left:'$', right:'$', display:false}}
    ],
    throwOnError: false
  }})"></script>
<style>
body{{font-family:-apple-system,sans-serif;max-width:900px;margin:20px auto;padding:0 20px;background:#f6f8fa}}
.q{{background:#fff;border:1px solid #d1d5da;border-radius:8px;padding:16px;margin:16px 0;position:relative}}
.q.has-err{{border-color:#d73a49;background:#ffeef0}}
.q.has-warn{{border-color:#f9c513;background:#fffbea}}
.qid{{display:inline-block;background:#0366d6;color:#fff;padding:4px 12px;border-radius:4px;font-weight:bold;margin-right:8px;font-size:14px}}
.qtype{{display:inline-block;background:#eaecef;padding:2px 8px;border-radius:3px;font-size:12px;color:#586069;margin-right:6px}}
.qscore{{color:#28a745;font-weight:bold;font-size:13px}}
.stem{{margin:12px 0;line-height:1.7;color:#24292e;white-space:pre-wrap;word-break:break-word}}
.opts{{display:grid;grid-template-columns:1fr 1fr;gap:8px 16px;margin:12px 0;font-size:14px}}
.opt{{background:#f6f8fa;padding:8px 12px;border-radius:4px}}
.figs{{margin:12px 0;display:flex;gap:8px;flex-wrap:wrap}}
.figs img{{max-width:200px;max-height:200px;border:1px solid #ccc;border-radius:3px;background:#fff}}
.ans{{margin-top:12px;padding:10px;background:#dcffe4;border-radius:4px;font-size:14px}}
.sol{{margin-top:8px;padding:10px;background:#f1f8ff;border-radius:4px;font-size:13px;color:#24292e;white-space:pre-wrap}}
.issues{{margin-top:12px;padding:10px;border-left:3px solid #d73a49;background:#ffeef0;border-radius:3px;font-size:13px}}
.issues.warn{{border-color:#f9c513;background:#fffbea}}
.issue-row{{margin:3px 0}}
.issue-row.error{{color:#cb2431}}
.issue-row.warn{{color:#735c0f}}
.paper-meta{{background:#fff;border:1px solid #d1d5da;border-radius:8px;padding:16px;margin:16px 0}}
.paper-meta h1{{margin:0 0 8px;font-size:18px}}
.stat{{display:inline-block;margin-right:16px;font-size:13px;color:#586069}}
.stat b{{color:#24292e}}
.toc{{position:fixed;top:10px;right:10px;background:rgba(255,255,255,.95);padding:10px;border:1px solid #ccc;border-radius:6px;max-height:80vh;overflow-y:auto;font-size:12px;max-width:160px}}
.toc a{{display:block;padding:2px 4px;color:#0366d6;text-decoration:none}}
.toc a.has-err{{color:#cb2431;font-weight:bold}}
.toc a.has-warn{{color:#735c0f}}
</style></head><body>"""


def _html_escape(s: str) -> str:
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))


def _render_text_with_md(text: str, figures_rel: str = "figures") -> str:
    """渲染文本：保留 $...$ 公式 + 把 ![](figures/xxx) 转 <img>。"""
    if not text: return ""
    # img
    text = re.sub(r"!\[\]\(([^)]+)\)",
                  lambda m: f'<img src="{m.group(1)}">', text)
    # 行内 escape 但保留 $ 不动
    # 简化：把 < > & 转义但保 $
    out = []
    for line in text.split("\n"):
        # 保留 LaTeX 内部，只 escape 非 $ 部分
        parts = re.split(r"(\$\$[^$]+\$\$|\$[^$]+\$)", line)
        for p in parts:
            if p.startswith("$"):
                out.append(p)
            elif p.startswith("<img"):
                out.append(p)
            else:
                # 不再 escape <img>
                p2 = re.sub(r"(?<!<)(<)(?!img)", "&lt;", p)
                p2 = p2.replace(">", "&gt;").replace("&lt;", "&lt;")
                out.append(p2)
        out.append("\n")
    return "".join(out).rstrip()


def render_html(final: dict, out_html: Path, figures_dir: Path) -> Path:
    qs = final.get("questions") or []
    answers_by_num = {a["number"]: a for a in (final.get("answers") or [])}
    paper_issues = detect_paper_issues(final, figures_dir)
    parts = [HTML_HEAD.format(title=final.get("exam") or "试卷审核")]

    # 卷级头
    n_total = len(qs)
    n_err = sum(1 for q in qs if any(i["level"]=="error"
                  for i in detect_question_issues(q, figures_dir)))
    n_warn = sum(1 for q in qs if any(i["level"]=="warn"
                  for i in detect_question_issues(q, figures_dir)))
    parts.append(f"""<div class="paper-meta">
      <h1>{_html_escape(final.get('exam') or '')}</h1>
      <span class="stat">题数 <b>{n_total}</b></span>
      <span class="stat">full_score <b>{final.get('full_score')}</b></span>
      <span class="stat">合计 <b>{sum(q.get('score',0) for q in qs)}</b></span>
      <span class="stat">含问题 <b>{n_err}err / {n_warn}warn</b></span>
    </div>""")
    if paper_issues["errors"] or paper_issues["warnings"]:
        parts.append('<div class="issues">')
        for e in paper_issues["errors"]:
            parts.append(f'<div class="issue-row error">[卷级 error] {_html_escape(e)}</div>')
        for w in paper_issues["warnings"]:
            parts.append(f'<div class="issue-row warn">[卷级 warn] {_html_escape(w)}</div>')
        parts.append('</div>')

    # TOC
    toc = ['<div class="toc"><b>TOC</b>']
    for q in qs:
        issues = detect_question_issues(q, figures_dir)
        cls = ("has-err" if any(i["level"]=="error" for i in issues)
               else "has-warn" if issues else "")
        toc.append(f'<a class="{cls}" href="#q{q["number"]}">Q{q["number"]}</a>')
    toc.append("</div>")
    parts.append("".join(toc))

    # 逐题
    for q in qs:
        n = q["number"]
        issues = detect_question_issues(q, figures_dir)
        has_err = any(i["level"]=="error" for i in issues)
        has_warn = any(i["level"]=="warn" for i in issues)
        cls = ("q has-err" if has_err else "q has-warn" if has_warn else "q")
        parts.append(f'<div id="q{n}" class="{cls}">')
        parts.append(f'<span class="qid">Q{n}</span>'
                     f'<span class="qtype">{q.get("type","?")}</span>'
                     f'<span class="qscore">{q.get("score","?")} 分</span>'
                     + (f'<span class="qtype">图选项</span>' if q.get("has_image_options") else ""))
        # stem
        parts.append(f'<div class="stem">{_render_text_with_md(q.get("stem") or "")}</div>')
        # options
        opts = q.get("options") or {}
        if opts:
            parts.append('<div class="opts">')
            for k in "ABCD":
                if k in opts:
                    parts.append(f'<div class="opt"><b>{k}</b>． '
                                 f'{_render_text_with_md(str(opts[k]))}</div>')
            parts.append('</div>')
        # figures
        figs = q.get("figures_all") or []
        if figs:
            parts.append('<div class="figs">')
            for fn in figs:
                if (figures_dir / fn).exists():
                    parts.append(f'<img src="figures/{fn}" alt="{fn}">')
                else:
                    parts.append(f'<span style="color:red">MISSING: {fn}</span>')
            parts.append('</div>')
        # answer + solution
        a = answers_by_num.get(n)
        if a:
            if a.get("correct"):
                parts.append(f'<div class="ans">✓ correct: <b>{a["correct"]}</b></div>')
            if a.get("solution"):
                parts.append(f'<div class="sol">'
                             f'{_render_text_with_md(a["solution"])}</div>')
        # issues
        if issues:
            parts.append('<div class="issues' + (' warn' if not has_err else '') + '">')
            for i in issues:
                parts.append(f'<div class="issue-row {i["level"]}">'
                             f'[{i["level"]}] {i["code"]}: {_html_escape(i["msg"])}</div>')
            parts.append('</div>')
        parts.append('</div>')  # q

    parts.append("</body></html>")
    out_html.write_text("".join(parts), encoding="utf-8")
    return out_html


# ─── 入口 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("final_json", type=Path,
                    help="docx_paper 输出的 final.json")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    fj = a.final_json.resolve()
    if not fj.exists(): sys.exit(f"找不到 {fj}")
    final = json.loads(fj.read_text(encoding="utf-8"))
    # figures_dir = final.json 同级 ../figures
    figures_dir = fj.parent.parent / "figures"
    out_html = (a.out or (fj.parent.parent / "review.html")).resolve()
    render_html(final, out_html, figures_dir)
    qs = final.get("questions") or []
    paper_iss = detect_paper_issues(final, figures_dir)
    n_q_err = sum(1 for q in qs if any(i["level"]=="error"
                  for i in detect_question_issues(q, figures_dir)))
    n_q_warn = sum(1 for q in qs if any(i["level"]=="warn"
                  for i in detect_question_issues(q, figures_dir)))
    print(f"📊 {len(qs)} 题  卷级 err={len(paper_iss['errors'])} "
          f"warn={len(paper_iss['warnings'])}  题级 err={n_q_err} warn={n_q_warn}")
    if paper_iss["errors"]:
        for e in paper_iss["errors"]: print(f"  ✗ {e}")
    if paper_iss["warnings"]:
        for w in paper_iss["warnings"]: print(f"  ⚠ {w}")
    print(f"🌐 {out_html}")
    if not a.no_open:
        subprocess.run(["open", str(out_html)])


if __name__ == "__main__":
    main()
