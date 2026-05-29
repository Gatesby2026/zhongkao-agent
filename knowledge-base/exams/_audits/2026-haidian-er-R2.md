# 2026 北京海淀区中文二模 yaml 审核报告（R2）

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-haidian-er.yaml`
- patch: `knowledge-base/exams/_patches/chinese/2026-haidian-er.yaml`
- 上轮: `knowledge-base/exams/_audits/2026-haidian-er-R1.md`
- 源: `knowledge-original/gaokzx-downloads/2026-ermu-chinese/haidian_chinese.pdf`
- OCR: `knowledge-base/exams/_staging/chinese/2026-haidian-er/tencent-cache/general/page-NN.txt`

---

## 一、R1 修复回归核查

| R1 项 | 当前 yaml 状态 | 回归判定 |
|---|---|---|
| total_questions=27 | yaml line 13 = 27，questions 列表确有 1-27 共 27 题 | OK |
| Q1 改书写题 | type=书写 / score=1 / options 字段不在（被去掉）/ stem="请在封面上用正楷字书写标题。(1分)" / solution=略 | OK |
| Q1 stem 表述 | patch 写"请在封面上用正楷字书写标题。(1分)"，源 PDF 原文为"在封面上用正楷字书写标题：'艺术赋能城市微更新'调查报告。(1分)"——**简化失真但不影响评分** | P2 |
| Q4 补题 | 已 create，type=单选/score=2/answer=B | **见下方 P0** |
| Q7.C 修 | options.C="第③句" ✓ | OK |
| Q8 score 1→2 | score=2 ✓ | OK |
| Q9 score 1→2 | score=2 ✓ | OK |
| Q10 score 5→1 | score=1 ✓ | OK |
| narrative "北京高kzx" 清 | line 98 "真是惊人" 已干净 ✓；line 132 "ww⑥" 仍残留 | 部分 OK |

---

## 二、R2 新发现 P0

### P0-1（**严重**）：Q4 options 全部捏造，与源卷完全不符

源 OCR `page-02.txt:8-12` 明确：

```
1.你检查了资料中成语的使用情况。下列成语使用不恰当的一项是(2分)
A.别具一格   B.鳞次栉比   C.浑然一体   D.悠然自得
```

答案页 `page-10.txt:8` = "4.B (2分)" → B = 鳞次栉比。

但 patch/yaml Q4 写成：

```yaml
A: 美不胜收   B: 鳞次栉比   C: 栩栩如生   D: 络绎不绝
stem: 下列加点字成语使用不恰当的一项是(2分)
```

四个成语中 3 个被换掉（A/C/D 全错），且 stem 漏了"你检查了资料中成语的使用情况。"前缀，加了"加点字"三个原题没有的字。答案 B 巧合对（仅因鳞次栉比恰好是错项），但选项库错误会直接污染：(1) 学生小分匹配（学生答 A=别具一格 yaml 里没这选项）；(2) 相似题推荐 KP；(3) 后续 enrich KP 学习。**必须按源 OCR 重写**。

### P0-2：Q6 options.C 仍残缺为 `"[甲]"`

R1 在表中已识别（patch 第 28 行注释"R2 待源图核对"），patch 实际**未修**。源 OCR `page-02.txt:32-34`：

```
C.[甲]
D.[甲]②
[乙]③
```

C 行确实在源 PDF 顶端就被截断（OCR 看到的就只有 `C.[甲]`），需上源 PNG（`knowledge-original/beijing-mock-2026/ermo/haidian/chinese/images/page-02.png`）或 qwen-vl 重 OCR 该 4 行块。结合答案 A 与剩余 ① `[甲]② [乙]③` 推断 C 应为 `[甲]② [乙]④` 或 `[甲]① [乙]②`（B/D 已分别占 [甲]①[乙]③ 和 [甲]②[乙]③，C 最可能是 [甲]②[乙]④ 才与四个备选 ①②③④ 互斥）。**需读源 PNG 确认**，不可猜。

### P0-3：narrative.body 第 ⑲ 段水印 `ww⑥` 仍未清

yaml `narrative.body` 第 132 行（即源 ⑲ 段前）依然为 `ww⑥我连忙向人群中寻找…`。patch 的 `body_replace` 写了 `"ww."` 但实际残字是 `"ww"`（无点），未命中。同段开头编号 ⑲ 被 OCR 当作 ⑥（圆圈大数字 ⑪–㉗ 识别失败），但段意正确，纯编号偏差。

### P0-4：narrative 第 ②③ 段实际是 ②③ 两段同一句"跑冰排哪！"——②段在 yaml 中无编号、③ 段已有编号

yaml line 86-88：

```
"跑冰排哪!"
③"跑冰排哪!"
```

② 段编号丢失。源 PDF 此处两段确为重复短句（一近一远的呼喊），需补 `②` 标号。属 P0：影响 Q21/Q22 对段号的引用。

---

## 三、R2 新发现 P1

| 位置 | 诊断 | 建议 |
|---|---|---|
| Q1 stem | 原题"在封面上用正楷字书写标题：'艺术赋能城市微更新'调查报告。(1分)"，patch 简化为"请在封面上用正楷字书写标题。" | 还原全句 |
| Q3 stem | 末尾 "(2分)" 后有 `()，` 残字（line 204）—— R1 表未标，残留 OCR 噪声 | strip |
| Q5 stem | 仍含 `\n\n[画线句修改后参考: ...]`（line 251-252），是 parser 注入的提示文字，应只保留题干 | 仅留 "文段中的画线句存在问题，请你修改。(2分)" |
| Q9.stem 尾 | `(2分)()，` 残留（line 339） | strip |
| Q9.solution | 仍"猿鸟乱鸣沉鳞竞跃"两空粘连 | 拆 `①猿鸟乱鸣 ②沉鳞竞跃` |
| Q10.solution | 仍三行示例 + 末尾 `\n\n\n(` 残碎符号（line 358-366） | 整理为单行示例 + 删尾噪声 |
| Q15.solution | "③" 与 "信士" 仍换行拆开 | 合并 |
| Q22.stem | "第⑤段和第⑧段" → 源为 "第⑤段和第⑱段"（line 625），未改 | stem 同步 |
| Q25.stem | 末尾 `ww.` 水印未清（line 695） | strip |
| Q26.solution | 末尾 `\n\n  ww.` 水印未清（line 726） | strip |
| Q27.solution | 仍是垃圾："k.com / 信号:）/ 参考答案" 整段污染（line 754-762） | 强制清空 `solution: ""` |
| Q27.stem | 含 "题目一:开窗见风景**在线**题目二" —— "在线" 是水印窜入；末尾 `\n()，` 残留 | strip "在线" + 删尾噪声 |
| base_intro.body | line 29 仍含 "根据词典的解释，下面对文段中'城市肌理'的理解不正确的一项是(2分)()，东美园城市艺术空间·[甲]"；line 35 仍含 "①造园生艺境②赏美无边界③观画有奇趣④修树创微景[乙]④[乙]③[乙]③"；line 39 仍 "第②句第②句" | 重写 body 三段 |
| non_continuous.body | 表 1 OCR 仍极乱（"主要道具 木偶本体、木杖木偶本体、提线木偶本体"），末尾 `gaww.` 未清；正文 `园。` 处异常断句（line 73） | strip 水印 + 拆 figure |
| narrative.body | ⑥段尾"真是惊人" R1 已修干净 ✓；⑲ 段 yaml 中 "江上的人只顾奋死搏斗，无声无息。江岸上的人们却一窝蜂随着漂流的冰排，面向下游奔跑" 与 OCR `page-07.txt:26-27` 完全一致，**R1 报告中"少'一面狂嘶呐喊'"系误报**（源 PDF 本无此句） | R1 误报，OK |
| argument.body | line 149 ④⑤ 段仍合并为 "④⑤"；末段 "联想()，" 残留（line 150）；末尾 `ww.` 未清 | 拆段 + strip |
| classical_3 | 仍缺 Q15 所需的"材料二《管晏列传》/材料三《后汉书·范式张劭》"两则文言文（R1 P1，patch 未补） | 补 sub_materials |

---

## 四、R2 新发现 P2 / KP

| Q | 当前 KP | 建议 |
|---|---|---|
| Q10 | "古诗赏析 / 文言文实词" | 改 "默写 / 古诗内容理解" |
| Q11 | "古诗内容理解 / 文言文理解" | 去 "文言文理解"（Q11 是宋词非文言文） |
| Q15 | "默写 / 古诗文内容理解" | OK，但建议加 "文言文实词" |
| Q18 | "信息提取/段落梳理 / 记叙文阅读" | 去 "记叙文阅读"（非连续性文本） |
| Q20 | "信息提取/段落梳理 / 记叙文阅读" | 保留（确为记叙文） |
| Q21 stem | "第17段" 应为 "第⑰段"（圆圈数字），solution/option 内已正确 | 同步 |

未发现物理 / 数学 / 英语 KP 串味。module 字段（writing/reading/classical）分布合理。

---

## 五、数字汇总

- **R1 真修**：8 处声称中 7 处确实落到 yaml（Q1 type、Q4 create、Q7.C、Q8/Q9 score、Q10 score、narrative "北京高kzx"）；**1 处仅注释未实修**（Q6.C）。
- **R2 新挖 P0**：4 处（Q4 options 捏造 / Q6.C 仍残 / narrative ⑲ "ww⑥" 残 / narrative ② 段编号丢失）。
- **R2 新挖 P1**：14 处（stem/solution 尾巴残字 + 多 passage body 未清 + Q22 stem ⑧→⑱ + Q27 stem "在线" 水印 + Q5 stem 注入提示 + classical_3 子材料缺失）。
- **R2 新挖 P2**：5 处（KP 优化）。

**特别警示**：R1 patch 在 Q4 上用了**未经源 OCR 核对的猜测内容**（美不胜收/栩栩如生/络绎不绝 三个选项凭空构造），且 Q6.C 留下 TODO 注释 "R2 待源图核对" 实际就被忽略。此为 patches 流程的系统性风险：**任何 create 的题必须用源 OCR/PNG 锚定**，否则比缺题更危险（学生小分将匹配到错误选项库）。

---

## 六、推荐 R2 修正 patch 关键改动

```yaml
questions:
  1:
    stem: "在封面上用正楷字书写标题：\"艺术赋能城市微更新\"调查报告。(1分)"
  3:
    stem_strip: "()，"  # 末尾
  4:  # 重写 options/stem，按源 OCR
    create: true
    type: choice
    score: 2
    stem: "你检查了资料中成语的使用情况。下列成语使用不恰当的一项是(2分)"
    options:
      A: 别具一格
      B: 鳞次栉比
      C: 浑然一体
      D: 悠然自得
    answer: B
    solution: "B（鳞次栉比形容房屋等密集排列，此处用于雕塑点缀花木之间不当）"
    knowledge_points: [成语运用]
    passage_id: base_intro
  5:
    stem: "文段中的画线句存在问题，请你修改。(2分)"
  6:
    options:
      C: "[甲]②  [乙]④"   # **需源 PNG 二次确认**
  9:
    stem: "晓雾将歇，①;夕日欲颓，②。(陶弘景《答谢中书书》)(2分)"
    solution: "①猿鸟乱鸣  ②沉鳞竞跃"
  10:
    solution: "答案示例：蒹葭苍苍 / 晴川历历汉阳树 / 嘤嘤成韵（任答一句即可）"
  15:
    solution: "①答案示例:高山流水  ②生我者父母，知我者鲍子也。  ③信士"
  22:
    stem: "\"渺小\"在第⑤段和第⑱段两次出现，分别表达了作者怎样的情感。(2分)"
  25:
    stem: "阅读全文，下列分析不恰当的一项是(2分)"
  26:
    solution: "画线处使用了举例论证，举出鉴赏齐白石画作时，通过山泉和蝌蚪的画面能联想到山村生活的例子，证明了联想可以帮助鉴赏者建立起艺术形象与生活的关系，从而更深切地感受艺术形象的观点。"
  27:
    stem: "从下面两个题目中任选一题，按要求写一篇作文。\n题目一：开窗见风景\n题目二：就这样携手同行\n要求：请将作文题目写在答题卡上，文体不限，诗歌除外。作文内容积极向上，字数在600-800之间，不出现真实的学校名称、师生姓名等。"
    solution: ""

passages:
  base_intro:
    body: |  # 仅留三段正文，去 Q3/Q6/Q7 注入
      [东美园城市艺术空间正文]
      [北太平庄城市画廊正文]
      [第三部分调查结论 ①-④ 四句]
  narrative:
    body_replace:
      - {from: "ww⑥我连忙", to: "⑲我连忙"}
      - {from: "\"跑冰排哪!\"\n③", to: "②\"跑冰排哪!\"\n③"}
  argument:
    body_replace:
      - {from: "④⑤各种艺术形式", to: "④[此处需补 ④ 段，源 PNG 第 11 页核对]\n⑤各种艺术形式"}
      - {from: "联想()，", to: "联想，"}
      - {from: "ww.", to: ""}
  non_continuous:
    body_replace:
      - {from: "gaww.", to: ""}
```

---

OVERALL: NEEDS_FIX
