# scripts/student-report/ — 学情分析报告生成

把 OCR 后的试卷 + 学生答题卡 + 小分表 → 一份带"原题/标答/学生答/失分分析/提分建议"的 PDF 报告。

## 脚本

| 脚本 | 作用 |
|------|------|
| `build-student-analysis-report.py` | 主流程：读题库 final.json + 答题卡 OCR + 小分 → 渲染 HTML → Chrome headless 出 PDF |

## 输入依赖

| 来源 | 路径 |
|------|------|
| 试卷题目（结构化） | `../../admin/data/<集合>/processed/<科目>/structured-cloud/final.json` |
| 学生答题卡 OCR | `../../knowledge-original/<集合>/answer-card-ocr/IMG_*.md` |
| 学生小分表 | `../../knowledge-original/<集合>/*.xlsx` |

## 输出

| 文件 | 路径 |
|------|------|
| 渲染 HTML | `../../learning situation/report-render/<学生>_<集合>_<科目>.html` |
| 终态 PDF | `../../learning situation/<学生>_<集合>_<科目>_失分分析与提分建议.pdf` |

> ⚠️ `learning situation/` 与 `students/` 在仓库根目录 gitignore，含真实姓名/成绩，**不进 GitHub**。

## 已用记录

- 贾小淇 · 2026 朝阳一模 · 数学 / 语文 / 物理 — 三份分析报告均由该脚本（或同等流程）生成

## 上游 / 下游

- 上游：`../exam-ocr/`（试卷 OCR）+ `../answer-card-ocr/`（答题卡 OCR）
- 下游：手动发给家长（PDF）
