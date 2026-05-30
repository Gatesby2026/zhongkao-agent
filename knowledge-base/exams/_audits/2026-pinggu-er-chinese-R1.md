# 2026 北京平谷区语文二模 R1 大模型审核

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-pinggu-er.yaml`
- 源 docx: `knowledge-original/zxxk-downloads/2026-ermu-chinese/pinggu_chinese.docx`
- final.json: `knowledge-base/exams/_staging/chinese/2026-pinggu-er/structured-cloud/final.json`

**OVERALL: NEEDS_FIX**（P0 parser bug，致 56 题/206 分；应为 27 题/100 分）

## 1. 源 docx 结构核查

`unzip` + 抽 `word/document.xml` 共 271 段，确认是 **单结构 = 试卷题面 + 「参考答案」 + 答案区**（不是双 docx 拼接）：

- para[0-9]：封面 + 注意事项「本试卷共8页，共27题，满分100分」
- para[10-126]：试卷题面，section 头 `一、基础·运用（共14分）` / `二、古诗文阅读` / `三、名著阅读` / `四、现代文阅读` / `五、作文`，题号 1-26（外加作文题）
- **para[128]：`参考答案`**（关键 marker，仅这一行）
- para[129-210]：答案区，子结构 = 重复一遍 `一、基础·运用（共14分）` 等 section header，然后逐题 `1.C（共2分）` / `2.D（共2分）` / `3. 答案示例：` / `8.答案：四面歌残终破楚` / `13. 答案: B` …

**答案区不使用 `【答案】` marker**，而是 `N. 答案[:：]…` 或 `N.X（共N分）` 直接形式。这是 pinggu 与朝阳/西城/海淀（用 `【答案】` + `【N题详解】`）的关键差异。

## 2. 答案 section marker 字符串

源 docx 唯一切换 marker = **`参考答案`**（para[128]，独占一行）。无 「答案及评分参考」 / 「答案与解析」 / 「【答案】」 等其他变体。

## 3. 题号重复 pattern 定位

final.json 题号序列：
`[1,2,3,4,5,6,7, 1,2,3,4,5,6,7, 8,9,10,11,12,14,15, 8,9,10,11,12,13,14,15,16, 16,17,18,19,20,21,22,23,24,25,26, 17,18,19,20,21,22,23,24,25,26,27, 25, 2,3,4]`

明显 1-7 / 1-7、17-26 / 17-26 各跑两遍。8-16 段没全重，是因为该段答案区出现 `【答案】` 子标记（para[160] `13. 答案: B` 之类不带【】但同段也有 `【答案】1.…` 风格的零星行），偶尔触发了 answer 模式，但整体仍漏判。

## 4. 根因（精确到代码位置）

`scripts/exam-docx/chinese_docx_paper.py`：

| 行 | 现状 | 问题 |
|---|---|---|
| 218 | `NOISE_LINE_RE` 把 `参考答案` 当噪声**静默丢弃** | 没切 mode |
| 207 | `ANSWER_MARKER_RE = r"^\s*【答案】"` 只认带【】 | 漏 `N. 答案:` 形式 |
| 250-255 | `_is_section_header` 命中 → `mode="question"` 无条件 | 「参考答案」后再出现 `一、基础·运用` 会**重置回题面模式**，于是 `1.C/2.D/3. 答案示例` 被当成新题 1/2/3 |

## 5. 修复建议

**P0（必修）**：`scripts/exam-docx/chinese_docx_paper.py` `parse_docx_chinese`：

1. **新增 sticky flag `in_answer_block`**（main loop 顶部 `in_answer_block = False`）。
2. **新增 marker 正则**（185 行附近）：
   ```python
   ANSWER_BLOCK_START_RE = re.compile(
       r"^\s*(?:参考答案|答案及评分参考|答案与解析|试题答案|参考解析)\s*$")
   ```
3. **主 loop 最前面**（紧接 `for ln in lines:` 后、`sec_m` 判定**之前**）插入：
   ```python
   if ANSWER_BLOCK_START_RE.match(ln):
       in_answer_block = True
       mode = "answer"
       a_lines.append(f"__Q_CTX__:{last_q_seen}")
       continue
   ```
4. **section header 命中时**（250-255）加守卫：
   ```python
   if sec_m:
       if in_answer_block:
           a_lines.append(ln)   # 答案区的 section header 进 a_lines 当上下文
           continue
       cur_typ = sem_m[0]; ...  # 原逻辑
   ```
5. **question-mode 题号匹配处**（278-291）加守卫：`in_answer_block` 为真时**不许**回切 question，全部归 a_lines。
6. `NOISE_LINE_RE`（218 行）移除 `参考答案` 项（已由步骤 3 处理）。

**P1（健壮性）**：`_parse_answers` 扩展正则识别 `N\s*[.、]\s*(?:答案[:：]|答案要点[:：]|答案示例[:：]?|[A-D]\s*[（(]共)`，提取 N、答案文本/字母、score。

## 6. 验证锚点

修复后预期：`total_questions: 27`，`full_score: 100`，`duration_minutes: 150`，题号 1-26 不重复（作文题号视 docx 是 27 还是嵌入二选一）。
