"""KB-MODULE-ID-SPEC 的程序事实标准：26 模块全集（kebab，subject 命名空间）。

任何脚本/数据与本表冲突 → 改数据或本表，不另立。
见 docs/specs/KB-MODULE-ID-SPEC.md。
"""
from __future__ import annotations

import re

MODULE_IDS: dict[str, set[str]] = {
    "math": {
        "numbers-and-expressions", "equations-and-inequalities", "functions",
        "triangles", "quadrilaterals", "circles",
        "geometry-comprehensive", "statistics-and-probability",
    },
    "chinese": {
        "basic-usage", "classical-reading", "masterpiece-reading",
        "modern-reading", "writing",
    },
    "english": {
        "grammar-basics", "grammar-advanced", "cloze", "reading", "writing",
    },
    "physics": {
        "sound-light-heat", "mechanics", "electricity",
        "experiments", "calculation",
    },
    "politics": {
        "moral-law", "national-conditions", "current-affairs",
        "answer-techniques",
    },
}

ALL = {(s, m) for s, ms in MODULE_IDS.items() for m in ms}


def camel_to_kebab(s: str) -> str:
    """numbersAndExpressions → numbers-and-expressions（单词形不变）。"""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", s).lower()


def is_valid(subject: str, module_id: str) -> bool:
    return module_id in MODULE_IDS.get(subject, set())
