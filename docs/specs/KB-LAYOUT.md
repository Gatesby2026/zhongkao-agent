# KB-LAYOUT — knowledge-base 域结构与数据契约

> 状态：v1.0（2026-05-18）· 阶段 0 立规（描述**目标态 + 现状差距 + 迁移阶段**）
> 配套：[KB-MODULE-ID-SPEC.md](./KB-MODULE-ID-SPEC.md)、[REPO-LAYOUT.md](./REPO-LAYOUT.md)、[EXAM-SLUG-SPEC.md](./EXAM-SLUG-SPEC.md)
> 取代：原 `docs/knowledge-base/KNOWLEDGE-BASE-PLAN.md`（已删，结构以本文件为准）

## 0. 定位

knowledge-base 是「**北京中考私人教研组**」的教研资产库。当前仅
「一模试卷学情分析」功能上线（消费 `exams/mock`）；其余层是**先于功能
建设的 roadmap 资产**——保留、治理、按里程碑接入，**不因暂无消费者而删/冻**。

铁律（承接 REPO-LAYOUT 三层）：
- **原始件**永远在 `knowledge-original/`（扫描页/抓取件），KB 不存 raw
- **派生中间件**（OCR/figures 等可重生件）进各域 `_staging/`，与最终知识件隔离
- **最终知识件**是 KB 的唯一真相，入 git

## 1. 五域结构（目标态）

```
knowledge-base/
├── exams/                      【考试域】试卷 + 分析；真题/模拟分离
│   ├── zhenti/<subj>/beijing/<year>-zhenti.yaml      官方真题（金标准，逐年累积，单卷不可变）
│   ├── mock/<subj>/beijing/<year>-<region>-<round>.yaml  各区模拟（当期，qc_report 门禁）
│   ├── analysis/<subj>/beijing/<year>.yaml           真题逐题分析 ← 并入 exam-analysis
│   └── _staging/<slug>/{pages,layout-cache,structured-cloud,figures}  派生中间件（gitignore pages/layout-cache）
├── pedagogy/                   【教研标准域】module-id 为主键的推理内核
│   ├── syllabus/<subj>/curriculum.yaml               课标知识图谱 ← 重命名自 subjects
│   ├── diagnostics/<subj>/<module-id>.yaml           能力分层量规 L0-L4
│   ├── mistakes/<subj>/<module-id>.yaml              易错点 ← 重命名自 common-mistakes
│   └── learning-paths/<subj>/beijing/<module-id>.yaml 提升路径
├── prep/                       【备考资源域】
│   ├── study-guides/<subj>/...                        自产辅导材料（冲刺清单/模板/公式）
│   ├── workbooks/catalog.yaml + <brand>/<...>.yaml    教辅品牌目录 + 章节→模块映射
│   ├── question-banks/<subj>/<workbook>/...           教辅题目结构化（raw 扫描页留 knowledge-original）
│   ├── quick-tests/<subj>.yaml                        诊断测评卷 ← 并入 assessment
│   ├── textbooks/beijing.yaml                         教材版本 ← 自 resources/textbooks
│   └── online-platforms.yaml                          ← 自 resources/online-platforms
├── admission/beijing/...       【升学域】区分数线/学校梯队（保持）
└── policies/beijing/policy.yaml 【政策域】中考政策 ← 重命名自 regions
```

## 2. 现状 → 目标 映射 + 命名正名

| 现状目录 | 问题 | 目标 |
|---|---|---|
| `mock-exams/` | 名实不符：含真题+模拟混放 | 拆 `exams/zhenti/` + `exams/mock/`；派生件入 `exams/_staging/` |
| `exam-analysis/` | 与试卷割裂 | 并入 `exams/analysis/` |
| `subjects/` | 名泛，实为课标知识图谱 | `pedagogy/syllabus/` |
| `common-mistakes/` | （内容 OK） | `pedagogy/mistakes/` |
| `diagnostics/` `learning-paths/` | （内容 OK） | 移入 `pedagogy/` |
| `resources/` | **冗余杂物筐**（4 文件 2 个与他域重复） | **解散**：textbooks→prep/textbooks；online-platforms→prep；workbooks.yaml→并入 prep/workbooks/catalog；exam-papers.yaml→并入 exams 说明 |
| `regions/` | 名泛，实为中考政策 | `policies/` |
| `assessment/` | 计划外，与 diagnostics 暧昧 | `prep/quick-tests/`（测评工具，与 pedagogy/diagnostics 量规解耦，同 module-id 对齐） |
| `workbooks/` | （内容 OK） | 移入 `prep/workbooks/` |
| `study-guides/` `question-banks/` | （内容 OK） | 移入 `prep/` |
| `admission/` | （内容 OK） | 保持 |

🐛 `question-banks/**/*.png`（教辅扫描页）属 raw，回迁 `knowledge-original/教辅材料/`。

## 3. 数据契约：质量态结构化

每个知识 yaml 顶部加标准 `meta` 块：

```yaml
meta:
  quality_status: llm_draft     # raw_import | llm_draft | teacher_reviewed | verified
  source: "义务教育课程标准2022 / 北京教育考试院 / ..."
  updated: 2026-05-18
  reviewed_by: null             # teacher_reviewed / verified 必填
  module_id: statistics-and-probability   # 仅 pedagogy 四层，对齐 KB-MODULE-ID-SPEC
```

- `quality_status` 取代现状埋在注释里的「LLM生成初稿待审」自由文本，**可查询可门禁**
- `scripts/knowledge-base/kb_lint.py`（待建，复用 `qc_report.py` 模式）：遍历全 KB，
  校验 meta 存在 / 枚举合法 / pedagogy 的 module_id 在 spec 内 /
  `teacher_reviewed|verified` 必有 `reviewed_by`；输出待审清单，有违规 exit 1

## 4. 域 × 功能里程碑（哪层已接入）

| 域 | 当前消费者 | 里程碑 |
|---|---|---|
| `exams/mock` | ✅ student-report（一模学情分析，已上线） | M1 已交付 |
| `exams/zhenti` `exams/analysis` | ⏳ 无 | M2 真题对标 |
| `pedagogy/*` | ⏳ 无（原 admin 消费者已删） | M2-M3 诊断/路径推荐 |
| `prep/*` `admission` `policies` | ⏳ 无 | M3-M4 资源推荐/升学规划 |

「⏳ 无」= roadmap 资产，非死数据；按里程碑接入，治理（meta+lint）先行。

## 5. 迁移阶段（零风险优先）

| 阶段 | 内容 | 风险 | 状态 |
|---|---|---|---|
| 0 | 本文件 + KB-MODULE-ID-SPEC；删 KNOWLEDGE-BASE-PLAN | 0 | ✅ |
| 2 | 解散 resources；subjects→pedagogy/syllabus、common-mistakes→pedagogy/mistakes、diagnostics/learning-paths→pedagogy/、regions→policies、workbooks/study-guides/question-banks→prep/、assessment→prep/quick-tests（221 文件全 rename，history 保留；改 .gitignore + pdf-to-questionbank docstring） | 中 | ✅ |
| 1 | `mock-exams`→`exams/{zhenti,mock,_staging}` + `exam-analysis`→`exams/analysis`（3355 renames，figures 保相对路径零数据改动）；改 ~20 处引用含 **server×2**（slug 解析搜 mock+zhenti）；本地全链路验证通过 | 中 | ✅（待阿里云重部署） |
| 3 | module-id 归一 kebab（pedagogy 三层 + quick-tests，68 文件确定性改写）；`kb_module_ids.py`(spec 真相) + `kb_normalize_module_id.py`(一次性) + `kb_lint.py`(门禁+覆盖矩阵) | 中 | ✅（1 内容缺口待人工） |
| 4 | 全 KB 补 meta 块；question-banks png 回迁 knowledge-original | 低 | ⏳ |

> 阶段 0/1/2/3 已执行。⚠️ **阶段 1 改了 server/（线上）** 已部署阿里云
> （`c33733e`，pull+restart+health+resolver 实测通过）。
> **阶段 3 遗留 1 内容任务**：`pedagogy/learning-paths/math/beijing/quadrilaterals-and-circles.yaml`
> 把 spec 两个独立模块 `quadrilaterals`+`circles` 合并成一个非合规文件 →
> 这两模块在 learning-paths 层缺覆盖。需**人工/LLM 按内容拆成
> `quadrilaterals.yaml` + `circles.yaml`**（非确定性，normalizer 已正确拒绝臆测）。
> `kb_lint.py` 会持续以 exit 1 + 覆盖矩阵报这 1 项，修完即绿。
> 剩余 ⏳ 阶段 4（meta 块 + png 回迁）。

## 6. 待决（阻塞阶段 2）

- `docs/knowledge-base/` 余 5 文件（REVIEW / TRACKING-REPORT / TEACHING-MATERIALS-STRATEGY / EXAM-QUALITY-AUDIT / math-exam-stats.txt）去留——是否一并并入 specs 或归档。
