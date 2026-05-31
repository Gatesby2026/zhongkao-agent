# 2026 北京丰台二模 chinese R4 终审

**OVERALL: FAIL** — 单选答案全对，但 parser 把答案 docx 的「sub-section 标题」「评分标准」整段粘到上一题 sol；逐题分值也多处错配（系统性 score allocator bug）。

---

## P0 — sol 末尾粘 sub-section / 评分标准（dual-docx merge 切题未拦截）

| Q | 污染内容 | 应为 |
|---|---|---|
| Q10 | sol 末尾 `（二）《游山西村》（7分）` | 仅 `长风破浪会有时，直挂云帆济沧海` |
| Q12 | sol 末尾 `（三）《爱莲说》（7分）` | 截掉 sub-header |
| Q19 | sol 末尾 `（二）《富春江上》（10分）` | 截掉 sub-header |
| Q26 | sol 后整段粘「评分标准 一类卷…五类卷…」5 个评分梯队 | 仅保留至 `…修身类书籍是首选。` |
| Q27 (作文) | sol = `![image1.png]![image2.png]丰台区2026年九年级…语文试卷答案`（答案 docx 首图+大标题） | 应为 Q26 之后被吞掉的「评分标准」5 档 |

→ root cause：Q26 把作文评分标准吃了；Q27 把答案 docx 第 1-3 行（图+大标题）吃了。merge 时缺「sub-header line `（X）xxx（N分）` 不算 sol」与「答案 docx 文件头不算 sol」过滤。

## P0 — 分值与源不符（9 题）

源真值 vs yaml：
- Q10: 2 vs 1
- Q11: 3 vs 4
- Q12: 4 vs 3
- Q20: 2 vs 4
- Q21: 3 vs 2
- Q23: 3 vs 2
- Q24: 2 vs 3
- Q26: 3 vs 2

总分 100 仅因每段(N分)封顶兜底；section 内题间分配错。需读 stem "(N分)" 直接写入，不要再用 score allocator 二次估算。

## P1
- Q8 stem `，江春入旧年` 缺首空（应 `___，江春入旧年`）。raw.md 是 `               ，` 全角空白，python-docx 抽取丢空白 → 应加占位 `___`。
- Q16 缺 `passage_id`（名著独立，可空但应显式）。

## P2
- Q3 KP `字音/字形/成语运用/病句/词语运用/连贯/书写` 一题挂 7 个 KP，明显是默认大杂烩，未细化为「成语运用」。
- Q5 KP 标为「字音/字形」应为「修辞手法」。
- Q13 KP 标为「古诗文默写」应为「文言文实词」。

---

**结论**：parser dual-docx merge 收尾过滤不全 + score allocator 在 sub-section 内分配错。修 5 处 sol 截尾 + 8 处 score 后即可 PASS。
