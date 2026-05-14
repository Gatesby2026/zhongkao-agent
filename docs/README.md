# 文档索引

中考智能学习规划项目的所有文档统一收口在 `docs/` 目录下，按三个维度分类：

## 📦 [product/](./product/) — 产品

| 文档 | 说明 |
|------|------|
| [PRD.md](./product/PRD.md) | **产品需求文档主线** v5.0（2026-05-10）— 服务号 + 小程序群聊 UI 架构 |
| [STUDENT-REPORT-FEATURE-SPEC.md](./product/STUDENT-REPORT-FEATURE-SPEC.md) | **学情报告生成**功能标准化规格（v0.1）— 5 步流水线 + 实施路线图 |
| [ANSWER-CARD-OCR-RESEARCH.md](./product/ANSWER-CARD-OCR-RESEARCH.md) | **答题卡 OCR 技术调研**（2026-05-14）— 决策：B 路线兼容任意答题卡 |
| [ANSWER-CARD-OCR-DEMO-RESULTS.md](./product/ANSWER-CARD-OCR-DEMO-RESULTS.md) | **答题卡 OCR 半天 demo 结果**（2026-05-14）— OMRChecker + ArUco 都跑通 |
| [ANSWER-CARD-OCR-TRACKB-RESULTS.md](./product/ANSWER-CARD-OCR-TRACKB-RESULTS.md) | **Track A+B 并行 demo 结果**（2026-05-14）— LLM 标坐标失败，建议重评 A/B 路线 |
| [PRODUCT-REVIEW.md](./product/PRODUCT-REVIEW.md) | 早期 PRD v2.1 评审报告（历史参考） |
| [USER-PERSONA-REPORT.md](./product/USER-PERSONA-REPORT.md) | 用户画像咨询报告 |

## 📐 [specs/](./specs/) — 数据规范

| 文档 | 说明 |
|------|------|
| [STUDENT-PROFILE-SPEC.md](./specs/STUDENT-PROFILE-SPEC.md) | 学生画像数据模型规范 |
| [EXAM-FORMAT-SPEC.md](./specs/EXAM-FORMAT-SPEC.md) | 北京中考各科试卷格式规范 |

## 📚 [knowledge-base/](./knowledge-base/) — 知识库建设

| 文档 | 说明 |
|------|------|
| [KNOWLEDGE-BASE-PLAN.md](./knowledge-base/KNOWLEDGE-BASE-PLAN.md) | 知识库建设方案与迭代计划 |
| [KNOWLEDGE-BASE-REVIEW.md](./knowledge-base/KNOWLEDGE-BASE-REVIEW.md) | 知识库质量评估报告 |
| [KNOWLEDGE-TRACKING-REPORT.md](./knowledge-base/KNOWLEDGE-TRACKING-REPORT.md) | 学生知识掌握动态追踪体系 |
| [EXAM-QUALITY-AUDIT.md](./knowledge-base/EXAM-QUALITY-AUDIT.md) | 数学试卷质量审核报告 |
| [TEACHING-MATERIALS-STRATEGY.md](./knowledge-base/TEACHING-MATERIALS-STRATEGY.md) | 教辅材料数据获取策略 |
| [math-exam-stats.txt](./knowledge-base/math-exam-stats.txt) | 数学考试题量统计 |

---

## 阅读路径建议

**第一次了解项目**：
1. [PRD.md](./product/PRD.md) 第一、四、八、九章（产品定位、产品形态、技术架构、MVP 范围）
2. [USER-PERSONA-REPORT.md](./product/USER-PERSONA-REPORT.md) 了解目标用户

**做后端开发**：
1. [PRD.md](./product/PRD.md) 八、技术架构
2. [STUDENT-PROFILE-SPEC.md](./specs/STUDENT-PROFILE-SPEC.md) 数据模型
3. `../backend/README.md`

**做小程序前端**：
1. [PRD.md](./product/PRD.md) 四、产品形态、六、对话流程设计
2. `../miniprogram/README.md`

**做内容/知识库**：
1. [KNOWLEDGE-BASE-PLAN.md](./knowledge-base/KNOWLEDGE-BASE-PLAN.md)
2. [EXAM-FORMAT-SPEC.md](./specs/EXAM-FORMAT-SPEC.md)
3. [TEACHING-MATERIALS-STRATEGY.md](./knowledge-base/TEACHING-MATERIALS-STRATEGY.md)

---

## 其他参考（不在 docs/ 下）

- `../admin/`（Next.js 管理后台 Web 端，含 components / lib / app 路由 / scripts/paper-scout.js）
- `../miniprogram/README.md` — 微信小程序前端目录与本地预览方法
- `../backend/README.md` — 服务号/小程序后端骨架（待开发）
- `../scripts/` — 流水线脚本，按职责分子目录：
  - `knowledge-base/` — docx/PDF → 题库 YAML、质量检查
  - `exam-ocr/` — 试卷 OCR（含 RECIPE-beijing-exam-fetch.md 检索方法）
  - `answer-card-ocr/` — 答题卡识别（Qwen-VL + Aliyun 手写）
  - `student-report/` — 学情分析报告生成
- `../archived/wechat-bot-ilink-spike/ARCHIVED.md` — 已废弃的 iLink Bot 预研记录
- `~/.claude/projects/-Users-jiakui-projects-zhongkao-agent/memory/wechat-platform-decision.md` — 微信接入选型决策记录（仓库外）
