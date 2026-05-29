# 2026 北京海淀英语二模 yaml 审核报告（R2）

- yaml: `knowledge-base/exams/mock/english/beijing/2026-haidian-er.yaml`（38 题 / 60 分 / nr=0）
- patches: `knowledge-base/exams/_patches/english/2026-haidian-er.yaml`（R1 已落盘，未 enrich）
- 源 PDF: `knowledge-original/gaokzx-downloads/2026-ermu-english/haidian_english.pdf`
- 路线：image OCR（dual GeneralAccurate+Basic）+ Claude 兜底
- 复审范围：R1 patch 真值核 + R1 未修 P1 + passage 完整性 + 38 道全题扫

---

## 1. R1 Patches 真值核对（逐条）

| Patch | 严重 | 真值核对 | 结论 |
|---|---|---|---|
| **Q1.solution = "C"** | P0 | yaml.Q1 stem "My mother loves animals." options C=She；语义匹配，原 sol "C2.D" 为下题串扰 | **TRUE** |
| **Q10 answer/sol = "C"** | P0 | stem "My sister ___ many books on robots since she visited the science museum"，since + present perfect → "has read" = C | **TRUE** |
| **Q11.solution = "C"** | P0 | "Chinese festivals ___ by more and more people"，被动语态 + 现在时 → are celebrated = C | **TRUE** |
| **Q13.solution = "C"** | P0 | cloze#13 答案 = "real"（C），与"expecting to solve a(n) ___ mystery"语义吻合 | **TRUE** |
| **Q21/22/23 type → reading** | P0 | image-match 子题归 reading 模块（has_image_options=true 已存），fix 后 structure 自然回正 | **TRUE** |
| **Q31 KP/module → reading** | P0 | stem "Which of the following is an example of being reasonable?" 属推理判断 reading；原 KP "vocabulary" 错 | **TRUE** |
| **Q33.options 清 footer** | P0 | A-D 四选项均为标题候选（What/Where/Why/How…），原 D 选项被粘"第二部分"footer，patch 后干净 | **TRUE** |
| **Q37.solution = "略"** | P0 | yaml.Q37 sol 实际 130 行污染（吸 Q38 范文 + okzx.com + 平台简介）；Q37 系开放题应留"略" | **TRUE** |
| **Q38.solution 范文** | P0 | **逐句核对** `tencent-cache/general/page-10.txt` line 49-60 = patch 中"题目1"全文 + line 1-7 = "题目2"全文；OCR 原文 100% 来自 page-10/11，非凭空生成 | **TRUE，零幻觉** |

**R1 9 处 P0 patch 全部真值核通过**。

---

## 2. R1 未修 P0/P1（R2 新增清单）

### P0（强烈建议补 patch）

**P0-A：水印 51 处全卷穿插破坏 LLM 阅读**
51 处 watermark 命中（grep `kzx|gaokzx|京考|高考在线|gaww` 计数）。其中**语义破坏级 5 处**：

| 位置 | 内容 | 问题 |
|---|---|---|
| cloze body line 20 | `Who ate all the kzx.com chocolates?!` | "kzx.com"插入故事对话，污染 LLM 推断 |
| reading_C body line 122 | `research so far 关注北京高考在线…(微信号:bjgkzx)…points to the hidden health problems` | 一句话被水印切断，LLM 无法连贯阅读 |
| reading_D body line 168 | `we see the 北京高考在线 world through different eyes` | "北京高考在线"插入句中破坏语义 |
| reading_D body line 149 | `even law experts struggle to 关注北京高考在线…define (定义) it` | "struggle to define"被水印强插中间 |
| Q9.stem line 404 | `w.gaokzx.com ___ Sorry, Mum.` | 水印混入对话起首 |

建议 patch 加全局 sed：所有 passage.body + 含水印的 question.stem/options 统一过 `re.sub(r'(关注北京高考在线官方微信:京考一点通\s*\(?微信号:bjgkzx\)?，?获取更多试题资料及排名分析信息。?|w*\.?gaokzx\.com|北京"?高考在线|京高考在线|okzx\.com|kzx\.com|(微信号:bjgkzx))', '', body)`。

**P0-B：reading_C body line 104 句首漏词 + line 115 图说碎片**
- line 104: `Many of us feel a sudden of anger` — 源应为 `a sudden burst of anger` 或 `a sudden surge of anger`，漏一名词。OCR 缺译。
- line 115: `A lever No rewards!` 与 line 117 `slow Why some adults…` — 这是源 PDF 中实验示意图（lever 图 + slow elevator 图）的图说文字被 OCR 误并入正文。R1 未标记。**建议清理 line 115-117 中前缀 `slow ` 移到正文段**：`A lever No rewards!` 整行删；`slow Why` → `Why`。

**P0-C：Q21 stem 串入选项标签 + 水印**
yaml.Q21 stem 起首 `B. D. 关注北京高考在线…` — "B. D."是上一题选项残留 + 水印一段。R1 已 fix type，但 stem 仍带 `B. D. + 水印`，导致学生题面阅读混乱。建议 patch：

```yaml
21:
  type: reading
  stem: "I wore a traditional Chinese costume and my mom styled my hair into a bun with a jade pin. When I touched it gently, I felt a warm pride. This special day helped me stay connected to my cultural roots. (Lin Wei)"
```

### P1（非阻塞但应清）

- **Q8/9/22/24/35/37 stem 末尾粘 footer**：6 处 `关注北京高考在线官方微信:京考一点通…` 行末残留，建议批量截掉行末水印。
- **Q11.solution 已 patch 为 "C"** 但 line 457-459 原值含 `北京"高考在线 / www.gaokzx.com`，patch 覆盖后 OK。
- **选项末尾换行 footer**：Q2.D / Q8.D / Q17.D / Q18.D / Q24.B / Q24.D / Q28.B / Q28.D 等多处单选选项末尾粘 `北京高考在线` 或 `www.gaokzx.com`，影响选项可读性。建议 patch 对所有 options.X 过 strip + sub。
- **Q12.stem line 476** `com` 单独成行 — 水印残。
- **Q37.stem line 1045-1047** `高考 / okzx.com / reasons)` — 水印插入题干，建议清。

---

## 3. Passage 完整性核对

| passage | q_range | body 状况 | 评估 |
|---|---|---|---|
| **cloze** | 13-20 | 全文 8 空连贯，1 处水印插入（`kzx.com chocolates`） | **P0 水印** |
| **reading_A** | 21-23 | body="" + `_is_image_match: true` + `_src_page_img` | OK（图片题正常） |
| **reading_B** | 24-26 | kite 故事 5 段完整 + 2 处选项末 footer | **P1** |
| **reading_C** | 27-29 | 5 段完整 + **P0：line 104 漏 burst/surge + line 115-117 图说碎片 + line 122 水印切句** | **P0** |
| **reading_D** | 30-33 | 5 段完整 + **P0：line 149/168 水印插入语义** + line 171 末尾 `www.gaokzx.com` | **P0** |
| **express** | 34-37 | Peer Support 5 段完整无水印，干净 | **OK** |

---

## 4. 数字汇总

- R1 patch 9 处 P0 真值率 **9/9 = 100%**（含 Q38 范文逐句核对原 OCR）
- R2 新增 **P0：3 类**（水印批量、reading_C 漏词+图说、Q21 stem 残）；**P1：~15 处**（选项/题干尾 footer）
- 卷面分布：12 单选(6) + 8 cloze(8) + 13 reading(26) + 4 reading_express(10) + 1 作文(10) = **60** ✓

---

## OVERALL: **NEEDS_FIX**

**R1 patches 真值零幻觉**（Q38 范文 100% 来自源 OCR page-10/11，非编造），可放行 enrich。

但 R2 新发现 **3 类 P0**：
1. **水印 51 处穿插**，其中 5 处语义破坏级（cloze "kzx.com chocolates" / reading_C "research so far 关注…points to" / reading_D 2 处 / Q9 "w.gaokzx.com ___ Sorry"）→ 建议加全局正则清理 patch（一条 `re.sub` 可覆盖所有 passage.body + question.stem/options）。
2. **reading_C body** line 104 缺名词（`a sudden of anger`）+ line 115-117 图说碎片串正文 → 建议手 patch passage body。
3. **Q21 stem** "B. D. 关注北京…"残留 → patch 中已 fix type 但未清 stem。

**enrich 前必须再过 R2 patch**，否则学情诊断时 LLM 阅读 reading_C/D 会被水印干扰，作文范文（Q38）虽 OK 但 Q37 stem 仍带"高考/okzx.com"碎片。**总分/题数/答案结构层面 0 错**；passage 与水印为剩余主战场。
