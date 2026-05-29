# 2026 北京房山区中文二模 R2 复审报告

审核对象: `knowledge-base/exams/mock/chinese/beijing/2026-fangshan-er.yaml`
Patch: `knowledge-base/exams/_patches/chinese/2026-fangshan-er.yaml`
R1 报告: `knowledge-base/exams/mock/chinese/beijing/_audits/2026-fangshan-er-R1.md`
源 PDF / OCR: `knowledge-base/exams/_staging/chinese/2026-fangshan-er/tencent-cache/general/page-{10..13}.txt`

---

## 1. R1 score 修复正确性核验

**结论：R1 patch 把 13 题 score 全 "patch=yaml+delta" 反向算了。这个公式本身是错的——R1 audit 表里的 src 列已经是真值，patch 应直接取 src 列。**

但巧合的是：13 项里有 10 项 src 同时等于 yaml+delta（因为 delta 在 audit 表里就是 |src-yaml|），所以这 10 项 patch 写对了。**3 项 patch 与 R1 audit src 列不一致**，这就是 yaml=97 vs 真值=100 的 -3 缺口：

| 题 | yaml(原) | R1 audit src（真值，已 OCR 交叉核对） | patch 值 | 差 |
|---|---|---|---|---|
| Q10 | 2 | **4**（OCR: "评分:本题4分"）| 3 | **-1** |
| Q17 | 1 | **3**（OCR: "评分:本题共3分"）| 2 | **-1** |
| Q24 | 1 | **3**（OCR: "评分:本题共3分"）| 2 | **-1** |

合计 -3 分，正好补 97 → 100。Patch 注释里写的 "Q10 src=3 / Q17 src=2 / Q24 src=2" 是 patch 作者**误读 R1 audit**（R1 表里这三项 src 列分别是 4/3/3），且 patch 头部公式 "patch = yaml + delta" 写法本身让人误以为是反算（实际 R1 已经给出 src，本不该再算）。

**R2 修复**（必修，P0）：
```yaml
10: { score: 4 }   # 原 patch=3 → 4，OCR "本题4分"
17: { score: 3 }   # 原 patch=2 → 3，OCR "本题共3分"
24: { score: 3 }   # 原 patch=2 → 3，OCR "本题共3分"
```
应用后 full_score 25 题 = 100，section 分配：基础 14 + 古诗文 16（4+2+4+2+2+2）+ 名著 5 + 现代文 25（2+2+3+2+3+3+3+2+2+3）+ 作文 40 = 100 ✓。

其余 10 项 score patch（Q1/Q8/Q9/Q12/Q14/Q15/Q16/Q20/Q22/Q23）经 OCR 复核全部正确，**不动**。

---

## 2. R1 未修的 P1 OCR 形态问题（仍存在）

### Q2/Q4/Q6/Q11/Q22 选项 4 合 1（R1 已列出，R2 仍未拆）

当前 yaml（5 题）options 仍是 A 字段塞 4 选项：
- Q2 `A: 生肖B.坚韧不拔C.窥见D.天人相应`
- Q4 `A: 活动渐进B.认知融入C.内涵渗透D.文化熏陶`
- Q6 `A: 精巧刚健传神` / `B: 精巧传神刚健` / **C: 刚健精巧传神 D.刚健传神精巧**（C 塞 D，**无 D 字段**）
- Q11 `A: 顽固不化B.固若金汤C.君子固穷D.根深蒂固`
- Q22 `A: 读书的智慧 B.青春与奋斗` / `C: 青年与读书D.成才的途径`（A 塞 B，C 塞 D）

下游做题/展示会把 ABCD 当一个选项呈现。**R2 必修（P0）**：手 patch 拆 ABCD（Q6 须新建 D 字段 "刚健传神精巧"；Q22 同理拆 B/D；Q11/Q2/Q4 按 OCR 末位字 split）。

### Q3 options 仍错位 + 缺 D
当前 yaml：`A: [甲]、[乙]，B.[甲]，\n[乙]、` / `C: [甲]，[乙]` —— B 仍塞在 A 字段，C 不全（应 "[甲]，[乙]。"），**全卷无 D 字段**。R2 必修。

### Q12 B 选项截断
仍是 `B: 愚公艰苦奋斗、誓要铲平大山的`（缺尾 "决心。"）。R2 必修。

---

## 3. R2 新发现 / R1 未列

### Q4 stem 跨页粘连未清（R1 已提及但未 patch）
yaml Q4 stem 末尾仍带 `..."青玉马上封侯坠"利用局部沁色的`，是 page 5 跨页 OCR 把 Q5 引文粘了进来。

### Q5 stem 仍混入手记五整段（R1 已提及）
约 200 字手记五全段粘在 Q5 stem 末尾。

### Q17 stem OCR 错字 "三kzx绍"
当前 yaml：`...材料分别从①③三kzx绍。(3分)` —— ② 漏 OCR、"方面介" 被水印 "kzx"（www.gaokzx.com）截断。**严重影响 stem 可读性**，R2 patch 必修为：`...材料分别从①___、②___、③___三个方面介绍。(3分)`

### Q23 solution 人名 OCR 错（R1 已提及）
"深圳快递小哥**聂剑**" 应为源 PDF 的 "**袁石剑**"（OCR 错字，需 patch 改 solution）。同时 solution 中含 `ga`/`w` 单字水印行。

### 水印 / 占位符残留（无新增 P0，但分布广）
- `()，` 图占位符：Q5/Q7/Q12/Q14/Q21/Q23 stem 或 solution 末尾共 6+ 处
- `om`/`m`/`com`/`W`/`ww`/`北京`/`考`/`kzx`/`gakzx`：base_intro、narrative、argument 三 passage body 及部分 solution 散落
- 跨题 stem 粘连：除 Q4/Q5 外，Q14 stem 末 `w()，`、Q21 stem 末 `()，`

均非 P0（不影响分值与答题），但污染 LLM 输入。R2 建议批量 sed 清洗 NOISE_PATTERNS 扩展。

### KP 跨学科错配
- Q13 KP 含 `默写`，实际是文言对比阅读填空（不是默写），P1。
- Q14 KP `名著情节/人物形象/主题理解` 全错，源题考的是**阅读方法**（圈点批注/精读跳读），应改 `阅读方法/名著阅读策略`，P1。
- 其余 KP 与学科 module 一致，未见跨 chinese↔其他学科串味（physics/politics 等关键词 0 命中）。

### passage q_range 校验
全部 ✓（base_intro 1-7 / classical_2 9-10 / classical_3 11-13 / non_continuous 15-17 / narrative 18-21 / argument 22-24）。Q8/Q14 无附文 passage_id 留空正确。

### Q25 作文评分标准表格
solution 仍是 OCR 平铺的破碎 80+ 行表格，对学生/教师无可读价值。建议 patch 简化为 "见详细评分标准表（一类卷 40-34 / 二类卷 33-29 / 三类卷 28-24 / 四类卷 23-0）+ 书写 4 分独立计"，P2。

---

## 4. 修复优先级汇总

**R2 必修（P0）— 让 full_score 真正回到 100**
1. Q10/Q17/Q24 patch score 从 3/2/2 改 4/3/3（+3 分）。
2. 改 yaml 头 `full_score: 97` → `100`。
3. Q2/Q4/Q6/Q11/Q22 五题选项 4 合 1 手拆 ABCD（Q6 补 D；Q22 拆 B/D）。
4. Q3 options 重写（补 D，C 加 "。"）。
5. Q12 B 选项补 "决心。"。
6. Q17 stem 改 "①\_\_\_、②\_\_\_、③\_\_\_三个方面介绍"。
7. Q4 stem 截掉末尾粘连 "...沁色的"；Q5 stem 截掉手记五段。

**R2 建议（P1）**
8. Q23 solution "聂剑" → "袁石剑"。
9. Q13 KP 删 `默写`；Q14 KP 改 `阅读方法` `名著阅读策略`。
10. 全卷批量清 `()，` / `om` / `m` / `kzx` / `北京` 单行水印。

**R2 可选（P2）**
11. Q25 作文评分表 patch 简化。
12. Q1 KP 加 `书法鉴赏`、Q8 KP 加 `名句默写`、Q20 KP 改 `句子含义`。

---

## OVERALL: NEEDS_FIX

R1 修复方向对，但 patch 3 处误读 R1 audit src 列（Q10/Q17/Q24）造成 -3 缺口，full_score 仍 97 ≠ 100。叠加 R1 已暴露但未动手的 7 处 P0 形态问题（5 题选项 4 合 1、Q3 缺 D、Q6 缺 D、Q12 截断、Q4/Q5/Q17 stem 污染），R2 还需一轮 patch 才能闭环到与朝阳/海淀/东城同档"精准 100 分 0 误差"。

根因仍是 R1 结论：**image OCR 路线 v3 在房山卷的集中爆发**，房山若能拿到 zxxk docx 源切 v4 docx 路线，可一键全修；当前只能继续手 patch。
