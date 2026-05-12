# scripts/knowledge-base/ — 知识库构建流水线

把原始教辅/试卷（docx、PDF）转成项目能用的结构化 YAML，并做质量检查。

## 脚本一览

| 脚本 | 作用 |
|------|------|
| `docx-pipeline.py` | docx 教辅 → 中间结构（含 OCR 公式） |
| `docx-to-yaml.py` | 中间结构 → 题库 YAML |
| `pdf-to-questionbank.py` | PDF 教辅 → 题库 YAML（含 toc.yaml 章节映射） |
| `generate-exam-pdf.py` | 题库 YAML → 可打印 PDF 试卷 |
| `validate-exam-structure.py` | 题库 YAML 结构校验（必填字段、ID 唯一性等） |
| `exam-deep-quality-check.py` | 深度质量审核（公式合法性、知识点标签、难度分布） |
| `quark_batch_save.py` | 夸克网盘教辅资源批量转存 |
| `crop_black_borders.py` | iPhone 截屏黑边裁剪工具 |

## 输出位置

题库 YAML：`../../knowledge-base/question-banks/<科目>/<book_id>/`
（按 `单元/p<book_page>-课时名.yaml` 分层组织，规则见各 book 内 `toc.yaml`）

## 运行时缓存（gitignored）

- `.ocr-cache/ocr-results.json` — 公式图片 OCR 缓存
- `quark_done_ids.json` / `quark_save_log.json` — 夸克转存状态

## 与其他流水线的关系

- 试卷 OCR：`../exam-ocr/`
- 答题卡 OCR：`../answer-card-ocr/`
- 学情报告：`../student-report/`
