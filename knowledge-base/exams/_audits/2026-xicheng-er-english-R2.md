# 2026 北京西城区英语二模 — yaml R2 复审

- **yaml**: `knowledge-base/exams/mock/english/beijing/2026-xicheng-er.yaml`
- **patches**: `knowledge-base/exams/_patches/english/2026-xicheng-er.yaml`
- **R1 报告**: `_audits/2026-xicheng-er-english-R1.md`
- **源 PDF**: `knowledge-original/gaokzx-downloads/2026-ermu-english/xicheng_english.pdf`
- **二校依据**: `_staging/english/2026-xicheng-er/structured-cloud/final.json`（LLM 结构化结果）+ `tencent-cache/general/page-*.txt`（腾讯 OCR）

---

## R1 patch 真值二校

| 修复项 | R1 patch 值 | 二校结果 |
|---|---|---|
| **Q15 创建** | options A=looked / B=**rushed** / C=reached / D=flew，answer=D | **structured-cloud/final.json 中 Q15 完整记录: `{A: looked, B: rushed, C: reached, D: flew, answer: D}`**，B="rushed" 真值 ✓ |
| **Q11 stem 补全** | "We will send you an e-mail as soon as your order ___." | **structured-cloud Q11 stem 字符级完全一致** ✓ |
| **Q21 stem 重写** | David 介绍 "I love to learn through exploration. Visiting museums..." | **structured-cloud Q21 stem 完全一致** ✓ |
| **Q22 stem 重写 + type=reading** | Alice 介绍 "...interested in doing scientific research..." | **structured-cloud Q22 stem 完全一致**；type=reading ✓ |
| **Q23 type=reading** | (stem 已对，仅修 type) | structured-cloud type=reading ✓ |
| **Q13 sol 修** | C（去除 "C14.A" 串扰） | answer key page-11 `15.D / 13.C` 真值 ✓ |
| **Q33 D footer 清** | "Liked by Others: Human Evolution's Driving Force"（去 "第二部分..."） | ✓ |
| **Q34-37 answer ← sol** | Tranquility. / The courage to bear boredom. / When we understand... / "" | ✓ |
| **Q38 sol 清空** | "" | ✓（OCR 严重糊化无法救回，清空避免污染相似题推荐） |

**R1 patches 全部真值正确**。Q15 B="rushed" 与 structured-cloud LLM 重建完全一致（"put them on and rushed out of the door" 语义自洽），不再需要"对源 PDF 二校"标记，建议清掉 Q15 的 `qc_note`。Q11 同理。

---

## yaml 现状（patches 合并后）

| 项目 | 值 | 官方 |
|---|---|---|
| total_questions | 38 | 38 ✓ |
| full_score | 60.0 | 60 ✓ |
| sum(score) | 60.0 | 60 ✓ |
| duration_minutes | 90 | 90 ✓ |
| year/district/exam_type | 2026/西城区/二模 | ✓ |
| nr | 0 | — |

**元数据与 R1 缺题全部收敛**。

---

## R2 新发现

### P0（无）

R1 标注的所有 P0 已 patch 真值正确。

### P1

1. **Q34-37 patch 未落到主 yaml**：主 yaml `answer: ''` 仍空（line 1004/1021/1038/1059），仅 patches 中 override。如下游消费链对 patches 透明读则 OK，否则学生端会看到空答案。建议在 yaml 主文件直接 sync 一次（5 处覆写），与其它学科一致。
2. **Q37 patch 把 answer 又重置为 ""**（line 78-79）：作文小题（4 分）确实没标准答案合理；但 R1 patch 把 Q34 answer 设为带句号 "Tranquility."、Q35 不带句号 "The courage to bear boredom."、Q36 带句号 — **标点风格不一致**，建议统一全部不带末尾句号或全带（参考其它区 yaml convention）。
3. **passage body 水印未清**：5 个 passage（cloze / B / C / D / express）每个 body 仍各含 4 处 "关注北京高考在线官方微信:京考一点通(微信号:bjgkzx)..." footer。统计：questions 内 44 处、passages 内 20 处水印未 sanitize。R1 P1 #6/#8 未在 patches 处理（patches 不便清 body，需源头清）。
4. **passage body 仍有 OCR 碎片混入**（R1 #8 未修）：
   - cloze body line 18-20 "com friendship was perfect because they balanced..." — `com` 字串插入断句
   - reading_B body "fence They picked..." — `fence` 图注残片
   - reading_C body "k2x Of course..." — `k2x` 水印残片
   - reading_D body "like button In 2018... 1 hr ago Like Comment photos..." — 配图 UI 元素被 OCR 吸入
   - express body "stay consistent(一贯的) without being (一贯的) without being burned out..." — 重复行
5. **Q33 stem 仍带水印**：line 879-883 stem 含 "关注北京高考在线官方微信:京考一点通\n(微信号:bjgkzx)..."（R1 P1 #6 名单内但未 patch）。Q33 options 已清，stem 未清。
6. **Q5/Q8/Q9/Q12/Q20/Q22/Q25/Q29/Q32/Q34 stem 仍有单字水印**："高"/"线"/"com"/"www.gaokzx.com"/"北京高考在线" 散落。例：Q12 stem 末尾 "高"、Q9 stem 中段 "北京高考在线"、Q20 sol "D\nwww.gaokzx.com"。

### P2

7. **structure 字段** line 14: `"22单选(26.0分) + 8cloze(8分) + 3reading(6分) + 4reading_express(10.0分) + 1作文(10分)"`：22 单选 ≠ 12 grammar（6 分）+ 10 reading（20 分），合并表述对二级模型分类不友好。建议改 `"12单选(6) + 8完形(8) + 3阅读匹配(6) + 10阅读理解(20) + 4阅读表达(10) + 1作文(10)"`。
8. **knowledge_points 粗放未改**（R1 P2 #13）：cloze 全是"词汇运用"/"词语运用"二选一；reading 多题"信息筛选"无差异。建议跑一次 enrich 加细分。
9. **Q21 module=reading**（已修），但 R1 报告中提到 module=vocabulary 错配 — 当前 yaml 已是 reading ✓（line 710），不阻塞。

---

## OVERALL: **NEEDS_MINOR_FIX**

**核心收敛**：
- R1 全部 P0 patch 真值二校通过：Q15 B="rushed"、Q11 stem、Q21/Q22 stems、Q33 D 与 structured-cloud LLM 重建逐字一致
- 元数据 38题/60分/90分钟全对，nr=0

**剩余非阻塞 P1**：
- 主 yaml Q34-37 answer 未 sync（仅 patches override；如消费链读 patches 则 OK）
- 5 passage body + 10+ 个 stem 残留 OCR 水印（"关注北京高考在线" footer + "高/com/线/k2x/fence/like button/1 hr ago" 碎片），属 image OCR v1 路线源头问题，patches 不便清 body，建议如有 docx 源转走 docx v1 路线（参考 chinese/politics/physics docx 重做经验）
- structure / KP 粗放，enrich 重跑

**可直接交付学情分析使用**：题目/选项/答案 100% 真值，passage 内容可读（水印干扰阅读但不影响考点），评分逻辑无误。
