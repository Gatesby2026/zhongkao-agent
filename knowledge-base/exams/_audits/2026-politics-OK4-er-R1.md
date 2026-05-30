# 2026 北京道法二模 4 卷 docx 路线 R1 跨区审核

审核区：changping / daxing / haidian / xicheng
源：knowledge-original/zxxk-downloads/2026-ermu-politics/{region}_politics.zip
方法：解 zip 取解析版 docx → 用 python-docx XML 抽段落对照 yaml；零 OCR。

## OVERALL: 1 跨区 parser bug（仅 changping 命中）+ 3 区 CLEAN

---

## 1. 结构总览（4 区一致）

| 区 | 判断 | 单选 | 材料分析 | 作文 | 合计 | 分值 |
|---|---|---|---|---|---|---|
| changping | 10(10) | 10(20) | 3(24) | 2(16) | 25 | 70 |
| daxing | 10(10) | 10(20) | 4(32) | 1(8) | 25 | 70 |
| haidian | 10(10) | 10(20) | 4(32) | 1(8) | 25 | 70 |
| xicheng | 10(10) | 10(20) | 4(32) | 1(8) | 25 | 70 |

- 题数/分值/duration=70min/开卷：全部精准
- judge answer 全部「正确/错误」中文文本 ✓（0 卷出现 √/×）
- 单选 4 选项 A/B/C/D：4 区共 40 题，0 缺项
- 空 answer 5/区：全部命中材料题/作文（答案在 solution），符合设计
- KP：4×25=100 题 0 缺失、0 单字段；module 字段全 "politics"
- passages：每区 1 条，q_range 21-25，OK

## 2. P0 跨区 parser BUG：`_flush_answer_buf` 错切 N.

**仅 changping 命中 3 处**，但是 parser 通用缺陷，跨区潜在风险。

### 现象
changping Q1/Q2/Q3 solution 头部出现错位段落：
- Q1 sol head: "树立远大理想，把个人理想融入国家发展…"（实际是 Q25 倡议书第 1 条）
- Q2 sol head: "努力学习科学文化知识…"（Q25 第 2 条）
- Q3 sol head: "增强社会责任感…让青春在强国建设的征程中绽放光彩！"（Q25 第 3 条 + 收尾）

「详解：」分隔之后才是各题真正详解，未污染。

### 源头
解析 docx para 270-285（Q25 作文【答案】块）写作示例为「亲爱的同学们：…在此我们倡议：1. 树立远大理想… 2. 努力学习… 3. 增强社会责任感…」。

`politics_docx_paper.py:550` `_flush_answer_buf` 的
```python
parts = re.split(r"\s+(?=\d{1,2}\s*[.、．])", text)
```
把这 3 行裂成「1./2./3.」三段，重新分别归到 Q1/Q2/Q3 → 覆盖原本空的 solution（answer 已是「正确」走判断分支不冲突）。

### 影响范围
仅 changping —— 因仅它的最后一道作文示例正文在【答案】块内做了「1. 2. 3.」分条。daxing/haidian/xicheng 的作文示例都是大段叙述无 N. 编号，故躲过。但**任何区下一次出现这种"答案块内分条"的写法都会重灾**。

### 建议修复
`_flush_answer_buf` 在 default_q ≥ 21 (essay/material 上下文) 时，不要按 `\d+\.` 二次拆；或拆完后丢掉 n < default_q 的小段；或要求 N. 必须出现在行首（buffer 行首），不允许跨行 mid-paragraph 切分。

## 3. 抽样事实校验（采样无问题）

- daxing Q11 ans=D 「台湾问题」(中美关系最重要问题)：源 docx 一致
- haidian Q1 ans=正确（人民民主专政）：源一致
- xicheng Q11 ans=C《国家发展规划法》：源一致
- changping Q4-Q10 判断 ans/sol：源一致，无污染
- 4 区 material body (Q21-Q25) stem_tail 抽样：均含完整设问句（"任选两个…"/"结合材料…"），表格 markdown 正常，figures/imageN.png 引用正常

## 4. KP enrich 抽样（道法 8 模块）

涵盖：心理健康、道德教育、公民基本权利、法治社会、强国建设、中华文化、国家与社会、经济发展、生态文明、中国梦、创新驱动、人类命运共同体、爱国主义、集体主义、乡村振兴 等。

抽样合理度：
- changping Q11 教育强国 → kp="强国建设" ✓
- daxing Q11 台湾问题 → kp="国家与社会" ✓
- haidian Q22 文化出海 → kp=[中华文化, 文化自信, 传承创新] ✓
- xicheng Q12 应急救护 → kp=[责任意识, 抗挫折] 合理但偏「心理健康」侧；可加「公共参与」

未见跨科 KP 串味（无生硬塞物理/数学概念）。冒号子分类（"心理健康-抗挫折" / "心理健康：自我认识"）4 区混用两种分隔符（`-` vs `：`），轻度不一致，非阻塞。

## 5. 【详解】同行内容捕获验证 OK

抽 changping Q1 源 `【答案】正确【解析】【详解】"见贤思齐"…` 单行同行结构，yaml Q1 sol 末尾 "详解：" 后文本完整捕获，证明 R3 期固化的 `GENERIC_DETAIL_RE` 同行抽取（politics_docx_paper.py:611-615）跨区稳定。

## 总结

- **结构层**：4/4 卷 CLEAN（题数/分值/类型分布/judge 文本答案/选项/KP enrich）
- **P0 parser bug**：1 个跨区潜在缺陷（`_flush_answer_buf` 错切 essay 答案块 N.），目前仅 changping Q1-Q3 命中（3 题 solution 头部污染），建议 R2 前修 parser 重跑 changping；其余 3 区暂不受影响。
- **建议优先级**：P0 changping Q1/Q2/Q3 sol 清洗 → R2；parser 修复（属源级，可保后续 11 区扩展时不踩同坑）。
