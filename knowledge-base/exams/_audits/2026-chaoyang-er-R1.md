# 2026 北京朝阳区中文二模 yaml 审核报告（R1）

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-chaoyang-er.yaml`
- 已有 patches（R1 已修 Q8/Q19/Q25）: `knowledge-base/exams/_patches/chinese/2026-chaoyang-er.yaml`
- 源 PDF（扫描版，无文本层）: `knowledge-original/gaokzx-downloads/2026-ermu-chinese/chaoyang_chinese.pdf`
- 源 PNG: `knowledge-original/beijing-mock-2026/ermo/chaoyang/chinese/images/page-NN.png`
- OCR 中间产物: `knowledge-base/exams/_staging/chinese/2026-chaoyang-er/tencent-cache/general/page-NN.txt`
- 审核范围：本次为应用 patches 之后的 27 题逐题再审，目标挖 R1 patches 未触及的 P0/P1/P2。

---

## 卷面元数据

| 项目 | yaml | 卷面规范（封面/OCR） | 一致 |
|---|---|---|---|
| 题数 | 27 | 27（封面"共五道大题，27道小题"） | OK |
| 总分（patches 后）| 100 | 100 | OK |
| 时长 | 150 分钟 | 150 分钟 | OK |
| 大题分配 | 14+16+5+25+40 = 100 | 一(14)/二(16)/三(5)/四(25)/五(40) | OK |
| 类型分布 | 8 单选 + 3 主观 + 5 默写 + 1 名著 + 9 现代文 + 1 作文 | 与卷面吻合 | OK |
| year 字段 | `null` | 2026 | **P1：缺失** |
| district 字段 | `''` | 朝阳 | **P1：缺失** |
| exam_type | `真题` | 模拟（二模） | **P1：错值** |

**逐分核算**（patches 后）：Q1-5=10 + Q6-7=4 + Q8-9=2 + Q10=2 + Q11=2 + Q12=3 + Q13-14=4 + Q15=3 + Q16=5 + Q17=2 + Q18=2 + Q19=3 + Q20-23=11 + Q24-26=7 + Q27=40 = **100** ✓

**各段总分核算**：一(Q1-7)=14 ✓；二(Q8-15)=4+5+7=16 ✓；三(Q16)=5 ✓；四(Q17-26)=7+11+7=25 ✓；五(Q27)=40 ✓。

---

## 逐题问题清单

以下表的"建议 patch"列均为可直接追加到 `_patches/chinese/2026-chaoyang-er.yaml` 的 YAML 片段（`questions:` 子键下，已经存在的 Q8/Q19/Q25 不重列）。

### 元数据层

| 字段 | 严重 | 维度 | 诊断 | 建议 patch |
|---|---|---|---|---|
| year | P1 | meta | `year: null`，源卷封面 "2026.5"，应为 2026 | 顶层加 `year: 2026` |
| district | P1 | meta | `district: ''`，源卷为"北京市朝阳区" | 顶层加 `district: 朝阳` |
| exam_type | P1 | meta | `exam_type: 真题`，本文件是"九年级综合练习(二)"——即二模，应为 `模拟` 或 `二模` | 顶层 `exam_type: 模拟` |
| header 注释 | P2 | meta | 文件首行 `# None年北京真题chinese — 自动生成` 是 parser 模板兜底输出（year=None/district 空），与上面 3 处同源 | parser 修 meta 提取后注释自然恢复 |

### 题目层

| Q | 严重 | 维度 | 诊断 | 建议 patch |
|---|---|---|---|---|
| Q1 | P0 | options | options.D 把下一段 passage "胜日寻芳" 完整文本（约 200 字）整段吞入 D 选项，D 选项实应仅 `第④句` | `1: { options: { D: "第④句" } }` |
| Q2 | P1 | solution | solution 字段尾巴粘了一行散漂的 `高` 残字（水印 "高考在线" 漏出）；不影响答案，但污染数据 | `2: { solution: "C" }` |
| Q3 | P0 | options | options.D 把下一段 passage "公益巡河"（约 200 字）整段吞入 D 选项，D 选项实应仅 `更新` | `3: { options: { D: "更新" } }` |
| Q6 | P1 | stem | stem 已 OCR 出题干 "文段中的画线句存在问题，请你修改。(2分)"，但接着把后面 "[画线句修改后参考: ..."（看上去是 parser 自己注入的提示）写到 stem 里。题干本身完整，建议清掉 stem 末尾追加段 | `6: { stem: "文段中的画线句存在问题，请你修改。(2分)" }` |
| Q7 | P1 | stem | stem 末尾粘水印残字 `关注:，` | `7: { stem: "根据语境，你在文段中的横线处补写一个分句。(2分)" }` |
| Q8 | (已修) | score | R1 patches 已 1.0；同时 solution 字段把后面 Q9/Q10 答案误粘成一大坨需清理 | `8: { solution: "江春入旧年" }`（顺带修正 OCR 把"入"误读成"人"） |
| Q9 | P2 | answer | "庭下如积水空明" 没问题；OCR 在 page-09 答案区写"庭下如积水空明"。CLEAN | — |
| Q10 | P1 | stem | stem 把两个空 `①` `②` 紧贴成 `①，②`（OCR 原文为 `①，\n②`），用读时人会以为只有一空标 ①——建议加空格区分 | `10: { stem: "游览名胜古迹，总有与之相关的古诗文名句涌上心头。你印象深刻的两句是\"①___，②___\"。(本试卷中出现的句子除外)(2分)" }` |
| Q12 | P2 | solution | solution 内有 "春壮近" 当为 OCR 误读，源卷为 "春社近"（陆游原诗 "箫鼓追随春社近"） | `12: { solution: "\"箫鼓追随\"与\"衣冠简朴\"、\"春社近\"与\"古风存\"两两相对，音韵和谐;前句写春社时箫鼓喧天的热闹，后句写村民简朴的衣着，突出了乡间淳厚的民风，表达了诗人对乡村生活的热爱。" }` |
| Q13 | P2 | solution | solution = `D\n\n\naokzx.com` 尾巴有水印；非阻塞 | `13: { solution: "D" }` |
| Q14 | P1 | options | options.D 末尾粘 `关注:\n微信\n号:` 三行水印残字，D 选项实应止于 "知音难觅的悲叹。" | `14: { options: { D: "体现了因隐居不为人所理解的孤独，以及对知音难觅的悲叹。" } }` |
| Q15 | P1 | stem | stem 末尾粘 `com` 水印残字 | `15: { stem: "根据《答谢中书书》及下面两则材料，在后面语段中的横线上填写恰当的内容。(3分)" }` |
| Q16 | P1 | passage_id | `passage_id: non_continuous` **错配**——Q16 属于第三大题"名著阅读"，并不依附非连续文本。应为 `null` 或独立 passage | `16: { passage_id: null }` |
| Q16 | P2 | solution | solution 字段后段一坨乱字 `关注在\n成日)\n了微后\nF:\n口.0门KZx\n入代口人...`（水印+广告 OCR），应清空或仅留题面 | `16: { solution: "" }` |
| Q17 | P1 | type | `type: 现代文阅读`、但 stem 是单选（"下列恰当的一项"），4 选项 `[甲][乙][丙]` 缺一个；同时 options 整体缺失（全在 stem 里）→ 建议拆 options | `17: { type: 单选, options: { 甲: "我国各类清洁能源的发电量较之上年均有所增长", 乙: "水电在清洁能源中发电量最高，增长速度遥遥领先", 丙: "太阳能发电、风电、核电发电量均突破1万亿千瓦时" }, answer: "甲" }` |
| Q18 | P1 | options | options.C 末尾粘 `\n线` 水印，options.D 末尾粘 `\n高考线` 水印 | `18: { options: { C: "我国森林面积及蓄积量连续双增长，已是森林覆盖率最高的国家。", D: "\"6.2万场\"\"3300多万人次\"这两个数据说明我国治沙成就巨大。" } }` |
| Q19 | (已修) | stem | R1 patches 已修；CLEAN | — |
| Q20 | P0 | passage_id | `passage_id: non_continuous` **错配**——Q20 属"(二)阅读《故乡》"叙事类文本，应指向 `narrative`（passages 里已定义）。Q20/21/22/23 同问题 | `20: { passage_id: narrative }`, `21: { passage_id: narrative }`, `22: { passage_id: narrative }`, `23: { passage_id: narrative }` |
| Q20 | P1 | solution | solution 尾巴粘 `(共2分。共2`（截断的评分细则），应清掉 | `20: { solution: "①儿子对故乡一无所知\n②儿子与隔壁男孩相识(放鞭炮、论宗亲)" }` |
| Q21 | P2 | solution | solution 末尾粘 `关注:，` 水印 | `21: { solution: "①儿子白天放烟花，不会挑选合适时机\n②儿子不熟悉鞭炮怎么放，不懂燃放技巧" }` |
| Q22 | P1 | solution | solution 中段 "刻画了男孩的\n\n在线\n切;" 中"在线"两字是水印误入，原应为"急切" → "刻画了男孩的急切" | `22: { solution: "答案示例一:\n\"冲\"写出男孩听到鞭炮声后快速跑过来的样子，刻画了男孩的急切;\"观望\"是写男孩站在一边观察，写出他犹犹豫豫、不好意思主动搭话的样子。两个动词表现了隔壁男孩渴望玩伴的心理与质朴害羞的特点。\n答案示例二:\n\"扎\"形象写出两个孩子脑袋紧紧凑在一起的模样，表现出两人瞬间亲近、毫无隔阂的状态;\"琢磨\"细致刻画了二人认真研究怎么放鞭炮的样子。两个动词生动勾勒出孩童天真烂漫、专注玩耍的情态。\n答案示例三:\n\"躺坐\"写出儿子返程时半躺半坐、无精打采的样子，\"遮\"写出他用帽子盖住脸，不愿与\"我\"交流。两个动词表现出儿子离别小伙伴后的失落与不舍，表达了他对故乡、对故乡玩伴的留恋之情。" }` |
| Q23 | P1 | stem | stem 末尾粘 `关注:，高` 水印 | `23: { stem: "文章结尾写道:\"砰一声音之大，飞驰的高铁都抖了一下。\"结合文章内容，说说你从中读出了什么。(4分)" }` |
| Q24 | P1 | stem | stem 末尾粘 `okzx.com` 水印 | `24: { stem: "文章启示我们:因为①___，所以阅读文学作品时，我们要②___。(2分)" }` |
| Q24 | P0 | passage_id | `passage_id: non_continuous` **错配**——Q24/25/26 属"(三)阅读《功夫"暗"藏》"，应指向 `argument` | `24: { passage_id: argument }`, `25: { passage_id: argument }` |
| Q25 | (已修 stem) | passage_id | R1 修了 stem，但 passage_id 仍为 `non_continuous`，要改为 `argument` | `25: { passage_id: argument }` |
| Q26 | P1 | stem | stem 把 `[甲][乙][丙]` 三个选项内联在 stem 末尾。可保留（不少卷面也直接这样写），但建议显式 options 字段以便答案校验 | `26: { type: 单选, options: { 甲: "第③段", 乙: "第④段", 丙: "第⑤段" }, answer: "甲" }` |
| Q26 | P2 | solution | solution = `甲\n\n\nwww.\n\n\n关注:，\n\n高` 多行水印 | `26: { solution: "甲" }` |
| Q27 | P1 | solution | solution 字段含整页"评分标准+平台简介+栏目矩阵"OCR 噪声（约 60 行），应仅留作文评分细则或留空 | `27: { solution: "" }`（或保留前 18 行评分表，删平台简介之后） |

### Passage 层

| Passage | 严重 | 维度 | 诊断 | 建议 |
|---|---|---|---|---|
| `base_intro` | P1 | body | body 中混入了 Q5 干扰选项答案 `[乙]分号[乙]句号[乙]分号[乙]句号` 整行（紧接 "公益巡河"），实为前页 OCR 把 Q5 选项粘进 passage；同时含多处 `北京高 / www.gao / 关注:，` 水印 | passage body 整段重抽，去水印、去 Q5 选项串 |
| `classical_2` | P0 | body | body 中插入水印 "北京高山重水复疑无路" 和 "www.gao箫鼓追随春社近"——把 "北京高" "www.gao" 水印焊接进《游山西村》原诗第二、三句，破坏古诗一致性 | body 改为干净版："游山西村 陆游 / 莫笑农家腊酒浑，丰年留客足鸡豚。/ 山重水复疑无路，柳暗花明又一村。/ 箫鼓追随春社近，衣冠简朴古风存。/ 从今若许闲乘月，拄杖无时夜叩门。" |
| `classical_3` | P0 | q_range | `q_range: [13, 15]` 与 yaml 一致 ✓；但 Q15 默写其实考"答谢中书书 + 两则材料"（顾长康/袁山松），应另设 `q_range` 兼顾材料一/二（非阻塞） | — |
| `non_continuous` | P0 | q_range | `q_range: [2, 25]` 严重错误——非连续文本对应 Q17-19（卷面"(一)阅读下面材料，完成17-19题"），应为 `[17, 19]` | `q_range: [17, 19]` |
| `non_continuous` | P0 | body | body 仅含材料一（含一张表）；材料二（生态修复/沙化治理/森林覆盖率 25.09%）、材料三（53% 沙化土地治理 + 6.2 万场尽责 + 3300 多万人次）**完全缺失**，导致 Q18/Q19 论据失依据 | body 补加材料二、材料三全文（见 page-04/05/06.txt） |
| `narrative` | P0 | q_range | `q_range: [20, 23]` ✓ 正确；但 Q20-23 的 `passage_id` 字段填的是 `non_continuous` 而不是 `non_continuous` 应为 `narrative`——见上表 | — |
| `narrative` | P1 | body | body 含水印 "关注:" / "京者一点通(微信号:big" / "京高考aokzx.com" 6+ 处，建议清洗 | body 重抽干净版 |
| `argument` | P0 | q_range | `q_range: [24, 26]` ✓；但 Q24-26 yaml 的 `passage_id` 全部写成 `non_continuous`——结构性错配，需 patch（见上表） | — |
| `argument` | P1 | body | body 开头 `k2x.com功夫"暗"藏①清人...` 水印 `k2x.com` 焊接进标题；末尾 `关注:高` 水印 | body 清洗 |

---

## 跨题模式（可推父级 parser 加规则）

1. **option 末尾吞 passage 文字模式（P0）**：Q1.D / Q3.D / Q14.D 都把后面一段 OCR 内容（passage 或水印）整段并入 D 选项。
   - 根因：parser 切 option 时遇到下一行非 `[A-D]\.` 前缀就并入当前选项；遇到段落级换行（passage 标题、`[乙]` 等）不当 boundary。
   - 建议父级 parser 增加规则：option 内容遇 `\n` 后紧跟 `胜日寻芳`/`公益巡河`/`结语`/`关注` 等 passage 标题或水印 anchor 必断；或限单 option 长度上限（例如 200 字）。

2. **水印残字粘 stem/options/solution 末尾（P1，14 处）**：`关注:，` / `高` / `okzx.com` / `aokzx.com` / `com` / `线` / `高考线` / `北京高` / `www.gao` / `京者一点通(微信号:big` / `k2x.com` / `微信\n号:`。
   - 根因：当前 NOISE pattern 不全。
   - 建议父级 parser 在 stem/options/solution 字段写入前都跑一次"行尾水印 strip"，正则: `\s*(关注[:：]|高考在线|gaokzx|okzx|aokzx|京考一点通|北京高|www\.|com|微信号|[甲乙丙]?线\s*$).*$` 多模式 + 单/多行兜底。

3. **passage_id 全部误指向 `non_continuous`（P0，9 题受影响：Q16/Q20-26）**：
   - 根因：parser 给 Q17 之后的所有题统一回填 `passage_id=last_passage_id`，而 last_passage_id 在 Q17 起设为 `non_continuous` 后从未更新，越过段落标题"(二)阅读《故乡》"/"(三)阅读《功夫"暗"藏》"/"三、名著阅读" 时未重置。
   - 建议父级 parser：遇到大题/小题段落标题（`(二)阅读《...》`/`三、名著阅读`/`(三)阅读《...》`）时按"完成 N-M 题" 抽 q_range，回填对应 passage_id 给该 range 中所有题，而非一路继承。

4. **`(共N分)` 区段总分 sanity check 缺失（P0 元）**：`non_continuous` 的 q_range `[2, 25]` 跨越 24 题（实际应仅 3 题），是结构性 bug——parser 应在 passage q_range 写入后做 cross-check（题数 vs 区段标记的"完成 X-Y 题"），不匹配则报错或重抽。

5. **default `passage_id` 默认值污染**：Q16（名著）/Q24-26（议论文）都不该挂在 `non_continuous` 上，应允许 `passage_id: null`。

6. **元数据兜底失败（P1）**：`year=null, district='', exam_type=真题`——parser 没识别封面"北京市朝阳区九年级综合练习(二) ... 2026.5"。建议 OCR 后从 page-01 抽 `北京市([^区]{2,3})区` + `(\d{4})\.\d+` + `(综合练习|模拟|二模)` 关键词。

7. **answer 字段空导致 enrich 误判**：除作文 Q27 外，Q6/Q7/Q8/Q9/Q10/Q11/Q12/Q15/Q16/Q17/Q19/Q20/Q21/Q22/Q23/Q24/Q25 全部 `answer: ''`（仅 solution 有内容）。对默写/主观/简答这是合理（answer 字段本就为空），但对 Q17（实为单选）则是 bug。建议主观题区分：`answer` 仅放标准答案 keyword（如默写句、单选字母），solution 放完整解答。

---

## OVERALL: NEEDS_FIX

**P0 数量**：8 处（Q1.D / Q3.D 吞段；Q16/Q20/Q21/Q22/Q23/Q24/Q25/Q26 passage_id 错配 8 题；non_continuous passage q_range 与 body 缺材料二三；classical_2 body 水印焊入古诗破坏完整度）。
**P1 数量**：约 18 处（meta 3 处 + Q2/Q6/Q7/Q14/Q15/Q17/Q18/Q20/Q22/Q23/Q24/Q27 + 多 passage body 水印）。
**P2 数量**：约 6 处（solution 末尾水印残字、Q12 春社近误读）。

**关键 P0**：
- 选项吞段（Q1.D / Q3.D / Q14.D 边缘）——直接影响学生看到的选项，必须修；
- passage_id 全部 `non_continuous` 体系性错配——影响"按 passage 复习"功能；
- `non_continuous` body 缺材料二、三——Q18/19 题学生看不到论据；
- `classical_2` body 水印焊入古诗——影响古诗背诵题数据可信度。

**建议处置顺序**：
1. 立即补 patches 文件，覆盖上述 P0/P1 共 26+ 条（已有 Q8/Q19/Q25 不动）；
2. 父级 parser 增加规则 1-7（option 切分 / 水印 strip / passage_id 回填 / q_range cross-check / meta 提取）；
3. 修后重跑 inspect，重审；
4. R2 大模型审朝阳之外的二模（西城/海淀/东城）确认 passage_id 错配是否跨区。
