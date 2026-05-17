#!/usr/bin/env python3
"""DEPRECATED：本脚本已迁移到 tools/exam-review/

请改用：
    tools/exam-review/exam-review <args>
    # 或 PATH 加入后：exam-review <args>

为向后兼容保留此 shim，自动转发。
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NEW_TOOL = REPO_ROOT / "tools" / "exam-review" / "exam_review.py"

if not NEW_TOOL.exists():
    print(f"❌ 找不到新工具：{NEW_TOOL}", file=sys.stderr)
    sys.exit(1)

print(f"⚠️  本脚本已迁移到 tools/exam-review/，请用 `exam-review`（详见 tools/exam-review/README.md）",
      file=sys.stderr)
os.execv(sys.executable, [sys.executable, str(NEW_TOOL)] + sys.argv[1:])
