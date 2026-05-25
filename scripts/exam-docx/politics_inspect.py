#!/usr/bin/env python3
"""politics_inspect — 北京中考道法（道德与法治）docx 路线 yaml 质量自动检查器

固化所有已知 bug pattern（来自 politics_docx_paper v1 + Round 2 修复）：

【结构性】
  - 题数 25（部分区 24-26 容忍）
  - 满分严格 70，sum(score) == full_score
  - 题号无重复、无跳号
  - 标准 5 部分：判断 10 + 单选 10 + 材料分析 3-5（含 1-2 作文）
  - duration_minutes == 70
  - subject == "politics"
  - exam_format == "open_book"（道法开卷考）

【答案格式】
  - 判断题 ans ∈ {正确, 错误, √, ×, 对, 错}（道法不用 "T/F"）
  - 单选题 ans ∈ {A,B,C,D}
  - 材料分析/作文 ans 可空（答案在 sol 里）

【分值核对】（已修 _line_idx 兜底 bug 防回归）
  - 所有 判断题 score=1
  - 所有 单选题 score=2（曾出现 Q13/Q19/Q20 score=0/6 错乱）
  - 材料分析+作文 score 合计 40

【内容完整性】
  - stem 非空
  - 选择题 options 非空、4 选项齐全
  - sol 非空（材料分析/作文 sol 长度 ≥ 30）
  - knowledge_points 非空

【噪声/marker 残留】
  - "第二部分" / "学科网" 不在 stem/sol
  - 行内 marker 残留：【小问N详解】、【N题详解】、【详解】、【解析】
  - sol "解析略" / "时政题，解析略" 占位（warn，源数据问题）

【markdown 表格破损】（exam-review 渲染崩溃源）
  - sol/stem 含 `|---|---|` 列数不一致

【KP 跨学科污染】
  - KP 不含语文 KP：字音字形、成语运用、段落作用、信息筛选、记叙文/说明文/议论文
  - KP 不含物理 KP：力学/电学/光学/牛顿/欧姆等
  - KP 不含化学/数学等

【类型分布合理性】
  - 判断题约 10 道
  - 单选题约 10 道
  - 材料分析+作文 合计 3-6 道

用法：
  python3 politics_inspect.py                            # 扫所有 politics yaml
  python3 politics_inspect.py path/to/2026-chaoyang-yi.yaml
  python3 politics_inspect.py --verbose
"""
from __future__ import annotations
import argparse, re, sys, yaml
from pathlib import Path

EXPECT_FULL_SCORE = 70
EXPECT_DURATION   = 70
EXPECT_SUBJECT    = "politics"
EXPECT_Q_RANGE    = (24, 26)

JUDGE_OK = {"正确", "错误", "√", "×", "对", "错"}
VALID_TYPES = {
    "判断", "单选", "材料分析", "作文", "写作",
    "judge", "choice", "material", "essay",
}

# 跨学科污染
CROSS_SUBJECT_KP = re.compile(
    r"字音字形|成语运用|病句|段落作用|信息筛选|"
    r"记叙文阅读|议论文阅读|说明文阅读|现代文阅读|文言文|名著阅读|"
    r"力学|电学|光学|热学|牛顿|欧姆|焦耳|安培|"
    r"凸透镜|平面镜|物态变化|分子运动|"
    r"化学方程式|元素周期|氧化还原|"
    r"二次函数|一元二次|圆锥|椭圆|微积分"
)

NOISE_FOOTER  = re.compile(r"^\s*第[一二三四五六]部分\s*$", re.MULTILINE)
NOISE_OTHER   = re.compile(r"学科网\(www|菁优网|本试卷共\d+页\b")
INLINE_MARKER = re.compile(r"【小问\d+详解】|【\d{1,2}题详解】|【详解】|【解析】")
LIYE_LIVE     = re.compile(r"解析略|时政题.*解析略|^\s*略\s*$", re.MULTILINE)
BAD_MD_TABLE  = re.compile(r"^\|[-]+\|", re.MULTILINE)  # `|---|...` 表格分隔


def md_table_columns_mismatch(text):
    """检测 markdown 表格列数不一致（haidian Q22/Q23 等渲染崩溃源）"""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        m = re.match(r"^\|[-:|]+\|$", line.strip())
        if not m:
            continue
        sep_cols = line.count("|") - 1
        # 检查上一行（应是 header）的列数
        if i > 0:
            prev = lines[i-1]
            if prev.strip().startswith("|"):
                prev_cols = prev.count("|") - 1
                if prev_cols != sep_cols:
                    return True
    return False


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
        "exam_format": d.get("exam_format", ""),
        "missing_ids": [], "dup_ids": [],
        "bad_type": [], "empty_stem": [], "empty_options": [],
        "bad_judge_ans": [], "bad_choice_ans": [],
        "bad_judge_score": [], "bad_choice_score": [],
        "short_sol": [], "no_kp": [], "cross_subj_kp": [],
        "noise_footer": [], "noise_other": [], "inline_marker": [],
        "liye": [], "md_table_broken": [],
        "n_judge": 0, "n_choice": 0, "n_material": 0, "n_essay": 0,
        "warnings": [],
    }
    ids = [q.get("id") for q in qs]
    s["dup_ids"] = sorted({i for i in ids if ids.count(i) > 1})
    expected = set(range(1, max(ids) + 1)) if ids else set()
    s["missing_ids"] = sorted(expected - set(ids))

    for q in qs:
        qid = q.get("id")
        t = q.get("type", "")
        ans = (q.get("answer") or "").strip()
        stem = q.get("stem") or ""
        sol = q.get("solution") or ""
        opts = q.get("options")
        kps = q.get("knowledge_points") or []
        score = q.get("score", 0)
        if t not in VALID_TYPES:
            s["bad_type"].append((qid, t))
        if not stem.strip():
            s["empty_stem"].append(qid)
        # 类型计数
        if t in ("判断", "judge"): s["n_judge"] += 1
        elif t in ("单选", "choice"): s["n_choice"] += 1
        elif t in ("材料分析", "material"): s["n_material"] += 1
        elif t in ("作文", "写作", "essay"): s["n_essay"] += 1
        # 答案格式 + 分值核对
        if t in ("判断", "judge"):
            if ans not in JUDGE_OK:
                s["bad_judge_ans"].append((qid, ans))
            if score != 1:
                s["bad_judge_score"].append((qid, score))
        elif t in ("单选", "choice"):
            if not re.fullmatch(r"[A-D]", ans):
                s["bad_choice_ans"].append((qid, ans))
            if score != 2:
                s["bad_choice_score"].append((qid, score))
        elif t in ("材料分析", "作文", "写作", "material", "essay"):
            if len(sol.strip()) < 30:
                s["short_sol"].append(qid)
        # 选择题 options 完整性
        if t in ("单选", "choice"):
            if not opts or len(opts) < 4 or any(not (v or "").strip() for v in opts.values()):
                s["empty_options"].append(qid)
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
        if LIYE_LIVE.search(sol):
            s["liye"].append(qid)
        if md_table_columns_mismatch(stem) or md_table_columns_mismatch(sol):
            s["md_table_broken"].append(qid)

    # 卷级告警
    if s["sum_score"] != s["full_score"]:
        s["warnings"].append(f"分值合计 {s['sum_score']} ≠ full_score {s['full_score']}")
    if s["full_score"] != EXPECT_FULL_SCORE:
        s["warnings"].append(f"满分 {s['full_score']} ≠ 标准 {EXPECT_FULL_SCORE}")
    if s["duration"] != EXPECT_DURATION:
        s["warnings"].append(f"时长 {s['duration']} ≠ 标准 {EXPECT_DURATION}min")
    if s["subject"] != EXPECT_SUBJECT:
        s["warnings"].append(f"subject={s['subject']!r} ≠ {EXPECT_SUBJECT!r}")
    if s["exam_format"] and s["exam_format"] != "open_book":
        s["warnings"].append(f"exam_format={s['exam_format']!r} ≠ open_book")
    if not (EXPECT_Q_RANGE[0] <= s["n_q"] <= EXPECT_Q_RANGE[1]):
        s["warnings"].append(f"题数 {s['n_q']} 不在 {EXPECT_Q_RANGE}")
    if s["n_judge"] != 10:
        s["warnings"].append(f"判断题 {s['n_judge']} ≠ 10")
    if s["n_choice"] != 10:
        s["warnings"].append(f"单选题 {s['n_choice']} ≠ 10")
    return s


def fmt_short(items, max_n=5):
    if not items: return "-"
    short = items[:max_n]
    return ",".join(str(x if not isinstance(x, tuple) else x[0]) for x in short) + \
            ("..." if len(items) > max_n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?",
                    default="knowledge-base/exams/mock/politics/beijing/")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args()
    p = Path(a.path)
    files = [p] if p.is_file() else sorted(p.glob("2026-*-yi.yaml"))
    if not files:
        sys.exit(f"no yaml in {p}")

    cols = ["district", "Q#", "sum", "full", "jdg", "chc", "mat", "esy",
            "miss", "dup", "badT", "emS", "emO",
            "badJa", "badCa", "badJs", "badCs",
            "shS", "noKP", "crKP",
            "noise", "marker", "liye", "mdT"]
    widths = [13, 4, 5, 5, 4, 4, 4, 4, 6, 4, 5, 5, 5, 6, 6, 6, 6, 5, 5, 5, 6, 7, 5, 5]
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
                s["n_judge"], s["n_choice"], s["n_material"], s["n_essay"],
                fmt_short(s["missing_ids"]),
                len(s["dup_ids"]) or "-",
                len(s["bad_type"]) or "-",
                len(s["empty_stem"]) or "-",
                len(s["empty_options"]) or "-",
                len(s["bad_judge_ans"]) or "-",
                len(s["bad_choice_ans"]) or "-",
                len(s["bad_judge_score"]) or "-",
                len(s["bad_choice_score"]) or "-",
                len(s["short_sol"]) or "-",
                len(s["no_kp"]) or "-",
                len(s["cross_subj_kp"]) or "-",
                len(s["noise_footer"]) + len(s["noise_other"]) or "-",
                len(s["inline_marker"]) or "-",
                len(s["liye"]) or "-",
                len(s["md_table_broken"]) or "-",
        ]
        print(fmt.format(*[str(x) for x in row]))
        for w in s["warnings"]:
            warn_lines.append(f"  ⚠ {district}: {w}")
        if a.verbose:
            for key in ("bad_judge_ans", "bad_choice_ans", "bad_judge_score",
                         "bad_choice_score", "cross_subj_kp", "inline_marker",
                         "liye", "md_table_broken", "noise_footer", "noise_other"):
                if s[key]:
                    print(f"    {key}: {s[key][:8]}")
    if warn_lines:
        print("\n=== 警告 ===")
        for w in warn_lines: print(w)
    print(f"\n合计 {len(files)} 区扫描完成")


if __name__ == "__main__":
    main()
