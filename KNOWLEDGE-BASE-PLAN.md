# 知识库建设方案 — 现状、结构与迭代计划

> 最后更新：2026-04-13
> 关联文档：[DESIGN.md](./DESIGN.md)（产品设计）、[KNOWLEDGE-BASE-REVIEW.md](./KNOWLEDGE-BASE-REVIEW.md)（质量评估）
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

### 知识库层级结构

| 层级 | 目录 | 数学 | 语文 | 英语 | 物理 | 道法 | 体育 | 说明 |
|------|------|:----:|:----:|:----:|:----:|:----:|:----:|------|
| ① 地区政策 | `regions/` | 共用 5 | 共用 | 共用 | 共用 | 共用 | 共用 | 北京市政策 + 4 区特色 |
| ② 学科考纲 | `subjects/` | 4 | 4 | 4 | 4 | 4 | 3 | 课标知识点 + 题型/权重分析 |
| ③ 诊断标准 | `diagnostics/` | 8 | 5 | 5 | 5 | 4 | — | L0-L3 分级标准 |
| ④ 学习路径 | `learning-paths/` | 7 | 5 | 5 | 5 | 4 | — | 分级进阶路径 + 资源推荐 |
| ⑤ 真题分析 | `exam-analysis/` | 6 | 6 | 6 | 6 | 6 | — | 2021-2025 逐题 + 跨年汇总 |
| ⑥ 录取数据 | `admission/` | 共用 6 | 共用 | 共用 | 共用 | 共用 | 共用 | 4 区分数线 + 目标映射 |
| ⑦ 易错点 | `common-mistakes/` | 8 | 5 | 5 | 5 | 4 | — | 分级易错点 + 纠正方法 |
| ⑧ 试卷库 | `mock-exams/` | 101+ | 3 | 3 | 3 | 3 | — | 真题结构化（2005-2025） |
| ⑨ 辅导材料 | `study-guides/` | 3 | 3 | 3 | 3 | 2 | — | 答题模板+冲刺清单+速查表 |
| ⑩ 教辅目录 | `workbooks/` | 2 | — | — | 1 | — | — | 章节→模块映射（+共用 catalog） |
| 辅助 | `resources/` | 共用 4 | 共用 | 共用 | 共用 | 共用 | 共用 | 教辅/教材/平台推荐 |

---

## 二、目录结构

```
knowledge-base/
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
│   ├── math/                                #    数学：curriculum + 3 beijing/*
│   ├── chinese/                             #    语文：curriculum + 3 beijing/*
│   ├── english/                             #    英语：curriculum + 3 beijing/*
│   ├── physics/                             #    物理：curriculum + 3 beijing/*
│   ├── politics/                            #    道法：curriculum + 3 beijing/*
│   └── pe/beijing/                          #    体育：exam-spec + scoring-standards + training-plans
│
├── diagnostics/                             # ③ 诊断标准（数学8+语文5+英语5+物理5+道法4=27）
│   ├── math/                                #    8 模块（数与式/方程/函数/三角/四边/圆/几何综合/统计）
│   ├── chinese/                             #    5 模块（基础/古诗文/名著/现代文/写作）
│   ├── english/                             #    5 模块（语法基础/高阶/完形/阅读/写作）
│   ├── physics/                             #    5 模块（声光热/力学/电学/实验/计算）
│   └── politics/                            #    4 模块（道法/国情/时政/答题技巧）
│
├── learning-paths/                          # ④ 学习路径（数学7+语文5+英语5+物理5+道法4=26）
│   ├── math/beijing/                        #    7 模块
│   ├── chinese/beijing/                     #    5 模块
│   ├── english/beijing/                     #    5 模块
│   ├── physics/beijing/                     #    5 模块
│   └── politics/beijing/                    #    4 模块
│
├── exam-analysis/                           # ⑤ 真题分析（5 科目 × 6 文件）
│   ├── math/beijing/                        #    2021-2025 逐题 + summary
│   ├── chinese/beijing/                     #    含作文题目规律
│   ├── english/beijing/                     #    含2024改革前后对比
│   ├── physics/beijing/                     #    含高频实验统计
│   └── politics/beijing/                    #    含开卷答题策略
│
├── admission/                               # ⑥ 录取数据（跨科目共用）
│   └── beijing/                             #    scoring-system + 4区分数线 + math-target-mapping
│
├── common-mistakes/                         # ⑦ 易错点（数学8+语文5+英语5+物理5+道法4=27）
│   ├── math/ ~ politics/                    #    与 diagnostics 模块一一对应
│
├── mock-exams/                              # ⑧ 试卷库
│   ├── math/beijing/                        #    101+ 套（2005-2025真题 + 各区一二三模）
│   ├── chinese/beijing/                     #    3 套（2023-2025真题摘要）
│   ├── english/beijing/                     #    3 套
│   ├── physics/beijing/                     #    3 套
│   └── politics/beijing/                    #    3 套
│
├── study-guides/                            # ⑨ 辅导材料
│   ├── math/                                #    answer-templates + sprint-checklist + formula-sheet
│   ├── chinese/                             #    answer-templates + sprint-checklist + classical-must-know
│   ├── english/                             #    answer-templates + sprint-checklist + vocabulary-by-level
│   ├── physics/                             #    answer-templates + sprint-checklist + formula-sheet
│   └── politics/                            #    answer-templates + sprint-checklist
│
├── workbooks/                               # ⑩ 教辅目录
│   ├── catalog.yaml                         #    8品牌14系列·选购指南·版本管理
│   ├── wusan/
│   │   ├── math-quanlian-2026-bj.yaml       #    五三数学·9章42课时→8模块映射
│   │   └── physics-quanlian-2026-bj.yaml    #    五三物理·21专题→5模块映射
│   └── wanwei/
│       └── math-shiti-2026-bj.yaml          #    万唯数学·8模块+压轴专题映射
│
├── assessment/                              # 快速测评题
│   └── math/quick-test.yaml
│
└── resources/                               # 辅助资源（跨科目共用）
    ├── textbooks.yaml
    ├── workbooks.yaml                       #    简化版，指向 workbooks/catalog.yaml
    ├── online-platforms.yaml
    └── exam-papers.yaml
```

---

## 三、数据质量标记

| 标记 | 含义 | 占比 |
|------|------|------|
| 🟢 官方数据 | 来自教育考试院/教委/课标 | ~15% |
| 🟡 网络数据 | 来自家长帮/菁优网/知乎，交叉验证过 | ~45% |
| 🔴 LLM 生成 | Claude/GPT 生成，未经教师审核 | ~40% |

各层分布：
- 🟢：policy.yaml、各科 curriculum.yaml、textbooks.yaml
- 🟡：exam-analysis/*（数学）、admission/*、weight-analysis.yaml（数学）、mock-exams/*、study-guides 中物理公式/英语词汇（基于学生真实辅导材料）
- 🔴：diagnostics/*、learning-paths/*、其他科目的 exam-analysis 和 weight-analysis（基于 LLM 知识生成，待真题原卷验证）

---

## 四、待办事项（按优先级）

### P1 — 数据验证

| # | 问题 | 说明 |
|---|------|------|
| 1 | 用真题原卷校准 4 科 exam-analysis | `knowledge-original/` 下已有 2005-2025 各科 PDF，需逐题对比 LLM 生成的分析 |
| 2 | 教辅章节映射用实体书目录校准 | 数学映射基于公开信息（partially_verified），需拍实体书目录页最终确认 |

### P2 — 数据扩充

| # | 问题 | 说明 |
|---|------|------|
| 3 | 诊断标准缺少配套诊断例题 | 当前只有 L0-L3 分级描述，需从真题中选配诊断题 |
| 4 | 学习路径缺少时间维度 | 距中考 X 月应有不同策略（当前是静态路径） |
| 5 | "目标学校→各科目标分→需达到什么水平"链路未结构化 | 需将录取数据与各科诊断标准打通 |
| 6 | 只覆盖 4 个区（缺丰台/大兴/石景山/通州等 12 区） | admission/ 和 regions/ 待扩展 |
| 7 | 教辅映射只覆盖数学+物理 | 语文/英语/道法的五三/万唯章节映射待建 |
| 8 | 其他科目试卷库只有 3 套真题摘要 | 数学有 101+ 套，其他科目差距大 |

### P3 — 长期

| # | 问题 |
|---|------|
| 9 | 教师审核 LLM 生成内容（diagnostics/learning-paths/common-mistakes） |
| 10 | 全科总分优化算法所需的跨科目数据结构 |

---

## 五、数据采集方法论

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
| ⑨ 辅导材料 | 学生实际辅导材料 | 教辅目录/公开复习资料 |
| ⑩ 教辅目录 | 实体书目录页 | 百度百科/出版社官网/电商 |

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
| 每年 9 月 | 更新 ⑩ 教辅目录层（新版教辅上市） |
| 持续 | ③④⑦ 根据用户反馈和教师审核迭代 |

---

## 六、资源推荐规则

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

matching_rules:           # 水平匹配（详见 workbooks/catalog.yaml 推荐矩阵）
  - L0 → 五三全练版（★题）、学霸笔记/五星学霸（辅助理解）
  - L1 → 五三全练版（★★题）、万唯试题研究
  - L2 → 五三真题分类、万唯试题研究、天利38套
  - L3 → 天利38套、万唯逆袭卷、海淀/西城一模二模限时训练
  - 教材版本必须匹配考生所在区
```
