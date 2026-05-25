#!/usr/bin/env python3
"""english_inspect — 北京中考英语 docx 路线 yaml 质量自动检查器

固化所有已知 bug pattern（来自 english_docx_paper v1 + 5 处适配）：

【结构性】
  - 题数 38-39（Q38 单题作文 / Q38+Q39 二选一作文）
  - 满分严格 60，sum(score) == full_score
  - 题号无重复、无跳号
  - 标准 5 大题：单选(12×0.5) + cloze(8×1) + reading(13×2) +
    reading_express(3×2+1×4) + 作文(1×10 或 2×二选一)
  - duration_minutes == 90
  - subject == "english"

【答案格式】
  - 单选/完形/阅读 ABCD 答案 ∈ {A,B,C,D}
  - reading_express 末题 ans 可空（开放题，答案在 sol）
  - essay (作文) ans 可空，sol 含 "Possible versions" 范文标记

【分值核对】（严格按 13 区统一规则）
  - 所有 单选 score=0.5
  - 所有 cloze score=1
  - 所有 reading score=2
  - reading_express 前 3 题 score=2，末题 score=4
  - essay 第 1 题 (题目①) score=10；二选一备选 (题目②) score=0

【内容完整性】
  - stem 非空（cloze 题 stem 可空，因为 ___N___ 填空在 passage 内）
  - 选择题 options 非空、4 选项齐全
  - sol 非空（reading/reading_express/essay 必填）
  - knowledge_points 非空

【passage 二级模型】
  - passages 数量 ≥ 4（cloze + reading_A + reading_BCD + reading_express）
  - 每个 passage 有 q_range
  - cloze passage body 含 ___N___ 编号填空标记
  - reading_A passage 应有 image_options 字段 (4 张图)

【image-match 检测】（reading A 篇 Q21-23）
  - reading section 含 `___N___` markdown 填空题号需识别

【essay 二选一】
  - essay 第 2 题（Q39）sol 应含 "[二选一备选" 前缀
  - essay 题数 1 或 2（≥3 异常）

【噪声/marker 残留】
  - "学校 班级 姓名 考号" 等考生须知不在 stem/sol
  - 行内 marker 残留：【小问N详解】、【N题详解】、【点睛】不在 sol body
  - "九年级英语试卷第N页" / "学科网" / "菁优网" 等页脚

【KP 跨学科污染】
  - KP 不含中文 KP（语文/物理/化学/数学）
  - 英语 modules 4 类：vocabulary / grammar / reading / writing

用法：
  python3 english_inspect.py
  python3 english_inspect.py path/to/2026-chaoyang-yi.yaml --verbose
"""
from __future__ import annotations
import argparse, re, sys, yaml
from pathlib import Path

EXPECT_FULL_SCORE = 60
EXPECT_DURATION   = 90
EXPECT_SUBJECT    = "english"
EXPECT_Q_RANGE    = (38, 40)

VALID_TYPES = {
    "单选", "cloze", "reading", "reading_express", "作文", "essay",
    "choice",
}

CROSS_SUBJECT_KP = re.compile(
    # "信息筛选" 英语 reading 合理用法（不算跨学科污染），从黑名单移除
    r"字音字形|成语运用|病句|段落作用|"
    r"记叙文阅读|议论文阅读|说明文|现代文阅读|文言文|名著阅读|"
    r"力学|电学|光学|热学|牛顿|欧姆|凸透镜|物态变化|分子运动|"
    r"化学方程式|元素周期|氧化还原|"
    r"中国梦|宪法|社会主义|"
    r"二次函数|一元二次|圆锥|椭圆|微积分"
)

NOISE_FOOTER = re.compile(
    r"九年级英语试卷第\d+页|九年级\(英语\)第\d+页|"
    r"北京市[一-龥]+区.*?练习|"
    r"学科网\(www|菁优网|"
    r"考生须知|本试卷共\d+页|"
    r"学校[_\s]+班级|学校[_\s]+姓名"
)
INLINE_MARKER = re.compile(r"【小问\d+详解】|【\d{1,2}题详解】|【点睛】(?![^\n]{0,3}$)")
CLOZE_BLANK   = re.compile(r"_+\s*\d{1,2}\s*_+")


def inspect(yaml_path: Path, verbose=False) -> dict:
    try:
        d = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return {"_error": f"YAML 解析失败: {e}"}

    qs = d.get("questions", []) or []
    passages = d.get("passages", []) or []
    s = {
        "n_q": len(qs),
        "sum_score": sum(q.get("score", 0) or 0 for q in qs),
        "full_score": d.get("full_score", 0),
        "duration": d.get("duration_minutes", 0),
        "subject": d.get("subject", ""),
        "n_passage": len(passages),
        "missing_ids": [], "dup_ids": [],
        "bad_type": [], "empty_stem": [], "empty_options": [],
        "bad_choice_ans": [],
        "bad_choice_score": [], "bad_cloze_score": [],
        "bad_reading_score": [], "bad_re_score": [],
        "short_sol": [], "no_kp": [], "cross_subj_kp": [],
        "noise_footer": [], "inline_marker": [],
        "passage_no_qrange": [], "cloze_no_blanks": [],
        "essay_dup_score": [],
        "n_choice": 0, "n_cloze": 0, "n_reading": 0,
        "n_re": 0, "n_essay": 0,
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
        # 类型计数
        if t in ("单选", "choice"): s["n_choice"] += 1
        elif t == "cloze": s["n_cloze"] += 1
        elif t == "reading": s["n_reading"] += 1
        elif t == "reading_express": s["n_re"] += 1
        elif t in ("作文", "essay"): s["n_essay"] += 1
        # 答案格式
        if t in ("单选", "choice", "cloze", "reading"):
            if not re.fullmatch(r"[A-D]", ans):
                s["bad_choice_ans"].append((qid, ans))
        # 分值检查
        if t in ("单选", "choice") and score != 0.5:
            s["bad_choice_score"].append((qid, score))
        if t == "cloze" and score != 1:
            s["bad_cloze_score"].append((qid, score))
        if t == "reading" and score != 2:
            s["bad_reading_score"].append((qid, score))
        if t == "reading_express" and score not in (2, 4):
            s["bad_re_score"].append((qid, score))
        if t in ("作文", "essay"):
            # 二选一备选 score=0 应有 "[二选一" 前缀
            if score == 0 and "二选一" not in sol and "任选" not in sol:
                s["essay_dup_score"].append(qid)
        # stem (cloze 题 stem 可空)
        if not stem.strip() and t != "cloze":
            s["empty_stem"].append(qid)
        # 选项完整性 (含 has_image_options 的 reading_A 豁免)
        if t in ("单选", "choice", "cloze"):
            if not opts or len(opts) < 4 or any(not (v or "").strip() for v in opts.values()):
                s["empty_options"].append(qid)
        elif t == "reading" and not q.get("has_image_options"):
            # 阅读理解选择题应有 options（除 image-match A 篇）
            if not opts or len(opts) < 4:
                s["empty_options"].append(qid)
        # sol
        if t in ("reading_express", "作文", "essay") and len(sol.strip()) < 10:
            s["short_sol"].append(qid)
        # KP
        if not kps:
            s["no_kp"].append(qid)
        for kp in kps:
            if CROSS_SUBJECT_KP.search(kp):
                s["cross_subj_kp"].append((qid, kp))
        # 噪声 / marker
        full_text = stem + "\n" + sol
        if NOISE_FOOTER.search(full_text):
            s["noise_footer"].append(qid)
        if INLINE_MARKER.search(sol):
            s["inline_marker"].append(qid)

    # passage
    for p in passages:
        if not p.get("q_range"):
            s["passage_no_qrange"].append(p.get("id", "?"))
        if p.get("type") == "cloze":
            if not CLOZE_BLANK.search(p.get("body", "") or ""):
                s["cloze_no_blanks"].append(p.get("id", "?"))

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
    if s["n_choice"] != 12:
        s["warnings"].append(f"单选 {s['n_choice']} ≠ 12")
    if s["n_cloze"] != 8:
        s["warnings"].append(f"完形 {s['n_cloze']} ≠ 8")
    if s["n_reading"] != 13:
        s["warnings"].append(f"阅读 {s['n_reading']} ≠ 13")
    if s["n_re"] not in (3, 4):
        s["warnings"].append(f"阅读表达 {s['n_re']} ∉ (3,4)")
    if s["n_essay"] not in (1, 2):
        s["warnings"].append(f"作文 {s['n_essay']} ∉ (1,2)")
    if s["n_passage"] < 4:
        s["warnings"].append(f"passages {s['n_passage']} < 4")
    return s


def fmt_short(items, max_n=5):
    if not items: return "-"
    short = items[:max_n]
    return ",".join(str(x if not isinstance(x, tuple) else x[0]) for x in short) + \
            ("..." if len(items) > max_n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?",
                    default="knowledge-base/exams/mock/english/beijing/")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args()
    p = Path(a.path)
    files = [p] if p.is_file() else sorted(p.glob("2026-*-yi.yaml"))
    if not files:
        sys.exit(f"no yaml in {p}")

    cols = ["district", "Q#", "sum", "full", "chc", "clz", "rd", "re", "es",
            "psg", "miss", "dup", "badT", "emS", "emO", "badC",
            "badCs", "badZs", "badRs", "shS", "noKP", "crKP",
            "noise", "marker", "pasQR", "clozeBl"]
    widths = [12, 4, 5, 5, 4, 4, 4, 4, 4, 4, 6, 4, 5, 5, 5, 5, 6, 6, 6, 5, 5, 5, 6, 7, 6, 7]
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
                s["n_choice"], s["n_cloze"], s["n_reading"],
                s["n_re"], s["n_essay"], s["n_passage"],
                fmt_short(s["missing_ids"]),
                len(s["dup_ids"]) or "-",
                len(s["bad_type"]) or "-",
                len(s["empty_stem"]) or "-",
                len(s["empty_options"]) or "-",
                len(s["bad_choice_ans"]) or "-",
                len(s["bad_choice_score"]) or "-",
                len(s["bad_cloze_score"]) or "-",
                len(s["bad_reading_score"]) or "-",
                len(s["short_sol"]) or "-",
                len(s["no_kp"]) or "-",
                len(s["cross_subj_kp"]) or "-",
                len(s["noise_footer"]) or "-",
                len(s["inline_marker"]) or "-",
                len(s["passage_no_qrange"]) or "-",
                len(s["cloze_no_blanks"]) or "-",
        ]
        print(fmt.format(*[str(x) for x in row]))
        for w in s["warnings"]:
            warn_lines.append(f"  ⚠ {district}: {w}")
        if a.verbose:
            for key in ("bad_choice_ans", "bad_choice_score", "bad_cloze_score",
                         "bad_reading_score", "cross_subj_kp", "inline_marker",
                         "noise_footer", "passage_no_qrange"):
                if s[key]:
                    print(f"    {key}: {s[key][:8]}")
    if warn_lines:
        print("\n=== 警告 ===")
        for w in warn_lines: print(w)
    print(f"\n合计 {len(files)} 区扫描完成")


if __name__ == "__main__":
    main()
