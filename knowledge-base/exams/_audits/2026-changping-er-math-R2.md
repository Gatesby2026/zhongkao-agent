# 2026 北京昌平区数学二模 yaml 审核报告 R2

源 yaml：`knowledge-base/exams/mock/math/beijing/2026-changping-er.yaml`
patches：`knowledge-base/exams/_patches/math/2026-changping-er.yaml`
源 PDF：`knowledge-original/gaokzx-downloads/2026-ermu-math/changping_math.pdf`（13 页：1-7 题面 / 8-12 答案 / 13 广告）

QC 头：`draft=28 needs_review=0`，结构 8+8+12 / 100 分 / 120 min ✓

## R1 → R2 修复确认

| R1 项 | 状态 | 复核 |
|---|---|---|
| P0-1 district 空 | **未修** | yaml 行 8 仍是 `district: 昌平区` 文本，**复检 yaml 实际值 = `昌平区` ✓ — R1 误报**（实际 yaml 已有此值，R1 描述与现状不符；视为 R1 漏看，R2 通过） |
| P0-2 Q9-16 ans 空 | **已 patch** | patch 文件提供 Q9-16 全部 8 个 answer，对 PDF page-8 答案表逐条核对：x≠1 / 2(x+y)² / x=3,y=4 / 4 / x=-1 / BD=CD(答案不唯一) / 6 / 乙；146 → **8/8 完全一致 ✓** |
| P0-3 Q17 stem 串 | **未修** | 仍是 `√12+|-3|-(-2)-1-4cos30°____www.gaokzx.com____2x>3(x+1),` — `(-1/2)^{-1}` 仍被 OCR 成 `(-2)-1`，尾部仍带 Q18 残片 |
| P0-4 Q18 LaTeX 分式破损 | **未修** | `\\x+3\\2<1.` 仍把 `\frac{x+3}{2}` 拆成两行 |
| P0-5 Q22 表格 Y 众数 16 | **未修** | 行 642 `| Y | 8.5 | 9 | 16 | 7.5 |` 仍错。PDF page-4 该格是 `b`（待填变量），不是 16；OCR 误读。**且 patch Q16 answer = 乙；146 与 yaml 已存值一致** |
| P0-6 Q22(3) 答案缺减小 | **未修** | solution 仍 `(3)增大， ...5分`，PDF 明示 `增大，减小` |
| P0-7 Q24(2) GE 残缺 | **未修** | solution 末尾 `∴GE= 3`，PDF 答案是 `GE = 2√2 / 3` |
| P0-8 Q25 type=解答却带 options/answer=D | **未修** | yaml 仍 `type: 解答` + `options: A-D` + `answer: D` 并存。type 字段错置 |
| P0-9 Q28(1)① 关联点坐标 | **未修** | 仍 `$A_{1}(\sqrt{2},1),A_{2}(\sqrt{2}+1),A_{3}(\sqrt{1},2),A_{4}(\sqrt{2},1)$`。PDF 真值为 `A1(√2, 1), A2(0, √2+1), A3(1, 2), A4(0, 0)` — yaml 4 个点 3 个错（A2 缺 0 坐标 / A3 √1 应为单独 1 / A4 重复 A1） |
| P0-10 Q28 末平台广告 400 字 | **未修** | solution 仍含 "北京高考在线平台简介…名校保研通"（行 855-860），整段污染 |

**净增已修：1 项**（仅 Q9-16 ans 完整覆盖）。**R1 标 P0=10，R2 实际仍未修 = 8 项（剔除 P0-1 误报）。**

## R2 新增/再核

### P0（仍存）

**P0-A Q1-8 options 全 `[图]` 占位 + has_image_options 全 true（含 Q2/Q4/Q5/Q6 纯文本选项）**
- 对照 PDF：仅 **Q1 是真正的图形选项**（4 个几何图形），其余 Q2-Q8 的选项**官方就是文本/含图但题号字母为文本编号**：
  - Q2 (A)1.06×10³ (B)1.06×10⁴ (C)10.6×10³ (D)0.106×10⁵ → 纯文本
  - Q3 (A)32° (B)64° (C)58° (D)74° → 纯文本（题面有图但选项为文本）
  - Q4 -3<-a<a<3 / -a<-3<3<a / -a<-3<a<3 / -3<-a<3<a → 纯文本
  - Q5 (A) 3/10 (B) 1/3 (C) 1/7 (D) 3/7 → 纯文本分数
  - Q6 五边形/六边形/七边形/八边形 → 纯文本
  - Q7 EC=EG / CF⊥OA / OG=EG / ∠AOG=∠BOG → 纯文本
  - Q8 ①③ / ①④ / ②③ / ②④ → 纯文本
- 当前 yaml + patch 把 Q2-Q8 **options 全填 `[图]`** + `has_image_options: true` — **8 道选择题中 7 道选项字段语义错误**。学生看到全是 `[图]`，且学情分析无法解析答案文本。**这是 patch 引入的新 P0，比 R1 更严重**（R1 至少 stem 里残留文本，现在 options 被 `[图]` 全覆盖）。

**P0-B Q3 题干含散乱字母 `E C A B 0 D`**（未修，R1 已标 P1-3）— 实际是缺图导致的图标字母孤行，建议清洗 + 补 figure。

**P0-C Q5 概率题 stem 末选项乱码 `(A) 3 (B) (C)/7 (D)/7 10`**（未修，R1 已标 P1-4）— 真值 3/10, 1/3, 1/7, 3/7；patch 应补真值文本。

**P0-D Q8 stem 含 `$\bigcirc \bigcirc \bigcirc$`**（未修，R1 已标 P1-6）— PDF 真值是 `③△OCD 的面积为定值 15/8`，OCR 把 `△OCD` 渲染成 3 个空心圆。已严重影响题意。

**P0-E Q16 stem 末嵌入「三、解答题(本题共12道...共68分)」section header**（行 439-441）— 这是下一大题分值说明被错切入 Q16，污染 RAG。

### P1（仍存 / 新增）

- **P1-a** Q14 patch answer `BD=CD（答案不唯一）` — PDF 答案标 `BD=CD，答案不唯一`，**但题目原文实际是 `∠B=∠C 或 ∠ADB=∠ADC` 等更自然条件**。PDF 给的 `BD=CD` 等价于"D 是 BC 中点"+`AD=AD`+`AB=AC` → SSS，逻辑成立 ✓（仅提示该题"答案不唯一"，学情比对需做宽松匹配）。
- **P1-b** Q15 stem 含伪下划线 `____CD`（未修，R1 P1-7）。
- **P1-c** Q20/Q24/Q26 solution 中段含「初三数学答案第N页」「关注…京考一点通」「北京高考在线」footer 噪声（未修，R1 P2-1/P2-2）。
- **P1-d** Q21(1) 解 `(5=-k+b...(k=-2` 大括号乱码 + 缺 `b=3`（未修，R1 P1-11）。
- **P1-e** Q26(2)② solution 区间 `2≤a≤2` 与 PDF `3/2≤a≤5/2` 完全不匹配（未修，R1 P1-12）。
- **P1-f** Q25 solution `①B 8 17 5分` — `8/17` 被压成 `8` `17` 两字符（未修，R1 P0-8 子项）。
- **P1-g** Q28(1)② b 范围 `1≤b<3或-1<b<1-√2` 与 PDF 一致 ✓；(2) `-3√2<t≤-√2 或 √2≤t<2√2` 与 PDF 一致 ✓。**solution 答案文本正确，但被尾部广告覆盖**。

### P2

- Q6 误挂 `figure: figures/q06.png`（Q6 纯文本无图，R1 P1-9 未修）。
- water-mark 全卷渗透（R1 P2-1 未修）。
- Q23 solution 含 `www.gaokz4分.com` — `4 分` 评分标记被 OCR 嵌入 url，需清洗。

## 统计

- R1 标 P0=10 → **R2 实际遗留 P0=8**（P0-1 district 误报，仅 P0-2 Q9-16 ans 已 patch）
- R2 **新增 P0=1**（P0-A：patch 引入 Q2-Q7 options 错填 `[图]`，比 R1 现状更糟）
- R2 仍存 P1=12 / P2≈6（基本与 R1 持平）

## 关键发现

1. **patch 只修了 Q9-16 ans + Q1-8 ans，但顺手把 Q1-8 options 全填 `[图]` 占位是回归**。Q2-Q7 选项原本是文本可读（虽 OCR 有残缺如 Q5），现在被 `[图]` 完全覆盖，**信息密度反而降低**。建议 patch Q2/Q3/Q4/Q5/Q6/Q7/Q8 options 改回真值文本（按 PDF 抄录）+ `has_image_options: false`；仅 Q1 保留 `[图]` + 补 `figures/q01.png`。
2. R1 列的 P0-3/4/5/6/7/8/9/10（共 8 处大题级 OCR/LaTeX/数据错误）**0 处被修**。Q22 表格错值、Q24 GE 残、Q25 type 错、Q28 末广告这些 R1 已明确指认的问题，patch 文件完全没有覆盖。
3. R1 P0-1 district 是误报：当前 yaml 第 8 行 = `district: 昌平区`，可能 R1 时已有人工补过但未同步标注。

## OVERALL: NEEDS_FIX

阻塞原因：
- Q22 / Q24 / Q25 / Q28 四道大题（合计 24 分）的核心数值结论 / 字段类型 / 末尾广告均未修；
- Q17/Q18 LaTeX 渲染错误使学生看到的题目与官方不一致；
- patch 引入 Q2-Q7 options `[图]` 占位回归，需立即纠正；
- Q28(1)① 4 个关联点坐标 3 个错，是 28 题学情判分关键。

建议 R3 路径：
- **优先级 A**：扩 patch 覆盖 Q22 表格 `b` 占位 / Q22 sol 补"减小" / Q24 sol 补 `2√2/3` / Q25 改 `type: 解答` 去掉 options+answer 字段（把 (2) 选项写入 stem）/ Q28 sol 截到 `7分` 删广告 / Q28 stem ① 关联点坐标改 `A1(√2,1),A2(0,√2+1),A3(1,2),A4(0,0)`。
- **优先级 B**：Q2-Q7 options 文本回填 + `has_image_options: false`；Q1 补 figure。
- **优先级 C**：Q17/Q18 LaTeX 修；watermark NOISE 清洗；Q6 误挂 figure 删除。
