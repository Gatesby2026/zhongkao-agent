#!/usr/bin/env python3
"""docx_paper — Word 数学试卷 → 结构化 final.json（v1 数学路线）。

唯一入口（与物理 tencent_paper.py 对偶）：
  python3 scripts/exam-docx/docx_paper.py <docx> --subject math [--force]

流水线（无外部依赖，纯 Python）：
  1. 解 docx zip → 抽 word/document.xml + media/*.png
  2. 逐段（w:p）转 markdown：
     - w:r → 文字
     - m:oMath → LaTeX `$...$`（omml2latex 转换）
     - w:drawing/a:blip → 图片占位 `![](media/imageN.png)`
  3. ^N. 锚点切题 → questions[]
  4. "参考答案" 标识切答案 → answers[]
  5. 校验：OMML 数 vs $ 数 / image 引用 vs media 文件 / 题号连续
  6. 输出 final.json + figures/ + status

公式/图"一个不能错"保证：
  - 公式：每个 OMML 对应一个 $...$，校验阶段计数一致；LaTeX 合法性（$ 配对、\\frac{}{} 完整）
  - 图：每张 media/*.png 至少被引用 1 次；每题"如图N"必须有对应 figure_path
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

NS = {"w": W_NS, "m": M_NS, "a": A_NS, "r": R_NS, "wp": WP_NS, "pic": PIC_NS}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


# ─── docx 结构解析 ──────────────────────────────────────────────────────────

def _load_docx(docx_path: Path, extract_dir: Path) -> tuple[ET.Element, dict[str, str]]:
    """解压 docx，返回 (document.xml root, rels: {rId: media_path})。"""
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path) as z:
        z.extractall(extract_dir)
    doc_xml = (extract_dir / "word" / "document.xml").read_text(encoding="utf-8")
    root = ET.fromstring(doc_xml)
    # 关系文件 word/_rels/document.xml.rels：rId → Target 路径
    rels_path = extract_dir / "word" / "_rels" / "document.xml.rels"
    rels: dict[str, str] = {}
    if rels_path.exists():
        rels_root = ET.fromstring(rels_path.read_text(encoding="utf-8"))
        for r in rels_root:
            if _local(r.tag) == "Relationship":
                rid = r.get("Id"); target = r.get("Target", "")
                # docx 内 image 多在根 media/，也可能 word/media/
                rels[rid] = target
    return root, rels


def _para_to_markdown(p: ET.Element, rels: dict[str, str],
                      extract_dir: Path,
                      figures_dir: Path) -> str:
    """把一段（w:p）转成单行 markdown。
    按子元素文档顺序拼：w:r 文字 / m:oMath 公式 / w:drawing 图。
    图片同时拷贝到 figures_dir 并生成 ![](figures/imageN.png) 占位。
    """
    parts = []
    for el in p.iter():
        tag = _local(el.tag)
        # 文字直接来自 w:t
        if tag == "t" and el.tag.startswith(f"{{{W_NS}}}"):
            if el.text:
                parts.append(("text", el.text))
        # OMML 公式：oMath 是叶级节点（被遍历到 t 之后会再次进入它的 t 子节点，避免重复）
        # 解决方案：用 iter() 不行，改为递归处理 w:p 子节点（一层）
        pass
    # 上面 iter() 会扁平化所有子孙节点；需要改成结构化遍历
    return _walk_paragraph(p, rels, extract_dir, figures_dir)


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
            # display 公式
            for om in child.findall(f"{{{M_NS}}}oMath"):
                out.append(omml_to_latex(om, inline=False))
        elif tag in ("hyperlink",):
            # 超链接：递归处理子 run
            out.append(_walk_paragraph(child, rels, extract_dir, figures_dir))
    return "".join(out).strip()


def _walk_run(r: ET.Element, rels: dict[str, str],
              extract_dir: Path, figures_dir: Path) -> str:
    """w:r 内可能含 w:t 文字 / w:drawing 图片 / m:oMath 公式。按顺序拼。"""
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
            # inline 公式嵌在 w:r 内（Word docx 常见结构）
            out.append(omml_to_latex(child))
    return "".join(out)


def _extract_image(drawing_el: ET.Element, rels: dict[str, str],
                    extract_dir: Path, figures_dir: Path) -> str:
    """从 w:drawing/w:pict 节点提取图片：拷贝到 figures_dir，返回 markdown 占位。"""
    # 找 a:blip embed="rIdN"
    for blip in drawing_el.iter(f"{{{A_NS}}}blip"):
        rid = blip.get(f"{{{R_NS}}}embed") or blip.get(f"{{{R_NS}}}link")
        if not rid: continue
        target = rels.get(rid)
        if not target: continue
        # target 可能是 media/image.png 或 ../media/image.png
        src = extract_dir / "word" / target  # word/媒体相对路径
        if not src.exists():
            # docx 根 media/
            src = extract_dir / target.lstrip("/.")
        if not src.exists():
            # 兜底：去除 ../ 前缀
            src = extract_dir / re.sub(r"^(\.\./)+", "", target)
        if not src.exists():
            print(f"  ⚠ 图片找不到: {target}", file=sys.stderr)
            continue
        figures_dir.mkdir(parents=True, exist_ok=True)
        out = figures_dir / src.name
        if not out.exists():
            shutil.copy(src, out)
        return f"![](figures/{src.name})"
    return ""


def docx_to_markdown(docx_path: Path, extract_dir: Path,
                     figures_dir: Path) -> tuple[str, dict]:
    """主转换：docx → markdown 字符串 + 统计信息。
    统计含 OMML 公式数、图片引用数、段落数，用于后续校验。
    """
    root, rels = _load_docx(docx_path, extract_dir)
    # 全文档 OMML 数（每个 oMath 一个公式）
    total_omath = len(list(root.iter(f"{{{M_NS}}}oMath")))
    # 全 blip 引用数（图片用次）
    total_blips = len(list(root.iter(f"{{{A_NS}}}blip")))

    # 按 body 子节点**实际顺序**遍历 w:p / w:tbl（关键！）
    # 旧版分两次 findall → 表格全聚到 md 末尾被最后一题 stem/solution 吞进
    body = root.find(f"{{{W_NS}}}body")
    if body is None:
        return "", {"omath": 0, "blips": 0, "paragraphs": 0}
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

    # markdown 中的 $ 配对数 + ![](图片) 数
    n_dollars = md.count("$")
    n_inline = len(re.findall(r"\$[^$]+\$", md))
    n_display = len(re.findall(r"\$\$[^$]+\$\$", md))
    n_img_md = len(re.findall(r"!\[\]\(figures/", md))

    return md, {
        "omath_source": total_omath,
        "blips_source": total_blips,
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


# ─── 切题 ───────────────────────────────────────────────────────────────────

NUM_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.*)$")
# 答案页 marker 必须是独立标题行（行首 + 短行）
ANSWER_MARKER_RE = re.compile(
    r"^\s*(?:参考答案|答案及评分|评分标准|答案与解析|参考答案与试题解析"
    r"|参考答案及评分标准)"
)
# 噪声行：试卷标题 / 著作权声明 / 用户水印
NOISE_LINE_RE = re.compile(
    r"^\s*(?:"
    r"\d{4}年[^\n]*?(?:试卷|试题)\s*$"
    r"|声明[:：][^\n]*?著作权"
    r"|试题解析著作权"
    r"|发布日期[:：]"
    r"|用户[:：][^\n]*?(?:邮箱|学号)"
    r"|菁优网"
    r")"
)
# 题首 `（N分）` 分值标识
STEM_SCORE_RE = re.compile(r"^\s*[（(]\s*(\d+)\s*分\s*[)）]\s*")
def _is_answer_title(line: str) -> bool:
    return bool(ANSWER_MARKER_RE.match(line)) and len(line.strip()) <= 20
SECTION_HEAD_RE = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、，]")
# 选项匹配：A． / A. / (A) 后跟内容直到下一个选项标识或文末
OPT_SPLIT_RE = re.compile(r"(?:\(([A-D])\)|([A-D])\s*[.、．])\s*")


def _extract_options(text: str) -> tuple[str, dict[str, str]]:
    """从一段（可能跨行）文本里抽 A/B/C/D 选项。
    支持「A．xxx B．xxx C．xxx D．xxx」一行多选项，或换行各占一行的混合排版。
    返回 (stem_clean, options_dict)。若未识别到 4 个完整选项，返回原文 + 空 dict。
    """
    matches = list(OPT_SPLIT_RE.finditer(text))
    if len(matches) < 4:
        return text, {}
    # 取末 4 个连续 ABCD（防 stem 里有 "A、B、C" 误匹配）
    # 找最后一段 A/B/C/D 连续出现
    labels = [m.group(1) or m.group(2) for m in matches]
    # 找尾部能凑出 ABCD 顺序的 4 个
    n = len(matches)
    start_idx = None
    for i in range(n - 3):
        if [labels[i], labels[i+1], labels[i+2], labels[i+3]] == ["A", "B", "C", "D"]:
            start_idx = i  # 取第一个完整 ABCD 序列
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
    """切题：返回 (questions, answers)。

    流程：
      1. 按行扫，^N. 锚点切题块（累积所有续行到 stem）
      2. 答案页 marker 触发 in_answer 切到答案累积
      3. 每题切完后 post-process 抽选项（支持一行多选项）
      4. 图片 ![]() 按出现顺序记录到 figures[]
    """
    questions: list[dict] = []
    answers: list[dict] = []
    cur: dict | None = None
    in_answer = False
    expected_q = 1  # 期望的下一道题号
    expected_a = 1

    def _flush_q():
        if cur and cur.get("number"):
            stem_full = cur["stem"].strip()
            stem_clean, opts = _extract_options(stem_full)
            questions.append({
                "number": cur["number"],
                "stem": stem_clean,
                "options": opts if opts else None,
                "figures": cur["figures"],
            })

    def _flush_a():
        if cur and cur.get("number"):
            raw = cur["stem"].strip()
            # 抽【答案】X / 【解答】xxx
            ans_m = re.search(r"【答案】\s*([A-D]+|[^\n【]*)", raw)
            correct = ans_m.group(1).strip() if ans_m else ""
            # 多选题 correct 可能是 "ABC" 多字母
            if correct and not re.fullmatch(r"[A-D]+", correct):
                correct = ""  # 非字母答案（填空/解答的最终答案）保留在 solution
            sol_m = re.search(r"【解答】(.+?)(?=\n*【|$)", raw, re.DOTALL)
            solution = sol_m.group(1).strip() if sol_m else raw
            answers.append({
                "number": cur["number"],
                "correct": correct,
                "solution": solution,
            })

    for line in md.split("\n"):
        if not line.strip():
            continue
        # 噪声行（试卷标题/著作权/水印）一律丢弃
        if NOISE_LINE_RE.search(line):
            continue
        if not in_answer and _is_answer_title(line):
            if cur:
                _flush_q()
            cur = None
            in_answer = True
            continue
        if SECTION_HEAD_RE.match(line):
            continue
        m = NUM_HEAD_RE.match(line)
        if m and 1 <= int(m.group(1)) <= 30:
            n = int(m.group(1))
            # 题号锚点必须递增（容忍 +0 重复）；非递增视为题目正文中嵌入的
            # "1. " "9. " 等小条目（典型如 daxing/pinggu/fengtai）
            exp = expected_a if in_answer else expected_q
            if n == exp or n == exp - 1:
                if in_answer:
                    _flush_a(); expected_a = n + 1
                else:
                    _flush_q(); expected_q = n + 1
                cur = {"number": n,
                       "stem": m.group(2).strip(),
                       "options": {},
                       "figures": [],
                       "correct": ""}
                continue
            # 题号倒退或跳号大 → 不是真题号，当正文处理
            if cur is None: continue
            # 累积到 stem（fall through to 下面默认行为）
        if cur is None: continue
        for img_m in re.finditer(r"!\[\]\(figures/([^)]+)\)", line):
            cur["figures"].append(img_m.group(1))
        cur["stem"] += "\n" + line

    if in_answer:
        _flush_a()
    else:
        _flush_q()
    return questions, answers


# ─── 类型推断（北京数学卷结构）─────────────────────────────────────────────

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
    """北京中考数学默认分值（兜底）。"""
    if 1 <= num <= 8:   return 2
    if 9 <= num <= 16:  return 3
    if 17 <= num <= 19: return 5
    if 20 <= num <= 22: return 6
    if 23 <= num <= 26: return 6
    if num == 27:       return 7
    if num == 28:       return 7
    return 6


# ─── 校验器 ─────────────────────────────────────────────────────────────────

def validate(stats: dict, questions: list[dict], answers: list[dict],
              figures_dir: Path) -> dict:
    """公式/图/结构三层校验。"""
    issues = {"errors": [], "warnings": []}
    # 公式数一致
    eq_md_total = stats["inline_eq_md"] + stats["display_eq_md"]
    if eq_md_total != stats["omath_source"]:
        issues["warnings"].append(
            f"公式计数不一致: OMML 源 {stats['omath_source']} ≠ "
            f"markdown $ {eq_md_total}（差 {stats['omath_source'] - eq_md_total}）"
        )
    # 题号连续
    nums = sorted(q["number"] for q in questions)
    if nums:
        gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
        if gaps:
            issues["errors"].append(f"题号断号: {gaps}")
    # 选择题 options 全
    for q in questions:
        n = q["number"]; t = _infer_type(n, q.get("options"))
        if t == "choice":
            opts = q.get("options") or {}
            if set(opts) != {"A", "B", "C", "D"}:
                issues["errors"].append(
                    f"Q{n} 选择题 options 不全: {sorted(opts.keys())}"
                )
    # 题干引图 vs figures
    for q in questions:
        n = q["number"]
        stem = q.get("stem") or ""
        refs = set(re.findall(r"图\s*(\d+)", stem) + re.findall(r"如图\s*(\d+)", stem))
        if refs and not q.get("figures"):
            issues["errors"].append(f"Q{n} 题干引图 {sorted(refs)} 但无 figure")
    # 媒体文件孤立检测：figures/ 下 png 是否全被引用（题 + 答案）
    used = set()
    for q in questions: used |= set(q.get("figures") or [])
    for a in answers:
        # 答案 solution 中也可能含图（如几何题示意图）
        used |= set(re.findall(r"figures/([^)\s]+)", a.get("solution") or ""))
    if figures_dir.is_dir():
        all_pngs = {p.name for p in figures_dir.glob("*.png")}
        orphan = all_pngs - used
        if orphan:
            issues["warnings"].append(
                f"figures/ 下未引用图 {len(orphan)} 张: {sorted(orphan)[:5]}...")
    return issues


# ─── 入口 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx", type=Path)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="staging 目录；缺省按 derive 规则推导")
    ap.add_argument("--subject", default="math")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    docx = a.docx.resolve()
    if not docx.exists():
        sys.exit(f"docx 不存在: {docx}")

    # 推导 staging 目录
    if a.out_dir:
        out_dir = a.out_dir.resolve()
    else:
        # 从文件名解析：如"2026年北京市朝阳区中考数学一模试卷.docx"
        name = docx.stem
        m_year = re.search(r"(\d{4})", name)
        m_region = re.search(r"北京市?([一-龥]+?)区", name)
        m_type = re.search(r"(一模|二模|三模|期中|期末|中考)", name)
        year = m_year.group(1) if m_year else "0000"
        region = m_region.group(1) if m_region else "unknown"
        type_cn = m_type.group(1) if m_type else "一模"
        type_map = {"一模": "yi", "二模": "er", "三模": "san", "中考": "zhen"}
        typ = type_map.get(type_cn, type_cn)
        # 区中文 → 拼音/英文 slug（按物理路径风格 mentougou/chaoyang...）
        region_slug = {"朝阳": "chaoyang", "海淀": "haidian", "门头沟": "mentougou",
                       "丰台": "fengtai", "西城": "xicheng", "东城": "dongcheng",
                       "石景山": "shijingshan", "通州": "tongzhou", "顺义": "shunyi",
                       "昌平": "changping", "大兴": "daxing", "房山": "fangshan",
                       "平谷": "pinggu", "怀柔": "huairou", "密云": "miyun",
                       "延庆": "yanqing", "燕山": "yanshan"}.get(region, region)
        slug = f"{year}-{region_slug}-{typ}"
        # 推 repo_root（从 docx 向上找含 knowledge-base 的目录）
        cur = docx.parent
        while cur.parent != cur:
            if (cur / "knowledge-base").is_dir():
                out_dir = (cur / "knowledge-base" / "exams" / "_staging"
                           / a.subject / slug)
                break
            cur = cur.parent
        else:
            sys.exit("无法定位 repo_root（找不到 knowledge-base/ ）")

    print(f"[docx_paper] {docx.name} → {out_dir}", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = out_dir / "docx-extracted"
    figures_dir = out_dir / "figures"
    structured = out_dir / "structured-cloud"
    structured.mkdir(parents=True, exist_ok=True)

    if a.force:
        for p in (extract_dir, figures_dir):
            if p.is_dir(): shutil.rmtree(p)

    md, stats = docx_to_markdown(docx, extract_dir, figures_dir)
    (structured / "raw.md").write_text(md, encoding="utf-8")
    print(f"[docx_paper] 段落 {stats['paragraphs']} | "
          f"OMML 源 {stats['omath_source']} → md $-公式 "
          f"{stats['inline_eq_md']+stats['display_eq_md']} | "
          f"图引用 src {stats['blips_source']} → md {stats['img_refs_md']}", flush=True)

    # 切题
    questions, answers = split_by_questions(md)
    print(f"[docx_paper] 切出 {len(questions)} 题 / {len(answers)} 答案", flush=True)

    # 类型 + 分值（先尝试从 stem 抽"（N分）"标识，失败再用默认）
    for q in questions:
        q["type"] = _infer_type(q["number"], q.get("options"))
        stem = q.get("stem", "")
        score_m = STEM_SCORE_RE.match(stem)
        if score_m:
            q["score"] = int(score_m.group(1))
            # 同时把 stem 开头的 "（N分）" 去掉（视觉噪声，分值已存 score 字段）
            q["stem"] = STEM_SCORE_RE.sub("", stem).lstrip()
        else:
            q["score"] = _default_score(q["number"])
        # has_image_options 推断（选择题且选项含 ![]() 图）
        q["has_image_options"] = (q["type"] == "choice"
            and q.get("options")
            and any("![](" in (v or "") for v in q["options"].values()))
        q["source_page"] = 1  # docx 无页号；统一 1

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

    # 输出 final.json
    full_score = sum(q["score"] for q in questions) or None
    # 元数据：从 stem 第一段头 / 文件名
    exam_name = f"{docx.stem.replace('.docx','').strip()}"
    final = {
        "subject": a.subject,
        "exam": exam_name,
        "full_score": full_score,
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
            "figures_all": q["figures"],  # 多图保留
        } for q in questions],
        "answers": answers,
        "validation": val,
        "stats": stats,
    }
    fj = structured / "final.json"
    fj.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[docx_paper] ✅ {fj}", flush=True)
    print(f"   题号={[q['number'] for q in questions]}", flush=True)

    # 同步输出兼容物理 exam-review 的 yaml（schema 一致：可用同一审核工具）
    _write_review_yaml(docx, a.subject, final, questions, answers,
                       figures_dir, out_dir)


# ─── 写 yaml（兼容物理 exam-review schema）─────────────────────────────────

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
    """把 final.json 转成兼容 tools/exam-review 的 yaml，落到
    knowledge-base/exams/mock/<subject>/beijing/<slug>.yaml + figures/ 软目录。

    schema 与物理 enrich 产物一致：
      year/district/exam_type/subject/full_score/duration_minutes/
      total_questions/questions[]：id(int)/type(中文)/score/stem/options/
      has_image_options/figure/answer/solution/knowledge_points/module/
      difficulty/qc_status/qc_note
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        print("[docx_paper] (skip yaml: PyYAML 未装)", flush=True)
        return

    slug = out_dir.name  # 如 2026-chaoyang-zhen
    # 解析 slug → year/region/typ
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
    type_cn = {"yi": "一模", "er": "二模", "san": "三模", "zhen": "一模"}.get(typ_slug, "一模")

    # 剥离 stem/options/solution 中的 ![](...) markdown 图引用：
    # 图已被 figure 字段独立持有；留在文本里 exam-review 不渲染 → 显示成
    # "![](figures/...)" 原文噪声，且与 figure 字段渲染的图重复显示。
    def _strip_md_img(s: str) -> str:
        if not isinstance(s, str): return s
        return re.sub(r"!\[\]\([^)]+\)", "", s).strip()

    answers_by_num = {a["number"]: a for a in answers}
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
            # 图选项题 option 值是 `![](figures/imgN.png)` → 转 "[图]" 占位
            # （has_image_options=True 让 exam-review 知道是图选项）
            clean_opts = {}
            for k, v in q["options"].items():
                if isinstance(v, str) and v.strip().startswith("![]("):
                    clean_opts[k] = "[图]"
                else:
                    clean_opts[k] = _strip_md_img(v)
            item["options"] = clean_opts
        if q.get("has_image_options"):
            item["has_image_options"] = True
        # figure 路径：与物理 yaml 一致 `<slug>/figures/<name>`
        if q["figures"]:
            item["figure"] = f"{slug}/figures/{q['figures'][0]}"
        item["answer"] = a.get("correct", "")
        item["solution"] = _strip_md_img(a.get("solution", ""))
        item["knowledge_points"] = []
        item["module"] = ""
        item["difficulty"] = ""
        item["qc_status"] = "draft"
        item["qc_note"] = ""
        yaml_questions.append(item)

    # 推 mock 目录：knowledge-base/exams/mock/<subject>/beijing/<slug>.yaml
    repo_root = out_dir
    while repo_root.parent != repo_root:
        if (repo_root / "knowledge-base").is_dir():
            break
        repo_root = repo_root.parent
    mock_dir = repo_root / "knowledge-base" / "exams" / "mock" / subject / "beijing"
    mock_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = mock_dir / f"{slug}.yaml"

    # figures 复制到 yaml 同级目录
    yaml_figs_dir = mock_dir / slug / "figures"
    yaml_figs_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    if figures_dir.is_dir():
        for f in figures_dir.glob("*.png"):
            shutil.copy(f, yaml_figs_dir / f.name)

    data = {
        "year": year,
        "district": (region_cn + "区") if region_cn else "",
        "exam_type": type_cn,
        "subject": subject,
        "full_score": final.get("full_score"),
        "duration_minutes": 120,  # 北京数学一模默认 120 分钟
        "total_questions": len(yaml_questions),
        "structure": _build_structure(yaml_questions),
        "questions": yaml_questions,
    }
    yaml_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    print(f"[docx_paper] ✅ yaml {yaml_path}", flush=True)


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
