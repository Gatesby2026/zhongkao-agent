# 2026 北京西城区数学二模 yaml 审核报告 R1

源 yaml：`knowledge-base/exams/mock/math/beijing/2026-xicheng-er.yaml`
源 PDF：`knowledge-original/gaokzx-downloads/2026-ermu-math/xicheng_math.pdf`（无文字层，PDF 抽文本为空）
源 PNG：`knowledge-original/beijing-mock-2026/ermo/xicheng/math/images/page-NN.png`（14 页：1-7 为题面，8-13 为答案及评分参考，14 为平台简介）

数据源：image OCR 路线 `math_image_paper.py`（fork physics），yaml 头部声明 `OCR: Qwen-VL-OCR  Enrich: qwen-max`，QC `draft=20 needs_review=8`。

## 卷面元数据

| 项目 | yaml | PDF 真值 | 一致性 |
|---|---|---|---|
| year | 2026 | 2026 | ✓ |
| exam_type | 二模 | 二模 | ✓ |
| subject | math | math | ✓ |
| district | `''` (空) | 西城区 | **P0** — district 为空，与同目录 changping 报告一致问题 |
| full_score | 100 | 100 | ✓ |
| duration_minutes | 120 | 120 | ✓ |
| total_questions | 28 | 28 | ✓ |
| structure | 8单选(16分)+8填空(16分)+12解答(68分) | 一致 | ✓ |

分值分配交叉验证（来自 page-04 题头）：
> 三、解答题（共 68 分，第 17-19 题每题 5 分，第 20-21 题每题 6 分，第 22-23 题每题 5 分，第 24 题 6 分，第 25 题 5 分，第 26 题 6 分，第 27-28 题每题 7 分）

逐题预期分值：Q17=5, Q18=5, Q19=5, Q20=6, Q21=6, Q22=5, Q23=5, Q24=6, Q25=5, Q26=6, Q27=7, Q28=7 → 合计 **68** ✓

yaml 实际分值：Q17=5, Q18=5, Q19=5, Q20=6, **Q21=5（应 6）**, Q22=5, **Q23=6（应 5）**, Q24=6, Q25=5, Q26=6, Q27=7, Q28=7 → 巧合合计仍 68，但 Q21/Q23 分值**互换错置**。

单选 8×2=16 ✓ 填空 8×2=16 ✓ 总分 100 ✓（仅大题分布合，单题分错）

答案对照（PDF page-08 答案表 vs yaml answer 字段）：

| 题 | PDF 真值 | yaml answer | 状态 |
|---|---|---|---|
| 1 | A | `''` | **P0 缺失** |
| 2 | C | `''` | **P0 缺失** |
| 3 | B | `''` | **P0 缺失** |
| 4 | A | `''` | **P0 缺失** |
| 5 | D | `''` | **P0 缺失** |
| 6 | C | `''` | **P0 缺失** |
| 7 | B | `''` | **P0 缺失** |
| 8 | B | `''` | **P0 缺失** |
| 9-16（填空） | x≠3 / 3a(x-1)² / x=2/3 / √5（不唯一） / 5 / 720 / 1/3 / (1)20;(2)1350 | 全空 | **P0 整段缺失**（部分塞在 solution） |
| 25 | (1)4 (2)93 (3)10,48 | `'4'` | **P0 不全且错位** |
| 26 | a≥4/3 | `-1,3,4` | **P0 完全错** |
| 27 | BD+EF=2AC | `10,48` | **P0 串到 Q25 答案** |
| 28 | (1)DF,EF (2)√3≤b≤√10 (3)√3/4≤k<1/2 或 1/2<k≤3/4 | `'93'` | **P0 串到 Q25 m=93** |

## 逐题问题清单

### P0（必修，影响事实正确性）

**P0-1 district 字段为空**
- 第 8 行 `district: ''`，应为 `district: 西城区`。索引/路由/排重失效。

**P0-2 Q1-Q8 全部 8 道单选 answer 全空**
- 行 38, 70, 116, 133, 150, 167, 186, 213 全 `answer: ''`，且 8 题 qc_note 都标"选择题 answer 为空"被打回 `needs_review`。OCR/enrich 未抓 page-08 答案表。
- 正确值：1.A 2.C 3.B 4.A 5.D 6.C 7.B 8.B（顶端 1-8 表）

**P0-3 Q1 has_image_options 但未生成 figure**
- 行 37 `has_image_options: true`，但 yaml 无 `figure:` 字段，意味着 A/B/C/D 鼓形主视图四个图选项**完全丢失**。源 page-01 选项行确实是四个矩形/三角形图。需自动 crop。
- 同样问题：Q2、Q3、Q4、Q5（全部 4 选项为文本/数字但被打 `has_image_options: true`，结果文本选项也未抽出）。

**P0-4 Q2 选项被 has_image_options=true 抹掉 + solution 串入 Q24 内容**
- stem 末尾正确含 (A)-(D) LaTeX，但 `has_image_options: true` 误判 → 选项数据未保存为 options 列表。
- 行 71-72 `solution:` 含 `2 关注北京高考在线…EF=BF=2…∴BN 3 …`，明显是 Q24 (2) 中 BN=4/3 部分的解析串污染 Q2。Q2 实际答案 C，正确解：传统 1000×2.5×10⁶ = 2.5×10⁹ 次。

**P0-5 Q3 stem 尾部混入页眉与下一页内容**
- 行 113-114 `关注北京高考在线官方北京市西城区九年级模拟测试试卷数学2026.5第页(共7页)资料及排名分析信息。`
- 选项也乱：(A) 25°、(B) 35°、错位 `A`/`0`/`B`，`45°` 缺 (C)，(D) 55° 后还塞 `C`。
- has_image_options=true 同样误标。

**P0-6 Q4 / Q5 选项完全缺失**
- Q4 stem 仅含概率题目题干，4 个分数选项 `1/6, 1/4, 1/3, 1/2`（page-02 实拍）未抓到。qc_note 已自报"选择题缺少 options"。
- Q5 同样：选项 `90°, 60°, 45°, 30°` 全丢，answer D=30° 也缺。

**P0-7 Q6 选项全部丢失**
- stem 仅有题干"实数 a，b，c 在数轴上…下列结论中正确的是"，4 个结论选项（涉及 `a>a`/`|a-c|=a+c`/`b+c>0`/`a+b-c>0`）全部丢失。answer 也缺（PDF=C）。

**P0-8 Q7 选项数值缺失**
- page-02 实拍：(A) √3 (B) 12/5 (C) √5 (D) 1/4。yaml 全无。answer 应 B。

**P0-9 Q8 ①②③④ 结论分支与选项 (A)(B)(C)(D) 同时缺失**
- page-02 选项 (A)①③ (B)①④ (C)②③ (D)②④。yaml 全无。answer 应 B。

**P0-10 Q9-Q16 填空题 answer 字段全空，正确答案被错塞 solution**
- Q9 `answer:''` `solution:x≠3` — 应迁移到 answer。
- Q10 `answer:''` `solution:3a(x-1)2` — 缺乘方上标（应 `3a(x-1)^2`），迁 answer。
- Q11 `answer:''` `solution:x=2` — **答案错**！PDF page-08 实拍 `11. x=2/3`，且 OCR 漏分母。
- Q12 `solution:答案不唯一，如√5 3` — 末尾 "3" 是页码污染；正确 `答案不唯一，如 √5`。
- Q13 solution `'5'` 正确，需迁 answer。
- Q14 solution `'720'` 正确，需迁。
- Q15 `solution:'1'` — **答案错**！PDF page-08 实拍 `15. 1/3`（△BEF 面积 = 1/3），OCR 把分式压成 1。需重 OCR 或人工修。
- Q16 solution `(1)20;(2)1350 5 第24题6分…` 正确数值对，但尾部混入题头。

**P0-11 Q16 stem 严重串入 Q17-Q22 全部内容**
- 行 358-418：stem 从 Q16 题干"某商店共有 a 种…"开始，但中段直接拼接 Q17 `计算:`、Q18 `解不等式组:`、Q19 `已知 a-b-4=0`、Q20 `如图，在 Rt△ABC 中`、Q21 研学小组、Q22 一次函数题干，长达 60+ 行。
- 后果：Q16 stem 包含未来 6 个大题，且 Q17-Q19 自己的 stem 几乎被掏空（见下）。

**P0-12 Q17-Q19 stem 几乎空白**
- Q17 (行 437-438)：`stem: '计算:\n\n    {x-3'` — 只剩"计算:"+下一题碎片。实际表达式 `(1/3)^{-1}+4sin45°-√18-(π-2026)°` 完全丢。
- Q18 (行 458-462)：`stem: '解不等式组:\n\n    <x+1,\n\n    4(1-x)>x-2.\n\n    a+b'` — 不等式组左半 `x-3/5` 缺，且尾 `a+b` 是 Q19 碎片。
- Q19 (行 480-488)：`stem` 只剩"已知 a-b-4=0，求代数式 / 的值 / 2a²+ab-b(a+2b) / 考在线 / com" — 没有分式 `(2a²+ab-b(a+2b))/(a+b)` 的完整分母分子结构。

**P0-13 Q20 figure 缺失**
- stem 含"如图，在 Rt△ABC 中"，page-04 有 ABCDE 平行四边形图。yaml 无 `figure:` 字段（同题 stem 字段 figure 字段路径不存在）。

**P0-14 Q22 stem 尾部混入 Q23 起句 + 页眉**
- 行 587 `北京市西城区九年级模拟测试试卷数学2026.5第4页(共7页)` 拖入 stem。
- solution (2) 只剩 `-1≤m≤ 且m≠0` — 上界数字丢失（PDF page-09 实拍：`-1 ≤ m ≤ 3/2 且 m≠0`），分数 3/2 OCR 压没。

**P0-15 Q21 / Q23 分值互换**
- yaml Q21=5，Q23=6；题头规定 Q20-21 每题 6 分、Q22-23 每题 5 分。应 Q21=6、Q23=5。两者刚好对调，需 swap。

**P0-16 Q23 solution 残缺**
- 行 636 `(1)14，22，23;` 只给 m=14、中位数=22、平均数=23 — 数字正确但 (1) 还应有"m=14"标签；(2) `17, A` 正确。但 (1) 详解步骤全删。

**P0-17 Q24 solution 在 `FM=` 处断尾**
- 行 673 末尾 `FM=` 后无值。page-11 实拍 `FM=7/2`、`BN=4/3`。yaml 缺 BN 最终值（学情打分时无法对比"BN=4/3"）。

**P0-18 Q25 answer 字段只给 `'4'`，solution 不全**
- 应为 `answer: (1)4;(2)93;(3)10,48` 或结构化分三小问。
- 当前 answer 只有 `'4'`（第 1 小问），第 2、3 小问没进 answer 字段。
- solution 文本 (2) `m的值是93` ✓，(3) `10, 48` ✓，但缺曲线 C₂ 图说明（图属第 2 小问关键作答）。

**P0-19 Q26 answer 完全错**
- 行 756 `answer: -1,3,4` — `-1,3` 是 (1) A、B 横坐标，但应该是 AB 长 = `3-(-1) = 4`。`4` 单独写也对，但整体格式 `-1,3,4` 无意义。
- (2) 答案 PDF page-12 实拍 `a ≥ 4/3` — yaml answer 完全没体现。

**P0-20 Q27 answer 串到 Q25**
- 行 790 `answer: 10,48` — 这是 Q25 (3) 答案。Q27 是几何证明 + 数量关系，answer 应是 `BD+EF=2AC`（来自 page-13 实拍）。

**P0-21 Q28 answer 串到 Q25**
- 行 819 `answer: '93'` — 这是 Q25 (2) m=93。Q28 三小问真实答案：
  - (1) DF, EF
  - (2) √3 ≤ b ≤ √10
  - (3) √3/4 ≤ k < 1/2 或 1/2 < k ≤ 3/4
- yaml 全错。

**P0-22 Q28 solution 末尾大段平台简介污染**
- 行 825-830 含"北京高考在线平台创办于 2014 年…京考一点通…名校保研通"等 page-14 平台简介整段。约 600+ 字垃圾文本污染 solution，需删。

### P1（应修，影响渲染/学习体验）

**P1-1 Q2 LaTeX `2.5 \times 10^{6}` 全题型可读但选项 LaTeX 与文本"次"粘连**
- 行 62-68 `(A) $2.5 \times 10^{7}$次` 等格式 OK，但 has_image_options=true 同时存在 → options 字段未存，前端渲染时取 stem 内嵌而非结构化 options。

**P1-2 Q10 答案 `3a(x-1)2` 缺幂符**
- 应 `3a(x-1)^2`。

**P1-3 Q15 figure 路径正确但 stem 中 `\triangle BEF` 与中文角逗号符号混排**
- 渲染时 `$\triangle BEF$` 后面接中文逗号无空格，多数渲染器 OK，可不修。但 solution `'1'` 错（见 P0-10）。

**P1-4 全部解答题 solution 含大量 `北京高考在线 / www.gaokzx.com / kzx.com / 关注…京考一点通 / 第N页(共6页)` 水印噪声**
- 影响题解可读性和向 LLM 灌库时的语义噪声。建议在 OCR 后置过滤所有 `gaokzx|京考|微信号|获取更多|高考在线|（共\d+页）|第\d+页` 通配 pattern。
- 当前 Q19、Q20、Q22、Q23、Q24、Q25、Q26、Q27、Q28 全部 solution 命中此噪声 ≥3 次。

**P1-5 Q23 表格 markdown 重复空列**
- 行 625-631 表格末列 `|  |` 多余空列，渲染会多一列。

**P1-6 Q14 表格末尾空白列同上**
- 行 317-323 末列空白多余。

**P1-7 Q16 stem 表格之前的散行 `(1)若 m=69…(2)若丙购买…` 直接没分小问 inline，渲染时与下一题混排无视觉分隔**
- 由 P0-11 串题导致，修复 P0-11 顺带解决。

**P1-8 Q25 stem 表格末尾空列 + `...` 列**
- 行 721-727 X、Y₁、Y₂ 表末两列空。

**P1-9 Q27 solution `△CEF△CDG` / `∴ CD=CE,` 缺连接符与全等符号 `≌`**
- 行 796-797 OCR 把全等符号 `≌` 完全丢掉。涉及全等三角形证明步骤可读性。

**P1-10 Q28 stem `(2)直线:y=x+b(b>0)` 缺前置"l"或"l₁"题号标识**
- 原题 page-07 显示 "直线 l: y=x+b"。OCR 丢字母 l。

### P2（建议，质量打磨）

**P2-1 Q1 stem 末两行 `任 / 任线` 是 OCR 把水印"北京高考在线"压成"任"再误抽**
- 噪声字符串，删除。

**P2-2 Q3 stem `www.g / E / D / A / 0 / B / C` 散字符 + LaTeX 角度排版差**
- 由图标签 + 水印切片导致，建议 figure crop 后从 stem 移除。

**P2-3 KP 模块映射全 28 题逐项检查**
- Q1 三视图 → geometryComprehensive ✓
- Q2 科学记数法 → numbersAndExpressions ✓
- Q3 角的性质/垂直关系 → geometryComprehensive ✓
- Q4 概率 → statisticsAndProbability ✓
- Q5 多边形内角和 → geometryComprehensive ✓
- Q6 实数/数轴 → numbersAndExpressions ✓
- Q7 圆 → circles ✓
- Q8 平面直角坐标系/正多边形/反比例函数 → geometryComprehensive（混合了 functions，但题目核心是几何位置判定，可接受）
- Q9 分式 → numbersAndExpressions ✓
- Q10 因式分解 → numbersAndExpressions ✓
- Q11 分式方程 → equationsAndInequalities ✓
- Q12 无理数 → numbersAndExpressions ✓
- Q13 一元二次根判别 → equationsAndInequalities ✓
- Q14 样本估计 → statisticsAndProbability ✓
- Q15 矩形/三角形面积 → quadrilaterals ✓
- Q16 方程组/不等式应用 → equationsAndInequalities ✓
- Q17 代数计算 → numbersAndExpressions ✓
- Q18 一元一次不等式组 → equationsAndInequalities ✓
- Q19 代数式化简求值 → numbersAndExpressions ✓
- Q20 直角三角形/平行四边形/三角函数 → triangles ✓
- Q21 方程组应用 → equationsAndInequalities ✓
- Q22 一次函数 → functions ✓
- Q23 统计 → statisticsAndProbability ✓
- Q24 圆切线/相似 → circles ✓
- Q25 函数概念/应用 → functions ✓
- Q26 二次函数 → functions ✓
- Q27 等腰/旋转/证明 → triangles ✓
- Q28 圆/等腰/直线与圆 → circles ✓
- **结论：KP 跨学科污染未发现**（math 28 题分配在 9 个 math 模块内部，无 physics/chinese/english/politics 串入）。✓

**P2-4 Q8 difficulty=能力、Q26/Q28 difficulty=能力 三档分布合理**

**P2-5 全部题目无 LaTeX 块未闭合问题（粗扫 `\$` 配对一致）**

## OVERALL: NEEDS_FIX

**核心结论：**

数据可用度 **< 20%**，**绝不能直接灌库 / 用于学情分析 / 推荐相似题 / 答题卡评分**。

**问题严重度排序：**

1. **22 处 P0**（事实错误 / 数据完全缺失），其中：
   - 8 道单选 + 8 道填空 answer 字段 100% 缺失；
   - Q11/Q15 答案数值错（漏分母）；
   - Q25/Q26/Q27/Q28 四题 answer 互串错位；
   - Q16 stem 吸入 Q17-Q22 全部题干；Q17-Q19 stem 几乎空白；
   - Q1 选项图 + Q3-Q8 文本选项 100% 缺失（图选项需 crop，文本选项需重抽）；
   - Q21/Q23 分值对调错置；
   - 多个解答题 solution 在分式处断尾（Q22 m 上界、Q23 详解、Q24 BN 终值、Q28 整段被平台简介污染）。

2. **10 处 P1**（渲染/语义噪声）：水印噪声未过滤、表格末列、全等符号 ≌ 丢失、LaTeX 上标缺、has_image_options 误判。

3. **5 处 P2**（打磨建议）。

**根因诊断：**

- **OCR 主管道选错**：math_image_paper.py 似乎对 page-08 答案表（横排 "题号 1-8 / 答案 A C B A D C B B"）解析失败，导致全部单选/填空 answer 字段悬空。需要为 math 单独写一个"答案对照表抽取器"（physics 的 fork 在 math 答案表布局上不通用）。
- **题号边界识别失败**：Q16 末尾"关注北京高考在线…"页眉水印让 parser 误以为 Q16 未结束，于是把 Q17-Q22 全部吸入 Q16 stem，剩余题号被掏空。`PAGE_BREAK_PATTERN` 需加 `共\d+页` 强力 split。
- **answer 字段路由错乱**：Q25-Q28 四道大题 answer 出现 4/10,48/93/`-1,3,4` 交叉污染，疑似 enrich 阶段把 solution 末段"最终答案"匹配到错误题号（题号 detection 偏 1-2 题）。
- **has_image_options 误判**：Q1-Q5 全部命中 true，但实际只有 Q1 是图选项。需复核 detector（可能是"(A)"前空格/位置阈值太松）。

**建议处置（按优先级）：**

1. **P0 紧急**：手补 8 道单选 + 8 道填空 answer（page-08 表 1 分钟人工拷入）；
2. **P0 紧急**：Q25-Q28 四题 answer 字段全部重写（用本报告第 2 节给出真值）；
3. **P0 重要**：重跑 OCR 加强 page-03 "（共7页）" 页脚 split，恢复 Q16-Q22 stem；
4. **P0 重要**：Q1 figure crop + Q3-Q8 重抽文本选项；
5. **P1**：增加 gaokzx 系列水印过滤，重新 enrich 一遍 solution；
6. **P2**：district 字段补全（写入 `北京西城区` 或 `xicheng`）；Q21/Q23 score swap。

修复后建议进入 R2 再审。
