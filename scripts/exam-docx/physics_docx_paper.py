#!/usr/bin/env python3
"""physics_docx_paper — 北京中考物理 docx 解析版 → final.json

跟 chinese_docx_paper.py 基本同构（解析版结构一样：题面+【答案】+【N题详解】
交替），只是物理特有：
  - SECTION_HEADERS：单选 / 多选 / 实验探究 / 科普阅读 / 计算 / 综合应用
  - 多选题答案可多字母（如 AD / BD / ABD）
  - 题型：choice / multi_choice / experiment / comprehensive / calculation
  - 不需要：加点字 / 下划线 / 拼音回填 / passage 二级模型 / 默写 / 资料分块
  - 内嵌图很多（电路图/装置图/示意图），全部抽到 figures/

北京中考物理满分 70 分（朝阳/类似区一模均如此）：
  一、单项选择 12 题 × 2 = 24
  二、多项选择 3 题 × 2 = 6
  三、实验探究 8 题（3/4 分混合）= 28
  四、科普阅读 1 题 = 4
  五、计算题 2 题 × 4 = 8
"""
from __future__ import annotations
import argparse, json, os, re, shutil, sys, tempfile, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "exam-ocr"))

# 复用 docx_paper 的底层 docx 解析
import docx_paper as dp  # noqa: E402
from omml2latex import omml_to_latex  # noqa: E402  物理需要保留公式
from paths import derive_out_dir  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V_NS = "urn:schemas-microsoft-com:vml"

# 模块级 mutable 状态：每次 docx_to_markdown_chinese 调用前在 main() 设置 / 重置。
# 内含 {"formulas": [latex,...], "idx": int}。_extract_ole_object 每被调用一次 idx+1。
# 用全局态避免给 _walk_paragraph_chinese / _walk_run_chinese / _walk_table_chinese
# 三层嵌套 walker 都改签名。
_FORMULA_STATE: dict = {"formulas": [], "idx": 0}


def _extract_ole_object(obj_el: ET.Element, rels: dict[str, str],
                          extract_dir: Path, figures_dir: Path,
                          formula_state: dict | None = None) -> str:
    """OLE 嵌入对象（MathType 公式）。三层 fallback：
      1. **优先**：docx2tex 预跑的 LaTeX cache（formula_state["formulas"]）→ $LaTeX$
      2. PNG 兄弟（soffice 转的）→ ![](figures/xxx.png)
      3. WMF 没转 → [公式] 占位

    formula_state: {"formulas": list[str], "idx": int}（mutable，跨调用累加 idx）
    """
    import shutil

    # 路线 1: docx2tex LaTeX cache（按出现顺序匹配）
    if formula_state is not None and formula_state.get("formulas"):
        idx = formula_state["idx"]
        formulas = formula_state["formulas"]
        if idx < len(formulas):
            latex = formulas[idx]
            formula_state["idx"] = idx + 1
            # 行内公式：$...$（KaTeX/MathJax 渲染）
            return f"${latex}$"
        # cache 不够长，落回路线 2/3

    # 路线 2/3: WMF/PNG fallback（保留原逻辑）
    for vd in obj_el.iter(f"{{{V_NS}}}imagedata"):
        rid = vd.get(f"{{{R_NS}}}id") or vd.get(f"{{{R_NS}}}href")
        if not rid: continue
        target = rels.get(rid)
        if not target: continue
        src = extract_dir / "word" / target
        if not src.exists():
            src = extract_dir / target.lstrip("/.")
        if not src.exists():
            src = extract_dir / re.sub(r"^(\.\./)+", "", target)
        if not src.exists():
            continue
        figures_dir.mkdir(parents=True, exist_ok=True)
        out = figures_dir / src.name
        if not out.exists():
            shutil.copy(src, out)
        # WMF/EMF 浏览器不显示。优先用同名 png 兄弟文件
        if out.suffix.lower() in (".wmf", ".emf"):
            png_sibling = out.with_suffix(".png")
            if png_sibling.exists():
                return f"![](figures/{png_sibling.name})"
            return f"[公式]"
        return f"![](figures/{out.name})"
    return ""

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
        elif tag == "oMath" and ns == f"{{{M_NS}":
            # 物理保留 OMML 公式（转 LaTeX inline $...$）
            out.append(omml_to_latex(child))
        elif tag == "object":
            # OLE MathType 公式：优先用 docx2tex LaTeX cache（_FORMULA_STATE）
            img = _extract_ole_object(child, rels, extract_dir, figures_dir,
                                       formula_state=_FORMULA_STATE)
            if img: out.append(img)
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
        ns = child.tag.rsplit("}", 1)[0] if "}" in child.tag else ""
        if tag == "r":
            out.append(_walk_run_chinese(child, rels, extract_dir, figures_dir))
        elif tag == "hyperlink":
            for r in child.findall(f"{{{W_NS}}}r"):
                out.append(_walk_run_chinese(r, rels, extract_dir, figures_dir))
        elif tag == "smartTag":
            out.append(_walk_paragraph_chinese(child, rels, extract_dir, figures_dir))
        elif tag == "oMath" and ns == f"{{{M_NS}":
            out.append(omml_to_latex(child))
        elif tag == "oMathPara" and ns == f"{{{M_NS}":
            # 块级公式：内含多个 oMath，逐个转
            for om in child.findall(f"{{{M_NS}}}oMath"):
                out.append(omml_to_latex(om))
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


def _count_ole_objects(docx_path: Path) -> int:
    """统计 docx body 内 <w:object> 数量（即 MathType OLE 公式总数），
    用于和 docx2tex 抽出的 LaTeX cache 比覆盖率，及早发现 d2t hub regex bug。
    """
    try:
        with zipfile.ZipFile(docx_path) as zf:
            doc = zf.read("word/document.xml").decode("utf-8", "ignore")
        return doc.count("<w:object")
    except Exception:
        return 0


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
    # 仅"答案"独立 docx（如石景山 "石景山--xxx-初三物理答案定稿.docx"）也算"试卷"模式时
    # 排除掉，避免被 max(size) 选成主文档
    non_answer = [p for p in docx_paths if "答案" not in p.stem]
    if non_answer:
        return max(non_answer, key=lambda d: d.stat().st_size)
    if docx_paths:
        return max(docx_paths, key=lambda d: d.stat().st_size)
    raise FileNotFoundError("zip 内未找到 docx")


def _pick_answer_only_docx(docx_paths: list[Path], jiexi: Path) -> Path | None:
    """挑独立答案 docx（试卷+答案双文件格式专用）。
    判定：jiexi 不是「解析」版（即只是试卷） + 存在含「答案」字样的兄弟 docx。
    返回 None 时不进入双文件 merge 流程（视作单 docx，按"精品解析"格式处理）。

    样例：
      - changping: 【试卷】xxx.docx + 【答案】xxx.docx
      - shijingshan: 【试卷】xxx.docx + 石景山--xxx-初三物理答案定稿(1).docx
    """
    if "解析" in jiexi.stem and "原卷" not in jiexi.stem:
        return None  # 主文档是精品解析版，已含答案
    for p in docx_paths:
        if p == jiexi: continue
        if "答案" in p.stem:
            return p
    return None


# ─── section / 题号 切分 ────────────────────────────────────────────────────

# **物理 section header（按内容关键词识别，跨区一致）**
# 北京中考物理 5 大题：单选 / 多选 / 实验 / 科普 / 计算
# 容错：朝阳"单项选择题"/海淀"单选题"/门头沟"单选题"，"选"和"选择"都接受
SECTION_HEADERS = [
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*单项?\s*选择?\s*题?"),         "choice"),
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*多项?\s*选择?\s*题?"),         "multi_choice"),
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*实验\s*(?:探究|题)?"),         "experiment"),
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*(?:科普|阅读)\s*(?:阅读|题)?"), "comprehensive"),
    # "计算题" / "应用题" / "论述、计算题"（大兴）/ "计算与论述题"
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*(?:计算|应用|论述)[\s、，,/]*"
                 r"(?:计算|应用|论述)?\s*题?"),                                 "calculation"),
    # 综合应用（部分区有）
    (re.compile(r"^\s*[一二三四五六七]\s*[、.]\s*综合\s*(?:应用|题)?"),         "comprehensive"),
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
# 子问号（实验题 "（1）/（2）/(1)/(2)" 等）。用于探测"题头独立段+紧随子问"的跨段格式
# 海淀 Q17 案例：题头单独一段 `17. ` 仅 3 字符，紧接 `（1）...`（小问题 body）
SUBQ_FOLLOW_RE = re.compile(r"^\s*[（(][1-9一二三四五][)）]")
# 选项行（A. X B. Y / A. X\nB. Y / A.X\tB.Y 等）
OPT_LINE_RE = re.compile(r"(?:^|\s)([A-D])\s*[.、．]\s*([^\sA-D].*?)(?=\s+[A-D]\s*[.、．]|$)")
# 答案 / 详解 marker
ANSWER_MARKER_RE = re.compile(r"^\s*【答案】")
DETAIL_TITLE_RE = re.compile(r"^\s*【(\d{1,2})题详解】")
GENERIC_DETAIL_RE = re.compile(r"^\s*【详解】")
# 物理实验/计算题的小问详解（【小问1详解】【小问2详解】等）
SUB_DETAIL_RE = re.compile(r"^\s*【小问(\d+)详解】")
DAOYU_RE = re.compile(r"^\s*【导语】(.*)$")  # 文章导语
DIANJING_RE = re.compile(r"^\s*【点睛】(.*)$")  # 多含 古诗文译文
ANALYSIS_RE = re.compile(r"^\s*【解析】")
# Cover/noise
NOISE_LINE_RE = re.compile(
    r"^\s*(?:学校[_\s]+班级|2026\.\d{1,2}|考生须知|\d+\s*年.*?试卷\s*$"
    r"|本试卷共\d+页|考试时间\d+\s*分钟"
    r"|语文试卷|声明.*?著作权|发布日期|菁优网"
    r"|参考答案|答案及评分"
    # 物理多区把 "第一/二/三/四部分" 写成单独一行的卷面分段标记，
    # 会泄漏到 Q15 等的 solution 末尾。当作噪声过滤。
    r"|第[一二三四五六]部分)\s*$")


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

    for i, ln in enumerate(lines):
        sec_m = _is_section_header(ln)
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
        if SUB_HEADER_RE.match(ln) and mode == "answer":
            mode = "question"
            if cur_typ:
                sections[cur_typ].append(ln)
            continue
        # **answer 模式里出现新题号锚（N > last_q_seen），且行不含【】标记 → 切回 question**
        # 用于解析版里 sub-header 缺失但题号跳过的情形
        q_m = NUM_HEAD_RE.match(ln)
        if (mode == "answer" and q_m and "【" not in ln):
            n = int(q_m.group(1))
            if n > last_q_seen and n <= 30:
                # 排除答案里的 "N. <短内容>" 这种短答案。但 essay 题号锚常很短
                # （朝阳 Q26 "26. 按要求作文。" 只 10 字符），所以在 essay section
                # 内放宽门槛。
                # **物理实验题 "题头-体跨段" 兜底**：海淀 Q17 题头独立段 `17. `
                # 只 3 字符 < 15 被 min_len 守卫挡掉。若紧随其后 ≤5 行内出现 `(N)`
                # 子问号，认定为实验题头跨段，bypass min_len 直接切回 question。
                has_subq = any(
                    SUBQ_FOLLOW_RE.match(lines[j])
                    for j in range(i+1, min(len(lines), i+6))
                )
                min_len = 6 if cur_typ == "essay" else 15
                if has_subq or len(ln.strip()) >= min_len:
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
            # **严格单调递增**：防止科普阅读题干里 "1．压缩 2．加热 3．膨胀 4．回收"
            # 工艺流程数字把 last_q_seen 从 24 倒退到 4，导致后续【答案】块归错题
            if n <= 30 and n > last_q_seen: last_q_seen = n
        if cur_typ:
            sections[cur_typ].append(ln)

    # 2. 每大题内：切 passage 子段 + 题号
    passages: list[dict] = []
    questions: list[dict] = []
    for sec_typ, sec_lines in sections.items():
        _parse_section(sec_typ, sec_lines, passages, questions, figures_dir)

    # 3. 解析答案 + 详解
    valid_qs = {q["number"] for q in questions}
    answers_map = _parse_answers(a_lines, valid_qs)
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
        # stem_head 取第一行非空内容前 6 字符（无换行干扰）
        stem_first_line = next((l for l in (q.get("stem","") or "").split("\n")
                                if l.strip()), "")
        stem_head = stem_first_line.strip()[:8]
        # 优先匹配题号 + stem_head；若失败 fallback 到首个题号锚（防 "16."
        # 单独一行后跟空行/子题如 "（1）..." 的情形，xicheng/海淀实验题常见）
        primary_match = None
        fallback_match = None
        for i, ln in enumerate(md_lines):
            m = NUM_HEAD_RE.match(ln)
            if not m or int(m.group(1)) != n: continue
            if fallback_match is None:
                fallback_match = i
            if stem_head and stem_head[:4] in ln:
                primary_match = i
                break
        q["_line_idx"] = primary_match if primary_match is not None else (
            fallback_match if fallback_match is not None else 0)
    score_blocks = _parse_score_blocks(md, questions)
    # 物理实验题等显式标注的"X、Y题各N分"
    per_q_fixed = _parse_per_question_scores(md)
    _assign_scores(questions, score_blocks, per_q_fixed)

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
    seen_max = 0   # 题号必须严格递增；防 "1. 压缩 2. 加热..." 工艺流程被误识
    for i, ln in enumerate(sec_lines):
        sub_m = SUB_HEADER_RE.match(ln)
        if sub_m:
            sub_starts.append((i, sub_m.group(1)))
            continue
        q_m = NUM_HEAD_RE.match(ln)
        if q_m and 1 <= int(q_m.group(1)) <= 30:
            n = int(q_m.group(1))
            if n <= seen_max:
                continue   # 题号回退或重复，跳过（科普阅读文中编号、答案中编号等）
            q_starts.append((i, n, q_m.group(2)))
            seen_max = n

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
    # 匹配 A. ... 直到下一个 [A-D]\s*[.、．] 或子问题号 "（N）"/"(N)" 或 EOF
    # 物理科普阅读题（pinggu/fangshan/shijingshan/yanqing Q24）有 3 选项 + 后接 (3)(4) 填空，
    # 不加 (N) 边界会把 (3) 段塞进最后一个选项
    for m in re.finditer(
        r"\b([A-D])\s*[.、．]\s*(.*?)"
        r"(?=(?:\s+[A-D]\s*[.、．])|(?:\s+[（\(]\s*\d+\s*[）\)])|\Z)",
        opts_part, re.DOTALL):
        key = m.group(1)
        val = m.group(2).strip().replace("\n", " ").strip()
        if key not in opts:
            opts[key] = val
    # 剩余 "(3) ..." 子问题文本回挂到 stem
    tail_m = re.search(r"\s+([（\(]\s*\d+\s*[）\)].*)$", opts_part, re.DOTALL)
    if tail_m and opts:
        stem = (stem + "\n\n" + tail_m.group(1).strip()).strip()
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


# ─── 双文件 (试卷+答案) merge ────────────────────────────────────────────
# 用于 zxxk 把试卷和答案拆成两份 docx 的区（changping/shijingshan 等）。
# 把答案 docx 的 markdown 转成 "【答案】...【N题详解】..." 等价的合成行，
# 追加到主 markdown 末尾，让 parse_docx_chinese 状态机正常工作。

# 答案表格行：| 题号 | 1 | 2 | ... |  + | 答案 | C | D | ... |
_ANS_TABLE_HEADER_RE = re.compile(r"^\|\s*题号\s*\|")
_ANS_TABLE_ANS_RE = re.compile(r"^\|\s*答案\s*\|")
# 题号行（如 "16．（1）2.2（2分）" / "17．（1）20（1分）"）
_ANS_Q_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.+)$")


def _extract_answers_from_ans_docx_md(ans_md: str) -> list[str]:
    """从「答案」docx markdown 抽出每题 answer / sol，
    返回追加到主 md 末尾的合成行（含【答案】+【N题详解】 marker）。

    答案 docx 结构（changping/shijingshan 通用）：
      [section header  →  | 题号 | ... |  →  | 答案 | C | D | ... |]
        ↓ 选择题对照表
      [section header  →  N．（1）xxx（2分）...]
        ↓ 主观题正文（题号开头）
    """
    lines = ans_md.split("\n")
    selected: dict[int, str] = {}   # {N: "C"} 选择题答案表
    subjective: dict[int, list[str]] = {}   # {N: [...lines]} 主观题答案文本
    cur_subj: int | None = None

    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        # 检测 "| 题号 | 1 | 2 | ... |" → 找下一个 "| 答案 | C | D | ... |"
        if _ANS_TABLE_HEADER_RE.match(ln):
            nums = [c.strip() for c in ln.strip("|").split("|") if c.strip()][1:]
            # 找紧邻的答案行（跳过 separator "|---|---|"）
            for j in range(i+1, min(i+5, len(lines))):
                ln2 = lines[j].strip()
                if _ANS_TABLE_ANS_RE.match(ln2):
                    ans_cells = [c.strip() for c in ln2.strip("|").split("|") if c.strip()][1:]
                    for k, n_str in enumerate(nums):
                        if k < len(ans_cells) and n_str.isdigit():
                            n = int(n_str)
                            ans = ans_cells[k]
                            if re.fullmatch(r"[A-D]{1,4}", ans):
                                selected[n] = ans
                    i = j + 1
                    break
            else:
                i += 1
            continue
        # 检测题号锚 "N．..."（不在选择题表内）
        m = _ANS_Q_HEAD_RE.match(ln)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 30 and n not in selected:
                cur_subj = n
                subjective.setdefault(n, []).append(m.group(2).strip())
                i += 1
                continue
        # 续行：归到 cur_subj
        if cur_subj is not None and ln and not ln.startswith("|"):
            # 跳过明显的 section header（"三、实验探究题..."）
            if not _is_section_header(ln):
                # 也跳过 "题号" 表残行
                if not ln.startswith("题号") and not ln.startswith("答案"):
                    subjective[cur_subj].append(ln)
        i += 1

    # 生成合成 markdown 行
    out: list[str] = []
    # 选择题：每条 "【答案】N. X" 单行，便于 _parse_answers 的 N. 锚解析
    for n in sorted(selected):
        out.append(f"【答案】{n}. {selected[n]}")
    # 主观题：每题 "【N题详解】<sol>" 单段，_parse_answers 的 DETAIL_TITLE_RE 会处理
    for n in sorted(subjective):
        chunks = [l for l in subjective[n] if l.strip()]
        if not chunks: continue
        body = " ".join(chunks)
        # 去掉行内残留 "（N分）" 评分括号（让 sol 干净点；评分仍由 _parse_per_question_scores 抓）
        body_clean = re.sub(r"[（\(]\s*\d+\s*分\s*[）\)]", "", body).strip()
        out.append(f"【{n}题详解】{body_clean}")
    return out


# ─── 答案 / 详解 解析 ──────────────────────────────────────────────────────

def _parse_answers(a_lines: list[str], valid_qs: set[int] | None = None) -> dict[int, dict]:
    _ = valid_qs  # 暂保留接口；逻辑用 entered_qs（见下）
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
    # 已"进入"过答案块的题号；防 Q17 三小问标 【17/18/19题详解】误识为 Q18/Q19 大题详解
    entered_qs: set[int] = set()

    def _flush_answer_buf():
        if not answer_buf: return
        text = " ".join(answer_buf)
        # 拆按 "N. " 题号锚；要求 "N." 后跟非数字（避免把 2.4 / 1.08×10⁷ 中的
        # 小数误识为题号——物理高频）。若整体无 "N." 前缀，归到 default_q
        parts = re.split(r"\s+(?=\d{1,2}\s*[.、．]\s*[^\d])", text)
        for part in parts:
            # 同样排除小数：N. 后必须跟非数字才算题号锚（防 "2.50" 被当 Q2+"50"）
            m = re.match(r"\s*(\d{1,2})\s*[.、．]\s*(?=[^\d])(.+)$", part, re.DOTALL)
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
            # choice 单字母答案 OR 多选多字母（物理 多选 AD/BD/ABD/ABCD）
            m_letter = re.match(r"^([A-D]{1,4})(?:\s|$)", content)
            if m_letter and len(content) <= 5:
                letters = m_letter.group(1)
                # 单字母 → choice / 多字母 → multi_choice 但都存 correct
                out[n]["correct"] = letters
            else:
                sol = re.sub(r"^(?:示例[:：]|参考[:：]|例文[:：]?)\s*", "", content)
                # 防覆盖：若已有更长 solution，跳过
                if not out[n]["solution"] or len(sol) > len(out[n]["solution"]):
                    out[n]["solution"] = sol
        answer_buf.clear()

    for ln in a_lines:
        # 上下文标记（由 parse_docx_chinese 注入）
        if ln.startswith("__Q_CTX__:"):
            try:
                default_q = int(ln.split(":",1)[1])
                entered_qs.add(default_q)
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
            n_detail = int(dm.group(1))
            # **防误识** 解析版 quirk：Q17 三个小问标 【17/18/19题详解】，但真正
            # 的 Q18/Q19 答案块还没进入（entered_qs 不含 18/19），且 N 离 default_q 很近。
            # 视为 default_q 的子问详解，sub_n = N - default_q + 1。
            if (n_detail not in entered_qs and default_q
                and 0 < (n_detail - default_q) <= 5):
                cur_detail = default_q
                detail_blocks.setdefault(cur_detail, [])
                sub_n = n_detail - default_q + 1
                after = ln[dm.end():].strip()
                detail_blocks[cur_detail].append(f"\n（{sub_n}）{after}".rstrip())
                continue
            cur_detail = n_detail
            detail_blocks.setdefault(cur_detail, [])
            # 同行内容也收（防 "【N题详解】内容..." 单行格式）
            after = ln[dm.end():].strip()
            if after:
                detail_blocks[cur_detail].append(after)
            continue
        if GENERIC_DETAIL_RE.match(ln):
            # 【详解】= 单题情况，把后续内容归到 default_q
            _flush_answer_buf()
            in_answer_block = False
            if default_q:
                cur_detail = default_q
                detail_blocks.setdefault(cur_detail, [])
                # **关键**：【详解】后同行内容也要收（物理多题是
                # "【详解】食品夹在使用过程中...故选D。" 单行格式）
                after = re.sub(r"^\s*【详解】\s*", "", ln)
                if after.strip():
                    detail_blocks[cur_detail].append(after)
            continue
        if SUB_DETAIL_RE.match(ln):
            # 【小问N详解】= 多空题的某个子问题详解（物理实验/计算高频）
            # 归到 default_q（多个小问详解都汇总到同一题）
            _flush_answer_buf()
            in_answer_block = False
            if default_q:
                cur_detail = default_q
                detail_blocks.setdefault(cur_detail, [])
                sub_m = SUB_DETAIL_RE.match(ln)
                after = ln[sub_m.end():].strip()
                # 加子问题标签 + 同行内容
                detail_blocks[cur_detail].append(f"\n（{sub_m.group(1)}）{after}".rstrip())
            continue
        if DAOYU_RE.match(ln) or DIANJING_RE.match(ln):
            cur_detail = None
            continue
        if NOISE_LINE_RE.match(ln):
            # 卷面分段噪声（"第二部分" 等）：不进 answer 也不进 detail
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
        # 清理行内残留的 【小问N详解】 / 【N题详解】 marker（行首已由 SUB_DETAIL_RE 处理，
        # 但 image+marker 同行格式 ![](image.png)【小问2详解】 漏过；这里二次清洗）
        text = re.sub(r"【小问\d+详解】", "", text)
        text = re.sub(r"【\d{1,2}题详解】", "", text)
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

# 标准 section 总分（北京中考物理，跨区一致 ≈70）
STANDARD_SECTION_TOTAL = {
    "choice":         24,   # 一、单选 12 题 × 2
    "multi_choice":   6,    # 二、多选 3 题 × 2
    "experiment":     28,   # 三、实验 8 题
    "comprehensive":  4,    # 四、科普阅读 1 题
    "calculation":    8,    # 五、计算 2 题 × 4
}


# （共N分）/（N分）标记
SCORE_BRACKET_RE = re.compile(r"[（\(]\s*共?\s*(\d+)\s*分\s*[）\)]")
# 大题头里的总分（一/二/三/四/五 + 共N分）
# 兼容头括号里继续写细节："（共11分，24题3分，26、27题各4分）"
SECTION_TOTAL_RE = re.compile(
    r"^\s*[一二三四五]\s*[、.]\s*[^（\(]*[（\(]\s*共?\s*(\d+)\s*分")
# 子段总分（(一)/(二)/(三)  + 共?N分）
SUB_TOTAL_RE = re.compile(
    r"^\s*[（\(][一二三四五][）\)][^（\(]*[（\(]\s*共?\s*(\d+)\s*分\s*[）\)]")


_PER_Q_SCORE_RE = re.compile(
    # 兼容 "16、17、19题各3分"（多题用 各） 和 "24题3分"（单题不带 各）
    r"([0-9]+(?:[、,，][0-9]+)*)\s*题\s*各?\s*(\d+)\s*分"
)


def _parse_per_question_scores(md: str) -> dict[int, int]:
    """从 section header 抽 "X、Y、Z 题各 N 分" 显式标注。
    朝阳物理 三、实验探究 header："共28分，16、17、19、23题各3分，18、20、21、22题各4分"
    返回 {题号: 分值}。
    """
    out: dict[int, int] = {}
    for line in md.split("\n"):
        for m in _PER_Q_SCORE_RE.finditer(line):
            nums_str, sc = m.group(1), int(m.group(2))
            for n in re.split(r"[、,，]", nums_str):
                if n.strip().isdigit():
                    out[int(n.strip())] = sc
    return out


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
    """题型推断（不动 score）。物理 type 直接由 section 决定。"""
    for q in questions:
        sec = q.get("section","")
        ans = q.get("answer","")
        # 直接按 section 映射
        if sec == "choice":
            q["type"] = "choice"
        elif sec == "multi_choice":
            q["type"] = "multi_choice"
        elif sec == "experiment":
            q["type"] = "experiment"
        elif sec == "comprehensive":
            q["type"] = "comprehensive"
        elif sec == "calculation":
            q["type"] = "calculation"
        # 兜底：答案是 A-D 单字母 → choice；多字母 → multi_choice
        elif ans:
            if re.fullmatch(r"[A-D]", ans):
                q["type"] = "choice"
            elif re.fullmatch(r"[A-D]{2,4}", ans):
                q["type"] = "multi_choice"
            else:
                q["type"] = "experiment"
        else:
            q["type"] = "experiment"


def _type_weight(qtype: str, n: int) -> int:
    """题型基础权重（物理 sub-section 内分配）。"""
    return {
        "choice":         2,
        "multi_choice":   2,
        "experiment":     3,    # 实验题平均，但可能 3 或 4 分
        "comprehensive":  4,
        "calculation":    4,
    }.get(qtype, 2)


def _allocate_scores_in_block(qs_in_block: list[dict], total: int) -> None:
    """把 block 总分分配到 block 内每题（物理）。
    - choice / multi_choice：固定 2 分（北京物理标准）
    - calculation：每题 4 分（朝阳/标准均如此）
    - comprehensive：4 分（科普阅读 1 题，1 个 block）
    - experiment：3 或 4 分，按 block 总分均摊 + 差额给最后题
    """
    if not qs_in_block or total <= 0: return
    fixed_score = {}
    flex_idx = []
    for i, q in enumerate(qs_in_block):
        t = q["type"]
        if t == "choice":
            fixed_score[i] = 2
        elif t == "multi_choice":
            fixed_score[i] = 2
        elif t == "calculation":
            fixed_score[i] = 4
        elif t == "comprehensive":
            # 科普阅读总 4 分 1 题（朝阳）；若多于 1 题则平摊
            fixed_score[i] = max(1, total // len(qs_in_block))
        else:
            # experiment 类：留作 flex
            flex_idx.append(i)
    fixed_sum = sum(fixed_score.values())
    remaining = total - fixed_sum
    if flex_idx and remaining > 0:
        per = max(1, remaining // len(flex_idx))
        for i in flex_idx: fixed_score[i] = per
        # 差额贴到最后一个 flex 题（通常分值大题在末尾）
        diff = remaining - per * len(flex_idx)
        if diff:
            fixed_score[flex_idx[-1]] += diff
    elif not flex_idx and remaining != 0:
        fixed_score[len(qs_in_block)-1] += remaining
    for i, q in enumerate(qs_in_block):
        q["score"] = fixed_score.get(i, 0)


def _assign_scores(questions: list[dict], score_blocks: list[dict],
                    per_q_fixed: dict[int, int] | None = None) -> None:
    """按 score_blocks 分配每题分数；per_q_fixed 是 header 显式标注（"X题各N分"）。
    流程：
      1. 优先用 per_q_fixed（最准确）
      2. 剩余题号走 block 均摊（_allocate_scores_in_block）
    """
    per_q_fixed = per_q_fixed or {}
    for q in questions:
        line_idx = q.get("_line_idx", 0)
        cand = [b for b in score_blocks if b["start"] <= line_idx < b["end"]]
        if cand:
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
        # **优先用 per_q_fixed**：该 block 内题号若在 per_q_fixed 中，固定分值；
        # 剩余题号在剩余分数里均摊
        fixed_in_block = {q["number"]: per_q_fixed[q["number"]]
                          for q in qs_in_block if q["number"] in per_q_fixed}
        if fixed_in_block:
            for q in qs_in_block:
                if q["number"] in fixed_in_block:
                    q["score"] = fixed_in_block[q["number"]]
            remaining_total = total - sum(fixed_in_block.values())
            remaining_qs = [q for q in qs_in_block if q["number"] not in fixed_in_block]
            if remaining_qs and remaining_total > 0:
                _allocate_scores_in_block(remaining_qs, remaining_total)
            elif remaining_qs:
                for q in remaining_qs: q["score"] = 0
        else:
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
                     default=Path("/Users/jiakui/projects/zhongkao-agent/knowledge-base/exams/_staging/physics"))
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
    print(f"[physics_docx_paper] 用主 docx: {docx.name}", flush=True)
    ans_only_docx = _pick_answer_only_docx(docx_paths, docx)
    if ans_only_docx:
        print(f"[physics_docx_paper] 📎 双文件模式，附加答案 docx: {ans_only_docx.name}",
              flush=True)

    # docx → markdown（同时把 docx unzip 到 docx_tmp/，下面会用 word/embeddings/）
    md = docx_to_markdown_chinese(docx, docx_tmp, figures_dir)

    # ── 抽 OLE 公式 LaTeX cache（按出现顺序）──
    # 走 docx2tex (Java XSLT) 主链路：OLE MathType → MathML → LaTeX
    # _FORMULA_STATE 内容用于 _walk_run_chinese 里 OLE→LaTeX 替换（**第二次**调用）
    global _FORMULA_STATE
    _FORMULA_STATE = {"formulas": [], "idx": 0}
    # 统计源 docx 的 <w:object> 数量（用于 cache 覆盖率诊断）
    ole_count_main = _count_ole_objects(docx)
    try:
        from docx_mtef_to_latex import extract_formulas
        cache_dir = structured_dir / "mtef-cache"
        # 新签名：传 docx 文件路径（不是 unzip 后的目录），d2t 内部自己 unzip
        formulas = extract_formulas(docx, cache_dir)
        _FORMULA_STATE["formulas"] = formulas
        cov = (len(formulas) / ole_count_main * 100) if ole_count_main else 0.0
        print(f"[physics_docx_paper] 🧮 MTEF→LaTeX cache: {len(formulas)} 个公式 "
              f"(源 OLE {ole_count_main}, 覆盖率 {cov:.1f}%)",
              flush=True, file=sys.stderr)
        if ole_count_main and len(formulas) < ole_count_main:
            print(f"[physics_docx_paper] ⚠ OLE→LaTeX 不全 ({ole_count_main - len(formulas)} "
                  f"个 OLE 未抓取，将渲染为 [公式])，检查 d2t hub regex / cache 链路",
                  flush=True, file=sys.stderr)
    except Exception as e:
        print(f"[physics_docx_paper] ⚠ MTEF cache 生成失败 ({ole_count_main} 个 OLE 全部 fallback "
              f"到 WMF/PNG/[公式]): {e}",
              flush=True, file=sys.stderr)

    # **第二次 docx → markdown**：这次 _FORMULA_STATE 有内容，OLE 会替换为 $LaTeX$
    md = docx_to_markdown_chinese(docx, docx_tmp, figures_dir)

    # 双文件模式：抽答案 docx 的合成行追加到主 md 末尾
    if ans_only_docx:
        ans_extract = out_dir / "docx-extract-ans"
        # 复用主 figures_dir（避免散落两套图）
        ans_md = docx_to_markdown_chinese(ans_only_docx, ans_extract, figures_dir)
        synth_lines = _extract_answers_from_ans_docx_md(ans_md)
        if synth_lines:
            md = md + "\n\n" + "\n\n".join(synth_lines) + "\n"
            print(f"[physics_docx_paper] 📎 合成 {len(synth_lines)} 行 answer marker "
                  f"追加到主 md", flush=True, file=sys.stderr)

    # 保存 markdown 备查
    (structured_dir / "raw.md").write_text(md, encoding="utf-8")

    # 解析
    result = parse_docx_chinese(md, figures_dir)
    result["slug"] = slug
    result["source"] = "docx"
    result["subject"] = "physics"
    # 卷面元数据（让 enrich 写入 yaml 头部）
    _populate_exam_meta(result, slug, src.stem)

    # **patches 系统**（与 image v3 路线共用 _patches/physics/<slug>.yaml）
    # 用于补 docx 源数据缺陷（如 xicheng Q13 docx 解析版漏 D 选项）
    try:
        import yaml as Y
        patch_path = (Path(__file__).resolve().parent.parent.parent
                      / "knowledge-base" / "exams" / "_patches" / "physics"
                      / f"{slug}.yaml")
        if patch_path.exists():
            patches = Y.safe_load(patch_path.read_text(encoding="utf-8")) or {}
            applied = _apply_patches(patches, result)
            if applied:
                print(f"[physics_docx_paper] 🔧 应用 {applied} 处 patch ({patch_path.name})", flush=True)
    except Exception as e:
        print(f"[physics_docx_paper] ⚠ patch 加载失败: {e}", flush=True)
    fj = structured_dir / "final.json"
    fj.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    qs = result["questions"]
    print(f"[physics_docx_paper] ✅ {fj}", flush=True)
    print(f"   slug: {slug}")
    print(f"   题号: {sorted(q['number'] for q in qs)}")
    print(f"   passages: {len(result['passages'])}  questions: {len(qs)}  "
          f"answers: {len(result['answers'])}  full_score: {result['full_score']}")
    return result


def _apply_patches(patches: dict, result: dict) -> int:
    """对 result（final.json 结构，questions 用 `number` 字段）应用 patches。
    schema 同 image 路线 _patches/physics/*.yaml：
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
            n_applied += 1
            continue
        if target is None: continue
        q = target
        if patch.get("stem") is not None:
            q["stem"] = patch["stem"]; n_applied += 1
        if patch.get("stem_append"):
            q["stem"] = q.get("stem","") + patch["stem_append"]; n_applied += 1
        if "options" in patch:  # 含 null/None：显式清掉 options（如 tongzhou Q22 实验题）
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
    result["duration_minutes"] = 70   # 北京中考物理 70 分钟（chinese 路线遗留默认 150 已修）
    # exam 名称（供 enrich NormalizedPaper.from_final 用）
    result["exam"] = f"{year}年北京{district}中考{exam_type}{result.get('subject','物理')}"


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
