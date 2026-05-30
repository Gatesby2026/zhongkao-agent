# 2026 北京中考语文二模 docx 路线 R1 跨区审核（5 卷）

审核范围：daxing / fengtai / haidian / shunyi / xicheng
审核维度：题数分值 OK（前提）→ answer / solution / passage / KP / stem 污染
方法：严格零 OCR / 核源 docx（cp437→utf-8 文件名解码后 grep XML 文本层）

---

## OVERALL: FAIL（按 5 卷最差给）

**3 类 P0 跨区共性 bug** 全部由 parser 触发，**4/5 卷题目作答信息基本缺失**，下游 enrich / 相似题推荐完全无法启动。

---

## P0-1【跨区共性 / parser bug】answer/solution 大面积缺失

| 区 | total | 空 answer | 空 solution | 源 docx 结构 |
|---|---|---|---|---|
| daxing | 27 | **27/27** | **27/27** | 只有 `【试卷】.docx`（参考答案在 PDF）|
| fengtai | 27 | **27/27** | **27/27** | `试卷.docx` + 独立 `答案.docx` |
| haidian | 27 | **27/27** | **27/27** | 只有 `【试卷】.docx`（参考答案在 PDF）|
| shunyi | 27 | **27/27** | **27/27** | `试卷.docx` + 独立 `答案.docx` |
| xicheng | 26 | **17/26** | 0/26 | `解析版.docx`（含 【答案】【解析】）|

**根因 / 三种情况**：

1. **daxing / haidian**：源仅 PDF 含答案，docx 全无 → 当前数据源天然不可解；需 PDF→docx 转换或拉 zxxk 解析版补齐（**数据源问题**，**非 parser bug**）
2. **fengtai / shunyi**：zip 内有独立 `*答案.docx`（27 题答案完整、纯文本如 "1. A（2分）"、"8. 海日生残夜"），但 `chinese_docx_paper.py` 只取一个 docx，**未做 quiz+answer 二合一 merge** → **P0 parser bug**，新增逻辑：识别 zip 内 `答案/参考答案/解析` docx，单独抽 `N. ANS` 行回填到对应题
3. **xicheng**：解析版 docx 自带 【答案】，但 **一个 【答案】 块合并多个题答案**（如 "【答案】1. ... 2. B 3. A 4. D 5. ..." 同段），parser 只把整块塞给 anchor 题（Q1 / Q15 / Q17 ...），导致 **17/26 题 answer 为空但 solution 反而被吞到 anchor 题中** → **P0 parser bug**，需在 `_extract_answer` 后做 "`\d+\.\s+`" 二次拆分 → 多题回填

---

## P0-2【4/5 卷 parser bug】sub-passage header 未识别 → stem 吞下整段 passage / 选项 D 吞 passage

| 受影响题（跨 daxing / fengtai / haidian / shunyi 共 4 卷一致） | 现象 |
|---|---|
| **Q4 选项 D** | "D．处心积虑  **义别**  北京东城区府学胡同63号文丞相祠..."（option D 把"义别"小标题及整段 passage 吞入）|
| **Q6 选项 D** | "D．①土牢存浩气...  **悟别**  古都别蕴藏于桥..."（同上）|
| **Q10 stem** | "古人以诗文载道..."（默写题 stem 后尾随 "**（二）阅读下面两首词，完成11-12题**" + 满江红/南乡子整篇）|
| **Q12 stem** | 同上模式：尾随 "（三）阅读《送东阳马生序》" + 文言文整段 |
| **Q19 stem** | 尾随 "（二）阅读文章，完成第20-23题" + 整篇散文（≈1600-1900 字）|
| **Q23 stem** | 尾随 "（三）阅读文章，完成第24-26题" + 整篇议论文 |

**根因**：`chinese_docx_paper.py` 第 197 行 `SUB_HEADER_RE` 只匹配 "（一）/（二）..."，**未覆盖 ermu 卷面新增的 4 种自定义 sub-section**：`情别 / 志别 / 义别 / 悟别`（daxing 主题"古都别蕴"特有，类似海淀的"志别"段落标题）。同时 4 区共性"（二）阅读..." 出现在题干末尾时也没被识别为 passage break。

**修复方向**：

1. 在 `SUB_HEADER_RE` 增加无序号、非 `（X）` 形式的 sub-header 兜底：行首 2-3 汉字 + 后续段为完整 passage（≥80 字、含书名号/句号超 N 处）
2. `_flush_question` 前对当前 stem 行尾扫描 `（[一二三四五]）阅读` / `（[一二三四五]）默写` → 强制切段并将后续推入新 passage
3. 校验：option D 不允许出现"。"以外的连续 ≥30 汉字段（option 单选合理上限）

**侧影响**：xicheng 因走"完全独立 passage 切分"路径（passages=7、有命名 `base_卷首语 / classical_（一）`）所以 stem 干净，**P0-2 对 xicheng 无影响**。这反向证明：daxing/fengtai/haidian/shunyi 4 区 passage=3 单体大块的结构是 parser 选错路径所致，**不是源 docx 结构差异**。

---

## P0-3【4/5 卷 parser bug】passage 完全没拆，3 个 monolith 大块

daxing/fengtai/haidian/shunyi 都只产出 3 个 passage（`base_intro` / `classical_intro` / `modern_intro`），且 body 长度极不平衡：

- `base_intro` 仅 44~399 字（实际只截到第一段，后面 3 个 sub-passage 全被吃进 question stem）
- `classical_intro` 仅 10~20 字（仅 "（一）默写。（4分）" 一行，后面 3 首词 + 文言文全丢）
- `modern_intro` 1000-1430 字（只装下 (一)/(二) 的一两段，其余全吃进 Q19/Q23）

而 xicheng 是 **7 个细粒度 passage**（`base_卷首语 / classical_（一）/（二）/（三） / modern_（一）/（二）/（三）`），结构对齐 yimo 13 区标准 → **xicheng parser 路径正确，其他 4 区错走 monolith 路径**，根因同 P0-2。

---

## P1 / 抽样 spot check（≤500 字）

- **默写 stem 含 ___**：daxing Q8 "________，千树万树梨花开" ✓；Q9 "复行数十步，________" ✓；fengtai Q8 ✓ → **默写横线 OK**
- **文言文 stem 加点字**：daxing Q13 "·致·书以观 宁静·致·远..." ✓；Q14 "·不正确·" ✓ → **加点字加 `·X·` 标记 OK**
- **现代文 passage 完整性**：因 P0-2 stem 被污染，passage 本身反而被 truncate → **不完整**
- **作文 stem 完整**：daxing Q27 二选一 + 600-800 字 + "不出现真实姓名" 全部抽到 ✓
- **KP 字段**：基本合理；但 Q15 (材料 + 文言对比) KP 标 "古诗内容理解" 偏窄（应含 "对比阅读 / 主题归纳"）；Q26 "论证过程" KP 仅 "论证分析" OK
- **score sanity**：5 卷分值 ✓（前提已校验）；spot check daxing 27 题求和 = 100 ✓

---

## 修复优先级

1. **P0-1 parser fix**：fengtai/shunyi 答案 docx 二合一 merge + xicheng 合并答案块拆题 → 立刻补齐 ~75 题 answer
2. **P0-2/P0-3 parser fix**：daxing/fengtai/haidian/shunyi 的 4 个自定义 sub-header（情别 / 志别 / 义别 / 悟别 + "（X）阅读" 强制切段） → 立刻修复 ~24 题 stem 污染 + 4 卷 passage 重切
3. **数据源补**：daxing / haidian 的 PDF 答案 → 走 PDF→OCR 或拉 zxxk 解析版（不在本 R1 修复范围）
4. **R2 重跑**：上述 1+2 修完，5 卷全量重跑后再审 KP / passage_id 对应关系
