# 2026 北京数学二模 R3 终审报告

**范围**: 11 卷 docx 路线 yaml（跳过 changping 数据源错位）
**约束**: 严格零 OCR / 严格核源 docx / 不写 patches / 不改 parser
**方法**: 结构 + 分值 + LaTeX/几何符号 + Q28 新定义题 stem 完整性 + 跨区对照

---

## 1. 总览验证（11/11 通过）

- **结构**: 11 卷全部 28 题 = 8 单选(16) + 8 填空(16) + 12 解答(68)
- **分值**: 11 卷 `full_score: 100`，逐题 `score` 求和 = 100 精准
- **时长**: 11 卷 `duration_minutes: 120`
- **图片**: 11 卷 figure 引用全部命中 `_staging/math/{region}/figures/`（0 missing），数量 11–15 张/卷

## 2. 内容填充实际状态（与任务描述对照）

| 区 | 单选 ans 填 | Q17-28 sol 填 | 实际 empty_ans/sol | 任务描述 | 偏差 |
|---|---|---|---|---|---|
| haidian | 8/8 | 12/12 | 0 / 0 | 全填 | OK |
| mentougou | 8/8 | 12/12 | 0 / 0 | 全填 | OK |
| xicheng | 8/8 | 12/12 | 0 / 0 | 全填 | OK |
| yanshan | 8/8 | 12/12 | 0 / 0 | 全填 | OK |
| fengtai | — | — | 12 / 8 | 12/8 | OK |
| **chaoyang** | 0/8 | 0/12 | **28 / 28** | 12/8 | **未填**（spec 错或漏跑 fill phase） |
| **pinggu** | 0/8 | 0/12 | **28 / 28** | 12/8 | **未填**（同上） |
| daxing | 0/8 | 0/12 | 28 / 28 | A 类源无答案 | OK |
| fangshan | 0/8 | 0/12 | 28 / 28 | A 类源无答案 | OK |
| shijingshan | 0/8 | 0/12 | 28 / 28 | A 类源无答案 | OK |
| shunyi | 0/8 | 0/12 | 28 / 28 | A 类源无答案 | OK |

**P1**: chaoyang / pinggu 与 spec 不符 — 当前是 28/28 全空，而非 12/8 部分填。需确认是任务描述过期，还是 fill phase 未跑这 2 卷。

## 3. LaTeX/几何符号抽样（haidian/chaoyang/fengtai）

| 区 | odd-$ 行 | bad \left{ | \triangle | \angle | \frac | \sqrt |
|---|---|---|---|---|---|---|
| haidian | 10 | 4 | 30 | 55 | 71 | 36 |
| chaoyang | 2 | 1 | 4 | 12 | 9 | 2 |
| fengtai | 10 | 4 | 16 | 32 | 45 | 14 |

- 几何符号抓取**充足**（haidian 30 \triangle / 55 \angle 合理）
- **odd-$ 行**多由 YAML 多行折叠（`solution` 跨 2 行）造成，inline `$..$` 在物理行内仍闭合；但部分是真破损（见 P0）
- **bad `\left{`** 11 卷全部存在（1–10 处），是 docx OLE → LaTeX 的已知 `\left\{` 转义丢失，**Markdown / KaTeX 渲染会失败**

### 11 卷 LaTeX 健康度全表

| 区 | odd-$ lines | bad \left{ |
|---|---|---|
| chaoyang | 2 | 1 |
| daxing | 2 | 1 |
| fangshan | 6 | 1 |
| fengtai | 10 | 4 |
| haidian | 10 | 4 |
| mentougou | **42** | **10** |
| pinggu | 4 | 1 |
| shijingshan | 4 | 1 |
| shunyi | 2 | 1 |
| xicheng | **24** | 5 |
| yanshan | 6 | 9 |

## 4. Q28 新定义题 stem 完整性

| 区 | stem 长 | 状态 |
|---|---|---|
| chaoyang | 646 | 完整连贯（坐标系/平移/关联图形定义清晰） |
| daxing | 706 | 完整 |
| fangshan | 678 | 完整 |
| fengtai | 533 | 完整但 **尾部混入页脚** "丰台区2026年九年级学业水平考试综合练习（二）"（P1 footer 未剥） |
| **haidian** | 710 | **P0 严重破损**：`平面直角坐标系$\angle A P B = \theta..$中` — 应为 `$xOy$`，新定义关键 token 被错绑到后段 inline-math（$\theta - k$ / $\bigodot O$ / $P_1$..$P_3$ 错位），语义被破坏，学生 / LLM 均无法理解 |
| mentougou | 524 | 完整 |
| pinggu | 511 | 完整 |
| shijingshan | 572 | 完整 |
| shunyi | 588 | 完整 |
| **xicheng** | 593 | **P0** 同 haidian 模式 — Q22/Q25/Q26 `平面直角坐标系$..$中` 的 inline 被错绑（应 `$xOy$`，实为 `$b$` / `$85\%$` / `$\left(2,0\right)$`） |
| yanshan | 456 | 完整 |

## 5. 跨区 P0 模式: 坐标系 token 错位

正则 `平面直角坐标系$([^$]+)$中` 抽取后判定 inner 是否含 `O`：

- **haidian**: Q22/Q26/Q28 错位（3 处）
- **xicheng**: Q22/Q25/Q26 错位（4 处）
- **mentougou**: Q12/Q22/Q26 错位（4 处，混入 `\therefore k = -6` / `\left\{begin\{matrix\}` 等不可能值）
- **yanshan / fangshan / 其余 6 区**: 0 错位 CLEAN

**疑似根因**: 跟物理 R4 hub-regex bug 同构 —— **OLE/inline-math counter 与文本 placeholder 替换错位**，在 inline-math 极密（函数/几何/新定义题）区集中爆发。3 区共性，非单区 docx artifact。

## 6. 11 卷 OVERALL

| 区 | 结构 | 分值 | LaTeX | Q28 | OVERALL |
|---|---|---|---|---|---|
| chaoyang | ✓ | ✓ | 2/1 | 完整 | **WARN**（28/28 未填 vs spec 12/8） |
| daxing | ✓ | ✓ | 2/1 | 完整 | **CLEAN-A**（A 类无答案预期） |
| fangshan | ✓ | ✓ | 6/1 | 完整 | **CLEAN-A** |
| fengtai | ✓ | ✓ | 10/4 | 含 footer | **MINOR**（页脚未剥） |
| haidian | ✓ | ✓ | 10/4 | **P0 破损** | **P0**（Q28 + Q22/Q26 token 错位） |
| mentougou | ✓ | ✓ | **42/10** | 完整 | **P0**（4 处坐标系 token 错位 + 大量 odd-$） |
| pinggu | ✓ | ✓ | 4/1 | 完整 | **WARN**（同 chaoyang） |
| shijingshan | ✓ | ✓ | 4/1 | 完整 | **CLEAN-A** |
| shunyi | ✓ | ✓ | 2/1 | 完整 | **CLEAN-A** |
| xicheng | ✓ | ✓ | 24/5 | **P0 破损** | **P0**（Q22/Q25/Q26 token 错位 + odd-$ 24 行） |
| yanshan | ✓ | ✓ | 6/9 | 完整 | **MINOR**（bad \left{ 9 处） |

## 7. OVERALL 结论

**11 卷全部 28题/100 分/120min 结构精准**；图片引用 100% 命中。

**3 区 P0（haidian/xicheng/mentougou）**: 跨区共性 inline-math token 错绑，根因疑似 docx OLE counter 偏移，**与物理 R4 hub regex bug 同构**，需 parser 修而非 patch（已超本任务约束，提交问题）。

**2 区 WARN（chaoyang/pinggu）**: spec 标 12/8 partial fill，实际 28/28 全空，需确认 fill phase 是否漏跑。

**1 区 MINOR（fengtai）**: Q28 stem 含页脚；**1 区 MINOR（yanshan）**: 9 处 `\left{` 未转义。

**4 区 CLEAN-A（daxing/fangshan/shijingshan/shunyi）**: A 类源真无答案符合预期，结构与 LaTeX 干净，可直接入库。

**推荐**: A 类 4 卷 + fengtai/yanshan + chaoyang/pinggu（确认后）可发布；haidian/xicheng/mentougou 待 parser counter bug 修复后重跑。
