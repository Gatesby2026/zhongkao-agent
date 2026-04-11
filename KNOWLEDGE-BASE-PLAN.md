# 知识库建设方案 — 现状、结构与迭代计划

> 最后更新：2026-04-11
> 关联文档：[DESIGN.md](./DESIGN.md)（产品设计）
> 当前范围：北京市 × 数学（MVP）

---

## 一、知识库总览

知识库共 **8 层**，51 个 YAML 文件。下表为当前建设状态：

| 层级 | 目录 | 文件数 | 完成度 | 说明 |
|------|------|--------|--------|------|
| ① 地区政策 | `regions/` | 5 | ✅ 可用 | 北京市政策 + 4 区特色 |
| ② 学科考纲 | `subjects/` | 4 | ⚠️ 需修正 | 课标知识点树 + 题型/权重分析 |
| ③ 诊断标准 | `diagnostics/` | 8 | ✅ 可用 | 8 个模块 × L0-L3 分级 |
| ④ 学习路径 | `learning-paths/` | 7 | ✅ 可用 | 7 个模块 × 分级路径 |
| ⑤ 真题分析 | `exam-analysis/` | 6 | ✅ 可用 | 2021-2025 逐题 + 跨年汇总 |
| ⑥ 录取分数线 | `admission/` | 6 | ✅ 可用 | 分制变迁 + 4 区逐校分数线 + 目标映射 + 校额到校 |
| ⑦ 易错点 | `common-mistakes/` | 8 | ✅ 已接入代码 | 8 模块 × 分级易错点，已注入 prompt |
| ⑧ 模拟题 | `mock-exams/` | 3 (+1 待补) | ⚠️ 未接入代码 | 一模试卷含完整题目+答案+解析 |
| 辅助：资源库 | `resources/` | 4 | ✅ 已接入代码 | 教辅推荐矩阵已注入 prompt |

---

## 二、目录结构（实际）

```
knowledge-base/
│
├── regions/                              # ① 地区政策
│   └── beijing/
│       ├── policy.yaml                   #    2026年中考政策（510分制、6科计分、校额到校等）
│       └── districts/
│           ├── haidian.yaml              #    海淀区（人教版、教研特色）
│           ├── xicheng.yaml              #    西城区
│           ├── dongcheng.yaml            #    东城区
│           └── chaoyang.yaml             #    朝阳区
│
├── subjects/                             # ② 学科考纲
│   └── math/
│       ├── curriculum.yaml               #    课标知识点树（2022版课标）
│       └── beijing/
│           ├── exam-spec.yaml            #    北京数学考试说明
│           ├── question-types.yaml       #    题型分布（⚠️ 总分仍写120，需改为100）
│           └── weight-analysis.yaml      #    知识点权重（真题统计）
│
├── diagnostics/                          # ③ 诊断标准（8模块 × L0-L3）
│   └── math/
│       ├── numbers-and-expressions.yaml
│       ├── equations-and-inequalities.yaml
│       ├── functions.yaml
│       ├── triangles.yaml
│       ├── quadrilaterals.yaml
│       ├── circles.yaml
│       ├── geometry-comprehensive.yaml
│       └── statistics-and-probability.yaml
│
├── learning-paths/                       # ④ 学习路径（7模块 × 分级）
│   └── math/
│       └── beijing/
│           ├── numbers-and-expressions.yaml
│           ├── equations-and-inequalities.yaml
│           ├── functions.yaml
│           ├── triangles.yaml
│           ├── quadrilaterals-and-circles.yaml  # 四边形+圆合并
│           ├── geometry-comprehensive.yaml
│           └── statistics-and-probability.yaml
│
├── exam-analysis/                        # ⑤ 真题分析
│   └── math/
│       └── beijing/
│           ├── 2021.yaml                 #    28题逐题分析
│           ├── 2022.yaml
│           ├── 2023.yaml
│           ├── 2024.yaml
│           ├── 2025.yaml
│           └── summary.yaml              #    5年汇总：题号规律/考频矩阵/分数段策略/趋势
│
├── admission/                            # ⑥ 录取分数线
│   └── beijing/
│       ├── scoring-system.yaml           #    总分制度变迁（660→670→510→520→530）
│       ├── math-target-mapping.yaml      #    目标学校→数学目标分映射
│       ├── chaoyang.yaml                 #    朝阳区25校·3年 + 校额到校数据
│       ├── haidian.yaml                  #    海淀区12校 + 校额到校数据
│       ├── xicheng.yaml                  #    西城区9校 + 校额到校数据
│       └── dongcheng.yaml               #    东城区11校 + 校额到校数据
│
├── common-mistakes/                      # ⑦ 易错点（NEW - 已接入代码）
│   └── math/
│       ├── numbers-and-expressions.yaml  #    8模块各含高频易错点
│       ├── equations-and-inequalities.yaml#   + 按 L0/L1/L2 分级聚焦
│       ├── functions.yaml                #   + 典型丢分·纠正方法·真题例子
│       ├── triangles.yaml
│       ├── quadrilaterals.yaml
│       ├── circles.yaml
│       ├── geometry-comprehensive.yaml
│       └── statistics-and-probability.yaml
│
├── mock-exams/                           # ⑧ 模拟题（NEW - 未接入代码）
│   └── math/
│       └── beijing/
│           ├── 2025-xicheng-yi.yaml      #    2025西城一模 28题完整
│           ├── 2025-chaoyang-yi.yaml      #    2025朝阳一模 28题完整
│           ├── 2025-dongcheng-yi.yaml     #    2025东城一模 28题完整
│           └── (2025-haidian-yi.yaml)     #    ⏳ 海淀一模待补充
│
└── resources/                            # 辅助：资源库
    ├── textbooks.yaml                    #    教材版本（人教版/北京版·按区分配）
    ├── workbooks.yaml                    #    教辅推荐 + 水平段推荐矩阵（已接入 prompt）
    ├── online-platforms.yaml             #    平台（智慧教育/菁优网等）
    └── exam-papers.yaml                  #    真题/模拟题索引
```

---

## 三、代码接入状态

知识库数据通过两个核心文件注入 LLM prompt：

| 模块 | knowledge-base.ts 加载 | prompt-builder.ts 注入 | 说明 |
|------|:---:|:---:|------|
| ① 地区政策 | ✅ | ✅ | 全量注入 |
| ② 学科考纲 | ✅ | ✅ | 全量注入 |
| ③ 诊断标准 | ✅ | ✅ | 按用户模块定级注入 |
| ④ 学习路径 | ✅ | ✅ | 按用户模块定级注入 |
| ⑤ 真题分析 | ✅ | ✅ | 注入 summary + 当年数据 |
| ⑥ 录取分数线 | ✅ | ✅ | 按用户所在区注入 |
| ⑦ 易错点 | ✅ | ✅ | 按模块+水平段注入 top 3 易错点 |
| ⑧ 模拟题 | ❌ | ❌ | **待接入** |
| 资源·教辅推荐矩阵 | ✅ | ✅ | 按用户水平段注入推荐 |

---

## 四、数据质量标记

| 标记 | 含义 | 占比 |
|------|------|------|
| 🟢 官方数据 | 来自教育考试院/教委/课标 | ~15% |
| 🟡 网络数据 | 来自家长帮/菁优网/知乎，交叉验证过 | ~50% |
| 🔴 LLM 生成 | Claude/GPT 生成，未经教师审核 | ~35% |

各层分布：
- 🟢：policy.yaml、curriculum.yaml、textbooks.yaml
- 🟡：exam-analysis/*、admission/*、weight-analysis.yaml、mock-exams/*、common-mistakes/*
- 🔴：diagnostics/*、learning-paths/*

---

## 五、已知问题清单（按优先级）

### P0 — 数据错误

| # | 问题 | 文件 | 状态 |
|---|------|------|------|
| 1 | question-types.yaml 总分写了 120，实际应为 100 | subjects/math/beijing/question-types.yaml | 🔴 待修 |
| 2 | exam-spec.yaml 是否与 510 分制对齐 | subjects/math/beijing/exam-spec.yaml | 🔴 待查 |

### P1 — 功能缺失

| # | 问题 | 状态 |
|---|------|------|
| 3 | 模拟题未接入代码（knowledge-base.ts + prompt-builder.ts） | 🔴 待做 |
| 4 | 海淀一模试卷数据待补充 | ⏳ 等用户提供文件 |
| 5 | 诊断标准缺少配套诊断例题 | 待做 |
| 6 | 学习路径缺少时间维度（距中考 X 月应有不同策略） | 待做 |
| 7 | "目标学校→数学目标分→需达到什么水平"链路未结构化 | 待做 |

### P2 — 覆盖不足

| # | 问题 |
|---|------|
| 8 | 只覆盖 4 个区（缺丰台/大兴/石景山/通州） |
| 9 | 只覆盖数学 1 科（缺物理/英语/道法） |
| 10 | 北京版教材未建章节目录 |
| 11 | 模拟题只有 2025 一模，缺二模和 2024 数据 |

---

## 六、下一步迭代计划

### 近期

1. **模拟题接入代码** — 将 mock-exams 加载到 knowledge-base.ts，在 prompt-builder.ts 中按模块/难度推荐练习题
2. **修正 P0** — question-types.yaml 总分 120→100，检查 exam-spec.yaml
3. **海淀一模补全** — 用户提供文件后转为 YAML

### 中期

4. **持续学习功能** — 模拟题作为学习跟进的练习题源，按用户水平段推荐
5. **诊断例题** — 为 diagnostics 每个级别配 3-5 道真题
6. **时间维度** — 学习路径按"距中考 X 月"区分策略

### 远期

7. **扩展学科** — 物理（第 2 个计分科目）
8. **扩展区域** — 丰台/大兴等区
9. **教师审核** — 将 diagnostics/learning-paths 从 🔴 升级为 🟡

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

> 本文档随项目演进持续更新。当前 MVP 阶段（北京 × 数学），8 层知识库 51 个文件基本建成。核心待办：模拟题接入代码、P0 数据修正、海淀一模补全。
