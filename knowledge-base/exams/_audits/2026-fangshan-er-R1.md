# 2026 北京房山区中文二模 R1 审核报告

审核对象: `knowledge-base/exams/mock/chinese/beijing/2026-fangshan-er.yaml`
源 PDF: `knowledge-original/gaokzx-downloads/2026-ermu-chinese/fangshan_chinese.pdf` (13 页, 纯扫描图)
OCR 中间产物: `knowledge-base/exams/_staging/chinese/2026-fangshan-er/tencent-cache/general/page-{01..13}.txt`
管线: chinese **image OCR 路线**（v3 chinese_image_paper.py，腾讯 dual-OCR + section_by_content）

---

## 卷面元数据 vs 源 PDF — 缺题分析

**结论: 没有缺题，yaml 题数与源 PDF 一致。**「缺 2 题 + 6 分」的判断基于错误的 spec（27/100），真实卷面就是 **25 题 / 100 分**。yaml 的 `full_score: 94.0` 是因为 13 道题 score 分配错误导致小计偏低 6 分。

### 源 PDF 全卷结构（来自 OCR + 答案页交叉核对）

| 大题 | 小题 | 分值 | yaml score | 是否一致 |
|---|---|---|---|---|
| 一、基础·运用 (14 分) | 1 选择 | 2 | **1** | ✗ -1 |
|  | 2 选择 | 2 | 2 | ✓ |
|  | 3 选择 | 2 | 2 | ✓ |
|  | 4 选择 | 2 | 2 | ✓ |
|  | 5 病句修改 | 2 | 2 | ✓ |
|  | 6 选择 | 2 | 2 | ✓ |
|  | 7 推荐语 | 2 | 2 | ✓ |
| 二、古诗文阅读 (16 分) | 8 默写 ①②③④ | 4 | **1** | ✗ -3 |
|  | 9 雁门太守行内容 | 2 | **1** | ✗ -1 |
|  | 10 雁门赏析 | 4 | **2** | ✗ -2 |
|  | 11 文言实词 | 2 | 2 | ✓ |
|  | 12 「诚」理解 | 2 | **3** | ✗ +1 |
|  | 13 比较阅读填空 | 2 | 2 | ✓ |
| 三、名著阅读 (5 分) | 14 阅读方法 | 5 | **2** | ✗ -3 |
| 四、现代文阅读 (25 分) | 15 信息筛选 | 2 | **3** | ✗ +1 |
|  | 16 横线补写 | 2 | **5** | ✗ +3 |
|  | 17 三材料梳理 | 3 | **2** | ✗ -1 |
|  | 18 四季概括 | 2 | 2 | ✓ |
|  | 19 句子赏析 | 3 | 3 | ✓ |
|  | 20 「新的老树」 | 3 | **1.0** | ✗ -2 |
|  | 21 成长启示 | 3 | 3 | ✓ |
|  | 22 论题 | 2 | **3** | ✗ +1 |
|  | 23 举例论证作用 | 2 | **4** | ✗ +2 |
|  | 24 AI 时代读书 | 3 | **2** | ✗ -1 |
| 五、作文 (40 分) | 25 二选一作文 | 40 | 40 | ✓ |
| **合计** | **25 题** | **100** | **94** | **-6** |

**Score diff 全部 13 项**: Q1(+1) Q8(+3) Q9(+1) Q10(+2) Q12(-1) Q14(+3) Q15(-1) Q16(-3) Q17(+1) Q20(+2) Q22(-1) Q23(-2) Q24(+1) — 合计 +6, 与 yaml 缺 6 分匹配。

### Root cause

`chinese_image_paper.py` 的 `_type_weight` + section 总分约束 allocator 对**房山卷面**这种 "section 内权重分布不均、且同一题型 1/2/3/4 分都有" 的情况，分配明显失准。典型表现:
- **Q8 默写整组 4 分被压成 1 分**（allocator 把默写当 "1 空 1 分" 而非 "①②③④ 共 4 分"）
- **Q14 名著阅读 5 分被压成 2 分**（独占一大题 5 分，但 allocator 按 "100 字简答 = 2 分" 类型先验扣分）
- **Q16 横线补写选择被抬到 5 分**（OCR 把后续 D 选项与 page 6 头部噪声 "om 北京" 一并并入 stem/options，allocator 误将其当大题填空）
- **Q23 举例论证 2 分被抬到 4 分**（与 Q24 错配；Q24 3 分被压到 2 分）

属于 v3 chinese 路线已知的 **"section + 类型权重 allocator 在 100 分含奇分值时易错配"** 问题。源数据 OCR 都正确捕获到 "(2分)" / "(4分)" / "(5分)" 等显式标注，但 allocator 未优先采纳行内标注。

---

## 逐题问题清单

### Q1 [P0 score]
- score=1，应为 2（stem 已含「(2分)」）。allocator 误判。

### Q2 [P1 options]
- options 全挤在 A 字段:
  ```
  A: 生肖B.坚韧不拔C.窥见D.天人相应
  ```
- 4 选项未拆分。下游展示/做题都会跨选项；建议 R2 切回 4 独立 A/B/C/D。

### Q3 [P1 options]
- options 错位:
  ```
  A: [甲]、[乙]，B.[甲]，\n[乙]、
  C: [甲]，[乙]
  ```
- 缺 D；A 字段裹了 B；C 内容也不全（源是 "[甲]，[乙]。"）。

### Q4 [P1 stem + options]
- stem 末尾混入下一段引文「"青玉马上封侯坠"利用局部沁色的」（来自 page 5 跨页粘连）。
- options 全挤 A 字段同 Q2:
  ```
  A: 活动渐进B.认知融入C.内涵渗透D.文化熏陶
  ```

### Q5 [P1 stem 污染]
- stem 末尾粘了**手记五整段**（约 200 字），把 Q6 的引导段并入 Q5 stem。

### Q6 [P0 options]
- D 选项粘在 C 字段:
  ```
  C: 刚健精巧传神 D.刚健传神精巧
  ```
- D 选项独立项缺失。

### Q7 [P2 stem]
- stem 末尾残留 `()，` 噪声标记（chinese_image_paper.py 的图占位符未清理）。

### Q8 [P0 score + P1 stem]
- score=1，应为 4（默写共 4 分: ①1+②1+③④2）
- stem 把 "意象/诗文/意象批注" 表格 OCR 平铺成段落，混入 "李白《闻王/月昌龄左迁龙标遥有此寄》" 这种**跨列拼接的破句**（"李白《闻王" + 跨行接 "昌龄..."）
- 这是源 PDF 表格 OCR 的固有问题，不是 parser 可单独修复的；qc_note 应注明。

### Q9 [P0 score]
- score=1，应为 2

### Q10 [P0 score]
- score=2，应为 4

### Q11 — OK
- score=2 ✓，options 全挤 A 字段同 Q2/Q4（P1 形式）。

### Q12 [P0 score + P1 options]
- score=3，应为 2
- B 选项截断: `B: 愚公艰苦奋斗、誓要铲平大山的` — 源是 "...铲平大山的决心。"
- solution 末尾残留 `()，` 噪声。

### Q13 — OK
- score=2 ✓
- stem 末尾解释性注释 `[注释]①御:驾车...` 完整保留（合理保留为 stem 的一部分）

### Q14 [P0 score + P2 stem 噪声]
- score=2，应为 5
- stem 末尾噪声 `w()，`

### Q15 [P0 score]
- score=3，应为 2
- solution `评分:本题2分` ✓（说明 OCR 抓到了正确分值，allocator 仍误判）

### Q16 [P0 score + P1 options 噪声]
- score=5，应为 2（异常高，明显 allocator 错配）
- B 选项混 `()，` 噪声
- D 选项末尾混入页脚 `om\n北京`

### Q17 [P0 score + P1 stem]
- score=2，应为 3
- stem `围绕提升青少年阅读素养，以上三则材料分别从①③三kzx绍。(3分)` — OCR 把 "②" 漏读，"方面介" 被水印 "kzx" 截断为 "三kzx绍"。**严重影响 stem 可读性**。

### Q18 — OK
- score=2 ✓

### Q19 — OK
- score=3 ✓

### Q20 [P0 score]
- score=1.0，应为 3（注意是浮点 1.0，疑 allocator 余额回填的残数）

### Q21 [P2 stem 噪声]
- stem 末尾 `()，` 噪声
- solution 末尾混入页边水印 `考`

### Q22 [P0 score + P1 options]
- score=3，应为 2
- options A 字段挤 B: `A: 读书的智慧 B.青春与奋斗`
- C 字段挤 D: `C: 青年与读书D.成才的途径`

### Q23 [P0 score + P2 solution 噪声]
- score=4，应为 2
- solution 中嵌水印 `ga`、`w` 单字符行（来自页脚 "www.gaokzx.com" 残破 OCR）
- solution 中人名 OCR 错: "深圳快递小哥**聂剑**" — 源 PDF 是 "**袁石剑**"（OCR 错字，**非 parser 问题**，需 patch 或重 OCR）

### Q24 [P0 score]
- score=2，应为 3

### Q25 — OK
- score=40 ✓
- solution 把整张 "作文评分标准表格" 完整 OCR 进来；理论上可保留作教师参考，但当前格式破碎、列粘连严重，建议 R2 简化为 "见评分细则" 或人工整理表格。

---

## 跨题模式

### P0 模式

1. **score allocator 失准（13/25 题，占比 52%）** — chinese_image_paper.py 的 section 总分约束 + 类型权重 fallback 没有优先使用 stem 内 "(N分)" 显式标注。建议改 allocator 顺序: **(a) 优先 stem 行内 "(N分)"，(b) 答案区 "本题N分"，(c) 类型权重兜底**。
2. **选项 4 合 1**（Q2 Q4 Q6 Q11 Q22 等至少 5 题）— OCR 把 ABCD 选项在源 PDF 横排紧凑布局下当成 1 行，parser 的选项切分 regex 应增 fallback: 当 options 只有 A 字段且其中含 `B.` `C.` `D.` 时, 强行二次 split。
3. **stem 跨题/跨页粘连**（Q4 Q5 Q14 Q17）— page 边界处 stem 与下题引文/下大题题干粘连，与水印 "om / kzx / 北京高考在线" 混入正文。

### P1 模式

4. **`()，` 图片占位符残留**（Q5 Q7 Q12 Q14 Q21 Q23 至少 6 处）— chinese_image_paper.py 的 figure placeholder 注入器在 image-less section 也注入了空占位 `()，`，应在 _flush_text 前剥离。
5. **页脚水印散落**（"考" "ga" "w" "com" "北京" "om" 等 1-2 字单行）— page-level OCR 噪声未被 NOISE_PATTERNS 滤掉，混入 solution / options。
6. **OCR 错字**（Q23 "袁石剑→聂剑"，Q9 stem 文字大体 OK）— 属真 OCR 误差，需 _patches/。

### P2 模式

7. **passage body 内同样含水印噪声**（base_intro、narrative、argument 三个 passage 的 body 都有 `()，` `om` `m` `com` `W` `ww` 残留）— 不影响做题但影响 LLM 喂题质量。
8. **Q8 默写表格 OCR 破裂**（"我寄愁心与明月，①___。(李白《闻王\n月昌龄左迁龙标遥有此寄》)" 这种跨列错位）— 表格类源数据无法靠 OCR 单 pass 解决，建议人工 patch。
9. **作文评分标准表格**（Q25 solution）— 完整 OCR 进 yaml 但碎成 80+ 行，没有教学价值，建议 patch 删除或简化。

---

## 答案 / 解析 完整性抽样

- 单选题 Q1-Q6, Q11, Q12, Q15, Q16, Q22 的 `answer` 字段全部正确捕获（B/D/C/A/A/A/A/D/D/A/C）。
- 主观题 `answer: ''`（共 13 题）符合规范（语文主观题 answer 字段缺省为空，答案在 solution 里），无问题。
- 作文 Q25 `answer: ''` 符合"作文 answer 空"约束，**不应标记问题**（按用户严禁标记规则）。
- 默写 Q8 / Q13 `answer: ''` 同理，答案在 solution 中（如 Q8 solution 含 "随君直到夜郎西" "征蓬出汉塞" 等正确诗句）。

---

## passages q_range 校验

- `base_intro` (1-7) ✓
- `classical_2` 雁门太守行 (9-10) ✓ — 但**漏了 passage_id 应不应包含 Q8 默写**？源 PDF Q8 是独立默写题（无附文），不该归任何 passage，yaml 正确把 Q8 作 `passage_id` 缺省 ✓
- `classical_3` 愚公移山 (11-13) ✓
- **缺 q_range 8-8 的默写表格"passage"** — 但 Q8 stem 已自带表格，不必单独建 passage，可接受。
- `non_continuous` (15-17) ✓
- `narrative` 窗前的树 (18-21) ✓
- `argument` (22-24) ✓
- **Q14 名著阅读独占一大题"三、名著阅读"**，无附文，不归 passage ✓

passages 结构整体正确，没有 q_range 错配。

---

## KP / module 标注抽样

- Q1 `书写`/writing — 源题是 "评价鉴赏书法笔法"，KP 应是 **`书法鉴赏` / `字体辨识`** 更准；`书写` 偏宽泛。P2。
- Q2 `字音`/chinese — ✓
- Q3 `标点符号运用`/writing — ✓
- Q4 `词语运用`/reading — ✓
- Q5 `病句`/writing — ✓
- Q8 `古诗赏析`/`古诗内容理解`/classical — KP 应加 `名句默写`，当前缺。P2。
- Q11/Q12 `文言文实词` — ✓
- Q13 `文言文理解`/`默写` — `默写` KP 错（这题是比较阅读填空，非默写）。P1。
- Q14 `名著情节`/`人物形象`/`主题理解` — 这题考的是**阅读方法**，KP 应是 `阅读方法` / `名著阅读策略`，当前 3 个 KP 全错。P1。
- Q15-17 信息筛选 / 段落梳理 — ✓
- Q19 `句式赏析`/`修辞手法`/`表达效果` — ✓
- Q20 `信息提取/段落梳理`/`词语含义` — 这题考的是**主旨理解/句子含义**，前一个 KP 偏；应是 `句子含义` `主旨理解`。P2。
- Q22-24 议论文阅读 / 论证分析 — ✓
- Q25 作文 KP ✓

KP 错误约 3-4 处，比同期朝阳/东城卷 KP 标注质量略低。

---

## OVERALL: NEEDS_FIX

**核心问题**: 13/25 题 score 错（占比 52%，累计 -6 分），属于 image OCR 路线 v3 chinese_image_paper.py 的**已知 allocator 缺陷在房山卷的集中爆发**。题数、passages、单选答案、主观 solution 都正确捕获，所以这是 "结构对、分值错" 而非 "题目缺失"。

### 修复优先级

**R2 必修（P0, 6 项）**:
1. 全卷 13 处 score 修正 → 按上表 src 列。
2. 选项 4 合 1 至少 Q2/Q4/Q6/Q11/Q22 五题手拆 ABCD（Q6 须补 D 选项 "刚健传神精巧"，Q12 须补 B 选项尾 "决心"）。
3. Q3 options 重写（A "[甲]、 [乙]，" / B "[甲]，[乙]、" / C "[甲]，[乙]。" / D "[甲]、[乙]、"）+ 补 D 选项。
4. Q4 stem 末尾去除跨页粘连 "...沁色的"。
5. Q5 stem 去除粘连的手记五全段。
6. Q17 stem 修复为 "围绕提升青少年阅读素养，以上三则材料分别从①\_\_\_、②\_\_\_、③\_\_\_三个方面介绍。(3分)"。

**R2 建议（P1, 4 项）**:
7. Q23 solution "聂剑" → "袁石剑"（patch）。
8. Q13 KP 删 `默写`；Q14 KP 改 `阅读方法` `名著阅读策略`。
9. 全卷 `()，` 噪声移除（6+ 处）。
10. passage body 中 "om / kzx / W / ww / com / m" 单字水印清理。

**R2 可选（P2, 2 项）**:
11. Q1 KP 加 `书法鉴赏`，Q8 KP 加 `名句默写`，Q20 KP 改 `句子含义`。
12. Q25 作文评分标准表格 patch 简化。

### 与其他区横向参考

朝阳/东城/海淀二模目前已"精准 100 分 0 误差"，房山是 image OCR 路线（其他几区是 docx 路线），属于流水线选择差异。**根本解法**: 房山若有 zxxk docx 源，建议切换 v4 docx 路线一键全修；若无，需手 patch 13 处 score + 7 处 stem/options。

源 PDF 100 分整数题数 = 25，**spec 上 27/100 的提法是 spec 笔误**，不需要 "找回缺失的 2 题"。
