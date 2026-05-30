# 2026 平谷英语二模 R1 大模型审核

**OVERALL**: NEEDS_FIX (parser bug，**3 题缺失 6 分**)

## 1. 缺失题量再核

- yaml 实际：35 题 / 54 分
- 源 docx **首页明示**："本试卷共 **38 题，满分 60 分**"（不是 39/60）
- **缺口 = 3 题 / 6 分**（用户给的 4 题/6 分有偏差，docx 权威 38 题）

## 2. 缺失题定位（已找到）

缺的 3 题是 **Q21 / Q22 / Q23**，属于「三、阅读理解（一）」**图片匹配题** —
教师给 4 张图(A/B/C/D) + 3 段对话，让学生匹配。

源 docx 段落（`word/document.xml` 解包后）：
```
P0059  三、阅读理解。（每题2分，共26分）
P0060  （一）...请根据人物讲述的内容，匹配最合适的图片...
P0061  A     ← 4 张图（A/B/C/D），多余 1 项
P0063  21. ___________
P0065  I think AI makes our daily life easier...
P0066  22. ___________
P0068  That's true. For studying, AI helps me...
P0069  23. ___________
P0071  Yes! When I don't understand a math problem...
```

`raw.md` 第 119/121/122 行渲染为 **markdown 表格**：
```
| 21. ___________ | ![](figures/image3.png) | I think AI makes...|
|---|---|---|
| 22. ___________ | ![](figures/image4.png) | That's true...    |
| 23. ___________ | ![](figures/image5.png) | Yes! When I...    |
```

## 3. 根因（parser bug，非源缺）

`scripts/exam-docx/english_docx_paper.py` 两条匹配路径**全部失效**：

**(a) `NUM_HEAD_RE = ^\s*(\d{1,2})\s*[.、．,，]\s*(.*)$`**
要求题号在行首（允许空白前缀）。pinggu 这 3 行行首是 `| 21.`，**pipe 字符不在
`\s` 范围**，主路径直接 miss。

**(b) image-match 兜底 `_+\s*(\d{1,2})\s*_+`**（L386-394, L450-455）
要求题号**两侧都是下划线**（朝阳/昌平/房山约定的 `___21___`）。
pinggu 是 `21. ___________`（题号在**前**，underscores 在**后**），不匹配。

→ Q21-23 既不进 `q_starts`，也不被 image-match fallback 捕获，全丢。
score block "（每题2分，共26分）" 预期 13 题（24-36），实际只识 10 题 (24-33)
+ 3 题 reading_express (34-36) → 总分对不上 26，但 reading_express 段有自己的
score block "(共12分)"，所以最终 54 = 60 - 6 与缺失 3×2 完全吻合，**侧面确证缺
口=image-match 全段**。

## 4. 精确 Fix

修 `english_docx_paper.py` 兜底 regex（**两处都改**）：

```diff
- IMG_Q_RE = re.compile(rf"_+\s*{n}\s*_+")
+ # 兼容：(a) ___N___（朝阳/昌平）  (b) | N. ___（平谷表格内）
+ IMG_Q_RE = re.compile(rf"(?:_+\s*{n}\s*_+|\|\s*{n}\s*[.．、]\s*_+)")
```
```diff
- for m in re.finditer(r"_+\s*(\d{1,2})\s*_+", ln):
+ for m in re.finditer(r"_+\s*(\d{1,2})\s*_+|\|\s*(\d{1,2})\s*[.．、]\s*_+", ln):
-     n = int(m.group(1))
+     n = int(m.group(1) or m.group(2))
```

更稳的等价改法：在 `q_starts` 主循环里**先 strip 行首 `|` 和空白再喂
NUM_HEAD_RE**（一处修复覆盖所有 markdown table 题号场景，建议优先采纳）。

## 5. 答案 / patches 提示

源 docx **无参考答案页**（末尾只到作文题目②结束，无 "参考答案" anchor）。
fix 后 Q21-23 stem 能拿到，但 `correct` 必走 `_patches/english/2026-pinggu-er.yaml`
人工补 3 条 `{number: 21/22/23, correct: <字母>, score: 2}`。图 A/B/C/D 即
image1.png（题首大图）+ image3/4/5.png（行内图），需人工对照确认正确字母。

## 6. 其他

- 13 选择 + 8 cloze + 10 reading(B/C/D) + 4 reading_express + 1 essay = 36；
  补上 3 题 image-match = **39**？不，docx 明示 **38**：作文 1 题，
  reading_express 是 4 题(34/35/36/37)。13+8+3+10+4+1 = **39**?
  重算：单选 12 (Q1-12) + cloze 8 (Q13-20) + image-match 3 (Q21-23) +
  reading 10 (Q24-33) + reading_express 4 (Q34-37) + essay 1 (Q38) = **38** ✓。
  yaml 单选实际 12 题 (Q1-12)，不是 13。
- fix 后预期：38 题 / 60 分 / 0 noise，与首页声明完全对齐。
