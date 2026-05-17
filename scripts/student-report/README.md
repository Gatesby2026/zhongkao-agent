# scripts/student-report/ — 学情分析报告生成（学生向）

把 **试卷结构化 yaml + 学生答题卡 json + 小分 json** → 一份学生向的 PDF 学情报告
（总览仪表盘 / 薄弱诊断 / 逐题精析 / 答题习惯 / 提分计划，失分题内嵌答题卡原图）。

## 用法

```bash
DASHSCOPE_API_KEY=$KEY python3 scripts/student-report/build_report.py \
  --student-dir students/jiaxiaoqi/2026-chaoyang-yi-physics
  # --standard <yaml>   不传则从目录名自动推断
  # --skip-pdf          只出 Markdown
```

## 输入（新数据约定）

| 来源 | 路径 | 关键字段 |
|---|---|---|
| 试卷结构化 | `knowledge-base/mock-exams/<subj>/beijing/<slug>.yaml` | stem/answer/solution/score/knowledge_points/module/difficulty |
| 学生作答 | `students/<name>/<exam-slug>/answer-card.json` | 选择题 filled / 主观题 handwritingText + grade(看图评分) |
| 最终得分 | `students/<name>/<exam-slug>/scores.json` | 每题 scored/fullScore |
| 学生信息 | `students/<name>/<exam-slug>/student.json` | name/examId（可选） |

## 输出

`learning situation/<姓名>_<exam-slug>_学情报告.{md,pdf}`
（PDF 由 `~/.claude/skills/md-to-pdf` skill 生成，中文字体 + 内嵌答题卡原图）

## 流程

```
1. lib/schemas.load_exam_view()   join 三方 → ExamView（每题 QView）
2. lib/aggregate.*                程序聚合（零 LLM）：模块/难度/知识点/大题得分率
3. lib/analyze.analyze_question() 逐失分题归因（qwen-max，并发，.cache）
                                  ↳ 事实约束：选择题用 filled vs answer；
                                    主观题用 grade.missedPoints/scoreReason
4. lib/analyze.analyze_overall()  整卷综合（学生向：亮点+薄弱+行动计划）
5. build_report.render_markdown() 渲染 MD（失分题内嵌 file:// 答题卡原图）
6. md-to-pdf skill convert.sh     → PDF
```

## 文件

| 文件 | 职责 |
|---|---|
| `build_report.py` | 主编排 + Markdown 渲染 + 调 md-to-pdf |
| `lib/schemas.py` | 三方 join → ExamView/QView；exam_title 从 slug 解析 |
| `lib/aggregate.py` | 程序聚合（无 LLM）：模块/难度/知识点/大题 |
| `lib/analyze.py` | LLM prompt（学生向单题归因 + 整卷综合）+ 输出漂移防御 |
| `lib/llm.py` | DashScope thin 层 + `.cache`（反复跑省 token） |

## 设计原则

- **失分原因基于事实**：LLM 只归纳不编造。选择题失分=程序确定；主观题失分=
  answer-card.json 的 `grade.missedPoints/scoreReason`（看图阅卷事实）
- **学生向语气**：直接说"你"，给可执行训练动作，不灌鸡汤
- **正向收尾**：最后一节"你做得好的地方"，引用真实数据稳信心

## 上游 / 下游

- 上游：`exam-ocr/`（试卷 yaml）+ `answer-card-ocr/`（答题卡 json，含 Phase C 看图评分）
- 下游：PDF 手动发学生/家长

## 跨考试趋势（预留）

schemas/aggregate 按单场设计。多场对比时：`overall_stats` 加 history 维度，
报告"总览"加趋势小节（当前单场显示"首次记录"）。

## 已用记录

- 贾小淇 · 2026 朝阳一模 · 物理 — 60/70，8 失分题，6 张答题卡原图，PDF 6.8MB
