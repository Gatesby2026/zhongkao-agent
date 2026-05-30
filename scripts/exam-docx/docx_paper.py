"""Backward-compat shim: `import docx_paper as dp` 重定向到 math_docx_paper。

历史背景：原始 docx_paper.py（数学路线 v1）在 fb93884 提交里被重命名为
math_docx_paper.py 与 chinese/english/physics/politics_docx_paper.py 命名对齐。
但 chinese/english/physics/politics_docx_paper.py 都用 `import docx_paper as dp`
依赖底层 _walk_run / _extract_image / _walk_table / _load_docx 实现，重命名后
4 个脚本全部 broken（ModuleNotFoundError），二模 docx 路线无法启动。

最小侵入修复：导出 math_docx_paper 全部公开 + 私有符号。这样：
- 一模/二模 docx 流水线立刻恢复
- 不需要修改 4 个上层脚本
- math_docx_paper.py 仍然是底层"单一真相"
"""
from math_docx_paper import *  # noqa: F401,F403
# math_docx_paper 内大量私有 _xxx 函数（_walk_run 等）`*` 默认不导出，
# 但 chinese/english/etc 用 dp._walk_run 形式访问，需要把模块本身的 attr
# 全 link 过来：
import math_docx_paper as _md
import sys as _sys
_sys.modules[__name__].__dict__.update(
    {k: v for k, v in _md.__dict__.items() if not k.startswith("__")}
)
