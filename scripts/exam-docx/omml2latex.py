"""OMML（Office Math Markup Language）→ LaTeX 转换器（纯 Python，零外部依赖）。

中考数学公式覆盖的 15 个 OMML 标签：
  m:t      文字内容
  m:r      run（包装）
  m:e      element 内容
  m:f / m:num / m:den           分数
  m:sSub / m:sub                下标
  m:sSup / m:sup                上标
  m:sSubSup                    上下标同时
  m:rad / m:deg / m:degHide / m:e   根号
  m:d / m:begChr / m:endChr     定界符（括号）
  m:m / m:mr / m:mc            矩阵
  m:nary                        求和/积分
  m:bar                         顶横
  m:acc                         重音（向量等）
  m:func / m:fName              函数名
  m:limLow / m:limUpp           lim 下/上标

用法：
  from omml2latex import omml_to_latex
  latex = omml_to_latex(omml_element)  # 输入 ElementTree.Element (<m:oMath>)
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

# OMML 命名空间
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"m": M_NS, "w": W_NS}


def _local(tag: str) -> str:
    """剥离命名空间前缀，返回本地标签名。"""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(el: ET.Element) -> str:
    """递归提取 m:t 文字（仅文本，不带任何 LaTeX 包装）。"""
    parts = []
    for c in el.iter(f"{{{M_NS}}}t"):
        if c.text:
            parts.append(c.text)
    return "".join(parts)


def _children_m(el: ET.Element) -> list[ET.Element]:
    """返回 el 的所有 m:* 子节点（跳过文档属性节点）。"""
    return [c for c in el if c.tag.startswith(f"{{{M_NS}}}")
            and _local(c.tag) not in ("ctrlPr", "fPr", "radPr", "sSubPr",
                                       "sSupPr", "sSubSupPr", "dPr", "mPr",
                                       "naryPr", "barPr", "accPr", "funcPr",
                                       "limLowPr", "limUppPr", "rPr", "mcPr",
                                       "mcs", "count", "type")]


def _convert(el: ET.Element) -> str:
    """递归把 OMML element 转为 LaTeX 片段（不带 $...$ 外层）。"""
    tag = _local(el.tag)

    if tag in ("oMath", "oMathPara"):
        return "".join(_convert(c) for c in _children_m(el))

    if tag == "r":
        # m:r 含 m:t —— 直接拼接文字（不包 \text{}，因为运行时已是数学环境）
        return "".join(_convert(c) for c in _children_m(el) if _local(c.tag) == "t") \
               or _text(el)

    if tag == "t":
        return el.text or ""

    if tag == "e":
        return "".join(_convert(c) for c in _children_m(el))

    # 分数 m:f { m:num, m:den }
    if tag == "f":
        num = _find_part(el, "num")
        den = _find_part(el, "den")
        return f"\\frac{{{num}}}{{{den}}}"

    # 下标 m:sSub { m:e, m:sub }
    if tag == "sSub":
        base = _find_part(el, "e")
        sub = _find_part(el, "sub")
        return f"{{{base}}}_{{{sub}}}"

    # 上标 m:sSup { m:e, m:sup }
    if tag == "sSup":
        base = _find_part(el, "e")
        sup = _find_part(el, "sup")
        return f"{{{base}}}^{{{sup}}}"

    # 上下标 m:sSubSup { m:e, m:sub, m:sup }
    if tag == "sSubSup":
        base = _find_part(el, "e")
        sub = _find_part(el, "sub")
        sup = _find_part(el, "sup")
        return f"{{{base}}}_{{{sub}}}^{{{sup}}}"

    # 根号 m:rad { m:deg, m:e } —— degHide 控制是否显示根指数
    if tag == "rad":
        e = _find_part(el, "e")
        deg = _find_part(el, "deg")
        # 检查 degHide
        deg_hide_el = el.find(f"{{{M_NS}}}radPr/{{{M_NS}}}degHide")
        hide = deg_hide_el is not None and deg_hide_el.get(f"{{{M_NS}}}val", "1") in ("1", "true")
        if hide or not deg:
            return f"\\sqrt{{{e}}}"
        return f"\\sqrt[{deg}]{{{e}}}"

    # 定界符 m:d { m:e, [m:begChr, m:endChr] }
    if tag == "d":
        # 找括号字符
        d_pr = el.find(f"{{{M_NS}}}dPr")
        beg, end = "(", ")"
        if d_pr is not None:
            b = d_pr.find(f"{{{M_NS}}}begChr")
            e_ = d_pr.find(f"{{{M_NS}}}endChr")
            if b is not None: beg = b.get(f"{{{M_NS}}}val", "(")
            if e_ is not None: end = e_.get(f"{{{M_NS}}}val", ")")
        # m:d 内部可能有多个 m:e (用 sepChr 分隔)
        es = el.findall(f"{{{M_NS}}}e")
        sep_el = el.find(f"{{{M_NS}}}dPr/{{{M_NS}}}sepChr")
        sep = sep_el.get(f"{{{M_NS}}}val", "|") if sep_el is not None else ","
        contents = sep.join("".join(_convert(c) for c in _children_m(e)) for e in es)
        # LaTeX: \left BEG ... \right END
        beg_tex = _bracket_to_tex(beg, left=True)
        end_tex = _bracket_to_tex(end, left=False)
        return f"\\left{beg_tex}{contents}\\right{end_tex}"

    # 矩阵 m:m { m:mr+ { m:e+ } }
    if tag == "m":
        rows = []
        for mr in el.findall(f"{{{M_NS}}}mr"):
            cells = ["".join(_convert(c) for c in _children_m(e))
                     for e in mr.findall(f"{{{M_NS}}}e")]
            rows.append(" & ".join(cells))
        body = " \\\\ ".join(rows)
        return f"\\begin{{matrix}} {body} \\end{{matrix}}"

    # 求和/积分 m:nary { m:naryPr, m:sub, m:sup, m:e } —— 类似 sSubSup 但有 operator
    if tag == "nary":
        nary_pr = el.find(f"{{{M_NS}}}naryPr")
        op = "\\sum"
        if nary_pr is not None:
            chr_el = nary_pr.find(f"{{{M_NS}}}chr")
            if chr_el is not None:
                ch = chr_el.get(f"{{{M_NS}}}val", "∑")
                op = {"∑": "\\sum", "∏": "\\prod", "∫": "\\int",
                      "∮": "\\oint"}.get(ch, ch)
        sub = _find_part(el, "sub")
        sup = _find_part(el, "sup")
        e = _find_part(el, "e")
        s = op
        if sub: s += f"_{{{sub}}}"
        if sup: s += f"^{{{sup}}}"
        if e: s += f" {e}"
        return s

    # 上下标的简化形式（OMML 中也可见 m:sub / m:sup 直接出现）
    if tag in ("sub", "sup"):
        # 通常作为父节点的一部分被消费，但若独立出现，转 _{} / ^{}
        inner = "".join(_convert(c) for c in _children_m(el))
        return f"_{{{inner}}}" if tag == "sub" else f"^{{{inner}}}"

    if tag == "deg":
        return "".join(_convert(c) for c in _children_m(el))
    if tag == "num":
        return "".join(_convert(c) for c in _children_m(el))
    if tag == "den":
        return "".join(_convert(c) for c in _children_m(el))

    # 顶横 m:bar
    if tag == "bar":
        e = _find_part(el, "e")
        return f"\\overline{{{e}}}"

    # 重音 m:acc（向量箭头）
    if tag == "acc":
        e = _find_part(el, "e")
        acc_pr = el.find(f"{{{M_NS}}}accPr")
        acc_chr = "→"
        if acc_pr is not None:
            ch = acc_pr.find(f"{{{M_NS}}}chr")
            if ch is not None:
                acc_chr = ch.get(f"{{{M_NS}}}val", "→")
        mapper = {"→": "\\vec", "^": "\\hat", "‾": "\\overline",
                  "˙": "\\dot", "¨": "\\ddot"}
        cmd = mapper.get(acc_chr, "\\vec")
        return f"{cmd}{{{e}}}"

    # 函数 m:func { m:fName, m:e } — sin, cos, log 等
    if tag == "func":
        name_el = el.find(f"{{{M_NS}}}fName")
        e = _find_part(el, "e")
        name = "".join(_convert(c) for c in _children_m(name_el)) if name_el is not None else ""
        # 标准函数名前加 \\
        std_funcs = {"sin", "cos", "tan", "log", "ln", "exp", "lim",
                     "max", "min", "arcsin", "arccos", "arctan"}
        if name.strip().lower() in std_funcs:
            name = "\\" + name.strip().lower()
        return f"{name} {e}"

    # lim 下标 / 上标
    if tag in ("limLow", "limUpp"):
        e = _find_part(el, "e")
        lim_part = _find_part(el, "lim")
        if tag == "limLow":
            return f"{e}_{{{lim_part}}}"
        return f"{e}^{{{lim_part}}}"

    # 默认：递归处理子节点
    return "".join(_convert(c) for c in _children_m(el))


def _find_part(parent: ET.Element, child_tag: str) -> str:
    """找到指定 OMML 子标签并转换为 LaTeX 字符串。"""
    el = parent.find(f"{{{M_NS}}}{child_tag}")
    if el is None:
        return ""
    return "".join(_convert(c) for c in _children_m(el)) or _text(el)


def _bracket_to_tex(ch: str, left: bool) -> str:
    """把括号字符映射为 LaTeX 命令。"""
    mapping = {
        "(": "(", ")": ")",
        "[": "[", "]": "]",
        "{": "\\{", "}": "\\}",
        "|": "|",
        "⟨": "\\langle", "⟩": "\\rangle",
        "‖": "\\|",
    }
    return mapping.get(ch, ch if ch else (".") )


def omml_to_latex(omml_el: ET.Element, inline: bool = True) -> str:
    """对外接口：OMML element → LaTeX 字符串（含 `$...$` 或 `$$...$$` 包裹）。"""
    body = _convert(omml_el).strip()
    if not body:
        return ""
    if inline:
        return f"${body}$"
    return f"$${body}$$"


# 自测
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: omml2latex.py <docx_file> [N=3]", file=sys.stderr)
        sys.exit(1)
    import zipfile
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    with zipfile.ZipFile(sys.argv[1]) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    root = ET.fromstring(xml)
    omaths = root.iter(f"{{{M_NS}}}oMath")
    count = 0
    for om in omaths:
        latex = omml_to_latex(om)
        text = _text(om)
        print(f"[{count}] text={text!r} → latex={latex}")
        count += 1
        if count >= n: break
