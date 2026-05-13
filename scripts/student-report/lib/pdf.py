"""Markdown → HTML → PDF（Chrome --headless=new + KaTeX，复用既有 skill）"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

try:
    import markdown as md_lib
except ImportError:
    print("pip install markdown", file=sys.stderr); sys.exit(1)


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

HTML_SHELL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{
    delimiters:[
      {left:'$$',right:'$$',display:true},
      {left:'$',right:'$',display:false}
    ],
    throwOnError:false
  });"></script>
<style>
@page { size: A4; margin: 16mm 14mm; }
body {
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 10.5pt; line-height: 1.6; max-width: 760px; margin: 0 auto; color: #222;
}
h1 { font-size: 19pt; border-bottom: 2px solid #2563eb; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 14pt; color: #1e40af; border-left: 4px solid #2563eb;
     padding-left: 10px; margin-top: 22px; page-break-after: avoid; }
h3 { font-size: 12pt; color: #1e3a8a; margin-top: 16px; page-break-after: avoid; }
h4 { font-size: 11pt; color: #444; margin-top: 12px; margin-bottom: 6px; page-break-after: avoid; }
p { margin: 6px 0; }
blockquote {
  border-left: 3px solid #c7d2fe; background: #eef2ff;
  padding: 6px 12px; margin: 10px 0; color: #1f2937; font-size: 10pt;
}
table {
  border-collapse: collapse; width: 100%; margin: 10px 0;
  font-size: 10pt; page-break-inside: avoid;
}
th, td { border: 1px solid #d1d5db; padding: 4px 8px; text-align: left; vertical-align: top; }
th { background: #eef2ff; font-weight: 600; }
code { font-family: ui-monospace, Menlo, Consolas, monospace;
       background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 9.5pt; }
ul, ol { padding-left: 22px; margin: 6px 0; }
li { margin: 3px 0; }
hr { border: none; border-top: 1px solid #d1d5db; margin: 18px 0; }
strong { color: #b91c1c; }
em { color: #2563eb; font-style: normal; }
.katex { font-size: 1em; }
</style>
</head>
<body>
__BODY__
</body>
</html>
"""


def md_to_pdf(md_text: str, pdf_out: Path, html_out: Path | None = None, title: str = "学情报告"):
    """Markdown 文本 → PDF 文件。"""
    body = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "attr_list", "sane_lists"],
    )
    html = HTML_SHELL.replace("__BODY__", body).replace("__TITLE__", title)

    if html_out is None:
        html_out = pdf_out.with_suffix(".html")
    html_out.write_text(html, encoding="utf-8")

    pdf_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        CHROME, "--headless=new", "--disable-gpu",
        "--no-pdf-header-footer", "--print-to-pdf-no-header",
        "--virtual-time-budget=20000",
        f"--print-to-pdf={pdf_out}",
        f"file://{html_out.resolve()}",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not pdf_out.exists():
        raise RuntimeError(f"Chrome PDF 失败：{r.stderr[-500:]}")
    return pdf_out
