#!/usr/bin/env python3
"""
从 YAML 结构化数据生成北京中考数学模拟试卷 PDF
用法: python3 scripts/generate-exam-pdf.py knowledge-base/mock-exams/math/beijing/2025-chaoyang-yi.yaml

图片尺寸策略（参见 EXAM-FORMAT-SPEC.md § 图形排版规范）:
  - 选项内图片（A.[图]B.[图]）: 2×2 网格, 每格 ≤55mm 宽
  - 题干配图（独立 [图]）: 居中, ≤90mm 宽, ≤55mm 高
  - 解答题大图: 居中, ≤110mm 宽, ≤70mm 高
"""

import sys, os, re, io, tempfile, hashlib, html
from pathlib import Path

import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.colors import black
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    Flowable, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── 字体注册 ──────────────────────────────────────────────
SONGTI_PATH = "/System/Library/Fonts/Supplemental/Songti.ttc"
SIMHEI_PATH = "/Library/Fonts/Microsoft/SimHei.ttf"
# subfontIndex: 0=Black, 1=Bold, 2=TC-Bold, 3=SC-Light, 4=STSong
# 原卷正文用常规宋体（Regular），对应 Light 或 STSong
pdfmetrics.registerFont(TTFont("Songti", SONGTI_PATH, subfontIndex=3))
pdfmetrics.registerFont(TTFont("Heiti", SIMHEI_PATH))

PAGE_W, PAGE_H = A4
MARGIN_LR = 25 * mm
MARGIN_TB = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_LR  # ~160mm

# ── 图片尺寸常量（基于原始 docx 实测数据）─────────────────
# 原始 docx 中选项图 ~29×15mm, 题干图 ~40×35mm, 解答题图 ~70×60mm
OPT_FIG_MAX_W = 35 * mm    # 选项内图片 (A.[图]) — 上限
OPT_FIG_MAX_H = 25 * mm
STEM_FIG_MAX_W = 60 * mm   # 题干配图 (选择/填空题) — 上限
STEM_FIG_MAX_H = 50 * mm
SOLVE_FIG_MAX_W = 100 * mm  # 解答题配图 — 上限
SOLVE_FIG_MAX_H = 80 * mm
# 后备 DPI（仅在 YAML 无原始尺寸时使用）
FALLBACK_PX_TO_MM = 25.4 / 150  # 假设 150dpi

# ── LaTeX 预处理 + 渲染 ──────────────────────────────────
FORMULA_CACHE_DIR = Path(tempfile.mkdtemp(prefix="exam_formula_"))

def _preprocess_latex(latex: str) -> str:
    """将 LaTeX 预处理为 matplotlib mathtext 兼容格式"""
    s = latex
    s = s.replace(r'\dfrac', r'\frac')
    s = re.sub(r'\\gt\b', '>', s)
    s = re.sub(r'\\lt\b', '<', s)
    # \ge → \geq, \le → \leq (但不影响 \left, \geqslant 等)
    s = re.sub(r'\\ge(?![qa-z])', r'\\geq', s)
    s = re.sub(r'\\le(?![fqa-z])', r'\\leq', s)
    # 去除 tikzpicture 垃圾（OCR 误识别）
    s = re.sub(r'\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}', '', s, flags=re.DOTALL)
    # 去除 bullet array 垃圾
    s = re.sub(r'\\begin\{array\}\{c\}\s*\\bullet.*?\\end\{array\}', '', s, flags=re.DOTALL)
    return s.strip()


def _is_equation_system(latex: str) -> bool:
    """检测是否是方程组/不等式组 (\\left\\{\\begin{array}...)"""
    return r'\begin{array}' in latex and r'\left' in latex


def _split_equation_system(latex: str) -> list:
    """将方程组拆分为多个独立方程"""
    # 提取 \begin{array}{l} eq1 \\ eq2 \end{array} 中的方程
    m = re.search(r'\\begin\{array\}\{[lcr]\}(.+?)\\end\{array\}', latex, re.DOTALL)
    if m:
        body = m.group(1)
        eqs = [e.strip() for e in body.split(r'\\') if e.strip()]
        return eqs
    return [latex]


def latex_to_image(latex_str: str, fontsize: int = 12) -> str:
    """将 LaTeX 公式渲染为 PNG 图片，返回路径"""
    processed = _preprocess_latex(latex_str)
    if not processed:
        return None

    cache_key = hashlib.md5(f"{processed}_{fontsize}".encode()).hexdigest()
    img_path = FORMULA_CACHE_DIR / f"{cache_key}.png"
    if img_path.exists():
        return str(img_path)

    fig = plt.figure(figsize=(0.01, 0.01))
    fig.patch.set_alpha(0)
    try:
        fig.text(0, 0, f"${processed}$", fontsize=fontsize, math_fontfamily="cm")
    except Exception:
        plt.close(fig)
        return None

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                pad_inches=0.02, transparent=True)
    plt.close(fig)
    with open(img_path, "wb") as f:
        f.write(buf.getvalue())
    return str(img_path)


def equation_system_to_image(latex_str: str, fontsize: int = 12) -> str:
    """将方程组渲染为 PNG：左侧大括号 + 上下排列的方程"""
    eqs = _split_equation_system(latex_str)
    processed_eqs = [_preprocess_latex(eq) for eq in eqs]

    cache_key = hashlib.md5(f"eqsys_{'|'.join(processed_eqs)}_{fontsize}".encode()).hexdigest()
    img_path = FORMULA_CACHE_DIR / f"{cache_key}.png"
    if img_path.exists():
        return str(img_path)

    n = len(processed_eqs)
    fig_h = max(0.4 * n, 0.5)
    fig = plt.figure(figsize=(4, fig_h))
    fig.patch.set_alpha(0)

    # 绘制大括号（用纯文本字符，大小按方程数量调整）
    brace_size = fontsize + 6 * n
    fig.text(0.02, 0.5, "{", fontsize=brace_size,
             va="center", ha="left", fontfamily="serif")

    # 绘制每个方程
    for i, eq in enumerate(processed_eqs):
        y = 1 - (i + 0.5) / n
        try:
            fig.text(0.12, y, f"${eq}$", fontsize=fontsize,
                     math_fontfamily="cm", va="center", ha="left")
        except Exception:
            fig.text(0.12, y, eq, fontsize=fontsize - 1,
                     va="center", ha="left")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                pad_inches=0.03, transparent=True)
    plt.close(fig)
    with open(img_path, "wb") as f:
        f.write(buf.getvalue())
    return str(img_path)


# 公式统一缩放系数：matplotlib fontsize=14 @ 150dpi → 映射到正文 10.5pt
# px → pt = 72/150; 再乘 body/render 字号比 = 10.5/14
FORMULA_RENDER_FONTSIZE = 14
FORMULA_RENDER_DPI = 150
FORMULA_BODY_FONTSIZE = 10.5
FORMULA_SCALE = (72 / FORMULA_RENDER_DPI) * (FORMULA_BODY_FONTSIZE / FORMULA_RENDER_FONTSIZE)


def _formula_display_size(iw_px: int, ih_px: int):
    """根据公式图片实际像素尺寸，用统一缩放比计算显示尺寸和基线偏移。
    返回 (w_pt, h_pt, valign_pt)
    """
    h = max(8, round(ih_px * FORMULA_SCALE))
    w = max(4, round(iw_px * FORMULA_SCALE))
    # 基线对齐：超出正文字号的部分按比例下沉
    valign = -max(0, round((h - FORMULA_BODY_FONTSIZE) * 0.6))
    return w, h, valign


def text_to_para_xml(text: str) -> str:
    """将含 $...$ LaTeX 的文本转为 reportlab Paragraph XML"""
    parts = re.split(r'(\$[^$]+?\$)', text)
    result = []
    for part in parts:
        if part.startswith('$') and part.endswith('$') and len(part) > 2:
            latex = part[1:-1].strip()
            if not latex:
                continue

            # 方程组特殊处理
            if _is_equation_system(latex):
                img_path = equation_system_to_image(latex, fontsize=14)
            else:
                img_path = latex_to_image(latex, fontsize=14)

            if img_path:
                try:
                    from reportlab.lib.utils import ImageReader
                    img = ImageReader(img_path)
                    iw, ih = img.getSize()
                    if _is_equation_system(latex):
                        # 方程组：按实际比例渲染
                        h = 40
                        w = max(1, int(h * iw / ih))
                        valign = -14
                    else:
                        # 统一缩放：保持所有公式比例一致
                        w, h, valign = _formula_display_size(iw, ih)
                    result.append(f'<img src="{img_path}" width="{w}" height="{h}" valign="{valign}"/>')
                except Exception:
                    result.append(html.escape(latex))
            else:
                result.append(html.escape(_preprocess_latex(latex)))
        else:
            result.append(html.escape(part))
    return "".join(result)


# ── 图片缩放 ──────────────────────────────────────────────
def _scaled_image(path: str, max_w, max_h, align="CENTER",
                  orig_w_mm=0, orig_h_mm=0):
    """缩放图片。优先使用原始 docx 宽高 (orig_w_mm/orig_h_mm)，无则用后备 DPI。"""
    try:
        from reportlab.lib.utils import ImageReader
        img = ImageReader(path)
        iw, ih = img.getSize()

        if orig_w_mm > 0 and orig_h_mm > 0:
            # 使用原始 HTML 属性记录的 mm 值（精确）
            w_mm = orig_w_mm
            h_mm = orig_h_mm
        else:
            # 后备：用 150dpi 估算
            w_mm = iw * FALLBACK_PX_TO_MM
            h_mm = ih * FALLBACK_PX_TO_MM

        # 限制不超过 max
        scale = min(1.0, max_w / (w_mm * mm), max_h / (h_mm * mm))
        w = w_mm * mm * scale
        h = h_mm * mm * scale

        if w < 5 * mm or h < 3 * mm:
            return Spacer(1, 1 * mm)

        return Image(path, width=w, height=h, hAlign=align)
    except Exception:
        return Spacer(1, 3 * mm)


# ── 样式 ──────────────────────────────────────────────────
def make_styles():
    s = {}
    # 字体规范（基于原始 docx 实测）:
    #   试卷标题: 16pt 黑体
    #   科目名: 22pt 黑体
    #   正文/题目: 10.5pt 宋体 (五号) — 默认正文
    #   大题标题: 12pt 黑体
    #   考生须知: 10pt 宋体
    # 标题行1: "2025年北京市初中学业水平考试" — 宋体 14pt 常规，居中
    s["title_main"] = ParagraphStyle(
        "title_main", fontName="Songti", fontSize=14,
        alignment=TA_CENTER, leading=20, spaceAfter=2*mm
    )
    # 标题行2: "数 学 试 卷" — 黑体 22pt，居中，字间距很大
    s["title_sub"] = ParagraphStyle(
        "title_sub", fontName="Heiti", fontSize=22,
        alignment=TA_CENTER, leading=28, spaceAfter=3*mm, charSpace=18
    )
    # 考生信息行
    s["info_line"] = ParagraphStyle(
        "info_line", fontName="Songti", fontSize=10.5,
        alignment=TA_CENTER, leading=16, spaceAfter=1*mm
    )
    # 考生须知条目 — 原卷边框内 ~8pt 紧凑排列
    s["notice"] = ParagraphStyle(
        "notice", fontName="Songti", fontSize=8,
        alignment=TA_LEFT, leading=12, spaceAfter=0
    )
    # 分部标题: "第一部分  选择题" — 黑体 12pt，居中
    s["part_title"] = ParagraphStyle(
        "part_title", fontName="Heiti", fontSize=12,
        alignment=TA_CENTER, leading=18, spaceBefore=3*mm, spaceAfter=3*mm
    )
    # 大题标题: "一、选择题（共16分，每题2分）" — 黑体 10.5pt
    s["section_title"] = ParagraphStyle(
        "section_title", fontName="Heiti", fontSize=10.5,
        alignment=TA_LEFT, leading=17, spaceBefore=4*mm, spaceAfter=2*mm
    )
    # 大题说明: "第1-8题均有四个选项..." — 宋体 9pt
    s["section_note"] = ParagraphStyle(
        "section_note", fontName="Songti", fontSize=9,
        alignment=TA_LEFT, leading=14, spaceAfter=2*mm, leftIndent=6*mm
    )
    s["body"] = ParagraphStyle(
        "body", fontName="Songti", fontSize=10.5,
        alignment=TA_LEFT, leading=17, spaceAfter=1*mm
    )
    s["body_indent"] = ParagraphStyle(
        "body_indent", fontName="Songti", fontSize=10.5,
        alignment=TA_LEFT, leading=17, spaceAfter=0.5*mm, leftIndent=6*mm
    )
    s["option"] = ParagraphStyle(
        "option", fontName="Songti", fontSize=10.5,
        alignment=TA_LEFT, leading=16, spaceAfter=0.5*mm, leftIndent=10*mm
    )
    s["table_cell"] = ParagraphStyle(
        "table_cell", fontName="Songti", fontSize=9,
        alignment=TA_CENTER, leading=14
    )
    return s


# ── Markdown 表格 → reportlab Table ──────────────────────
def _split_text_and_tables(text: str):
    """将文本拆分为交替的 [("text", str), ("table", rows), ...] 段。
    支持一段文本中包含多个 markdown 表格。"""
    lines = text.split('\n')
    segments = []
    buf = []  # 当前文本缓冲区
    table_buf = []  # 当前表格行缓冲区
    in_table = False

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith('|') and stripped.endswith('|') and len(stripped) > 2

        if is_table_line:
            if not in_table:
                # 文本 → 表格切换
                text_block = '\n'.join(buf).strip()
                if text_block:
                    segments.append(("text", text_block))
                buf = []
                in_table = True
            table_buf.append(stripped)
        else:
            if in_table:
                # 表格 → 文本切换，输出表格
                rows = []
                for tl in table_buf:
                    cells = [c.strip() for c in tl.strip('|').split('|')]
                    if all(re.match(r'^[-:]+$', c) for c in cells if c):
                        continue  # 跳过分隔行
                    rows.append(cells)
                if rows:
                    segments.append(("table", rows))
                table_buf = []
                in_table = False
            buf.append(line)

    # 收尾
    if in_table and table_buf:
        rows = []
        for tl in table_buf:
            cells = [c.strip() for c in tl.strip('|').split('|')]
            if all(re.match(r'^[-:]+$', c) for c in cells if c):
                continue
            rows.append(cells)
        if rows:
            segments.append(("table", rows))
    elif buf:
        text_block = '\n'.join(buf).strip()
        if text_block:
            segments.append(("text", text_block))

    return segments


def _build_md_table(rows, styles):
    """将 markdown 表格行转为 reportlab Table flowable"""
    n_cols = max(len(r) for r in rows) if rows else 1
    table_data = []
    for row in rows:
        while len(row) < n_cols:
            row.append("")
        table_row = []
        for cell in row:
            cell_xml = text_to_para_xml(cell) if '$' in cell else html.escape(cell)
            try:
                table_row.append(Paragraph(cell_xml, styles["table_cell"]))
            except Exception:
                table_row.append(Paragraph(html.escape(cell), styles["table_cell"]))
        table_data.append(table_row)

    # 计算列宽
    col_w = CONTENT_W / n_cols
    t = Table(table_data, colWidths=[col_w] * n_cols)
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Heiti'),  # 表头加粗
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


# ── 选项图片网格 ──────────────────────────────────────────
def _build_option_figure_grid(labels_and_figs, base_dir):
    """构建图片选项网格：4 个选项一排（1×4 布局），标号用 (A) 格式"""
    lbl_style = ParagraphStyle("lbl", fontName="Songti",
                                fontSize=10.5, alignment=TA_CENTER)
    n = len(labels_and_figs)
    col_w = CONTENT_W / n

    # 图片行
    img_cells = []
    for label, fig_info in labels_and_figs:
        fig_path = base_dir / fig_info["path"] if fig_info else None
        if fig_path and fig_path.exists():
            img_cells.append(_scaled_image(
                str(fig_path), col_w - 4*mm, OPT_FIG_MAX_H, "CENTER",
                orig_w_mm=fig_info.get("width_mm", 0) if fig_info else 0,
                orig_h_mm=fig_info.get("height_mm", 0) if fig_info else 0,
            ))
        else:
            img_cells.append(Paragraph("[图]", lbl_style))

    # 标号行: (A) (B) (C) (D)
    lbl_cells = [Paragraph(f"({label})", lbl_style) for label, _ in labels_and_figs]

    table_data = [img_cells, lbl_cells]
    t = Table(table_data, colWidths=[col_w] * n)
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return t


# ── 构建单道题 ──────────────────────────────────────────────
def _normalize_figures(figures):
    """统一 figures 格式为 dict 列表。兼容旧格式（纯字符串列表）和新格式（dict 列表）。"""
    result = []
    for f in figures:
        if isinstance(f, str):
            result.append({"path": f, "width_mm": 0, "height_mm": 0})
        elif isinstance(f, dict):
            result.append(f)
        else:
            result.append({"path": str(f), "width_mm": 0, "height_mm": 0})
    return result


def add_question(story, q, styles, base_dir, is_solve=False):
    qid = q["id"]
    score = q["score"]
    raw = q["question"]
    figures = _normalize_figures(q.get("figures", []))
    fig_idx = [0]

    prefix = f"{qid}．"
    if is_solve:
        prefix = f"{qid}．（{score} 分）"

    fig_max_w = SOLVE_FIG_MAX_W if is_solve else STEM_FIG_MAX_W
    fig_max_h = SOLVE_FIG_MAX_H if is_solve else STEM_FIG_MAX_H

    # 解答题：先收集到临时列表，再用 KeepTogether 包裹防止分页
    target = [] if is_solve else story

    # ── 检测选项图片模式 ──
    option_fig_pattern = re.compile(r'([A-D])[\.\．]\s*\[图\]')
    all_opt_fig_matches = option_fig_pattern.findall(raw)

    if len(all_opt_fig_matches) >= 2:
        stem_end = re.search(r'[A-D][\.\．]\s*\[图\]', raw)
        stem_text = raw[:stem_end.start()].strip() if stem_end else raw

        _render_text_block(target, stem_text, prefix, figures, fig_idx,
                           fig_max_w, fig_max_h, styles, base_dir)

        labels_and_figs = []
        for label in all_opt_fig_matches:
            fig_info = figures[fig_idx[0]] if fig_idx[0] < len(figures) else None
            fig_idx[0] += 1
            labels_and_figs.append((label, fig_info))

        grid = _build_option_figure_grid(labels_and_figs, base_dir)
        target.append(Spacer(1, 1*mm))
        target.append(grid)

    else:
        # ── 拆分文本和表格段 ──
        parts = _split_text_and_tables(raw)
        has_table = any(p[0] == "table" for p in parts)

        if has_table:
            cur_prefix = prefix
            for seg_type, seg_content in parts:
                if seg_type == "text":
                    _render_text_block(target, seg_content, cur_prefix, figures, fig_idx,
                                       fig_max_w, fig_max_h, styles, base_dir)
                    cur_prefix = ""  # 前缀只用一次
                elif seg_type == "table":
                    target.append(Spacer(1, 2*mm))
                    target.append(_build_md_table(seg_content, styles))
                    target.append(Spacer(1, 2*mm))
        else:
            _render_text_block(target, raw, prefix, figures, fig_idx,
                               fig_max_w, fig_max_h, styles, base_dir)

    # 解答题：用 KeepTogether 包裹题干+图片，避免分页割裂
    if is_solve:
        story.append(KeepTogether(target))

    # 解答题留答题空白
    if is_solve:
        if score <= 5:
            blank_h = 18 * mm
        elif score <= 6:
            blank_h = 22 * mm
        else:
            blank_h = 28 * mm
        story.append(Spacer(1, blank_h))

    story.append(Spacer(1, 2*mm))


def _opt_label_to_paren(text: str) -> str:
    """将选项标号 'A.xxx' / 'A．xxx' 转为 '(A) xxx' 圆括号格式"""
    return re.sub(r'^([A-D])[\.\．]\s*', r'(\1) ', text)


def _is_short_option(text: str) -> bool:
    """判断选项文本是否足够短，可以和其他选项排在同一行。
    短选项：纯数字/短文字/简单公式，不含图片，总长度 ≤ 20 字符。
    """
    # 去掉选项标号: A./B. 或 (A)/(B) 格式
    content = re.sub(r'^\(?[A-D]\)?[\.\．]?\s*', '', text).strip()
    # 含 [图] 的不算短
    if '[图]' in content:
        return False
    # 提取 LaTeX 公式，检查是否简单
    plain = re.sub(r'\$[^$]+\$', 'XX', content)
    return len(plain) <= 20


def _render_text_block(story, text, prefix, figures, fig_idx,
                       fig_max_w, fig_max_h, styles, base_dir):
    """渲染一段文本（可含 [图] 和 LaTeX）"""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    first = bool(prefix)

    # ── 先分离出题干行和选项行 ──
    # 从末尾向前找连续的 A./B./C./D. 行作为选项，要求 ABCD 连续出现
    stem_lines = list(lines)
    option_lines = []

    # 从后往前扫描，收集连续的选项行
    candidate_opts = []
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r'^[A-D][\.\．]', lines[i]):
            candidate_opts.insert(0, (i, lines[i]))
        else:
            break  # 遇到非选项行就停止

    # 验证：选项标号必须连续（A→B→C→D）
    if len(candidate_opts) >= 2:
        labels = [re.match(r'^([A-D])', c[1]).group(1) for c in candidate_opts]
        expected = list("ABCD"[:len(labels)])
        if labels == expected:
            option_lines = [c[1] for c in candidate_opts]
            stem_lines = lines[:candidate_opts[0][0]]

    # ── 渲染题干 ──
    for line in stem_lines:
        fig_segs = re.split(r'(\[图\])', line)

        for seg in fig_segs:
            if seg == '[图]':
                if fig_idx[0] < len(figures):
                    fig_info = figures[fig_idx[0]]
                    fig_idx[0] += 1
                    fp = base_dir / fig_info["path"]
                    if fp.exists():
                        story.append(_scaled_image(
                            str(fp), fig_max_w, fig_max_h,
                            orig_w_mm=fig_info.get("width_mm", 0),
                            orig_h_mm=fig_info.get("height_mm", 0),
                        ))
                    else:
                        story.append(Paragraph(html.escape("[图:文件缺失]"), styles["body_indent"]))
                else:
                    story.append(Paragraph(html.escape("[图]"), styles["body_indent"]))
                continue

            seg = seg.strip()
            if not seg:
                continue

            para_xml = text_to_para_xml(seg)

            if first:
                para_xml = html.escape(prefix) + para_xml
                first = False
                style = styles["body"]
            else:
                style = styles["body_indent"]

            _safe_append(story, para_xml, style)

    # ── 渲染选项 ──
    if option_lines:
        # 转换标号格式: A.xxx → (A) xxx
        option_lines = [_opt_label_to_paren(opt) for opt in option_lines]

        # 检查是否所有选项都足够短 → 可以合并
        all_short = all(_is_short_option(opt) for opt in option_lines)

        if all_short and len(option_lines) == 4:
            # 短选项：用 4 列 Table 均匀分布
            opt_style = ParagraphStyle("opt_inline", fontName="Songti",
                                        fontSize=10.5, leading=16,
                                        alignment=TA_LEFT)
            cells = []
            for opt in option_lines:
                opt_xml = text_to_para_xml(opt)
                try:
                    cells.append(Paragraph(opt_xml, opt_style))
                except Exception:
                    cells.append(Paragraph(html.escape(opt), opt_style))

            col_w = CONTENT_W / 4
            t = Table([cells], colWidths=[col_w] * 4)
            t.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ]))
            story.append(Spacer(1, 0.5*mm))
            story.append(t)
        else:
            # 长选项：每个独占一行
            for opt in option_lines:
                fig_segs = re.split(r'(\[图\])', opt)
                for seg in fig_segs:
                    if seg == '[图]':
                        if fig_idx[0] < len(figures):
                            fig_info = figures[fig_idx[0]]
                            fig_idx[0] += 1
                            fp = base_dir / fig_info["path"]
                            if fp.exists():
                                story.append(_scaled_image(
                                    str(fp), fig_max_w, fig_max_h,
                                    orig_w_mm=fig_info.get("width_mm", 0),
                                    orig_h_mm=fig_info.get("height_mm", 0),
                                ))
                        continue

                    seg = seg.strip()
                    if not seg:
                        continue
                    para_xml = text_to_para_xml(seg)
                    _safe_append(story, para_xml, styles["option"])


def _safe_append(story, para_xml, style):
    try:
        story.append(Paragraph(para_xml, style))
    except Exception:
        fallback = html.escape(re.sub(r'<[^>]+>', '', para_xml))
        story.append(Paragraph(fallback if fallback.strip() else " ", style))


# ── 主构建 ──────────────────────────────────────────────────
def build_exam_pdf(yaml_path: str, output_path: str = None):
    yaml_path = Path(yaml_path)
    base_dir = yaml_path.parent

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if output_path is None:
        output_path = yaml_path.with_suffix(".pdf")
    else:
        output_path = Path(output_path)

    styles = make_styles()
    story = []

    district = data.get("district", "")
    year = data.get("year", "")
    exam_type = data.get("exam_type", "")
    full_score = data.get("full_score", 100)
    duration = data.get("duration_minutes", 120)
    total_q = data.get("total_questions", 28)

    # ── 头部（仿照 2025 真题原卷格式）──
    is_zhenti = "真题" in exam_type or "学业水平" in exam_type

    story.append(Spacer(1, 3*mm))

    # 标题行1
    if is_zhenti:
        title_line1 = f"{year} 年北京市初中学业水平考试"
    else:
        title_line1 = f"{year}北京市{district}初三（下）学期{exam_type}考试"
    story.append(Paragraph(title_line1, styles["title_main"]))

    # 标题行2: "数 学 试 卷"
    if is_zhenti:
        story.append(Paragraph("数学试卷", styles["title_sub"]))
    else:
        story.append(Paragraph("数　学", styles["title_sub"]))

    # ── 考生信息行（仿原卷：姓名____ 准考证号[方框] 考场号[方框] 座位号[方框]）──
    info_label_style = ParagraphStyle("info_lbl", fontName="Songti",
                                       fontSize=10.5, leading=14)
    box_size = 5.5 * mm  # 每个方框大小

    def _make_boxes(n):
        """生成 n 个空方框的 Table"""
        cells = [[""] * n]
        t = Table(cells, colWidths=[box_size] * n, rowHeights=[box_size])
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return t

    info_data = [[
        Paragraph("姓名", info_label_style),
        Paragraph("__________", info_label_style),
        Paragraph("准考证号", info_label_style),
        _make_boxes(8),
        Paragraph("考场号", info_label_style),
        _make_boxes(3),
        Paragraph("座位号", info_label_style),
        _make_boxes(2),
    ]]
    info_table = Table(info_data, colWidths=[
        14*mm, 22*mm, 20*mm, 8*box_size + 2*mm,
        16*mm, 3*box_size + 2*mm, 16*mm, 2*box_size + 2*mm
    ])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 1.5*mm))

    # ── 考生须知（带边框表格，左侧竖排"考生须知"）──
    notice_items = [
        f"1．本试卷共两部分，三道大题，{total_q} 道小题。满分 {full_score} 分。考试时间 {duration} 分钟。",
        "2．在试卷和草稿纸上准确填写姓名、准考证号、考场号和座位号。",
        "3．试题答案一律填涂或书写在答题卡上，在试卷上作答无效。",
        "4．在答题卡上，选择题、作图题用 2B 铅笔作答，其他试题用黑色字迹签字笔作答。",
        "5．考试结束，将本试卷、答题卡和草稿纸一并交回。",
    ]
    # 左列: "考生须知" 竖排
    notice_label_style = ParagraphStyle("notice_label", fontName="Heiti",
                                         fontSize=9, alignment=TA_CENTER,
                                         leading=13)
    label_text = "<br/>".join("考生须知")  # 每字一行 → 竖排
    label_cell = Paragraph(label_text, notice_label_style)

    # 右列: 5条须知
    notice_content = "<br/>".join(html.escape(n) for n in notice_items)
    notice_cell = Paragraph(notice_content, styles["notice"])

    notice_table = Table(
        [[label_cell, notice_cell]],
        colWidths=[10*mm, CONTENT_W - 10*mm],
    )
    notice_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, black),
        ('LINEAFTER', (0, 0), (0, 0), 0.5, black),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('VALIGN', (1, 0), (1, 0), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(notice_table)
    story.append(Spacer(1, 2*mm))

    # ── 分类 ──
    questions = data.get("questions", [])
    choice_qs = [q for q in questions if q["type"] == "选择"]
    fill_qs = [q for q in questions if q["type"] == "填空"]
    solve_qs = [q for q in questions if q["type"] == "解答"]

    choice_total = sum(q["score"] for q in choice_qs)
    fill_total = sum(q["score"] for q in fill_qs)
    solve_total = sum(q["score"] for q in solve_qs)

    # ── 分部标题: 第一部分 选择题 ──
    story.append(Paragraph("第一部分　选择题", styles["part_title"]))

    # 一、选择题
    story.append(Paragraph(
        f"一、选择题（共 {choice_total} 分，每题 {choice_qs[0]['score']} 分）",
        styles["section_title"]
    ))
    first_id = choice_qs[0]["id"]
    last_id = choice_qs[-1]["id"]
    story.append(Paragraph(
        f"第 {first_id}-{last_id} 题均有四个选项，符合题意的选项只有一个。",
        styles["section_note"]
    ))

    for q in choice_qs:
        add_question(story, q, styles, base_dir)

    # ── 分部标题: 第二部分 非选择题 ──
    story.append(Paragraph("第二部分　非选择题", styles["part_title"]))

    # 二、填空题
    story.append(Paragraph(
        f"二、填空题（共 {fill_total} 分，每题 {fill_qs[0]['score']} 分）",
        styles["section_title"]
    ))
    for q in fill_qs:
        add_question(story, q, styles, base_dir)

    # 三、解答题
    solve_score_detail = f"第 {solve_qs[0]['id']}-{solve_qs[-1]['id']} 题，共 {solve_total} 分"
    story.append(Paragraph(
        f"三、解答题（{solve_score_detail}）",
        styles["section_title"]
    ))
    story.append(Paragraph(
        "解答应写出文字说明、演算步骤或证明过程。",
        styles["section_note"]
    ))
    for q in solve_qs:
        add_question(story, q, styles, base_dir, is_solve=True)

    # ── 生成 ──
    page_num = [0]

    total_pages = [0]

    def footer(canvas, doc):
        total_pages[0] += 1
        canvas.saveState()
        canvas.setFont("Songti", 9)
        canvas.drawCentredString(PAGE_W / 2, 10*mm,
                                 f"数学试卷　第 {total_pages[0]} 页")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=MARGIN_LR, rightMargin=MARGIN_LR,
        topMargin=MARGIN_TB, bottomMargin=MARGIN_TB,
        title=f"{year}{district}{exam_type}数学试卷",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)

    fig_count = sum(len(q.get("figures", [])) for q in questions)
    print(f"✅ PDF 已生成: {output_path}")
    print(f"   {len(questions)} 题, {fig_count} 张图, {total_pages[0]} 页")
    return str(output_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 generate-exam-pdf.py <yaml_path> [output_path]")
        sys.exit(1)
    build_exam_pdf(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
