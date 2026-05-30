# 2026 北京二模 道法 docx 路线 R1 大模型审核（chaoyang + shunyi 合并）

零 OCR / 全量核源 docx（chaoyang 解析版 .docx / shunyi 解析版 .docx）。

---

## OVERALL

- chaoyang：**源 docx 缺 Q25** — parser 无错，源材料解析版本身漏题。需手补 Q25（patches 或重抓 zxxk）。
- shunyi：**parser bug — 试卷答案 section 二次进入产生 7 道假题** (id:1, id:6, id:21-25)；真题为 25 题/70 分。Q1/Q6 重复 + Q21-25 重复（且 type 误判为 "单选"）。源 docx 正常。

P0 fix：politics_docx_paper.py 加 "试卷答案" 终止条件（与"参考答案/答案及评分"统一）。修后两区 yaml 重跑 + 人工补 chaoyang Q25。

---

## chaoyang 详查（yaml 24 题 / 标称 25 题 / 70 分 → -10 分 = 缺 Q25 10 分）

**源 docx**：`chaoyang_politics.zip` 解出"精品解析：2026 朝阳二模道法（解析版）.docx"。
- 卷首 L2 明示："共8页，共两部分，共25题，满分70分"
- "第二部分 本部分共5题，共40分"（L160-161）
- 实际解析版只含 Q1–Q24（最后段落 L210 即 Q24 详解末句）。
- 第二部分分值：Q21=6 + Q22(1+1)=6 + Q23=8 + Q24=10 = **30 分**（缺 10 分的 Q25）。

**结论**：源 docx 解析版漏 Q25。不是 parser 问题，是 zxxk 源材料缺失。

**fix 路径**：
1. 重抓 zxxk 朝阳二模道法（可能源站 docx 已更新），或
2. 手补 patches：`knowledge-base/exams/_patches/politics/2026-chaoyang-er.yaml` 加 Q25（10 分 essay），stem 需另寻原卷 PDF/图片源（gaokzx 等）。

---

## shunyi 详查（yaml 32 题 / 标称 25 题 / 70 分 → +7 题；prompt 写 +10 题，实际 +7）

**源 docx**：`shunyi_politics.docx` 解析版。卷头明示 "共25题，70 分"。

### 多出的 7 题（全为 parser 误识别）

| yaml id | yaml 行 | 真实来源 | bug |
|---|---|---|---|
| 1 (dup) | L196 | docx L129 `1. √ 2. √ 3. √ 4. √ 5. ×` | 试卷答案行被当判断题 Q1 |
| 6 (dup) | L208 | docx L130 `6. √ 7. √ 8. √ 9. √ 10. ×` | 同上，Q6 |
| 21 (dup, 单选) | L537 | docx L133 `21. （6分）` + answer body | 试卷答案 essay 部分被当 question |
| 22 (dup, 单选) | L561 | docx L136 `22. （6分）` | 同上 |
| 23 (dup, 单选) | L583 | docx L138 `23. （8分）` | 同上 |
| 24 (dup, 单选) | L605 | docx L140 `24. （10分）` | 同上 |
| 25 (dup, 单选) | L630 | docx L143 `25. （10分）` | 同上 |

**真题正确部分**（应保留）：Q1-10 判断（L24-178）+ Q11-20 单选（L220-501）+ Q21-25 材料/作文（L651-812）= 25 题 70 分。

### 根因（politics_docx_paper.py）

docx L127 "试卷答案" 之后出现：
- L128 "一、判断题（每题1分，共10分）" — **匹配 SECTION_HEADERS**，重新进 `mode="question"` + `cur_typ="judge"`。
- L129 `1. √ 2. √ 3. √ 4. √ 5. ×` — NUM_HEAD 匹配 n=1，但 last_q_seen=25，`n > last_q_seen` False，按 question 模式直接 append（不走 answer→question 切换），创建 Q1 dup。
- L132 "三、非选择题" — SECTION_HEADERS 匹配（essay/material），进 `mode="question"`，cur_typ 切换。
- L133-143 `21. （6分）…25. （10分）` — NUM_HEAD 匹配，全部当 question append，type_assign 再误判为 "单选"（因 score=2 + 缺 options 兜底；阈值 70 已涵盖不触发 _self_check）。

`NOISE_LINE_RE` (L215-219) 只覆盖 "参考答案|答案及评分"，**漏 "试卷答案"**（顺义独有写法）；且即便加入 NOISE，也只过滤当前行，下游 "一、判断题" 仍会触发 SECTION_HEADERS 二次匹配。

### 精确 fix（politics_docx_paper.py）

**P0 最简方案**：进入主循环前加 "试卷答案 / 答案及评分 / 参考答案 / 试题答案" 截断哨兵：

```python
# parse_docx_chinese 开头，lines 切分后
ANSWER_SECTION_RE = re.compile(r"^\s*(试卷答案|试题答案|参考答案|答案及评分)\s*$")
for idx, ln in enumerate(lines):
    if ANSWER_SECTION_RE.match(ln.strip()):
        lines = lines[:idx]  # 截断，后续 [答案]/[详解] 已经在前面交替出现完成
        break
```

注：解析版的【答案】+【详解】是在每题题面后**就近**给出的（chaoyang L11/L15/L20 即在 Q1/Q2/Q3 后立刻出现），并不依赖卷尾"试卷答案"段；截断不会丢失答案数据。

**P1**：`NOISE_LINE_RE` 同步加入 `试卷答案|试题答案` 以防其他区出现"试卷答案"嵌在正文中（防御性）。

修后预期：shunyi 25 题 / 70 分 / 0 dup。chaoyang 仍需独立补 Q25。
