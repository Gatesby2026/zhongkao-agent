# 学生画像数据模型规范

> 版本：v1.0 | 更新日期：2026-04-12
> 状态：Phase 1 已实现，持续迭代中

---

## 一、设计原则

1. **每条数据带来源（source）和置信度（confidence）**：系统知道哪些信息可靠、哪些需要验证
2. **被动采集 > 主动询问**：用户操作自然产生数据，不做问卷填表
3. **多来源交叉验证**：自评、测评、刷题、AI 诊断互相校验，冲突时降低置信度
4. **渐进丰富**：画像不是一次填完，每次交互自然积累

---

## 二、数据模型总览

```
StudentProfile
│
├── 1. 基础信息层（Static）
│   ├── district          区域          "朝阳区"
│   ├── school            学校          "陈经纶中学分校"
│   ├── grade             年级          "初三"
│   └── examDate          中考日期       "2026-06-24"（系统常量）
│
├── 2. 目标层（Goal）
│   ├── targetSchool      目标学校       "八十中"
│   ├── targetScore       目标分数       92
│   ├── currentScore      当前总分       78
│   └── hoursPerDay       每日可用时间   1.5（小时）
│
├── 3. 学科能力层（Academic）← 核心，权重最大
│   ├── modules[7]        模块级评估     详见 §3
│   ├── knowledgePoints[] 知识点级掌握   详见 §4
│   └── examHistory[]     考试/测评记录  详见 §5
│
├── 4. 行为层（Behavioral）
│   ├── drillHistory[]    刷题记录       详见 §6
│   ├── planHistory[]     计划记录       详见 §7
│   ├── streak            连续使用天数
│   └── lastActiveAt      最近活跃时间
│
└── 5. 偏好层（Preference）
    ├── role              操作者角色     "student" | "parent" | "tutor"
    ├── style             偏好讲解风格   "简洁" | "详细" | "举例多"
    └── priority          学习优先级     "先易后难" | "先补最弱"
```

---

## 三、模块级评估（modules）

7 个数学模块，每个模块独立评估：

| 模块 ID | 中文名 | 中考占比 |
|---------|--------|---------|
| numbersAndExpressions | 计算/数与式（实数运算、因式分解、分式） | ~15% |
| equationsAndInequalities | 方程与不等式（一元二次方程、分式方程、应用题） | ~15% |
| functions | 函数（一次函数、反比例函数、二次函数） | ~20% |
| triangles | 三角形（全等、相似、勾股定理、三角函数） | ~15% |
| circles | 圆（垂径定理、圆周角、切线） | ~10% |
| statisticsAndProbability | 统计与概率（平均数、方差、树状图） | ~10% |
| geometryComprehensive | 压轴题（几何综合、动态几何、代几综合） | ~15% |

### 单个模块的数据结构

```typescript
interface ModuleProfile {
  level: string;        // "很差" | "薄弱" | "还行" | "不错" | "擅长" | "不确定"
  source: LevelSource;  // 评估来源（决定 confidence 基准）
  confidence: number;   // 0.0 ~ 1.0（这个评估有多可信）
  updatedAt: string;    // 最后更新时间
}
```

### 来源与置信度映射

| 来源 source | 含义 | 基准置信度 | 说明 |
|------------|------|-----------|------|
| `self` | 用户自评 | 0.3 | 最不可靠，主观偏差大 |
| `assessment` | 快速测评 | 0.6 | 10 题诊断，错因追踪 |
| `drill` | 刷题数据 | 0.8 | 多次刷题后统计，较可靠 |
| `llm` | AI 对话诊断 | 0.9 | LLM 深度追问，最精准（Phase 2） |

### Level 数值映射

| level | 数值 | 含义 |
|-------|------|------|
| 很差 | 0 | 基础概念不清，需要从头补 |
| 薄弱 | 1 | 知道概念但容易出错 |
| 还行 | 2 | 中档题基本能做，偶尔犯错 |
| 不错 | 3 | 中档题稳定，较难题有思路 |
| 擅长 | 4 | 难题也能拿分 |
| 不确定 | -1 | 无数据，需要评估 |

---

## 四、知识点级掌握（knowledgePoints）

比模块更细的粒度，精确到具体知识点：

```typescript
interface KnowledgePoint {
  topic: string;           // "一元二次方程-韦达定理"
  mastery: number;         // 0.0 ~ 1.0（掌握概率，BKT 模型）
  errorPatterns: string[]; // ["符号判断错误", "忘记验根"]
  evidence: Evidence[];    // 所有支撑数据
  lastUpdated: string;
}

interface Evidence {
  source: "assessment" | "drill" | "llm";
  result: "correct" | "wrong" | "partial";
  detail?: string;    // 具体错因
  date: string;
}
```

### 知识点编码规范

采用「模块-主题-子项」三级结构：

```
functions.linear.slope          → 函数 > 一次函数 > 斜率
functions.quadratic.vertex      → 函数 > 二次函数 > 顶点式
equations.quadratic.vieta       → 方程 > 一元二次方程 > 韦达定理
triangles.congruent.sas         → 三角形 > 全等 > SAS 判定
circles.tangent.property        → 圆 > 切线 > 切线性质
```

### 掌握度更新规则（BKT 简化版）

```
答对: mastery_new = mastery + (1 - mastery) × learn_rate
答错: mastery_new = mastery × (1 - forget_rate)

learn_rate  = 0.15（默认学习速率）
forget_rate = 0.10（默认遗忘速率）
```

> Phase 1 暂不启用 BKT，直接用刷题正确率映射。Phase 3 接入完整 BKT 模型。

---

## 五、测评记录（assessmentHistory）

```typescript
interface AssessmentRecord {
  id: number;
  date: string;
  answers: number[];          // [1,2,3,0,2,...] 每题选项（0=超时未答）
  score: number;              // 总得分（满分 10）
  moduleResults: Record<ModuleId, {
    level: string;
    weaknesses: string[];     // 检测到的具体弱点
  }>;
  duration: number;           // 总耗时（秒）
}
```

### 数据用途
- 对比多次测评看趋势（进步/退步）
- 提取错题模式用于精准推荐
- 计算模块水平变化曲线

---

## 六、刷题记录（drillHistory）

```typescript
interface DrillRecord {
  id: number;
  module: ModuleId;
  difficulty: "easy" | "medium" | "hard";
  date: string;
  totalQuestions: number;
  correctRate: number;        // 0.0 ~ 1.0
  timeSpent: number;          // 秒
  details: {
    questionId?: string;
    correct: boolean;
    userAnswer?: string;
    knowledgePoint?: string;  // 关联的知识点 ID
  }[];
}
```

### 刷题数据对画像的影响

```
每次刷题完成 → updateModuleFromDrill()
  ├── 正确率 ≥ 90% → level 信号 "擅长"
  ├── 正确率 75~89% → level 信号 "不错"
  ├── 正确率 60~74% → level 信号 "还行"
  ├── 正确率 40~59% → level 信号 "薄弱"
  └── 正确率 < 40%  → level 信号 "很差"

新 level 与旧 level 做 EMA 融合（alpha = 0.3）：
  blended = old_level × 0.7 + new_level × 0.3

每次刷题 confidence += 0.1（上限 1.0）
```

---

## 七、学习计划记录（planHistory）

```typescript
interface PlanRecord {
  id: number;
  date: string;
  inputSnapshot: {           // 生成计划时的输入快照
    district: string;
    currentScore: number;
    targetSchool: string;
    modules: Record<ModuleId, string>;
  };
  planText: string;          // LLM 生成的计划原文
  completionRate?: number;   // 计划完成率（Phase 2）
}
```

---

## 八、画像完整度计算

总分 100，四个维度加权：

```
┌─────────────┬───────┬──────────────────────────────────────────┐
│ 维度        │ 权重  │ 满分条件                                  │
├─────────────┼───────┼──────────────────────────────────────────┤
│ 基础信息    │ 15 分 │ 区域(5) + 学校(5) + 当前分数(5)           │
│ 目标层      │ 15 分 │ 目标学校(8) + 每日时间(7)                 │
│ 学科能力    │ 55 分 │ 7 模块 × confidence 加权平均 × 55         │
│ 行为数据    │ 15 分 │ 角色(5) + 刷题≥5次(5) + 使用≥3天(5)       │
└─────────────┴───────┴──────────────────────────────────────────┘

completeness = basic + goal + academic + behavioral
```

### 完整度→引导语映射

| 完整度 | 引导语 | 推荐动作 |
|--------|--------|---------|
| 0~15% | 画像刚开始建立 | 做一次快速测评 |
| 15~30% | 基础信息已有，学科能力待评估 | 做一次快速测评 |
| 30~60% | 画像基本建立 | 多做刷题让评估更精准 |
| 60~80% | 画像较为完善 | 持续使用会越来越准 |
| 80~100% | 画像已经很完善 | 保持使用，关注趋势变化 |

---

## 九、多来源冲突检测

同一模块有多个来源评估时，需要检测一致性：

```
规则 1：任意两个来源的 level 相差 ≥ 2 级 → 标记冲突
规则 2：冲突时 confidence 自动降至 0.3
规则 3：冲突模块在画像页显示 ⚠️ 提示，建议做针对性测试

示例：
  自评 "擅长函数" (level=4) + 测评函数题做错 (level=1)
  → 差 3 级 → 冲突 → confidence 降至 0.3
  → 提示 "函数模块评估存在矛盾，建议做一次函数专项测试"
```

---

## 十、数据采集时机矩阵

每次用户交互自然采集画像数据，无额外操作负担：

| 用户行为 | 采集的画像数据 | 侵入感 | 实现状态 |
|---------|---------------|--------|---------|
| 首次打开 → 查学校 | 区域、当前分数 | 零（用户主动输入） | ✅ 已实现 |
| 做快速测评 | 7 模块 level + 具体弱点 | 低（用户主动参与） | ✅ 已实现 |
| 生成学习计划 | 目标校、每日时间、自评 | 零（表单必填项） | ✅ 已实现 |
| 刷题 | 正确率、耗时、错题模式 | 零（自动记录） | 🔲 待接入 |
| 再次测评 | level 变化趋势 | 低 | 🔲 待接入 |
| 对话咨询（Phase 2） | 学习偏好、焦虑点、困惑点 | 零（LLM 自然提取） | 🔲 未开始 |
| 登录注册 | 手机号、用户 ID | 零 | ✅ 已实现 |
| 编辑画像 | 学校、目标校、角色 | 低（用户主动编辑） | ✅ 已实现 |

---

## 十一、存储实现

### 当前方案（Phase 1）：SQLite

```sql
-- 用户表
users (
  id          INTEGER PRIMARY KEY,
  phone       VARCHAR(11) UNIQUE NOT NULL,
  nickname    VARCHAR(50),
  role        VARCHAR(20) DEFAULT 'student',
  created_at  DATETIME,
  last_login_at DATETIME
)

-- 学生画像（核心表，1:1 关联 users）
profiles (
  user_id         INTEGER UNIQUE → users.id,
  district        VARCHAR(20),
  school          VARCHAR(50),
  grade           VARCHAR(10),
  current_score   INTEGER,
  target_school   VARCHAR(50),
  target_score    INTEGER,
  hours_per_day   REAL,
  modules_json    TEXT,       -- JSON: Record<ModuleId, ModuleProfile>
  knowledge_points_json TEXT, -- JSON: Record<string, KnowledgePoint>
  preferences_json TEXT,      -- JSON: { role, style, priority }
  completeness    INTEGER,
  updated_at      DATETIME
)

-- 测评记录（1:N）
assessment_records (
  user_id            INTEGER → users.id,
  answers_json       TEXT,
  score              INTEGER,
  module_results_json TEXT,
  created_at         DATETIME
)

-- 刷题记录（1:N）
drill_records (
  user_id         INTEGER → users.id,
  module          VARCHAR(50),
  difficulty      VARCHAR(20),
  correct_rate    REAL,
  total_questions INTEGER,
  time_spent      INTEGER,
  details_json    TEXT,
  created_at      DATETIME
)

-- 学习计划记录（1:N）
plan_records (
  user_id    INTEGER → users.id,
  plan_text  TEXT,
  input_json TEXT,
  created_at DATETIME
)
```

### 未来演进路径

| 阶段 | 存储方案 | 触发条件 |
|------|---------|---------|
| Phase 1（当前） | SQLite 单文件 | — |
| Phase 2 | SQLite + 定期备份 | 用户量 < 1000 |
| Phase 3 | PostgreSQL + Redis 缓存 | 用户量 > 1000 或需要多实例部署 |

---

## 十二、API 接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/auth/send-code` | 发送验证码 | 无 |
| POST | `/api/auth/verify` | 验证码校验 + 登录/注册 | 无 |
| GET | `/api/auth/me` | 获取当前用户信息 | Bearer Token |
| GET | `/api/profile` | 获取画像 | Bearer Token |
| PUT | `/api/profile` | 更新画像（部分更新） | Bearer Token |

### 待新增 API（Phase 2）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/profile/assessment` | 提交测评结果 → 自动更新画像 |
| POST | `/api/profile/drill` | 提交刷题结果 → 自动更新画像 |
| GET | `/api/profile/history` | 获取历史记录（测评+刷题+计划） |
| GET | `/api/profile/trend` | 获取能力变化趋势 |

---

## 十三、迭代路线

### Phase 1 ✅ 已完成
- [x] 手机号验证码登录
- [x] SQLite 用户表 + 画像表
- [x] 画像 CRUD API
- [x] 完整度计算（四维度加权）
- [x] 画像页面（完整度条 + 基础信息编辑 + 模块水平展示）
- [x] AuthProvider 全局登录状态

### Phase 2 — 数据自动回写
- [ ] 测评完成 → 自动写入 assessment_records + 更新 modules
- [ ] 刷题完成 → 自动写入 drill_records + EMA 更新 modules
- [ ] 计划生成 → 自动写入 plan_records
- [ ] 画像页展示历史趋势图
- [ ] 多来源冲突检测 + ⚠️ 提示

### Phase 3 — 知识点级精准追踪
- [ ] BKT 模型接入（知识点掌握概率动态更新）
- [ ] 知识图谱可视化（哪些知识点已掌握/薄弱/未覆盖）
- [ ] LLM 对话诊断（通过追问定位精确错因）
- [ ] 错题本（关联知识点 + 推荐类似题）

### Phase 4 — 高级特性
- [ ] 学习行为分析（最佳学习时段、效率曲线）
- [ ] 同区/同校匿名对比（你的函数水平超过 60% 同区考生）
- [ ] 家长端独立视图（进度报告 + 预警推送）
- [ ] 数据导出（PDF 学习报告）

---

## 附录 A：TypeScript 完整类型定义

> 代码位置：`app/lib/profile.ts`

```typescript
type ModuleId =
  | "numbersAndExpressions"
  | "equationsAndInequalities"
  | "functions"
  | "triangles"
  | "circles"
  | "statisticsAndProbability"
  | "geometryComprehensive";

type LevelSource = "self" | "assessment" | "drill" | "llm";

interface ModuleProfile {
  level: string;
  source: LevelSource;
  confidence: number;     // 0.0 ~ 1.0
  updatedAt: string;
}

interface StudentProfile {
  district: string;
  school: string;
  grade: string;
  currentScore: number;
  targetSchool: string;
  targetScore: number;
  hoursPerDay: number;
  modules: Record<ModuleId, ModuleProfile>;
  knowledgePoints: Record<string, {
    mastery: number;
    errorPatterns: string[];
    lastUpdated: string;
  }>;
  preferences: {
    role: "student" | "parent" | "tutor";
    style: string;
    priority: string;
  };
  completeness: number;
}
```

---

## 附录 B：画像数据流示意

```
用户操作                    触发函数                       画像变化
────────────────────────────────────────────────────────────────────

查学校页填分数     →  (前端 URL 参数传递)          →  currentScore, district
                                                      completeness +10

做 10 题测评       →  updateModulesFromAssessment() →  modules[*].level 更新
                                                      modules[*].source = "assessment"
                                                      modules[*].confidence = 0.6
                                                      completeness +30~40

生成学习计划       →  (plan_records 写入)           →  targetSchool, hoursPerDay
                                                      completeness +15

刷函数专项 20 题   →  updateModuleFromDrill()       →  modules.functions.level EMA 更新
                                                      modules.functions.source = "drill"
                                                      modules.functions.confidence += 0.1
                                                      completeness +2~5

再次测评（2 周后） →  updateModulesFromAssessment() →  modules[*] 全量更新
                                                      可对比趋势
                                                      冲突检测触发
```
