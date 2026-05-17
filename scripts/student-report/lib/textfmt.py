"""LaTeX → Unicode 文本规整。

md-to-pdf skill 用 Python markdown，无 MathJax/KaTeX，`$...$` 原样显示。
学生看不懂 LaTeX 源码，故在报告侧把常见物理/数学 LaTeX 规则替换成 Unicode。
覆盖中考物理 ~95% 公式场景；复杂场景退化为去壳显示（可读优先）。
"""
from __future__ import annotations

import re

_SUP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")

_GREEK = {
    r"\\alpha": "α", r"\\beta": "β", r"\\gamma": "γ", r"\\delta": "δ",
    r"\\theta": "θ", r"\\lambda": "λ", r"\\mu": "μ", r"\\pi": "π",
    r"\\rho": "ρ", r"\\sigma": "σ", r"\\tau": "τ", r"\\phi": "φ",
    r"\\omega": "ω", r"\\Delta": "Δ", r"\\Omega": "Ω", r"\\eta": "η",
}
_CMD = {
    r"\\times": "×", r"\\cdot": "·", r"\\div": "÷", r"\\pm": "±",
    r"\\approx": "≈", r"\\neq": "≠", r"\\leq": "≤", r"\\geq": "≥",
    r"\\le": "≤", r"\\ge": "≥", r"\\propto": "∝", r"\\infty": "∞",
    r"\\circ": "°", r"\\%": "%", r"\\,": " ", r"\\;": " ", r"\\!": "",
    r"\\quad": "  ", r"\\qquad": "    ", r"\\ ": " ",
}


def _sup(s: str) -> str:
    return s.translate(_SUP) if all(c in "0123456789+-=()n" for c in s) else f"^{s}"


def _sub(s: str) -> str:
    return s.translate(_SUB) if all(c in "0123456789+-=()" for c in s) else f"_{s}"


def _delatex(t: str) -> str:
    """对一段 LaTeX 片段（不含 $）做替换。"""
    # \mathrm{...} \text{...} \mathbf{...} → 内容
    t = re.sub(r"\\(?:mathrm|text|mathbf|rm|operatorname)\s*\{([^{}]*)\}",
               r"\1", t)
    # \frac{a}{b} → (a)/(b)（简化）
    t = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", t)
    # \sqrt{x} → √(x)
    t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", t)
    # 希腊字母 / 命令
    for k, v in {**_GREEK, **_CMD}.items():
        t = re.sub(k + r"(?![a-zA-Z])", v, t)
    # 上标 ^{...} / ^x
    t = re.sub(r"\^\{([^{}]*)\}", lambda m: _sup(m.group(1)), t)
    t = re.sub(r"\^(\w)", lambda m: _sup(m.group(1)), t)
    # 下标 _{...} / _x
    t = re.sub(r"_\{([^{}]*)\}", lambda m: _sub(m.group(1)), t)
    t = re.sub(r"_(\w)", lambda m: _sub(m.group(1)), t)
    # 残余花括号 / 反斜杠命令去壳
    t = re.sub(r"\\[a-zA-Z]+", "", t)
    t = t.replace("{", "").replace("}", "")
    # 多余空格收敛（~ 是 LaTeX 不断行空格）
    t = t.replace("~", " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def latex_to_unicode(text: str) -> str:
    """把字符串里所有 $...$ / $$...$$ / \\(...\\) 数学段转 Unicode。

    非数学段原样保留。无 $ 包裹但含裸 LaTeX 命令的也尽力清理。
    """
    if not text:
        return text

    def _seg(m):
        inner = m.group(1) or m.group(2) or m.group(3) or ""
        return _delatex(inner)

    # $$...$$ | $...$ | \(...\)
    text = re.sub(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)",
                  _seg, text, flags=re.S)
    # 兜底：仍残留的裸 LaTeX 命令（如 OCR 文本里没加 $）
    if "\\" in text:
        text = _delatex(text)
    return text
