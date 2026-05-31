# 2026 顺义二模 语文 R4 终审

**OVERALL: FAIL**（10 处 P0，parser dual-docx merge 切题准确，但子标题误粘 + 选项缺失 + 单题分值错位）

## P0 — sub-section 标题误粘到上一题 sol
- Q10 sol 尾追加 `（二）《游山西村》（5分）`
- Q12 sol 尾追加 `（三）《鱼我所欲也》（7分）`
- Q16 sol 尾追加 `（一）材料阅读（7分）`
- Q19 sol 尾追加 `（二）《无尽灯》（11分）`
- Q23 sol 尾追加 `（三）《韧字当头破万难》（7分）`

源答案 docx 这些行是独立 sub-section header；parser 在 flush 当前题 sol 前误吞了下一行 header（fengtai 同类问题）。建议在 `chinese_docx_paper.py` 的 `_flush_answer_buf` 加 sub-section header regex 终止符（`^（[一二三四五六七八九十]+）.+（\d+分）$`）。

## P0 — Q1 选项缺失/损坏
```
A: ·模·型
B: 不·禁· 0  静·谧·     # B 混入 0 与 C 项
D: ·契·合
```
缺 C 项；B 误并 C "静·谧·"，并夹 "0" 噪声。源 docx 试卷应有 4 项独立加点字，需重抽 options。

## P0 — 单题分值错位（section 总分正确，但题间分配错）
源 docx 标 1 分 / 2 分 / 3 分 与 yaml 不符：
- Q8 yaml 2 → 源 1 分
- Q10 yaml 1 → 源 2 分
- Q11 yaml 3 → 源 2 分
- Q12 yaml 2 → 源 3 分
- Q20 yaml 5 → 源 2 分
- Q21 yaml 2 → 源 3 分
- Q22 yaml 2 → 源 3 分
- Q23 yaml 2 → 源 3 分
- Q24 yaml 3 → 源 2 分
- Q26 yaml 2 → 源 3 分

parser 把题号 stem 末尾的 "(N分)" 抽取出错，应优先信 stem 末尾 `(N分)` 而非 section 残留。

## P1 — stem 吞入下题/下篇阅读材料
- Q2 stem 含 "第二组：青瓦韵四时" 整段（含 Q3 成语 / Q4 划线句出处）
- Q4 stem 含 "第三组：四合养心性" 整段
- Q10 stem 含 《游山西村》全诗
- Q12 stem 含 《鱼我所欲也》全文
- Q19 stem 含 《无尽灯》全文（13 段）
- Q23 stem 含 《韧字当头破万难》全文

passage 切分粒度过粗：只有 base_intro / classical_intro / modern_intro 三大 passage，子篇章塞到题目 stem。建议拆 4 个独立 passage（游山西村 / 鱼我所欲也 / 无尽灯 / 韧字当头）并 q_range 绑定。

## P2 — type 字段不一致
Q12 type=古诗赏析 / Q15 type=古诗内容理解 应统一为 主观填空 或 古诗题，命名不规范但不影响计分。
