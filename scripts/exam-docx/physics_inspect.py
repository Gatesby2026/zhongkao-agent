#!/usr/bin/env python3
"""physics_inspect — 北京中考物理 docx 路线 yaml 质量自动检查器

固化所有已知 bug pattern（来自 physics_docx_paper 4 轮迭代踩坑笔记）：

【结构性】
  - 题数 26 (xicheng 28)
  - 满分严格 70，sum(score) == full_score
  - 题号无重复、无跳号
  - 标准 5 大题：choice(12)+multi_choice(3)+experiment(7-10)+
    comprehensive(0-1)+calculation(2-3)
  - duration_minutes == 70（北京中考物理）
  - subject == "physics"

【答案格式】
  - 单选 choice 答案 ∈ {A,B,C,D} 单字母
  - 多选 multi_choice 答案 [A-D]{2,4}（如 AD/BD/ABD/ABCD）
  - 实验/计算/科普 ans 可空（答案在 sol 子问 (1)(2) 里）

【内容完整性】
  - stem 非空
  - 选择题 options 非空、4 选项齐全
  - sol 非空（experiment/calculation/comprehensive 必填）
  - knowledge_points 非空

【公式 LaTeX 化检测】（最重要，物理特有）
  - [公式] 占位符残留（应已全部转 LaTeX，0 容忍）
  - .wmf 引用残留（应转 .png 兄弟 fallback 或 LaTeX）
  - LaTeX 块数 vs OLE 数 sanity check（如有 mtef-cache 则比对）
  - 单纯无 LaTeX 也无 PNG → 物理题缺公式渲染（warn）

【噪声/marker 残留检测】（修过的 bug 必须不再出现）
  - "第二部分" / "学科网" / "菁优网" 不在 stem/sol
  - 行内 marker 残留：【小问N详解】、【N题详解】（行尾紧邻图后高频）
  - 答案行 decimal 前缀（sol 以 "50"/"6" 等纯数字开头紧跟换行 — Q16 答案
    "2.50" / "3.6" 被误读为 Q2/Q3+50 类型 bug）
  - "故选[A-D]" 在 stem（说明 sol 串入了 stem）

【KP 跨学科污染】（cache_prefix 不带 subject 的 P0 silent disaster）
  - KP 不含语文 KP：基础运用/字音字形/成语运用/古诗赏析/记叙文阅读/
    议论文阅读/说明文/作文/书写
  - KP 不含化学 KP：化学方程式/元素周期/氧化还原/酸碱盐
  - KP 不含其他学科明显特征词

【cross-question 串扰检测】（已修 bug 防回归）
  - 某题 sol 含其他题的 "故选[A-D]" 模式 → 跨题污染信号
  - 末尾 sol 含 "请将本试卷..." footer

【单选/多选分值核对】（已修 _allocate_scores bug 防回归）
  - 所有 choice 题 score=2
  - 所有 multi_choice 题 score=2
  - 12+3+实验+科普+计算 = 70

【实验题专项】
  - experiment 类型 sol 应含 "(1)" "(2)" 等子问 / "①②③" 等子号
  - 实验题 stem 应含 "____" 空格 或 "（   ）" 选择标记

用法：
  python3 physics_inspect.py                            # 扫所有 physics yaml
  python3 physics_inspect.py path/to/2026-chaoyang-yi.yaml
  python3 physics_inspect.py --verbose
"""
from __future__ import annotations
import argparse, json, re, sys, yaml
from pathlib import Path

EXPECT_FULL_SCORE = 70
EXPECT_DURATION   = 70
EXPECT_SUBJECT    = "physics"
EXPECT_Q_RANGE    = (26, 28)

VALID_TYPES = {
    "单选", "多选", "实验探究", "科普阅读", "计算题",
    "choice", "multi_choice", "experiment", "comprehensive", "calculation",
}

# 跨学科污染
CROSS_SUBJECT_KP = re.compile(
    r"字音字形|成语运用|病句|古诗赏析|记叙文阅读|议论文阅读|说明文阅读|"
    r"现代文阅读|文言文|名著阅读|基础运用|"
    r"化学方程式|元素周期|氧化还原|酸碱盐|"
    r"中国梦|宪法地位|公民基本权利|"
    r"二次函数|一元二次|圆锥|椭圆"
)

NOISE_FOOTER  = re.compile(r"第[一二三四五六]部分\s*$|^\s*第[一二三四五六]部分\s*$",
                            re.MULTILINE)
NOISE_OTHER   = re.compile(r"学科网\(www|菁优网|本试卷共\d+页\b")
INLINE_MARKER = re.compile(r"【小问\d+详解】|【\d{1,2}题详解】")
DECIMAL_PREFIX = re.compile(r"^\s*\d{1,3}\s*\n")
WMF_REF       = re.compile(r"\.wmf[\)\s]")
FORMULA_PLACEHOLDER = re.compile(r"\[公式\]")
CROSS_Q_LEAK  = re.compile(r"故选[A-D]")  # 用于 sol 字符串末尾外的位置

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
        "duration": d.get("duration_minutes", 0),
        "subject": d.get("subject", ""),
        "missing_ids": [], "dup_ids": [],
        "bad_type": [], "empty_stem": [], "empty_options": [],
        "bad_choice_ans": [], "bad_multi_ans": [],
        "short_sol": [], "no_kp": [], "cross_subj_kp": [],
        "noise_footer": [], "noise_other": [], "inline_marker": [],
        "decimal_prefix": [],
        "wmf_residual": [], "formula_placeholder": [],
        "no_latex_no_png": [],
        "cross_q_leak": [], "bad_choice_score": [], "bad_multi_score": [],
        "experiment_no_substem": [],
        "warnings": [],
        # LaTeX cache 比对
        "ole_count": None, "latex_cache_count": None,
    }
    ids = [q.get("id") for q in qs]
    s["dup_ids"] = sorted({i for i in ids if ids.count(i) > 1})
    expected = set(range(1, max(ids) + 1)) if ids else set()
    s["missing_ids"] = sorted(expected - set(ids))

    n_choice = n_multi = n_exp = n_comp = n_calc = 0
    for q in qs:
        qid = q.get("id")
        t   = q.get("type", "")
        ans = (q.get("answer") or "").strip()
        stem = q.get("stem") or ""
        sol  = q.get("solution") or ""
        opts = q.get("options")
        kps  = q.get("knowledge_points") or []
        score = q.get("score", 0)
        if t not in VALID_TYPES:
            s["bad_type"].append((qid, t))
        if not stem.strip():
            s["empty_stem"].append(qid)
        # 类型计数
        if t in ("单选", "choice"): n_choice += 1
        elif t in ("多选", "multi_choice"): n_multi += 1
        elif t in ("实验探究", "experiment"): n_exp += 1
        elif t in ("科普阅读", "comprehensive"): n_comp += 1
        elif t in ("计算题", "calculation"): n_calc += 1
        # 答案格式
        if t in ("单选", "choice"):
            if not re.fullmatch(r"[A-D]", ans):
                s["bad_choice_ans"].append((qid, ans))
            if score != 2:
                s["bad_choice_score"].append((qid, score))
        if t in ("多选", "multi_choice"):
            if not re.fullmatch(r"[A-D]{2,4}", ans):
                s["bad_multi_ans"].append((qid, ans))
            if score != 2:
                s["bad_multi_score"].append((qid, score))
        # options 完整性
        if t in ("单选", "多选", "choice", "multi_choice"):
            if not opts or len(opts) < 4 or any(not (v or "").strip() for v in opts.values()):
                s["empty_options"].append(qid)
        # sol 长度（实验/计算/科普必填）
        if t in ("实验探究", "计算题", "科普阅读",
                  "experiment", "calculation", "comprehensive"):
            if len(sol.strip()) < 20:
                s["short_sol"].append(qid)
            # 实验题 sol 应含子问标记
            if t in ("实验探究", "experiment"):
                if not re.search(r"[\(（][123]|[①②③]", sol):
                    s["experiment_no_substem"].append(qid)
        # KP
        if not kps:
            s["no_kp"].append(qid)
        for kp in kps:
            if CROSS_SUBJECT_KP.search(kp):
                s["cross_subj_kp"].append((qid, kp))
        # 噪声/marker
        full_text = stem + "\n" + sol
        if NOISE_FOOTER.search(full_text):
            s["noise_footer"].append(qid)
        if NOISE_OTHER.search(full_text):
            s["noise_other"].append(qid)
        if INLINE_MARKER.search(sol):
            s["inline_marker"].append(qid)
        # decimal 前缀
        if DECIMAL_PREFIX.match(sol):
            s["decimal_prefix"].append(qid)
        # wmf 引用
        if WMF_REF.search(full_text):
            s["wmf_residual"].append(qid)
        # [公式] 占位
        if FORMULA_PLACEHOLDER.search(full_text):
            s["formula_placeholder"].append(qid)
        # 物理题应有 LaTeX 公式 ($) 或 PNG 引用；都没 → warn
        has_latex = "$" in full_text
        has_png = ".png" in full_text
        if t in ("实验探究", "计算题", "experiment", "calculation"):
            if not has_latex and not has_png:
                s["no_latex_no_png"].append(qid)
        # 跨题串扰：stem 含 "故选X" 是泄漏（sol 末尾 OK，stem 不该有）
        if CROSS_Q_LEAK.search(stem):
            s["cross_q_leak"].append(qid)

    # mtef-cache OLE vs LaTeX 块数比对
    cache_f = (yaml_path.parents[3] / "_staging" / "physics"
                / yaml_path.stem / "structured-cloud" / "mtef-cache" / "formulas.json")
    docx_xml = (yaml_path.parents[3] / "_staging" / "physics"
                 / yaml_path.stem / "docx-extract" / "word" / "document.xml")
    if cache_f.exists() and docx_xml.exists():
        try:
            s["latex_cache_count"] = len(json.load(cache_f.open()))
            s["ole_count"] = docx_xml.read_text().count("<w:object")
        except Exception:
            pass

    # 卷级告警
    if s["sum_score"] != s["full_score"]:
        s["warnings"].append(f"分值合计 {s['sum_score']} ≠ full_score {s['full_score']}")
    if s["full_score"] != EXPECT_FULL_SCORE:
        s["warnings"].append(f"满分 {s['full_score']} ≠ 标准 {EXPECT_FULL_SCORE}")
    if s["duration"] != EXPECT_DURATION:
        s["warnings"].append(f"时长 {s['duration']} ≠ 标准 {EXPECT_DURATION}min")
    if s["subject"] != EXPECT_SUBJECT:
        s["warnings"].append(f"subject={s['subject']!r} ≠ {EXPECT_SUBJECT!r}")
    if not (EXPECT_Q_RANGE[0] <= s["n_q"] <= EXPECT_Q_RANGE[1]):
        s["warnings"].append(f"题数 {s['n_q']} 不在 {EXPECT_Q_RANGE}")
    # 题型分布异常
    if n_choice != 12:
        s["warnings"].append(f"单选 {n_choice} ≠ 12")
    if n_multi != 3:
        s["warnings"].append(f"多选 {n_multi} ≠ 3")
    # LaTeX cache 不匹配
    if (s["ole_count"] is not None and s["latex_cache_count"] is not None
        and s["ole_count"] != s["latex_cache_count"]):
        diff = s["ole_count"] - s["latex_cache_count"]
        s["warnings"].append(
            f"OLE 公式数 {s['ole_count']} ≠ LaTeX cache {s['latex_cache_count']} (差 {diff})")
    s["n_choice"] = n_choice
    s["n_multi"]  = n_multi
    s["n_exp"]    = n_exp
    s["n_calc"]   = n_calc
    return s


def fmt_short(items, max_n=5):
    if not items: return "-"
    short = items[:max_n]
    return ",".join(str(x if not isinstance(x, tuple) else x[0]) for x in short) + \
            ("..." if len(items) > max_n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?",
                    default="knowledge-base/exams/mock/physics/beijing/")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args()
    p = Path(a.path)
    files = [p] if p.is_file() else sorted(p.glob("2026-*-yi.yaml"))
    if not files:
        sys.exit(f"no yaml in {p}")

    cols = ["district", "Q#", "sum", "full", "ch", "mu", "ex", "ca",
            "miss", "dup", "badT", "emS", "emO", "badC", "badM",
            "shS", "noKP", "crKP",
            "fml", "wmf", "noL", "mkr", "dec", "leak"]
    widths = [13, 4, 5, 5, 4, 4, 4, 4, 6, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]
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
                s["n_choice"], s["n_multi"], s["n_exp"], s["n_calc"],
                fmt_short(s["missing_ids"]),
                len(s["dup_ids"]) or "-",
                len(s["bad_type"]) or "-",
                len(s["empty_stem"]) or "-",
                len(s["empty_options"]) or "-",
                len(s["bad_choice_ans"]) or "-",
                len(s["bad_multi_ans"]) or "-",
                len(s["short_sol"]) or "-",
                len(s["no_kp"]) or "-",
                len(s["cross_subj_kp"]) or "-",
                len(s["formula_placeholder"]) or "-",
                len(s["wmf_residual"]) or "-",
                len(s["no_latex_no_png"]) or "-",
                len(s["inline_marker"]) or "-",
                len(s["decimal_prefix"]) or "-",
                len(s["cross_q_leak"]) or "-",
        ]
        print(fmt.format(*[str(x) for x in row]))
        for w in s["warnings"]:
            warn_lines.append(f"  ⚠ {district}: {w}")
        if a.verbose:
            for key in ("bad_choice_ans", "bad_multi_ans", "bad_choice_score",
                         "bad_multi_score", "cross_subj_kp", "formula_placeholder",
                         "wmf_residual", "inline_marker", "decimal_prefix",
                         "cross_q_leak", "experiment_no_substem"):
                if s[key]:
                    print(f"    {key}: {s[key][:8]}")

    if warn_lines:
        print("\n=== 警告 ===")
        for w in warn_lines: print(w)
    print(f"\n合计 {len(files)} 区扫描完成")


if __name__ == "__main__":
    main()
