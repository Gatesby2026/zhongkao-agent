# 学情报告生成 — 产品功能标准化规格

> **版本**：v0.1 草案 | **更新日期**：2026-05-13
> **关联文档**：[`PRD.md`](./PRD.md) v5.0 · [`../../scripts/README.md`](../../scripts/README.md)
> **目标**：把目前"手工 + 半自动"的学情报告流程固化为家长用户可一键触发的产品功能

---

## 一、产品愿景

### 1.1 用户故事

**家长视角**（主要用户）：
```
家长扫码进入「李同学的私人教研组」小程序
→ 班主任主动推送："这次朝阳一模成绩出来了，要不要做个详细分析？"
→ 家长点"分析"，进入流程：
   1) 选择考试（朝阳 2026 一模 · 物理）— 系统自动识别科目
   2) 上传 / 拍照学生答题卡（4 张物理答题卡）
   3) 输入或上传小分（自动 OCR 表格 / 手工输入每题分数）
→ 系统 30 秒内生成《学情分析与提分建议》PDF
→ 班主任在群里发分析卡片：「我看了子涵的卷子，重点要补电学综合，详细看这里 ↗」
→ 点开 = 完整 PDF 报告
```

**老师视角**（运营侧）：
```
管理后台批量处理一个班级的小分 + 答题卡 → 一次产出 30 份个性化报告
```

### 1.2 已实现的 MVP 案例

已成功手工生成 **3 份**学情报告（贾小淇 · 2026 朝阳一模）：
- 数学 79/100（[贾小淇_2026朝阳初三一模_学情诊断与提分建议.pdf](../../../zhongkao-agent/learning%20situation/)）
- 语文（同上目录）
- 物理 60/70（[贾小淇_2026朝阳初三一模物理_失分分析与提分建议.pdf](../../../zhongkao-agent/learning%20situation/)）

**手工耗时**：每份约 1-2 小时（含人工核对）。**目标自动化后**：≤ 5 分钟。

---

## 二、五步流水线 — 现状盘点

| 步骤 | 自动化程度 | 现有产物 | 主要缺口 |
|------|-----------|---------|---------|
| 1. 试卷下载 | 🟡 半自动 | `RECIPE-beijing-exam-fetch.md` + `paper-scout.js` | gaokzx adapter 未做，需人工找 URL |
| 2. 试卷结构化 | 🟢 已就绪 | `cloud-ocr-exam.py` + `structure-exam-*.py` | 答案页（题目 vs 答案）切分手工 |
| 3. 答题卡识别 | 🟡 半自动 | `qwen-answer-card-ocr.py` | **涂卡 OCR 不可靠**（核心痛点） |
| 4. 小分解析 | 🔴 无 | 临时 openpyxl | 表格格式百花齐放，无标准 schema |
| 5. 报告生成 | 🟡 半自动 | `build-student-analysis-report.py` 框架 + 手工 LLM | 错题分析 prompt 未固化 |

---

## 三、各步详细规格（含数据契约）

### 步骤 1：试卷下载

#### 输入（用户提供）

```typescript
interface ExamIdentifier {
  city: '北京'              // 目前只支持北京
  district: string         // '朝阳' | '海淀' | ...
  grade: '初三'
  examType: '一模' | '二模' | '期中' | '期末' | '中考真题'
  year: number             // 2026
  subject: '语文' | '数学' | '英语' | '物理' | '化学' | '道法' | '历史' | '生物' | '地理'
}
```

#### 输出（系统产出）

```
data/<exam-slug>/
├── manifest.json                # 数据来源 + 文件清单
├── <subject>-pages/
│   ├── page-01.png              # 试卷扫描页
│   ├── ...
│   └── page-NN.png              # 含答案页
└── source.html                  # 源页 HTML 备份
```

`manifest.json` 标准 schema：
```json
{
  "exam": { "city": "北京", "district": "朝阳", "grade": "初三",
            "examType": "一模", "year": 2026, "subject": "物理" },
  "source": {
    "name": "北京高考在线",
    "url": "https://www.gaokzx.com/gk/zhongkao/154733.html",
    "fetchedAt": "2026-05-13T10:00:00Z"
  },
  "pages": {
    "questions": ["page-01.png", "..., "page-08.png"],
    "answers":   ["page-09.png", "page-10.png"]
  }
}
```

#### 实现路径

**阶段 1（短期，1 周）**：扩展 `admin/scripts/paper-scout.js` 加 `gaokzx` adapter：

```js
// admin/scripts/scouts/gaokzx.js  (新)
async function discover({ year, examType, district, subject }) {
  // 1. 抓 gaokzx 一模二模汇总页
  // 2. 在表格里 grep 出 <district> 行 + <subject> 列的详情页 URL
  // 3. 返回 { sourceUrl, ... }
}
async function fetch(sourceUrl, outDir) {
  // 1. curl 详情页 HTML → out/source.html
  // 2. 从 HTML 解析所有 cdn.gaokzx.com/zixunzhan/*.png
  // 3. 按顺序下载 → out/<subject>-pages/page-NN.png
  // 4. 写 manifest.json
}
```

**阶段 2（中期）**：加更多源（教习网+人工滑块、夸克网盘公开链）。

**阶段 3（长期）**：监控类、定时全量抓取（一模 5 月、二模 6 月、期中/期末 11-1 月）。

#### 已知风险

- ⚠️ gaokzx 短链可能失效 — manifest 中记录 fetchedAt，本地永久缓存
- ⚠️ 某些区某些科目缺失 — 兜底走"上传 PDF" 路径
- ⚠️ 法律边界 — 只爬公开页面，不绕付费墙；用户上传的家长版图片永远合法

---

### 步骤 2：试卷结构化

#### 输入

`data/<exam-slug>/<subject>-pages/*.png` + `manifest.json`

#### 输出

```
data/<exam-slug>/processed/<subject>/
├── structured-cloud/
│   ├── final.json                ⭐ 主要产物
│   ├── final.md                  调试用人类可读版
│   └── validation-report.json
├── cloud-ocr/                    原始 OCR 结果
└── answer-key.json               ⭐ 新增 — 答案与评分参考
```

`final.json` schema（已实现）：
```json
{
  "questions": [
    {
      "id": "Q12",
      "type": "choice" | "multi_choice" | "fill_blank" | "calculation" | "experiment" | "essay",
      "section": "一、单项选择题",
      "score": 2,
      "stem": "如图所示，是小阳设计的测量液体密度的装置图...",
      "options": [
        { "label": "A", "text": "可将电流表改装为测量液体密度的仪表" },
        { "label": "B", "text": "..." },
        { "label": "C", "text": "..." },
        { "label": "D", "text": "..." }
      ],
      "figures": ["fig-q12-a.png"],
      "sourcePages": ["page-03"]
    }
  ],
  "metadata": {
    "totalScore": 70,
    "questionCount": 26,
    "sectionStructure": [
      { "section": "一、单项选择题", "qRange": [1, 12], "totalScore": 24 },
      { "section": "二、多项选择题", "qRange": [13, 15], "totalScore": 6 },
      ...
    ]
  }
}
```

`answer-key.json` schema（**新增，待开发**）：
```json
{
  "answers": [
    { "id": "Q1", "correct": "C" },
    { "id": "Q12", "correct": "C" },
    { "id": "Q15", "correct": ["A", "B", "D"], "partialCreditRule": "选对但不全得1分,错选0分" },
    { "id": "Q16", "correct": ["不变", "晶体", "引力"], "score": 3 },
    { "id": "Q25", "correctSolution": "...完整解题过程...", "keySteps": ["...", "..."], "score": 4 },
    ...
  ]
}
```

#### 实现路径

**已就绪**：试卷题目部分。

**待开发**：
1. **答案页自动识别**：每张 PNG 扫一遍，识别"答案及评分标准"标题 → 划分 questions / answers 页
2. **答案结构化**：把答案页 OCR 结果 → 标准 `answer-key.json`
   - 选择题：直接读答案表格 ABCD
   - 填空题：抽取每空标准答案
   - 大题：抽取每步给分要点
3. **题目与答案匹配**：按题号映射 questions[i].id ↔ answers[j].id

预估工作量：3-5 天。

---

### 步骤 3：答题卡识别

#### 输入（用户提供）

- 学生答题卡照片（HEIC / JPG / PNG，1-N 张）
- 关联的试卷标识（哪个考试的答题卡）

#### 输出

`data/<exam-slug>/students/<student-id>/answer-card.json`：
```json
{
  "student": { "name": "贾小淇", "examId": "17020950" },
  "rawImages": ["IMG_1929.jpg", "IMG_1930.jpg", ...],
  "answers": [
    { "qId": "Q1",  "type": "choice",    "filled": "C", "confidence": 0.95 },
    { "qId": "Q12", "type": "choice",    "filled": "B", "confidence": 0.91 },
    { "qId": "Q15", "type": "multi_choice", "filled": ["A","B"], "confidence": 0.88 },
    { "qId": "Q16", "type": "fill_blank", "rawText": "(1) 不变 (2) 引力", "ocrConfidence": 0.85 },
    { "qId": "Q25", "type": "calculation", "rawText": "R = U/I = 2V/10mA = 200Ω ...", "ocrConfidence": 0.80 }
  ]
}
```

#### 实现路径

**关键技术挑战**：涂卡 OCR 不可靠（Qwen-VL 多次把已涂格识别错）。

详细调研见 [ANSWER-CARD-OCR-RESEARCH.md](./ANSWER-CARD-OCR-RESEARCH.md)。

**决策（2026-05-14）**：选 **B 路线 — 兼容任意答题卡**（牺牲准确率换零摩擦）：

| | A. 标准答题卡 | **B. 任意答题卡** ✅ |
|---|---|---|
| 准确率 | 98%+ | ~90% |
| 用户体验 | 家长需打印 PDF | **零摩擦** |
| 周期 | 3-4 周 | 6-8 周 |

**架构**：
```
家长拍照 → 模糊度检测 → 透视矫正
   ↓
   ├─ 涂卡区：OpenCV CV pipeline（基于 OMRChecker 改）
   └─ 手写区：Qwen-VL-Max（保留）
   ↓
[置信度]
   - 高置信 → 直接出结果
   - 低置信（10% 题） → 小程序内 UI 让家长 1 秒确认
```

**关键事实（防止重复研究）**：
- 国内三大云的"教育 OCR"全是切印刷试卷，**没有商业涂卡 OMR API**
- LLM 视觉模型对涂卡 fill ratio 判断天生不擅长，换模型解决不了
- C 端"手机拍 + 任意答题卡"自动批改在中国市场**没有先例**——技术上必须自建

---

### 步骤 4：小分解析

#### 输入（用户提供）

任意之一：
- **A. 上传 xlsx**：班级小分表（如 `6班一模物理小分.xlsx`）
- **B. 上传截图**：手机拍的小分通知截图
- **C. 手工录入**：小程序里逐题输入分数

#### 输出

`data/<exam-slug>/students/<student-id>/scores.json`：
```json
{
  "examTotal": { "scored": 60, "fullScore": 70 },
  "questions": [
    { "qId": "Q1",  "scored": 2, "fullScore": 2 },
    { "qId": "Q12", "scored": 0, "fullScore": 2, "isWrong": true },
    { "qId": "Q15", "scored": 1, "fullScore": 2, "isPartial": true },
    { "qId": "Q20", "scored": 2, "fullScore": 4, "isPartial": true },
    ...
  ],
  "lostPoints": { "total": 10, "byQuestion": [{"qId":"Q12","lost":2}, ...] }
}
```

#### 实现路径

**A. xlsx 解析（最快）**：
- 不同学校的 xlsx 格式有差异，但**列基本固定**：题号 + 满分 + 得分
- 用规则匹配题号格式（"12(2_0)" → qId=Q12, fullScore=2）

**B. 截图 OCR**：
- 调 Aliyun 教育 OCR `recognize-edu-paper-structed` 提表格
- 或用 PaddleOCR + 表格识别模型

**C. 手工录入**：
- 小程序里展示题号列表，每题一个数字输入框
- 默认值 = 满分（家长改"丢分"题即可）

预估工作量：A + C 两天，B 加 3 天。

---

### 步骤 5：综合分析生成报告

#### 输入

来自前 4 步的：
- `final.json`（试卷题目）
- `answer-key.json`（标准答案）
- `answer-card.json`（学生答案）
- `scores.json`（学生小分）
- 学生历史档案（如果有）

#### 输出

`learning situation/<student>_<exam-slug>_分析报告.pdf` + `.md`

#### 算法/Prompt 设计

**1. 失分聚焦**：
```python
focused_questions = [
    q for q in scores.questions
    if q.isWrong or q.isPartial
]
```

**2. 每题错因分析 — 标准 Prompt**：
```
角色：你是该学科教师。

输入数据：
- 题目: {q.stem}（含选项/图）
- 标准答案: {answer_key.correct}
- 学生答案: {student.filled}
- 学生扣分: -{lost}/{full}

请输出 JSON：
{
  "knowledgePoint": "电学综合 / 串联分压",
  "errorType": "概念错 | 计算错 | 审题漏 | 表述不规范 | 读图错 | 其他",
  "rootCause": "(50-100 字)",
  "improvement": "(50-100 字，具体可执行)",
  "similarQuestions": ["...知识库里同知识点题目 ID..."]
}
```

**3. 整卷综合分析 — Prompt**：
```
学生失分分布：{各题失分汇总}
请输出：
- 三大失分主因（聚类）
- 知识点掌握情况按板块评分（声光热/力学/电学/...）
- 提分优先级（按ROI排序）
- 4 周备战清单
- 本次考试的肯定面（避免打击）
```

**4. 报告渲染**：
- MD 模板（已有 v1）→ HTML（用 KaTeX 渲染公式）→ Chrome --headless=new → PDF

#### 实现路径

主要工作：
1. 把已生成的 3 份报告的**模板**抽取出来 → `report-template.md.j2`
2. 把 LLM prompt 固化到代码里（不再每次手写）
3. 把 `build-student-analysis-report.py` 改造成完整流水线

预估工作量：4-6 天。

---

## 四、用户侧 UI 流程（小程序）

```
┌──────────────────────────────────────┐
│ [李同学的私人教研组] 群聊 UI         │
├──────────────────────────────────────┤
│ 张老师·班主任                          │
│ 朝阳一模成绩出来了 📊                  │
│ 要不要做个详细分析？我让科任老师看看   │
│                                       │
│ [✨ 生成学情分析] ← 点击触发           │
└──────────────────────────────────────┘
        ↓ 跳转分析创建页
┌──────────────────────────────────────┐
│ 第 1 步：选考试                        │
│   2026 朝阳一模 · 物理  ✅            │
│                                       │
│ 第 2 步：上传答题卡                    │
│   [+ 拍照] [+ 从相册]                  │
│   预览 4 张 ✅                         │
│                                       │
│ 第 3 步：录入小分                      │
│   [上传 Excel] [手动输入]              │
│   总分 60/70 ✅                        │
│                                       │
│ [开始分析] →                           │
└──────────────────────────────────────┘
        ↓ 后端处理（~30秒）
┌──────────────────────────────────────┐
│ 处理中... ✨                          │
│  ✓ 识别答题卡                          │
│  ✓ 对照标准答案                        │
│  ⏳ AI 老师分析每道错题                │
│  ⏳ 生成报告...                        │
└──────────────────────────────────────┘
        ↓
┌──────────────────────────────────────┐
│ 学情分析已生成 🎯                      │
│                                       │
│ [📄 查看 PDF 报告]                     │
│ [💬 让王老师在群里讲讲]                │
│ [📌 加到学习计划]                      │
└──────────────────────────────────────┘
```

---

## 五、实施路线图

按"先打通端到端、再优化各环节"原则：

### 第 1 周（脚手架）— Pipeline MVP

| 任务 | 产物 |
|------|------|
| 定义标准 schema 文件 | `schemas/{manifest,final,answer-key,answer-card,scores}.schema.json` |
| 串联现有脚本成 CLI | `scripts/student-report/pipeline.py <exam-slug> <student-id>` |
| 测试：复现贾小淇物理报告 | 端到端跑通 |

### 第 2 周（最大风险点 1）— 涂卡 CV 流水线

| 任务 | 产物 |
|------|------|
| 答题卡边界检测 + 透视矫正 | `scripts/answer-card-ocr/bubble-detect.py` |
| 单选/多选格子定位（模板法） | 同上 |
| 填涂度阈值 | 用贾小淇 4 张卡 + 至少 5 张其他学生卡校准 |

### 第 3 周（最大风险点 2）— 答案页结构化

| 任务 | 产物 |
|------|------|
| 答案页自动识别 | `scripts/exam-ocr/extract-answer-key.py` |
| 选择题 ABCD 表格 OCR | 同上 |
| 大题给分要点抽取 | LLM 辅助 |

### 第 4 周（产品化）— 试卷检索 + 报告渲染

| 任务 | 产物 |
|------|------|
| gaokzx adapter | `admin/scripts/scouts/gaokzx.js` |
| 报告 LLM prompt 固化 | `scripts/student-report/prompts.py` |
| 报告模板（J2） | `scripts/student-report/report-template.md.j2` |

### 第 5-6 周（小程序集成）

| 任务 | 产物 |
|------|------|
| 后端 API（4 个端点） | `backend/api/student-report/` |
| 小程序 UI（3 步表单 + 报告查看页） | `miniprogram/pages/student-report/` |
| 班主任群聊触发 | 联动现有群聊 UI |

---

## 六、4 个 API 设计（前后端契约）

### POST `/api/exam/discover`
请求：`ExamIdentifier` → 返回：`{ examSlug, paperReady: bool, manifest? }`
（已有缓存就直接返回；没有就触发抓取任务，返回 task_id 让前端轮询）

### POST `/api/student-report/upload-card`
请求：multipart files + `{ examSlug, studentId }` → 返回：`{ answerCardId, ocrPreview }`
（前端展示 OCR 结果让家长核对涂卡题）

### POST `/api/student-report/score`
请求：multipart xlsx 或 JSON 直接录入 → 返回：`{ scoresId, lostPointsPreview }`

### POST `/api/student-report/generate`
请求：`{ examSlug, studentId, answerCardId, scoresId }` → 返回：`{ taskId }`
SSE / WebSocket 实时推送进度 → 完成时返回 `{ pdfUrl, mdUrl }`

---

## 七、数据隐私

- 学生姓名、答题卡、报告等 **不进入公共仓库** 已 gitignore（`learning situation/`、`students/`）
- 后端存储：学生数据按 `unionid` 隔离，单租户
- 报告 PDF 仅家长本人可访问，**链接含一次性签名 token**，1 小时过期

---

## 八、已知关键风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 🔴 涂卡 OCR 准确率低 | 选择题失分判断错误 | UI 让家长二次确认；阶段 B CV pipeline |
| 🟡 试卷源不稳定 | gaokzx 短链 / 政策变化 | 多源 fallback + 用户上传兜底 |
| 🟡 答案页结构化失败 | 报告缺标答对照 | 关键失分题用 LLM 补 + 人工备份 |
| 🟢 小分表格百花齐放 | xlsx 解析失败 | 多种 fallback（截图 OCR、手工录入） |
| 🟡 LLM 错题分析质量不稳 | 报告内容生硬/不准 | 固化高质量 prompt，对照已有 3 份案例做回归测试 |

---

## 九、与 PRD 主线的关系

本功能是 [PRD v5.0](./PRD.md) **「私人教研组」**模型中**最高频、最有价值**的一项：

- **频次**：每年至少 6 次（开学摸底 + 期中 + 期末 + 一模 + 二模 + 中考）
- **价值**：直接回答家长五问中的 Q2「差的这些分从哪里补」+ Q4「这周做了没进步了没」
- **触达**：与"小程序群聊 UI" + "服务号订阅消息推送"天然结合

---

## 十、术语表

| 术语 | 含义 |
|------|------|
| exam-slug | 考试唯一标识，格式 `chaoyang-2026-yimo-physics` |
| 试卷结构化 | 把扫描页 OCR + 题号识别 + 题型分类 + 选项/题干分离 → 标准 JSON |
| 涂卡 | 选择题答题卡的黑色填涂格 |
| 失分主因 | 同一类错误的聚类标签（如"电学综合分析能力不足"） |
| 五问 | 家长最关心的 5 个问题（见 PRD §1.3） |
