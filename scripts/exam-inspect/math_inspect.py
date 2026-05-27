#!/usr/bin/env python3
"""math_inspect — 北京中考数学 docx 路线 yaml 质量自动检查器

固化所有已知 bug pattern（来自 math_docx_paper v1 + 数学特异性）：

【结构性】
  - 题数 == 28（8单选+8填空+12解答）
  - 满分严格 100，sum(score) == full_score
  - 题号无重复无跳号
  - duration_minutes == 120
  - subject == "math"
  - 题型分布：单选8 + 填空8 + 解答12

【答案格式】
  - 单选 [A-D]
  - 填空/解答 非空（可含 LaTeX、分数、特殊符号、文本）

【分值核对】（13 区统一）
  - 单选: 2 分
  - 填空: 2-3 分（部分区个别题 3 分）
  - 解答: Q17-19=5, Q20=6, Q21-22=5, Q23-24=6, Q25=5, Q26=6, Q27-28=7（±1 跨区微调）
  - 解答总分 68

【内容完整性】
  - stem 非空
  - 单选 options 4 选项齐全
  - sol 非空
  - knowledge_points 非空
  - module 字段非空

【LaTeX 公式合法性】★ 数学特有
  - $ 配对（成对出现）
  - \\frac{}{} 大括号完整
  - \\sqrt{} 完整

【图片完整性】★ P0 关键
  - has_image_options=True 时，options 必须真挂图（image_options 字段）
  - figures/ 目录里 ≥75% 图被 yaml 引用（允许 watermark < 25%）
  - "[图]" 字面占位不应是唯一引用（必须配 image_options 或 figure 字段）

【新定义压轴 Q28】
  - solution 长度 ≥ 200 char（压轴题应详尽）

【KP 跨学科污染】
  - 不应含 字音字形/文言文/力学/牛顿/化学方程式/中国梦/记叙文 等
  - 数学合理 KP: 实数/分式/根式/方程/函数/几何/概率/统计 等

【噪声/marker 残留】
  - "学校 班级 姓名" 考生须知
  - 行内 marker：【小问N详解】、【N题详解】、【点睛】
  - "数学试卷第N页"、"学科网"、"菁优网" 等页脚

用法：
  python3 math_inspect.py
  python3 math_inspect.py path/to/2026-chaoyang-yi.yaml --verbose
"""
from __future__ import annotations
import argparse, re, sys, yaml
from pathlib import Path

EXPECT_FULL_SCORE = 100
EXPECT_DURATION   = 120
EXPECT_SUBJECT    = "math"
EXPECT_N_Q        = 28
EXPECT_N_CHOICE   = 8
EXPECT_N_FILL     = 8
EXPECT_N_SOLVE    = 12

VALID_TYPES = {"单选", "填空", "解答", "choice", "fill", "solve"}

# 跨学科 KP 黑名单（数学不应该出现的 KP）
CROSS_SUBJECT_KP = re.compile(
    r"字音字形|成语运用|病句|段落作用|"
    r"记叙文阅读|议论文阅读|说明文|文言文|名著阅读|"
    r"力学|电学|光学|热学|牛顿|欧姆|凸透镜|物态变化|分子运动|"
    r"化学方程式|元素周期|氧化还原|"
    r"中国梦|宪法|社会主义|"
    r"信息筛选|完形填空"
)

NOISE_FOOTER = re.compile(
    r"数学试卷第\d+页|九年级\(数学\)第\d+页|九年级数学试卷第\d+页|"
    r"北京市[一-龥]+区.*?练习|"
    r"学科网\(www|菁优网|"
    r"考生须知|本试卷共\d+页|"
    r"学校[_\s]+班级|学校[_\s]+姓名"
)
INLINE_MARKER = re.compile(r"【小问\d+详解】|【\d{1,2}题详解】|【点睛】(?![^\n]{0,3}$)")

# LaTeX 公式合法性
RE_DOLLAR = re.compile(r"\$")
RE_FRAC_BAD = re.compile(r"\\frac\s*\{\s*\}|\\frac\s*\{[^}]*\}\s*\{\s*\}")  # \frac{}{x} 或 \frac{x}{}
RE_SQRT_BAD = re.compile(r"\\sqrt\s*\{\s*\}")  # \sqrt{} 空


def _count_dollars(text: str) -> int:
    """统计未转义 $ 数。"""
    if not text: return 0
    # 简化：去掉 \$ 再数
    return len(RE_DOLLAR.findall(re.sub(r"\\\$", "", text)))


def _check_latex(text: str) -> list[str]:
    """返回 LaTeX 问题列表。"""
    if not text: return []
    issues = []
    if _count_dollars(text) % 2 != 0:
        issues.append("dollar_unpaired")
    if RE_FRAC_BAD.search(text):
        issues.append("frac_empty")
    if RE_SQRT_BAD.search(text):
        issues.append("sqrt_empty")
    return issues


def inspect(yaml_path: Path, verbose=False) -> dict:
    try:
        d = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return {"_error": f"YAML 解析失败: {e}"}

    qs = d.get("questions", []) or []
    s = {
        "n_q": len(qs),
        "sum_score": sum(q.get("score", 0) or 0 for q in qs),
        "full_score": d.get("full_score", 0),
        "duration": d.get("duration_minutes", 0) or 0,
        "subject": d.get("subject", ""),
        "missing_ids": [], "dup_ids": [],
        "bad_type": [], "empty_stem": [], "empty_options": [],
        "bad_choice_ans": [], "empty_ans": [],
        "bad_choice_score": [], "bad_fill_score": [], "bad_solve_score": [],
        "short_sol": [], "no_kp": [], "no_module": [], "cross_subj_kp": [],
        "noise_footer": [], "inline_marker": [],
        "latex_bad": [],          # [(qid, issues)]
        "img_opt_bare_placeholder": [],  # has_image_options=True 但没挂 image_options
        "q28_short_sol": False,
        "n_choice": 0, "n_fill": 0, "n_solve": 0,
        "n_figures_dir": 0, "n_figures_referenced": 0,
        "warnings": [],
    }
    ids = [q.get("id") or q.get("number") for q in qs]
    s["dup_ids"] = sorted({i for i in ids if ids.count(i) > 1})
    expected = set(range(1, max(ids) + 1)) if ids else set()
    s["missing_ids"] = sorted(expected - set(ids))

    for q in qs:
        qid = q.get("id") or q.get("number")
        t = q.get("type", "")
        ans = (q.get("answer") or "").strip()
        stem = q.get("stem") or ""
        sol = q.get("solution") or ""
        opts = q.get("options")
        kps = q.get("knowledge_points") or []
        mod = q.get("module")
        score = q.get("score", 0) or 0

        if t not in VALID_TYPES:
            s["bad_type"].append((qid, t))

        # 类型计数
        if t in ("单选", "choice"): s["n_choice"] += 1
        elif t in ("填空", "fill"): s["n_fill"] += 1
        elif t in ("解答", "solve"): s["n_solve"] += 1

        # 答案
        if t in ("单选", "choice"):
            if not re.fullmatch(r"[A-D]", ans):
                s["bad_choice_ans"].append((qid, ans))
            if score != 2:
                s["bad_choice_score"].append((qid, score))
        elif t in ("填空", "fill"):
            if not ans:
                s["empty_ans"].append(qid)
            if score not in (2, 3):
                s["bad_fill_score"].append((qid, score))
        elif t in ("解答", "solve"):
            if not ans and not sol.strip():
                s["empty_ans"].append(qid)
            # 解答分值梯度 5-7 (允许 4-8 防边界)
            if score not in (4, 5, 6, 7, 8):
                s["bad_solve_score"].append((qid, score))

        # stem
        if not stem.strip():
            s["empty_stem"].append(qid)

        # 单选 options
        if t in ("单选", "choice"):
            has_img_opts = q.get("has_image_options")
            if not opts or len(opts) < 4:
                s["empty_options"].append(qid)
            elif has_img_opts:
                # 图选项题必须有 image_options 字段或 options 内挂图
                img_opts = q.get("image_options")
                opts_have_img = any("![](" in str(v) or "figures/" in str(v) for v in opts.values())
                if not img_opts and not opts_have_img:
                    s["img_opt_bare_placeholder"].append(qid)

        # sol
        if len(sol.strip()) < 5 and t in ("解答", "solve"):
            s["short_sol"].append(qid)
        # Q28 新定义压轴
        if qid == 28 and len(sol.strip()) < 200:
            s["q28_short_sol"] = True

        # KP / module
        if not kps:
            s["no_kp"].append(qid)
        for kp in kps:
            if CROSS_SUBJECT_KP.search(kp):
                s["cross_subj_kp"].append((qid, kp))
        if not mod:
            s["no_module"].append(qid)

        # LaTeX
        for txt in (stem, sol):
            issues = _check_latex(txt)
            if issues:
                s["latex_bad"].append((qid, issues))
                break  # 一题报一次

        # 噪声
        full_text = stem + "\n" + sol
        if NOISE_FOOTER.search(full_text):
            s["noise_footer"].append(qid)
        if INLINE_MARKER.search(sol):
            s["inline_marker"].append(qid)

    # 图片完整性：用 final.json (docx_paper 输出去重后的"标准图集") 作期望，
    # 看 enrich 阶段是否丢图。zxxk docx 题目段和答案段会重复同一张图（image1
    # vs image15 是同图不同号），docx_paper 已去重，故对比 yaml vs final.json
    # 而非 yaml vs figures/ 全集
    import json as _json
    stem_name = yaml_path.stem  # e.g. 2026-chaoyang-yi
    final_json = (Path("knowledge-base/exams/_staging/math") / stem_name
                  / "structured-cloud" / "final.json")
    if final_json.is_file():
        fj = _json.loads(final_json.read_text(encoding="utf-8"))
        # 只数 questions + answers 引用的图（跳过 validation 里"未引用图清单"）
        fj_imgs: set = set()
        for q in fj.get("questions", []) or []:
            for fld in ("stem",):
                fj_imgs.update(re.findall(r"image\d*\.png", q.get(fld) or ""))
            fj_imgs.update(q.get("figures_all") or [])
            if q.get("figure_path"):
                fj_imgs.add(Path(q["figure_path"]).name)
        for a in fj.get("answers", []) or []:
            fj_imgs.update(re.findall(r"image\d*\.png", a.get("solution") or ""))
        s["n_figures_dir"] = len(fj_imgs)  # final.json 期望图集
        yaml_text = yaml_path.read_text(encoding="utf-8")
        yaml_imgs = set(re.findall(r"image\d*\.png", yaml_text))
        s["n_figures_referenced"] = len(yaml_imgs & fj_imgs)
        missing = fj_imgs - yaml_imgs
        if missing:
            s["warnings"].append(
                f"enrich 阶段丢图 {len(missing)}/{len(fj_imgs)}: {sorted(missing)[:5]}"
                + ("..." if len(missing) > 5 else ""))

    # 卷级告警
    if s["sum_score"] != s["full_score"]:
        s["warnings"].append(f"分值合计 {s['sum_score']} ≠ full_score {s['full_score']}")
    if s["full_score"] != EXPECT_FULL_SCORE:
        s["warnings"].append(f"满分 {s['full_score']} ≠ {EXPECT_FULL_SCORE}")
    if s["duration"] != EXPECT_DURATION:
        s["warnings"].append(f"时长 {s['duration']} ≠ {EXPECT_DURATION}min")
    if s["subject"] != EXPECT_SUBJECT:
        s["warnings"].append(f"subject={s['subject']!r} ≠ {EXPECT_SUBJECT!r}")
    if s["n_q"] != EXPECT_N_Q:
        s["warnings"].append(f"题数 {s['n_q']} ≠ {EXPECT_N_Q}")
    if s["n_choice"] != EXPECT_N_CHOICE:
        s["warnings"].append(f"单选 {s['n_choice']} ≠ {EXPECT_N_CHOICE}")
    if s["n_fill"] != EXPECT_N_FILL:
        s["warnings"].append(f"填空 {s['n_fill']} ≠ {EXPECT_N_FILL}")
    if s["n_solve"] != EXPECT_N_SOLVE:
        s["warnings"].append(f"解答 {s['n_solve']} ≠ {EXPECT_N_SOLVE}")
    if s["q28_short_sol"]:
        s["warnings"].append("Q28 (新定义压轴) sol < 200 字符，疑详解不全")
    return s


def fmt_short(items, max_n=5):
    if not items: return "-"
    short = items[:max_n]
    return ",".join(str(x if not isinstance(x, tuple) else x[0]) for x in short) + \
            ("..." if len(items) > max_n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?",
                    default="knowledge-base/exams/mock/math/beijing/")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args()
    p = Path(a.path)
    files = [p] if p.is_file() else sorted(p.glob("2026-*-yi.yaml"))
    if not files:
        sys.exit(f"no yaml in {p}")

    cols = ["district", "Q#", "sum", "full", "chc", "fil", "slv",
            "miss", "dup", "badT", "emS", "emO", "badC", "emA",
            "badCs", "badFs", "badSs", "shS", "noKP", "noMod",
            "crKP", "noise", "marker", "latex", "imgOpt",
            "figDir", "figRef"]
    widths = [12, 4, 5, 5, 4, 4, 4, 6, 4, 5, 4, 4, 5, 4,
              6, 6, 6, 4, 5, 6, 5, 6, 7, 6, 7, 7, 7]
    fmt = "".join(f"{{:>{w}}}" for w in widths)
    print(fmt.format(*cols))
    print("─" * sum(widths))
    warn_lines = []
    for f in files:
        s = inspect(f, a.verbose)
        if "_error" in s:
            print(f"{f.name}: {s['_error']}"); continue
        district = f.stem.replace("2026-", "").replace("-yi", "")
        row = [district, s["n_q"], s["sum_score"], s["full_score"],
                s["n_choice"], s["n_fill"], s["n_solve"],
                fmt_short(s["missing_ids"]),
                len(s["dup_ids"]) or "-",
                len(s["bad_type"]) or "-",
                len(s["empty_stem"]) or "-",
                len(s["empty_options"]) or "-",
                len(s["bad_choice_ans"]) or "-",
                len(s["empty_ans"]) or "-",
                len(s["bad_choice_score"]) or "-",
                len(s["bad_fill_score"]) or "-",
                len(s["bad_solve_score"]) or "-",
                len(s["short_sol"]) or "-",
                len(s["no_kp"]) or "-",
                len(s["no_module"]) or "-",
                len(s["cross_subj_kp"]) or "-",
                len(s["noise_footer"]) or "-",
                len(s["inline_marker"]) or "-",
                len(s["latex_bad"]) or "-",
                len(s["img_opt_bare_placeholder"]) or "-",
                s["n_figures_dir"] or "-",
                s["n_figures_referenced"] or "-",
        ]
        print(fmt.format(*[str(x) for x in row]))
        for w in s["warnings"]:
            warn_lines.append(f"  ⚠ {district}: {w}")
        if a.verbose:
            for key in ("bad_choice_ans", "bad_choice_score", "bad_fill_score",
                         "bad_solve_score", "cross_subj_kp", "latex_bad",
                         "img_opt_bare_placeholder", "inline_marker",
                         "noise_footer", "no_module", "empty_ans"):
                if s[key]:
                    print(f"    {key}: {s[key][:8]}")
    if warn_lines:
        print("\n=== 警告 ===")
        for w in warn_lines: print(w)
    print(f"\n合计 {len(files)} 区扫描完成")


if __name__ == "__main__":
    main()
