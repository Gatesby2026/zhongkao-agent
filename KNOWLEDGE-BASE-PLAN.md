# 知识库建设方案 — 现状、结构与迭代计划

> 最后更新：2026-04-13（Phase 9 workbooks 完成后更新）
> 关联文档：[DESIGN.md](./DESIGN.md)（产品设计）
> 当前范围：北京市 × 6 科全覆盖

---

## 一、知识库总览

知识库共 **282 个 YAML 文件**（约 170,800 行），覆盖 2026 年北京中考全部 6 个计分科目（总分 510）。

### 科目覆盖状态

| 科目 | 满分 | 考纲 | 真题分析 | 诊断标准 | 学习路径 | 易错点 | 试卷库 |
|------|------|:----:|:--------:|:--------:|:--------:|:------:|:------:|
| 数学 | 100 | ✅ 4 | ✅ 6 | ✅ 8 | ✅ 7 | ✅ 8 | ✅ 101+ |
| 语文 | 100 | ✅ 4 | ✅ 6 | ✅ 5 | ✅ 5 | ✅ 5 | ✅ 3 |
| 英语 | 100 | ✅ 4 | ✅ 6 | ✅ 5 | ✅ 5 | ✅ 5 | ✅ 3 |
| 物理 | 80  | ✅ 4 | ✅ 6 | ✅ 5 | ✅ 5 | ✅ 5 | ✅ 3 |
| 道法 | 80  | ✅ 4 | ✅ 6 | ✅ 4 | ✅ 4 | ✅ 4 | ✅ 3 |
| 体育 | 50  | ✅ 3 | N/A | N/A | N/A | N/A | N/A |

> ✅ = 已完成  N/A = 该科目不适用

### 知识库层级结构

| 层级 | 目录 | 数学 | 语/英/物/道 | 体育 | 说明 |
|------|------|:----:|:-----------:|:----:|------|
| ① 地区政策 | `regions/` | ✅ 5 | 共用 | 共用 | 北京市政策 + 4 区特色 |
| ② 学科考纲 | `subjects/` | ✅ 4 | ✅ 各 4 | ✅ 3 | 课标知识点 + 题型/权重分析 |
| ③ 诊断标准 | `diagnostics/` | ✅ 8 | ✅ 各 4-5 | N/A | L0-L3 分级标准 |
| ④ 学习路径 | `learning-paths/` | ✅ 7 | ✅ 各 4-5 | N/A | 分级进阶路径 + 资源推荐 |
| ⑤ 真题分析 | `exam-analysis/` | ✅ 6 | ✅ 各 6 | N/A | 2021-2025 逐题 + 跨年汇总 |
| ⑥ 录取数据 | `admission/` | ✅ 6 | 共用 | 共用 | 4 区分数线 + 目标映射 |
| ⑦ 易错点 | `common-mistakes/` | ✅ 8 | ✅ 各 4-5 | N/A | 分级易错点 + 纠正方法 |
| ⑧ 试卷库 | `mock-exams/` | ✅ 101+ | ✅ 各 3 | N/A | 真题结构化（2023-2025） |
| ⑨ 辅导材料 | `study-guides/` | ✅ 3 | ✅ 各 2-3 | N/A | 答题模板+冲刺清单+速查表 |
| ⑩ 教辅目录 | `workbooks/` | ✅ 4 | 共用 | N/A | 8品牌14系列+选购指南+章节映射 |
| 辅助 | `resources/` | ✅ 4 | 共用 | 共用 | 教辅/教材/平台推荐 |

---

## 二、目录结构（实际）

```
knowledge-base/                              # 195 个 YAML 文件
│
├── regions/                                 # ① 地区政策（跨科目共用）
│   └── beijing/
│       ├── policy.yaml                      #    2026年中考政策（510分制、6科计分）
│       └── districts/
│           ├── haidian.yaml                 #    海淀区
│           ├── xicheng.yaml                 #    西城区
│           ├── dongcheng.yaml               #    东城区
│           └── chaoyang.yaml                #    朝阳区
│
├── subjects/                                # ② 学科考纲（6 科目）
│   ├── math/
│   │   ├── curriculum.yaml                  #    数学课标知识点树（2022版）
│   │   └── beijing/
│   │       ├── exam-spec.yaml               #    考试说明（100分/120分钟/闭卷）
│   │       ├── question-types.yaml          #    题型分布与历年对比
│   │       └── weight-analysis.yaml         #    知识点权重（真题统计）
│   ├── chinese/
│   │   ├── curriculum.yaml                  #    语文课标知识点树（2022版）
│   │   └── beijing/
│   │       ├── exam-spec.yaml               #    考试说明（100分/150分钟/闭卷）
│   │       ├── question-types.yaml          #    题型分布（基础+古诗文+现代文+写作）
│   │       └── weight-analysis.yaml         #    知识点权重
│   ├── english/
│   │   ├── curriculum.yaml                  #    英语课标知识点树（2022版/1600词）
│   │   └── beijing/
│   │       ├── exam-spec.yaml               #    考试说明（笔试60+听口40=100分）
│   │       ├── question-types.yaml          #    题型分布（含2024改革对比）
│   │       └── weight-analysis.yaml         #    知识点权重
│   ├── physics/
│   │   ├── curriculum.yaml                  #    物理课标知识点树（声光热力电）
│   │   └── beijing/
│   │       ├── exam-spec.yaml               #    考试说明（80分/90分钟/闭卷）
│   │       ├── question-types.yaml          #    题型分布
│   │       └── weight-analysis.yaml         #    知识点权重（力电各35%）
│   ├── politics/
│   │   ├── curriculum.yaml                  #    道法课标知识点树（道德/法治/国情/时政/心理）
│   │   └── beijing/
│   │       ├── exam-spec.yaml               #    考试说明（80分/90分钟/开卷！）
│   │       ├── question-types.yaml          #    题型分布（含开卷考策略）
│   │       └── weight-analysis.yaml         #    知识点权重
│   └── pe/
│       └── beijing/
│           ├── exam-spec.yaml               #    体育考试说明（过程性10+现场40=50分）
│           ├── scoring-standards.yaml        #    男女各项目评分标准
│           └── training-plans.yaml           #    各项目训练方案
│
├── diagnostics/                             # ③ 诊断标准（6 科目，数学8+语文5+英语5+物理5+道法4=27）
│   ├── math/
│   │   ├── numbers-and-expressions.yaml
│   │   ├── equations-and-inequalities.yaml
│   │   ├── functions.yaml
│   │   ├── triangles.yaml
│   │   ├── quadrilaterals.yaml
│   │   ├── circles.yaml
│   │   ├── geometry-comprehensive.yaml
│   │   └── statistics-and-probability.yaml
│   ├── chinese/
│   │   ├── basic-usage.yaml                 #    基础·运用
│   │   ├── classical-reading.yaml           #    古诗文阅读
│   │   ├── masterpiece-reading.yaml         #    名著阅读
│   │   ├── modern-reading.yaml              #    现代文阅读
│   │   └── writing.yaml                     #    写作
│   ├── english/
│   │   ├── grammar-basics.yaml              #    基础语法
│   │   ├── grammar-advanced.yaml            #    高阶语法
│   │   ├── cloze.yaml                       #    完形填空
│   │   ├── reading.yaml                     #    阅读理解
│   │   └── writing.yaml                     #    写作
│   ├── physics/
│   │   ├── sound-light-heat.yaml            #    声光热
│   │   ├── mechanics.yaml                   #    力学
│   │   ├── electricity.yaml                 #    电学
│   │   ├── experiments.yaml                 #    实验探究
│   │   └── calculation.yaml                 #    计算题
│   └── politics/
│       ├── moral-law.yaml                   #    道德与法治
│       ├── national-conditions.yaml         #    国情
│       ├── current-affairs.yaml             #    时政
│       └── answer-techniques.yaml           #    答题技巧
│
├── learning-paths/                          # ④ 学习路径（5 科目，数学7+语文5+英语5+物理5+道法4=26）
│   ├── math/
│   │   └── beijing/
│   │       ├── numbers-and-expressions.yaml
│   │       ├── equations-and-inequalities.yaml
│   │       ├── functions.yaml
│   │       ├── triangles.yaml
│   │       ├── quadrilaterals-and-circles.yaml
│   │       ├── geometry-comprehensive.yaml
│   │       └── statistics-and-probability.yaml
│   ├── chinese/beijing/                     #    语文 5 模块
│   │   ├── basic-usage.yaml ~ writing.yaml
│   ├── english/beijing/                     #    英语 5 模块
│   │   ├── grammar-basics.yaml ~ writing.yaml
│   ├── physics/beijing/                     #    物理 5 模块
│   │   ├── sound-light-heat.yaml ~ calculation.yaml
│   └── politics/beijing/                    #    道法 4 模块
│       ├── moral-law.yaml ~ answer-techniques.yaml
│
├── exam-analysis/                           # ⑤ 真题分析（5 科目 × 6 文件）
│   ├── math/beijing/
│   │   ├── 2021.yaml ~ 2025.yaml           #    逐题分析（28题/年）
│   │   └── summary.yaml                    #    5年汇总
│   ├── chinese/beijing/
│   │   ├── 2021.yaml ~ 2025.yaml           #    逐题分析（~25题/年）
│   │   └── summary.yaml                    #    5年汇总（含作文题目规律）
│   ├── english/beijing/
│   │   ├── 2021.yaml ~ 2025.yaml           #    逐题分析（含2024改革前后对比）
│   │   └── summary.yaml                    #    5年汇总（含改革影响分析）
│   ├── physics/beijing/
│   │   ├── 2021.yaml ~ 2025.yaml           #    逐题分析（含实验探究详解）
│   │   └── summary.yaml                    #    5年汇总（含高频实验统计）
│   └── politics/beijing/
│       ├── 2021.yaml ~ 2025.yaml           #    逐题分析（含时政热点关联）
│       └── summary.yaml                    #    5年汇总（含开卷答题策略）
│
├── admission/                               # ⑥ 录取数据（跨科目共用）
│   └── beijing/
│       ├── scoring-system.yaml
│       ├── math-target-mapping.yaml
│       ├── chaoyang.yaml
│       ├── haidian.yaml
│       ├── xicheng.yaml
│       └── dongcheng.yaml
│
├── common-mistakes/                         # ⑦ 易错点（5 科目，数学8+语文5+英语5+物理5+道法4=27）
│   ├── math/
│   │   ├── numbers-and-expressions.yaml ~ statistics-and-probability.yaml  # 8 模块
│   ├── chinese/
│   │   ├── basic-usage.yaml ~ writing.yaml  #    5 模块（25 个易错点）
│   ├── english/
│   │   ├── grammar-basics.yaml ~ writing.yaml  # 5 模块（28 个易错点）
│   ├── physics/
│   │   ├── sound-light-heat.yaml ~ calculation.yaml  # 5 模块（31 个易错点）
│   └── politics/
│       ├── moral-law.yaml ~ answer-techniques.yaml   # 4 模块（24 个易错点）
│
├── mock-exams/                              # ⑧ 试卷库（数学101++语文3+英语3+物理3+道法3=113+）
│   ├── math/
│   │   └── beijing/
│   │       ├── 2005-beijing-zhenti.yaml ~ 2025-beijing-zhenti.yaml  # 21年真题
│   │       ├── 2023-*.yaml                  #    2023各区一二三模
│   │       ├── 2024-*.yaml                  #    2024各区一二三模
│   │       └── 2025-*.yaml                  #    2025各区一二模
│   ├── chinese/beijing/
│   │   ├── 2023/2024/2025-beijing-zhenti.yaml  # 真题结构化摘要
│   ├── english/beijing/
│   │   ├── 2023/2024/2025-beijing-zhenti.yaml  # 含2024改革前后对比
│   ├── physics/beijing/
│   │   ├── 2023/2024/2025-beijing-zhenti.yaml
│   └── politics/beijing/
│       ├── 2023/2024/2025-beijing-zhenti.yaml  # 开卷考试
│
├── workbooks/                               # ⑩ 教辅目录（跨科目共用）
│   ├── catalog.yaml                         #    8品牌14系列·选购指南·版本管理（503行）
│   ├── wusan/
│   │   ├── math-quanlian-2026-bj.yaml       #    五三全练版数学·9章42课时→8模块映射
│   │   └── physics-quanlian-2026-bj.yaml    #    五三全练版物理·21专题→5模块映射
│   └── wanwei/
│       └── math-shiti-2026-bj.yaml          #    万唯试题研究数学·8模块+压轴专题映射
│
├── assessment/                              # 快速测评题
│   └── math/
│       └── quick-test.yaml
│
└── resources/                               # 辅助资源（跨科目共用）
    ├── textbooks.yaml
    ├── workbooks.yaml
    ├── online-platforms.yaml
    └── exam-papers.yaml
```

---

## 三、代码接入状态

知识库通过 `app/lib/knowledge-base.ts` 加载，`prompt-builder.ts` 注入 LLM prompt。

### 数据加载

`knowledge-base.ts` 已支持多科目加载：
- `KnowledgeBase.subjects.chinese/english/physics/politics` — 各科 `SubjectData`（curriculum + examSpec + questionTypes + weightAnalysis + examAnalysis）
- `KnowledgeBase.subjects.pe` — 体育 `PEData`（examSpec + scoringStandards + trainingPlans）
- 数学保持原有字段向后兼容
- 新增 `getSubjectData()` 和 `getAllSubjectsOverview()` 便捷方法

### Prompt 注入状态

| 数据 | 加载 | 注入 Prompt | 说明 |
|------|:----:|:-----------:|------|
| ① 地区政策 | ✅ | ✅ | 全量注入 |
| ② 数学考纲 | ✅ | ✅ | 全量注入 |
| ② 其他科目考纲 | ✅ | ⏳ | 已加载，prompt-builder 代码已写，待 API 路由接入 |
| ③ 数学诊断标准 | ✅ | ✅ | 按用户模块定级注入 |
| ③ 其他科目诊断标准 | ✅ | ⏳ | 19 文件已就绪，待代码适配加载 |
| ④ 数学学习路径 | ✅ | ✅ | 按用户模块定级注入 |
| ④ 其他科目学习路径 | ✅ | ⏳ | 19 文件已就绪，待代码适配加载 |
| ⑤ 数学真题分析 | ✅ | ✅ | summary + 当年数据 |
| ⑤ 其他科目真题分析 | ✅ | ⏳ | 已加载，prompt-builder 代码已写，待 API 路由接入 |
| ⑥ 录取数据 | ✅ | ✅ | 按用户所在区注入 |
| ⑦ 数学易错点 | ✅ | ✅ | 按模块+水平段注入 |
| ⑦ 其他科目易错点 | ✅ | ⏳ | 19 文件已就绪，待代码适配加载 |
| ⑧ 试卷库 | ✅ | ⚠️ 部分 | 数学已注入，其他科目 12 文件待适配 |
| 资源推荐 | ✅ | ✅ | 按用户水平段注入 |

---

## 四、数据质量标记

| 标记 | 含义 | 占比 |
|------|------|------|
| 🟢 官方数据 | 来自教育考试院/教委/课标 | ~15% |
| 🟡 网络数据 | 来自家长帮/菁优网/知乎，交叉验证过 | ~45% |
| 🔴 LLM 生成 | Claude/GPT 生成，未经教师审核 | ~40% |

各层分布：
- 🟢：policy.yaml、各科 curriculum.yaml、textbooks.yaml
- 🟡：exam-analysis/*（数学）、admission/*、weight-analysis.yaml（数学）、mock-exams/*、common-mistakes/*
- 🔴：diagnostics/*、learning-paths/*、其他科目的 exam-analysis 和 weight-analysis（基于 LLM 知识生成，待真题原卷验证）

---

## 五、已知问题清单（按优先级）

### P0 — 数据错误

| # | 问题 | 状态 |
|---|------|------|
| 1 | ~~question-types.yaml 总分写了 120~~ | ✅ 已修正 |
| 2 | ~~exam-spec.yaml 与 510 分制对齐~~ | ✅ 已确认 |
| 3 | ~~exam-papers.yaml 2024年误写 full_score: 120~~ | ✅ 已修正 |

### P1 — 功能缺失

| # | 问题 | 状态 |
|---|------|------|
| 4 | 其他科目数据未注入 prompt（已加载但 prompt-builder 尚未使用） | ⏳ 待做 |
| 5 | 诊断标准缺少配套诊断例题 | ⏳ 待做 |
| 6 | 学习路径缺少时间维度（距中考 X 月应有不同策略） | ⏳ 待做 |
| 7 | "目标学校→各科目标分→需达到什么水平"链路未结构化 | ⏳ 待做 |

### P2 — 覆盖不足

| # | 问题 | 状态 |
|---|------|------|
| 8 | 只覆盖 4 个区（缺丰台/大兴/石景山/通州等 12 区） | ⏳ |
| 9 | ~~只覆盖数学 1 科~~ | ✅ 已扩展至 6 科 |
| 10 | ~~语文/英语/物理/道法缺诊断标准（diagnostics）~~ | ✅ Phase 3 完成 |
| 11 | ~~语文/英语/物理/道法缺学习路径（learning-paths）~~ | ✅ Phase 3 完成 |
| 12 | ~~语文/英语/物理/道法缺易错点（common-mistakes）~~ | ✅ Phase 5 完成 |
| 13 | ~~语文/英语/物理/道法缺试卷库（mock-exams）~~ | ✅ Phase 5 完成 |
| 14 | 其他科目真题分析基于 LLM 生成，需用 knowledge-original 原卷验证 | ⏳ |

---

## 六、迭代计划

### ~~Phase 1 — 四科考试大纲（已完成 2026-04-12）~~

✅ 语文/英语/物理/道法各 4 文件（curriculum + exam-spec + question-types + weight-analysis）

### ~~Phase 2 — 四科真题分析（已完成 2026-04-12）~~

✅ 语文/英语/物理/道法各 6 文件（2021-2025 逐年 + summary）

### ~~Phase 4 — 体育科目（已完成 2026-04-12）~~

✅ 3 文件（exam-spec + scoring-standards + training-plans）

### ~~Phase 6 — 代码适配（已完成 2026-04-12）~~

✅ knowledge-base.ts 重构为多科目加载，向后兼容

### ~~Phase 3 — 四科诊断标准 + 学习路径（已完成 2026-04-12）~~

✅ 38 个文件：
- `diagnostics/`：语文 5 + 英语 5 + 物理 5 + 道法 4 = 19 文件
- `learning-paths/`：语文 5 + 英语 5 + 物理 5 + 道法 4 = 19 文件
- 每模块含 L0-L3 分级标准、diagnostic_questions、exam_benchmarks
- 学习路径含 steps/resources/pass_criteria 三要素

### ~~Phase 5 — 易错点 + 试卷库（已完成 2026-04-12）~~

✅ 31 个文件：
- `common-mistakes/`：语文 5 + 英语 5 + 物理 5 + 道法 4 = 19 文件（共 108 个易错点）
- `mock-exams/`：语文 3 + 英语 3 + 物理 3 + 道法 3 = 12 文件（2023-2025 真题结构化摘要）
- 易错点含 by_level 分级关联，按学生水平精准推送
- 试卷为结构化元数据（题号/考点/分值/难度），非原题文本

### ~~Phase 8 — 辅导材料 study-guides（已完成 2026-04-13）~~

✅ 14 个文件（约 7,000 行）：
- `answer-templates/`：5 科答题模板（数学/语文/英语/物理/道法），含各题型标准步骤+好坏范例
- `sprint-checklist/`：5 科考前冲刺清单（14 天计划+必拿分+易丢分+考场时间分配）
- `formula-sheet`：数学公式（67 条）+ 物理公式（19 条+常量+电路规则）
- `vocabulary-by-level`：英语词汇分级（1600 考纲词/718 核心词/440 纲外词/627 词组/100 不规则动词）
- `classical-must-know`：语文古诗文必背（61 篇+高频考句+30 易错字+20 虚词+15 实词）
- 物理公式和英语词汇基于学生本地真实辅导材料结构化，非纯 LLM 生成

### ~~Phase 9 — 教辅目录 workbooks（已完成 2026-04-13）~~

✅ 4 个文件（~1,521 行）：
- `workbooks/catalog.yaml`（503 行）：8 品牌 14 系列教辅完整目录
  - 品牌：五三（4 系列）、万唯（3）、全品（1）、天利（1）、金考卷（1）、学霸笔记（1）、中考帮（1）、五星学霸（2）
  - 每系列含：target_levels、usage_phase、how_to_use_by_level、subjects_available、price_range
  - 综合选购指南：按预算（75-160元）/ 按水平（L0-L3）/ 按阶段（9月→6月）
  - 版本管理策略：changes_from_<year> 增量记录，年度更新节奏
- `workbooks/wusan/math-quanlian-2026-bj.yaml`（373 行）：五三全练版数学 9 章 42 课时→8 模块映射
  - 数据来源：百度百科+中国考研网，含全国版 7 章 vs 地区版 9 章对照
- `workbooks/wusan/physics-quanlian-2026-bj.yaml`（376 行）：五三全练版物理 21 专题→5 模块映射
  - 数据来源：百度百科完整 TOC（data_confidence: verified）
  - 含 6 大核心实验→模块映射、分级使用建议
- `workbooks/wanwei/math-shiti-2026-bj.yaml`（269 行）：万唯试题研究数学 8 模块+4 压轴专题映射
  - 含万唯 vs 五三选择对比
- 同步更新 `resources/workbooks.yaml` 为简化版（保持向后兼容）

### ~~Phase 7 — Prompt 全科注入（代码部分已完成 2026-04-12）~~

✅ `prompt-builder.ts` 新增：
- `buildMultiSubjectPrompt()` — 多科目系统提示词构建
- `analyzeSubjects()` — ROI 驱动的跨科目时间分配
- `buildSubjectKBContext()` — 按科目注入知识库上下文
- ⏳ API 路由层适配待另一 session 完成

---

## 七、数据采集方法论

### 各层最佳数据源

| 层级 | 一手来源 | 二手来源 |
|------|---------|---------|
| ① 政策 | 教育考试院官网 | 中考网/公众号 |
| ② 考纲 | 课标 PDF + 考试说明 | 菁优网知识点树 |
| ③ 诊断 | 教师访谈 | 真题难度分层 |
| ④ 路径 | 教师设计 | 教辅目录体系 |
| ⑤ 真题 | 考试院真题 | 菁优网/知乎解析 |
| ⑥ 分数线 | 考试院录取数据 | 家长帮/北京中考在线 |
| ⑦ 易错点 | 教师教学经验 | 菁优网易错题标签 |
| ⑧ 模拟题 | 菁优网/学科网 | 各区教研公开资料 |

### 核心工具

| 工具 | 用途 | 费用 |
|------|------|------|
| 菁优网 VIP | 知识点体系 + 真题标注 + 模拟题 | ~200 元/年 |
| 学科网 | 模拟题/试卷下载 | ~298 元/年 |
| 国家智慧教育平台 | 免费教学视频资源 | 免费 |

### 年度更新节奏

| 时间 | 动作 |
|------|------|
| 每年 3 月 | 更新 ① 政策层（新年度中考方案发布） |
| 每年 4-5 月 | 更新 ⑧ 模拟题层（各区一模二模） |
| 每年 7 月 | 更新 ⑤ 真题层（当年中考结束后） |
| 每年 8 月 | 更新 ⑥ 分数线层（录取结果公布后） |
| 持续 | ③④⑦ 根据用户反馈和教师审核迭代 |

---

## 八、资源推荐规则

```yaml
safe_to_recommend:        # 放心推荐
  - 对应版本教材（需匹配考生所在区的版本）
  - 五年中考三年模拟（五三）
  - 万唯中考系列
  - 天利38套
  - 国家中小学智慧教育平台视频
  - 各区一模二模真题
  - 近5年北京中考真题

need_verification:        # 确认后推荐
  - 各类网课平台（质量参差）
  - 小众参考书
  - 自媒体教学内容

never_recommend:          # 不推荐
  - 盗版资源
  - 未经验证的付费课程

matching_rules:           # 水平匹配（已通过 workbooks.yaml 推荐矩阵实现）
  - L0 → 五三基础篇、教材全解
  - L1 → 五三A版、万唯基础
  - L2 → 万唯压轴、天利38套
  - L3 → 真题+模拟题限时训练、压轴突破
  - 教材版本必须匹配考生所在区
```

---

> 本文档随项目演进持续更新。截至 2026-04-13，知识库已从 MVP 阶段（北京 × 数学，51 文件）扩展至 **6 科全覆盖、10 层完整（282 文件，~170,800 行）**。Phase 1-9 全部完成，核心待办：教辅数学映射用实体书校准、扩展其他科目映射、真题原卷校验、API 路由层适配、教师审核 LLM 生成内容。
