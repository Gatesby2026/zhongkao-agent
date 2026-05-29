# 2026 北京海淀区中文二模 yaml 审核报告（R1）

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-haidian-er.yaml`
- 源 PDF（含完整文本层，第 1–12 页为试题，第 10–12 页为答案/评分标准，第 13 页为广告页）: `knowledge-original/gaokzx-downloads/2026-ermu-chinese/haidian_chinese.pdf`
- 源 PNG: `knowledge-original/beijing-mock-2026/ermo/haidian/chinese/images/page-NN.png` (13 页)
- OCR 中间产物: `knowledge-base/exams/_staging/chinese/2026-haidian-er/tencent-cache/general/page-NN.txt`
- 路线：**image OCR 路线（chinese_image_paper.py）**，OCR 误差可见。
- 审核范围：现状 yaml 为 26 题 / 100 分；源卷封面"共五道大题，**27 道小题**，满分 100 分，考试时间 150 分钟"。

---

## 卷面元数据 vs 源 PDF

| 项目 | yaml | 源 PDF | 一致 |
|---|---|---|---|
| year | 2026 | 2026 | OK |
| district | 海淀区 | 海淀区 | OK |
| exam_type | 二模 | 二模（封面"2026 北京海淀初三二模"） | OK |
| subject | chinese | 语文 | OK |
| full_score | 100.0 | 100 | OK |
| duration_minutes | 150 | 150 | OK |
| **total_questions** | **26** | **27** | **P0：少 1 题** |
| 大题分数分配 | （未存）实算 11+19+5+25+40 = 100 | 一(13)+二(17)+三(5)+四(25)+五(40) = 100 | **P0：一/二大题段分错位** |
| passages | base_intro/classical_2/classical_3/non_continuous/narrative/argument | 同 | OK |

**关键 P0**：

1. yaml 缺整道 Q4（2 分）。源 PDF 顺序为 Q1(书写,1) → Q2(单选,2) → Q3(单选,2) → **Q4(单选,2)** → Q5(主观,2) → Q6(单选,2) → Q7(单选,2) = 一大题共 13 分。
2. yaml Q1 的 stem/options 实际是源 Q4 的内容（"你检查了资料中成语的使用情况…别具一格/鳞次栉比/浑然一体/悠然自得"），但 score=1.0、solution="略" 又对应源 Q1（"在封面上用正楷字书写标题…(1 分)"），是 Q1+Q4 的混合体。一段被吞掉。
3. yaml Q10（默写）score=5.0，实际源卷为 **1 分**（"如'____'一句就妙用了叠词。(本试卷中出现的句子除外)(1 分)"）。该题被错赋为整段(一)默写 5 分小计。
4. yaml Q8/Q9 score=1，实际源卷各 **2 分**（"(2 分)" 在 PDF 行末明示）。
5. 一大题段总分：yaml 实算 1+2+2+2+2+2 = **11**（少 Q4 的 2 分） vs 源 13；二大题(一)默写：yaml 实算 1+1+5 = 7 vs 源 5；其余对得上。**总分意外算对**只是因为 Q10 多算的 4 分恰好补了 Q4 缺的 2 分 + 默写小计漂移。

> 来源参考（PDF text 行号）：line 23 = Q1 真 stem；line 62 = "1.你检查了资料中成语…(2 分)" 这是源卷自身排版把 Q4 又重新从 1 编号（页 2 顶部，独立段落"东美园城市艺术空间·【甲】"之后）；line 71 = "5.文段中…(2 分)" 表示 Q5；line 361 答案 "4.B（2 分）"。

---

## 逐题问题清单

| Q | 严重 | 维度 | 诊断 | patch 建议 |
|---|---|---|---|---|
| **Q1** | **P0** | type/stem/options | yaml.Q1 是 "书写题 + Q4 的 stem/options" 混合体。真 Q1 是"在封面上用正楷字书写标题：'艺术赋能城市微更新'调查报告。(1 分)"，无选项，answer/solution=略。 | 重写：`1: { type: 书写, score: 1, stem: "在封面上用正楷字书写标题：\"艺术赋能城市微更新\"调查报告。(1分)", options: null, answer: "", solution: "略" }` |
| **Q1.solution** | P1 | solution | 当前 solution="略" 对应真 Q1，但被错绑到 Q4 的 stem 上。配合上一条修。 | 同上 |
| **新增 Q4** | **P0** | 整题缺失 | 整道 Q4（单选 2 分）缺失。stem："你检查了资料中成语的使用情况。下列成语使用不恰当的一项是(2 分)"；options：A.别具一格 B.鳞次栉比 C.浑然一体 D.悠然自得；answer/solution=B；KP=成语运用；passage_id=base_intro。 | 在 questions 列表 Q3 后插入完整 Q4 节点；并把现 yaml Q1 的 stem/options/KP=成语运用/passage_id=base_intro 等内容迁到此 |
| Q2 | OK | — | stem/options/answer=C 一致；solution=C ✓；KP=字形（"端详/蓄势待发/相应成趣/焕发"四个加点词典型字形题）合理。 | — |
| Q3 | P1 | options 缺 D | 源卷 Q3 只有 A/B/C 三个选项，yaml 也只列 A/B/C。**这是合法的（源卷确实就 3 个）**。但 base_intro passage.body 末尾把这个 3 选项题与后续 Q4 的 4 个成语并入了 passage 文本，建议清理 passage.body 避免后续 LLM 误读。 | passage `base_intro.body` 末段从 "根据词典的解释，下面对文段中'城市肌理'..." 起到 "第②句第②句" 全删，仅留正文 |
| Q5 | P1 | stem | stem 尾部夹带了 `\n\n[画线句修改后参考: ...]`，是 parser 注入的提示文字，应只保留题干 "文段中的画线句存在问题，请你修改。(2 分)"。solution 内容正确。 | `5: { stem: "文段中的画线句存在问题，请你修改。(2分)" }` |
| Q6 | **P0** | options | options.C 残缺为 `"[甲]"`，丢了 `②` 和 `[乙]④`。源卷为 `C.【甲】②  【乙】④`。 | `6: { options: { C: "[甲]②  [乙]④" } }` |
| Q7 | **P0** | options | options.B 与 C 同为"第②句"，源 PDF 实为 `A.第①句  B.第②句  C.第③句  D.第④句`。OCR 把 C 误读为"第②句"。answer=C 没问题（"第③句"是修辞句），但 C 选项文字错。 | `7: { options: { C: "第③句" } }` |
| Q8 | **P0** | score | score=1，源卷"(2 分)"。 | `8: { score: 2 }` |
| Q8 | P1 | stem | stem 把"安得广厦千万间，大庇天下寒士俱欢颜！风雨不动安如山。"开头两空 OCR 成 `①②`，后接`!风雨不动安如山。`——正常默写填空表达，但 stem 中应保留两个 ①② 空位（合理）；可读性 OK。 | — |
| Q9 | **P0** | score | score=1，源卷"(2 分)"。 | `9: { score: 2 }` |
| Q9 | P1 | stem | stem 末尾 `(2分)()，` 残留 OCR 噪声 `()，`，应删。 | `9: { stem: "晓雾将歇，①;夕日欲颓，②。(陶弘景《答谢中书书》)(2分)" }` |
| Q9 | P1 | solution | solution=`猿鸟乱鸣沉鳞竞跃` 两空粘连，应拆为两行/加空格：`猿鸟乱鸣  沉鳞竞跃`。 | `9: { solution: "①猿鸟乱鸣  ②沉鳞竞跃" }` |
| **Q10** | **P0** | score | score=5.0，源卷 "(1 分)"。当前误把整段(一)默写的小计 5 分压到本题，且解答区放了 3 行示例答案（蒹葭苍苍 / 晴川历历汉阳树 / 嘤嘤成韵）。Q10 是开放题"妙用叠词的一句，本试卷出现的句子除外"，只需 1 个示例。 | `10: { score: 1, solution: "答案示例：蒹葭苍苍 / 晴川历历汉阳树 / 嘤嘤成韵（任答一句即可）" }` |
| Q10 | P1 | solution | 末尾 `\n\n\n(` 一行残碎符号。 | 见上 |
| Q11 | P1 | solution | "①星河流转千帆舞动" 在源卷答案为同样表述，OK；但与原词"星河欲转千帆舞"相比缺逻辑校对（参考答案就是这样写的，**保留**，无错）。 | — |
| Q12 | OK | — | solution 内容 3 行分行 OK，与答案一致。 | — |
| Q13 | OK | — | answer=D（韦编三绝 = 断），solution=D ✓。 | — |
| Q14 | OK | — | answer=A ✓。题干"下列对'终身不复鼓琴'的理解，不正确的一项"，A=世间再无足够优秀琴曲——错读，源答案 A。 | — |
| Q15 | P1 | solution | 当前 `solution: "①答案示例：高山流水\n②生我者父母，知我者鲍子也。\n③\n信士"`，③ 与 "信士" 被换行拆开，应合并为 `③信士`。 | `15: { solution: "①答案示例：高山流水  ②生我者父母，知我者鲍子也。  ③信士" }` |
| Q16 | OK | — | 名著阅读 5 分，answer 空合理（开放题），solution 给保尔示例。passage_id 无（OK，独立大题）。 | — |
| Q17 | OK | — | answer=C ✓ |（C 选项是因果倒置） | — |
| Q18 | P2 | KP | knowledge_points 含 "记叙文阅读"——本题属"非连续性文本"信息筛选，应仅 "信息提取/段落梳理"。 | `18: { knowledge_points: ["信息提取/段落梳理"] }` |
| Q19 | OK | — | 答案 ①发展历程 ②表演形式 ③创新发展 ✓。 | — |
| Q20 | P2 | KP | KP 含 "记叙文阅读"——通用项，可保留；但 "信息提取/段落梳理" 已覆盖，可去重。 | 非阻塞 |
| Q21 | P1 | stem | stem 用"第17段"指代源卷第⑰段，应保留 ⑰（圆圈数字）。当前已 OK，仅说明。 | — |
| Q22 | P1 | stem | stem 写"第⑤段和第⑧段"，源卷为"第⑤段和第**⑱**段"（OCR 把 ⑱ 误读为 ⑧）。answer/solution 内已正确写 "第⑤段…第⑱段"，故 stem 应同步修。 | `22: { stem: "\"渺小\"在第⑤段和第⑱段两次出现，分别表达了作者怎样的情感。(2分)" }` |
| Q23 | OK | — | 4 分主观题，solution 三层精神品质（英勇/淳朴/团结）齐全。 | — |
| Q24 | OK | — | 2 分主观题，solution 准确（承上启下连接句）。 | — |
| **Q25** | **P0** | stem | stem 末尾粘 `ww.` 水印残字（gaokzx 水印）。 | `25: { stem: "阅读全文，下列分析不恰当的一项是(2分)" }` |
| Q26 | P1 | solution | solution 末尾粘 `\n\nww.` 水印残字。 | `26: { solution: "画线处使用了举例论证，举出鉴赏齐白石画作时，通过山泉和蝌蚪的画面能联想到山村生活的例子，证明了联想可以帮助鉴赏者建立起艺术形象与生活的关系，从而更深切地感受艺术形象的观点。" }` |
| **Q27** | **P0** | solution | solution 把"参考答案/题目/k.com/信号:）/）"作为正文写入，造成 LLM 误把题干当答案。**作文 answer/solution 应留空**（严禁标记为 bug — 这是题目设计，但 solution 实际写了垃圾，需清空）。 | `27: { solution: "" }` |
| Q27 | P1 | stem | stem 尾 `()，` 残留 OCR 噪声。 | `27: { stem: "从下面两个题目中任选一题，按要求写一篇作文。\n题目一：开窗见风景\n题目二：就这样携手同行\n要求：请将作文题目写在答题卡上，文体不限，诗歌除外。作文内容积极向上，字数在600-800之间，不出现真实的学校名称、师生姓名等。" }` |

---

## passage 体清单

| passage | q_range | 主要问题 |
|---|---|---|
| base_intro | 1-7 | **P0**：body 把 Q3/Q4/Q5/Q6/Q7 的题干、选项、提示语整段吞入 passage 正文。"根据词典的解释，下面对文段中'城市肌理'的理解不正确的一项是(2 分)()" 出现在 body 中（line 29）；"①造园生艺境②赏美无边界③观画有奇趣④修树创微景[乙]④[乙]③[乙]③" 出现（line 35，把 Q6 选项和答案分布全部吞下）；"第②句第②句" 出现（line 39，是 Q7 选项残）。**建议重写 body 为三段：东美园、北太平庄、第三部分调查结论**（按源 PDF 行 47-67、67-77）。 |
| classical_2 | 11-12 | OK，《渔家傲》全词正确。 |
| classical_3 | 13-15 | OK，《伯牙鼓琴》正文齐全。但**缺材料二《管晏列传》/材料三《后汉书·范式张劭》两则文言文**——Q15 需要这两则材料，应作为 classical_3 的 sub_materials 或单独 passage。 |
| non_continuous | 17-19 | P1：body 把材料一/二/三 + 表 1 整段塞入。表 1 OCR 极乱（"主要道具 木偶本体、木杖 木偶本体、提线 木偶本体" 等行错位），建议拆 figure 或重排表格；尾部 `gaww.` 水印残字。 |
| narrative | 20-23 | P1：开头 "①今天，我想起…" 后第 ②③ 段同为 "跑冰排哪!"，但 yaml 缺第②段（直接到 ③），少一行；OCR 缺 ⑲ 段 "江上的人只顾奋死搏斗…" 中"一面狂嘶呐喊，一面向下游奔跑"（yaml 写"江上的人只顾奋死搏斗，无声无息。江岸上的人们却一窝蜂随着漂流的冰排，面向下游奔跑"，少"一面狂嘶呐喊"）。⑥ 段尾"真是惊北京高kzx人"是水印"北京高kzx"插入正文，源为"真是惊人"。⑲ 段编号在 yaml 丢失。**P0：水印"北京高kzx"插入 ⑧ 段正文，污染语义**。 |
| argument | 24-26 | P1：尾段 "联想()，" 残留 `()，` 噪声；④⑤ 段被合并为 "④⑤"（yaml line 149），源 PDF ④ 段是独立短句"我们如何运用形象思维进行鉴赏呢？"（推断，需核），⑤ 段"各种艺术形式…"。当前 ④⑤ 合并可能丢失 ④ 段独立内容（影响 Q24 "建立②③段与⑤⑥段联系"的语境）。 |

---

## 水印/噪声残字清单（跨题模式）

| 位置 | 内容 | 严重 |
|---|---|---|
| narrative.body line 98 | `真是惊北京高kzx人` (源："真是惊人") | **P0**（语义破坏） |
| narrative.body line 128 | `()，④松花江` | P1 |
| narrative.body line 132 | `ww⑥我连忙` | P1 |
| Q9.stem 尾 | `(2分)()，` | P1 |
| Q25.stem 尾 | `(2分)ww.` | **P0** |
| Q26.solution 尾 | `\n\nww.` | P1 |
| Q27.stem 尾 | `()，` | P1 |
| Q27.solution 内 | `k.com / 信号:)，/ 参考答案` | **P0**（答案串污染） |
| base_intro.body 多处 | `om漫步海淀同庆街` / `m秉持"开放美术馆"` / `g木偶艺人` / 末尾"第②句第②句" | P1 |
| non_continuous.body 尾 | `gaww.` | P1 |
| argument.body 尾 | `ww.` | P1 |

---

## 跨题模式

1. **gaokzx 水印**（"北京高考在线" → OCR 残留为 `ww` / `gaww` / `kzx` / `k.com` / `aokzx`）穿插于 13 处文本，已识别 11 个集中点。R1 patches 应统一过 `re.sub(r'(ww\.|gaww?\.?|北京高?kzx|aokzx|k\.com|京考一点通)', '', ...)`。
2. **题号丢失**：Q4 整题被合并入 Q1（书写题 + 单选题"端详/蓄势待发"被并位），疑为 OCR 看到 page 2 顶端再次出现"1." 编号（源 PDF 自己的排版 bug，第 2 页"东美园"段后真的把成语题重新编号为"1."），parser 把 Q4 当作"重号 Q1" 跳过。**建议 parser 在 base_intro section 内对题号连续性强制递增**：当上一题为 Q3 且新题号为 "1" 但其前已确认非 dictation/section 切换时，自动 +3 校正。
3. **score 错配**：默写题 Q8/Q9 各 2 分被 OCR 漏 → 录为 1；Q10 整段小计 5 分被错赋单题。建议 parser 用"(N 分)" 行末标记**严格按题号绑定**，且整段标"共 N 分" 时拒绝下放到单题。
4. **作文题 solution 污染**：Q27 应 answer/solution 强制留空（"严禁标记为 bug"是指空属合理，但当前 solution 写了垃圾，需主动清空）。
5. **passage.body 吞下题干/选项**：base_intro 把 Q3/Q6/Q7 的题干选项吞入，narrative ⑲ 段缺失短语，argument ④段合并 ⑤段。Image OCR 路线对"题干插入正文段"的边界识别弱，建议增加二次切分。
6. **stem 中"第⑱段" → "第⑧段"** 圆圈大数字 OCR 误读：Q22 中 ⑱ 被误读为 ⑧（pages 7-8 出现 ⑪–㉗ 都是 OCR 难点）。建议对圆圈数字增加 ⑪–㉗ 字典强制纠错。
7. **KP 跨学科**：未发现物理/数学 KP 污染。但"现代文阅读" 类型在 Q18/Q20 被附加"记叙文阅读"——非连续性文本不该挂记叙文 KP，需 KP 表细分 "记叙文/议论文/非连续/说明文"。

---

## 数字汇总

- **P0**：8 处（Q1 stem/options 错位、Q4 整题缺失、Q6 options.C 残缺、Q7 options.C 错文、Q8 score、Q9 score、Q10 score、Q25 stem 水印、Q27 solution 污染、narrative "北京高kzx" 插入正文）
- **P1**：14 处（stem/solution 尾巴残字、Q15/Q9 solution 拆行、Q22 stem ⑧→⑱、passage 段缺失等）
- **P2**：3 处（KP 去重）

---

## OVERALL: **NEEDS_FIX**

- 必须修：**Q4 整题缺失** + **Q1 stem/options 错位** + **Q6/Q7 options 错** + **Q10 score 错** + **Q8/Q9 score 错** + **narrative 正文被水印破坏语义** + **Q25 stem 水印** + **Q27 solution 垃圾**。
- 共 27 题（patch 后），段分应为 一(13) / 二(17) / 三(5) / 四(25) / 五(40) = 100。当前 yaml 总分 100 是"巧合"——Q4 缺 2 分 + Q10 多算 4 分 + Q8Q9 各少 1 分（合 -2）正好抵消（-2+4-2=0），但**结构性错误严重**，无法用于学情诊断（Q4 学生答了但 yaml 没该题；Q10 显示 5 分但实际 1 分会导致小分严重错配）。

建议 patch 文件路径：`knowledge-base/exams/_patches/chinese/2026-haidian-er.yaml`，**R1 patch 至少需覆盖上表 8 处 P0 + 4 处 P1（水印清理）**。

修复后建议追加一轮 R2 大模型审核，重点核：narrative ⑲ 段全文 / classical_3 sub_materials 完整性 / argument ④⑤ 段拆分。
