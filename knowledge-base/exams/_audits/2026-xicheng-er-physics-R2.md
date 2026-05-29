# 2026 北京西城区 物理二模 yaml 审核报告 R2

- yaml: `knowledge-base/exams/mock/physics/beijing/2026-xicheng-er.yaml`
- patches: `knowledge-base/exams/_patches/physics/2026-xicheng-er.yaml`
- 前序: `_audits/2026-xicheng-er-physics-R1.md`（22+ P0 已识别）
- 源 PDF: `knowledge-original/gaokzx-downloads/2026-ermu-physics/xicheng_physics.pdf` (11p)
- 源图: `knowledge-original/beijing-mock-2026/ermo/xicheng/physics/images/page-0{1..11}.png`

---

## R1 修复 patch 复核（核对源 PDF 答案页 p.9）

### ✅ 已修干净（CLEAN）

| 项 | R1 patch | 真值 | 结论 |
|---|---|---|---|
| Q1–12 单选 answer | `B D C A B D B C B A C D` | 同 | ✅ 12/12 全对 |
| Q13–15 多选 answer | `BD BC ABD` | 同 | ✅ 3/3 全对 |
| Q17 score | 3 | 3 | ✅ |
| Q18 score | 5 | 5 | ✅ |
| Q19 score | 3 | 3 | ✅ |
| Q20 score | 5 | 5 | ✅ |
| Q21 score | 2 | 2 | ✅ |
| Q22 score | 2 | 2 | ✅ |
| Q24 score | 3 + type=实验探究 | 3 + 实验探究 | ✅（type 已纠） |
| Q27 score | 4 | 4 | ✅ |
| Q16 整题 create | score=2 + solution | 真值 2 分 + 同 | ⚠ score 对，但 stem 是占位符（见下 P0） |
| Q4 has_image_options + 占位 | `[图] × 4` | 4 张实物图 | ⚠ 占位字符串，仍缺真实子图（P1 未消） |
| 合计分 | 70 | 70 | ✅ 总分对齐 |

### ⚠ R1 patch 自身遗留缺口

**P0-1 Q16 stem 仍是占位符 `"Q16 实验探究题 (待人工补全 stem，OCR i6 误识致缺题)"`**
- 真值（源 PDF p.4 已清晰可读）：
  > 如图所示，用毛皮摩擦过的橡胶棒接触验电器的金属球时，验电器的金属箔张开是由于______相互排斥；再用丝绸摩擦过的玻璃棒接触该验电器的金属球，验电器的金属箔张开的角度会先______。
- 真值 answer：`同种电荷；减小`（patch 的 solution 写「同种电荷相互排斥；减小」第 1 空多塞了「相互排斥」，因为题目里"相互排斥"已经印在题面上，空格只填"同种电荷"四字 — 否则学生作答比对会判错）
- 此外 type 应是 `实验探究` 或 `填空`，patch 写的 `实验探究` 与 section 一致 ✅；module 标 `experiments` 不准，建议 `electricity`（摩擦起电、电荷间相互作用）。
- **必修**：把占位 stem 替换为真值；solution 第 1 空改为「同种电荷」；module 改 electricity；同步 knowledge_points 加 `摩擦起电` `电荷间相互作用`。

**P0-2 Q15 stem 末尾 Q16 残段未切除**
yaml Q15 stem 仍含：
> `i6.如图所示，用毛皮摩擦过的橡胶棒接触验电器的金属球时验电器的金属箔张开是由于_相互排斥;再用丝绸摩擦过的玻璃棒接触该验电器的金属球，验电器的金属箔张开的角度会先_。`

R1 patch 只补了 Q16，没在 patches 里覆盖 Q15.stem 切除残段。**必修**：patches 加 `15.stem`，恢复为「甲、乙两密度计的质量相同甲密度计的横截面积大于乙密度计的横截面积，下列说法中正确的是」结尾。

---

## R1 未覆盖、R2 新发现 P0/P1

### P0-3 Q10 科学计数法负号仍丢
R1 未在 patches 修。yaml 现状：
- stem「底面积为$4×10^{2}m^{2}$」→ 真值 `4×10⁻²m²`（源图明确）
- 选项 D「水对桶底的压强为$4×10^{2}Pa$」→ 真值 `4×10³Pa`（深度 0.4m × ρg ≈ 4000 Pa，物理上必为 10³）
- 不修则 Q10 整道题量纲错乱，正确答案 A 也无法用 OCR 文本推出来。

### P0-4 Q12 stem `\Omega_2` 错绑下标未修
yaml「R的阻值为 $40 \Omega_2$ 热敏电阻」→ 真值「R 的阻值为 40Ω，R₂ 热敏电阻」（源图 p.3 清楚分两句）。`\Omega_2` 是把后句 R₂ 下标错绑到 Ω。下游 LaTeX 渲染 `\Omega_2` 仍可显示但语义错。同 Q12 选项 D 也缺 R₂。

### P0-5 Q19 stem (2) LaTeX 未闭合 `$\text{文…`
yaml 现状仍是 `$\text{文螺线管周围摆放…该实验探究的问题是_。`，`$` 未配对、`\text{` 的 `}` 缺失，首字「在」被 OCR 成「文」。KaTeX/MathJax 渲染 Q19 (2) 整段会 fallback 报错。**必修**：strip `$\text{`、首字改「在」、清掉 `''` 反引号污染。

### P0-6 Q20 solution (4)③ 公式分母 R₀ 丢失
yaml `Uo(U1-Uo)` → 真值 `P = U₀(U₁−U₀)/R₀`（源 PDF p.9 评分参考）。无分母即无量纲（W = V²/Ω，缺 Ω 不可解）。

### P1-7 Q4 image_options 仍是 `[图]` 占位
R1 patch 标了 `has_image_options: true`，但 A/B/C/D 仍为字符串 `'[图]'`。源 PDF p.1 是「脚印 / 图钉尖 / 拱桥 / 刀片轮胎」四张实物图，需重裁子图入 `figures/q04_optA-D.png`，或至少把文字描述写入 options（A. 沙滩脚印 / B. 图钉尖端朝下 / C. 城墙拱桥 / D. 切菜刀刃）。

### P1-8 Q26 `P_催温` → `P_保温`、Q23 表头 `Unh/V → Uah/V`
R1 已在 §跨题模式 §1 列出但未进 patches。Q26 solution 公式里 4 处出现「P催温」全是 OCR 误识。Q23 表 2 列头 `Unh/V` 应为 `Uah/V`（电压表接 a-h 两端）。

### P1-9 5–6 处页眉页脚噪声未剔
Q18/Q19/Q23/Q24/Q25/Q27 solution 含 `关注北京高考在线…京考一点通…`、`www.gaokzx.com`、`北京市西城区九年级模拟测试试卷`、Q27 末尾整段 1100+ 字的「北京高考在线平台简介」广告。**必修**：parser 加 STALE_PATTERNS 或 patches 覆盖；当前 Q27 末尾广告会污染学生答案比对。

### P1-10 Q23 top-level options 应嵌回 stem
yaml Q23 同时存在 stem 内 `A. 灯泡 L1 短路 / …` 与 top-level `options.A-D`，下游会把 Q23 当成主选择题；实际它是 (1) 小问的内嵌选项。

### P1-11 Q27 answer 字段大写 Latin 化
`Η=W_有用/W_总=GH/FS=...75%` — Greek 大写 Η 应为小写 η；GH/FS/MGH/MG/NF/KG 全部应小写；缺空格。

---

## 27 题 / 70 分核对

- 题数：yaml `total_questions: 27` ✅；逐题 id 1..27 连续无跳号 ✅。
- 分值：12×2(单)+3×2(多)+Q16-24 各分(2+3+5+3+5+2+2+3+3=28)+Q25(4)+Q26(4)+Q27(4) = 24+6+28+4+4+4 = **70** ✅。

但 yaml header `structure: "12单选(24分) + 3多选(6分) + 10实验探究(32分) + 2计算题(8分)"` 与真值不符：
- 实验探究 = Q16-24 共 **9 题 28 分**（非 10 题 32 分）；
- 计算题/科普阅读：Q25 科普(4) + Q26-27 计算(8) = **3 题 12 分**（非 2 题 8 分）。
- **建议改**：`12单选(24) + 3多选(6) + 9实验探究(28) + 1科普阅读(4) + 2计算题(8)`，并把 Q25 type 从 `计算题` 改为 `科普阅读`。

---

## LaTeX / 单位 / 科学计数法整体抽查

| 位置 | 现状 | 真值 | 状态 |
|---|---|---|---|
| Q3.A `3×10^{8}m/s` | ✅ | ✅ | OK |
| Q10 stem `4×10^{2}m^{2}` | ❌ | `4×10⁻²m²` | **P0** |
| Q10.D `4×10^{2}Pa` | ❌ | `4×10³Pa` | **P0** |
| Q12 stem `\Omega_2` | ❌ | `\Omega`,`R_2` | **P0** |
| Q19 stem `$\text{文…` | ❌ 未闭合 | `在螺线管…` | **P0** |
| Q20 (4)③ `Uo(U1-Uo)` | ❌ 缺分母 | `U_0(U_1-U_0)/R_0` | **P0** |
| Q25 (2) `$2.494 \times 10^{13}$` | ✅ | ✅ | OK（缺单位 J，P2） |
| Q26 (3) `$3.3 \times 10^{5}$J` | ✅ | ✅ | OK |
| `\Omega` Q20.(3) | ✅ | ✅ | OK |

---

## OVERALL: **NEEDS_FIX**

### R2 阻塞项（必修，6 处 P0）

1. **Q16 stem**：替换占位符为真值（毛皮橡胶棒/丝绸玻璃棒/验电器全文）；solution 第 1 空 `同种电荷相互排斥` → `同种电荷`；module → electricity；KP 加 `摩擦起电` `电荷间相互作用`。
2. **Q15 stem**：patches 覆盖去掉末尾 `i6.…的角度会先_。` 整段 Q16 污染。
3. **Q10**：stem 与选项 D 两处 `10^{2}` → 真值 `10^{-2}` 和 `10^{3}`。
4. **Q12**：stem + 选项 D `\Omega_2` 拆为 `\Omega` + 独立 `R_2`。
5. **Q19**：stem (2) `$\text{文螺线管…现象。` 改 `在螺线管…现象。`，剔 `''` 反引号，确保无未闭合 `$` `{`。
6. **Q20**：solution (4)③ 公式补回 R₀ 分母 → `P = U_0(U_1-U_0)/R_0`。

### R2 建议项（P1，5 处）

7. Q4 image_options A-D 补真实子图或文字描述（重裁 `figures/q04_optA-D.png`）。
8. Q26 solution `P_催温` → `P_保温`（4 处）。
9. Q23 表头 `Unh/V` → `Uah/V`；top-level options 嵌回 stem (1)。
10. 6 处页脚噪声 strip（含 Q27 末尾 1100+ 字广告，必剔否则污染向量库）。
11. Q27 answer 字段 `Η` → `η`，公式字母小写化。
12. yaml header `structure` 描述与真值不符，按上节真值改写；Q25 type → `科普阅读`。

### Parser 改造（沿用 R1 §A–G，新增）

- (H) Q15→Q17 跳号触发后，自动从 Q15 stem 末尾切断「(疑似下题题号)+正文」尾巴，防 Q16 缺失同时 Q15 stem 被污染。
- (I) Q10 `10^{N}` 数字与量纲量级不符时（压强 1e2 Pa 不合理）回看源图。

**R1 已修 12 选择 answer + 3 多选 answer 全部对、9 题 score 全部对、Q27 type 对**，分值合 70 ✅，整体框架正确；但 R1 patch 自身的 Q16 占位 + Q15 残段未切，加上 R1 未触碰的 4 处 LaTeX/科学计数法 P0，仍阻塞发布。预计 R3 再 patch 6 处 P0 + 5 处 P1 可达 CLEAN。
