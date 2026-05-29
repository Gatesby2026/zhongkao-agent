# 2026 北京朝阳区数学二模 yaml 审核报告 R1

源 yaml：`knowledge-base/exams/mock/math/beijing/2026-chaoyang-er.yaml`
源 PDF：`knowledge-original/gaokzx-downloads/2026-ermu-math/chaoyang_math.pdf`（无文本层，纯扫描图）
源 PNG：`knowledge-original/beijing-mock-2026/ermo/chaoyang/math/images/page-NN.png`（14 页，前 8 页题面，后 6 页答案解析）
中间 OCR：`knowledge-base/exams/_staging/math/2026-chaoyang-er/`（tencent-cache page-01..14.json，structured-cloud/final.json，qwen-vl-answers.json）

数据源：image OCR 路线 `math_image_paper.py`（首份 math image fork from physics）。yaml header 标 `OCR: Qwen-VL-OCR  Enrich: qwen-max`，QC `draft=20  needs_review=8`。

## 卷面元数据

| 项目 | yaml | PDF 真值 | 一致性 |
|---|---|---|---|
| year | 2026 | 2026 | OK |
| exam_type | 二模 | "九年级综合练习（二）" 2026.5 | OK |
| subject | math | math | OK |
| district | `''` (空) | 北京市朝阳区 | **P0** — 与 changping 一模一样的 P0：district 字段为空，所有按区索引/路由/枚举的下游都失效 |
| full_score | 100 | 100 | OK |
| duration_minutes | 120 | 120 | OK |
| total_questions | 28 | 28 | OK |
| structure | 8单选(16) + 8填空(16) + 12解答(68) | 一致 | OK |
| passages | `[]` | n/a | OK（数学不用 passage） |

分值约束（PDF 第 3 页 footer "三、解答题（共68分，第17-19题，每题5分，第20题6分，第21题5分，第22题6分，第23题5分，第24题6分，第25题5分，第26题6分，第27-28题，每题7分"）：

yaml 实际：Q17=5, Q18=5, Q19=5, Q20=6, Q21=5, Q22=5, Q23=6, Q24=6, Q25=5, Q26=6, Q27=7, Q28=7 → 5×3 + 6×1 + 5×1 + 5×1 + 6×1 + 6×1 + 5×1 + 6×1 + 7×2 = **68** OK

**注意**：朝阳的 footer 与昌平略不同（22 题 5 分而非 6 分；23 题 6 分而非 5 分）— yaml 的逐题分值跟朝阳 footer 一致，可信。单选 8×2=16，填空 8×2=16，总分 100 OK。

## 逐题问题清单

### P0（必修，影响事实正确性）

**P0-1 district 字段为空（同 changping 一模一样的跨区共性 parser bug）**
- 第 8 行 `district: ''`。下游全部失效（routing / enum / 跨区聚合）。

**P0-2 八道单选题全部 0 个选项（A/B/C/D 文本全丢，options 字段不存在）**
- Q1-Q8 的 yaml block 全部没有 `options:` 字段；qc_note 已自动标注 "选择题缺少 options（既无文本也无图片选项）"，说明 parser 检测到了但没能恢复。
- 从源 PDF 实测每题选项均为纯文本（A/B/C/D 各占一行），并非图选项：
  - Q1: (A)圆柱 (B)长方体 (C)圆锥 (D)球
  - Q2: (A)-3 (B)-1 (C)1 (D)4
  - Q3: (A)36 (B)72 (C)108 (D)144
  - Q4: (A)35° (B)55° (C)65° (D)125°
  - Q5: (A)1/6 (B)1/3 (C)1/2 (D)5/6
  - Q6: (A)4×10⁻¹⁰ (B)4×10⁻¹¹ (C)4×10⁻¹² (D)40×10⁻¹⁰ 秒（仅 Q6/Q7/Q8 把选项嵌进了 stem 字符串里，但 options 字段仍然空）
  - Q7: (A)40° (B)50° (C)80° (D)100°
  - Q8: (A)①② (B)②③ (C)①③④ (D)①②③④（typical multi-correct mark）
- 影响：所有 8 道选择题学生作答无法显示选项，相似题召回拿不到 distractor 语义，且即便有 `answer: B` 也对不上 distractor 文本。**这是 image OCR 路线 math 的最重 P0**——physics fork 过来的题级切割对数学选项的 (A)…(B) 行检测显然没接住。
- Q1/Q4/Q7/Q8 还有 figure，options 与 figure 是两个独立缺失维度，Q1/Q4/Q7/Q8 即使补回 figure 也必须独立修 options。

**P0-3 Q2 缺数轴图**
- 源 PDF page 1：Q2 紧跟一个数轴线段图（标 a 与 -a 范围）；yaml Q2 无 `figure:` 字段。
- 题干提到"实数 a在数轴上的对应点的位置如图所示"，缺图等于题目不可解。

**P0-4 Q15 缺图**
- 源 PDF page 3 明确标"第15题图"（矩形 ABCD 含 E、F 点）；yaml Q15 无 `figure:` 字段。
- Q14 同页有"第14题图"和"第15题图"两张并排，OCR 只挂上了 Q14。题级切割漏了第二张。

**P0-5 Q9 答案大小写破坏：`X≠5` 应为 `x≠5`**
- 行 189。`qwen-vl-answers.json` 的 raw 值也是大写 `X`，应是 qwen-vl-max 把数学变量小写 x 误归一化成大写。后续 Q10 `M(A+2)(A-2)` 应为 `m(a+2)(a-2)`，Q18 答案 `X≥3` 应为 `x≥3`，Q19 `M²` 应为 `m²`——`m, x, a` 都被强制大写化。
- 数学符号大小写在初中代数里就是身份标识（M 通常代表点，m 代表系数），强制改大写会破坏 stem 与 answer 的指代一致性。

**P0-6 Q13 答案被截成单字符 `(`**
- 行 272 `answer: (`。预期答案是 `>`（最高气温方差大于最低气温方差，因为最高气温 22-32 的离散程度比最低气温 14-19 大）。
- qwen-vl 看到答案区里写的"(填'>''='或'<')"括号导致把括号当答案抓了。

**P0-7 Q20-Q28 共 9 道大题 `answer` 字段全空**
- 行 437, 467, 494, 558, 587, 653, 679, 715, 758（Q20/21/22/23/24/25/26/27/28）全是 `answer: ''`。
- `solution` 字段有内容（虽然格式很烂），但学情分析/批改流水线一般以 `answer` 字段为最终结论 ground truth。这 9 道题占 68 分中的 63 分，等于解答题区的 ground truth answer 索引几乎全失。
- 应从 solution 末尾抽出最终结论填回 answer，例如：
  - Q20 (2) `CD=2√5`
  - Q21 (1) `y=-x+4`；(2) `0<m≤1`
  - Q22 一台 A 型节能灯年用电 150 度
  - Q23 (1) m=22.6 中位数 …等等
  - Q26 (2) m₀ 最小值 = 1+√2
  - Q28 (3) r=√5, A(1/2, -2)
- 与 Q1-Q19 答案被 qwen-vl 单独刷过、Q20-28 没刷直接来自 OCR solution 拆分形成的两段式断层——`qwen-vl-answers.json` 只有 1-19 共 19 个 key 印证了这一点。

**P0-8 Q23 频数分布表丢失（仅 stem 列散乱数据，没还原表结构）**
- 源 PDF page 5 a 段是 5 列频数分布表：`x<18.5 | 18.5≤x<23.2 | 23.2≤x<27.9 | 27.9≤x<32.6 | x≥32.6`，人数 `6 | 20 | 9 | 4 | 1`。
- yaml stem 只有 b/c 数据段的散文文本"18.5≤x<23.2 23.2≤x<27.9____27.9≤x<32.6____"——表格被压成一行字符串，5 个人数 `6 20 9 4 1` 完全消失。后面 (1) 问"表中 m 的值"也因此失锚（这里 m 是 d 表女员工中位数列，但 a 表的频数也都丢了）。
- 影响：Q23 第(1)问 yaml 把 m=20.5 写在 solution，但 a 表 m 实际是女员工 BMI 数据中位数=20.5（按 25 个数排序的第 13 个），与原题题意一致；不过整张 a 表丢失使得 (3) ② 学生再去验证"BMI 较大前 20%"会无据可查。

**P0-9 Q25 表格 fi/Hz 一行 `257` 被噪声渗入**
- 行 647：`| fi/Hz | 900 | 600 | 450 | 360 | 300 | 257 | 225 | 200 | 180 |` —— 表头"fi"应为 "f₁"（带下标 1），且整个表头行表头多了 `L/cm` 列空白没对齐（行 643 共 10 列分隔符却 11 个值）。
- 第 70 列 257 是源数据真值，但 257 行右边其实在 PDF 里被用红色高亮（PDF page 6 可见），意味着是 problem statement 中标出来的"已知点"（让学生写 70 cm 时 f₂ 多少）；yaml 没保留这个高亮语义。
- 同表 `f2/Hz` 也应是 `f₂/Hz` 下标，被 OCR 压成普通字符。

### P1（重要，影响阅读体验/可用性）

**P1-1 stem/solution 内残留 `www.gaokzx.com` / `kzx.com` / `北京高考在线` 等水印噪声**
- Q14 stem 末尾 `....www.gaokzx.com`（行 287）
- Q20 solution 含 `kzx.com`、`B H C` 等水印/标签碎字（行 438-442）
- Q22 solution 末尾整段"关注北京高考在线官方微信"footer 没被 strip（行 496）
- Q23 stem 含 `____ookzx.com`、`com`（行 512, 530）
- Q25, Q26, Q28 solution 末尾各有 1-3 段"北京高考在线平台简介"等长 footer（Q28 行 763-768 整整 6 行公司介绍渗入题目！）
- physics image OCR 路线已有的 footer NOISE pattern 没有完全继承到 math，需要加 NOISE_PATTERNS：`北京高考在线|gaokzx\.com|京考一点通|bjgkzx|数学试卷答案及评分参考第[一二三四五六]页|kzx\.com|北京高考在线平台简介`。

**P1-2 LaTeX 公式损坏 / 配对失败**
- Q17 行 375：`stem: 计算：$\sqrt{8} +（\frac{1}{4} ）^{-1}-2026°-2cos45°$` — 全角括号 `（）` 应转半角 `()`，`2026°` 应为 `2026⁰`（零次幂）；当前 LaTeX 渲染会出错。
- Q17 行 377 solution：`$\longdots$$\longdots$4分` — `\longdots` 不是合法 LaTeX 命令（应为 `\ldots` 或省略号 `\cdots`）；两次 `$$` 配对会让 4分 错位。
- Q18 行 393：`$\left\{\begin{matrix}2x+3≥x+6,\\2x+1\\3>x-1.\end{matrix}\right.$` — 第二个不等式应是 `\frac{2x+1}{3}>x-1`，被错切成 `2x+1` 与 `3>x-1` 两行（与 changping 的 Q18 同模式 parser bug，应是 math_image_paper.py 对分式跨行 OCR 还没修）。
- Q19 stem 行 411：`3m2-2m-7=0` 上标 `²` 丢失（应为 `3m²-2m-7=0` 或 `3m^2-2m-7=0`）。同行 `(m+1)2` 同。Q23 d 表 `s_{1}^{2}` 出现，说明上下标 OCR 还是 case-by-case。
- Q26 stem 行 678：`使得当m>m_{0}$时,都有t随m的增大而增大,求$m_{0}$的最小值.` — `$` 三个奇数个，前后配对错位。
- Q26 solution 多处 `p2-p` / `p2-2p` / `y1-y2` 上下标全丢。
- Q28 stem 行 736：`$P_{0}$` 中 P' 撇号已成 `'`（行 740 `P''`），多了一层引号转义。

**P1-3 solution 多处行内噪声字符 / 题号粘连**
- Q20 solution 行 441：`∴EF=BE·sin∠ABC=5x/5=4.` 中 `5x/5` 应该是 `5×4/5`（sin ABC = 4/5 显式给的）。OCR 把 4 读成 x。
- Q24 solution 行 588：`∴∠EDF=2∠EDG. 1分 :AC切O于点C，` 冒号粘连。
- Q24 行 593：`∴EG=DE·sin 13 ∴EF=2EG=10√13` 里 sin 后面少了角度参数，且 `√13/13` 分式被压。
- Q25 solution 行 654：` f/Hz www.gaokzx.com 1200 1100 1000 900 800 700 …` — 把图像 y 轴刻度文字当 solution 抓了，1200…0 共 13 个数字根本不是答题内容。
- Q27 solution 行 716：`(1)∠DAE=2∠ 2分` 答案截断 — 应为 `∠DAE = 2∠BAC`，关键变量丢失。
- Q27 solution 行 718：`∴△AEC△APC.` 缺 `≌`。
- Q28 solution 行 759 (1) `(1,2),(3,0);` — 应为 `(1, 2), (3, 0)`，前一个是 `(1,0)` 的关联图形 `(1, 1+2×1)=(1,2)` OK，但第二个 `(-1,2)` 的关联图形 yaml 给了 `(3, 0)`——可能正确，但缺 (2) 问的 m,n 表达式整段全空。
- Q28 solution 行 761-762 (2) 只有"...4分"占位，没有 `n = ...` 含 m 的表达式。

**P1-4 Q16 stem 内嵌"三、解答题(共68分...)"footer，串入下一大题区**
- 行 337-339：`(2)若九年级代表队要获得最多积分，则选手B应完成环节\n\n    三、解答题(共68分，第17-19题，每题5分，第20题6分，第21题5分，第22题6分，第23\n\n    题5分，第24题6分，第25题5分，第26题6分，第27-28题，每题7分)`
- 大题区 banner 不应在题干里，应被 section 切割吃掉。这与 P1-1 NOISE 没 strip 同根因，但更严重——把分值约束 banner 当题目正文。

**P1-5 Q7/Q8 答案为多选但 type 仍写 单选**
- Q8 是典型多选（结论①②③④的子集），yaml `type: 单选 answer: D`。从原题"上述结论中,所有正确结论的序号为"+ 选项 D (①②③④) 看，本身确实是单选问题（选项是组合），所以 type 标 单选 没错；但 `answer: D` 在没 options 文本支持下完全无法验证语义。

### P2（建议，影响一致性/可维护性）

**P2-1 qc_status 标注偏松**
- Q9-Q19 全标 `qc_status: draft` 而非 `needs_review`，但 Q13 `answer: (`、Q17/18 LaTeX 破损、Q19 上标全丢，明显需要复审。建议 inspect 阶段加 `len(answer) < 2 and type=填空 → needs_review`、`stem 含未配对 $ → needs_review` 两条规则。
- Q20-Q28 答案全空都标 `draft`，应改 `needs_review`。

**P2-2 knowledge_points 颗粒过粗**
- Q22（年用电量分式方程应用题）只有 `方程的应用` 一项 KP，过于宽泛；应至少加 `分式方程` `应用题建模`。
- Q26（抛物线 + 直线 + 最大值参数 m₀）只有 `二次函数的图像与性质 一次函数的图像与性质`，缺 `参数讨论 / 函数最值`（高难能力题的核心 KP 缺失）。
- Q28（图形关联 + 最小覆盖圆）只有 `坐标变换 图形变换 圆的性质`，缺 `数形结合 / 动点轨迹` —— 这是 image OCR 路线 enrich 步对数学语义识别还不够细的共性。

**P2-3 figure 命名前缀冗长 + 缺 q02/q15**
- 现 9 张 figure 命名为 `2026-chaoyang-er/figures/q01.png` 等，前缀重复区名（其它学科如 chinese docx 路线只写 `figures/q01.png`，由 base path 推断），可统一规范。
- 缺 q02.png（数轴）和 q15.png（矩形 ABCDEF），需 page-01.png 和 page-03.png 二次裁剪。

**P2-4 Q1 figure 内是 3 张三视图（正/侧/俯）排成 1 行，但选项 4 张图（圆柱/长方体/圆锥/球）才是真正的图选项**
- 现在 yaml 把"几何体"的图（即"主视图"已知图）放到 figure 字段；但实际从源页 Q1 上文看，A/B/C/D 是文字选项（圆柱/长方体/圆锥/球），不是图选项。所以现 figure 的语义是"题面给定的三视图"——正确。但 qc_note `选择题缺少 options` 说明 parser 把 figure 当 image option 误判过。需要在 image-option vs stem-figure 之间做更精细的区分。

## image OCR 路线 generality 验证（fork from physics）

**框架适合度判断：勉强可用，但 4 处 physics → math 不适配点必须补**：

1. **选项文本未抓**：物理选项往往在题号下独占 4 行 `A. ...\nB. ...\nC. ...\nD. ...`，且选项常含中文长描述；math 朝阳 8 题选项却分两个亚型：
   - 短文本型（数字/分数/角度，Q2/Q3/Q4/Q5）：`(A)-3 (B)-1 (C)1 (D)4` 4 项可能挤在 1-2 行；
   - 中文型（Q1）：`(A)圆柱 (B)长方体 …` 1 行 4 项。
   - physics fork 来的 option splitter 对"(A)"前缀 + 横向排版 4 项格式没处理 → 全部漏抓。
   - 改进方向：math 必须加 `(A)…(B)…(C)…(D)` 行内拆分（`re.split(r'\([A-D]\)\s*', line)`）+ 数字/分数/角度短答案的兜底。

2. **LaTeX 公式密度高**：math 的 stem/answer/solution LaTeX 出现频次远超物理（物理 LaTeX 主要在公式行，数学几乎每题都有 `\frac \sqrt ^ _`）。当前 yaml 已显示分式跨行（Q18）、上下标丢失（Q19/Q23/Q26/Q28）、`\longdots` 等多类 LaTeX 损坏，必须复用 docx 路线 physics 的 OMML→LaTeX 思路，或对 image OCR 加 LaTeX sanity check（`stem.count('$') % 2 != 0` flag）。**image OCR 路线对 math LaTeX 重保真度天然劣势**。

3. **题级切割漏 figure**：Q2 数轴 / Q15 矩形 ABCDEF 同页有"第N题图"标注却没被切出，说明 figure region 检测对 math"小图嵌正文中"模式不灵敏（物理 figure 通常独立大块，math 经常是小段 inline 图）。

4. **答案 ground-truth 断层**：Q1-Q19 走 qwen-vl-answers.json 单独刷一遍补 answer，Q20-Q28 没刷直接 OCR solution → answer 字段一律空。需要把 qwen-vl 调用扩到全 28 题，或在 inspect/enrich 阶段从 solution 末位抽 "答案/最终结果"。

5. **noise footer 没继承**：physics docx 路线已有 `北京高考在线|gaokzx\.com|京考一点通|bjgkzx` 等噪声 pattern；image OCR 路线 math 没继承，导致 Q28 solution 末尾整整 6 行公司介绍渗入。属于一次性 patch 即可修。

**结论**：image OCR 路线对数学是"能跑通但 fidelity 差一档"，options/LaTeX/figure 三项核心问题都得专项补丁。如有 docx 源（如 zxxk），强烈建议优先走 docx 路线（参考 chinese v4 / physics v2 的成功经验：零 OCR / 零 API / 数据干净度上一个量级）。当前 image 路线产物只能算 R0，必须 R1→R2→R3 迭代收敛 + 至少 5-8 处 parser fix 才能合并到 mock 主线。

## OVERALL: **NEEDS_FIX**

- P0 共 9 项，其中 P0-2（8 题选择题全无 options）和 P0-7（9 道大题 answer 全空）单项已足以判 NEEDS_FIX；
- P0-1（district 空）与 changping 二模复现，确认是 math image 路线跨区共性 parser bug，**修一次解决全市**；
- P1 共 5 项主要是 OCR 噪声 / LaTeX 损坏 / footer 串入，需 parser + 后处理双路修；
- P2 共 4 项是 schema / enrich 语义 polish。
- **不建议直接进入下一阶段（学情分析 / 答题卡批改）**，必须先把 P0 全部修掉，重新 R2 审。
- 优先级建议：先修 P0-1（district）、P0-2（options 抓取）、P0-7（answer 从 solution 抽取）三个 parser 层 P0，跑 R2 后再处理 P0-3/4（figure 补抓）、P0-5/6/8/9（点级数据 patch）。
