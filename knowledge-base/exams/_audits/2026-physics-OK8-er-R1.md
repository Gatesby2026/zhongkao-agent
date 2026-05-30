# 2026 北京物理二模 R1 跨区 sanity 审核（8 区 docx 路线）

**OVERALL：WARN（题数/分值全 OK，但 P0 跨区共性 OLE→LaTeX 失败 + 3 区走错管线）**

审核范围：changping / chaoyang / daxing / fangshan / pinggu / shijingshan / shunyi / xicheng（2026-{region}-er.yaml）。
零 OCR / 严格核源 docx（已用 Python cp437→utf-8 解 zip 还原中文文件名）。

---

## 1. 题数 / 分值 / 结构一致性

| 区 | 题数 | 总分 | duration | 结构对账 | 备注 |
|---|---|---|---|---|---|
| changping | 26 | 70 | None ❌ | OK | duration_minutes 字段缺失（应 70）|
| chaoyang | 26 | 70 | 70 | OK | |
| daxing | 26 | 70 | 70 | OK | 结构 7 实验 +3 计算（与 8+2 主流不同，源 docx 一致）|
| fangshan | 26 | 70 | 70 | OK | |
| pinggu | 26 | 70 | 70 | OK | |
| shijingshan | 26 | 70 | None ❌ | OK | duration 字段缺失 |
| shunyi | 26 | 70 | None ❌ | OK | duration 字段缺失 |
| xicheng | **27 ❌** | 70 | 70 | **不符 P0** | structure 写 10 实验 +2 计算（实际 12+0 题大段错）|

P0：**xicheng 27 题**（其他 26）；structure 也写 10 实验探究但实际没有「科普阅读」。源是 PDF（无 docx），走 PDF 管线。

---

## 2. 三区走错管线（P0，致命）

**changping / shijingshan / shunyi** 的 yaml 头注 `OCR: Qwen-VL-OCR  Enrich: qwen-max`，三区共性：
- **全部 26 题 answer 为空**（含 12 单选 + 3 多选 + 11 主观）
- 18/26 solution 为空（含 Q1-Q15 + Q24 + Q25/Q26 计算题）
- 23 题 qc_status=needs_review；qc_note：`选择题 answer 为空` / `解题步骤未提取，需补全 solution`
- `[公式]` 占位符（30~106 处/区，stem 内）零 LaTeX、零图片解析

**根因核源**：这三区的源不是「精品解析（合本含详解）」格式：
- changping：拆成「【试卷】」+「【答案】」两份 docx
- shijingshan：拆成「【试卷】」+「答案定稿」两份
- shunyi：单 docx（160KB，含 35 OLE / 含「答案」无「解析」无「详解」）

`physics_docx_paper.py` 只认「精品解析」合本 → 这三区降级走了 OCR 兜底 → 全空。

**优先级**：必须改 parser 接两段式（试卷 + 答案）并合并，或先人工拼成精品解析等价物，否则三区不可用。

---

## 3. P0 跨区共性：OLE MathType → LaTeX 大面积失败

skill memory 称 docx 物理路线 "**1901 LaTeX 块** + `\rho_{\text{max}}`/`\Omega`/`\text{V}` 100% 保留"，但二模 R1 严重退化：

| 区 | 源 docx OLE | 转 LaTeX 成功（`$..$`） | 残留 `[公式]` 占位 | `\rho` | `\Omega` | `\text` | `\frac` |
|---|---:|---:|---:|---:|---:|---:|---:|
| chaoyang | 147 | 54 | **137**（26 字段）| 0 | 0 | 0 | 31 |
| daxing | 123 | 22 | **106**（25 字段）| 0 | 0 | 0 | 21 |
| fangshan | 213 | 57 | **195**（30 字段）| 0 | 0 | 0 | 32 |
| pinggu | 89 | 32 | **84**（19 字段）| 0 | 0 | 0 | 14 |
| changping | - | 0 | 90 | 0 | 0 | 0 | 0 |
| shijingshan | - | 0 | 106 | 0 | 0 | 0 | 0 |
| shunyi | - | 0 | 30 | 0 | 0 | 0 | 0 |
| xicheng (PDF) | - | 19 | 0 | 2 | 2 | 1 | 0 |

样本：
- chaoyang Q11 stem：「两烧杯液体 [公式]、[公式]，其质量 [公式]；电加热器 [公式]…」（A/B/m/P 全成 [公式]）
- fangshan Q7 stem：「电阻阻值 [公式]。开关 S 闭合后，[公式]、[公式] 两端电压 [公式]、[公式]…」（R1/R2/U1/U2 全成 [公式]）
- daxing Q9 / pinggu Q15 同模式

**根因怀疑**：counter-based replacement 中 d2t 输出 OLE 数 vs cache 数 mismatch（参见 skill R4 教训），二模一批样本再次触发；**且 7/8 区零 `\Omega`/`\rho`/`\text{...}` 中文下标完全丢失** → 即使留下的 `$..$` 块也多是简单 `\frac{}{}` 无电学/光学专业符号，等于 LLM 视角下题干语义不完整。

**影响面**：4 个"良好区" stem+sol 共 522 处 [公式]，等于这些题对 LLM/学生展示都不可用。

---

## 4. xicheng（PDF 路线）三处独立 P0/P1

- **P0 题数 27 ≠ 26**：Q24/Q25/Q26/Q27 全 type=实验探究 或 计算题，**完全没有「科普阅读」节**。Q25 stem 写「请阅读《全球最大的纯电动智能集装箱海船》并回答25题」其实是科普阅读，但 type 标 计算题。需重新分段。
- **P0 footer 污染**：Q18/Q19/Q23/Q24/Q27 含「关注北京高考在线官方微信:京考一点通」「www.gaokzx.com」泄漏到 stem/sol。
- **P1 answer 与 solution 混淆**：Q25 `answer="(3)由于电流的热效应造成…"`（完整解释挤进 answer）；Q26 `answer="(3)图甲为加热档，因此 W=PT=…"`（解题过程当答案）；Q27 同样把 `Η=W_有用/W_总=…` 当 answer。
- **P1 上下标退化**：Q26 sol "(220V)² × T=3.3×10⁵J"（用 `²` `⁵` 而非 LaTeX，混合编码）。

---

## 5. 4 区良好区（chaoyang/daxing/fangshan/pinggu）spot check

- 多选 Q13/14/15 ans 均填且为 [A-D]{1,4}：chaoyang AC/BC/AC、daxing ACD/BD/AB、fangshan AD/ABD/BD、pinggu AD/CD/AB（已和 chaoyang 源 docx「【答案】AC/BC/AC」核对一致）。
- Q24 科普阅读 stem 完整、有 passages 文本（changping/fangshan/pinggu 含独立 passages 列表）。
- Q25/Q26 计算题 stem + sol 非空，但 stem 充斥 [公式] 占位（见 §3）。
- 实验题 16-23 figure 引用 100% 落地（chaoyang 22/49、fangshan 27/27、pinggu 22/26、daxing 16/28；无 missing）。

良好区**唯一阻碍**就是 §3 的 `[公式]` 占位率太高，否则结构、答案、图片、解析都可用。

---

## 6. 修复优先级建议

| 优先级 | 任务 | 影响区 |
|---|---|---|
| **P0** | 修 OLE→LaTeX counter mismatch（再扫一遍 d2t hub regex / cache prefix），剩余 [公式] 至 0 | chaoyang/daxing/fangshan/pinggu |
| **P0** | parser 接两段式（试卷 + 答案）docx，对应文件命名规则 `【试卷】*` + `【答案】*` 或单 docx 含「答案」无「详解」 | changping/shijingshan/shunyi |
| **P0** | xicheng 科普阅读分段错位 + 题数 27→26 | xicheng |
| **P0** | xicheng PDF footer 过滤 `京考一点通` `gaokzx.com` | xicheng |
| **P1** | duration_minutes 补 70 | changping/shijingshan/shunyi |
| **P1** | xicheng answer 与 solution 解耦（answer 只留 (1)(2)(3) 数值/选项） | xicheng |
| **P2** | xicheng 上下标 `²/⁵` 统一回 LaTeX `^{2}/^{5}` | xicheng |

---

OVERALL：**WARN**。8/8 题数=26（除 xicheng=27 P0）、8/8 分值=70 通过；但 3 区走错管线全空 + 5 区 OLE→LaTeX 大面积 [公式] 残留，LLM 可用度 ≈ 40%，必须 R2 复跑 parser/转换链路。
