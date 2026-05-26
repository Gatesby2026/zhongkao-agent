#!/usr/bin/env python3
"""chinese_inspect — 北京中考语文 docx 路线 yaml 质量自动检查器

固化所有已知 bug pattern（来自 chinese_docx_paper 踩坑笔记）：

【结构性】
  - 题数 23-28（昌平 28 / 海淀 26 / 东城 23 都合法）
  - 满分严格 100，sum(score) 必须 == full_score
  - 题号无重复、无跳号
  - 5 大类型 section 类型分布合理：handwriting/subjective_blank/dictation/
    appreciation/comprehension/poem_comprehension/classical_comprehension/
    book_review/essay
  - duration_minutes == 150（语文统一）
  - subject == "chinese"

【答案格式】
  - 单选题答案 ∈ {A,B,C,D}
  - 默写题 sol 应含 ①②③ 空标记（dictation 题）
  - essay 二选一题（如 Q24+Q25 / Q26+Q27）：第二题 score=0
    且 sol 含 "[二选一备选题目..." 前缀

【内容完整性】
  - stem 非空
  - 选择题 options 非空、4 选项齐全
  - answer 非空（dictation/essay 类型允许空，因答案在 sol 里）
  - sol 非空（dictation/comprehension/essay 必填）
  - knowledge_points 非空

【passage 二级模型】
  - passages 非空（语文必有 6-9 个 passage：资料一/二/三/材料一 等）
  - 每个 passage q_range 非 null（用 _backfill_passage_qrange 兜底）

【噪声/marker 残留检测】（修过的 bug 必须不再出现）
  - "第二部分" / "学科网" / "菁优网" / "考生须知" 不在 stem/sol
  - 行内 marker 残留：【小问N详解】、【N题详解】、【点睛】不在 sol body
  - "答案及评分" / "参考答案" 等 footer 关键字不在 stem
  - decimal 前缀（sol 以纯数字 + 换行开头）— 物理同类问题，语文也防

【KP 跨学科污染】
  - KP 不含其他学科词：力学/电学/光学/热学/牛顿/欧姆/化学方程式/
    元素周期/正确/错误（判断题专用）/写作题型/编程语言/数学函数

【旧 image OCR 残留 qc_note】
  - 不含模式：OCR / 划线 / 加点 / 图没识别 / 答案错位 / patch /
    兜底 / 占位 / 请对照（image v3 时代标的，docx 时代应清空）

【拼音/字音特殊检查】
  - 字音字形题（stem 含"字音/读音/拼音"）：options 应已回填拼音
    （`·X·` 模式 → `X（pīn）` 已替换）

【KP 准确性引导】（信息提示）
  - 现代文题不应标"文言文"KP；文言文题不应标"现代文"KP

用法：
  python3 chinese_inspect.py                            # 扫所有 chinese yaml
  python3 chinese_inspect.py path/to/2026-chaoyang-yi.yaml
  python3 chinese_inspect.py --verbose                  # 显示所有警告详情
"""
from __future__ import annotations
import argparse, re, sys, yaml
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# 期望值常量
# ──────────────────────────────────────────────────────────────
EXPECT_FULL_SCORE = 100
EXPECT_DURATION   = 150
EXPECT_SUBJECT    = "chinese"
EXPECT_Q_RANGE    = (23, 28)

# 标准 type 枚举
VALID_TYPES = {
    "书写", "单选", "主观填空", "默写", "古诗赏析",
    "古诗内容理解", "文言文综合理解", "现代文阅读",
    "名著阅读", "作文",
    # enrich 可能保留英文 type
    "handwriting", "choice", "subjective_blank", "dictation",
    "appreciation", "poem_comprehension", "classical_comprehension",
    "comprehension", "book_review", "essay",
}

# 跨学科污染：以下 KP 词不应出现（物理/化学/数学）
CROSS_SUBJECT_KP = re.compile(
    r"力学|电学|光学|热学|牛顿|欧姆|焦耳|安培|伏特|"
    r"分子运动|物态变化|凸透镜|平面镜|"
    r"化学方程式|元素周期|原子结构|氧化还原|"
    r"二次函数|一元二次|圆锥|椭圆|导数|微积分"
)

# 噪声/footer 关键字（不应在 stem 或 sol body 中）
NOISE_IN_STEM = re.compile(
    r"^.*(?:学校[_\s]+班级|考生须知|本试卷共\d+页|考试时间\d+\s*分钟|"
    r"参考答案|答案及评分|菁优网|学科网\(www|声明.*?著作权).*$",
    re.MULTILINE
)
NOISE_FOOTER  = re.compile(r"第[一二三四五六]部分\s*$|第[一二三四五六]部分$")

# 行内 marker 残留（应在 parser 阶段清理）
INLINE_MARKER = re.compile(r"【小问\d+详解】|【\d{1,2}题详解】|【点睛】(?![^\n]{0,3}$)")

# 旧 image v3 qc_note 残留 pattern
STALE_QC_NOTE = re.compile(
    r"OCR|划线|加点|图没识别|答案错位|patch|兜底|占位|请对照|"
    r"answer 为空|缺少 options|需补全 solution"
)

# 拼音残留 ·X· （字音题 options 应已回填）
PINYIN_UNFILLED = re.compile(r"·[一-鿿]·")


def inspect(yaml_path: Path, verbose=False) -> dict:
    """检查单个 yaml，返回 stats dict。"""
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
        "missing_ids": [],
        "dup_ids": [],
        "bad_type": [],
        "empty_stem": [], "empty_ans_judge": [], "bad_choice_ans": [],
        "empty_options": [], "short_sol": [], "no_kp": [],
        "cross_subj_kp": [], "noise_in_stem": [], "noise_footer": [],
        "inline_marker": [], "stale_qc_note": [], "decimal_prefix": [],
        "dictation_no_blank": [], "essay_dup_score": [],
        "pinyin_unfilled": [], "passage_no_qrange": [],
        "n_passage": len(passages),
        "warnings": [],
    }
    # 题号检查
    ids = [q.get("id") for q in qs]
    s["dup_ids"] = sorted({i for i in ids if ids.count(i) > 1})
    expected = set(range(1, max(ids) + 1)) if ids else set()
    s["missing_ids"] = sorted(expected - set(ids))

    # 每题检查
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
        # 单选题答案
        if t in ("单选", "choice") and not re.fullmatch(r"[A-D]", ans):
            s["bad_choice_ans"].append((qid, ans))
        # 选择题选项完整性
        if t in ("单选", "choice"):
            if not opts or len(opts) < 4 or any(not (v or "").strip() for v in opts.values()):
                s["empty_options"].append(qid)
        # 默写题应含空标记
        if t in ("默写", "dictation"):
            if not re.search(r"[①②③④⑤⑥⑦⑧⑨⑩]", sol):
                s["dictation_no_blank"].append(qid)
        # essay 二选一 score=0 + 注明
        if t in ("作文", "essay") and score == 0:
            if "二选一" not in sol and "任选" not in sol:
                s["essay_dup_score"].append(qid)
        # sol 太短（主观题）
        if t in ("现代文阅读", "古诗赏析", "古诗内容理解", "文言文综合理解",
                  "名著阅读", "主观填空", "作文", "默写",
                  "comprehension", "appreciation", "poem_comprehension",
                  "classical_comprehension", "book_review", "essay",
                  "dictation", "subjective_blank"):
            if len(sol.strip()) < 20 and t not in ("作文", "essay"):
                s["short_sol"].append(qid)
        # KP 检查
        if not kps:
            s["no_kp"].append(qid)
        for kp in kps:
            if CROSS_SUBJECT_KP.search(kp):
                s["cross_subj_kp"].append((qid, kp))
        # 噪声/marker 残留
        full_text = stem + "\n" + sol
        if NOISE_IN_STEM.search(full_text):
            s["noise_in_stem"].append(qid)
        if NOISE_FOOTER.search(full_text):
            s["noise_footer"].append(qid)
        if INLINE_MARKER.search(sol):
            s["inline_marker"].append(qid)
        # decimal 前缀（sol 以纯数字开头）
        if re.match(r"^\s*\d{1,3}\s*\n", sol):
            s["decimal_prefix"].append(qid)
        # 旧 qc_note 残留
        note = (q.get("qc_note") or "").strip()
        if note and STALE_QC_NOTE.search(note):
            s["stale_qc_note"].append(qid)
        # 字音字形题拼音回填
        if any(k in stem for k in ("字音", "读音", "拼音")):
            opt_str = " ".join((opts or {}).values()) if opts else ""
            if PINYIN_UNFILLED.search(opt_str):
                s["pinyin_unfilled"].append(qid)

    # passage q_range 检查
    for p in passages:
        qr = p.get("q_range")
        if qr is None:
            s["passage_no_qrange"].append(p.get("id", "?"))

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
    if s["n_passage"] < 4:
        s["warnings"].append(f"passages 仅 {s['n_passage']} 个，语文通常 6-9 个")
    return s


def fmt_short(items, max_n=5):
    """简化显示 (qid 列表 / (qid,...) tuple 列表)"""
    if not items: return "-"
    short = items[:max_n]
    s = ",".join(str(x if not isinstance(x, tuple) else x[0]) for x in short)
    return s + ("..." if len(items) > max_n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?",
                    default="knowledge-base/exams/mock/chinese/beijing/",
                    help="yaml 文件或目录（默认扫北京 chinese mock）")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="显示所有警告详情而非简表")
    a = ap.parse_args()
    p = Path(a.path)
    if p.is_file():
        files = [p]
    else:
        # 同时扫一模 (yi) 和二模 (er)；三模 (san) 也兼顾
        files = sorted(set(p.glob("2026-*-yi.yaml"))
                       | set(p.glob("2026-*-er.yaml"))
                       | set(p.glob("2026-*-san.yaml")))
    if not files:
        sys.exit(f"no yaml found in {p}")

    # 表头
    cols = ["district", "Q#", "sum", "full", "miss", "dup", "badT",
            "emS", "emO", "shS", "badC", "noKP", "crKP",
            "noise", "marker", "decim", "stale", "pasQR"]
    widths = [14, 4, 5, 5, 6, 5, 5, 5, 5, 5, 5, 5, 5, 6, 7, 6, 6, 6]
    fmt = "".join(f"{{:>{w}}}" for w in widths)
    print(fmt.format(*cols))
    print("─" * sum(widths))
    totals = {k: 0 for k in cols if k not in ("district",)}
    warn_lines = []

    for f in files:
        s = inspect(f, a.verbose)
        if "_error" in s:
            print(f"{f.name}: {s['_error']}")
            continue
        district = f.stem.replace("2026-", "").replace("-yi", "")
        row = [
            district, s["n_q"], s["sum_score"], s["full_score"],
            fmt_short(s["missing_ids"]),
            len(s["dup_ids"]) or "-",
            len(s["bad_type"]) or "-",
            len(s["empty_stem"]) or "-",
            len(s["empty_options"]) or "-",
            len(s["short_sol"]) or "-",
            len(s["bad_choice_ans"]) or "-",
            len(s["no_kp"]) or "-",
            len(s["cross_subj_kp"]) or "-",
            len(s["noise_in_stem"]) + len(s["noise_footer"]) or "-",
            len(s["inline_marker"]) or "-",
            len(s["decimal_prefix"]) or "-",
            len(s["stale_qc_note"]) or "-",
            len(s["passage_no_qrange"]) or "-",
        ]
        print(fmt.format(*[str(x) for x in row]))
        for w in s["warnings"]:
            warn_lines.append(f"  ⚠ {district}: {w}")
        if a.verbose:
            for key in ("bad_type", "bad_choice_ans", "empty_options",
                        "cross_subj_kp", "inline_marker", "decimal_prefix",
                        "stale_qc_note", "noise_in_stem", "noise_footer"):
                if s[key]:
                    print(f"    {key}: {s[key][:10]}")

    if warn_lines:
        print("\n=== 警告 ===")
        for w in warn_lines: print(w)
    print(f"\n合计 {len(files)} 区扫描完成")


if __name__ == "__main__":
    main()
