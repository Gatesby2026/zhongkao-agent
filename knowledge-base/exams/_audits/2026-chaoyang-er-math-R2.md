# 2026 北京朝阳区数学二模 yaml 审核报告 R2

源 yaml：`knowledge-base/exams/mock/math/beijing/2026-chaoyang-er.yaml`
patches：`knowledge-base/exams/_patches/math/2026-chaoyang-er.yaml`
源 PDF：`knowledge-original/gaokzx-downloads/2026-ermu-math/chaoyang_math.pdf`
答案页源 OCR：`_staging/math/2026-chaoyang-er/tencent-cache/general/page-09..14.txt`

R1 9 项 P0 修复后复审。

## R1 修复验证

| R1 P0 | R2 状态 | 证据 |
|---|---|---|
| P0-1 district 空 | **CLEAN** | 行 8 `district: 朝阳区` |
| P0-2 Q1-8 options 全丢 | PARTIAL | 现 8 题统一填 `'[图]'` 占位 + `has_image_options: true`；非真值（实际选项是纯文本 (A)圆柱/(B)长方体 等，不是图选项），但至少不再 schema 缺字段。语义层仍待人工 patch |
| P0-3 Q2 数轴图 | **未修** | yaml Q2 仍无 `figure:` 字段 |
| P0-4 Q15 矩形图 | **未修** | yaml Q15 仍无 `figure:` 字段 |
| P0-5 Q9 大写 X→x | CLEAN | 行 238 `answer: x≠5`；Q10 `m(a+2)(a-2)` 也已修 |
| P0-6 Q13 `(` → `>` | CLEAN | 行 321 `answer: '>'` |
| P0-7 Q20-28 answer 空 | **未修** | 行 487/517/544/608/641/706/732/769/812 共 9 题 `answer: ''` 全空 |
| P0-8 Q23 频数表丢失 | PARTIAL | patches solution 已写入 5 列频数 `6/20/9/4/1` + m=20.5 + p>q + ①23/②140,120 与源页一致 |
| P0-9 Q25 f1/f2 下标 | 未修 | 表头仍 `fi/Hz f2/Hz`，下标 1 丢失 |

## 卷面元数据 — CLEAN

| 项 | R2 |
|---|---|
| year/district/exam_type/subject | 2026 / 朝阳区 / 二模 / math |
| full_score / total_questions / duration | **100 / 28 / 120** OK |
| structure | 8单选(16) + 8填空(16) + 12解答(68) OK |
| 逐题分值合计 | 2×16 + 5×3+6+5+6+5+6+5+6+7×2 = **100** OK |
| Q22/Q23 分值 | Q22=6, Q23=5（与朝阳 footer 一致）OK |

## R2 重点回答

**1. R1 修复仍清洁？** Q1-8 ans 比对源答案页 (page-09)「A C C B C A B D」**100% 一致**。

**2. Q9-16 填空 ans 准确性**：逐题比对源答案页：
- Q9 x≠5 ✓  Q10 m(a+2)(a-2) ✓  Q11 2 ✓  Q12 0 ✓
- Q13 > ✓  Q14 15 ✓  Q15 3√3 ✓  Q16 80;2 ✓
- **8/8 全对**。Q14 数学含义：15°（缺单位但符号匹配）。Q16 多空题用 `;` 分隔合理。

**3. Q20-28 解答题 ans/sol 完整性**：
- **answer 字段 9/9 全空**（P0-7 未修，最重 P0 复现）— `solution` 末位的「150 度 / 2√5 / 1+√2 / √5,(1/2,-2)」结论没回填到 `answer`。
- solution 字段保真度参差：
  - Q20-26 sol 主体在，但夹杂 `kzx.com` / `B H C` / 噪声字
  - Q27 (1) `∠DAE=2∠` **截断**（缺 `BAC`）—— 源 PDF 答案页扫描本身就缺，非 parser 错
  - Q28 (2) `...4分` **完全空**——源 PDF 该处亦未印出 `n = m² − 2m − 1` 类表达式（gaokzx 卷答案页缺刻）
  - Q23 patches 已补 (1)(2)(3) 完整结论，质量最好

**4. LaTeX 公式损坏率**（R1 P1-2 未单独修复）：
- Q17 stem 全角 `（）` + `2026°` 上标错位 + sol `\longdots` 非法命令
- Q18 stem 分式 `\frac{2x+1}{3}` 被切成两行
- Q19 stem `3m2-2m-7=0` 上标 `²` 丢失，answer 同
- Q26 stem `$m_{0}$` 多次出现致单行 `$` 计数奇数
- Q28 stem `P''` 撇号转义异常
- **目测约 8-10 题含 LaTeX 损坏**（28 题中 ~30%），重灾区 Q17/18/19/26/28
- math LaTeX 密度远超 physics，image OCR 路线天然劣势依旧

**5. 28 题 / 100 分**：CLEAN ✓

## R2 新发现

**P0 残留**：
- **P0-7 9 道大题 answer 全空**（R1 第一优先未修）
- **P0-3/P0-4** Q2、Q15 figure 仍缺
- **新 P0-N1** Q1-8 options 真值丢失：现统一 `'[图]'` + `has_image_options: true` 是 schema 兜底而非事实。源 PDF 8 题选项全部是**纯文本**（如 Q5 `(A)1/6 (B)1/3 (C)1/2 (D)5/6`）。下游学情/相似题召回拿不到 distractor 语义。

**P1**：
- Q14/20/22/23/25/26/28 仍残留 `www.gaokzx.com` `北京高考在线` `kzx.com` `京考一点通` footer 噪声（NOISE_PATTERNS 未实施）
- Q16 stem 仍内嵌「三、解答题(共68分...)」banner 串入下一大题区
- Q25 表头 `fi/Hz` `f2/Hz` 下标 1/2 丢失
- Q23 stem 仍是散乱单行（虽 sol 补齐），a 段 5 列频数表未还原到 stem

**P2**：
- 9 道解答题 `qc_status: draft`（应 `needs_review`）
- LaTeX `$` 配对未做 sanity check

## OVERALL: **NEEDS_FIX**

R1 9 P0 仅修 4 项 CLEAN + 2 项 PARTIAL + **3 项未修**（P0-3/P0-4/P0-7 三个最影响事实正确性）。Q1-16 答案侧已 100% 与源对齐（含 patches），是本轮主要进步；但 Q20-28 解答题 answer 全空 + Q2/Q15 figure 缺失 + Q1-8 options 用 `[图]` 假兜底，三处 P0 未触及。

**R3 优先级建议**：
1. 从 sol 末位抽 Q20-28 answer（必要时人工 patch，9 条覆盖最高分段 63/100 分）
2. patches 加 Q1-8 真实选项文本（OCR 已抓到 page-01..02，覆盖 16 分基础题）
3. Q2/Q15 figure 补抓（page-01/page-03 二次裁剪）
4. NOISE_PATTERNS 后处理（一次性 strip 所有 gaokzx footer，5-7 题受益）
5. LaTeX 损坏 8-10 题最好走 docx 源（如无 zxxk docx，则单独 LLM 重写 Q17/18/19/26/28 的 stem/sol）

R2 不建议进入学情分析阶段；先做 R3 把 P0-3/4/7 + Q1-8 options 真值四项闭环再审。
