# knowledge-base/

本目录的**结构规范、五域划分、数据契约与质量门禁**的唯一真相在：

→ [`docs/architecture/KB-LAYOUT.md`](../docs/architecture/KB-LAYOUT.md)

配套规范：
- [`docs/specs/KB-MODULE-ID-SPEC.md`](../docs/specs/KB-MODULE-ID-SPEC.md) — 模块标识（pedagogy 跨层 join 键）
- [`docs/specs/EXAM-SLUG-SPEC.md`](../docs/specs/EXAM-SLUG-SPEC.md) — 试卷标识

门禁脚本（改动后请跑）：
- `python3 scripts/knowledge-base/kb_lint.py` — module-id 合规 + 三层覆盖 + meta 完整
- `python3 scripts/exam-ocr/qc_report.py <staging>` — 单卷结构化质量

> 不要在此另写结构说明；一切以上述 canonical 文档为准（避免双真相）。
