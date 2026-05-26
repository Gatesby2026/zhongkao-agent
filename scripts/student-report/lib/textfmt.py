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


_LATEX_CMDS_AFTER_QUOTE = (
    "text", "mathrm", "mathbf", "mathit", "operatorname", "boldsymbol",
    "frac", "sqrt", "vec", "hat", "bar", "dot", "ddot", "tilde",
    "times", "cdot", "div", "pm", "neq", "leq", "geq", "approx",
    "alpha", "beta", "gamma", "delta", "theta", "lambda", "mu", "pi",
    "rho", "sigma", "tau", "phi", "omega", "Delta", "Omega", "eta",
)


def fix_latex_escape(s: str) -> str:
    """规范化 LLM 输出里的 LaTeX 转义，渲染前必经一道。

    三类常见坑：
      1. JSON 多重转义：`\\\\frac` → `\\frac`（≥2 反斜杠 + 命令前缀字符压回单反斜杠，
         前缀含 [({%&_#$]）
      2. `\\(` `\\)` 误用：LLM 拿它当普通括号；学情报告公式统一 `$...$`，一律还原
      3. 引号替代反斜杠：LLM 偶把 `\\text{}` 写成 `"text{}`（`_{` 后误生成），
         凡 `"<LaTeX 命令名>{` 模式还原 `\\<命令名>{`（白名单内）

    幂等：已规范字符串再过一遍仍原样。
    """
    if not s:
        return s
    s = re.sub(r"\\{2,}(?=[A-Za-z(\[{%&_#$])", r"\\", s)
    # `\[ ... \]` 是 LaTeX 显示模式定界符；md-to-pdf KaTeX 支持 $$...$$ 显示
    # 模式但不识别 `\[/\]`。审核员也常把它当未闭合公式 → 统一换 $$
    s = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", s, flags=re.S)
    s = re.sub(r"\${3,}", "$$", s)              # 折叠 LLM 把 \[\] 嵌套在 $...$ 造成的 $$$
    # LLM 偶把 `\text{V}` 错写成 `\[text{V}]`（`\[` 替代 `\`、`]` 替代 `}`）。
    # 命中白名单命令名才转，避免误伤真正的 display math `\[...\]`（上面已先处理）
    cmd_alt = "|".join(_LATEX_CMDS_AFTER_QUOTE)
    s = re.sub(r"\\\[(" + cmd_alt + r")\{([^{}]*)\}\]", r"\\\1{\2}", s)
    s = re.sub(r"\\\[(" + cmd_alt + r")\]", r"\\\1", s)
    # `\[times 10^{-3}` 这类后跟空格/数字（不带 {} 也无 ]）→ `\times`
    s = re.sub(r"\\\[(" + cmd_alt + r")(?=[\s\d])", r"\\\1", s)
    # `\(` `\)` 误用：还原成普通括号（同一原因，避免与 KaTeX 行内定界混淆）
    s = s.replace(r"\(", "(").replace(r"\)", ")")
    pat = r'"(' + "|".join(_LATEX_CMDS_AFTER_QUOTE) + r')(?=[\s{])'
    s = re.sub(pat, r"\\\1", s)
    return s


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
