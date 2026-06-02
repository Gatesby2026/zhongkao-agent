#!/usr/bin/env python3
"""politics_docx_paper — 北京中考道法（道德与法治）docx 解析版 → final.json

基于 chinese_docx_paper.py（共享 ~70% 框架）。道法特异性：
  - 满分 70 分（开卷考），70 分钟（部分区 80/100，inspect 容忍）
  - section 三类：判断题（√/×/正确/错误）/ 选择题（ABCD）/ 材料分析（长文字答案）
  - 题号 1-25 左右，判断题 10 × 1 分、选择 10 × 2 分、材料 5 × 8 分（朝阳）
  - 答案 marker 同 chinese：【答案】+ 【N题详解】 / 【小问N详解】 / 【详解】
  - 无加点字/拼音/古诗文/默写 — 这些都跳过；保留 chinese 框架兼容性即可

输入：精品解析 .zip 含 (原卷版.docx + 解析版.docx) 或单 解析版.docx
处理流程同 chinese：
  1. 解压 zip / 直接打开 docx
  2. 优先用 解析版.docx
  3. body 顺序遍历 paragraphs + tables
  4. 切大题 + 题号锚 + 答案抽取
  5. 输出 final.json
"""
from __future__ import annotations
import argparse, json, os, re, shutil, sys, tempfile, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "exam-ocr"))

# 复用 docx_paper 的底层 docx 解析
import docx_paper as dp  # noqa: E402
from paths import derive_out_dir  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


# ─── run 层重写：加点字 / 下划线（语文专属）───────────────────────────────

def _walk_run_chinese(r: ET.Element, rels: dict[str, str],
                       extract_dir: Path, figures_dir: Path) -> str:
    """复刻 dp._walk_run 但增加 emphasis dot + underline 包裹。
    - <w:em w:val="dot"/>   → ·X·
    - <w:u w:val="single"/>  → <u>X</u>
    - 二者并存优先 underline 外 emphasis 内 → <u>·X·</u>
    跳过 OMML（语文无公式）。
    """
    rpr = r.find(f"{{{W_NS}}}rPr")
    has_em = has_u = False
    if rpr is not None:
        em = rpr.find(f"{{{W_NS}}}em")
        if em is not None:
            val = em.get(f"{{{W_NS}}}val") or em.get("val")
            if val in (None, "dot", "circle", "comma", "underDot"):
                has_em = True
        u = rpr.find(f"{{{W_NS}}}u")
        if u is not None:
            val = u.get(f"{{{W_NS}}}val") or u.get("val")
            if val and val != "none":
                has_u = True
    out: list[str] = []
    for child in r:
        tag = _local(child.tag)
        ns = child.tag.rsplit("}", 1)[0] if "}" in child.tag else ""
        if tag == "t" and ns == f"{{{W_NS}":
            if child.text:
                out.append(child.text)
        elif tag == "br":
            out.append("\n")
        elif tag == "tab":
            out.append(" ")
        elif tag in ("drawing", "pict"):
            img = dp._extract_image(child, rels, extract_dir, figures_dir)
            if img: out.append(img)
        # OMML 跳过（语文无公式）
    text = "".join(out)
    if not text.strip():
        return text
    # 包裹
    if has_em:
        text = f"·{text}·"
    if has_u:
        text = f"<u>{text}</u>"
    return text


def _walk_paragraph_chinese(p: ET.Element, rels: dict[str, str],
                              extract_dir: Path, figures_dir: Path) -> str:
    out: list[str] = []
    for child in p:
        tag = _local(child.tag)
        if tag == "r":
            out.append(_walk_run_chinese(child, rels, extract_dir, figures_dir))
        elif tag == "hyperlink":
            for r in child.findall(f"{{{W_NS}}}r"):
                out.append(_walk_run_chinese(r, rels, extract_dir, figures_dir))
        elif tag == "smartTag":
            out.append(_walk_paragraph_chinese(child, rels, extract_dir, figures_dir))
    return "".join(out)


def _walk_table_chinese(tbl: ET.Element, rels: dict[str, str],
                          extract_dir: Path, figures_dir: Path) -> str:
    """复刻 dp._walk_table 但用 chinese paragraph walker。"""
    rows = []
    for tr in tbl.findall(f"{{{W_NS}}}tr"):
        cells = []
        for tc in tr.findall(f"{{{W_NS}}}tc"):
            cell = " ".join(
                _walk_paragraph_chinese(p, rels, extract_dir, figures_dir)
                for p in tc.findall(f"{{{W_NS}}}p")
            )
            cells.append(cell.strip())
        rows.append("| " + " | ".join(cells) + " |")
    if not rows: return ""
    n_cols = max(r.count("|") - 1 for r in rows)
    sep = "|" + "|".join(["---"] * n_cols) + "|"
    return rows[0] + "\n" + sep + "\n" + "\n".join(rows[1:])


def docx_to_markdown_chinese(docx_path: Path, extract_dir: Path,
                                figures_dir: Path) -> str:
    """完整 docx → markdown 字符串。返回 markdown。"""
    root, rels = dp._load_docx(docx_path, extract_dir)
    body = root.find(f"{{{W_NS}}}body")
    if body is None: return ""
    md_lines: list[str] = []
    for child in body:
        tag = _local(child.tag)
        if tag == "p":
            line = _walk_paragraph_chinese(child, rels, extract_dir, figures_dir)
            if line.strip():
                md_lines.append(line)
        elif tag == "tbl":
            tbl_md = _walk_table_chinese(child, rels, extract_dir, figures_dir)
            if tbl_md: md_lines.append(tbl_md)
    return "\n\n".join(md_lines)


# ─── zip / docx 输入处理 ───────────────────────────────────────────────────

def _unzip_to(zip_path: Path, dest: Path) -> list[Path]:
    """解压（cp437→gbk 修正），返回 docx 文件列表。"""
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            try:
                name = info.filename.encode("cp437").decode("gbk")
            except Exception:
                name = info.filename
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if info.is_dir(): continue
            target.write_bytes(zf.read(info))
            if target.suffix.lower() == ".docx":
                out.append(target)
    return out


def _pick_jiexi_docx(docx_paths: list[Path]) -> Path:
    """选 docx 优先级：解析版 > 试卷版 > 最大文件。

    zxxk 2026 二模有部分区是「试卷.docx + 答案.docx」双文件格式（无'解析'
    字样），原 fallback docx_paths[0] 会拿到答案文件导致 0 题。
    """
    for p in docx_paths:
        if "解析" in p.stem and "原卷" not in p.stem:
            return p
    for p in docx_paths:
        if "试卷" in p.stem and "答案" not in p.stem:
            return p
    if docx_paths:
        return max(docx_paths, key=lambda d: d.stat().st_size)
    raise FileNotFoundError("zip 内未找到 docx")


# ─── section / 题号 切分 ────────────────────────────────────────────────────

# **跨区通用**：按**内容关键词**识别 section type（忽略大题编号位置）。
# 朝阳=三名著/四现代文；石景山=三现代文/四名著。两区都能正确分。
SECTION_HEADERS = [
    # 道法卷：判断题 / 选择题 / 材料分析（综合探究 / 简答 / 论述 / 探究与实践）
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*判断\s*题?"),                  "judge"),
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*(?:单项)?\s*选择\s*题?"),       "choice"),
    (re.compile(
        r"^\s*[一二三四五六七]\s*[、.]\s*"
        r"(?:材料分析|分析说明|简答|论述|综合探究|情境分析|探究与实践|实践探究)"
        r"\s*题?"
    ), "material"),
    # **道法特有**：朝阳卷无 "三、材料分析题" header，直接用"第二部分"分隔
    # 第二部分多为材料分析（Q21-Q25），归 material section
    (re.compile(r"^\s*第二部分\s*$"), "material"),
]
# 子段标题（资料一/二/三/后记 / 材料一/二/三 / (一)(二)(三)）
# 子段标题：行首关键字 + 可选 "(共?N分)" 或描述（如 "（一）默写。（共4分）"
# **不**严格要求 \s*$，允许后跟分值标注或描述（大兴 "（一）（4分）" / 朝阳 "（一）默写。（共4分）"）
SUB_HEADER_RE = re.compile(
    r"^\s*(资料[一二三四五]|后记|卷首语|前言|序言|材料[一二三四五]"
    r"|[\(（][一二三四五][\)）])(?:\s|$|[\(（])"
)
# 题号
NUM_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．,，]\s*(.*)$")
# 选项行（A. X B. Y / A. X\nB. Y / A.X\tB.Y 等）
OPT_LINE_RE = re.compile(r"(?:^|\s)([A-D])\s*[.、．]\s*([^\sA-D].*?)(?=\s+[A-D]\s*[.、．]|$)")
# 答案 / 详解 marker
ANSWER_MARKER_RE = re.compile(r"^\s*【答案】")
DETAIL_TITLE_RE = re.compile(r"^\s*【(\d{1,2})题详解】")
GENERIC_DETAIL_RE = re.compile(r"^\s*【详解】")
DAOYU_RE = re.compile(r"^\s*【导语】(.*)$")  # 文章导语
DIANJING_RE = re.compile(r"^\s*【点睛】(.*)$")  # 多含 古诗文译文
ANALYSIS_RE = re.compile(r"^\s*【解析】")
# Cover/noise
NOISE_LINE_RE = re.compile(
    r"^\s*(?:学校[_\s]+班级|2026\.\d{1,2}|考生须知|\d+\s*年.*?试卷\s*$"
    r"|本试卷共\d+页|考试时间\d+\s*分钟"
    r"|语文试卷|声明.*?著作权|发布日期|菁优网"
    r"|参考答案|答案及评分)\s*$")


def _is_section_header(line: str) -> tuple[str, str] | None:
    for pat, typ in SECTION_HEADERS:
        if pat.search(line): return typ, line
    return None


# ─── 主解析 ──────────────────────────────────────────────────────────────────

def parse_docx_chinese(md: str, figures_dir: Path) -> dict:
    """把 docx 解析版 markdown 拆成 final.json 结构。

    解析版结构是 **题面 + 答案 交替**：每大题先题面再【答案】+【N题详解】，
    然后下一大题题面再答案……需用状态机切分。
    """
    lines = md.split("\n")
    # **P0 答案哨兵**（shunyi 二模教训）：试卷答案 / 参考答案 / 试题答案 / 答案及评分
    # 这些 marker 之后通常是"一、判断题（每题1分，共10分）"类 section header 复述，
    # 会让 SECTION_HEADERS 二次匹配产生幽灵题（shunyi: 25→32 题, 70→80 分）。
    # 修复：进入 sentinel 后，**禁用 section header 二次匹配**，state machine
    # 维持当前 section 继续吃答案行（让 N. ABCD 等行经 _parse_answers 解析）。
    _ANSWER_SENTINEL = re.compile(
        r"^\s*(?:试卷答案|试题答案|参考答案|答案及评分(?:参考|标准)?)\s*$")
    seen_answer_sentinel = False
    # 1. 用状态机分别收集 q_lines（按 section）和 a_lines（全局）
    # **关键**：解析版结构是 题面+【答案】+【详解】+ sub-header (一)/(二) + 下一组题面
    # +【答案】... 反复交替。所以 sub-header 也要触发 answer→question 切换。
    sections: dict[str, list[str]] = {}
    cur_typ: str | None = None
    mode = "init"   # init / question / answer
    a_lines: list[str] = []
    # 看到 next question anchor 也回 question（用 last_q_seen 跟踪）
    last_q_seen = 0
    # **关键**：【答案】 行如果不带 "N." 前缀，content 归属上一题。在 a_lines
    # 里插入 __Q_CTX__:N 标记让 _parse_answers 知道默认归属。
    last_q_before_answer = 0

    for ln in lines:
        # 进入"试卷答案" sentinel 后，禁用 SECTION_HEADERS 二次匹配，强制进入
        # answer mode（剩余行直接交 _parse_answers 抽 N. ABCD / 答案表格 / N. (N分) 示例 等）
        if _ANSWER_SENTINEL.match(ln):
            seen_answer_sentinel = True
            if mode == "question":
                last_q_before_answer = last_q_seen
                a_lines.append(f"__Q_CTX__:{last_q_before_answer}")
            mode = "answer"
            continue
        sec_m = None if seen_answer_sentinel else _is_section_header(ln)
        if sec_m:
            cur_typ = sec_m[0]
            sections.setdefault(cur_typ, [])
            mode = "question"
            continue
        if mode == "init":
            continue
        # 答案/详解 标记 → 切到 answer 模式
        if (ANSWER_MARKER_RE.match(ln) or DETAIL_TITLE_RE.match(ln)
            or GENERIC_DETAIL_RE.match(ln) or ANALYSIS_RE.match(ln)
            or DAOYU_RE.match(ln) or DIANJING_RE.match(ln)):
            if mode == "question":
                # 入答案模式：记下"上一题号"作为无 N. 前缀【答案】的默认归属
                last_q_before_answer = last_q_seen
                a_lines.append(f"__Q_CTX__:{last_q_before_answer}")
            mode = "answer"
            a_lines.append(ln)
            continue
        # **sub-header 在 answer 模式 → 切回 question 模式**
        # （古诗文 (二)(三) / 现代文 (一)(二)(三) 都是子段切换信号）
        if SUB_HEADER_RE.match(ln) and mode == "answer" and not seen_answer_sentinel:
            mode = "question"
            if cur_typ:
                sections[cur_typ].append(ln)
            continue
        # **answer 模式里出现新题号锚（N > last_q_seen），且行不含【】标记 → 切回 question**
        # 用于解析版里 sub-header 缺失但题号跳过的情形
        q_m = NUM_HEAD_RE.match(ln)
        # **不**用 "【" not in ln（道法题干常有 "25. 【以法为纲，山清水秀】" 子标题）
        # 改为精确排除 answer/detail marker 开头
        is_marker = (ANSWER_MARKER_RE.match(ln) or DETAIL_TITLE_RE.match(ln)
                     or GENERIC_DETAIL_RE.match(ln) or ANALYSIS_RE.match(ln))
        if (mode == "answer" and q_m and not is_marker and not seen_answer_sentinel):
            n = int(q_m.group(1))
            if n > last_q_seen and n <= 30:
                content = ln.strip()
                # 严格答案行 pattern："N. C" / "N. AB" / "N. 略" / "N. √" 等 — 跳过
                # 否则即使短题号（如朝阳道法 "16. 小产品，大产业。"）也视为题号
                ans_only = re.match(
                    r"^\d{1,2}\s*[.、．]\s*"
                    r"(?:[A-D]{1,4}|√|×|对|错|正确|错误|略|\d+(?:\.\d+)?\s*[A-Za-z]*)\s*$",
                    content)
                if ans_only:
                    pass  # 是答案，不切
                else:
                    # 严格递增（n == last_q_seen + 1 才算下一题，防工艺数字 / 序号 ①②）
                    if n == last_q_seen + 1 or cur_typ in ("essay", "material"):
                        mode = "question"
                        if cur_typ:
                            sections[cur_typ].append(ln)
                        last_q_seen = n
                        continue
        if mode == "answer":
            a_lines.append(ln)
            continue
        # mode == question
        if q_m:
            n = int(q_m.group(1))
            if n <= 30: last_q_seen = n
        if cur_typ:
            sections[cur_typ].append(ln)

    # 2. 每大题内：切 passage 子段 + 题号
    passages: list[dict] = []
    questions: list[dict] = []
    for sec_typ, sec_lines in sections.items():
        _parse_section(sec_typ, sec_lines, passages, questions, figures_dir)

    # 3. 解析答案 + 详解
    answers_map = _parse_answers(a_lines)
    poem_trans = _parse_dianjing_translations(a_lines)
    # 合并 answer 到 question
    for q in questions:
        n = q["number"]
        a = answers_map.get(n)
        if a:
            q["answer"] = a.get("correct", "")
            q["solution"] = a.get("solution", "")
            if a.get("score") is not None and not q.get("score"):
                q["score"] = a["score"]
    # 古诗文译文附加到 passage body
    for ps in passages:
        if ps.get("type") == "classical":
            trans = poem_trans.get(ps.get("name") or "")
            if trans:
                ps["body"] = (ps.get("body","") + "\n\n[参考译文]\n" + trans).strip()

    # 4.5 字音/字形题 options 回填 passage 拼音（朝阳 Q3 案例）
    # passage 里 "矗（zhù）立" → option "·矗·立" 补成 "矗（zhù）立"
    _backfill_pinyin_to_options(questions, passages)

    # 4.6 passage q_range 兜底填（modern_（一）/材料一/二/三 这种共享阅读材料）
    _backfill_passage_qrange(passages, questions)

    # 5. type 推断 + section/sub-section 总分驱动的 score 分配
    _assign_types(questions)
    # 给每题打全局 line_idx（在 md 里搜 "N." + stem 前 12 字符匹配）
    md_lines = md.split("\n")
    for q in questions:
        n = q["number"]
        stem_first_line = next((l for l in (q.get("stem","") or "").split("\n")
                                if l.strip()), "")
        stem_head = stem_first_line.strip()[:8]
        first_num_match_idx = -1
        for i, ln in enumerate(md_lines):
            m = NUM_HEAD_RE.match(ln)
            if not m or int(m.group(1)) != n: continue
            if first_num_match_idx == -1:
                first_num_match_idx = i  # 记录第一个 "N." 行 (兜底)
            if not stem_head or stem_head[:4] in ln:
                q["_line_idx"] = i
                break
        else:
            # **道法 stem 常是 markdown table (`|...`)**，与"N. "空行内容不匹配，
            # stem_head check 失败但第一个 "N." 题号行已识别 — 用它兜底
            q["_line_idx"] = first_num_match_idx if first_num_match_idx >= 0 else 0
    score_blocks = _parse_score_blocks(md, questions)
    _assign_scores(questions, score_blocks)

    # 6. full_score
    full_score = sum(q.get("score", 0) or 0 for q in questions) or None

    # **关键**：answers_list 必须从 questions 取，因为 _assign_scores 可能改了
    # questions[i].solution（如二选一作文加 [二选一备选] 前缀），如果走 answers_map
    # 会丢失这些修改
    q_by_num = {q["number"]: q for q in questions}
    answers_list = []
    for n, a in sorted(answers_map.items()):
        q = q_by_num.get(n)
        sol = (q.get("solution","") if q else a.get("solution","")) or a.get("solution","")
        ans = (q.get("answer","")   if q else a.get("correct","")) or a.get("correct","")
        score = (q.get("score") if q else a.get("score"))
        answers_list.append({"number": n, "correct": ans, "solution": sol, "score": score})
    return {
        "passages": passages,
        "questions": questions,
        "answers": answers_list,
        "full_score": full_score,
    }


def _parse_section(sec_typ: str, sec_lines: list[str],
                    passages: list[dict], questions: list[dict],
                    figures_dir: Path) -> None:
    """切 passage 子段 + 题号锚切题。"""
    # 先扫所有子段起始
    sub_starts: list[tuple[int, str]] = []   # (line_idx, sub_name)
    q_starts: list[tuple[int, int, str]] = []  # (line_idx, num, rest)
    for i, ln in enumerate(sec_lines):
        sub_m = SUB_HEADER_RE.match(ln)
        if sub_m:
            sub_starts.append((i, sub_m.group(1)))
            continue
        q_m = NUM_HEAD_RE.match(ln)
        if q_m and 1 <= int(q_m.group(1)) <= 30:
            q_starts.append((i, int(q_m.group(1)), q_m.group(2)))

    # 给每个子段构 passage（base/classical/modern 有子段；book_review/essay 通常无）
    # **passage 合并策略**：
    #   - "资料一/(一)(二)(三)/后记" = 真子段 → 独立 passage
    #   - "材料一/材料二/材料三" = 题面引文 → **合并到上一个真子段的 passage body**
    # 这样 modern_（一）内的 材料一/二/三 不会变 3 个独立 passage
    real_subs = [(i, name) for (i, name) in sub_starts if not name.startswith("材料")]
    real_sub_idx = {s[0]: s[1] for s in real_subs}
    if real_subs:
        # 用 real_subs 切 passage 边界
        real_boundaries = [s[0] for s in real_subs] + [len(sec_lines)]
        for idx, (start_i, sub_name) in enumerate(real_subs):
            end_i = real_boundaries[idx + 1]
            # passage body：sub_name 后到第一个 q anchor 前（含 materials）
            first_q_in_sub = next((qs[0] for qs in q_starts
                                   if start_i < qs[0] < end_i), end_i)
            body = _join_lines(sec_lines[start_i+1:first_q_in_sub])
            body = _clean_noise(body)
            # 提取 figures 引用（passage body 内 ![](figures/xxx.png)）
            fig = None
            fig_m = re.search(r"!\[\]\(figures/([^)]+)\)", body)
            if fig_m:
                fig = f"figures/{fig_m.group(1)}"
            # 子段内的题号范围
            q_in_sub = [qs[1] for qs in q_starts if start_i < qs[0] < end_i]
            q_range = [min(q_in_sub), max(q_in_sub)] if q_in_sub else None
            pid = f"{sec_typ}_{sub_name}"
            passages.append({
                "id": pid, "type": sec_typ, "name": sub_name,
                "q_range": q_range, "body": body,
                **({"figure": fig} if fig else {}),
            })
    elif sec_typ != "essay":
        # 整段作为一个 passage（如 modern 单材料）
        first_q_idx = q_starts[0][0] if q_starts else len(sec_lines)
        body = _join_lines(sec_lines[:first_q_idx])
        if body.strip():
            q_in_sec = [qs[1] for qs in q_starts]
            q_range = [min(q_in_sec), max(q_in_sec)] if q_in_sec else None
            fig = None
            fig_m = re.search(r"!\[\]\(figures/([^)]+)\)", body)
            if fig_m: fig = f"figures/{fig_m.group(1)}"
            passages.append({
                "id": f"{sec_typ}_intro", "type": sec_typ, "name": "",
                "q_range": q_range, "body": _clean_noise(body),
                **({"figure": fig} if fig else {}),
            })

    # 题：每个 q anchor 到下一个 q anchor 前
    q_boundaries = [qs[0] for qs in q_starts] + [len(sec_lines)]
    # **关键区分**：
    #   - "资料一/二/三/后记 / (一)(二)(三)" = 真子段（多题共享 passage）→ 截 stem
    #   - "材料一/二/三" = 题面引文（孟子/论语原文 / 非连续文本各材料）→ **不**截 stem
    #     让 Q13 等"综合材料"题的 stem 完整含所有材料
    real_sub_starts = [(i, name) for (i, name) in sub_starts
                       if not name.startswith("材料")]
    real_sub_idx_set = {s[0] for s in real_sub_starts}
    for idx, (li, num, rest) in enumerate(q_starts):
        end_i = q_boundaries[idx + 1]
        for s_i in real_sub_idx_set:
            if li < s_i < end_i:
                end_i = s_i; break
        chunk_lines = [rest] + sec_lines[li+1:end_i]
        chunk = "\n".join(chunk_lines)
        # 切 stem / options
        stem, options = _extract_stem_and_options(chunk)
        questions.append({
            "number": num,
            "stem": stem,
            "options": options if options else None,
            "section": sec_typ,
            "answer": "",
            "solution": "",
        })


def _extract_stem_and_options(chunk: str) -> tuple[str, dict[str, str] | None]:
    """从题块抽 stem + options（A./B./C./D.）。
    多选项格式：
      'A. xxx\tB. yyy'   tab/space 分隔的同一行
      'A. xxx\nB. yyy'   多行
      'A.X B.Y C.Z D.W'  紧凑
    """
    # 先尝试找 'A.' 锚（行首或空白后）
    a_m = re.search(r"(?:^|\n)\s*A\s*[.、．]\s*", chunk)
    if not a_m:
        return chunk.strip(), None
    stem = chunk[:a_m.start()].strip()
    opts_part = chunk[a_m.start():]
    # 优先用换行分隔（每行一个或多个选项）→ 拆出 A/B/C/D
    opts: dict[str, str] = {}
    # 匹配 A. ... (B. ... | tab+B. | $)
    for m in re.finditer(
        r"\b([A-D])\s*[.、．]\s*(.*?)(?=(?:\s+[A-D]\s*[.、．])|\Z)",
        opts_part, re.DOTALL):
        key = m.group(1)
        val = m.group(2).strip().replace("\n", " ").strip()
        if key not in opts:
            opts[key] = val
    return stem, opts if opts else None


def _join_lines(lines: list[str]) -> str:
    out = []
    for ln in lines:
        ln = ln.rstrip()
        if not ln: continue
        if NOISE_LINE_RE.match(ln): continue
        out.append(ln)
    return "\n".join(out)


def _clean_noise(text: str) -> str:
    lines = [ln for ln in text.split("\n") if not NOISE_LINE_RE.match(ln)]
    return "\n".join(lines).strip()


# ─── 答案 / 详解 解析 ──────────────────────────────────────────────────────

def _parse_answers(a_lines: list[str]) -> dict[int, dict]:
    """从 【答案】/【N题详解】块里抽 {N: {correct, solution, score}}。
    格式样例：
      【答案】1. 京城书香之旅    2. A    3. A
      4. 示例：...    5. C
      6. 示例：...    7. B
      【解析】
      【1题详解】
      <详解文本>
    """
    out: dict[int, dict] = {}
    # 阶段 A：【答案】段（连续行直到 【解析】 或 【N题详解】 或 段末）
    in_answer_block = False
    answer_buf: list[str] = []
    detail_blocks: dict[int, list[str]] = {}
    cur_detail: int | None = None
    # 默认归属题号（来自 q_text 最后题号锚，由调用方在 a_lines 里以 __Q_CTX__:N 标记传入）
    default_q = 0

    def _flush_answer_buf():
        if not answer_buf: return
        text = " ".join(answer_buf)
        # **P0 范文不切**（changping 二模教训 R1）：default_q ≥ 21 (essay/material 上下文)
        # 范文/倡议书内部常含 "1./2./3." 分条编号 → 不能按 N. 拆，否则被错切给 Q1-Q3
        if default_q >= 21:
            parts = [text]
        else:
            # 拆按 "N. " 题号锚；若整体无 "N." 前缀，归到 default_q
            parts = re.split(r"\s+(?=\d{1,2}\s*[.、．])", text)
        for part in parts:
            m = re.match(r"\s*(\d{1,2})\s*[.、．]\s*(.+)$", part, re.DOTALL)
            if m:
                n = int(m.group(1))
                content = m.group(2).strip()
            elif default_q:
                # 整段【答案】没 "N." 前缀，归 default_q（如朝阳 Q8 默写、Q14 名著、Q25 作文）
                n = default_q
                content = part.strip()
            else:
                continue
            if n not in out:
                out[n] = {"correct": "", "solution": "", "score": None}
            # 道法判断题答案 "正确" / "错误" / "√" / "×" / "对" / "错"
            m_judge = re.match(r"^(正确|错误|√|×|对|错)\s*$", content)
            if m_judge:
                out[n]["correct"] = m_judge.group(1)
            else:
                # choice 单字母答案（含多选 A-D 1-4 字符）
                m_letter = re.match(r"^([A-D]{1,4})(?:\s|$)", content)
                if m_letter and len(content) <= 5:
                    out[n]["correct"] = m_letter.group(1)
                else:
                    sol = re.sub(r"^(?:示例[:：]|参考[:：]|例文[:：]?)\s*", "", content)
                    # 防覆盖：若已有更长 solution，跳过
                    if not out[n]["solution"] or len(sol) > len(out[n]["solution"]):
                        out[n]["solution"] = sol
        answer_buf.clear()

    for ln in a_lines:
        # 上下文标记（由 parse_docx_chinese 注入）
        if ln.startswith("__Q_CTX__:"):
            try: default_q = int(ln.split(":",1)[1])
            except: pass
            continue
        if ANSWER_MARKER_RE.match(ln):
            _flush_answer_buf()
            in_answer_block = True
            cur_detail = None
            after = re.sub(r"^\s*【答案】\s*", "", ln)
            if after.strip(): answer_buf.append(after)
            continue
        if ANALYSIS_RE.match(ln):
            _flush_answer_buf()
            in_answer_block = False
            continue
        dm = DETAIL_TITLE_RE.match(ln)
        if dm:
            _flush_answer_buf()
            in_answer_block = False
            cur_detail = int(dm.group(1))
            detail_blocks.setdefault(cur_detail, [])
            continue
        if GENERIC_DETAIL_RE.match(ln):
            # 【详解】= 单题情况，把后续内容归到 default_q
            _flush_answer_buf()
            in_answer_block = False
            if default_q:
                cur_detail = default_q
                detail_blocks.setdefault(cur_detail, [])
                # **道法/物理同行模式**：【详解】后面紧跟内容（"【详解】依据教材..."）
                # 把同行内容也收入 detail_blocks
                after = re.sub(r"^\s*【详解】\s*", "", ln)
                if after.strip():
                    detail_blocks[cur_detail].append(after)
            continue
        if DAOYU_RE.match(ln) or DIANJING_RE.match(ln):
            cur_detail = None
            continue
        if in_answer_block:
            answer_buf.append(ln)
            continue
        if cur_detail is not None:
            detail_blocks[cur_detail].append(ln)
    _flush_answer_buf()

    # 把 detail block 拼成 solution（**总是追加详解**，除非详解与答案重复）
    for n, dl in detail_blocks.items():
        text = "\n".join(l for l in dl if l.strip()).strip()
        if not text: continue
        if n not in out:
            out[n] = {"correct": "", "solution": "", "score": None}
        cur = (out[n].get("solution","") or "").strip()
        if not cur:
            out[n]["solution"] = text
            continue
        if cur in ("略",):
            out[n]["solution"] = text
            continue
        # 详解与答案完全重复（如 Q3 "·矗·（zhù）立——chù"）→ 不重复追加
        if text == cur or text in cur:
            continue
        # 答案在详解里也含 → 直接用详解（详解更全）
        if cur in text and len(text) > len(cur) * 1.5:
            out[n]["solution"] = text
            continue
        # 否则：答案 + 详解 拼接
        out[n]["solution"] = f"{cur}\n\n详解：{text}"
    return out


def _parse_dianjing_translations(a_lines: list[str]) -> dict[str, str]:
    """从 【点睛】参考译文 抽 古诗文译文。
    返回 {sub_passage_name: translation} —— 但实际无 sub 名匹配，简化为 list 后合并。
    本函数返回 {"_pool_0": text_0, "_pool_1": text_1} 由调用方按出现顺序匹配。
    """
    # TODO: 暂不解析译文（独立的优化项）；返回空
    return {}


# ─── type 推断 + DEFAULT_QSCORE ─────────────────────────────────────────────

# 标准 section 总分（北京中考语文，跨区一致 ≈100）
STANDARD_SECTION_TOTAL = {
    "judge":     10,   # 10 题 × 1 分（朝阳/常见）
    "choice":    20,   # 10 题 × 2 分（朝阳/常见）
    "material":  40,   # 5 题 × 8 分（朝阳；其他区可能 3-5 题，分值浮动）
}


# （共N分）/（N分）标记
SCORE_BRACKET_RE = re.compile(r"[（\(]\s*共?\s*(\d+)\s*分\s*[）\)]")
# 大题头里的总分（一/二/三/四/五 + 共N分）
SECTION_TOTAL_RE = re.compile(
    r"^\s*[一二三四五]\s*[、.]\s*[^（\(]*[（\(]\s*共?\s*(\d+)\s*分\s*[）\)]")
# 子段总分（(一)/(二)/(三)  + 共?N分）
SUB_TOTAL_RE = re.compile(
    r"^\s*[（\(][一二三四五][）\)][^（\(]*[（\(]\s*共?\s*(\d+)\s*分\s*[）\)]")


def _parse_score_blocks(md: str, questions: list[dict]) -> list[dict]:
    """从 md 文本扫所有 "（共N分）" 标记 + 所有 sub-headers，建 score block 树。

    每个 section 包含 N 个 sub-block：
    - sub-header 出现位置 → block.start
    - 下一个 sub-header / section 结束 → block.end
    - "(共?N分)" 标识 → block.total（可缺失，缺失则均摊）
    """
    lines = md.split("\n")
    # 1. 扫所有 section header
    sec_brackets: list[dict] = []
    for i, ln in enumerate(lines):
        sec_m = _is_section_header(ln)
        if sec_m:
            sec_t_m = SECTION_TOTAL_RE.match(ln)
            total = int(sec_t_m.group(1)) if sec_t_m else \
                    STANDARD_SECTION_TOTAL.get(sec_m[0], 0)
            sec_brackets.append({
                "start": i, "end": -1, "total": total,
                "level": "section", "type": sec_m[0]})
            if len(sec_brackets) > 1:
                sec_brackets[-2]["end"] = i
    if sec_brackets:
        sec_brackets[-1]["end"] = len(lines)

    # 2. 在每个 section 内扫所有 sub-header（（一）/（二）/（三）），有无总分都算
    SUB_HEADER_ANY_RE = re.compile(r"^\s*[（\(][一二三四五][）\)]")
    SUB_TOTAL_INLINE_RE = re.compile(
        r"^\s*[（\(][一二三四五][）\)][^（\(]*[（\(]\s*共?\s*(\d+)\s*分\s*[）\)]")
    # 特殊：朝阳 "（一）默写。（共4分）" 已被 SUB_TOTAL_INLINE_RE 覆盖
    sub_brackets: list[dict] = []
    for sec in sec_brackets:
        sec_sub: list[dict] = []
        for i in range(sec["start"]+1, sec["end"]):
            ln = lines[i]
            if not SUB_HEADER_ANY_RE.match(ln): continue
            t_m = SUB_TOTAL_INLINE_RE.match(ln)
            sec_sub.append({
                "start": i, "end": -1,
                "total": int(t_m.group(1)) if t_m else None,
                "level": "sub", "section_type": sec["type"]})
        # 设置 sub.end
        for j, sb in enumerate(sec_sub):
            sb["end"] = sec_sub[j+1]["start"] if j+1 < len(sec_sub) else sec["end"]
        # 分配未知 total（用 section 剩余分平摊）
        known_sum = sum(sb["total"] for sb in sec_sub if sb["total"] is not None)
        unknown = [sb for sb in sec_sub if sb["total"] is None]
        if unknown:
            remaining = max(0, sec["total"] - known_sum)
            per = remaining // len(unknown) if unknown else 0
            for k, sb in enumerate(unknown):
                sb["total"] = per
                if k == len(unknown) - 1:
                    sb["total"] += (remaining - per * len(unknown))
        sub_brackets.extend(sec_sub)

    # 3. 若某 section 完全没有 sub-header（朝阳 essay 是 单 Q25 直接在 essay section），
    #    section 自身作为 block 就够了，无需 sub
    return sec_brackets + sub_brackets


# 拼音注音模式：汉字（拼音）—— passage 里的标注
# 拼音字符类含全部声调（āáǎà ēéěè īíǐì ōóǒò ūúǔù ǖǘǚǜü）
_PINYIN_CHARS = "a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü"
_PINYIN_RE = re.compile(rf"([一-鿿])\s*[（(]\s*([{_PINYIN_CHARS}]+)\s*[）)]")


def _backfill_pinyin_to_options(questions: list[dict], passages: list[dict]) -> None:
    """字音/字形题（如朝阳 Q3）的 options 是孤立的 ·X·Y 加点字短语；
    需从关联 passage 里把"X（pīn）Y" 注音回填到 options 才能让学生判断。

    判定字音题：stem 含 "字音" / "读音" / "拼音"，且 options 是中文短语
    （非完整句子，长度 ≤ 8 字）
    """
    # 先建 passage 拼音字典 {汉字串: "汉字（拼音）"}
    pinyin_map: dict[str, str] = {}
    for ps in passages:
        body = ps.get("body","") or ""
        for m in _PINYIN_RE.finditer(body):
            char, py = m.group(1), m.group(2)
            # 抽前后字组成短语，存到 map
            pinyin_map[char] = f"{char}（{py}）"
    if not pinyin_map: return

    for q in questions:
        stem = q.get("stem","") or ""
        if not any(k in stem for k in ("字音","读音","拼音")):
            continue
        opts = q.get("options") or {}
        if not opts: continue
        new_opts = {}
        for k, v in opts.items():
            new_v = v
            # 对每个 option 文字里出现的 加点 ·X· 字符做拼音回填
            for m in re.finditer(r"·([一-鿿])·", v):
                char = m.group(1)
                if char in pinyin_map:
                    # 替换 ·X· → X（拼音）
                    new_v = new_v.replace(f"·{char}·", pinyin_map[char], 1)
            new_opts[k] = new_v
        q["options"] = new_opts


def _backfill_passage_qrange(passages: list[dict], questions: list[dict]) -> None:
    """很多 sub-passage 是"阅读材料"性质（材料一/材料二/(一)/古诗原文 等），它们自身
    没有题号，q_range=null。但同 section 内题目其实是综合这些材料作答。

    策略：对 q_range=null 的 passage，找同 section_type 邻近的有 q_range 的兄弟，
    借用其 q_range；若全 section 都没有，用 section 内所有题号的 [min, max]。
    """
    # 按 section_type 分组
    by_type: dict[str, list[dict]] = {}
    for ps in passages:
        by_type.setdefault(ps.get("type",""), []).append(ps)
    section_q_range: dict[str, list[int]] = {}
    for q in questions:
        sec = q.get("section","")
        section_q_range.setdefault(sec, []).append(q["number"])

    for sec, sec_passages in by_type.items():
        # 该 section 已有 q_range 的题号 union
        existing_qranges = [ps["q_range"] for ps in sec_passages if ps.get("q_range")]
        # 该 section 所有题号
        all_qs = section_q_range.get(sec, [])
        section_range = [min(all_qs), max(all_qs)] if all_qs else None
        for ps in sec_passages:
            if ps.get("q_range"): continue
            # 找邻近的兄弟 q_range
            if existing_qranges:
                # 用最近的（取第一个 sibling 的范围作 fallback）
                sib = existing_qranges[0]
                ps["q_range"] = list(sib)
            elif section_range:
                ps["q_range"] = section_range


def _assign_types(questions: list[dict]) -> None:
    """题型推断（不动 score）。道法 4 类：judge / choice / material / essay。"""
    for q in questions:
        ans = (q.get("answer","") or "").strip()
        sol = q.get("solution","") or ""
        stem = q.get("stem","") or ""
        sec = q.get("section","")
        if sec == "judge":
            q["type"] = "judge"
        elif sec == "choice" or (ans and re.fullmatch(r"[A-D]", ans)):
            q["type"] = "choice"
        elif sec == "material":
            # 写作/感悟题判别：stem 含 "写一篇" / "以...为题" / "不少于N字"
            if (re.search(r"写一篇|以.{0,15}为题|不少于\s*\d+\s*字|微访谈感悟|题目.{0,5}：", stem)):
                q["type"] = "essay"
            else:
                q["type"] = "material"
        else:
            # 兜底：判断题答案匹配 → judge
            if ans in ("正确","错误","√","×","对","错"):
                q["type"] = "judge"
            elif ans and re.fullmatch(r"[A-D]", ans):
                q["type"] = "choice"
            else:
                q["type"] = "material"


def _type_weight(qtype: str, n: int) -> int:
    """题型基础权重（用于 sub-section 内分配，可能被调整）。"""
    return {
        "judge":     1,    # 道法判断题
        "choice":    2,    # 道法选择题
        "material":  8,    # 道法材料分析题（平均 6-10 分）
        "essay":    12,    # 道法写作题（部分区独立写作 10-12 分；朝阳 Q25 是 essay）
    }.get(qtype, 2)


def _allocate_scores_in_block(qs_in_block: list[dict], total: int) -> None:
    """把 block 总分分配到 block 内每题。
    策略：先给固定项（choice=2、handwriting=1），余额平摊到主观题；
    最后差额调到末题确保 sum == total。
    """
    if not qs_in_block or total <= 0: return
    # 道法无 essay 二选一情况（朝阳 Q25 是单写作题，归 material section 内的 essay type）
    fixed_score = {}
    flex_idx = []
    for i, q in enumerate(qs_in_block):
        if q["type"] == "judge":
            fixed_score[i] = 1
        elif q["type"] == "choice":
            fixed_score[i] = 2
        else:
            # material / essay 在 flex（按 block 余额均分）
            flex_idx.append(i)
    fixed_sum = sum(fixed_score.values())
    remaining = total - fixed_sum
    if flex_idx and remaining > 0:
        per = max(1, remaining // len(flex_idx))
        for i in flex_idx: fixed_score[i] = per
        # 把差额贴到第一个 flex（赏析/简答这类常分数稍高）
        diff = remaining - per * len(flex_idx)
        if diff:
            fixed_score[flex_idx[0]] += diff
    elif not flex_idx and remaining != 0:
        # 全是固定题 + 余额 → 加到末题
        fixed_score[len(qs_in_block)-1] += remaining
    for i, q in enumerate(qs_in_block):
        q["score"] = fixed_score.get(i, 0)


def _assign_scores(questions: list[dict], score_blocks: list[dict]) -> None:
    """按 score_blocks（(共N分) 标记的子段）分配每题分数。
    score_blocks: [{start: int, end: int, total: int, level: 'section'|'sub'}]
    每题属于覆盖它的最小 block。
    """
    # 按 question.number 找对应 block（用 q._line_idx 与 block 的 start/end 比对）
    for q in questions:
        line_idx = q.get("_line_idx", 0)
        # 找最小覆盖 block
        cand = [b for b in score_blocks if b["start"] <= line_idx < b["end"]]
        if cand:
            # 取范围最小的（最具体的）
            cand.sort(key=lambda b: b["end"] - b["start"])
            q["_block_id"] = id(cand[0])
        else:
            q["_block_id"] = None
    # 按 block 聚合
    block_to_qs: dict[int, list[dict]] = {}
    for q in questions:
        bid = q.get("_block_id")
        block_to_qs.setdefault(bid, []).append(q)
    for bid, qs_in_block in block_to_qs.items():
        if bid is None:
            for q in qs_in_block: q["score"] = q.get("score", 0) or 0
            continue
        block = next(b for b in score_blocks if id(b) == bid)
        total = block["total"]
        _allocate_scores_in_block(qs_in_block, total)
    # 清理临时字段
    for q in questions:
        q.pop("_line_idx", None)
        q.pop("_block_id", None)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="zip 或单 docx 文件")
    ap.add_argument("--slug", help="覆盖默认 slug（如 2026-chaoyang-yi）")
    ap.add_argument("--out-root", type=Path,
                     default=Path("/Users/jiakui/projects/zhongkao-agent/knowledge-base/exams/_staging/politics"))
    a = ap.parse_args()
    src = a.src.resolve()
    if not src.exists():
        sys.exit(f"src 不存在: {src}")

    # 解析 slug
    if a.slug:
        slug = a.slug
    else:
        slug = _infer_slug(src.stem)
    out_dir = a.out_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"
    structured_dir = out_dir / "structured-cloud"
    structured_dir.mkdir(parents=True, exist_ok=True)
    docx_tmp = out_dir / "docx-extract"

    # 拿 docx 列表
    if src.suffix.lower() == ".zip":
        unzip_dir = out_dir / "src-unzip"
        docx_paths = _unzip_to(src, unzip_dir)
    elif src.suffix.lower() == ".docx":
        docx_paths = [src]
    else:
        sys.exit(f"不支持的输入: {src}")
    docx = _pick_jiexi_docx(docx_paths)
    print(f"[politics_docx_paper] 用解析版: {docx.name}", flush=True)

    # docx → markdown
    md = docx_to_markdown_chinese(docx, docx_tmp, figures_dir)
    # 保存 markdown 备查
    (structured_dir / "raw.md").write_text(md, encoding="utf-8")

    # 解析
    result = parse_docx_chinese(md, figures_dir)
    result["slug"] = slug
    result["source"] = "docx"
    result["subject"] = "politics"
    # 卷面元数据（让 enrich 写入 yaml 头部）
    _populate_exam_meta(result, slug, src.stem)

    # patches 系统（_patches/politics/<slug>.yaml）
    try:
        import yaml as Y
        patch_path = (Path(__file__).resolve().parent.parent.parent
                      / "knowledge-base" / "exams" / "_patches" / "politics"
                      / f"{slug}.yaml")
        if patch_path.exists():
            patches = Y.safe_load(patch_path.read_text(encoding="utf-8")) or {}
            applied = _apply_patches(patches, result)
            if applied:
                print(f"[politics_docx_paper] 🔧 应用 {applied} 处 patch ({patch_path.name})", flush=True)
    except Exception as e:
        print(f"[politics_docx_paper] ⚠ patch 加载失败: {e}", flush=True)
    fj = structured_dir / "final.json"
    fj.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    qs = result["questions"]
    print(f"[politics_docx_paper] ✅ {fj}", flush=True)
    print(f"   slug: {slug}")
    print(f"   题号: {sorted(q['number'] for q in qs)}")
    print(f"   passages: {len(result['passages'])}  questions: {len(qs)}  "
          f"answers: {len(result['answers'])}  full_score: {result['full_score']}")
    return result


def _apply_patches(patches: dict, result: dict) -> int:
    """对 result（final.json 结构，questions 用 `number` 字段）应用 patches。
    schema 同 image 路线 _patches/chinese/*.yaml：
      passages.<id>.body_replace/body_append/figure/body
      questions.<N>.{stem,stem_append,options,solution,answer,type,score,create}
    """
    n_applied = 0
    # passages
    ps_patches = patches.get("passages") or {}
    for pid, patch in ps_patches.items():
        for ps in result.get("passages", []):
            if ps["id"] != pid: continue
            for rep in patch.get("body_replace") or []:
                if rep.get("from") and rep["from"] in ps.get("body",""):
                    ps["body"] = ps["body"].replace(rep["from"], rep.get("to",""))
                    n_applied += 1
            if patch.get("body_append"):
                ps["body"] = (ps.get("body","") + patch["body_append"]); n_applied += 1
            if patch.get("figure"):
                ps["figure"] = patch["figure"]; n_applied += 1
            if patch.get("body"):
                ps["body"] = patch["body"]; n_applied += 1
            break
    # questions（按 number 字段在 result["questions"] 找）
    q_patches = patches.get("questions") or {}
    for qid_raw, patch in q_patches.items():
        qid = int(qid_raw)
        target = next((q for q in result["questions"] if q["number"] == qid), None)
        if target is None and patch.get("create"):
            new_q = {
                "number": qid,
                "type": patch.get("type", "subjective_blank"),
                "stem": patch.get("stem", ""),
                "options": patch.get("options"),
                "answer": patch.get("answer", ""),
                "solution": patch.get("solution", ""),
                "score": patch.get("score", 0),
                "section": patch.get("section", ""),
            }
            insert_at = next((i for i, q in enumerate(result["questions"])
                              if q["number"] > qid), len(result["questions"]))
            result["questions"].insert(insert_at, new_q)
            # **R5.3**：create 出来的新题也要进 result["answers"] 列表，否则
            # enrich 读 answers 时找不到这题，stem/sol 在 questions 但 enrich
            # 输出 yaml 时 solution 为空（朝阳道法 Q25 教训）
            new_ans = {
                "number": qid,
                "correct": patch.get("answer", ""),
                "solution": patch.get("solution", ""),
            }
            ans_insert = next(
                (i for i, a in enumerate(result.get("answers", []))
                 if a.get("number", 0) > qid),
                len(result.get("answers", []))
            )
            result.setdefault("answers", []).insert(ans_insert, new_ans)
            n_applied += 1
            continue
        if target is None: continue
        q = target
        if patch.get("stem") is not None:
            q["stem"] = patch["stem"]; n_applied += 1
        if patch.get("stem_append"):
            q["stem"] = q.get("stem","") + patch["stem_append"]; n_applied += 1
        if patch.get("options") is not None:
            q["options"] = patch["options"]; n_applied += 1
        if patch.get("solution") is not None:
            q["solution"] = patch["solution"]; n_applied += 1
        if patch.get("answer") is not None:
            q["answer"] = patch["answer"]; n_applied += 1
        if patch.get("type"):
            q["type"] = patch["type"]; n_applied += 1
        if patch.get("score") is not None:
            q["score"] = patch["score"]; n_applied += 1
    # 同步 answer/solution 到 answers 列表
    if n_applied:
        q_by_num = {q["number"]: q for q in result.get("questions", [])}
        for a in result.get("answers", []):
            n = a.get("number")
            q = q_by_num.get(n)
            if q:
                if q.get("answer"): a["correct"] = q["answer"]
                if q.get("solution"): a["solution"] = q["solution"]
        result["full_score"] = sum(q.get("score", 0) or 0 for q in result["questions"])
    return n_applied


def _populate_exam_meta(result: dict, slug: str, src_stem: str) -> None:
    """从 slug + 源文件名抽 year / district / exam_type / duration_minutes，
    写到 result 顶层。让 enrich 直接读用（避免 enrich 再走 NormalizedPaper
    的 exam_name 解析路径）。"""
    region_cn_map = {
        "chaoyang":"朝阳区","haidian":"海淀区","xicheng":"西城区","dongcheng":"东城区",
        "fengtai":"丰台区","shijingshan":"石景山区","mentougou":"门头沟区","fangshan":"房山区",
        "tongzhou":"通州区","shunyi":"顺义区","changping":"昌平区","daxing":"大兴区",
        "pinggu":"平谷区","yanqing":"延庆区","huairou":"怀柔区","miyun":"密云区",
        "yanshan":"燕山区",
    }
    type_cn_map = {"yi": "一模", "er": "二模", "zhen": "中考", "qmo": "期末"}
    parts = slug.split("-")
    year = int(parts[0]) if parts and parts[0].isdigit() else None
    region_en = parts[1] if len(parts) > 1 else ""
    type_en = parts[2] if len(parts) > 2 else "yi"
    district = region_cn_map.get(region_en, "")
    exam_type = type_cn_map.get(type_en, "一模")
    result["year"] = year
    result["district"] = district
    result["exam_type"] = exam_type
    result["duration_minutes"] = 70   # 北京中考道法 70 分钟（开卷）
    result["exam_format"] = "open_book"  # 道法是开卷考
    # exam 名称（供 enrich NormalizedPaper.from_final 用）
    result["exam"] = f"{year}年北京{district}中考{exam_type}{result.get('subject','道法')}"


def _infer_slug(stem: str) -> str:
    # 朝阳 / 海淀 / 西城 ... 区识别
    region_map = {
        "朝阳":"chaoyang","海淀":"haidian","西城":"xicheng","东城":"dongcheng",
        "丰台":"fengtai","石景山":"shijingshan","门头沟":"mentougou","房山":"fangshan",
        "通州":"tongzhou","顺义":"shunyi","昌平":"changping","大兴":"daxing",
        "平谷":"pinggu","延庆":"yanqing","怀柔":"huairou","密云":"miyun",
        "燕山":"yanshan",
    }
    region = None
    for cn, en in region_map.items():
        if cn in stem:
            region = en; break
    # 取最后/最大年份（"2025-2026学年" 文件名取 2026）
    years = re.findall(r"(20\d{2})", stem)
    year = max(years) if years else "2026"
    typ = "yi" if "一模" in stem else ("er" if "二模" in stem else "yi")
    if not region:
        return f"{year}-unknown-{typ}"
    return f"{year}-{region}-{typ}"


if __name__ == "__main__":
    main()
