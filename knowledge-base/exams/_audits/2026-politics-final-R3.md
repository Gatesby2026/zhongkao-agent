# 2026 北京道法二模 docx 路线 R3 终审

**范围**：6 卷 yaml — changping / chaoyang / daxing / haidian / shunyi / xicheng
**审核**：分值精度 + 内容完整性 + 源 docx 抽样比对（零 OCR）
**结论**：6/6 CLEAN，**统一 OVERALL = PASS**

---

## 一、结构与分值

| 区 | 题数 | 总分 | judge | 单选 | 材料 | 作文 | empty_ans | empty_sol |
|---|---|---|---|---|---|---|---|---|
| changping | 25 | **70** | 10 | 10 | 3 | 2 | 5 (Q21-25) | 0 |
| chaoyang  | 25 | **70** | 10 | 10 | 3 | 2 | 5 (Q21-25) | 0 |
| daxing    | 25 | **70** | 10 | 10 | 4 | 1 | 5 (Q21-25) | 0 |
| haidian   | 25 | **70** | 10 | 10 | 4 | 1 | 5 (Q21-25) | 0 |
| shunyi    | 25 | **70** | 10 | 10 | 2 | 3 | 25 (A 类源) | 25 (A 类源) |
| xicheng   | 25 | **70** | 10 | 10 | 4 | 1 | 5 (Q21-25) | 0 |

- 6 卷全 70 分精准命中（10 判断×1 + 10 单选×2 + 主观 40 = 70）✓
- 5 卷的 5 空 ans 全部落在 Q21-25 主观题（材料/作文），合规 ✓
- shunyi 25 空 ans/sol 与源 docx 一致（raw.md 全无 `【答案】` 段）→ A 类源，合规 ✓

## 二、内容质量抽样

### 判断题 answer 文本（changping/chaoyang/xicheng/daxing/haidian）
- 5 卷 judge ans set = `{'正确', '错误'}`，无英文/无空值 ✓
- changping Q1-Q8 逐条比对源 raw.md（`正确/正确/正确/正确/错误/正确/错误/正确`）100% 一致 ✓

### 单选题 options
- 5 卷 single ans set = `{'A','B','C','D'}` 全四选项分布
- options 全部为 dict，键 `>= {A,B,C,D}` ✓
- 抽样 changping Q11：`{A:'制造强国', B:'教育强国', C:'交通强国', D:'体育强国'} ans=B`，options 非占位 ✓

### 材料分析 body
- changping Q21 stem_len=339；chaoyang Q21 stem_len=354（含 markdown 表格）；xicheng Q21 stem_len=429
- daxing/haidian 材料题 stem_min ≥ 102/194；shunyi material stem_min=64（Q21 短但完整：`感人画面 + image + "暖在何处"` 设问完整）
- 4 卷材料题保留 `| ... |` markdown 表格结构，含 `figures/imageN.png` 引用 ✓

### chaoyang Q25（R2 patch 重点）
- type=材料分析 score=8 stem_len=635
- 完整含 "民主守护民生 破解井盖难题" 三层 table（人大代表/政协委员/社区居委会案例）+ 两个设问 "(1) 述评 / (2) 设计内容二"
- solution=346 chars，含示例答案 + 详解（KP：人大制度/多党合作/基层自治/政府宗旨/全过程人民民主）
- **R2 patch 内容实质性、非占位 ✓**

### shunyi 源数据校验
- raw.md 全文无 `【答案】`/`【详解】` 段 → 与 yaml empty_ans=25 empty_sol=25 完全一致
- judge Q1 yaml stem 与 raw.md 行对应（"中国共产党领导是中国特色社会主义最本质的特征"）✓
- 单选 Q11 options 1×4 排版完整 → yaml dict 4 key ✓

## 三、跨卷一致性
- 6 卷 100% 25 题 / 70 分 / 70 分钟（开卷）
- type 分布合理：10 judge + 10 单选 + 5 主观（材料/作文配比 区内自洽）
- module 字段全部 `politics`；options 全部 dict 结构

## 四、OVERALL

**6/6 PASS**：分值精准、内容完整、源数据一致、type/options/answer 结构整齐。
shunyi 的 "25 空" 为源 docx A 类（无答案），非 parser bug。
chaoyang Q25 R2 patch 实质性补全，可直接进入 enrich 阶段。

**建议下一步**：5 卷（除 shunyi）可直接 enrich KP；shunyi 走人工/LLM 兜底答案路径或保留 A 类标记。
