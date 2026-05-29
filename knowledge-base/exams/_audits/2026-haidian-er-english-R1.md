# 2026 北京海淀 英语 二模 yaml 审核报告 R1

- yaml: `/Users/jiakui/projects/zhongkao-agent/knowledge-base/exams/mock/english/beijing/2026-haidian-er.yaml`
- 源 PDF: `/Users/jiakui/projects/zhongkao-agent/knowledge-original/gaokzx-downloads/2026-ermu-english/haidian_english.pdf`
- 源 PNG: `/Users/jiakui/projects/zhongkao-agent/knowledge-original/beijing-mock-2026/ermo/haidian/english/images/page-{01..12}.png`
- OCR 中间: `/Users/jiakui/projects/zhongkao-agent/knowledge-base/exams/_staging/english/2026-haidian-er/tencent-cache/general/page-{01..12}.txt`

---

## 卷面元数据

**对 user 任务描述的关键勘误**：本卷**确为 38 题 / 60 分 / 90 分钟**，**不是 39 题**。
page-01.txt L11 原文：

> "本试卷共10页，共两部分，五道大题，**38道小题**，满分60分。考试时间90分钟。"

题型分布（实测，与 page-10 参考答案及 page-01/02/03/05/07/08/09 题号对账后）：

| 大题 | 题号 | 题数 | 单分 | 小计 |
|---|---|---|---|---|
| 一 单项填空 | 1–12 | 12 | 0.5 | 6 |
| 二 完形填空 | 13–20 | 8 | 1 | 8 |
| 三 阅读理解 A (image-match) | 21–23 | 3 | 2 | 6 |
| 三 阅读理解 B | 24–26 | 3 | 2 | 6 |
| 三 阅读理解 C | 27–29 | 3 | 2 | 6 |
| 三 阅读理解 D | 30–33 | 4 | 2 | 8 |
| 四 阅读表达 | 34–36 / 37 | 3 + 1 | 2 / 4 | 10 |
| 五 文段表达（二选一） | 38 | 1 | 10 | 10 |
| **合计** | | **38** | | **60** |

第一部分小计：12 + 8 + 13 = **33 题 / 40 分**（与 page-01 "本部分共33题，共40分" 一致）。
第二部分小计：4 + 1 = **5 题 / 20 分**（与 page-08 "本部分共5题，共20分" 一致）。

yaml 头部当前字段：
- `year: null` —— **缺**（应 2026）
- `district: ''` —— **缺**（应 海淀 / haidian）
- `exam_type: 真题` —— **错**（应 模拟 或 二模 / mock；这是海淀二模）
- `duration_minutes: null` —— **缺**（应 90）
- `full_score: 60.0` ✓
- `total_questions: 38` ✓（与卷面一致；user 任务描述的 "应 39" 不成立）
- `structure: '25单选(32.0分) + 8cloze(8分) + 4reading_express(10.0分) + 1作文(10分)'` —— **严重错**：
  - "25 单选" 把单选 12 + 阅读 13 都按 `单选` 类型合并；阅读理解 21–33 类型应为 `reading`，不是 `单选`。
  - 缺独立的 reading 小计；缺 cloze 32 分以外的拆分维度。
  - 实际正确字符串应类似：`12单选(6分) + 8cloze(8分) + 13reading(26分) + 4reading_express(10分) + 1作文(10分)`。

**Header 字段需要全量补齐**：year=2026, district=haidian, exam_type=mock（或与库内既定一致），duration_minutes=90，structure 重写。

---

## passages 结构问题

1. **cloze passage body 含水印噪声**（passage `cloze`，body 内）：
   - `... in her life.` 后插入 `kzx.com chocolates?!` —— "kzx.com" 是从页眉/水印跨行 OCR 出的杂字，应清洗成 `chocolates?!`。
   - 段内 `Something 者在线 CHOCOLATEY?` —— `者在线` 是 "北京高考在线" 水印碎片。
   - 段内 `关注北京高考在线官方微信:京考一点通 (微信号:bjgkzx)，获取更多试题资料及排名分析信息。` —— 整段水印直接嵌入正文。
   全部要剔除，否则 LLM 阅读理解会被噪声污染。

2. **reading_A passage（id `reading_A`，q_range 21–23）**：
   - `body: ''` 空 —— 这本是 image-match 题（三段文字 + A/B/C/D 四张图，需图配文），passage body 留空合理；但 stems 部分（Q21/22/23）把 Lin Wei / Wang Lei / Liu Yu 的整段叙述塞进了 `stem`，且 Q21 的 stem 头部还混入了 `B. D.` 与水印 `关注北京高考在线官方微信:京考一点通...` 噪声。建议把三段叙述移到 passage body 或子条目，stem 改为题目本身（"Match the activity image for each student"），并保留 image_options 引用。

3. **reading_C passage**：body 中段插入 `关注北京高考在线官方微信:京考一点通 (微信号:bjgkzx)...` 水印行，影响 Q27–Q29 上下文（research so far 与 points to the hidden health problems 之间被切断）。需清洗。

4. **reading_D passage**：body 第二段后插入 `关注北京高考在线官方微信:京考一点通 (微信号:bjgkzx)...`；末尾段插入 `北京高考在线 / www.gaokzx.com`。需清洗。

5. **express passage** (q_range 34–37): 本身较干净，但 Q37 的 solution 字段被严重污染（详见 Q37）。

---

## 逐题问题清单

### 单项填空 1–12

- **Q1** stem 选项 D 多出 `D: 'We\n\n北京高考在线'` —— 水印 `北京高考在线` 拼到 We 后。所有单选都有此类 D/最后选项尾巴水印（Q2 D 含 `www.gaokzx.com`，Q8 D 含 `北京高考在线`，Q9 stem 含 `w.gaokzx.com`，Q11 solution 含 `C12.A 北京"高考在线 www.gaokzx.com`，Q12 stem 含 `com`）。**13 处需 strip**。
- **Q1** solution: `C2.D` —— 把 Q2 答案 D 拼到了 Q1 solution 末尾（"C" 后接 "2.D"，OCR 答案行 `1.C 2.D` 切分错误）。
- **Q3** stem 缺主语：`-I'm not sure how to use this app.\nyou please help me?` —— page-01 OCR 同样如此，是源 PDF 排版折行；可读但语义不完整，建议在 `you` 前补 "Could/Would"（应为题面的空格位）。**实为 OCR 折行不影响选项作答**。
- **Q5** stem `- ___ did it take you to get to the Great Wall yesterday?` —— OK，空格位明确。
- **Q9** stem `Look, Lily. What a mess you've madel.\nw.gaokzx.com ___ Sorry, Mum. I it up as soon as I finish my painting.` —— `madel` 应为 `made!`（OCR 把感叹号误读为 `l`），`w.gaokzx.com` 水印夹在中间，应清洗。
- **Q10** answer 为空，qc_status: needs_review，qc_note: "选择题 answer 为空"。**确为源 PDF 答案页缺失**（page-10 L14 `10.` 后直接空行接 `11.C`，OCR 没抓到字母）。**根据题干 `since she visited` → 现在完成时 → 应填 C (has read)**。需手工补 patch。
- **Q11** solution `C12.A\n北京"高考在线\nwww.gaokzx.com` —— "C" 后多出 `12.A` 答案串扰 + 水印两行；应只保留 `C`。
- **Q12** stem 中夹 `com` 单字符（"-Do you remember ___ on your first day of junior high?\ncom\n-Yes, a little nervous but excited."）—— 水印 `www.gaokzx.com` 折行碎片。

### 完形填空 13–20

- **Q13** solution `C14.A` —— 同 Q1，把 Q14 答案 A 串扰到 Q13。
- **Q17 / Q18 / Q19** 最后一个选项 D 都有尾巴水印 `北京高考在线` / `gaokzx.com`。
- cloze passage body 噪声见 passages 节。**答案本身 13C 14A 15D 16C 17B 18A 19D 20B 与 page-10 答案区一致**，cloze 答案正确率 8/8。

### 阅读理解 21–23（A 篇，image-match）

- **type 错**：yaml 中 Q21/22/23 的 `type: 单选`，正确应为 `reading`（或专用 `image_match`）。`structure` 字段也因此把它们错算到 "25单选"。
- Q21 stem 头部 `B. D. 关注北京高考在线官方微信:京考一点通 (微信号:bjgkzx)，获取更多试题资料及排名分析信息。 I wore a traditional Chinese costume...` —— `B.` `D.` 是 page-03 OCR 把图选项标签 `A. B. C. D.`（图片下方）漏掉 A/C 后残留的 B/D 标签；水印同上。stem 应只保留 Lin Wei 段落（`I wore a traditional Chinese costume...cultural roots. (Lin Wei)`）。
- Q22 stem 尾 `(Wang Lei)` ✓ 但身份归属信息丢失（Lin Wei/Wang Lei/Liu Yu 是题中署名，必须保留以匹配图选项）。
- Q23 stem 尾 `(Liu Yu)` ✓。
- Q21–23 的 `has_image_options: true` 标记正确，需要 `_src_page_img: .../page-03.png` 链接（已在 passage 条目）和 4 张子图裁剪（A/B/C/D）。**当前 yaml 没有真正的 options 字段，依赖图源**。
- 答案 21=A 22=D 23=C，与 page-10 一致 ✓。

### 阅读理解 24–26（B 篇）

- 内容/答案/选项均正确（D / B / D 与 page-10 一致）。
- Q24 选项 B / D 含尾水印 `北京高考在线` / `www.gaokzx.com`，需 strip。
- Q24 stem 含水印 `关注北京高考在线官方微信:京考一点通(微信号:bjgkzx)...` 应清洗。

### 阅读理解 27–29（C 篇）

- 答案 27=B 28=C 29=D 与 page-10 一致 ✓。
- Q28 选项 B/D 尾水印（同前）。
- C 篇 passage body 含 `A lever No rewards! slow` 三个孤立词 —— 是 page-05 L27–L29 OCR 把题图（lever 图示）的图说碎片当正文读入；应剔除并替换为图引用。

### 阅读理解 30–33（D 篇）

- 答案 30=B 31=C 32=C 33=A —— **page-10 答案区的 30 题被 OCR 误打成 "28.C"**（重复 L34 `28.C`），但根据 yaml Q30 = B (Undefined) 是基于 elusive 语义的正确合理推断；建议留 qc_note 标注 "Q30 答案源自人工/语义推断，PDF 答案行 OCR 异常"。**真实答案应核对原 PDF 扫描件**。
- **Q31 knowledge_points / module 字段错**：当前 `knowledge_points: [vocabulary]`、`module: vocabulary` —— 应为 `信息筛选`、`reading`，和同篇其他题保持一致。
- Q33 选项 A / C / D 含水印：A 尾 `关注北京高考在线官方微信:京考一点通 / (微信号:bjgkzx)... / 北京高考在线`；C 尾 `www.gaokzx.com`；D 尾**严重**：拼入了下一部分 header `第二部分\n本部分共5题，共20分。根据题目要求，完成相应任务。` —— 必须 strip。

### 阅读表达 34–37

- Q34/35/36 stem/solution 基本正确，answer 字段为空（reading_express 题型 answer 留空，solution 即为参考答案，**符合既定规范**）。
- Q35 stem 尾水印 `关注北京高考在线官方微信:京考一点通 / (微信号:bjgkzx)...`。
- Q36 solution 有两行（陈述句 + 介词短语版本），符合 reading_express 允许多版本答案的规范 ✓。
- **Q37 solution 灾难性污染**：从 yaml L1064 起，solution 抓取了**整段 Q38 题目1 + 题目2 的参考范文**（pocket money 题、teacher 题），再拼入 **整段 "北京高考在线平台简介"** 推广文案直至 yaml L1192。约 130 行污染。Q37 的正确 solution 应只是 page-10 L45 的 `略`（open-ended）。**P0 必须修**。

### 文段表达 38

- type=`作文`、score=10 ✓。
- stem 含完整题目1 + 题目2（二选一作文，含表格提示）—— **结构上保留两题是正确的**（二选一），但 stem 内嵌大量水印（`北京高考在线`×4、`关注北京高考在线官方微信...` ×2）和 page-09 footer，需清洗。
- answer / solution **均空** —— **应迁移 Q37 错位的范文内容到 Q38**：page-10 L48–L57 题目1 范文、L58 之后 题目2 范文应作为 Q38 的 solution（possible_version_1 + possible_version_2）。
- knowledge_points: `[命题作文]` —— OK，可补 `半开放写作 / 二选一 / pocket money / job observation`。

---

## 系统性 / 跨题问题汇总（按优先级）

**P0（必须修）**

1. **Q37 solution 错位污染 130 行**（吸入 Q38 全部范文 + 平台推广文案）—— 反向把范文挪到 Q38 solution，Q37 改 `略`。根因是 OCR `_flush_answer_buf` 拼接策略对 reading_express + 作文边界识别失败（参考 MEMORY 中 v1 英语 docx R3 同款 bug）。
2. **Q10 answer 缺失**（needs_review）—— patch 强制 `answer: C`（since → has read）。
3. **Q1 / Q11 / Q13 solution 串扰下一题答案**（`C2.D` / `C12.A` / `C14.A`）—— OCR 答案行 `1.C 2.D` 横向切分错误，需 parser 后处理 `solution = solution[0]` 截断或重写答案 expander。
4. **structure 字段错误聚类**（25单选 ≠ 12单选+13reading），yaml header 4 个字段缺失（year/district/exam_type/duration）。
5. **Q21/22/23 type 应改 `reading`**（当前 `单选` 误归类）。
6. **Q33 D 选项拼入 "第二部分" header**。
7. **Q31 knowledge_points/module 错为 vocabulary**（应 reading / 信息筛选）。

**P1（影响 LLM 阅读质量）**

8. 所有 passage body 水印清洗（cloze、reading_C、reading_D 各 1–3 处）。
9. reading_C passage body 中 `A lever / No rewards! / slow` 图说碎片删除。
10. 所有选项尾巴水印 strip（`北京高考在线` / `www.gaokzx.com` / `gaokzx.com` / `京考一点通...`）—— Q1/2/8/17/18/19/24/28/33 至少 13 处。
11. Q9 stem 中 `madel` 应为 `made!`，`w.gaokzx.com` 折行水印清洗。
12. Q12 stem 中孤立 `com` 字符删除。
13. Q21 stem 头部 `B. D.` 残留标签 + 水印清洗。

**P2（结构优化）**

14. Q21–23 image-match：补 `_src_page_img` cropped 4 子图引用（A/B/C/D）至 options 字段，方便下游 LLM。
15. Q30 答案行 OCR 异常（`28.C` 重号），solution 字段加 qc_note 标注来源。
16. Q34–37 reading_express stem 中作者署名 `(Lin Wei) / (Wang Lei) / (Liu Yu)` 此处不适用，但 reading_A 的同款署名是答题线索，须保留。
17. enrich KP 多为通用 "信息筛选"，可按题目特点细化（人物形象/词语含义/启示感悟/标题归纳）。

---

## OVERALL: **NEEDS_FIX**

- 题数 38 ✓、分数 60 ✓、时长（待补）—— 卷面元数据本身正确，user 任务描述 "39 题" 不成立。
- 但 **P0 级 7 类 bug**（Q37 范文污染、Q10 缺答案、3 处 solution 串扰、structure 字段错、Q21–23 type 错、Q33 header 污染、Q31 KP 错）均需 patch / parser 修复才能上线。
- 水印污染（≥30 处）横跨所有题型，建议在 english_image_paper.py 增加全局水印 strip pass（`关注北京高考在线官方微信.*`、`北京高考在线`、`www.gaokzx.com`、`gaokzx.com`、`京考一点通`、`(微信号:bjgkzx)`、`者在线`、`京高考在线`）作为 OCR 后清洗第 0 步。
- 此外 page-10 答案区 OCR 不稳（Q10 全丢、Q30 重号成 `28.C`），二模卷面普遍如此，建议把"答案行强校验 + needs_review 兜底"做成跨区通用规则。

文件可信度评级：**40%**（题数/分数/题型基本正确；但内容污染严重，作文范文与解答题答案错位，需深度清洗+人工核对后可用）。
