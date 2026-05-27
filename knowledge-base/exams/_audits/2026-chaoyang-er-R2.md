# 2026 北京朝阳区中文二模 yaml 审核报告（R2 复审）

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-chaoyang-er.yaml`
- patches: `knowledge-base/exams/_patches/chinese/2026-chaoyang-er.yaml`（已修 Q8/Q12/Q14/Q17/Q19/Q25/Q26/Q27）
- R1 报告: `knowledge-base/exams/_audits/2026-chaoyang-er-R1.md`
- 审核范围：R1 完成 + parser 4 处跨区 P0 修后再审，目标 (1) 验证 R1 修复无回归 (2) 挖 R1 漏的 P0/P1 (3) 处置剩余水印残

---

## R1 修复回归验证

| R1 修复项 | 当前状态 |
|---|---|
| meta `year=2026` (line 6) | ✅ |
| meta `district=朝阳区` (line 7) | ✅ |
| meta `exam_type=二模` (line 8) | ✅ |
| passage `non_continuous.q_range=[17,19]` (lines 53-55) | ✅ |
| passage `narrative.q_range=[20,23]` (lines 68-70) | ✅ |
| passage `argument.q_range=[24,26]` (lines 132-134) | ✅ |
| Q16 `passage_id` 不再指 non_continuous | ✅（yaml 无字段=null）|
| Q20-Q23 `passage_id=narrative` (lines 641,662,705,729) | ✅ |
| Q24-Q26 `passage_id=argument` (lines 749,771,794) | ✅ |
| Q1.D 截到 "第④句" (line 157) | ✅ |
| Q3.D 截到 "更新" (line 203) | ✅ |
| Q5/Q11/Q15/Q18 长 stem/options 干净 | ✅ |
| Q8 score=1.0 (line 313, via patch) | ✅ |
| Q12 sol "春社近" (via patch) | ✅ |
| Q14.D 干净尾 (via patch) | ✅ |
| Q17 type=单选 + options 拆 (via patch) | ✅ |
| Q19 stem (line 596) | ✅ |
| Q25 stem (line 753) | ✅ |
| Q26 type=单选 + options 拆 (via patch) | ✅ |
| Q27 sol 留空 (via patch) | ✅ |
| Q18 options C/D 水印 `\n线`/`\n高考线` 已 strip (lines 578-579) | ✅ |
| Q24 stem 末水印 `okzx.com` 已 strip (line 733) | ✅ |
| Q23 stem 末水印 `关注:，高` 已 strip (line 709) | ✅ |
| Q20 sol 末 `(共2分。共2` 已 strip (lines 624-629) | ✅ |

**全部 22 处 R1 修复无回归。**

---

## R2 新发现问题清单

| Q / 字段 | 严重 | 维度 | 诊断 | 建议 patch |
|---|---|---|---|---|
| Q8 sol | **P0** | data-integrity | line 316-333: Q8 solution 仍是 OCR 大坨 `江春人旧年\n\n\n\n9.答案:庭下如积水空明\n\n\n10.答案示例一\n\n①昔人已乘黄鹤去\n\n②此地空余黄鹤楼\n\n答案示例二\n\n①先天下之忧而忧\n\n②后天下之乐而乐`。把 Q9/Q10 答案焊进 Q8，且 "江春**人**旧年" 是 OCR 误读（原诗 "江春**入**旧年"）。R1 patches 只改 score=1 没碰 sol | `8: { solution: "江春入旧年" }` |
| Q11 sol | P2 | accuracy | line 395: `①丰年农家殷勤待客` 表述偏离标准答案。真实答案应为 "莫笑农家腊酒浑，丰年留客足鸡豚"（先写农家盛情款待客人）— 当前简化版可接受但建议核对源 PDF | 选保留或核对 |
| Q16 stem | **P1** | watermark | line 507 末尾 `关注:京考一点通()，'` — 这是用户提到的剩余 2 处水印之一 | `16: { stem: "从下面两个题目中任选一题，按要求作答。\n(1)阅读整本书，你积累了怎样的阅读经验?请从《朝花夕拾》《红星照耀中国》《昆虫记》《经典常谈》《艾青诗选》中任选一部，从整本书阅读经验的角度，给学弟学妹写一条建议，并结合具体内容，加以说明。(100字左右)\n(2)环境对人物的成长起着重要作用。请从《海底两万里》《钢铁是怎样炼成的》《简·爱》中任选一部，结合人物所处的环境，简要分析它对人物成长的作用。(100字左右)" }` |
| Q16 sol | P1 | data-integrity | lines 509-536 残留旧 OCR 噪声段（"关注在 / 成日) / 了微后 / F: / 口.0门KZx / 入代口人..."），patches 未清，且 sol 实际应该是 "示例" 性答案文本 | `16: { solution: "" }`（参照名著阅读规范，无标答留空）|
| narrative body | **P0** | passage-corruption | line 97 段 ③ 末："**开始京高考琢磨放鞭炮**" — "京高考" 三字是水印焊入正文（应为 "开始琢磨放鞭炮"）。R1 已发现却未 patch | passage `narrative.body` 重写或目标行修：`开始琢磨放鞭炮` |
| classical_2 body | **P0** | passage-corruption | line 40 `北京高山重水复疑无路` — "北京高" 是水印焊入古诗。陆游原句为 "山重水复疑无路"。R1 已发现却未 patch（patches 不含 passage override）| classical_2.body 第三句改：`山重水复疑无路，柳暗花明又一村。` |
| non_continuous body | **P0** | passage-incomplete | lines 56-64：只含材料一 + 残半表格（`63271.5-0.7w.` `水电14616.7` 截断），**材料二（生态修复/陕西榆林/森林覆盖率25.09%）和材料三（53%沙化土地/6.2万场/3300多万人次）完全缺失**。这两段是 Q18 选项 C/D 与 Q19 主观题答案的直接依据。R1 已发现却未补 | 从 page-05.txt 第 37 行起 + page-06 抽材料二/三补入 body |
| non_continuous body | P1 | watermark/truncation | line 62 末 `63271.5-0.7w.` 中 `w.` 是水印残尾；line 64 `水电14616.7` 表格被截掉增长率列；表格数据极不完整 | 配合上一条同步重抽 |
| Q22 sol | P1 | watermark | lines 668-693：示例一 "刻画了男孩的\n\n**在线**\n切;" — "在线" 是水印误入，原应是 "刻画了男孩的**急**切;"（"急" 字与 "在线" 水印重叠被替换）。R1 已发现 P1 仍未 patch | `22: { solution: "答案示例一:\n\"冲\"写出男孩听到鞭炮声后快速跑过来的样子，刻画了男孩的急切;\"观望\"是写男孩站在一边观察，写出他犹犹豫豫、不好意思主动搭话的样子。两个动词表现了隔壁男孩渴望玩伴的心理与质朴害羞的特点。\n答案示例二:\n\"扎\"形象写出两个孩子脑袋紧紧凑在一起的模样，表现出两人瞬间亲近、毫无隔阂的状态;\"琢磨\"细致刻画了二人认真研究怎么放鞭炮的样子。两个动词生动勾勒出孩童天真烂漫、专注玩耍的情态。\n答案示例三:\n\"躺坐\"写出儿子返程时半躺半坐、无精打采的样子，\"遮\"写出他用帽子盖住脸，不愿与\"我\"交流。两个动词表现出儿子离别小伙伴后的失落与不舍，表达了他对故乡、对故乡玩伴的留恋之情。" }` |
| Q24 stem | P2 | format | line 733 `因为①___，所以阅读文学作品时，我们要②___。` — yaml 实际是 `因为①，所以…我们要②。` 缺 `___` 横线 marker（用户友好度小损） | `24: { stem: "文章启示我们:因为①___，所以阅读文学作品时，我们要②___。(2分)" }` |
| Q27 sol | P1 | content-policy | 即使 patches 已设 `27: { solution: "" }`，yaml 源文件 lines 808-1009 仍存有 200 行评分细则+平台广告 OCR。运行时 patches 生效=干净，但源 yaml 体积冗余；如直接序列化分发该文件则会泄露广告 | 已 patch 处理，建议未来 parser 在写盘前清作文广告块 |
| Q7 stem | P2 | format | line 296 末 "补写一个分句。(2分)，" — 末尾粘 `，` 单字（原 OCR 残） | `7: { stem: "根据语境，你在文段中的横线处补写一个分句。(2分)" }` |
| Q10 stem | P2 | format | line 365 `“①，②”` — 应为 `"①___，②___"` 横线标记缺失 | `10: { stem: "游览名胜古迹，总有与之相关的古诗文名句涌上心头。你印象深刻的两句是\"①___，②___\"。(本试卷中出现的句子除外)(2分)" }` |
| base_intro body | P1 | passage-corruption | line 30 `[乙]分号[乙]句号[乙]分号[乙]句号结语在本次"美丽朝阳生态之旅"研学活动中`——把 Q5 选项 `[乙]分号/[乙]句号` 4 串焊接进 passage 紧靠 "结语" 段；末尾 line 32 仅一个 `，` 散字 | base_intro.body 清理：删除 `[乙]分号[乙]句号[乙]分号[乙]句号` 串，"结语" 直接接续 |
| passages 未带 figure | P2 | meta | non_continuous 唯一带 figure（line 65）；narrative/argument 无图—对，但 base_intro 实际含照片（page-01 题干上方研学照），未抽 | 可选补 |

### "剩余 2 处水印残" 定位结论
用户提到的 "京考一点通" / "关注:" 残：
- **京考一点通**：Q16 stem 末（line 507）— 上表已建议 patch
- **关注:**：同一处（line 507 末 `关注:京考一点通()，`）— 同上

其他 grep 命中的 "关注/京考/微信/www." 全部在 Q27 sol 广告段（patches 已 `solution: ""` 处理）或 narrative `京高考` 焊入（上表 P0）。**这 2 处水印只对应 Q16 stem 一处 patch**。

---

## P0 跨区 parser 建议（R2 新挖）

R1 已建议的 4 处 parser 修（option 切分/水印 strip/passage_id 回填/q_range cross-check/meta 提取）确认全部落地。R2 新发现：

1. **passage body 不在 patches 覆盖范围**：当前 patches 只支持 `questions.N.field` 覆盖，无 `passages.X.body` 覆盖路径。导致 R1 报告的 5 处 passage 级 P0（classical_2 古诗焊水印、non_continuous 缺材料二三、narrative `京高考` 焊入、base_intro Q5 选项焊入、argument 标题水印 `k2x.com`）**全部无法通过 patches 修**。建议父级 parser 扩展 patches schema 支持 passage override。

2. **Q8 sol 沿用了 R1 之前的 OCR 全 block（含 Q9/Q10 答案）**：根因是 parser 给默写题切答案块时，遇 `8.答案:...` 起到下一题 `9.答案:` 之前都吞入 Q8。需在 `_collect_dictation_answer` 加 `\n\d+\.(答案|示例)` 终止符。波及 Q20 sol（已修但 R1 修法是手 strip）。

3. **古诗/古文 body 水印焊入字符内（非行尾）**：classical_2 line 40 `北京高山重水复` 中 `北京高` 三字直接焊在 `山` 前面。当前水印 strip 只看行尾，需补 "古诗/古文 body 写入前过白名单字符集（只留中文+常用标点）" 一道兜底。

---

## OVERALL: NEEDS_FIX

**P0 数量**：4 处（Q8 sol 焊后题答案 + narrative body `京高考` 焊入 + classical_2 body `北京高` 焊入 + non_continuous body 缺材料二三）。
**P1 数量**：5 处（Q16 stem 水印 + Q16 sol 噪声 + Q22 sol `在线`→`急` + base_intro body Q5 焊入 + non_continuous body 表格截断）。
**P2 数量**：4 处（Q7/Q10/Q24 横线 marker + Q11 sol 表述偏简）。

**关键 P0 提醒**：
- **Q8 sol** 当前焊接 Q9/Q10 答案是阻塞性 bug — 学生看到 Q8 就被剧透下两题，必须立即修；
- **passage body 3 处 P0** R1 已诊断但 patches 无法承载（schema 不支持），需双轨：(a) 升级 patches schema 支持 passages override；(b) 临时手改 yaml 源文件清水印；
- **non_continuous body 缺材料二三** 影响 Q18/Q19 答题/讲评，是最大数据可信度问题。

**建议处置顺序**：
1. 立即扩 patches 增 Q7/Q8/Q10/Q16/Q22/Q24 共 6 条；
2. 升级 patches schema 支持 `passages.X.body` 覆盖，补 4 处 passage 级 P0；
3. parser 修 `_collect_dictation_answer` 终止符 + 古文字符白名单兜底；
4. 修后重跑 inspect，进 R3 收敛或挪 exam-review 人工。
