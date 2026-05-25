#!/usr/bin/env python3
"""docx 里 MathType OLE 公式 → LaTeX list (有序、按文档出现顺序)。

链路（d2t Java pipeline，100% 准确率）：
  1. docx2tex (Java + XProc + transpect XSLT chain) → hub XML (含 <inlineequation>+MathML)
  2. Python re.findall 抽所有 <inlineequation> 内 MathML 块（按文档顺序）
  3. Python `mathml-to-latex`: MathML → LaTeX

为什么不走 jure/mathtype_to_mathml gem (纯 Ruby)：
  - 加速 6× 但 XSLT 覆盖不全：丢 \\text{max} 文本下标、丢 Ω 单位
  - transpect 的 XSLT (d2t 内嵌的) 才是 prod-grade，覆盖物理常见公式 100%

依赖：
  - docx2tex (https://github.com/transpect/docx2tex) - 安装在 D2T_HOME=/tmp/d2t/docx2tex
  - Python: pip install mathml-to-latex

慢但**只跑一次**：每区 ~5 min × 14 区 ≈ 70 min；之后 formulas.json cache 命中，重抽几秒。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

D2T_HOME = Path(os.environ.get("D2T_HOME", "/tmp/d2t/docx2tex"))
# d2t 把 OLE 公式输出为两种 hub 元素：
#   - <inlineequation role="mtef" condition="ole">  （行内公式，绝大多数）
#   - <equation role="mtef" condition="ole">          （独占段落的 block 公式）
# 必须两种都抓，否则 counter 会跟 walker 的 99 个 <w:object> 错位
EQ_RE = re.compile(
    r'<(?:inline)?equation[^>]*condition="ole"[^>]*>(.*?)</(?:inline)?equation>',
    re.DOTALL)


def _run_d2t(docx_path: Path, out_dir: Path) -> Path:
    """调 docx2tex，返回 hub xml 路径。"""
    if not (D2T_HOME / "d2t").exists():
        raise RuntimeError(
            f"docx2tex 未安装在 {D2T_HOME}（环境变量 D2T_HOME 覆盖路径）。"
            "下载: https://github.com/transpect/docx2tex/releases/latest")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_docx = out_dir / "input.docx"
    import shutil
    if tmp_docx.exists():
        tmp_docx.unlink()
    shutil.copy(docx_path, tmp_docx)
    result = subprocess.run(
        [str(D2T_HOME / "d2t"), "-m", "ole", "-o", str(out_dir), str(tmp_docx)],
        capture_output=True, text=True)
    hub_xml = out_dir / "input.xml"
    if not hub_xml.exists():
        raise RuntimeError(
            f"d2t 失败 - hub xml 未生成。stderr:\n{result.stderr[:500]}")
    return hub_xml


def _mathml_to_latex_block(mml_xml: str) -> str:
    """单条 MathML XML → LaTeX 字符串。"""
    from mathml_to_latex.converter import MathMLToLaTeX
    # mathml-to-latex 期望默认 namespace
    normalized = mml_xml.replace('mml:', '').replace(
        ' xmlns:mml=', ' xmlns=')
    try:
        return MathMLToLaTeX().convert(normalized).strip()
    except Exception as e:
        return f"[公式转换失败:{e}]"


def extract_formulas(docx_path: Path, cache_dir: Path,
                     force: bool = False) -> list[str]:
    """主入口：返回 docx 内所有 MathType OLE 公式的 LaTeX 列表（按出现顺序）。
    缓存到 cache_dir/formulas.json，第二次调用直接读缓存。
    """
    cache_file = cache_dir / "formulas.json"
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text(encoding="utf-8"))

    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="d2t-") as tmp:
        hub_xml = _run_d2t(docx_path, Path(tmp))
        text = hub_xml.read_text(encoding="utf-8")

    blocks = EQ_RE.findall(text)
    formulas = [_mathml_to_latex_block(b) for b in blocks]
    cache_file.write_text(
        json.dumps(formulas, ensure_ascii=False, indent=2), encoding="utf-8")
    return formulas


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("docx", type=Path)
    ap.add_argument("--cache-dir", "-c", type=Path, required=True)
    ap.add_argument("--force", "-f", action="store_true")
    a = ap.parse_args()
    formulas = extract_formulas(a.docx, a.cache_dir, force=a.force)
    print(f"✅ {len(formulas)} 个 OLE 公式 → {a.cache_dir / 'formulas.json'}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
