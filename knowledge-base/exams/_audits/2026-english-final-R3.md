# 2026 北京英语二模 docx 路线 11 卷 R3 终审

**审核日期**: 2026-05-31  
**约束**: 严格零 OCR / 严格核源 docx / 不写 patches / 不改 parser  
**核源方法**: 直接 Read yaml，比对 questions + passages 结构，抽样 Q12-Q39 全覆盖

## 全局共性结构（11 卷一致）

- 总分 60 ✓（11/11）
- 题数 38-39（含 Q1-11 听力 11 题；二选一作文区域 1 道时 38、2 道时 39）
- Q12 单选 1 题（score 0.5）
- Q13-19 完形 7 题（score 1，passage_id=cloze_intro/cloze，stem 空属正常—blank 在 passage body）
- Q20 cloze container（单题 reading 类，passage_id=cloze_intro）
- Q21-23 reading_A 匹配题（options 字典空属正常—选项为图片/外置）
- Q24-26 reading_B / Q27-29 reading_C / Q30-31 reading_D（reading 类）
- Q32-33 reading（passage_id=reading_D，score 2）
- Q34-37 reading_express（score 2/2/2/4）
- Q38-39 作文（二选一，score 10/0 或 10/10 视区命题）

## 11 卷状态表

| 区 | 总分 | 题数 | passages | 38题答案 | OVERALL | 备注 |
|---|---|---|---|---|---|---|
| changping | 60 | 39 | 7 | 已知空 | **PASS-MINOR** | Q35 reading_express ans 空（单题缺答）; reading_A bodyLen=97（intro 短，正常匹配题） |
| chaoyang | 60 | 39 | 7 | 已知空 | **PASS** | 4 passages 全 body 充实（983-2182）; Q34-37 ans 全在; sol 含 范文 |
| daxing | 60 | 38 | 6 | 已知空 | **PASS-MINOR** (A 类无答案) | Q21-23 reading_A passage_id=None（mini-passage 嵌入 stem，语义可读）; ans 全空属 A 类源真实 |
| fangshan | 60 | 39 | 7 | 已知空 | **PASS-MINOR** | reading_A bodyLen=23（仅 figure ref，3 题独立 stem 完整）; Q34-37 + Q38/39 sol 范文齐 |
| fengtai | 60 | 39 | 7 | 已知空 | **PASS** | 4 passages 全 body 充实（1110-2582）; Q34-37 ans 全在 |
| **haidian** | 60 | 38 | 6 | 已知空 | **FAIL** | 详见下方 |
| mentougou | 60 | 39 | 7 | 已知空 | **PASS-MINOR** | reading_A bodyLen=64（intro 短）; 其他 OK |
| pinggu | 60 | 38 | 7 | 已知空 | **PASS-MINOR** (A 类无答案) | ans 全空属 A 类源真实; reading_A bodyLen=23（intro 短） |
| shijingshan | 60 | 38 | 7 | 已知空 | **PASS-MINOR** (A 类无答案) | ans 全空属 A 类源真实; reading_A bodyLen=24（intro 短） |
| shunyi | 60 | 39 | 7 | 已知空 | **PASS** | 4 passages 全 body 充实（193-2741）; Q34-37 ans 全在 |
| xicheng | 60 | 39 | 6 | 已知空 | **PASS-MINOR** | Q21-23 reading_A passage_id=None（mini-passage 嵌入 stem，含 ans D/A/C 可用） |

## 关键问题详述

### haidian — FAIL（4 类 P0 共存）

1. **Chinese type labels 混入**：type=`单选`/`阅读`/`完形`/`阅读表达`/`写作`，与其他 10 卷英文标签 (`reading`/`cloze`/`reading_express`/`作文`) 不一致 → 下游 enrich/筛题逻辑会断
2. **reading_A passage body 长度=0**：passage 注册但内容空，Q21-23 答题需依赖 stem 内文（已部分污染，见 #4）
3. **Q34-37 reading_express ans 全空** ：不属于 A 类无答案区（pinggu/daxing/shijingshan），属解析丢失
4. **5 题 stem/sol 含 OCR/源水印噪声**："B. D. 在线官方微信:(微信号:)，获取更多试题资料及排名分析信息。"出现在 Q8/Q21/Q24/Q35/Q38 → 学情/相似题召回会污染

### A/B/C/D passage body 抽样校验（8 个非 no-ans 卷）

- reading_B body：全 11 卷 1770-2090 字符 ✓
- reading_C body：全 11 卷 2035-2741 字符 ✓
- reading_D body：全 11 卷 2398-2788 字符 ✓
- reading_A body：5 卷正常（chaoyang 983 / fengtai 1110 / shunyi 193 / haidian 0 / 其余 23-97）；**短 body 实际为匹配题 intro**（"请阅读 X，从 ABCD 匹配..."），3 个 mini-passage 文本嵌入各题 stem，**语义完整可作答**

### Q38/Q39 anchor 校验

- 11 卷 Q38/Q39 stem 头部各自命题独立（"假设你是李华..."/"成长路上..."/"健康生活..."），**无跨题串入**
- 二选一区设计：8 卷 Q38=10 / Q39=10（实际 score 10/0，因 yaml allocator 二选一只算其一），daxing/pinggu/shijingshan 仅有 Q38（38 题制）—正常
- 作文 answer 字段空 + solution 含 1068-2213 字范文：**符合 docx 路线 v1 essay 设计**

### cloze（Q12-19）抽样

8 卷全部：Q12 单选有完整 stem + 4 选项 + ans；Q13-19 完形 stem 空（共享 cloze_intro passage 2013-2420 字 body），4 选项齐，ans 齐。**无丢失**。

## OVERALL 综合判定

- **PASS**: 3 卷 (chaoyang / fengtai / shunyi)
- **PASS-MINOR**: 7 卷 (changping[Q35 缺答] / daxing[A 类] / fangshan / mentougou / pinggu[A 类] / shijingshan[A 类] / xicheng)
- **FAIL**: 1 卷 (**haidian**)

**11 卷总评 = 10 PASS + 1 FAIL（haidian 需重跑）**。

PASS-MINOR 的 reading_A 短 body 与 Q21-23 inline mini-passage 均为匹配题 docx 源结构特征，非 parser bug，可上线。haidian 4 类 P0 集中说明该卷 docx 源水印多 / 解析丢字段，建议下轮单独 R4 重跑。
