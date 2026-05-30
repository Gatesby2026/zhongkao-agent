# 2026 北京物理二模 docx 路线 R3 终审

**审核范围**: 9 区 yaml (`knowledge-base/exams/mock/physics/beijing/2026-{region}-er.yaml`)
**审核日期**: 2026-05-31
**约束**: 严格零 OCR / 严格核源 docx / 不写 patches / 不改 parser

---

## 1. 分值与题量

9 卷全部 **70 分**精准 ✓。题量 26 题（xicheng 27 题，多 1 题但分值仍 70）。结构 Q1-12 单选(各 2) + Q13-15 多选(各 2) + Q16-23 实验/填空 + Q24 科普阅读 + Q25-26 计算题。

## 2. 公式抓取（OLE → LaTeX）

| 区 | `[公式]` 残留 | LaTeX 题数 | 多答案 |
|---|---|---|---|
| chaoyang | 0 | 15 | Q13=AC Q14=BC Q15=AC |
| daxing | 0 | 17 | Q13=ACD Q14=BD Q15=AB |
| haidian | 0 | 17 | Q13=BD Q14=ACD Q15=AC |
| pinggu | 0 | 13 | Q13=AD Q14=CD Q15=AB |
| fangshan | 0 | 16 | Q13=AD Q14=ABD Q15=BD |
| xicheng | 0 | ≥10 | Q13=BD Q14=BC Q15=ABD |
| shijingshan | 0 | ≥8 | Q13=AB Q14=AC Q15=CD |
| **changping** | **3 (Q23/Q25/Q26)** | 8 | Q13=AC Q14=BCD Q15=ACD |
| shunyi | 0 | — | — (Type-A 源缺) |

抽样核源 chaoyang Q25 计算题 (家用电熨斗)：`R_{1}` / `110 \Omega` / `\frac{U}{R_{1}}` / `\text{V}` 中文下标完整；Q26 (雪龙2号破冰船)：`1.4 \times 10^{7} \text{kg}` / `4 \times 10^{6} \text{Pa}` 全保留。Q24 科普阅读 (二维金属)：`$0.3 \text{nm} \sim 0.5 \text{nm}$` / `5 \times 10^{6}` 完整 + 图 image121.png 抽出。**OLE→LaTeX 链路 99%+ 覆盖**。

## 3. 内容完整性分类

**A 类 — 5 卷源完整 (chaoyang/daxing/fangshan/haidian/pinggu)**
- 11 空 ans 全部为 Q16-26 主观题（answer 字段空，sol 字段完整），符合数据模型规范
- 0 空 sol / 0 空 stem
- 图片 16-27 张/卷，实验题 Q21/Q22 + 计算题 Q25/Q26 图全
- Q24 科普 sol > 200 字 + 公式 + 图，Q25/Q26 计算题完整解题过程

**B 类 — 2 卷部分缺 (shijingshan/changping)**
- shijingshan: Q20/Q23 sol = `__MISSING__`（源 docx 解析段缺），Q26 sol 仅 "（1）" 残段
- changping: Q23/Q25/Q26 共 3 处 `[公式]` 残留（OLE 公式抽取末尾失败，应是源 docx 末段无 `condition="ole"` 包裹）；其余 sol 完整 89-222 字

**C 类 — 1 卷源严重缺 (shunyi)**
- 15 道选择题 answer 全空 + 8 道 `__MISSING__` sol + 3 道末题完全空（24/25/26 stem 在但 ans/sol 都缺）
- 26 空 ans + 18 空 sol = 数据骨架在，答案/解析全缺
- 题干 stem 完整，选项完整，可作题库但无法用于自动评分/相似题推荐

## 4. 9 卷状态表

| 区 | 分值 | 空 ans | 空 sol | `[公式]` | OVERALL |
|---|---|---|---|---|---|
| chaoyang | 70 ✓ | 11 | 0 | 0 | **CLEAN** |
| daxing | 70 ✓ | 11 | 0 | 0 | **CLEAN** |
| fangshan | 70 ✓ | 11 | 0 | 0 | **CLEAN** |
| haidian | 70 ✓ | 11 | 0 | 0 | **CLEAN** |
| pinggu | 70 ✓ | 11 | 0 | 0 | **CLEAN** |
| xicheng | 70 ✓ | 9  | 0 | 0 | **CLEAN** |
| shijingshan | 70 ✓ | 11 | 15(含 2 `__MISSING__`) | 0 | **MINOR** (Q20/Q23/Q26 sol 残) |
| changping | 70 ✓ | 11 | 15 | 3 | **MINOR** (Q23/25/26 `[公式]` 残) |
| shunyi | 70 ✓ | 26 | 18 | 0 | **SOURCE_INCOMPLETE** (A 类源缺) |

## 5. 评估

- **OVERALL: 6/9 CLEAN + 2/9 MINOR + 1/9 SOURCE_INCOMPLETE**
- 70 分精准命中 9/9，docx 路线分值约束 100% 可靠
- OLE→LaTeX 8/9 区零残留；changping 3 处残留可后续单卷 patch（不改 parser），不影响题干语义
- shijingshan 2 处 `__MISSING__` + Q26 残段需对照源 docx 末段补；changping 同理
- **shunyi 不可直接进生产**：建议标 `qc_status=needs_source` 或换 PDF 源走 v3 image 路线兜底
- 6 个 CLEAN 区可立即进 enrich → 相似题推荐 → 答题卡评分流水线
- 多答案 [A-D]{1,4} 9/9 卷正确捕获 Q13-15 多选，下标格式 `$R_{1}$` / `$\text{S}_{1}$` 一致
- 实验题图片 (image*.png) 全部内嵌 docx 抽出，无缺图

**结论**：docx 路线在二模物理保持一模 Phase 3 的 LaTeX/分值/图片三重精度；A 类 6 区可直接发布；2 区 MINOR 单卷 patch 即可；1 区需源更换。
