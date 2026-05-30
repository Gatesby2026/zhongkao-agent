# 2026 北京英语二模 docx-route R1 跨区 sanity 审核（10 区）

审核口径：严格零 OCR / 严格核源 docx（`knowledge-original/zxxk-downloads/2026-ermu-english/`）。

## OVERALL

**FAIL — 3 区灾难级（daxing / shijingshan / haidian），其余 7 区基本健康但存在 5 类跨区共性 P1/P2 bug。** 分值/题数全部 60 分对齐，但 reading/cloze/作文等内容字段在多个区存在结构性丢失或错配。

| 区 | n | total | passages | answer 覆盖 | 主要风险 |
|---|---|---|---|---|---|
| changping | 39 | 60 | 7 | 缺 Q35,38,39 | P1: Q35 answer 抽取丢失（solution 含正解但未提级到 answer 字段） |
| chaoyang | 39 | 60 | 7 | 缺 Q38,39 | **P0**: Q24-33 reading B/C/D 全部被错分类为 `单选`；Q35 answer 字段实为 solution 内容 |
| daxing | 38 | 60 | 6 | **全卷空** | **P0 源限制**：仅 `_english.docx` 单文件且为"原卷版"（无【答案】区） → 38/38 答案空、38/38 solution 空；passage 缺 reading_A；reading_express q_range 错写 `[1,37]` |
| fangshan | 39 | 60 | 7 | 缺 Q38,39 | P2: reading_A body 仅 23 字符（仅一张 image，无介绍语） |
| fengtai | 39 | 60 | 7 | 缺 Q38,39 | 健康 |
| haidian | 38 | 60 | 6 | 缺 Q34-38 | **P0**：(a) 中文 type 标签 `阅读/完形/写作/阅读表达` ≠ 其他 9 区英文标签 `reading/cloze/作文/reading_express` → schema 不一致；(b) Q24-33 reading B/C/D 全部被错分类为 `单选`；(c) zxxk 水印 "在线官方微信:(微信号:)" 污染 8 处（含 Q21 stem 句首）；(d) Q34-37 全 answer 空 但 Q1-33 完整；(e) 缺 reading_A passage |
| mentougou | 39 | 60 | 7 | 缺 Q38,39 | P2: reading_A body 64 字符（缺介绍语，仅 image） |
| shijingshan | 38 | 60 | 7 | **全卷空** | **P0 源限制**：仅 `_english.docx` 单文件 原卷版 → 38/38 答案空、38/38 solution 空 |
| shunyi | 39 | 60 | 7 | 缺 Q38,39 | 健康 |
| xicheng | 39 | 60 | 6 | 缺 Q38,39 | **P0**: passages 缺 reading_A 但 Q21-23 仍存在且 `passage_id: None`；Q37 answer 含原始题号 "①.\n... ②.\n..." 未清洗 |

## 跨区共性 bug

1. **【P0 解析数据源缺失】daxing / shijingshan**
   `knowledge-original/zxxk-downloads/2026-ermu-english/` 仅提供 `daxing_english.docx` / `shijingshan_english.docx`（同一名字、无 `.zip`），实际是 ZXXK "原卷版"，**没有【答案】节**。其他 8 区是 `.zip`，包含 `原卷版.docx` + `解析版.docx` 两份。
   后果：parser 没有解析数据可读，全卷 answer/solution 空。
   解法：补抓 ZXXK 解析版 docx，重跑 daxing / shijingshan；否则只能上 image OCR 兜底。
   验证命令：
   ```bash
   unzip -l /Users/jiakui/projects/zhongkao-agent/knowledge-original/zxxk-downloads/2026-ermu-english/xicheng_english.zip
   # 看到两份 docx（原卷版 + 解析版）才正常
   ```

2. **【P0 type 分类错】chaoyang Q24-33 + haidian Q24-33（reading B/C/D 全部）**
   `passage_id` 正确写到 `reading_B/C/D`，但 `type` 字段是 `单选` / `单选`（chaoyang 英文，haidian 中文）而不是 `reading` / `阅读`。
   - chaoyang 表现：`单选`=22 而非 12（其他 8 区都是 12）。
   - haidian 表现：除了 reading B/C/D 错类，整套 yaml 用中文 type 标签，与其余 9 区 schema 不一致 → 下游消费方按 type 路由会全断。
   - 共因怀疑：chaoyang / haidian 源 docx 在 reading B/C/D 段未保留 "阅读下列短文" anchor，或 parser 对 "C. xxx" 选项行错判为单选 stem。这两区 docx 都是 "选用" / 海淀官方版式，可能是 ZXXK 解析模板偏差。
   解法：parser 增加 fallback —— **`if passage_id startswith 'reading_' then type := reading（按区映射 reading/阅读）`**；同时 haidian schema 应该强制统一为英文标签。

3. **【P0 passage 拆分错位】xicheng / haidian / daxing reading_A 缺失但 Q21-23 仍生成**
   - xicheng：passages 列表只有 6 个（缺 `reading_A`），Q21-23 写到 yaml 但 `passage_id: None`，下游对接答题卡按 passage 取 body 会拿不到任务匹配介绍语和 4 张候选 image。
   - haidian：同上（缺 reading_A），Q21 stem 句首误吞 "B. D. 在线官方微信..." 水印 + 实际正文，是 passage anchor 没识别到 → 整段被吸进 Q21 stem。
   - daxing：缺 reading_A + reading_express q_range 错写 `[1, 37]`（应为 `[34, 37]`），是因为解析数据空 → q_range 推断退化。
   解法：parser 增加 `READING_A_ANCHOR = ('阅读下列|根据三位|每幅图片代表')` 兜底；当 Q21-23 存在但无 reading_A passage 时强制兜底生成空 body passage（避免 passage_id=None）。

4. **【P1 跨区共性】answer 字段抽取不一致**
   - changping Q35：`answer: ''` 但 `solution` 末尾写 `"答案将这两点整合为 'They feel it is cool and like a treasure hunt.'"` —— answer 应能从 solution 反向提级。
   - chaoyang Q35：`answer` 字段实为 solution 全文（"根据文章第 2 段..."），answer/solution **粘连错位**。
   - xicheng Q37：`answer` 含原始 OCR 顺序号 `"①.\nSet a clear goal...   ②.\nBreak down tasks..."`，solution_len=1 → answer/solution buffer 串味。
   - haidian Q34-37：全空（与 Q1-33 已填对照下是 reading_express 段独立漏抽）。
   解法：增加 `_extract_answer_from_solution()` 兜底 + answer ≠ solution 互斥校验。

5. **【P2 跨区共性】reading_A passage body 字数过短 / Q21-23 options 全空**
   - 6/10 区（changping/fangshan/fengtai/mentougou/shijingshan/shunyi）的 Q21-23 `options` 全 `[]`。这是任务型匹配题（4 选 3 + 1 多余），需把候选 A-D 抽到 options。
   - 5 区 reading_A body 极短（fangshan 23 / shijingshan 24 / mentougou 64 / changping 97 / shunyi 193）——多数只有一张图占位（`![](figures/imageN.png)`），缺介绍语。
   解法：parser 把 4 张候选 image 与说明文字一起注入 passage.body（或 Q21-23 options），不要拆裂。

6. **【P2 cloze stem 全空（10/10 区）】**
   所有区 Q13-20 stem 都是空字符串。这是 docx 路线设计：cloze 填空 stem 在 `passages.cloze_intro.body` 的 `<u>____13____</u>` 标记里，consumer 端按 passage_id+id 渲染。**确认为 by design 不算 bug**，但建议 parser 至少写一句占位 stem（如 `"见 cloze 短文第 N 空"`）便于下游单题查询。

7. **【P2 作文 Q39 score=0】**
   chaoyang/xicheng/changping/fangshan/fengtai/mentougou/shunyi（7 区）使用"二选一作文 Q38+Q39"结构，full_score 已经在 Q38 一次性给 10 分，Q39 给 0 分作为可选项。daxing/shijingshan/haidian（3 区）合并成单独 Q38。两种表达都对 60 分目标无影响，但建议统一为单题二 anchor 写法以便下游评分逻辑统一。

## 抽样核源结果（spot check 4 卷）

- **xicheng**：cloze passage 8 空标记完整 / reading B/C/D body 完整且与 docx 一致 / Q34-37 简答 answer 正确 / Q38 essay anchor 已正确切割（"健康生活" / 不串题）。OK 除上述 P0 reading_A。
- **chaoyang**：cloze passage 完整 / reading B/C/D body 完整 / Q38-39 essay anchor 不串 / Q34-37 reading_express answer 已抽取。**仅 type 错分** + Q35 answer/solution 粘连。
- **fengtai**：39 题 / passages 7 个完整 / answer 仅 Q38-39 essay 空 / reading_express Q34-37 answer 均填好。最干净的一卷。
- **haidian**：水印未清 + reading_A passage 缺 + Q34-37 空 + Q21 stem 被水印污染 —— 一卷集齐 4 类 bug，建议重跑前先清水印 regex。

## 建议处置（按优先级）

1. **P0**：补抓 daxing / shijingshan ZXXK 解析版 docx（`.zip` 两份装），重跑 parser。否则这 2 区不能进 enrich / 不能进答题卡评分。
2. **P0**：parser 修 chaoyang / haidian reading B/C/D type 错分（`passage_id` → `type` 兜底映射）。
3. **P0**：parser 修 haidian zxxk 水印 regex；加入 `"在线官方微信.*?信息。"`、`"(微信号:)"` 到 NOISE_PATTERNS。
4. **P0**：parser 修 xicheng / haidian / daxing reading_A passage 缺失（anchor 兜底 + Q21-23 强制绑 passage）。
5. **P0**：haidian schema 中英文 type 不一致，强制 type 字段输出英文（与其他 9 区对齐）。
6. **P1**：answer/solution 互斥校验 + answer 从 solution 提级兜底（changping Q35 / chaoyang Q35 / xicheng Q37 案例）。
7. **P2**：reading_A 任务匹配题 4 候选 image + 说明文字注入 passage.body 或 Q21-23 options。

进入 R2 前请先修 P0 4 类 + 补 daxing/shijingshan 数据源，否则 10 区只有 fengtai / shunyi 可算"基本可用"。
