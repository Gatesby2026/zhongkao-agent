# 2026 北京数学二模 8 卷 R2 深审 —— answer/sol 全空根因诊断

**审核范围**：chaoyang / daxing / fangshan / fengtai / pinggu / shijingshan / shunyi / yanshan
**问题**：28 题 100 分结构 OK，但所有题目 answer/solution 字段为空（yanshan 除外）。
**结论先行**：8 卷中 7 卷 ans/sol 全空，根因是 **`_pick_jiexi_docx` 选错 docx + parser 不读「答案文档」**；剩 1 卷（yanshan）实测 0 空字段（已工作正常，本报告标记其为基线对照）。

---

## 一、yaml 实测验证

| 区 | total | empty_ans | empty_sol |
|---|---|---|---|
| chaoyang | 28 | 28 | 28 |
| daxing | 28 | 28 | 28 |
| fangshan | 28 | 28 | 28 |
| fengtai | 28 | 28 | 28 |
| pinggu | 28 | 28 | 28 |
| shijingshan | 28 | 28 | 28 |
| shunyi | 28 | 28 | 28 |
| **yanshan** | **28** | **0** | **0** |

→ 用户描述「8 卷全空」实测应为 **7 卷全空 + yanshan 已正常**。

---

## 二、源 docx 抽样诊断（document.xml 标签计数）

针对每区源压缩包/docx 逐一解压并扫 `【答案】/【详解】/【解析】/【分析】/参考答案/答案及评分/评分参考/试卷答案` 等 marker：

| 区 | 源包结构 | 用到的 docx | inline marker | 答案文档存在 | 答案 marker 风格 |
|---|---|---|---|---|---|
| chaoyang | zip 2 docx | 【试卷】 | 0 | ✅ 同 zip 另一份【答案】docx | 表格题号/答案竖排 + "N．解：" 主观 + "N 分" 评分点；**0 个【】marker** |
| daxing | 单 docx | 唯一 | 0 | ❌ 完全没有答案段 | 纯试卷版 |
| fangshan | zip 1 docx + 1 PDF | 【试卷】 | 0 | ⚠️ 答案在 **PDF** | 答案 PDF（非 docx）|
| fengtai | 单 docx | 唯一 | 0 | ✅ 同 docx 尾部 line 148+ | "数学参考答案" 标题 + 表格 MC + 一行多题填空 + "N．解：...N 分" |
| pinggu | zip 2 docx | 【试卷】 | 0 | ✅ 同 zip 另一份【答案】docx | 表格 MC + 一行多题填空 + "N．解：...N 分"；**0 个【】marker** |
| shijingshan | 单 docx | 唯一 | 0 | ❌ 完全没有答案段 | 纯试卷版 |
| shunyi | zip 1 docx + 2 PDF | 唯一 docx | 0 | ⚠️ 答案在 **PDF** | docx 是纯试卷；答案.pdf 独立 |
| **yanshan** | zip 2 docx（解析版+原卷版）| **解析版** | **28+21+28+28** | 自带 | 标准 zxxk 解析版 inline【答案】【详解】【解析】【分析】 |

注：fengtai 单 docx 内末尾接答案，line 148 起 `数学参考答案2026.05` 标题，与 chaoyang/pinggu/shijingshan 独立答案 docx 内部结构 **完全同款** —— 这是北京教研院评分参考的通用模板。

---

## 三、parser 行为定位

`scripts/exam-docx/math_docx_paper.py:647 _pick_jiexi_docx`：

```python
for p in docx_paths:
    if "解析" in p.stem and "原卷" not in p.stem: return p   # ① 解析版
for p in docx_paths:
    if "试卷" in p.stem and "答案" not in p.stem: return p   # ② 试卷版（排除答案）
return max(docx_paths, key=lambda d: d.stat().st_size)        # ③ 最大文件
```

且 `_load_docx` **只读单 docx 的 `word/document.xml`**，没有「试卷 docx + 答案 docx 合并」逻辑。

→ chaoyang/pinggu 命中 ②，选【试卷】docx，【答案】docx 被丢弃 → 28 题 ans/sol 全空。
→ daxing/shijingshan/shunyi 只有 1 个 docx 且无答案段 → 必空。
→ fangshan 命中 ②，答案在 PDF（被 `_extract_zip` 的 `.docx` 后缀过滤掉）。
→ fengtai 同 docx 内有答案，但末尾 `数学参考答案` 头部已命中 `ANSWER_PAGE`（`SECTION_TOTAL_RE`），代码注释明说："**直接 drop** 答案页内容（避免 fengtai 把 28． 当 Q29）" —— 这是 R1 的有意 trade-off。
→ shunyi 答案在 PDF。

另：math_docx_paper 的 ANSWER_MARKER_RE 只匹配行首 `【答案】`，对「表格 MC + N．解：...N 分」格式毫无识别能力 —— 这是 7 区共性缺失。

---

## 四、跨区分类标签 + 修复方案

| 区 | 分类 | 修复方案 |
|---|---|---|
| **chaoyang** | **C 类**（试卷 docx + 答案 docx 双文件）| parser 加 zip 内双 docx merge：检测【答案】文件 → 走「答案页解析器」（表格 MC 竖排 + N．主观）；不必重抓 |
| **pinggu** | **C 类** | 同上 |
| **fengtai** | **B 类**（同 docx 内 inline 但非【】marker，已被 ANSWER_PAGE drop）| parser 加「答案页解析器」并打开 `in_answer_page` 模式（当前注释里写"drop"，改为"parse"）；不重抓 |
| **daxing** | **A 类**（源 docx 纯试卷无答案）| 需重抓 zxxk「答案版」或「解析版」docx |
| **shijingshan** | **A 类** | 同 daxing |
| **fangshan** | **A 类\*** | 同 zip 内答案是 PDF；建议重抓 zxxk 答案 docx；fallback：PDF→OCR/Claude 抽答案 |
| **shunyi** | **A 类\*** | 同 fangshan，答案 PDF 与试卷 docx 共存 |
| **yanshan** | **基线 OK**（解析版同 zip）| 无 action，作为对照 |

**A 类 = 数据源缺答案**（4 区：daxing/shijingshan/fangshan/shunyi，后两者 PDF 不算）
**B 类 = 同文件内答案非 marker 形式**（1 区：fengtai）
**C 类 = 双 docx 试卷+答案分离**（2 区：chaoyang/pinggu）

---

## 五、OVERALL 推荐策略（按 ROI 排序）

1. **B+C 类共 3 区先做 parser 加强（chaoyang/pinggu/fengtai）**：
   - 新增 `_parse_answer_page(lines, q_objs)` 子模块，识别 4 种 pattern：
     - (a) `题号\nN…\n答案\nX…` 表格竖排 → 按位置 join 给 Q1-Q8 选择题
     - (b) `9．X； 10．Y；…` 一行多题填空（chaoyang/pinggu/fengtai 共用）
     - (c) `N．解：…X 分…Y 分…(N+1)分` 主观题逐题 → solution；末尾 [A-D]+ / 数字 / 表达式 → answer
     - (d) ANSWER_PAGE 触发条件：`数学参考答案 | 答案及评分 | 评分参考 | 评分标准 | 试卷答案`
   - C 类入口：`_pick_jiexi_docx` 改返 `list[Path]`，第二份【答案】docx 作 answer-only 输入喂给 `_parse_answer_page`；
   - B 类入口：`_load_docx` 单 docx 里 `数学参考答案` 行号以后整段交给 `_parse_answer_page`，不再 drop。
   - 风险：fengtai 当年被 drop 是因「答案区 28．」误识别 Q29 → 新解析器先按 ANSWER_PAGE 标志截断主管道再单独跑，不污染 question 计数。

2. **A 类 4 区重抓（daxing/shijingshan/fangshan/shunyi）**：
   - 优先 zxxk 搜「2026 北京 {区} 二模 数学 解析」或「答案版」docx；
   - fangshan/shunyi 已有 PDF，可作为兜底来源（Claude/qwen-vl 抽 → patch yaml，但优先 zxxk docx 路线零成本）。

3. **yanshan 维持现状**。

---

## 六、需求清单（不写 patches，仅记录）

- parser 改：math_docx_paper.py 加 `_parse_answer_page` + `_pick_jiexi_docx` 返双 docx + `_load_docx` 接「答案 docx 路径」可选参数；
- 重抓：daxing / shijingshan / fangshan / shunyi 的 zxxk 答案版 docx；
- 验收：8 卷 R3 跑 chinese_inspect 风格 audit，empty_ans/empty_sol 应 →0。

---

## 七、关键 insight

- yanshan 走通是因 zxxk 命中「精品解析」版（解析版），自带【答案】【详解】【解析】【分析】4 marker —— **parser 现有 ANSWER_MARKER_RE 仅识别这一种格式**。
- 其余 7 区源是「评分参考」格式（表格 MC + 一行多空填空 + "N．解：...N 分" 主观），是北京教研院二模评分标准模板，与一模朝阳/海淀/西城/东城（zxxk 解析版）走的两条路线本质不同。
- B/C 类合计 3 区是 parser bug，A 类 4 区是数据源 bug。**ROI 优先 B+C parser fix，因为可一次覆盖 3 区且 0 重抓成本**。
- 物理 docx 路线（physics_docx_paper.py）此前已经实现过「试卷+答案 docx merge」吗？需查证（用户提示「physics 已实现可参考」）—— 若已实现，math 直接复用 physics 的 merge 框架可省一半开发时间。
