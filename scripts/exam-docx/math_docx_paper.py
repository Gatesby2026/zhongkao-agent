#!/usr/bin/env python3
"""math_docx_paper — Word 数学试卷 → 结构化 final.json（v2 数学路线，含 OLE/marker）。

唯一入口（与 chinese/english/physics/politics_docx_paper.py 命名对齐）：
  python3 scripts/exam-docx/math_docx_paper.py <docx|zip> --subject math [--force]

v2 关键改动（解 R1 二模 audit 3 个 P0）：
  1. **OLE → LaTeX 链路接入**（复用 physics 的 d2t / docx_mtef_to_latex）。
     二模解析版每卷 300-1000 个 OLE 公式不抓全等于内容碎片化。
  2. **【答案】/【解析】/【分析】/【详解】marker 解析**。
     - 题号锚 → mode=question；marker → mode=answer
     - answer 段累积 → flush 时按 N. 拆题归位；选择题答案 [A-D]{1,4} 单独抽
     - 【N题详解】 / 【小问N详解】 / 【详解】 三种 detail block 都收
  3. **考生须知 / 试卷答案 / 第N部分 噪声过滤** + **题号严格递增**
     - 防 yanshan 把 "考生须知 1./2./3./4./5." 当 Q1-Q5
     - 防 fengtai 把答案区 "28．" 当 Q29

依赖（与 physics 同）：
  - docx2tex（D2T_HOME=/tmp/d2t/docx2tex），缺则 OLE→[公式] fallback
  - mathml-to-latex (pip install mathml-to-latex)

流水线：
  1. zip 解压 → 选解析版 docx
  2. 第一次 walk：触发 OLE 占位（占位但 _FORMULA_STATE 空）
  3. d2t 预抽 OLE→LaTeX cache
  4. 第二次 walk：用 cache 替换 OLE 为 $LaTeX$
  5. 状态机切题：question / answer 模式 + marker 触发
  6. 解析答案块 + 详解块 → answer / solution
  7. 写 final.json + yaml（schema 与 v1 一致）
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omml2latex import omml_to_latex, M_NS, W_NS  # noqa: E402

# DrawingML 命名空间（图片）
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V_NS = "urn:schemas-microsoft-com:vml"

NS = {"w": W_NS, "m": M_NS, "a": A_NS, "r": R_NS, "wp": WP_NS, "pic": PIC_NS,
       "v": V_NS}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


# ─── 模块级 OLE 公式 cache state（与 physics 同结构）──────────────────────
# 每次 main() 调用前由 _FORMULA_STATE = {...} 重置；
# _extract_ole_object 每被调用一次 idx+1，按文档出现顺序匹配 d2t 抽出的公式
_FORMULA_STATE: dict = {"formulas": [], "idx": 0}

# ─── R4 修复：rId 对齐的 fallback map（绕过 d2t 静默丢公式的 counter 错位）─
# d2t 在 mid-paper 偶尔静默丢 OLE（haidian -4, xicheng -28, mentougou -12），
# 导致后续所有 OLE 的 idx 错位 → 题干/解题里 `$xOy$` 变 `$k$` / `$b$` 等。
# 启用条件：cache_size < 源 OLE 数 时，预跑 Ruby per-OLE → MathML → LaTeX，
# 按 r:id 直查映射，绝对对齐。
_FORMULA_BY_RID: dict[str, str] = {}


def _ole_obj_rid(obj_el: ET.Element) -> str | None:
    """从 <w:object> 内的 <o:OLEObject> 抽 r:id（指向 oleObjectN.bin）。"""
    for sub in obj_el.iter():
        if _local(sub.tag) == "OLEObject":
            return sub.get(f"{{{R_NS}}}id")
    return None


def _build_formula_by_rid(extract_dir: Path, rels: dict[str, str]) -> dict[str, str]:
    """Ruby per-OLE → MathML → Python mathml-to-latex → {rId: latex} 完整映射。
    用 mtef_extract.rb (mathtype_to_mathml gem)，按 oleObject*.bin 逐个抽。
    失败的 bin 不进 map（_extract_ole_object 会落回 PNG fallback）。
    """
    embed_dir = extract_dir / "word" / "embeddings"
    if not embed_dir.is_dir():
        return {}
    import subprocess, json
    bins = sorted(embed_dir.glob("oleObject*.bin"))
    if not bins:
        return {}
    rb = Path(__file__).resolve().parent / "mtef_extract.rb"
    if not rb.exists():
        print(f"[math_docx_paper] ⚠ mtef_extract.rb 不存在，跳过 rId 对齐", flush=True)
        return {}
    try:
        # mentougou 1196 个 OLE 把 argv 撑爆 → 改 STDIN 一行一文件
        file_list = "\n".join(str(b) for b in bins) + "\n"
        r = subprocess.run(
            ["ruby", str(rb), "-"],
            input=file_list, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(f"[math_docx_paper] ⚠ ruby mtef_extract 失败: {r.stderr[:200]}",
                  flush=True)
            return {}
        rows = json.loads(r.stdout)
    except Exception as e:
        print(f"[math_docx_paper] ⚠ ruby per-OLE 失败 ({e})，跳过 rId 对齐",
              flush=True)
        return {}
    # bin_filename → mathml
    mml_by_bin: dict[str, str] = {}
    for row in rows:
        if "mathml" in row:
            mml_by_bin[row["file"]] = row["mathml"]
    # bin_filename → latex
    try:
        from docx_mtef_to_latex import _mathml_to_latex_block
    except Exception as e:
        print(f"[math_docx_paper] ⚠ 导入 _mathml_to_latex_block 失败: {e}",
              flush=True)
        return {}
    latex_by_bin: dict[str, str] = {}
    for fn, mml in mml_by_bin.items():
        try:
            latex_by_bin[fn] = _mathml_to_latex_block(mml)
        except Exception:
            pass
    # rels: rId → "embeddings/oleObjectN.bin"（也可能 ../embeddings/...）
    rid_to_latex: dict[str, str] = {}
    for rid, target in rels.items():
        bin_name = Path(target).name  # 抓尾文件名
        if bin_name in latex_by_bin:
            rid_to_latex[rid] = latex_by_bin[bin_name]
    return rid_to_latex


def _extract_ole_object(obj_el: ET.Element, rels: dict[str, str],
                          extract_dir: Path, figures_dir: Path,
                          formula_state: dict | None = None) -> str:
    """OLE 嵌入对象（MathType 公式）。四层 fallback：
      0. **R4 对齐 fallback**：_FORMULA_BY_RID[rId]（cache 短于 OLE 时启用）
      1. **默认**：docx2tex 预跑的 LaTeX cache（formula_state["formulas"]）→ $LaTeX$
      2. PNG 兄弟（soffice 转的）→ ![](figures/xxx.png)
      3. WMF 没转 → [公式] 占位
    """
    # 路线 0: rId 直查（R4 — d2t 漏 OLE 时绝对对齐）
    if _FORMULA_BY_RID:
        rid = _ole_obj_rid(obj_el)
        if rid and rid in _FORMULA_BY_RID:
            latex = _FORMULA_BY_RID[rid]
            # 仍然推进 d2t cache idx（保持后续 OLE 走 d2t 路径时一致）
            if formula_state is not None and formula_state.get("formulas"):
                formula_state["idx"] = formula_state.get("idx", 0) + 1
            return f"${latex}$"

    # 路线 1: docx2tex LaTeX cache（按出现顺序匹配）
    if formula_state is not None and formula_state.get("formulas"):
        idx = formula_state["idx"]
        formulas = formula_state["formulas"]
        if idx < len(formulas):
            latex = formulas[idx]
            formula_state["idx"] = idx + 1
            return f"${latex}$"
        # cache 不够长，落回路线 2/3

    # 路线 2/3: WMF/PNG fallback
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
        if out.suffix.lower() in (".wmf", ".emf"):
            png_sibling = out.with_suffix(".png")
            if png_sibling.exists():
                return f"![](figures/{png_sibling.name})"
            return "[公式]"
        return f"![](figures/{out.name})"
    return ""


# ─── docx 结构解析 ──────────────────────────────────────────────────────────

def _load_docx(docx_path: Path, extract_dir: Path) -> tuple[ET.Element, dict[str, str]]:
    """解压 docx，返回 (document.xml root, rels: {rId: media_path})。"""
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path) as z:
        z.extractall(extract_dir)
    doc_xml = (extract_dir / "word" / "document.xml").read_text(encoding="utf-8")
    root = ET.fromstring(doc_xml)
    rels_path = extract_dir / "word" / "_rels" / "document.xml.rels"
    rels: dict[str, str] = {}
    if rels_path.exists():
        rels_root = ET.fromstring(rels_path.read_text(encoding="utf-8"))
        for r in rels_root:
            if _local(r.tag) == "Relationship":
                rid = r.get("Id"); target = r.get("Target", "")
                rels[rid] = target
    return root, rels


def _walk_paragraph(p: ET.Element, rels: dict[str, str],
                    extract_dir: Path, figures_dir: Path) -> str:
    """结构化遍历段落子节点：保持顺序，每类节点产出对应 markdown 片段。"""
    out: list[str] = []
    for child in p:
        tag = _local(child.tag)
        if tag == "r" and child.tag.startswith(f"{{{W_NS}}}"):
            out.append(_walk_run(child, rels, extract_dir, figures_dir))
        elif tag == "oMath" and child.tag.startswith(f"{{{M_NS}}}"):
            out.append(omml_to_latex(child))
        elif tag == "oMathPara" and child.tag.startswith(f"{{{M_NS}}}"):
            for om in child.findall(f"{{{M_NS}}}oMath"):
                out.append(omml_to_latex(om, inline=False))
        elif tag in ("hyperlink",):
            out.append(_walk_paragraph(child, rels, extract_dir, figures_dir))
    text = "".join(out).strip()
    # **源数据 sanitize**：出题人误输的 "▱△ABCD"（chaoyang Q20）
    text = re.sub(r"▱△", "▱", text)
    # **合并相邻同 vertAlign 下/上标**
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"_\{([^{}]+)\}_\{([^{}]+)\}", r"_{\1\2}", text)
        text = re.sub(r"\^\{([^{}]+)\}\^\{([^{}]+)\}", r"^{\1\2}", text)
    return text


def _walk_run(r: ET.Element, rels: dict[str, str],
              extract_dir: Path, figures_dir: Path) -> str:
    """w:r 内可能含 w:t 文字 / w:drawing 图片 / m:oMath OMML / w:object OLE。
    按顺序拼并处理 vertAlign 上下标。
    """
    # 先扫 rPr 探测上下标
    vert_align = None
    for child in r:
        if _local(child.tag) == "rPr":
            for sub in child:
                if _local(sub.tag) == "vertAlign":
                    val = sub.get(f"{{{W_NS}}}val") or sub.get("val")
                    if val in ("superscript", "subscript"):
                        vert_align = val
            break

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
        elif tag == "drawing":
            img = _extract_image(child, rels, extract_dir, figures_dir)
            if img:
                out.append(img)
        elif tag == "pict":
            img = _extract_image(child, rels, extract_dir, figures_dir)
            if img:
                out.append(img)
        elif tag == "oMath" and ns == f"{{{M_NS}":
            out.append(omml_to_latex(child))
        elif tag == "object":
            # OLE MathType 公式：优先用 docx2tex LaTeX cache（_FORMULA_STATE）
            img = _extract_ole_object(child, rels, extract_dir, figures_dir,
                                       formula_state=_FORMULA_STATE)
            if img:
                out.append(img)
    text = "".join(out)
    if vert_align and text.strip():
        sep = "^" if vert_align == "superscript" else "_"
        text = f"{sep}{{{text}}}"
    return text


def _extract_image(drawing_el: ET.Element, rels: dict[str, str],
                    extract_dir: Path, figures_dir: Path) -> str:
    """从 w:drawing/w:pict 节点提取图片：拷贝到 figures_dir，返回 markdown 占位。"""
    for blip in drawing_el.iter(f"{{{A_NS}}}blip"):
        rid = blip.get(f"{{{R_NS}}}embed") or blip.get(f"{{{R_NS}}}link")
        if not rid: continue
        target = rels.get(rid)
        if not target: continue
        src = extract_dir / "word" / target
        if not src.exists():
            src = extract_dir / target.lstrip("/.")
        if not src.exists():
            src = extract_dir / re.sub(r"^(\.\./)+", "", target)
        if not src.exists():
            print(f"  ⚠ 图片找不到: {target}", file=sys.stderr)
            continue
        figures_dir.mkdir(parents=True, exist_ok=True)
        out = figures_dir / src.name
        if not out.exists():
            shutil.copy(src, out)
        if out.suffix.lower() in (".wmf", ".emf"):
            png_sibling = out.with_suffix(".png")
            if png_sibling.exists():
                return f"![](figures/{png_sibling.name})"
        return f"![](figures/{src.name})"
    # OLE 内嵌图（v:imagedata）兜底
    for vd in drawing_el.iter(f"{{{V_NS}}}imagedata"):
        rid = vd.get(f"{{{R_NS}}}id") or vd.get(f"{{{R_NS}}}href")
        if not rid: continue
        target = rels.get(rid)
        if not target: continue
        src = extract_dir / "word" / target
        if not src.exists():
            src = extract_dir / target.lstrip("/.")
        if not src.exists():
            continue
        out = figures_dir / src.name
        if not out.exists():
            figures_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, out)
        if out.suffix.lower() in (".wmf", ".emf"):
            png_sibling = out.with_suffix(".png")
            if png_sibling.exists():
                return f"![](figures/{png_sibling.name})"
        return f"![](figures/{src.name})"
    return ""


def docx_to_markdown(docx_path: Path, extract_dir: Path,
                     figures_dir: Path) -> tuple[str, dict]:
    """主转换：docx → markdown 字符串 + 统计信息。"""
    root, rels = _load_docx(docx_path, extract_dir)
    total_omath = len(list(root.iter(f"{{{M_NS}}}oMath")))
    total_blips = len(list(root.iter(f"{{{A_NS}}}blip")))
    # OLE objects 数（用于 sanity check：d2t 抽到的公式数应 ≈ ole 数）
    total_ole = sum(
        1 for o in root.iter()
        if _local(o.tag) == "object" and o.tag.startswith(f"{{{W_NS}}}")
    )

    body = root.find(f"{{{W_NS}}}body")
    if body is None:
        return "", {"omath": 0, "blips": 0, "ole": 0, "paragraphs": 0}
    md_lines: list[str] = []
    for child in body:
        tag = _local(child.tag)
        if tag == "p":
            line = _walk_paragraph(child, rels, extract_dir, figures_dir)
            if line.strip():
                md_lines.append(line)
        elif tag == "tbl":
            tbl_md = _walk_table(child, rels, extract_dir, figures_dir)
            if tbl_md:
                md_lines.append(tbl_md)
    md = "\n\n".join(md_lines)

    n_dollars = md.count("$")
    n_inline = len(re.findall(r"\$[^$]+\$", md))
    n_display = len(re.findall(r"\$\$[^$]+\$\$", md))
    n_img_md = len(re.findall(r"!\[\]\(figures/", md))

    return md, {
        "omath_source": total_omath,
        "blips_source": total_blips,
        "ole_source": total_ole,
        "dollars_md": n_dollars,
        "inline_eq_md": n_inline,
        "display_eq_md": n_display,
        "img_refs_md": n_img_md,
        "paragraphs": len(md_lines),
    }


def _walk_table(tbl: ET.Element, rels: dict[str, str],
                 extract_dir: Path, figures_dir: Path) -> str:
    """表格转 markdown 表格。"""
    rows = []
    for tr in tbl.findall(f"{{{W_NS}}}tr"):
        cells = []
        for tc in tr.findall(f"{{{W_NS}}}tc"):
            cell = " ".join(_walk_paragraph(p, rels, extract_dir, figures_dir)
                            for p in tc.findall(f"{{{W_NS}}}p"))
            cells.append(cell.strip())
        rows.append("| " + " | ".join(cells) + " |")
    if not rows:
        return ""
    n_cols = max(r.count("|") - 1 for r in rows) if rows else 0
    sep = "|" + "|".join(["---"] * n_cols) + "|"
    return rows[0] + "\n" + sep + "\n" + "\n".join(rows[1:])


# ─── 切题（v2：带 marker 状态机）─────────────────────────────────────────

NUM_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.*)$")
# 答案/解析/详解 marker（用于 mode 切换）
ANSWER_MARKER_RE = re.compile(r"^\s*【答案】")
ANALYSIS_MARKER_RE = re.compile(r"^\s*【解析】")
ANALYZE_MARKER_RE = re.compile(r"^\s*【分析】")
DETAIL_MARKER_RE = re.compile(r"^\s*【详解】")
DETAIL_TITLE_RE = re.compile(r"^\s*【(\d{1,2})题详解】")
SUB_DETAIL_RE = re.compile(r"^\s*【小问(\d+)详解】")
POINT_MARKER_RE = re.compile(r"^\s*【点睛】")
# 答案页 marker（独立标题行）
ANSWER_PAGE_RE = re.compile(
    r"^\s*(?:参考答案|答案及评分|评分标准|答案与解析|参考答案与试题解析"
    r"|参考答案及评分标准|试卷答案|试题答案|数学参考答案"
    r"|数学试卷答案)"
)
def _is_answer_page_title(line: str) -> bool:
    return bool(ANSWER_PAGE_RE.match(line)) and len(line.strip()) <= 30
# 噪声 / 卷面分段（要么丢，要么截断后续）
# yanshan 须知 1./2./3./4./5. 5 行符合 \d+\. 题头被误识为 Q1-Q5；
# 必须在到达 "一、选择题" 之前抑制
NOISE_LINE_RE = re.compile(
    r"^\s*(?:"
    r"\d{4}年[^\n]*?(?:试卷|试题)\s*$"
    r"|声明[:：][^\n]*?著作权"
    r"|试题解析著作权"
    r"|发布日期[:：]"
    r"|用户[:：][^\n]*?(?:邮箱|学号)"
    r"|菁优网"
    r"|第[一二三四五六]部分(?:\s|$)"
    r")"
)
# 考生须知 / 注意事项 等 anchor，触发"未进入题目正文"
PROLOGUE_ANCHOR_RE = re.compile(
    r"^\s*(?:考\s*生\s*须\s*知|注意事项|答题须知)"
)
# 进入正文的 anchor：第一/二/三部分 + 大题 header（一、二、三…）
SECTION_HEAD_RE = re.compile(
    r"^\s*[一二三四五六七八九十]+\s*[、，.]\s*"
    r"(?:选择题?|填空题?|解答题?|计算题?|证明题?|应用题?)"
)
# 题首 `（N分）` 分值标识
STEM_SCORE_RE = re.compile(r"^\s*[（(]\s*(\d+)\s*分\s*[)）]\s*")
# 选项匹配
OPT_SPLIT_RE = re.compile(r"(?:\(([A-D])\)|([A-D])\s*[.、．])\s*")


def _extract_options(text: str) -> tuple[str, dict[str, str]]:
    """从一段（可能跨行）文本里抽 A/B/C/D 选项。"""
    matches = list(OPT_SPLIT_RE.finditer(text))
    if len(matches) < 4:
        return text, {}
    labels = [m.group(1) or m.group(2) for m in matches]
    n = len(matches)
    start_idx = None
    for i in range(n - 3):
        if [labels[i], labels[i+1], labels[i+2], labels[i+3]] == ["A", "B", "C", "D"]:
            start_idx = i
    if start_idx is None:
        return text, {}
    stem_clean = text[:matches[start_idx].start()].rstrip(" \n　")
    opts: dict[str, str] = {}
    for k in range(4):
        m_cur = matches[start_idx + k]
        m_nxt = matches[start_idx + k + 1] if start_idx + k + 1 < n else None
        end = m_nxt.start() if m_nxt else len(text)
        label = m_cur.group(1) or m_cur.group(2)
        opts[label] = text[m_cur.end():end].strip(" \n　．.")
    return stem_clean, opts


def split_by_questions(md: str) -> tuple[list[dict], list[dict]]:
    """状态机切题：返回 (questions, answers)。

    状态机：
      - prologue：在 SECTION_HEAD（"一、选择题"）出现前，**完全不收题**
      - question：累积当前题 stem，遇 marker 进 answer，遇下一题号 flush
      - answer：累积当前题 answer/solution，遇下一题号回 question
      - 见 ANSWER_PAGE（"参考答案"独立行）+ stem 已收满 → 进 answer_page
        模式（不再创建新 question，仅累积答案文本）

    每题 cur 结构：
      {number, stem, options, figures, answer, solution_buf}
    """
    questions: list[dict] = []
    answers: list[dict] = []  # answers 与 questions 同号对齐，flush 时一起写

    cur: dict | None = None
    in_prologue = True           # 默认在 prologue（考生须知/封面）
    mode = "stem"                 # stem | answer
    in_answer_page = False        # 见过"参考答案"标题后，不再 create 新题
    last_q_seen = 0
    # 答案页内容缓冲（fengtai 评分参考模板：选择题表 + "9．X 10．Y ..." 一行多题 + "N．解：...N 分"）
    # 见 _is_answer_page_title 触发后所有行进这里，主管道不创建 Q29 phantom；
    # 末尾由 _parse_answer_page_block 抽答案合并回 answers
    answer_page_buf: list[str] = []

    def _flush():
        """把 cur 落到 questions + answers。"""
        if not cur or not cur.get("number"):
            return
        stem_full = cur["stem"].strip()
        # answer/solution 已剥离，stem 仅剩题面 + 选项
        stem_clean, opts = _extract_options(stem_full)
        questions.append({
            "number": cur["number"],
            "stem": stem_clean,
            "options": opts if opts else None,
            "figures": cur["figures"],
        })
        # 答案归位
        ans = cur.get("answer", "").strip()
        sol = "\n".join(s for s in cur.get("solution_buf", []) if s.strip()).strip()
        # 清理 sol 中残留的 marker
        sol = re.sub(r"【小问\d+详解】", "", sol)
        sol = re.sub(r"【\d{1,2}题详解】", "", sol)
        sol = re.sub(r"^【(?:解析|分析|详解|点睛)】\s*", "", sol)
        sol = sol.strip()
        # 选择题答案：从 ans 抽 [A-D]+；解答题答案常为空（落在 sol 里）
        correct = ans
        m_letter = re.match(r"^([A-D]{1,4})\s*(?:[．.、，,；;]|$)", ans)
        if m_letter:
            correct = m_letter.group(1)
        elif re.fullmatch(r"[A-D]{1,4}\s*", ans):
            correct = ans.strip()
        answers.append({
            "number": cur["number"],
            "correct": correct,
            "solution": sol or ans,  # 解答题：详解 fallback 到 answer 文本
        })

    for line in md.split("\n"):
        if not line.strip():
            continue
        # ─── 1. prologue（封面/考生须知）：直到见 SECTION_HEAD 才进 question 模式
        if in_prologue:
            if SECTION_HEAD_RE.match(line):
                in_prologue = False
            # 否则一概丢弃（包括 考生须知 5 条 1./2./3./4./5.）
            continue

        # ─── 2. 噪声 + 段标 ────────────────────────────────────────
        if NOISE_LINE_RE.search(line):
            continue
        # 段标（"一、选择题"）：flush + reset，不当题
        if SECTION_HEAD_RE.match(line):
            if cur and cur.get("number"): _flush()
            cur = None; mode = "stem"
            continue

        # ─── 3. 答案页 marker（独立行）→ 截断后续，进 answer_page 模式
        if not in_answer_page and _is_answer_page_title(line):
            if cur and cur.get("number"): _flush()
            cur = None; mode = "stem"
            in_answer_page = True
            continue

        # ─── 4. 答案页模式：累积到 answer_page_buf，主管道不创建新题
        #     fengtai/chaoyang/pinggu「评分参考」模板：
        #       - "| 题号 | 1..8 | / | 答案 | A..X |" 选择题横表
        #       - "9．X     10．Y    11．Z..." 一行多题填空
        #       - "N．解：...N 分..." 主观题逐题
        #     主管道 drop 行避免 28． 被当 Q29，末尾走 _parse_answer_page_block
        if in_answer_page:
            answer_page_buf.append(line)
            continue

        # ─── 5. marker 触发 mode 切换 ─────────────────────────────
        if cur is not None:
            # 【答案】 marker
            m_ans = ANSWER_MARKER_RE.match(line)
            if m_ans:
                mode = "answer"
                after = re.sub(r"^\s*【答案】\s*", "", line)
                if after.strip():
                    cur["answer"] = (cur.get("answer", "") + after).strip()
                continue
            # 【解析】/【分析】 marker：进 solution buf
            if ANALYSIS_MARKER_RE.match(line) or ANALYZE_MARKER_RE.match(line):
                mode = "solution"
                after = re.sub(r"^\s*【(?:解析|分析)】\s*", "", line)
                if after.strip():
                    cur["solution_buf"].append(after)
                continue
            # 【详解】 / 【N题详解】 / 【小问N详解】 → solution
            m_dt = DETAIL_TITLE_RE.match(line)
            if m_dt:
                mode = "solution"
                after = line[m_dt.end():].strip()
                # 标记子问号（如 Q17 内 【17题详解】→视为 sub_n=1）
                if after:
                    cur["solution_buf"].append(after)
                continue
            m_sd = SUB_DETAIL_RE.match(line)
            if m_sd:
                mode = "solution"
                after = line[m_sd.end():].strip()
                cur["solution_buf"].append(f"（{m_sd.group(1)}）{after}".rstrip())
                continue
            if DETAIL_MARKER_RE.match(line):
                mode = "solution"
                after = re.sub(r"^\s*【详解】\s*", "", line)
                if after.strip():
                    cur["solution_buf"].append(after)
                continue
            if POINT_MARKER_RE.match(line):
                # 【点睛】 通常是知识点总结，跟在详解后；并入 solution
                mode = "solution"
                after = re.sub(r"^\s*【点睛】\s*", "", line)
                if after.strip():
                    cur["solution_buf"].append(after)
                continue

        # ─── 6. 题号锚 ────────────────────────────────────────────
        m = NUM_HEAD_RE.match(line)
        if m and 1 <= int(m.group(1)) <= 30:
            n = int(m.group(1))
            # **题号严格递增 + 容忍 +0 重复**（防 chaoyang Q23 表格数据
            # 误识、防 fengtai 答案区 28．重复识别）
            if n > last_q_seen or n == last_q_seen + 0:
                # 实际只接受 n == last_q_seen + 1（严格递增 1）
                # 但允许 last_q_seen = 0 时任何起始（第一题）
                if last_q_seen == 0 or n == last_q_seen + 1:
                    if cur and cur.get("number"): _flush()
                    cur = {
                        "number": n,
                        "stem": m.group(2).strip(),
                        "options": {},
                        "figures": [],
                        "answer": "",
                        "solution_buf": [],
                    }
                    mode = "stem"
                    last_q_seen = n
                    continue
            # 题号倒退/跳号 → 不是真题号，当正文累积
        # ─── 7. 累积到当前 cur 的对应 buf ─────────────────────────
        if cur is None:
            continue
        for img_m in re.finditer(r"!\[\]\(figures/([^)]+)\)", line):
            cur["figures"].append(img_m.group(1))
        if mode == "stem":
            cur["stem"] += "\n" + line
        elif mode == "answer":
            # answer mode：单字母 / 数字 / 取值范围；通常 1-2 行
            cur["answer"] = (cur.get("answer", "") + " " + line).strip()
        elif mode == "solution":
            cur["solution_buf"].append(line)

    # 最后 flush
    if cur and cur.get("number"):
        _flush()

    # 答案页缓冲解析：把 in_answer_page 期间累积的内容拆成 per-Q answer/sol，
    # 合并回 answers（仅补已存在的题，不创建新题号 → 不会引入 Q29 phantom）
    if answer_page_buf:
        ap_map = _parse_answer_page_block(answer_page_buf)
        existing_qnums = {a["number"] for a in answers}
        for n, info in ap_map.items():
            if n not in existing_qnums:
                continue  # 只补已存在题；防 Q29 phantom
            # 找对应 answer entry
            for a in answers:
                if a["number"] != n: continue
                # correct 字段：只补缺
                if not a.get("correct") and info.get("correct"):
                    a["correct"] = info["correct"]
                # solution 字段：只补缺（已有则保留主管道版本）
                if (not a.get("solution") or a.get("solution") == a.get("correct")) \
                   and info.get("solution"):
                    a["solution"] = info["solution"]
                break

    return questions, answers


# ─── 答案页解析 (评分参考模板：fengtai/chaoyang/pinggu) ───────────────────

_AP_CHOICE_HDR_RE = re.compile(r"^\|\s*题号\s*\|")
_AP_CHOICE_ANS_RE = re.compile(r"^\|\s*答案\s*\|")
# 一行多题填空：N．content    N+1．content    ...
# 分隔符：(a) 4+ 空格 (fengtai)；(b) "；" 后零或多空格 (pinggu)；(c) Unicode 全角空格
# 用 lookahead 切：找下个 "<sep>(?=\d{1,2}[.、．])" 作分隔
_AP_MULTI_FILL_SPLIT_RE = re.compile(
    r"(?:\s{2,}|[；;]\s*)(?=\d{1,2}\s*[.、．])")
_AP_Q_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.+)$")
# "X 分" 评分点（行尾出现，可重复多个；区分末尾标记 vs 数学公式里的中文"分"）
# 评分点常以 4+ 空格 + 数字 + 分 + 行尾 形式出现
_AP_SCORE_TAIL_RE = re.compile(r"\s{2,}(\d+)\s*分[,，。.]?\s*$")


def _parse_answer_page_block(lines: list[str]) -> dict[int, dict]:
    """从答案页缓冲行抽 {N: {correct, solution}}。

    覆盖三种格式：
      (a) 选择题横表 `| 题号 | 1..N | / | 答案 | A..X |` → correct
      (b) 一行多题填空 "9．X     10．Y    11．>    12．3" → correct/solution
      (c) "N．解：...    N 分..." 主观题 → solution（末尾 [A-D]+ / 数字 → correct）
    """
    out: dict[int, dict] = {}
    # subjective buffer：cur_q → list[str]
    cur_q: int | None = None
    subj_buf: dict[int, list[str]] = {}

    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            i += 1; continue
        # (a) 横表答案：`| 题号 | N1..Nk |` + `| 答案 | A1..Ak |`
        # 选择题（A-D 单/多字母）+ 填空题（公式/数字/区间，朝阳/平谷格式）
        if _AP_CHOICE_HDR_RE.match(ln):
            nums = [c.strip() for c in ln.strip("|").split("|") if c.strip()][1:]
            for j in range(i+1, min(i+5, len(lines))):
                ln2 = lines[j].strip()
                if _AP_CHOICE_ANS_RE.match(ln2):
                    ans_cells = [c.strip() for c in ln2.strip("|").split("|")
                                 if c.strip()][1:]
                    for k, n_str in enumerate(nums):
                        if k < len(ans_cells) and n_str.isdigit():
                            n = int(n_str)
                            ans = ans_cells[k]
                            if not ans: continue
                            entry = out.setdefault(n, {})
                            if re.fullmatch(r"[A-D]{1,4}", ans):
                                # 选择题
                                entry["correct"] = ans
                            else:
                                # 填空题（公式/数字/区间）→ correct + solution
                                entry["correct"] = ans
                                entry["solution"] = ans
                    i = j + 1
                    break
            else:
                i += 1
            cur_q = None
            continue
        # 段标 / section header / "答案" 单字  → 不进 cur_q buf
        if SECTION_HEAD_RE.match(ln) or ln in ("答案", "题号"):
            cur_q = None
            i += 1; continue
        # (b) 一行多题填空：含 2+ 个 "N．" 锚（用 4+ 空格切）
        # 朝阳/丰台/平谷：填空区一行写 4 道
        parts = _AP_MULTI_FILL_SPLIT_RE.split(ln)
        if len(parts) >= 2:
            # 验证每段都以 "N．" 开头
            heads = [_AP_Q_HEAD_RE.match(p) for p in parts]
            if all(h for h in heads):
                for h in heads:
                    n = int(h.group(1))
                    body = h.group(2).strip()
                    # 去尾部分值 "（N分）"
                    body = re.sub(r"[（\(]\s*\d+\s*分\s*[）\)]\s*$", "", body).strip()
                    # 去尾标点 "；" / ";" / "．" / "." (一行多题填空末项)
                    body = re.sub(r"[；;．.]+\s*$", "", body).strip()
                    if not body: continue
                    entry = out.setdefault(n, {})
                    m_letter = re.match(r"^([A-D]{1,4})$", body)
                    if m_letter:
                        entry["correct"] = m_letter.group(1)
                    else:
                        # 填空答案：当作 correct（短）+ solution（同）
                        entry["correct"] = body
                        entry["solution"] = body
                cur_q = None
                i += 1; continue
        # (c) 主观题题号锚 "N．解：..." → 进 cur_q buf
        m = _AP_Q_HEAD_RE.match(ln)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 30:
                cur_q = n
                subj_buf.setdefault(n, []).append(m.group(2).strip())
                i += 1; continue
        # 续行：归 cur_q buf（仅主观题）
        if cur_q is not None:
            subj_buf[cur_q].append(ln)
        i += 1

    # subj_buf → solution（先把"X 分"评分点压扁，保留正文）
    for n, buf in subj_buf.items():
        text_lines = []
        for l in buf:
            # 行尾 "  N 分" 评分点去掉但保正文
            cleaned = _AP_SCORE_TAIL_RE.sub("", l).rstrip()
            if cleaned:
                text_lines.append(cleaned)
        if not text_lines: continue
        sol = "\n".join(text_lines).strip()
        if not sol: continue
        entry = out.setdefault(n, {})
        entry["solution"] = sol
        # 末尾若是单字母 [A-D]+ → 也补到 correct（罕见）
        last = text_lines[-1].strip()
        m_letter = re.fullmatch(r"[A-D]{1,4}", last)
        if m_letter and not entry.get("correct"):
            entry["correct"] = last
    return out


# ─── 类型推断 ─────────────────────────────────────────────────────────────

def _infer_type(num: int, options: dict | None) -> str:
    """北京中考数学：1-8 单选，9-16 填空，17-28 解答。"""
    if num <= 8 and options:
        return "choice"
    if 1 <= num <= 8:
        return "choice"
    if 9 <= num <= 16:
        return "fill_blank"
    return "problem_solving"


def _default_score(num: int) -> int:
    """北京中考数学默认分值（兜底）。28 题/100 分梯度。"""
    if 1 <= num <= 16:  return 2
    if 17 <= num <= 19: return 5
    if num == 20:       return 6
    if 21 <= num <= 22: return 5
    if 23 <= num <= 24: return 6
    if num == 25:       return 5
    if num == 26:       return 6
    if 27 <= num <= 28: return 7
    return 5


# ─── 校验器 ─────────────────────────────────────────────────────────────

def validate(stats: dict, questions: list[dict], answers: list[dict],
              figures_dir: Path) -> dict:
    """公式/图/结构 + answer 完整性 校验。"""
    issues = {"errors": [], "warnings": []}
    eq_md_total = stats["inline_eq_md"] + stats["display_eq_md"]
    if eq_md_total != stats.get("omath_source", 0) + stats.get("ole_source", 0):
        issues["warnings"].append(
            f"公式计数不一致: OMML+OLE 源 "
            f"{stats.get('omath_source', 0) + stats.get('ole_source', 0)} ≠ "
            f"markdown $ {eq_md_total}"
        )
    nums = sorted(q["number"] for q in questions)
    if nums:
        gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
        if gaps:
            issues["errors"].append(f"题号断号: {gaps}")
    for q in questions:
        n = q["number"]; t = _infer_type(n, q.get("options"))
        if t == "choice":
            opts = q.get("options") or {}
            if set(opts) != {"A", "B", "C", "D"}:
                issues["errors"].append(
                    f"Q{n} 选择题 options 不全: {sorted(opts.keys())}"
                )
    for q in questions:
        n = q["number"]
        stem = q.get("stem") or ""
        refs = set(re.findall(r"图\s*(\d+)", stem) + re.findall(r"如图\s*(\d+)", stem))
        if refs and not q.get("figures"):
            issues["errors"].append(f"Q{n} 题干引图 {sorted(refs)} 但无 figure")
    used = set()
    for q in questions: used |= set(q.get("figures") or [])
    for a in answers:
        used |= set(re.findall(r"figures/([^)\s]+)", a.get("solution") or ""))
    if figures_dir.is_dir():
        all_pngs = {p.name for p in figures_dir.glob("*.png")}
        orphan = all_pngs - used
        if orphan:
            issues["warnings"].append(
                f"figures/ 下未引用图 {len(orphan)} 张: {sorted(orphan)[:5]}...")
    # answer 覆盖率
    empty_ans = sum(1 for a in answers if not a.get("correct") and not a.get("solution"))
    if questions and empty_ans / len(questions) > 0.5:
        issues["errors"].append(
            f"answer/solution 全空率 {empty_ans}/{len(questions)} >50%"
        )
    return issues


# ─── 选 docx（解析版优先）─────────────────────────────────────────────────

def _pick_jiexi_docx(docx_paths: list[Path]) -> Path:
    """选 docx 优先级：解析版 > 试卷版 > 最大文件。"""
    for p in docx_paths:
        if "解析" in p.stem and "原卷" not in p.stem:
            return p
    for p in docx_paths:
        if "试卷" in p.stem and "答案" not in p.stem:
            return p
    if docx_paths:
        return max(docx_paths, key=lambda d: d.stat().st_size)
    raise FileNotFoundError("未找到 docx")


def _pick_answer_only_docx(docx_paths: list[Path], jiexi: Path) -> Path | None:
    """挑独立答案 docx（试卷+答案双文件格式专用）。
    判定：jiexi 不是「解析」版（即只是试卷） + 存在含「答案」字样的兄弟 docx。
    返回 None 时不进入双文件 merge 流程（视作单 docx）。

    样例：
      - chaoyang: 【试卷】xxx.docx + 【答案】xxx.docx
      - pinggu:  【试卷】xxx.docx + 【答案】xxx.docx
    """
    if "解析" in jiexi.stem and "原卷" not in jiexi.stem:
        return None  # 主文档是精品解析版，已含答案
    for p in docx_paths:
        if p == jiexi: continue
        if "答案" in p.stem:
            return p
    return None


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


# ─── 入口 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="docx 或 zip")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="staging 目录；缺省按 derive 规则推导")
    ap.add_argument("--subject", default="math")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    src = a.src.resolve()
    if not src.exists():
        sys.exit(f"src 不存在: {src}")

    # 先推导 out_dir，再决定从哪选 docx
    if a.out_dir:
        out_dir = a.out_dir.resolve()
    else:
        # 用 src 名解析 slug
        name = src.stem
        m_year = re.search(r"(\d{4})", name)
        # 优先匹配明确 "X区" 名（防 "九年级"/"教育集团" 等混入）
        m_region = re.search(r"北京市?([一-龥]+?)(?:区|教育集团)", name)
        year = m_year.group(1) if m_year else "0000"
        region = m_region.group(1) if m_region else "unknown"
        type_cn = next((t for t in ("一模", "二模", "三模", "期中", "期末", "真题")
                        if t in name), "一模")
        # zxxk 二模合订文件常没"二模"字样而带"统一测试（二）"或"期末练习"
        if type_cn == "一模":
            if "（二）" in name or "(二)" in name or "测试二" in name:
                type_cn = "二模"
            elif "期末练习" in name and "二模" not in name:
                # 海淀风格："期末练习" 但实际是二模 - 由调用方走 zip 路径名识别
                pass
        type_map = {"一模": "yi", "二模": "er", "三模": "san",
                    "真题": "zhen", "期中": "qz", "期末": "qm"}
        typ = type_map.get(type_cn, type_cn)
        region_slug = {"朝阳": "chaoyang", "海淀": "haidian", "门头沟": "mentougou",
                       "丰台": "fengtai", "西城": "xicheng", "东城": "dongcheng",
                       "石景山": "shijingshan", "通州": "tongzhou", "顺义": "shunyi",
                       "昌平": "changping", "大兴": "daxing", "房山": "fangshan",
                       "平谷": "pinggu", "怀柔": "huairou", "密云": "miyun",
                       "延庆": "yanqing", "燕山": "yanshan"}.get(region, region)
        slug = f"{year}-{region_slug}-{typ}"
        cur = src.parent
        while cur.parent != cur:
            if (cur / "knowledge-base").is_dir():
                out_dir = (cur / "knowledge-base" / "exams" / "_staging"
                           / a.subject / slug)
                break
            cur = cur.parent
        else:
            sys.exit("无法定位 repo_root（找不到 knowledge-base/ ）")

    print(f"[math_docx_paper] {src.name} → {out_dir}", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = out_dir / "docx-extracted"
    figures_dir = out_dir / "figures"
    structured = out_dir / "structured-cloud"
    structured.mkdir(parents=True, exist_ok=True)

    if a.force:
        for p in (extract_dir, figures_dir):
            if p.is_dir(): shutil.rmtree(p)

    # ── 确定要解析的 docx：若 src 是 zip 先 unzip 选解析版 ──
    ans_only_docx: Path | None = None
    if src.suffix.lower() == ".zip":
        unzip_dir = out_dir / "src-unzip"
        docx_paths = _unzip_to(src, unzip_dir)
        docx = _pick_jiexi_docx(docx_paths)
        ans_only_docx = _pick_answer_only_docx(docx_paths, docx)
    elif src.suffix.lower() == ".docx":
        docx = src
    else:
        sys.exit(f"不支持的输入: {src}")
    print(f"[math_docx_paper] 用 docx: {docx.name}", flush=True)
    if ans_only_docx:
        print(f"[math_docx_paper] 📎 双文件模式，附加答案 docx: {ans_only_docx.name}",
              flush=True)

    # ── 第 1 遍 walk：占位 OLE（_FORMULA_STATE 空 → fallback 到 WMF/PNG/[公式]）
    global _FORMULA_STATE
    _FORMULA_STATE = {"formulas": [], "idx": 0}
    md, stats = docx_to_markdown(docx, extract_dir, figures_dir)

    # ── 预抽 OLE → LaTeX cache ──
    try:
        from docx_mtef_to_latex import extract_formulas
        cache_dir = structured / "mtef-cache"
        formulas = extract_formulas(docx, cache_dir)
        _FORMULA_STATE = {"formulas": formulas, "idx": 0}
        print(f"[math_docx_paper] 🧮 MTEF→LaTeX cache: {len(formulas)} 个公式 "
              f"(源 OLE={stats.get('ole_source', 0)})", flush=True)
    except Exception as e:
        print(f"[math_docx_paper] ⚠ MTEF cache 生成失败，OLE 走 WMF/PNG fallback: {e}",
              flush=True)
        _FORMULA_STATE = {"formulas": [], "idx": 0}

    # ── R4 修复：d2t cache 比源 OLE 短 → 启 Ruby per-OLE rId 对齐 fallback ──
    # haidian/xicheng/mentougou 跨区共性：d2t 静默丢 OLE 致 counter 错位
    global _FORMULA_BY_RID
    _FORMULA_BY_RID = {}
    ole_src = stats.get("ole_source", 0)
    if ole_src and len(_FORMULA_STATE.get("formulas", [])) < ole_src:
        gap = ole_src - len(_FORMULA_STATE["formulas"])
        print(f"[math_docx_paper] 🛟 d2t cache 短缺 {gap} 个 OLE → "
              f"启 Ruby per-OLE rId 对齐 fallback", flush=True)
        try:
            # 先加载 rels 用于映射 rId → bin
            _root, _rels = _load_docx(docx, extract_dir)
            _FORMULA_BY_RID = _build_formula_by_rid(extract_dir, _rels)
            print(f"[math_docx_paper] 🛟 Ruby 对齐 map 大小: "
                  f"{len(_FORMULA_BY_RID)} rId → LaTeX", flush=True)
        except Exception as e:
            print(f"[math_docx_paper] ⚠ Ruby 对齐 fallback 失败: {e}", flush=True)
            _FORMULA_BY_RID = {}

    # ── 第 2 遍 walk：用 cache 替换 OLE 为 $LaTeX$ ──
    # 重新 extract（避免 figures 重复拷贝；用同一 extract_dir 即可）
    md, stats = docx_to_markdown(docx, extract_dir, figures_dir)

    # ── 双文件模式：抽答案 docx，把内容追加到主 md，让 split_by_questions
    # 的 in_answer_page 分支接管（chaoyang/pinggu 评分参考模板）──
    if ans_only_docx:
        ans_extract_dir = out_dir / "docx-extracted-ans"
        # 答案 docx 也单独建 OLE cache（公式题号可能不同）
        try:
            from docx_mtef_to_latex import extract_formulas
            ans_cache_dir = structured / "mtef-cache-ans"
            ans_formulas = extract_formulas(ans_only_docx, ans_cache_dir)
            _FORMULA_STATE = {"formulas": ans_formulas, "idx": 0}
            print(f"[math_docx_paper] 🧮 (ans) MTEF→LaTeX cache: "
                  f"{len(ans_formulas)} 个公式", flush=True)
        except Exception as e:
            print(f"[math_docx_paper] ⚠ (ans) MTEF cache 失败: {e}", flush=True)
            _FORMULA_STATE = {"formulas": [], "idx": 0}
        # (ans docx) Ruby per-OLE rId 对齐 fallback（先做一次 ans walk 拿 ole_source）
        _ans_root, _ans_rels = _load_docx(ans_only_docx, ans_extract_dir)
        _ans_ole = sum(1 for o in _ans_root.iter()
                       if _local(o.tag) == "object"
                       and o.tag.startswith(f"{{{W_NS}}}"))
        if _ans_ole and len(_FORMULA_STATE.get("formulas", [])) < _ans_ole:
            try:
                _FORMULA_BY_RID = _build_formula_by_rid(ans_extract_dir, _ans_rels)
                print(f"[math_docx_paper] 🛟 (ans) Ruby 对齐 map: "
                      f"{len(_FORMULA_BY_RID)} rId → LaTeX", flush=True)
            except Exception as e:
                print(f"[math_docx_paper] ⚠ (ans) Ruby 对齐 fallback 失败: {e}",
                      flush=True)
                _FORMULA_BY_RID = {}
        else:
            _FORMULA_BY_RID = {}
        ans_md, _ans_stats = docx_to_markdown(ans_only_docx, ans_extract_dir,
                                                figures_dir)
        # 追加触发 anchor，确保 in_answer_page 分支被激活
        if not _is_answer_page_title(ans_md.split("\n", 1)[0].strip()):
            md = md + "\n\n数学参考答案\n\n" + ans_md
        else:
            md = md + "\n\n" + ans_md
        print(f"[math_docx_paper] 📎 合成 ans md ({len(ans_md)} chars) 追加到主 md",
              flush=True)

    (structured / "raw.md").write_text(md, encoding="utf-8")
    print(f"[math_docx_paper] 段落 {stats['paragraphs']} | "
          f"OMML {stats['omath_source']} / OLE {stats.get('ole_source', 0)} "
          f"→ md $-公式 {stats['inline_eq_md']+stats['display_eq_md']} | "
          f"图引用 src {stats['blips_source']} → md {stats['img_refs_md']}",
          flush=True)

    # ── 切题 + 答案 ──
    questions, answers = split_by_questions(md)
    print(f"[math_docx_paper] 切出 {len(questions)} 题 / {len(answers)} 答案",
          flush=True)

    # 类型 + 分值
    for q in questions:
        q["type"] = _infer_type(q["number"], q.get("options"))
        stem = q.get("stem", "")
        score_m = STEM_SCORE_RE.match(stem)
        if score_m:
            q["score"] = int(score_m.group(1))
            q["stem"] = STEM_SCORE_RE.sub("", stem).lstrip()
        else:
            q["score"] = _default_score(q["number"])
        q["has_image_options"] = (q["type"] == "choice"
            and q.get("options")
            and any("![](" in (v or "") for v in q["options"].values()))
        q["source_page"] = 1
        # stem 里的 ![](...) 剥干净（figures 字段已独立保存）
        q["stem"] = re.sub(r"!\[\]\([^)]+\)", "", q["stem"]).strip()
        # 选项里的 ![](...) → "[图]" 占位
        if q.get("options"):
            for k, v in list(q["options"].items()):
                if isinstance(v, str) and v.strip().startswith("![]("):
                    q["options"][k] = "[图]"
                elif isinstance(v, str):
                    q["options"][k] = re.sub(r"!\[\]\([^)]+\)", "", v).strip()

    # 校验
    val = validate(stats, questions, answers, figures_dir)
    if val["errors"]:
        print("[校验] errors:")
        for e in val["errors"]:
            print(f"  ✗ {e}")
    if val["warnings"]:
        print("[校验] warnings:")
        for w in val["warnings"]:
            print(f"  ⚠ {w}")

    full_score = sum(q["score"] for q in questions) or None
    exam_name = docx.stem.replace(".docx", "").strip()
    DEFAULT_DURATION = {"math": 120, "chinese": 150, "english": 90,
                          "physics": 70, "politics": 70}
    final = {
        "subject": a.subject,
        "exam": exam_name,
        "full_score": full_score,
        "duration_minutes": DEFAULT_DURATION.get(a.subject, 120),
        "questions": [{
            "id": f"{a.subject}-q{q['number']:02d}",
            "number": q["number"],
            "type": q["type"],
            "score": q["score"],
            "stem": q["stem"],
            "options": q["options"],
            "has_image_options": q["has_image_options"],
            "source_page": q["source_page"],
            "figure_path": (f"figures/{q['figures'][0]}"
                            if q["figures"] else None),
            "figures_all": q["figures"],
        } for q in questions],
        "answers": answers,
        "validation": val,
        "stats": stats,
    }
    fj = structured / "final.json"
    fj.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[math_docx_paper] ✅ {fj}", flush=True)
    print(f"   题号={[q['number'] for q in questions]}", flush=True)

    _write_review_yaml(docx, a.subject, final, questions, answers,
                       figures_dir, out_dir)


# ─── 写 yaml ─────────────────────────────────────────────────────────────────

TYPE_EN2CN = {
    "choice": "单选",
    "multi_choice": "多选",
    "fill_blank": "填空",
    "problem_solving": "解答",
    "calculation": "计算",
    "experiment": "实验探究",
    "essay": "解答",
}


def _write_review_yaml(docx: Path, subject: str, final: dict,
                        questions: list[dict], answers: list[dict],
                        figures_dir: Path, out_dir: Path) -> None:
    try:
        import yaml
    except ImportError:
        print("[math_docx_paper] (skip yaml: PyYAML 未装)", flush=True)
        return

    slug = out_dir.name
    m = re.match(r"(\d{4})-(.+?)-(\w+)", slug)
    year = int(m.group(1)) if m else None
    region_slug = m.group(2) if m else ""
    typ_slug = m.group(3) if m else ""

    region_cn = {"chaoyang": "朝阳", "haidian": "海淀", "mentougou": "门头沟",
                 "fengtai": "丰台", "xicheng": "西城", "dongcheng": "东城",
                 "shijingshan": "石景山", "tongzhou": "通州", "shunyi": "顺义",
                 "changping": "昌平", "daxing": "大兴", "fangshan": "房山",
                 "pinggu": "平谷", "huairou": "怀柔", "miyun": "密云",
                 "yanqing": "延庆", "yanshan": "燕山"}.get(region_slug, region_slug)
    type_cn = {"yi": "一模", "er": "二模", "san": "三模", "zhen": "真题",
               "qz": "期中", "qm": "期末"}.get(typ_slug, "一模")

    def _strip_md_img(s: str) -> str:
        if not isinstance(s, str): return s
        return re.sub(r"!\[\]\([^)]+\)", "", s).strip()

    answers_by_num = {a["number"]: a for a in answers}

    repo_root = out_dir
    while repo_root.parent != repo_root:
        if (repo_root / "knowledge-base").is_dir(): break
        repo_root = repo_root.parent
    _yaml_path_pre = (repo_root / "knowledge-base" / "exams" / "mock"
                      / subject / "beijing" / f"{slug}.yaml")
    existing_qc: dict[int, dict] = {}
    if _yaml_path_pre.exists():
        try:
            old = yaml.safe_load(_yaml_path_pre.read_text(encoding="utf-8")) or {}
            for oq in (old.get("questions") or []):
                qid = oq.get("id")
                if qid is None: continue
                existing_qc[qid] = {
                    "qc_status": oq.get("qc_status", "draft"),
                    "qc_note":   oq.get("qc_note", ""),
                }
        except Exception as e:
            print(f"[math_docx_paper] ⚠ 读旧 yaml 合并 qc_* 失败: {e}", flush=True)

    yaml_questions = []
    for q in questions:
        n = q["number"]
        a = answers_by_num.get(n, {})
        qtype = TYPE_EN2CN.get(q["type"], "解答")
        item: dict = {
            "id": n,
            "type": qtype,
            "score": q["score"],
            "stem": _strip_md_img(q["stem"]),
        }
        if q["options"]:
            clean_opts = {}
            for k, v in q["options"].items():
                if isinstance(v, str) and v.strip().startswith("![]("):
                    clean_opts[k] = "[图]"
                else:
                    clean_opts[k] = _strip_md_img(v)
            item["options"] = clean_opts
        if q.get("has_image_options"):
            item["has_image_options"] = True
        if q["figures"]:
            item["figure"] = f"{slug}/figures/{q['figures'][0]}"
        item["answer"] = a.get("correct", "")
        item["solution"] = _strip_md_img(a.get("solution", ""))
        item["knowledge_points"] = []
        item["module"] = ""
        item["difficulty"] = ""
        prev = existing_qc.get(n, {})
        item["qc_status"] = prev.get("qc_status", "draft")
        item["qc_note"] = prev.get("qc_note", "")
        yaml_questions.append(item)

    mock_dir = _yaml_path_pre.parent
    mock_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = _yaml_path_pre

    yaml_figs_dir = mock_dir / slug / "figures"
    yaml_figs_dir.mkdir(parents=True, exist_ok=True)
    if figures_dir.is_dir():
        for f in figures_dir.glob("*.png"):
            shutil.copy(f, yaml_figs_dir / f.name)

    data = {
        "year": year,
        "district": (region_cn + "区") if region_cn else "",
        "exam_type": type_cn,
        "subject": subject,
        "full_score": final.get("full_score"),
        "duration_minutes": 120,
        "total_questions": len(yaml_questions),
        "structure": _build_structure(yaml_questions),
        "questions": yaml_questions,
    }
    yaml_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    print(f"[math_docx_paper] ✅ yaml {yaml_path}", flush=True)


def _build_structure(qs: list[dict]) -> str:
    from collections import OrderedDict
    counts: "OrderedDict[str, dict]" = OrderedDict()
    for q in qs:
        t = q["type"]
        if t not in counts:
            counts[t] = {"count": 0, "score": 0}
        counts[t]["count"] += 1
        counts[t]["score"] += q["score"]
    return " + ".join(f"{v['count']}{t}({v['score']}分)" for t, v in counts.items())


if __name__ == "__main__":
    main()
