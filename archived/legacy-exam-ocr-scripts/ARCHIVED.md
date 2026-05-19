# Legacy exam-ocr 脚本（已退役）

归档于 2026-05-18。这些是 **v2 流水线（`scripts/exam-ocr/ocr_paper.py`）之前**的草稿/旧链路，
已被取代，仅作历史参考——**不保证可运行**（如 `bulk_pipeline.py` 仍 `import ocr_paper`，
而 ocr_paper 留在 `scripts/exam-ocr/`，路径已断）。

| 文件 | 原职责 | 取代者 |
|---|---|---|
| `bulk_pipeline.py` | 旧批量端到端（产出 `data/exams/<slug>/paper.json+answer-key.json`） | `ocr_paper.py` → `enrich_to_mock_exam.py` |
| `final_to_paper.py` | final.json → paper.json（旧格式） | 无（旧格式已废，见 `archived/legacy-data-exams/`） |
| `extract_answer_key.py` | 答案页 OCR → answer-key.json | 已并入 `ocr_paper.py` v2 的答案抽取步骤 |
| `structure-exam-final.py` | 早期结构化草稿（默认 `data/chaoyang-2026-yimo`） | `structure_pages_v2`（在 ocr_paper.py） |
| `segment-exam-draft.py` | 早期切题草稿 | `split_by_question_number`（在 ocr_paper.py） |
| `ocr-paddle-exam.py` | 早期 paddle OCR 草稿 | `ocr_paper.py` + `paddle_layout.py` |

现行链路与目录约定见 `docs/specs/REPO-LAYOUT.md`。
