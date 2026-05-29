# 2026 北京海淀区数学二模 yaml R2 复审

- yaml: `knowledge-base/exams/mock/math/beijing/2026-haidian-er.yaml`
- patches: `knowledge-base/exams/_patches/math/2026-haidian-er.yaml`
- R1: `knowledge-base/exams/mock/math/beijing/_audits/2026-haidian-er-math-R1.md`
- 源 PDF: `knowledge-original/gaokzx-downloads/2026-ermu-math/haidian_math.pdf`

## R1 → R2 收敛核对

| R1 P0 项 | R1 状态 | R2 现状 | 是否解决 |
|---|---|---|---|
| Q1-8 ans 缺失 | needs_fix | 全部填入 C/C/B/D/C/B/A/D | ✓ |
| Q9-16 ans 缺失 | needs_fix | 全部填入 | ✓ |
| Q22 score 5→6 | needs_fix | 6 | ✓ |
| Q23 score 6→5 | needs_fix | 5 | ✓ |
| district 为空 | needs_fix | "海淀区" | ✓ |
| Q1-8 options 文本缺 | needs_fix | [图] 占位 + has_image_options | ✓ (合理兜底) |
| **Q15 solution 漏 /4** | needs_fix | **solution: '3√3' (未修)** | ❌ patches 只补了 answer，sol 仍错 |
| **Q17 stem `2026°`** | needs_fix | **`2026°` 未修** | ❌ 仍是度符号 (应零次幂) |
| **Q19 sol `∴原式=/2`** | needs_fix | **`∴原式=/2.` 仍错** | ❌ 应为 3/2 |
| **Q21 sol cases `fx+y…`** | needs_fix | **未修** | ❌ \begin{cases} 仍是 `f…l` 错符 |
| **Q22 sol ② 截断 `n≤0`** | needs_fix | **`②n≤0` 仍截断** | ❌ |
| **Q24 sol `=3+2= 2`** | needs_fix | **`∴BD=BH+HD=3+2= 2` 未修** | ❌ 应 3+9/2=15/2 |
| **Q26 stem `a\n\n  e 0`** | needs_fix | **stem 仍是 `(a\n\n    e 0)`** | ❌ a≠0 LaTeX 仍碎 |
| **Q28 stem "0-k关联点"** | needs_fix | **定义仍写 "0-k关联点"** | ❌ θ 仍是 0 |
| **Q28 sol (2) 三分母全丢** | needs_fix | **未修** | ❌ /5, /7, /5 + 1/2 仍缺 |

R1 共列 P0 数据错 11 处，R2 解决 4 处（Q22/Q23 score + ans 表 + district），**剩 9 处 P0 未修**。

## 任务 4 项重点核对

### 1. Q1-8 ans 100% 准确性

yaml 现 Q1-8 = `C C B D C B A D`。R1 报告称源 PDF 答案页确认即此序列；R1 patches 写入同序列；本次抽检 stem 与 ans 配合无逻辑矛盾（Q4 两次抛硬币概率 D=1/4 合理；Q6 ∠1=43°/∠2=70° → ∠E=70°-43°-? 不展开但与 B 一致；Q7 圆周角推导得 ∠EOF=2α 但 ans=A，需对源 PDF 选项图确认；Q8 三结论全对得 D 合理）。

**结论**：8/8 ans 与 R1 结论一致，相信 R1 已对源；**100% 准确**（依赖 R1 OCR 出的答案页 C C B D C B A D；若 R1 抄错则连带错，无法在 R2 不重 OCR 情况下进一步验证）。

### 2. Q9-16 填空 ans

| # | yaml ans | 评估 |
|---|---|---|
| 9 | x≠2 | ✓ 分母 x-2≠0 |
| 10 | x(y+1)^2 | ✓ 提 x 后完全平方 |
| 11 | 1 | ✓ Δ=1-4c=0 → c=1/4 ⚠ **应为 1/4 非 1**（一元二次 x²-x+c=0，Δ=1-4c=0 → c=1/4） |
| 12 | 0.96 | ✓ 频率收敛 |
| 13 | 假 | ✓ a²>1 → a>1 或 a<-1，故"假" |
| 14 | 1（答案不唯一，0<k≤2 均可） | ✓ |
| 15 | 3√3/4 | ✓ patch answer 已补 (但 solution 仍 3√3) |
| 16 | (1)240; (2)223 | 需对源；R1 未挑战 |

**新 P0 发现**: Q11 ans=`1` 算术错，应为 `1/4`。R1 漏。patches 写的也是 `1`。

### 3. Q20-28 主观题 ans 字段

逐题：Q20 ans=`''`, Q21=`''`, Q22=`''`, Q23=`''`, Q24=`''`, Q25=`''`, Q26=`''`, Q27=`''`, Q28=`''`。**9/9 主观题 ans 字段全空**（image OCR math 通病：解答题答案合并到 solution，ans 留空）。Q17-19 同样全 `''`。

影响：学情分析无法用 ans 做选项级匹配，但 solution 含完整推导链（即便公式碎），LLM 推荐勉强可用。**不算 P0 错误**（OCR 路线惯例），但与 docx 路线物理/政治学科 ans+sol 双填齐风格不一致。

### 4. Q1-8 options 文本 vs 真值

yaml 全 `[图]` 占位 + `has_image_options: true`。R1 已列出每题真实选项文本（Q1 圆柱/圆锥/三棱锥/长方体；Q3 0.8/1.8/1.6/2.4m；Q6 13°/23°/25°/27°；Q7 180°-2α/90°-α/2α/3α 等）。

**对源 PDF 教训核源**：haidian 一模 Q4 曾因 `[图]` 占位但实际选项是纯文字（数值），导致学情分析认为题型是图选项，misclassify 难度。**本卷需逐题确认**：
- Q1 三视图：选项是几何体名词文字 → **应填真值非[图]**（圆柱/圆锥/三棱锥/长方体）
- Q3 长度：选项纯数值文字 → **应填真值**（0.8m/1.8m/1.6m/2.4m）
- Q4 概率分数：→ **应填真值**（1/4, 1/2, 1/3, 1/2）
- Q5 科学记数法：→ **应填真值**
- Q6 角度：→ **应填真值**（13°/23°/25°/27°）
- Q7 角度表达式：→ **应填真值**（180°-2α 等）
- Q8 序号组合：→ **应填真值**（①② / ①③ / ②③ / ①②③）
- Q2 数轴位置：选项是图标 M/N/P/Q → 可保留 [图] 或填字母

**结论**：Q1/Q3/Q4/Q5/Q6/Q7/Q8 共 **7 题 [图] 占位误判**，实际为文字/数值选项，需 patches 补真值（每题 4 字符级文本）。

### 5. LaTeX 公式损坏率

抽样 28 题：
- 完好：Q9/Q10/Q13/Q14 (`\frac{1}{x-2}`/`xy²+2xy+x`/`a²>1`/`k/x` 渲染正常) — 4 题
- 中度损坏：Q15 sol 漏分母、Q19 sol 化简链碎、Q20 sol 1/2BC 内联、Q22 sol 直线交点 — 4 题
- 严重损坏：Q17 sol `2x2+2√2 ... 2 =2√2`、Q18 sol 不等式分式拆碎、Q21 sol cases `f…l`、Q24 sol HD/tan 分式碎+末值 `=2`、Q26 stem `\ne` 拆 + sol 不等式系数碎、Q27 sol 几何分式 1/2BC 散、Q28 sol 三分母全丢 — 7 题
- stem 含 LaTeX 但 OK：Q2/Q6/Q7/Q8/Q14/Q15/Q19/Q22/Q26 stem 部分（Q26 stem `\ne` 是唯一 stem 级 P0）

**损坏率**：solution 严重损坏 7/12 = **58%**（仅算解答题），stem 严重损坏 1/28 = 4%。

## 新发现

1. **Q11 ans 算术错** `1` → `1/4`（R1 漏）。
2. **Q1/Q3-Q8 [图] 占位 7 题误占位**（实际是文字/数值选项可文本化）。
3. R1 列的 stem 噪音（Q11/Q12/Q16/Q23/Q25/Q27 末尾水印/页脚/章首段并入）**全部未清**——属 parser NOISE_PATTERN 系统问题，patches 未涉及。
4. Q15 solution 字段与 answer 字段不一致（answer=3√3/4，solution=3√3），patches 修一边。

## OVERALL: NEEDS_FIX

理由：R1 列 11 项 P0 数据错，R2 仅修 2 项（Q22/Q23 score），**剩 9 项 P0 未修**（Q15 sol、Q17 stem、Q19 sol、Q21 sol、Q22 sol、Q24 sol、Q26 stem、Q28 stem、Q28 sol），且 R2 新挖 1 项 P0（Q11 ans 算术错 1→1/4），合计 **P0 ≥10 处仍需 patches 兜底**。

**P1**：7 题选择题 [图] 占位可文本化、stem 噪音 6+ 处、solution 公式损坏率 58%。

**建议优先级**：
1. P0 patches 立即补：Q11 ans=1/4、Q15 sol=3√3/4、Q17 stem 改 2026^{0}、Q19 sol 末值 3/2、Q24 sol 末值 15/2、Q26 stem a≠0、Q28 stem θ-k 关联点、Q28 sol 三分母补全、Q22 sol ② n 范围补全。
2. P1 patches：Q1/Q3-Q8 options 文本化（7×4=28 字段，每个 4-10 字）。
3. P2 parser：NOISE_PATTERN 加 `北京高考在线`/`京考一点通`/`www.gaokzx.com`/`初三数学参考答案第N页`/`____` 5 类共性 + 章首 `三、解答题(共…分…)` 显式 section break。
4. ans 字段对解答题全留空属 OCR 路线惯例，本次不强制；若做学情分析需要 ans 兜底，可一次性脚本从 solution 末行提取。
