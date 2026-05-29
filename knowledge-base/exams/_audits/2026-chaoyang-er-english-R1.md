# 2026 北京朝阳英语二模 — R1 审核报告

数据源：
- YAML: `knowledge-base/exams/mock/english/beijing/2026-chaoyang-er.yaml`
- 源 PDF: `knowledge-original/gaokzx-downloads/2026-ermu-english/chaoyang_english.pdf`
- OCR：`_staging/english/2026-chaoyang-er/tencent-cache/general/page-NN.txt`（12 页）

---

## 卷面元数据 + 题数对比

源卷 page-01 明示："本试卷共 10 页，共两部分，**五道大题，38 道小题，满分 60 分，考试时间 90 分钟**"。

| 字段 | 源卷 | YAML | 结论 |
|---|---|---|---|
| year | 2026 | `null` | **P0 缺失** |
| district | 朝阳 | `''` | **P0 缺失** |
| exam_type | 二模 | `真题` | **P0 错** — 朝阳二模是 mock，不是真题；且未标 `一模/二模` |
| subject | english | english | OK |
| full_score | 60 | 60.0 | OK |
| duration_minutes | 90 | `null` | **P0 缺失** |
| total_questions | 38 | 38 | OK |
| structure 描述 | 12 单选+8 完形+13 阅读+4 阅读表达+1 作文 | `25单选(32.0分) + 8cloze(8分) + 4reading_express(10.0分) + 1作文(10分)` | **P0 错** — "25 单选" 把单选(12) + 阅读(13) 当一类合并；分值 32 与卷面任一组合都对不上 |

**审核脑图的"39 题"是 brief 写错**：源卷明确 38 题（第二部分作文为"二选一"算 1 道题位，不是 2 道）。

题数分项实际：12 单选 + 8 完形 + 13 阅读 + 4 阅读表达 + 1 作文 = 38。
YAML 实际 38 条 question 条目 + 3 条 passage 条目 ✓（数量符合）。

题型分项分值：
- 单选 12×0.5 = 6 ✓（Q1–Q12，YAML 全 0.5）
- 完形 8×1 = 8 ✓（Q13–Q20，YAML 全 1）
- 阅读 13×2 = 26 ✓（Q21–Q33，YAML 全 2）
- 阅读表达 Q34–36 各 2 + Q37 4 = 10 ✓（Q34/35/36 score=2.0，Q37 score=4.0）
- 作文 10 ✓（Q38 score=10）
- 合计 60 ✓

但 `structure` 字段拼写错误且分值算式错（32 ≠ 6+26），与 60 总分对不上。生成器只用 `type` 字段统计，没有把单选/阅读区分开。

---

## passage 结构核对

源卷阅读段落（page-03 ~ page-07）：
- **A 篇** Work Experience Day 图片匹配（Q21–23，3 题，0 选项作 D 多余）
- **B 篇** The Day Lisa Lost（Q24–26）
- **C 篇** China's commercial spacecraft（Q27–29）
- **D 篇** Monkeys' facial expressions（Q30–33）

YAML 现有 passages：
| id | type | q_range | 状态 |
|---|---|---|---|
| cloze | cloze | 13–20 | body 大致完整但有 OCR 噪声（"com"、"graffit"、"最在线"、"关注北京高考在线… 微信号:bjgkzx" 长插入串）— **P1** |
| reading_A | reading | **21–33** | **P0 错** — 真实 q_range 应是 21–23（仅 A 篇图配）。**B/C/D 三篇 passage 完全缺失**；Q24–33 全部错挂到 reading_A 名下 |
| express | reading_express | 34–37 | body 完整 ✓，但 Q37 在源卷算"文段表达前的最后一道阅读表达"，对应 module 应该是 reading 而非 writing — **P2** 类别可商榷 |

**P0 阻断性问题**：B/C/D 三篇阅读全文都没有作为独立 passage 写入 yaml。但在 **Q22 的 stem** 里塞了一段约 2000 字的巨型脏块，把 A 篇选项 + B 篇全文（含 The Day Lisa Lost）+ C 篇全文（含 spacecraft）+ D 篇全文（含 facial expressions）+ Q24–Q33 全部题干及选项 + "第二部分"section header 全部粘连在一起。Q22 stem 完全无法作为答题题面使用。

---

## 逐题问题清单

### 第一大题 单项填空 Q1–Q12

| Q | 现状 | 问题 | 等级 |
|---|---|---|---|
| 1 | options.D = `'they\n\n      北京高考在线'` | **P1** 水印 "北京高考在线" 拼入选项 D | P1 |
| 2 | options.A = `'on'` (引号正确) | OK | — |
| 3 | answer=D / solution=D，options 完整 | **P1** — 源卷选项一致；语义校验："Mrs.Zhang, I take more exercise…"+"No, you needn't" → 应是 "should"，YAML 标 D (must) 也行（"No, you needn't" 否定 must/should 都可），但 D 更典型，可接受。但 stem 里 `--Mrs.Zhang, ___ I take more exercise after class?` 的破折号要规范化 | P2 |
| 7 | stem 末尾混入 "关注北京高考在线官方微信:京考一点通 ___ (微信号:bjgkzx)，获取更多试题资料及排名分析信息。" | **P1** 水印污染题干 | P1 |
| 8 | stem 末尾 "北京高考 www.gaokzx.com" 水印 | **P1** | P1 |
| 11 | options.A = `'built\n\n      A. built'`、**options.B 完全缺失** | **P0** 选项严重破损。源卷四选项实际为 A.built / B.is built / C.will build / D.will be built。当前 yaml 只有 A(脏)、C、D。答案 D 正确但选项不完整无法练习 | P0 |
| 12 | solution = `'B\n\n    北京高考在线'` | **P1** solution 字段被水印污染 | P1 |

### 第二大题 完形 Q13–Q20

| Q | 问题 | 等级 |
|---|---|---|
| 13–19 | 选项与源卷一致；body 中第 13/15 空号变成 `___13___` / `___15___`（已加规范下划线）但 14/16/17/18/19/20 在 passage body 中显示为粘连数字（如 `I14 misspelled it`、`it 15 me`）→ Cloze 阅读模式可读性受损 | **P1** body 部分空号未做下划线标准化 |
| 18 | answer=C (meaningful) | 语义检查："my effort had helped others, so the experience still felt ___" → meaningful ✓ |
| 20 | solution = `'B\n\n    www.gaokzx.com'` | **P1** 水印拼接 | P1 |

cloze passage body 含杂质："**graffit**"（被 OCR 重复一次）、"**最在线**"（疑似"最重要的"+水印拼读乱码）、长串 "关注北京高考在线官方微信:京考一点通(微信号:bjgkzx)，获取更多试题资料及排名分析信息。" 整段插入到 16 题前后。**P1**。

### 第三大题 阅读理解 Q21–Q33

整段是这份 yaml 最严重的灾区。

**A 篇图片匹配（Q21–23）**：
- Q21 / 22 / 23 都标 `has_image_options: true`，没有 stem 或挂在 reading_A，但顺序乱：yaml 里 Q23 排在 Q21 前面。**P1** 排序。
- Q21 stem 被填入 `"com www.gao Cathy: I am patient and good at looking Leo: I stay calm when after others. I hope to ..."` — Cathy/Leo 是图中两个人物描述，应该属于 passage 公共背景而不是单题 stem。**P1**
- Q22 stem **=灾难性 stem**：约 2000 字，把 Sam 描述 + A 篇四个选项 NPCD 描述 + B 篇全文 + Q24/25/26 题干 + C 篇全文 + Q27/28/29 题干 + D 篇全文 + Q30/31/32/33 题干 + "第二部分" header 全部塞进一个 stem 字符串。**P0** — 完全不可用，必须重切。
- Q23 stem='' has_image_options=true，answer=A — Q23 在源卷其实是 Cathy（"I am patient … learn more about basic care work"）对应 A. Nurse for a day。答案 A 与源卷对得上但 stem 空且没有把 Cathy 描述放进来。**P0** 缺关键人物 stem
- 配对答案核对（图配源题 21/22/23 在源卷 page-03 的实际位置）：
  - 21 = Leo（消防）→ C. Firefighter ✓ yaml=C
  - 22 = Sam（教学）→ B. Teacher ✓ yaml=B
  - 23 = Cathy（看护）→ A. Nurse ✓ yaml=A
  - 实际答案对得上，但 stem 串错位

**B 篇 The Day Lisa Lost（Q24–26）**：
- Q24 stem='' answer=D（Uncomfortable）— 与源卷 "How did Lisa feel when people talked about her success?" 对应 ✓ 答案对，但 stem 空，必须从 Q22 灾难块里抽 "24. How did Lisa feel…" 行回填。
- Q25 stem='' answer=A（she stopped to encourage Jane）✓ 答案对，stem 空，问题同 Q24。
- Q26 stem='' answer=D（praise an athlete who values sportsmanship over winning）✓ 答案对，stem 空。**knowledge_points 异常**：`未提供题干，无法标注` 三连击（KP / difficulty / recommended_for 全是这串中文标签字面值）— **P1** 是 enrich 在 stem 空时的兜底但仍然不应写入正式字段。
- **passage_id 错挂 reading_A**，应为 reading_B（缺）。

**C 篇 spacecraft（Q27–29）**：
- Q27 stem='' answer=A（reused many times）✓
- Q28 stem='' answer=B（Push forward）✓
- Q29 stem='' answer=C（China's New Commercial Space Project）✓
- 全部 passage_id=reading_A，应为 reading_C（缺）。stem 空缺。

**D 篇 facial expressions（Q30–33）**：
- Q30 stem='' answer=C ✓
- Q31 stem='' answer=B ✓
- Q31 字段最差：`knowledge_points: []`、`difficulty: ''`、`recommended_for: []`（enrich 直接放弃）**P1**
- Q32 stem='' answer=C ✓（但源卷 C 选项 "Monkeys may plan and control their" 被 OCR 截断；选项 D 也截断："Monkeys' expressions depend on slow background changes."）
- Q33 stem='' answer=D ✓
- 全部 passage_id=reading_A，应为 reading_D（缺）。

### 第四大题 阅读表达 Q34–Q37

| Q | answer | solution | 评 |
|---|---|---|---|
| 34 | '' | `By playing outside` | ✓ 语义 OK，结尾少句点（"By playing outside."）**P2** |
| 35 | '' | `(The writer) Richard Louv.` | ✓ 但加 "The writer" 是 yaml 自加注释，且源文是 "writer Richard Louv"，更准是 "Richard Louv." 即可 |
| 36 | '' | `Spending time outdoors both in loneliness and at play.` | ✓ |
| 37 | '' | `略` | **P2** 开放题用"略"合规，但建议给出 sample answer 或评分要点 |
| 37 | module=`writing` | 应为 reading（阅读表达内的开放问答仍是 reading 类别，跟 38 题作文区分）— **P2** |

### 第五大题 文段表达 Q38

- type=`作文` score=10 ✓
- **stem 严重格式破碎**：作文题"题目①"和"题目②"两段被 OCR 拆成 80+ 行碎片（"do volunteer work / 10% / do some reading / 15% / play video games / 考 / com / 北京 / 25% / take exercise"），饼图百分比丢失了"play video games 50%"（源卷写 25 但加和不到 100，应该是 50）。**P1** — 写作两个题目对调研报告型来说，图表数据丢失影响考生作答参考。
- solution 字段含从 "评分标准"（第一档/第二档/第三档/第四档）到"北京高考在线平台简介"长达 1000+ 字的水印底部页脚污染。**P0** solution 长度膨胀，无效信息覆盖正常 sample writing。

---

## 其他横向问题

1. **水印噪声**至少出现 35+ 次，涉及：题号 1/3/7/8/11/12/20/21/22/26 stem 或 solution，cloze body，作文 solution 整大段。pattern 包括：
   - `关注北京高考在线官方微信:京考一点通(微信号:bjgkzx)，获取更多试题资料及排名分析信息。`
   - `www.gaokzx.com` / `北京高考在线` / `京考` / `高考在线` / `最在线` / `com` 单字断片
   - `北京高考` 三字孤立
   - 建议在 image_paper 解析器加 `NOISE_PATTERNS` 黑名单 + 二次 strip。

2. **KP / module 串味**：
   - Q11 knowledge_points = [时态运用, 被动语态] ✓
   - Q21 module=reading ✓
   - Q23 module=reading ✓ 但 Q25 module=vocabulary（应为 reading，A 篇是图配信息筛选）**P1**
   - Q26 knowledge_points='未提供题干，无法标注'（中文字面）**P1**
   - Q31 knowledge_points=[] difficulty='' recommended_for=[]（enrich 完全失败）**P1**
   - Q23 knowledge_points=['vocabulary'] module=vocabulary —— A 篇图配的"信息筛选"反而被打成 vocabulary **P1**

3. **跨学科污染**：未发现 chinese/math/physics 知识点串入。

4. **passage_id 一致性**：reading_A 名下挂了 13 道题（Q21–Q33 都挂同一个 reading_A），但 reading_A passage 只有 A 篇 body —— **P0** B/C/D 三篇 passage 全缺，且 q_range 标 21–33 是 parser 把 4 篇连续区段误判为单一 passage。

5. **题号顺序异常**：question 列表里 Q23 出现在 Q21 之前（line 564 vs 582），其他题号按序，但 Q21/22/23 三题被 Q23 → Q21 → Q22 → Q24 这种顺序排列。**P1**

6. **`_needs_src_page_figure: true` / `_is_image_match: true`**：reading_A 上的 image_match marker 正确（A 篇是图配题），但 figures 目录是否生成需另行核查（`figures/reading_A-options.png` 之类）。

7. **作文饼图数据丢失**：源卷给出 4 个百分比：play video games 50% / take exercise 25% / do some reading 15% / do volunteer work 10%。yaml 里 50% 完全没出现（OCR page-09 line 13 也漏了），导致考生看不到关键数据。**P1** 需要从 PDF 重抽图或手补。

---

## OVERALL: NEEDS_FIX

**P0 阻断（必修）**：
1. metadata: year / district / duration_minutes 三项 null/空；exam_type 错标"真题"应为"模拟"或"二模"；structure 字段算式错
2. reading_B / C / D 三篇 passage 完全缺失，Q24–33 共 10 题 stem 全空且错挂 reading_A
3. Q22 stem 是 2000 字灾难块（4 篇 passage + 10 题面 + section header 全部粘连），完全不可用
4. Q11 options.A 破损（含换行 +重复字面）且 options.B 整个缺失
5. Q23 stem 空但属于"图配人物描述"（Cathy）应回填
6. Q38 solution 含 1000+ 字网页/平台水印长尾

**P1 必清**：
7. 水印模式（北京高考在线 / 微信号:bjgkzx / www.gaokzx.com / 京考一点通 / 高考在线）共 35+ 处污染 stem / solution / options / body
8. cloze body 空号 14/16/17/18/19/20 未规范化为 `___N___` 形式
9. Q21–23 排序错乱（YAML 里 23/21/22 顺序），应按 21/22/23
10. Q31 enrich 失败（KP/difficulty/recommended_for 三空）
11. Q26 KP 字段写入中文 "未提供题干，无法标注" 字面错误兜底
12. Q23 module=vocabulary 错（应为 reading 信息筛选）
13. Q25 module=vocabulary 错（B 篇情节理解，应 reading）
14. Q22 / 28 / 32 等部分原题选项被 OCR 截断（"Monkeys may plan and control their"）
15. 作文饼图丢失 "play video games 50%" 关键数据

**P2 建议**：
16. Q3 stem 破折号格式化
17. Q34 solution 末尾标点
18. Q37 module 改 reading（与 38 作文区分）
19. Q37 solution `略` 可补 sample answer

**整体可用度**：单选 Q1–Q12 基本可用（修水印+Q11 选项即可），完形 Q13–Q20 答案与选项完整可用（修 body 空号格式），阅读 Q21–Q33 **几乎不可用**（缺 3 篇 passage、10 题 stem 全空），阅读表达 Q34–37 可用，作文 Q38 stem/solution 需重建。

**估计修复工作量**：parser 重跑前置 — 需在 english_image_paper.py 加：(a) A/B/C/D 篇 4 段切分（按 `^[A-D]$` 单字符行或 passage 行首字母 anchor）(b) 全局 NOISE_PATTERNS 黑名单 (c) cloze 空号补 `___N___` (d) section header `第二部分` 不要并入 stem (e) Q11 当 OCR 重复同字母选项时去重 + 缺位选项补占位 (f) 二次校验题号顺序 (g) Q26/Q31 enrich KP 写入校验。

建议优先级：先 parser 改 → 重跑 chaoyang-er → 二次过 inspect → 再人工 patch（饼图、作文 sample）。
