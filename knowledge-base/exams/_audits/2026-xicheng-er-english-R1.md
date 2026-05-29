# 2026 北京西城区英语二模 — yaml R1 深度审核

- **yaml**: `/Users/jiakui/projects/zhongkao-agent/knowledge-base/exams/mock/english/beijing/2026-xicheng-er.yaml`
- **源 PDF**: `/Users/jiakui/projects/zhongkao-agent/knowledge-original/gaokzx-downloads/2026-ermu-english/xicheng_english.pdf`
- **OCR**: `_staging/english/2026-xicheng-er/tencent-cache/general/page-01..12.txt`
- **路线**: english_image_paper.py (image OCR v1)

---

## 卷面元数据 + 缺题分析

### 官方元数据（OCR page-01 line 6 直接给出）

> 本试卷共11页，共两部分，**共38题。满分60分。考试时间90分钟。**
> 第一部分 — 本部分共33题，共40分
> 第二部分 — 本部分共5题，共20分

**结论：官方共 38 题 / 60 分 / 90 分钟，不是 39 题**。task 描述的 "应 39/60" 不准确，西城二模卷面与一模常见结构差 1 题（一模 39 题，二模 38 题，少了一道单选 — 西城二模 12 单选 vs 一模 13 单选）。

### yaml 现状（Python 实测）

| 项目 | 现状 | 官方 | 差值 |
|---|---|---|---|
| 总题数 | 37 | 38 | **-1** |
| 总分 | 59.0 | 60 | **-1** |
| 单选 | 12 (1-12) | 12 | 0 |
| cloze | 7 (13,14,**16**,17,18,19,20) | 8 (13-20) | **-1（缺 15）** |
| reading (单选 21-33) | 13 | 13 | 0 |
| reading_express | 4 (34-37) | 4 | 0 |
| 作文 | 1 (38) | 1 | 0 |
| 考试时间 | `duration_minutes: null` | 90 | **错** |
| 学科年份 | `year: null  district: ''  exam_type: 真题` | 2026 / 西城 / 模拟 | **元数据全错** |

### Root cause：Q15 被 parser 丢弃

OCR `page-03.txt` line 21-23 显示 Q15 选项被 OCR 截断成 3 个：

```
21: 15. A. looked
22: C.reached
23: D. flew
```

**B 选项整行漏读**。english_image_paper.py 对 cloze 选项强校验 4 个 (A/B/C/D)，只有 3 个时直接丢题，导致 yaml 中 ID 从 14 跳到 16，passage `q_range: [13, 20]` 仍标 8 题但 questions 列表只 7 题。

题干在 OCR `page-02.txt` line 25 完整存在：
> she grabbed (抓起) two dark socks, put them on and **15** out of the door.

答案 key（`page-11.txt` line 20）：**15.D**。

**修复建议**：手动 patch Q15，options = `{A: looked, B: <从源图补>, C: reached, D: flew}`，answer=D。建议从 `images/page-03.png` 用 qwen-vl-max 复审 B 选项原词（看场景多半是 `walked` 或 `rushed`/`ran`/`hurried` 一类与"冲出门口"匹配的动词，答案 flew = 飞快冲出）。

---

## 逐题问题清单

### P0（错或缺）

1. **缺 Q15（cloze）** — 见上节根因分析。passage `cloze` q_range=[13,20] 标 8 题但 yaml 只 7 题，total_questions=37 而非 38，total_score 59 而非 60。

2. **元数据全空**
   - `year: null` → 应 `2026`
   - `district: ''` → 应 `西城`（YAML 头部注释也错："None年北京真题english"，应"2026年北京西城二模english"）
   - `exam_type: 真题` → 应 `模拟` 或 `二模`
   - `duration_minutes: null` → 应 `90`
   - `subject: english` ✓

3. **structure 字段错** — `"25单选(32.0分) + 7cloze(7分) + 4reading_express(10.0分) + 1作文(10分)"` 不含 cloze 缺题情况，且把 "单选" 笼统合并为 25（12 grammar 0.5分 + 13 reading 2分），不利于二级模型分类。建议拆分为 `"12单选(6) + 8完形(8) + 1阅读匹配(6) + 3阅读理解B(6) + 3C(6) + 4D(8) + 4阅读表达(10) + 1作文(10)"` 或更精细。

4. **Q11 题干完全缺失** — yaml line 466: `stem: "We will send you an e-"`，OCR `page-02.txt` line 9 也同样残缺。这是 OCR 漏题（应为 "We will send you an e-mail when your application **___**"），需手补题干，否则学生看不懂。

5. **Q21 题干被噪声覆盖** — yaml line 679: `stem: "www."`，正确应为 "David 21." + David 自我介绍段落（OCR page-04.txt line 5-8）。当前 yaml 把 David 段当题干给了 Q22，错位。
   - 实际应：Q21 stem = David 段，Q22 stem = Alice 段（OCR 现也错配在 Q22）、Q23 stem = Mike 段 ✓。Q22 当前 stem 是 "Alice" 但把 "NEWS NEWS" 水印拼进去了。
   - 建议三题 stem 重排为 David/Alice/Mike 三段。

### P1（数据脏 / 影响学生体验）

6. **大量题干内嵌水印**（"北京高考在线" / "www.gaokzx.com" / "高" / "关注北京高考在线官方微信:京考一点通(微信号:bjgkzx)..."）。受影响：Q2, Q3, Q6, Q8, Q9, Q12, Q20, Q22, Q25, Q29, Q32, Q33, Q34（passage body）, Q38, 以及 Q20 solution、Q12 solution。需要全量 sanitize 一次。NOISE 黑名单已有但未覆盖单字"高""线""com""ww."等 OCR 噪声残片。

7. **Q33 答案 stem 尾巴混入下一段标题** — yaml line 957-962: D 选项 = "Liked by Others: Human Evolution's Driving Force\n\n第二部分\n\n本部分共5题，共20分..."，第二部分 section header 被错误粘到 Q33 D 选项末尾。english docx v1 这是 R2 已知 bug（"Q33 footer"），image 路线同款。

8. **passage body 全部带 OCR 水印与碎片**：
   - cloze passage line 18-20: `"Maya overslept. ... com friendship was perfect because they balanced each other out."` — `com` 水印插入断句。
   - reading_B body 含 `"fence They picked..."` — `fence` 是图注/水印残片
   - reading_C body 含 `"k2x Of course..."`
   - reading_D body 含 `"like button In 2018... 1 hr ago Like Comment photos..."` — 图片中"like button"和UI元素"1 hr ago Like Comment"被 OCR 抓入正文
   - reading_express body line 191-193: `"The key is to stay consistent(一贯的) without being (一贯的) without being burned out..."` — 重复 OCR
   - 所有 passage body 末尾或中段都有"关注北京高考在线..."

9. **Q34-37 阅读表达 answer 字段空** — `answer: ''` 而 `solution:` 有值。学生作答评分需要 answer 作为标准答案文本。应把 solution 拷到 answer，或把 answer/solution 分别用作 model_answer/explanation。

10. **Q38 作文 solution 范文 OCR 极烂**
    - line 1157: `"The results show that students interests are qite tdenced spl ofte ssests roa em"`（应为 "students' interests are quite balanced..."，OCR page-11.txt line 53 实际清晰，但 yaml 拷的是 page-10/12 残段）
    - 范文断行错乱、夹杂"在线""ok""北京"水印、`"关注北京高考在线官方微信:京考一点通(被瘩号:bjgkzx)"`（被瘩号 = 微信号 OCR 错）
    - 应直接采用 page-11.txt line 47-69 + page-12.txt 的清版本重组。

11. **Q12 stem 有错字** — `"-Do you know on the far side of the moon?"` 缺 "what's"。源题应是 "Do you know **when Chang'e-4 landed** on the far side of the moon?" — 实际填空内容才是 4 选项，stem 这样写没问题，但应去尾"高"水印。

12. **Q5 stem** 行首 `________` 是 OCR 把题号当作下划线读入。可保留作填空提示。OK。

### P2（轻微 / 风格）

13. **knowledge_points 偏粗**：12 道 cloze 全部 `词汇运用`/`词语运用` 二选一无差别；阅读理解 27 题中 9 题都是"信息筛选"。建议 enrich 重跑加细分（词义猜测 / 主旨大意 / 推理判断 / 段落作用 / 写作意图）。

14. **module 不一致**：reading_express Q34-36 `module: reading`，Q37 `module: writing`（作文小题）。Q38 `module: writing` ✓。但 Q21 `module: vocabulary`（信息匹配题）明显错配，应 `module: reading`。

15. **difficulty 偏 "基础" 过多**：阅读理解 13 题中 9 题"基础"4 题"中等"，与真实二模难度（6-7 基础 / 5-6 中等 / 1-2 难）有差。建议根据题型自动分配（词义猜测 / 主旨题 → 中等，事实细节 → 基础）。

16. **passages.cloze.body** 段内换行混乱（`\n\n` 和 OCR 噪声混进），阅读体验差。建议规范化为按原文段落分段。

17. **`_audits/` 之前未为西城二模英语创建审核**，本次为 R1 首次。建议 fix 后跑 R2 大模型审核 + R3 收敛，参照 docx 路线流程。

18. **passage_id 命名 OK**（cloze / reading_A-D / express），但 reading_A 是图片匹配题，passage body 仅有任务说明，3 道题 stem 各自是 David/Alice/Mike 自我介绍 — 当前 Q21 stem 被 "www." 覆盖（见 P0 #5）必须修。

19. **Q21 `knowledge_points: []` + `difficulty: ''` + `recommended_for: []`** — 因 stem 被识别为"www."这种短噪声后 enrich 阶段 skip 了，应 fix stem 后重 enrich。

20. **figures 目录健康** — `/figures/passage-reading_A-opt-A.png` 到 `opt-D.png` 4 张图存在 ✓，与 reading_A `_is_image_match: true` + `_src_page_img` 字段配套。OK。

---

## OVERALL: **NEEDS_FIX**

**核心阻塞**：
- 缺 1 题（Q15）→ 总题数 37 / 38，总分 59 / 60
- 元数据 4 字段全空/错（year, district, exam_type, duration_minutes）
- Q11 题干残缺、Q21 stem 错位、Q33 D 选项粘 section header
- 全 yaml 题干/passage/solution 残留 OCR 水印

**修复路径建议**（按优先级）：
1. **P0 立即**：手补 Q15（options B 从源 PNG 看一眼，answer=D；可用 qwen-vl-max 对 page-03 右侧选项区裁图复审）；补元数据 year=2026/district=西城/exam_type=模拟/duration_minutes=90；修 Q11 题干、Q21/22 stem 重排、Q33 D 截断。
2. **P1 批量**：扩展 english_image_paper.py 的 NOISE 黑名单加 "高/线/com/ww./fence/like button/k2x/m/1 hr ago Like Comment/被瘩号"等单字与碎片；passage body 跑一次 dedup（reading_express 重复行）；Q38 solution 改用 page-11.txt line 47-69 重抽。
3. **P2 后续**：重跑 enrich 加细分 KP、修 Q21 module 类型、difficulty 分布调整。
4. **流程建议**：image OCR 路线对 cloze 缺选项的兜底应改成 "保留题号 + answer_only + qc_status: needs_review"，不要直接 drop，至少保住计数和分值。
