# 2026 北京房山区语文二模 R1 审核

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-fangshan-er.yaml`
- 源 docx: `knowledge-original/zxxk-downloads/2026-ermu-chinese/fangshan_chinese.docx`
- final.json: 1 题 / 14 分（应 27 题 / 100 分）

## OVERALL: **FAIL — P0 parser 灾难，需修 parser**

仅 Q7 被抓，passages OK 但全部 Q1-Q6、Q8-Q27 完全丢失。根因已定位，**100% 是 parser 缺陷**，非源数据问题。

## 根因（实锤）

### P0-1 fangshan docx 用 **Word 自动编号**，parser 只读 `<w:t>` 文本丢号

源 docx 解压 `word/document.xml`，关键证据：

```
para  8 numId=1  text=「小组成员对于宣传海报上"垌野彭彭"的评价鉴赏正确的一项是（2分）」
para 15 numId=2  text=「你审核手记中标注的字音…」
para 19 numId=3  text=「【甲】【乙】两处标点的使用，你认为正确的一项是（2分）」
para 23 numId=4  text=「"浸润"在物理学领域…下列不正确的一项是（2分）」
para 25 numId=4  text=「小组成员认为文段中画线的句子存在问题，请你修改。（2分）」
para 28 numId=5  text=「根据文段内容，你将一组词语填在句中的横线处…」
…（共 24 个 numId≠0 段落，对应 Q1-Q6、Q8-Q27）
para 32  (无 numPr) text=「7. 请你结合手记的内容…」   ← 唯一手敲 "7." 的题
```

题号 `1.` `2.` … `27.` **不在 `<w:t>` 里**，而是 `<w:numPr><w:numId>` 引用 `numbering.xml` 由 Word 渲染时拼出。parser 走 `''.join(t.text for t in p.iter('w:t'))` 抽段落，再过 `NUM_HEAD_RE = ^\s*(\d{1,2})\s*[.、．]` 匹配——`numId` 段落全部得到 0 匹配，所以 Q1-Q6、Q8-Q27 **从未进入 q_starts 列表**。

为什么 Q7 单独抓到？因为该题作者手敲了 "7."（para 32 `numPr=None`），是全文唯一显式题号文本，恰好成了 parser 在 `base` section 内拿到的唯一锚。

### P0-2 fangshan docx 是**试卷版（无答案/无解析）**

全文 132 段，搜索 `【答案】`/`【详解】`/`【解析】`/`参考` 均 **0 命中**（仅 para 2 副词性的"答案"出现在考生须知"答案填涂在答题卡上"）。`_pick_jiexi_docx` 优先级是 "解析版 > 试卷版"，fangshan zxxk 包**只有单 .docx**（同目录其他区是 `.zip` 含 试卷+解析），无解析版可选。

对比朝阳 docx：174 段，36 个 `^\d+．` 段，全部 Q1-Q27 都显式 `1．/2．/…/27．` 前缀（注意是全角点 `．`，但仍命中 NUM_HEAD_RE）。所以 chinese parser **从未在"题号靠 numId"的场景上跑通过**。

## 修复建议（按优先级）

### 兜底 A（**首选**，不改 parser 输入路径）：抽段落时把 numId 还原成 "N. "

`chinese_docx_paper.py` 的 docx → markdown 转换层（应该在 `docx2tex` 之外的纯 Python 抽段路径），改成：

1. 解析 `numbering.xml`：建 `numId → (起始值, 分隔符 like "."/"、")` 表
2. 抽段时若 `p` 有 `<w:numPr><w:numId w:val="K"/>`：维护 `counter[K]`，前缀输出 `"{counter[K]}. "`，再拼 `<w:t>` 内容
3. 对 numId=0 段（不参与编号）跳过 counter

注意：fangshan numId 有多个独立列表（`1,2,3,4,5,6,7,8,9,10,11,12,13`），每个列表只 1-4 段。**不能跨 numId 共用 counter**。但题目编号要全局连续 1-27——所以**实际应统一所有 numId≠0 段共享一个全局 counter**（fangshan 案例下 24 段刚好对应 26 题中的 Q1-Q6+Q8-Q27，但 numId=4 出现 2 段=Q4+Q5 / numId=7 出现 2 段=Q9+Q10 / numId=8 出现 3 段=Q11+Q12+Q13……需用全局 counter 而非 per-numId）

风险：若 Word 同时用 numId 编了"非题目"列表项（如选项 A/B/C/D），会污染计数。fangshan 实测 24 个 numId≠0 段全部是题干，**安全**。但跨区可能出问题——建议加 sanity：抽完后题号必须严格递增且 ≤30，否则回退到正则路径。

### 兜底 B：缺第一题号锚 → 用 `下列…的一项是（N分）` 推断

弱兜底：对 base section 内未捕获题号、但末尾含 `（[12]分）` 的段落，按出现顺序赋 `1, 2, 3 …`。**不推荐**——脆弱且不通用，治标。

### 兜底 C：去拿带答案的源

zxxk 同卷可能有"解析版" PDF/docx，但目前 `download_zxxk_ermu.py` 只抓到单 docx。若有，重抓后走 docx 路径——但**答案版**通常仍用 numId 编号，仍需兜底 A 才能根治。

## 行动项

- **必做**：实现兜底 A（numId → 文本前缀），重跑 fangshan 并确认 27 题 / 100 分
- **必做**：跑兜底 A 回归 13 区已通过案例（朝阳/海淀等），确认不破坏现有逻辑
- **强建议**：抓 fangshan 答案/解析版（可能要从教师上传找）— **现在没答案，所有 answer/solution 字段都将为空**，下游 enrich + 学情分析全废
- **可选**：在 inspect 里加 "fewer-than-15 questions" P0 红灯

## 备注

- 当前 yaml total_questions=1 / full_score=14 是 Q7 错误吃满 base section 14 分的产物（_assign_scores 把 base 总分全分给唯一一题）。修 parser 后会自然纠正。
- 通州/平谷语文目前也只有单 .docx — 建议一并核查是否同 numId 模式。
