# 2026 朝阳二模 chinese R4 终审报告

**对象**：`mock/chinese/beijing/2026-chaoyang-er.yaml`
**核源**：`/tmp/chaoyang_pdf/p11-14.jpg`（PDF 答案页）
**OVERALL**：**FAIL**（1 个 P0 答案错 + 系统性 P1 score 字段错配）

---

## P0（必修，影响判分）

- **Q17 answer 字母错**：PDF p12 明示 "17. 答案：甲"，但 yaml `answer: A`。Q17 选项是 【甲】【乙】【丙】（见 stem line 482-487 无 A/B/C/D），必须改为 `answer: 甲`，否则学生答题卡匹配全错。

## P1（结构错，不影响最终判分总分但单题分值不对）

- **per-question `score` 字段系统性错配**（13 题），section 总分对但单题分布错，会污染小分报告：
  - Q1: yaml=1 / PDF=2  | Q2: yaml=3 / PDF=2
  - Q8: yaml=2 / PDF=1  | Q10: yaml=1 / PDF=2
  - Q11: yaml=3 / PDF=2 | Q12: yaml=2 / PDF=3
  - Q13: yaml=3 / PDF=2 | Q15: yaml=2 / PDF=3
  - Q17: yaml=3 / PDF=2 | Q19: yaml=2 / PDF=3
  - Q20: yaml=5 / PDF=2 | Q22: yaml=2 / PDF=3 | Q23: yaml=2 / PDF=4
  - Q24: yaml=3 / PDF=2 | Q25: yaml=2 / PDF=3
  - （stem 字符串里 "(2分)/(3分)" 正确，仅 score 字段错）

## P2（提示性，可保留）

- **Q22 示例三 "瞟"**：PDF p13 答案确实写 "瞟"，但 passage【丙】加点词是 "躺坐/遮"（yaml line 605），属源 PDF 自身印刷瑕疵，yaml 已忠实复制，建议补 qc_note。
- **passage / stem 水印 "京高考/gaokzx"**：扫 yaml 全文未发现，干净 ✓。
- 单选答案 Q1/2/3/4/5/13/14/18/26 全部正确 ✓；Q15/Q19/Q20 主观题文本与 PDF 字字吻合 ✓；Q10/Q16/Q22 多示例齐 ✓；section 总分 14+16+5+25+40=100 ✓。

## 待修清单（不重写 yaml）

1. Q17 `answer: A` → `answer: 甲`
2. 13 题 `score` 字段按 PDF 修正（清单见 P1）
3. Q22 加 qc_note 标注 PDF 源 "瞟" vs passage "躺坐" 不一致
