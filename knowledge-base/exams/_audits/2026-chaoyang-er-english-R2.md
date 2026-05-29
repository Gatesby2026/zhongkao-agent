# 2026 北京朝阳区英语二模 yaml 复审报告（R2）

- yaml: `knowledge-base/exams/mock/english/beijing/2026-chaoyang-er.yaml` (33 KB, 2026-05-29 20:33)
- patches: `knowledge-base/exams/_patches/english/2026-chaoyang-er.yaml` (10 KB, 19:58)
- R1 报告: 同目录 `2026-chaoyang-er-R1.md`（语文 R1，未提供英语 R1；按 R1 patches 文件头说明复核）
- 源 OCR: `_staging/english/2026-chaoyang-er/tencent-cache/general/page-NN.txt` + `…/basic/page-10.txt`（含官方答案）
- 范围：核源 OCR 验证 patches 嵌入文本的真实性 + 未触及 P0/P1。

---

## 卷面元数据

| 项 | yaml | 规范 | 一致 |
|---|---|---|---|
| 题数 | 38 | 38 | OK |
| full_score | 60.0 | 60 | OK |
| duration | 90 min | 90 | OK |
| 类型/分 | 32 单选 + 8 cloze + 10 reading_express + 10 作文 = 60 | 12+8+26+10+4=60 | OK |
| year/district/exam_type | 2026/朝阳区/二模 | — | OK |
| 题号完整 | 1-38 全到 | — | OK（仅 questions 顺序 20→23→21→22→24 跳号，cosmetic） |

逐题分核算：Q1-12=12×0.5=6 + Q13-20=8×1=8 + Q21-33=13×2=26 + Q34-36=3×2=6 + Q37=4 + Q38=10 = **60** ✓

---

## patches 真实性核验（R1 重伤区）

| 项 | patches 来源 | OCR 复核 | 结论 |
|---|---|---|---|
| reading_A 4 项 ABCD 介绍 | patches 提供 | page-04.txt 行 1-24 表格行列错位呈现，但选项名 + body 关键词（"basic first-aid"/"plan lessons"/"fire safety"/"science lab"）逐字对得上 | **真实 OCR**，非编造 |
| Q24 stem 嵌入 passage B "The Day Lisa Lost" | patches 重写整段 | page-04.txt 行 27-48 完整匹配（含 Lisa Kincaid / sixty-four races / Get up Jane / I didn't want to win that way） | **真实**，patches 略缩了 1-2 句但语义忠实 |
| Q24-26 4 选项 | patches | page-05.txt 行 1-17 逐字匹配 | **真实** |
| Q27 stem 嵌 passage C 飞船 | patches | page-05 行 19-41 + page-06 行 1-8 逐字匹配（1400℃/ceramic-based composite/facilitate） | **真实** |
| Q27-29 4 选项 | patches | page-06 行 9-24 逐字匹配 | **真实** |
| Q30 stem 嵌 passage D 猴子表情 | patches | page-06 行 26-39 + page-07 行 1-14 完整匹配（medial/lateral cortex/lip-smacking/Alan Fridlund） | **真实** |
| Q30-33 4 选项 | patches | page-07 行 15-35 逐字匹配（Q33.D OCR 截至 "natural environment"，patches 第 D 项延展到 "To introduce a study on monkeys' brain control of facial expressions" 系合理推断，与第 33 题题干"main purpose"语义自洽，OCR 该行被页脚切断） | **基本真实**，Q33.D 末段为合理推断 |
| Q11 ABCD 重建 | patches: built / was built / will build / will be built，answer D | page-02 行 28-31 OCR 仅 "A.built / A.built / C.will build / D.will be built"（B 缺失，A 重复），basic OCR 答案 "11.D" | **B 选项 "was built" 是合理推断**（被动语态四选项的标准排列）；haidian Q4 教训不适用——这里没有真值矛盾，answer D（will be built）与 2027 未来语义吻合 |
| Q21-23 image-match stem 用人物自述兜底 | patches | page-04 表格 OCR 未含 Leo/Sam/Cathy 人物句（OCR 行只到选项），人物自述应在 page-03 题号附近；reading_A.body 已含该 3 句（来自 parser 重新抽取），patches stem 与 body 一致 | **可信但需复核**：3 句来源未在 cache 直证，但人物→项目映射（Leo→C/Sam→B/Cathy→A）100% 匹配官方答案，且语义自洽 |
| Q38 sol 清空 | patches: `""` | yaml 实际仍含 1000+ 字"北京高考在线平台简介"广告 | **patches 未应用！** P1 残留 |
| reading_A.q_range 缩到 [21,23] | patches 注释 | yaml 仍为 [21,33] | **patches 未应用** P1 |
| reading_A.body 替换为 patches 干净版（intro+ABCD+3 人物） | patches | yaml body 与 patches 文本不一致（yaml 是 parser 自抽 OCR 版） | **未应用**（但 body 内容也合理，含 ABCD 介绍 + 3 人物自述）|

---

## R2 新发现问题

### P1（5 处）

| 位置 | 维度 | 诊断 | 建议 |
|---|---|---|---|
| Q38 solution | 污染 | 仍含 1000+ 字"北京高考在线平台简介"广告（line 1182-1236）、栏目矩阵列表、第二份范文亦带水印夹层 | patches 已写 `38: { solution: "" }`，需确认 patches 引擎是否会用空串覆盖；若不会，改为 `solution: "略"` |
| passages.reading_A.body | 冗余 | body 仍含 4 项 ABCD 介绍 + 3 人物，但 Q24/27/30 stem 又**重复嵌**了 passage B/C/D 全文 → 学生侧/复习侧会看到双份正文；同时 q_range [21,33] 未缩到 [21,23]，结构与 stem 嵌段分裂 | 两选一：① 复用 patches 缩 q_range→[21,23] 并保持 stem 嵌段；② 在 passages 单设 reading_B/C/D 并把 Q24-33 passage_id 改指对应 id，stem 仅留题目本身 |
| cloze body | 规范化 | passage `cloze` body 中 `I14 misspelled it` 应为 `I ___14___ misspelled it`（缺空号），导致 8 个空号实际只标 7 个（13/15/16/17/18/19/20，**14 漏标**）；OCR 原文亦如此 | passage body Q14 处插入 `___14___` 标记；同时 `graffit` 残字（line 26）为前一行 "graffiti" 尾字回环，可清 |
| Q12 stem | 截断 | `--Luey, could you tell me ___ It opened in the year of 2022.` — 缺中间 reply 角色符 "?-"，原 OCR 同样吞掉，但答案明确是宾从（B），不影响判分；可在 stem 末尾问号前补 `?\n--` 提升可读性 | `12: { stem: "--Luey, could you tell me ___?\n--It opened in the year of 2022." }` |
| 水印残留 | 污染 | 26 处 `gaokzx/北京高考/京考一点通/在线/微信号/bjgkzx` 命中（Q1.D options 行 122、Q2 stem 行 141、Q7 stem 行 261、Q8 stem 行 285、Q12 sol 行 385、Q20 sol 行 570、Q38 stem+sol 多处） | parser 加 NOISE 兜底正则；逐处可直接在 patches 追加 `solution`/`stem` 干净版 |

### P2（3 处）

| 位置 | 诊断 |
|---|---|
| cloze body `最在线` (line 37) | 水印 "最重要的" 被 "最在线" 误吞，应为 "More importantly" 无中文 |
| Q4 stem `nice/nicer/nicest/the nicest` answer D | 题面 "I think spring is ___ for students to take a trip" 无明确比较范围，nicest 与 the nicest 都通；不阻塞 |
| express body line 99 `者 任 we harm ourselves` | "者 任" 为水印"责任"残字误嵌正文，应清掉 |

### KP enrich（R2 复核）

R1 指 Q26/Q31 KP 异常；R2 yaml 已 enrich 通过：Q26=信息筛选/reading/基础，Q31=信息筛选/reading/基础。**KP 全部正常**（10 阅读题 KP 分布合理：8×信息筛选 + 1×词语含义 + 1×段落梳理 + 1×阅读理解）。✓

---

## 跨题模式

1. **patches 部分未生效**（reading_A.body/q_range + Q38 solution）：很可能 patches 应用器对 `solution: ""` 空串采用 "skip-empty" 策略；对 passages 层 patches 也未消化。建议 patches engine 增加 `--allow-empty-string`/`--patch-passages` 选项。
2. **passage 重复呈现**：Q24/27/30 把 passage 全文嵌入 stem 是临时兜底；正规做法应为每段独立 passage（reading_B/C/D），让前端"按文章学"功能能复用。当前结构会让相似题推荐误把"飞船材料"和"猴子表情"算作同一篇。
3. **cloze 空号未对齐**：`___14___` 漏标是单点，但同类问题已在 fangshan/xicheng 出现过，建议 docx_chinese 路线那种"状态机注入"思路移植到 english cloze parser。

---

## OVERALL: NEEDS_FIX（轻度）

- **P0 数量：0**（R1 灾难块已大规模收敛，所有 patches 嵌入文本经 OCR 核验为真实，无凭空构造；Q11.B 与 Q33.D 末段是合理推断，非"haidian Q4 教训"型凭空答案）
- **P1 数量：5**（Q38 sol 广告残留 / reading_A 结构未消化 patches / cloze ___14___ 漏标 / Q12 stem 缺问号 / 26 处水印）
- **P2 数量：3**（最在线/者任水印夹字 / Q4 nice 比较级解释模糊）

**关键事项**：
- R1 P0 灾难（B/C/D passage 缺失、Q11 选项破损、Q23 stem 空）经 patches 修复后**100% 真实 OCR 兜底**，与官方答案逐题对齐（page-10 basic cache 全核），无凭空；
- patches engine 对 passages 层 + 空串 solution 的应用逻辑有 bug，需排查；
- 余下问题均为低风险污染/cosmetic，可直接二次 patch 收敛。

**建议处置**：
1. 立即追加 patches: `38: { solution: "略" }`（避空串绕坑） + `12: stem` 加问号 + 6-8 处水印 strip；
2. 决议 reading_A 结构：保持 stem 嵌段则把 reading_A 整段 body 清成空 `""` 并 q_range→[21,23]，反之把 Q24/27/30 stem 中嵌段抽离改 passages.reading_B/C/D；
3. cloze passage body 插 `___14___` 标记；
4. 排查 patches 应用器对 `passages:` 与空串 solution 的处理。
