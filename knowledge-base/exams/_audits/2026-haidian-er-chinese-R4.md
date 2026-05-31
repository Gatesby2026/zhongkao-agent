# 2026 北京海淀区中考二模 语文 yaml R4 终审

**对象**：`knowledge-base/exams/mock/chinese/beijing/2026-haidian-er.yaml`
**真值源**：`gaokzx-downloads/2026-ermu-chinese/haidian_chinese.pdf` p10–p11（文本层）

## OVERALL：PASS-MINOR

答案字母 / solution 文本 / 总分 100 / 题数 27 全部正确，PDF→patches 转录质量极高。但**单题分值**与 PDF "（N分）" 普遍不符（虽总和恰好 100，属人工拆分误差），另有 1 处缺选项需补。

---

## P0（必修，影响作答判定）

- **Q3**：yaml options 仅 A/B/C 三项，stem 写"下面…不正确的一项"。PDF 原卷应有 D 项（"街道的建筑材料"或类似），需补 D。**缺项会让答题卡选 D 无法匹配。**

## P1（分值口径错位，每空/每问标错；总分仍=100）

PDF 明示分值 vs yaml score：
- Q8=2（yaml=3）；Q9=2（yaml=1）；Q10=1 ✓
- Q11=2（yaml=3）；Q12=3（yaml=2）
- Q13=2（yaml=3）；Q15=3（yaml=2）
- Q17=2（yaml=3）；Q19=3（yaml=2）
- Q20=2（yaml=5）；Q21=3（yaml=2）；Q23=4（yaml=2）
- Q24=2（yaml=3）；Q26=3（yaml=2）

14 题分值错，stem 括号 "（2分）/（3分）" 已写对，仅 `score:` 字段错。建议按 PDF 改 score。

## P2（cosmetic）

- **Q15 type="古诗内容理解"**：其他默写/填空题统一用 "主观填空"，Q15 应改 type=主观填空（KP 自带"默写"即可）。
- **Q16 缺 passage_id**：名著独立题无 passage 正常，但与其他题字段不一致；可加 `passage_id: ''` 或忽略。
- **Q10 stem 含《渔家傲》正文+作者**：本属 passage 范畴被并入 stem，Q11/Q12 共用此文。不影响作答但 passage 切分粒度偏粗。
- **Q19 stem 含《开江的日子》全文 + Q23 stem 含第三篇议论文全文**：现代文阅读三篇分别塞进了 Q19/Q23 的 stem，应放入 modern_intro 或拆 3 个 passage。不影响答题判定。

无水印 "高kzx" / "ww." 残留。无明显 OCR 错字。

---

## 待修清单（精简）

1. Q3 补 D 项（核 PDF p1-2 题面）
2. Q8/9/11/12/13/15/17/19/20/21/23/24/26 score 字段按 PDF 修正
3. Q15 type 改 主观填空
4. （可选）现代文 passage 重构，移出 Q19/Q23 stem
