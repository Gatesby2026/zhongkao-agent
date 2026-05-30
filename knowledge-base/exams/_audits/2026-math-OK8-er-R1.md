# 2026 北京数学二模 8 卷 R1 跨区 sanity 审核

**范围**：daxing / fangshan / haidian / mentougou / pinggu / shijingshan / shunyi / xicheng
**口径**：纯零 OCR，严格核源 docx + 已生成 yaml

## OVERALL: ❌ FAIL（8/8 全卷不可用，结构 OK 内容空）

骨架题数全部 OK（28 题 / 100 分 / 120 分钟），**但每卷答案、解析、几乎全部数学公式均缺失**。属 parser 层 P0 缺陷，不是源 docx 问题，**必须修 `scripts/exam-docx/math_docx_paper.py` 重跑 8 卷**。

---

## P0-1：所有 8 卷 `answer` / `solution` 字段 100% 为空（224/224 题）

`empty_answer_total = 28、empty_solution_total = 28` 八区一致。

**根因**：源 docx 分两类（见 §源数据分类），parser 对两类都失败：
- A 类「试卷-only」（daxing / shijingshan / fangshan / shunyi）：源 docx 本身就没有 `答案 / 详解 / 解析` 段（daxing/shijingshan 全文 `答案` 仅 1 次出现在"试题答案一律填涂在答题卡上"考试须知里），parser 自然抓不到。但同目录其实有 `参考答案.pdf` / `答案.pdf`，parser **未配 PDF 答案合并路径**。
- B 类「解析版」（haidian / xicheng / mentougou / pinggu）：源 docx 含 33-44 处 `答案/详解/解析`，但 parser **未识别题间嵌入的【答案】【解析】【详解】块**作为答案/解析归属字段——见 P0-2。

## P0-2：B 类 4 卷的【答案】【解析】【详解】被错粘进 stem 或 option D

精确量化（解析版 4 卷一致跨区共性）：
- **Q1-Q8 单选**：D 选项 string value **包含整段【答案】X 【解析】【分析】…【详解】…**
  - haidian: 8/8 题 D 选项被污染
  - mentougou / xicheng: 7/8 题（Q1 例外）
  - 同时 A/B/C 选项常常被前序公式 OLE 吞掉变成空串 (`A: '' B: '' C: ''`)
- **Q9-Q16 填空 stem**：8/8 题 stem 末尾粘上 `【答案】… 【解析】… 【详解】…`，stem 与解答不分。
- **Q17-Q28 解答 stem**：12/12 题 stem 末尾粘整段【答案】【解析】【分析】【详解】，尤其 Q28 新定义题 stem 真实结构已被严重淹没（haidian Q28 stem 1454 字、xicheng 1255 字、mentougou 1181 字，正常应 ~250 字）。

修复方向：parser 需在分题循环里先扫【答案】/【解析】/【分析】/【详解】marker，将 marker 之后到下一题号 / 下一 marker 之间的内容剥离出 stem/options，按 marker 类型分别落到 `answer` 与 `solution`。

## P0-3：所有 OLE MathType 公式（300+/卷）全丢，导致 stem/options 不可读

OMML / OLE 对象统计（源 docx）：
| 区 | OMML | OLE | LaTeX in yaml |
|---|---|---|---|
| daxing 试卷 | 0 | 309 | 0 |
| shijingshan 试卷 | 0 | 315 | 0 |
| fangshan 试卷 | 0 | (未测) | 0 |
| shunyi 试卷 | 0 | (未测) | 0 |
| haidian 解析版 | 46 | 914 | 14 frac / 7 sqrt / 92 `$`（仅 OMML 部分被抓） |
| xicheng 解析版 | 0 | 1013 | 0 |
| mentougou 解析版 | 0 | 1196 | 0 |
| pinggu 答案/试卷 | 0 | 193 | 0 |

`grep -nE "OLE|oleObject|MathType|mathml" scripts/exam-docx/math_docx_paper.py` → **零结果**：math_docx_paper.py 完全没有 OLE→LaTeX 链路，与 MEMORY 里 `skill_exam_docx_physics` 描述的"d2t/MathType→MathML→LaTeX 全链路"完全没接通。

可见破坏举例（daxing Q2 stem）：
```
实数，在数轴上的对应点的位置如图所示，下列结论正确的是
A．  B．  C．  D．
```
源 docx 真实内容是 `实数 a, b, c 在数轴上…  A. a>b  B. b>c  C. ac>bc  D. a+c>0`——所有变量、不等式、常数全部 OLE，零落地。

stem 长度 < 20 的"碎片题"共 17 处（daxing 6 / fangshan 6 / pinggu 6 / shijingshan 7 / shunyi 7 …），全部由 OLE 公式被剥光导致，最严重 Q17 仅 4 字（`如图，`）。

## P0-4：fangshan / shunyi 答案在 PDF 里，parser 未走 PDF 合并路径

源 zip 内 `北京市房山区2026…数学参考答案.pdf` / `答案.pdf` 与试卷 docx 并列，parser 只吃了 docx 一个文件，PDF 答案被完全无视。建议两种修法：
- 短期：手 patch（学习 chinese / politics 的 `_patches/` 模式）
- 长期：parser 支持同目录 `*答案*.pdf` → pdfplumber 提文本 → 按 `1.A 2.B 3.D …` regex 落到 `answer` 字段

## P1：Q28 新定义题 stem 完整性

A 类（无答案污染）4 卷 Q28 stem 框架 OK（daxing 315 字 / fangshan 230 字 / shijingshan 232 字 / shunyi 201 字 / pinggu 211 字），主结构（定义 → (1) (2) (3) 小问）齐全，但内部公式 OLE 全丢（"半径为，"、"点关于的弦分点"），实际可读性低。
B 类 4 卷 Q28 stem 被【答案】污染（haidian 1454 / xicheng 1255 / mentougou 1181 字），真实小问与解答混杂，无法直接用。

## P1：几何符号 \triangle / \angle 0 出现

8 卷全部 `\\triangle = 0`、`\\angle = 0`、`\\pi = 0`——几何题（Q7 圆/三角形、Q19-26 多有△和∠）的核心符号全消失。这是 OLE 漏抓的直接后果。

## 源数据分类（修复优先级排序参考）

| 区 | 源 docx | 答案来源 | 修复路径 |
|---|---|---|---|
| haidian | 原卷版.docx + 解析版.docx | 解析版含 | parser 修剥离【答案】块 → 可用 |
| xicheng | 原卷版.docx + 解析版.docx | 解析版含 | 同上 |
| mentougou | 原卷版.docx + 解析版.docx | 解析版含 | 同上 |
| pinggu | 试卷.docx + 答案.docx | 答案.docx 独立 | parser 改读双 docx 合并 |
| daxing | 仅 .docx（试卷） | 无答案文件 | 走人工 patches |
| shijingshan | 仅 .docx（试卷） | 无答案文件 | 走人工 patches |
| fangshan | 试卷.docx + 参考答案.pdf | PDF | parser 加 PDF 答案合并 |
| shunyi | 试卷.docx + 答案.pdf | PDF | 同上 |

公式 OLE→LaTeX 链路属于 8 卷共性 P0，**优先于上述任何分支修复**，否则即使补上答案，stem 仍然不可读。

## 建议下一步（修复优先级）

1. **P0**：math_docx_paper.py 接入 OLE→MathType→MathML→LaTeX 链路（physics 已跑通可直接抄）。
2. **P0**：math_docx_paper.py 加【答案】【解析】【分析】【详解】marker 解析，4 解析版区直接受益。
3. **P0**：A 类 4 卷加 PDF 答案合并或 patches 兜底。
4. **P1**：math_inspect.py 增 sanity check：`empty_answer_ratio > 0.5` 直接 FAIL；`stem 含【答案】` 报错。

R1 结论：**8 区都需要重跑，禁止下游 enrich/embedding 使用本批 yaml**。
