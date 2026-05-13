"""模板渲染：把 LLM 分析结果 + 输入数据 → Markdown 报告。"""
from __future__ import annotations
import datetime
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    print("pip install jinja2", file=sys.stderr); sys.exit(1)


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
    trim_blocks=False,
    lstrip_blocks=False,
    keep_trailing_newline=True,
)


def render_report(context: dict) -> str:
    tpl = _env.get_template("report.md.j2")
    return tpl.render(**context, generated_at=datetime.date.today().isoformat())


TYPE_LABEL = {
    "choice": "单选",
    "multi_choice": "多选",
    "fill_blank": "填空",
    "calculation": "计算",
    "experiment": "实验探究",
    "essay": "大题",
}
