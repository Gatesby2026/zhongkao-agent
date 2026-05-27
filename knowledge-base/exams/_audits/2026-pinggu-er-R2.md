# 2026 北京平谷区 二模 chinese — R2 复审报告

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-pinggu-er.yaml`
- patches: `knowledge-base/exams/_patches/chinese/2026-pinggu-er.yaml`
- 源 PDF: `knowledge-original/gaokzx-downloads/2026-ermu-chinese/pinggu_chinese.pdf`（共 13 页正文 + 答案，14 页含尾页广告）
- 复审基线：R1 已修 Q12 吞 Q13 / Q24 吞 Q25 / Q21 分值
- 复审范围：27 题 / 7 篇 passage / 字段污染 / 类型分类 / passage 挂载

---

## 卷面元数据 vs 源 PDF

| 项 | 源 PDF（注意事项 1） | yaml | 状态 |
| --- | --- | --- | --- |
| 题数 | 共 27 题 | 27 | ✓ |
| 满分 | 100 分 | 100.0 | ✓ |
| 时长 | 150 分钟 | 150 | ✓（注意北京二模平谷确为 150min，与西城/海淀/朝阳 120min 不同） |
| 学科 | 语文 | chinese | ✓ |
| 区 | 平谷 | 平谷区 | ✓ |

各大题分值核对（源 PDF 大题标头 + 单题加总）：

| 大题 | 标头分值 | 题号 | 单题加总 | 一致？ |
| --- | --- | --- | --- | --- |
| 一、基础·运用 | 14 分 | 1-7 | 2+2+2+2+2+1+3 = 14 | ✓ |
| 二、古诗文阅读 | 16 分 | 8-15 | (1+1+2)+(3+2)+(2+2+3) = 16 | ✓ |
| 三、名著阅读 | 5 分 | 16 | 5 | ✓ |
| 四、现代文阅读 | 25 分 | 17-26 | (2+2+3)+(2+3+3+3)+(2+2+3) = 25 | ✓ |
| 五、作文 | 40 分 | 27 | 40 | ✓ |
| 合计 | 100 分 | 27 题 | 100 | ✓ |

⚠️ **structure 字符串字面错** — yaml 顶部 `structure` 写「5默写(10.0分)」与「8现代文阅读(21.0分)」均与官方题型计数不符（默写实为 Q8/9/10 共 4 分；现代文段落 10 题但内部 type 混判为「主观填空 / 现代文阅读 / 单选」三种）。仅显示字段、不影响下游消费，**P2** 暂不强修。

---

## R1 修复回归验证

| R1 修复点 | 期望结果 | yaml 实际 | 结论 |
| --- | --- | --- | --- |
| Q12 吞 Q13 → 拆 | Q12 简答（陋室铭）+ Q13 单选 (B) | Q12 stem **被改成「室主人生活描写」（陋室铭风格）** + options 仍残留 A/B/C/D；Q13 新建 ✓ B | **❌ 双失：(a) Q12 stem 错指 — 源 PDF 中 Q12 是登幽州台歌「画线诗句作者情感分析」；(b) Q12 options 未清空（patch 用 `options: null` 未生效）** |
| Q24 吞 Q25 → 拆 | Q24 简答（第①段作用）+ Q25 单选 (B) | Q24 stem ✓「分析第①段的作用」；Q24 options 仍残留 A/B/C/D（patch options:null 未清）；Q25 新建 ✓ B 但 **没有 options** | **❌ 同类污染：Q24 options 未清空 + Q25 单选竟无 options（patch 漏写）** |
| Q21 score 2→3 | 3 | 3 | ✓ |

**根因**：patch loader 的 `options: null` 未生效（疑 `_apply_patches` 跳过 None / 空 dict 字段，未真正赋空）。已影响 R1 两处分拆，**P0 必须 R2 修**。

---

## passage 结构核对（narrative 7 题 vs 源 PDF）

### 源 PDF 第四大题（现代文阅读 25 分）真实结构

PDF 第 4 页底 / 第 5 页：
> 四、现代文阅读（共 25 分）
> **（一）阅读材料，完成下面 17-19 题。（共 7 分）** ← 非连续性 3 篇材料 = `non_continuous`
> **（二）阅读《清溪的灯》，完成下面 20-23 题。（共 11 分）** ← 散文叙事 4 题 = `narrative`
> **（三）阅读《全民阅读，点亮心灵的灯塔》，完成 24-26 题。（共 7 分）** ← 议论文 3 题 = `argumentative` ✗ **当前 yaml 完全缺这篇 passage**

### 当前 yaml 的状态

| passage_id | yaml 标 q_range | 应为 | 状态 |
| --- | --- | --- | --- |
| narrative | [20, 26] | [20, 23] | ❌ **跨写到 Q26，吞掉了第三篇议论文** |
| 缺失 | — | Q24-26 应单独建 `argumentative_全民阅读` | ❌ **整篇缺失** |

### Q23 stem 重大污染（P0）

Q23 stem 字段当前内容：
> 「结合全文内容，分析13段"灯亮着，就能照亮人心"的深刻意蕴。(3分)**阅读《全民阅读，点亮心灵的灯塔》，完成24-26题。(共7分)全民阅读，点亮心灵的灯塔()，王祎婧①在人类文明的漫漫征途中，书籍宛如熠熠生辉的灯塔…（数千字议论文全文）…(节选自《文明网》，有删改)**」

**Q23 stem 误吞了整篇议论文正文 +「13段」OCR 漏字（应为「⑬段」）**。下游做相似题 / 学情分析时这道题的 stem 长度 ≈10× 正常题，会污染向量检索 & 错配 KP。

---

## 逐题问题清单

| Q | 严重 | 维度 | 诊断 | 建议 patch |
| --- | --- | --- | --- | --- |
| Q1 | P2 | options 拼音 | `A: 澎湃(péngbai)` 漏掉 `à` 上的声调（源 PDF 是 péngbài） | `1.options.A: "澎湃(péngbài)"` |
| Q1 | P2 | options 拼音 | `D: 累累(leilei)` 漏 `ě` 上声 → `lěi lěi` | `1.options.D: "累累(lěi lěi)"` |
| Q2 | P1 | options 折行 | `A: 络绎不绝B.因地制宜C.身临其境` 把 A/B/C 黏在一起 | 拆为 A/B/C/D 四独立选项 |
| Q2 | P1 | solution 污染 | solution 字段不止「D」，还粘贴了 Q3-Q7 全部答案 (16 行)。下游用 solution 做相似题讲解会爆字。 | `2.solution: "D"` |
| Q3 | — | — | OK，passage_id 正确 | — |
| Q4 | — | — | OK | — |
| Q5 | P1 | options 折行 | `A: ④①②③⑤ B.⑤①②③④ C.④②①③⑤` 全黏在 A 上 | 拆 4 选项 |
| Q5 | P2 | knowledge_points | `词语连贯` 应为 `句子衔接`/`语段排序` | `5.knowledge_points: [语段排序]` |
| Q7 | P1 | solution 尾噪 | 残留「，语句通顺。超过50字扣1分。)」（属评分细则非答案） | trim 到「…我的成长。」 |
| Q9 | P1 | solution 尾噪 | 「沉鳞竞跃」后尾巴「\n\nw.g」OCR 水印残留 | `9.solution: "沉鳞竞跃"` |
| Q10 | P0 | stem | OCR 漏抽题干前半 — 实际「请你从学过的古诗文中，写出体现作者对学习的理解或追求的句子：「__①__，__②__」(本试卷中出现的句子除外)(2分)」当前 stem 只剩「写出体现作者对学习的理解或追求的句子:」之后直接跳到引号 | 补全 stem 并 `\n` 加入 ①② 横线占位 |
| Q10 | P1 | solution 噪 | solution 前后含「www\n\n」「\n\n()，」非答案 | trim 到「学而不思则罔，思而不学则殆」 |
| Q11 | P0 | stem | 当前 stem「诗人登高远眺，①的心情，并与"②"形成对比，衬托出人的___③__」**漏「俯仰古今。诗中的"独"体现了诗人」一整句**（passage body 里反而抓到了），导致 ① 前文承接断 | 修 stem 补「俯仰古今。诗中的"独"体现了诗人」 |
| Q12 | P0 | stem 错 | R1 patch 写「'室主人'生活描写」 — 但 **Q12 实际是登幽州台歌「请结合画线诗句的内容，简要分析作者的情感。(2分)」**（PDF 第 2 页底，紧跟 Q11 后）。R1 把 Q12 错填成了陋室铭风格的题（疑似 R1 把 Q12 / Q13 都当陋室铭 → 错） | `12.stem: "请结合画线诗句的内容，简要分析作者的情感。(2分)"` + `12.passage_id: classical_2` 保持，但 classical_2 body 也要补陋室铭原文（见下） |
| Q12 | P0 | options 未清 | patch `options: null` 无效，yaml 仍含 A/B/C/D（Q13 选项残留） | parser 修 None 处理 或 用 `options: {}` |
| Q12 | P0 | solution 错 | solution 是 Q12 真题答案（登幽州台诗赏析）✓ — 但 R1 stem 写错使 stem/solution 不匹配 | 只需修 stem 即对齐 |
| Q12 | P1 | type | 当前 `主观填空` 应为 `简答`/`古诗赏析` | `12.type: "古诗赏析"` |
| Q13 | — | — | R1 新建 ✓ B 正确 | — |
| Q14 | — | — | ✓ | — |
| Q15 | P2 | knowledge_points | 当前 `[默写, 古诗文内容理解]` — 实际是「比较阅读 + 文言文理解」混合，建议加 `比较阅读` | `15.knowledge_points: [文言文比较阅读, 主旨理解]` |
| Q18 | P2 | stem 尾噪 | 末尾「京高考任线」OCR 水印 | trim |
| Q20 | P1 | stem 缺空 | 「①;后来，，实现了自我成长」缺 ② 标记，应「①___；后来，②___，实现了自我成长」 | 修补 |
| Q21 | — | — | R1 ✓ score 修 3，stem 完整 | — |
| Q21 | P1 | solution 缺 ② | solution 列了 ① 但 ② 行被吞，应「②是文学作品的精神力量在现实中…」 | 补 ② 前缀 |
| Q23 | **P0** | stem 污染 | stem **吞掉整篇议论文 1200+ 字正文**（Q24-26 的 passage） | stem 截到「…的深刻意蕴。(3分)」止；议论文文本剥出建新 passage |
| Q23 | P1 | stem 数字 | 「13段」应「⑬段」（OCR 漏抓圈数字） | `23.stem: "结合全文内容，分析⑬段「灯亮着，就能照亮人心」的深刻意蕴。(3分)"` |
| Q23 | P1 | solution 尾噪 | 「成为照亮别人的"灯光"」漏句号；「一一」应「——」 | 微调 |
| Q24 | **P0** | options 错挂 | Q24 是简答题（分析第①段作用 2 分），但 yaml 给了 4 选项（实为 Q25 选项 + A 选项自吞重复"A.全民阅读重在参与，贵在坚持。"） | `24.options: {}` + 删除 |
| Q24 | P0 | passage_id 错 | `narrative` → 应为新建 `argumentative_全民阅读` | 修 passage_id |
| Q25 | **P0** | options 缺 | R1 新建后没补 options（patch 漏） | 补 A/B/C/D，answer:B ✓ |
| Q25 | P1 | qc_status | `needs_review` qc_note「选择题缺 options」— R2 后应改 draft | 补 options 后 `qc_status: draft` |
| Q25 | P0 | passage_id 错 | `narrative` → `argumentative_全民阅读` | 修 |
| Q26 | P0 | passage_id 错 | `narrative` → `argumentative_全民阅读` | 修 |
| Q26 | P2 | knowledge_points | `段落梳理` → 建议 `论证思路分析`/`段落顺序` 更贴 | 微调 |
| Q27 | P1 | stem 尾噪 | 「a\nq\n),\n参考答案」OCR 残留答案页 header | trim 到「…师生姓名。」止 |
| Q27 | P1 | solution | solution 是 stem 整段重复 + 末尾「参考答案」噪音；作文题 solution 应留空（patch 已正确设 `solution: ""`，但 yaml 显示未应用 — 同 None 处理 bug） | 同 parser None bug |

---

## passage 结构问题（汇总）

### classical_2 body 严重缺漏

当前 `classical_2.body`：
> 「京高登幽州台歌陈子昂前不见古人，念天地之悠悠，独怆然而涕下。\n\n俯仰古今。诗中的"独"体现了诗人」

**问题**：
1. 「京高」OCR 抓的水印（北京高考在线）
2. 缺第二句「后不见来者」
3. **完全缺失陋室铭全文**（Q13/Q14/Q15 引用文言文）— 学情分析时学生看不到原文
4. 缺《送东阳马生序》《论语·原宪》两则链接材料（Q15 用）
5. 「俯仰古今。诗中的…」是 Q11 题干，不应在 body

**建议重建 classical_2**：
- 拆为 `classical_poem_登幽州台歌`（q_range [11,12]）+ `classical_prose_陋室铭`（q_range [13,15]）
- 前者 body 含全诗 4 句
- 后者 body 含《陋室铭》全文 + 两则链接材料

### 缺失 passage：argumentative_全民阅读

需 R2 新建：
```yaml
- id: argumentative_全民阅读点亮心灵的灯塔
  type: argumentative
  name: 全民阅读，点亮心灵的灯塔
  q_range: [24, 26]
  body: |
    （王祎婧 ①…⑦ 全文，源 PDF 第 6-7 页）
```

### narrative q_range 修

`narrative.q_range: [20, 26]` → `[20, 23]`

### base_资料一/二/三/四 噪音

- base_资料一 body 尾「mkz」OCR 水印
- base_资料三 body 中「ww.」水印 + 题 3 题干被混入 body
- non_continuous body 多处「在线」「ww.g」水印 + Q18 题干插入

均 P1，可批量 trim。

---

## OVERALL: NEEDS_FIX

**严重等级**：R1 修复留下 **5 处 P0 必修**：

1. **Q12 stem 完全错** — R1 patch 把登幽州台歌 Q12 错填成陋室铭风格
2. **Q23 stem 吞议论文全文 1200+ 字**
3. **Q24/Q25/Q26 passage_id 全错挂 narrative**（应为新建 argumentative）
4. **缺失 argumentative passage**（《全民阅读，点亮心灵的灯塔》整篇没建）
5. **patch `options: null` / `solution: ""` 不生效** — 跨题 parser bug：Q12 / Q24 / Q27 三处字段未被清空

**次要等级 P1**：13 处（Q2 options 折行 + Q5 options 折行 + Q10 stem 缺前半 + Q11 stem 缺前句 + Q20 stem 缺 ② + Q21 solution 缺 ② + Q23 圈数字 + Q24 + 4 处 solution 尾噪 + classical_2 body 重建）

**结构等级 P2**：6 处（拼音声调 / KP 微调 / structure 字符串字面）

**建议**：
- (a) **patches 文件扩写 5 处 P0**（Q12 stem 改为登幽州台歌；Q23 stem 截尾；Q24/25/26 改 passage_id；新增 passages 块建 argumentative；classical_2 拆 2 passage）
- (b) **parser 修 patch `None` 处理**（chinese_image_paper.py `_apply_patches` 跳 None 应判定为「清空」）
- (c) **平谷二模本次"0 水印 0 干净"假象** — base body 仍有 OCR 水印「mkz / ww.g / 在线 / 京高」，下次 inspect 加 stale watermark pattern 扫描

教训：**R1 单卷盲修易把题号挪错** — 平谷 Q12 是古诗赏析非文言（与同卷 Q13/14/15 三道陋室铭题易混），R1 看 Q12「文言文实词」类 KP 误推 stem，需结合 PDF 大题 anchor「（二）阅读《登幽州台歌》」严格校位。
