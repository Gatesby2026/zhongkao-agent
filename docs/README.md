# 文档索引

中考智能学习规划项目（北京中考 AI 私人教研组）的所有长期文档收口在 `docs/`。

**分类按「角色」，currency 按「状态」**（见每表"状态"列）：

| 目录 | 职责 | 能否被校验 |
|---|---|---|
| `product/` | 产品意图：为什么做、给用户什么 | 否（目标/取舍） |
| `specs/` | 数据/标识契约：必须长什么样 | **是**（有 lint：paths.py / kb_lint.py / qc_report.py） |
| `architecture/` | 系统/仓库结构与组织决策 + 数据流 | 部分（含可校验契约碎片，已抽到 specs/） |
| `design/` | 做事的方法/策略思路（durable 非契约） | 否 |
| `archive/` | 一次性/历史/被取代（文件名带 `YYYY-MM-DD-`） | — |

> 治理约定见末节「docs 规范」。新增/移动文档须遵守，并在本索引登记。

## 📦 [product/](./product/) — 产品

| 文档 | 状态 | 说明 |
|------|------|------|
| [PRD.md](./product/PRD.md) | durable ⚠架构待更新 | 产品需求主线 v5.0（服务号+小程序愿景）。**注**：小程序/admin 已下线，实际上线形态为 web H5 + FastAPI，架构章节待 reconcile |
| [STUDENT-REPORT-FLOW.md](./product/STUDENT-REPORT-FLOW.md) | durable | 学情分析 H5 闭环「落地实现」PRD（已上线，原 XUEQING-H5-FLOW-PRD） |
| [USER-PERSONA-REPORT.md](./product/USER-PERSONA-REPORT.md) | durable | 用户画像 |

## 📐 [specs/](./specs/) — 数据/标识契约

| 文档 | 状态 | 说明 |
|------|------|------|
| [EXAM-SLUG-SPEC.md](./specs/EXAM-SLUG-SPEC.md) | spec v1.0 | 试卷唯一标识（跨层 join 键，paths.py 校验） |
| [KB-MODULE-ID-SPEC.md](./specs/KB-MODULE-ID-SPEC.md) | spec v1.0 | 知识模块标识（pedagogy 跨层 join，kb_lint 校验） |
| [STUDENT-PROFILE-SPEC.md](./specs/STUDENT-PROFILE-SPEC.md) | spec | 学生画像数据模型 |
| [EXAM-FORMAT-SPEC.md](./specs/EXAM-FORMAT-SPEC.md) | spec | 北京中考各科试卷格式 |
| [STUDENT-REPORT-FEATURE-SPEC.md](./specs/STUDENT-REPORT-FEATURE-SPEC.md) | spec v0.1 | 学情报告功能标准化规格 |

## 🏗 [architecture/](./architecture/) — 结构与组织

| 文档 | 状态 | 说明 |
|------|------|------|
| [REPO-LAYOUT.md](./architecture/REPO-LAYOUT.md) | architecture v1.x | 仓库目录拓扑 + 数据流 + 三层铁律 + 整改阶段（**找结构先看这里**） |
| [KB-LAYOUT.md](./architecture/KB-LAYOUT.md) | architecture v1.x | knowledge-base 五域结构与数据契约（取代旧 KNOWLEDGE-BASE-PLAN） |

## 🧭 [design/](./design/) — 设计/策略

| 文档 | 状态 | 说明 |
|------|------|------|
| [KNOWLEDGE-TRACKING-DESIGN.md](./design/KNOWLEDGE-TRACKING-DESIGN.md) | design | 学生知识掌握动态追踪体系设计 |
| [TEACHING-MATERIALS-STRATEGY.md](./design/TEACHING-MATERIALS-STRATEGY.md) | design | 教辅材料数据获取策略 |
| [RANK-PREDICTION-2026-V3.md](./design/RANK-PREDICTION-2026-V3.md) | canonical design | 朝阳区 2026 录取位次预测基线 |

## 🗄 [archive/](./archive/) — 一次性/历史

| 文档 | 说明 |
|------|------|
| 2026-05-14-ANSWER-CARD-OCR-{RESEARCH,DEMO-RESULTS,TRACKB-RESULTS,BREAKTHROUGH}.md | 答题卡 OCR 调研流水账（已被落地流水线取代） |
| 2026-05-11-EXAM-QUALITY-AUDIT.md | 数学试卷质量审核（一次性报告） |
| 2026-04-12-KNOWLEDGE-BASE-REVIEW.md | 知识库建设评估 v2（一次性报告） |
| 2026-05-11-PRODUCT-REVIEW-v2.1.md | 早期 PRD v2.1 评审（历史） |
| math-exam-stats.txt | 数学题量统计数据 artifact（非文档，待移出 docs） |

---

## 阅读路径建议

**第一次了解项目**
1. [architecture/REPO-LAYOUT.md](./architecture/REPO-LAYOUT.md) — 仓库怎么组织、数据怎么流
2. [product/PRD.md](./product/PRD.md) 产品定位 + [product/USER-PERSONA-REPORT.md](./product/USER-PERSONA-REPORT.md)

**做后端 / 服务**
1. [product/STUDENT-REPORT-FLOW.md](./product/STUDENT-REPORT-FLOW.md) — 已上线 H5+API 闭环
2. [specs/STUDENT-PROFILE-SPEC.md](./specs/STUDENT-PROFILE-SPEC.md) 数据模型
3. `../server/`（唯一后端：FastAPI）

**做前端**
1. [product/STUDENT-REPORT-FLOW.md](./product/STUDENT-REPORT-FLOW.md)
2. `../web/`（唯一前端：Vite SPA）

**做内容/知识库**
1. [architecture/KB-LAYOUT.md](./architecture/KB-LAYOUT.md) + [specs/KB-MODULE-ID-SPEC.md](./specs/KB-MODULE-ID-SPEC.md)
2. [specs/EXAM-FORMAT-SPEC.md](./specs/EXAM-FORMAT-SPEC.md)
3. [design/TEACHING-MATERIALS-STRATEGY.md](./design/TEACHING-MATERIALS-STRATEGY.md)

## 其他参考（不在 docs/ 下）

- `../server/` — 唯一后端（FastAPI 学情分析 H5 接口，systemd `zhongkao.service`）
- `../web/` — 唯一前端（Vite SPA）
- `../scripts/` — 流水线脚本，按职责分子目录：
  - `exam-ocr/` — 试卷 OCR + 结构化（含 `paths.py` 路径真相、`qc_report.py` 质量门禁）
  - `knowledge-base/` — docx/PDF → 题库 YAML、`kb_lint.py`/`kb_module_ids.py` 门禁
  - `answer-card-ocr/` — 答题卡识别
  - `student-report/` — 学情分析报告生成
- `../knowledge-base/README.md` — 数据目录结构指针（→ architecture/KB-LAYOUT.md）
- `../archived/` — 已废弃代码/预研（legacy 脚本、iLink Bot spike）
- `~/.claude/.../memory/` — 仓库外的 skill 记忆与决策记录

## docs 规范（治理约定）

1. docs 只放**长期知识**；按角色入 `product/` `specs/` `architecture/` `design/` 之一，根目录仅 `README.md`
2. **一次性/带日期/被取代** 的报告与调研日志一律进 `archive/`，文件名加 `YYYY-MM-DD-` 前缀
3. 文件名 `SCREAMING-KEBAB.md`，英文无拼音；数据 artifact 不进 docs
4. 每份文档在本索引登记并标"状态"列（durable/spec/architecture/design/archived）
5. canonical 唯一：架构文档放 `architecture/`，被治理目录放**指针**回链，不复制内容
6. （规划）`scripts/docs_lint.py` 将自动校验 1–4 并反向生成本索引——见 REPO-LAYOUT
