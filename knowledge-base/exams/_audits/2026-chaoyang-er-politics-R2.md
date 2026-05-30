# 2026 朝阳区道法二模 yaml R2 复审（docx 路线）

- yaml: `knowledge-base/exams/mock/politics/beijing/2026-chaoyang-er.yaml`
- final.json: `knowledge-base/exams/_staging/politics/2026-chaoyang-er/structured-cloud/final.json`
- patches: `knowledge-base/exams/_patches/politics/2026-chaoyang-er.yaml`
- 源 docx: `knowledge-original/zxxk-downloads/2026-ermu-politics/chaoyang_politics.zip`
  （含解析版 + 原卷版 2 份 .docx）
- 真值参照：image OCR R3 commit `afb5861c` 的 25 题/70 分版本
- R1: `_audits/2026-chaoyang-er-politics-R1.md`（指出"docx baseline 缺 Q25"）

## 第一步：源 docx 现场勘验

unzip + `word/document.xml` 全文 grep `2[3-6][\.．、]`：

| docx | 出现的题号 | 末题内容 |
|---|---|---|
| 解析版 | 21./22./23./24. | Q24 红旗渠/平陆运河"感悟传承 接力奋斗" |
| 原卷版 | 21./22./23./24. | 同上 |

**docx 真缺独立 Q25 题号** — 不是 parser 漏识别。

进一步勘验 Q22 段内容（解析版）：`22.` 题号下文本依次为：
1. 肖像权题完整材料（"镜头有框…"+"法律链接 第一千零一十八条…民法典》"）
2. **直接拼接** 井盖民主题完整材料（"内容一 井盖虽小…学生分享"）
3. 仅 1 个设问块（"（1）结合材料…对内容一的报道进行述评。（2）请你完成内容二的设计…"）
4. 【答案】只有井盖（1）（2）小问示例，**完全无肖像权题的设问与答案**

→ 源 docx 把 image OCR 真值的 **Q22(肖像权 6分) + Q23(井盖 8分)** 两题错误合并到 "22." 题号下，**漏抄肖像权设问与答案**，并少 1 个题号导致结尾 Q24（红旗渠）实际对应真值 Q25。

对应当前 docx yaml：
- yaml Q22 (6分) stem = 肖像权 + 井盖粘合；solution = 井盖答案；肖像权设问/答案丢失
- yaml Q23 (8分) = 真值 Q24（琉璃厂4地标）
- yaml Q24 (8分) = 真值 Q25（红旗渠，**应 10 分**）
- 总计 24 题/60 分（应 25 题/70 分）

## 第二步：R2 fix 方案

走 patches 兜底，不依赖 parser 重跑：

| Patch 项 | 操作 | 真值来源 |
|---|---|---|
| `passages.material_intro.q_range` | [21,24] → [21,25] | 题数恢复 |
| `Q22.stem` | 重写为纯肖像权材料 + 设问（"对'蹭拍者'的言行进行评析，并提出合理建议"） | image OCR R3 真值 |
| `Q22.solution` | 重写为肖像权评析示例 + 详解 | image OCR R3 真值 |
| `Q22.score` | 6（不变） | — |
| `Q24.score` | 8 → 10 | image OCR R3 真值 + 7×5+(8+6+8+8+10)=70 算式 |
| `Q25` create | type=材料分析 score=8，stem/solution 用源 docx Q22 末尾粘进来的真实井盖材料 + 真实井盖答案（含评分细则） | docx 原文 + image OCR R3 |

注：**保留** docx yaml Q23/Q24 当前 stem 不动（琉璃厂/红旗渠内容真实，只是题号语义偏移一位）；Q25 新增在末尾，不能在中部插入（patch applier 不支持重排）。题号顺序与原卷不完全一致（真值 Q23=井盖），但 25 题/70 分/题号连续/内容完整/分值正确。

## R2 实际改动

- `_patches/politics/2026-chaoyang-er.yaml`：+ `passages.material_intro` 块、Q22 加 stem/solution、Q24 score 8→10、Q25 完整 create 块
- `mock/politics/beijing/2026-chaoyang-er.yaml`：questions 25 项 / full_score 70 / total_questions 25 / structure "10判断+10单选+3材料分析(22)+2作文(18)" / passages.q_range [21,25]
- `_staging/politics/2026-chaoyang-er/structured-cloud/final.json`：questions 25 项 / answers 25 项 / full_score 70 / passages.q_range [21,25]

## 验收

```
total: 25 score: 70 duration: 70
structure: 10判断(10分) + 10单选(20分) + 3材料分析(22分) + 2作文(18分)
passages: q_range=[21,25]
Q22 type=材料分析 score=6 stem=281 sol=215 ans=''
Q24 type=作文    score=10 stem=592 sol=403 ans=''
Q25 type=材料分析 score=8 stem=635 sol=284 ans=''  ← 新增
```

## 残留 / 后续建议

- **P1（KP）**：Q25 由 patches 写入未经 enrich，KP 用手工默认值 `[公民参与, 基层群众自治, 人民代表大会制度, 全过程人民民主]`；下轮重跑 enrich 可自动覆盖更精细的 8 模块 KP。
- **P2（题号语义）**：原卷真实题号 Q22=肖像权 / Q23=井盖 / Q24=琉璃厂 / Q25=红旗渠；当前 yaml Q22=肖像权 / Q23=琉璃厂 / Q24=红旗渠 / Q25=井盖，题号位移不影响内容正确性，对学生答题影响为零（材料题独立成题）。如需精确还原原卷顺序，需 parser 层支持 patch 重排（当前 `_apply_patches` 仅支持末尾插入）。
- **P3（parser 兜底）**：politics_docx_paper.py 可加 "粘合题号探测" — 同一题号下出现两套 `（1）…（2）…` 设问或两套独立"材料"标题时告警，本案可被预先捕获。

## OVERALL: **CLEAN**（R2 P0 全修，3 条残留全为 P1/P2/P3 非阻塞）
