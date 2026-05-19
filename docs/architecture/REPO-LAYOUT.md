# REPO-LAYOUT — 仓库目录拓扑与数据流

> 状态：v1.1（2026-05-18）· 阶段 0-3 已执行；阶段 4 + students/_web 迁移 deferred
> 配套：[KB-LAYOUT.md](./KB-LAYOUT.md)、[../specs/EXAM-SLUG-SPEC.md](../specs/EXAM-SLUG-SPEC.md)
>
> **决策已定**：① data/exams + data/zhongkao.db = legacy（已归档）② 仅 `web/`
> 在用，`admin/`+`miniprogram/`+`backend/` 半成品（已删）③ 交付物收口 `out/`（已改）。

## 1. 三层铁律（数据分层的根本约束）

| 层 | 目录 | 谁写 | 谁读 | 约束 |
|---|---|---|---|---|
| **原始 raw** | `knowledge-original/` | 抓取/扫描工具 | 流水线只读 | 只读，永不在此产出派生件；gitignore（36G） |
| **派生 derived** | `knowledge-base/` | 流水线脚本 | enrich/报告/UI | 一切结构化产物的唯一真相；入 git |
| **交付 deliverable** | `out/`（目标态） | 报告/渲染脚本 | 人/学生 | 最终给人的文件；隐私部分 gitignore |

> ✅ 已收口：交付物统一 `out/`（`out/student-reports/<id>/<slug>/report.{md,pdf}` +
> `out/papers/<slug>.pdf`）。旧 `learning situation/` 已迁入 `out/student-reports/jiaxiaoqi/_legacy/` 并删除。
> 例外：`students/_web/`（server 运行时）暂留——live 服务器硬编码 `WEB_STUDENTS`，迁移待后续与部署一并处理。

## 2. 数据流（端到端）

```
knowledge-original/<series>/<round>/<region>/<subject>/images/page-*.png   [raw]
  │  scripts/exam-ocr/ocr_paper.py   (OCR + 结构化, 见 skill_exam_image_to_kb_yaml)
  ▼
knowledge-base/exams/_staging/<subject>/<slug>/                            [derived staging]
  ├─ pages/  layout-cache/  structured-cloud/final.json+md  (figures 临时)
  │  scripts/exam-ocr/extract_figures.py     (paddle 图形)
  │  scripts/exam-ocr/qc_report.py           (质量门禁)
  │  scripts/knowledge-base/enrich_to_mock_exam.py（figures 复制到最终件旁）
  ▼
knowledge-base/exams/mock/<subject>/beijing/<slug>.yaml                    [最终知识库件]
  （真题在 exams/zhenti/，真题分析在 exams/analysis/；详见 KB-LAYOUT.md）
  │
  │  ＋ students/<name>/<slug>/{answer-card.json, scores.json, student.json}  [学生数据, 私]
  ▼  scripts/student-report/build_report.py   (三方按 slug join)
out/student-reports/<name>/<slug>/report.{md,pdf}                          [交付物, 目标态]
```

slug 对齐键见 EXAM-SLUG-SPEC；`paths.py:derive_out_dir()` 为唯一映射真相。

## 3. 目录职责总表

### 数据
| 目录 | 职责 | git | 备注 |
|---|---|---|---|
| `knowledge-original/` | 原始扫描/抓取件（images/source.html/urls.txt/cloud-ocr） | ignore | raw 层，只读 |
| `knowledge-base/` | 结构化派生件 + 知识库 | track | derived 层；唯一真相 |
| `knowledge-base/exams/` | 试卷域（主力，3500+ 文件）：`mock/` 模拟 · `zhenti/` 真题 · `analysis/` 真题分析 · `_staging/` 派生中间件 | track | `_staging/**/pages\|layout-cache` 为可重生缓存→gitignore；只 track `structured-cloud/`+`figures/`+`.yaml` |
| `knowledge-base/prep/question-banks/` | 教辅题库（阶段 2 已并入 prep/） | track | 子域 |
| `knowledge-base/`{pedagogy,prep,policies,admission} | 教研标准/备考/政策/升学域（阶段 2 已域化重组，原 13 平铺目录已正名归并） | track | 详见 **KB-LAYOUT.md**（KB 内部结构的唯一真相） |
| `students/` | 学生答题卡+小分（真实姓名/成绩） | ignore | 私；`<name>/<slug>/`；`_web/`=server 运行时（暂留） |
| `data/` | **本地 scratch/POC 区，禁放正式数据**（运行时自动重建，如 answer-card-poc.py 输出） | ignore | exams/zhongkao.db/answer-card-poc 均已归档，目录现为空 |
| `out/` | **唯一交付根**：`student-reports/<id>/<slug>/report.{md,pdf}`、`papers/<slug>.pdf` | student-reports/ + papers/ ignore | ✅ 已收口 |
| `archived/legacy-exam-ocr-scripts/` | 6 个 v2 前旧脚本（bulk_pipeline / final_to_paper / extract_answer_key / structure-exam-final / segment-exam-draft / ocr-paddle-exam） | track | 小体量代码，留史；见该目录 ARCHIVED.md |
| `archived/legacy-*`（data） | `legacy-data-exams/`(39 旧件) + `legacy-db/` + `legacy-answer-card-poc/`(100M) | ignore | 备查不入 git |

### 代码 / 应用
| 目录 | 职责 | 备注 |
|---|---|---|
| `scripts/` | 流水线（exam-ocr / answer-card-ocr / student-report / knowledge-base） | 核心，结构清晰 ✅ |
| `tools/` | 人工审核工具（exam-review / answer-card-review） | 独立工具 |
| `server/` | **唯一后端**：FastAPI 学情分析 H5 接口（main.py + sqlite `data.sqlite3` + uploads/） | 权威服务层 |
| `web/` | **唯一前端**：Vite SPA（学生 H5） | 在用 |
| ~~`admin/` `miniprogram/` `backend/`~~ | 半成品 / 空壳 | ✅ 已删除 |
| `students/_web/<hash>/` | server 运行时 web 会话产物 | 仍错位但暂留（live server 硬编码 `WEB_STUDENTS`），后续随部署迁 `server/uploads/` |
| `docs/` | 文档（product / specs / knowledge-base） | 组织良好 ✅ |
| `archived/` | 历史归档（spike 等） | 归档区，legacy 去处 |

## 4. 已知问题 → 处置阶段映射

| 问题 | 阶段 | 状态 |
|---|---|---|
| 结构化数据三处并存（raw / data/exams 旧 / knowledge-base 新） | 1 | ✅ data/exams 归档 |
| 两个 SQLite（data/zhongkao.db vs server/data.sqlite3）无主 | 1 | ✅ data/zhongkao.db 归档，server 为权威 |
| backend/ 空壳 vs server/ 真实 | 3 | ✅ backend/ 已删 |
| 4 个 UI 面边界不清 | 3 | ✅ 仅留 web/，admin+miniprogram 已删 |
| `learning situation/` 空格目录 + 交付物散三处 | 2 | ✅ 收口 out/ |
| students/_web 错位 | 2/3 | ⏸ deferred（live server 依赖） |
| knowledge-base 近空骨架子域 | 4 | ⏸ deferred（低优先） |
| slug 未文档化 | 0 | ✅ EXAM-SLUG-SPEC |
| 无仓库总览 | 0 | ✅ 本文件 |
| .gitignore 缺全局 node_modules | 3 | ✅ 已加 `**/node_modules/` |

## 5. 决策与执行记录

| 决策点 | 结论 | 落地 |
|---|---|---|
| data/exams + data/zhongkao.db | legacy | 归档 `archived/legacy-*`（gitignore） |
| 前端定位 | 仅 web 在用 | 删 admin/miniprogram/backend |
| 交付物收口 out/ | 认可 | `build_report.py` 输出改 `out/student-reports/<id>/<slug>/report.{md,pdf}` |

**剩余 deferred**：
- `students/_web/` 迁 `server/uploads/`：需同步改 `server/main.py:WEB_STUDENTS` 并与 aliyun 部署一起做，避免动线上。
- 阶段 4 knowledge-base 近空子域（assessment/resources/regions/workbooks/admission）：低优先，待知识库建设规划时一并定。
