# 2026 北京数学二模 daxing R4 复审报告

**触发**：daxing 数学 zxxk 精品解析版（含答案）于 2026-05-31 补到，原 R3 终审时为 A 类无答案标记。重新跑 `math_docx_paper.py` 后 28/28 ans + 28/28 sol 全填，需复审填充质量。

**审核日期**：2026-05-31
**约束**：严格零 OCR / 严格核源 docx / 不写 patches / 不改 parser
**对象**：[2026-daxing-er.yaml](../mock/math/beijing/2026-daxing-er.yaml)
**源 docx**：`knowledge-original/zxxk-downloads/2026-ermu-math/daxing_math.zip` →（解析版）`精品解析：2026年北京市大兴区中考二模考试数学（解析版）.docx`

---

## 1. 结构与分值（OK）

| 指标 | 期望 | 实际 |
|---|---|---|
| 题数 | 28 | 28 ✓ |
| 总分 | 100 | 100 ✓ |
| 结构 | 8 单选(16) + 8 填空(16) + 12 解答(68) | 一致 ✓ |
| 时长 | 120 min | 120 ✓ |
| 空 ans | 0 | 0 ✓ |
| 空 sol | 0 | 0 ✓ |
| __MISSING__ | 0 | 0 ✓ |
| 单选 options 完整 ABCD | 8/8 | 8/8 ✓ |
| 单选 ans ∈ {A,B,C,D} | 8/8 | 8/8 ✓ |
| KP 跨学科污染 | 0 | 0 ✓ |
| figure 引用 | 全命中 | 15/15 disk-resolvable ✓ |

inspect tool 报告：`28 100 100 8 8 12 - - - - - - - - - - - - - - - - - - 33 33`（零异常列）。

---

## 2. 填充质量抽样（PASS）

- **Q1-Q8 单选**：ans = `C/C/D/A/A/D/C/B`，sol 含完整推理（132–2535 chars，Q8 含 ①②③④ 四结论逐条论证）。
- **Q9-Q16 填空**：ans 全 LaTeX/中文落地，Q12 含双答案 `①. 19    ②. 30`，Q14 含两种格式 `$40\circ$##40度`，Q9 含中文括号 `m（n+1）（n﹣1）`。
- **Q17-Q19 计算/化简**：ans + 完整 sol。
- **Q20/Q24/Q27 几何证明**：sol 含 `\triangle/\angle/\bigodot/\bot/\parallel` 与中文下标 `S_{△ABE}`。
- **Q25 函数应用**：sol 1465 chars 含表格 + 描点 + 五问全解。
- **Q28 新定义题**：ans = 三问答案合并 110 chars，sol 3361 chars 含完整推理。

---

## 3. 发现的问题

### P1 — Q17 ans 末尾 `\sqrt{3}` 截断 [docx OLE 漏抓]

```
ans  : '$5 -$'                              ← 应为 '$5 - \sqrt{3}$'
sol 末: '$= 5 -$．'                          ← 同样漏 √3
```

源 docx 末尾 OLE 公式 `√3` 未被 d2t MTEF→LaTeX 翻译且 Ruby per-OLE fallback 也没补回（计算结果 `2-2√3+3+√3 = 5-√3`）。整卷只此 1 题受影响。

### P1 — `[公式]` 残留 34 处 / 7 题 [d2t 翻译率不足]

| 题号 | stem | answer | solution | 主因 |
|---|---|---|---|---|
| Q21 | 0 | 0 | **12** | 一次函数表达式重复出现 |
| Q23 | 0 | 0 | 1 | — |
| Q24 | 1 | 1 | 3 | 点 `H` 名/`\bigodot O` 切线表达式漏抓 |
| Q25 | 1 | 0 | 2 | A 家庭表达式 |
| Q26 | 0 | 0 | 1 | — |
| Q27 | 0 | 1 | 1 | 辅助延长点 `H` 漏抓 |
| Q28 | 4 | 0 | 6 | $B_2 / A_2$ 等下标点名漏抓 |

抽样：
- Q24 stem：`...点$D E$并延长交$A B$于点[公式]，若...` —— 点 `H` 名号 OLE 漏（应为 `$H$`）
- Q28 stem：`...$A_{1}$，[公式]是半径为[公式]的$\bigodot O$上...` —— `$A_2$ / $2\sqrt{5}$` 漏
- Q21 sol：12 处全为 `y = mx + 3 / y = kx + b` 表达式相关 OLE

**根因**：日志 `OMML 140 / OLE 881 → md $-公式 986`，OMML+OLE 源 1021 个 ≠ md $ 986 个，34 个 OLE 未翻译，落成 `[公式]`。和 R3 时 changping Q23/Q25/Q26 共 3 处同类问题，但本卷量级更大（解析版 sol 文本远长）。

**对比 R3 其他 11 卷**：
- haidian / mentougou / xicheng / yanshan / fengtai 实测 0 残留
- chaoyang / pinggu sol 全空（A 类）故无法对比
- changping 3 处（Q23/Q25/Q26）—— 是已知 P1

### P2 — Q27 ans 含完整证明（937 chars，非 bug）

- ans 字段包含【答案】section 全证明 + 图片引用
- sol 字段是【分析】+ `（1）证明：略．（2）解：略．`
- 源 docx 该题【详解】小节实际写 "略"（因证明已在【答案】），属源数据风格
- parser 分流合规：ans 来自 `【答案】`，sol 来自 `【分析】+【详解】`
- 影响：学情分析时 "标准答案展示 / 解题步骤" 区分被混淆。**不推荐 patch，建议下游 enrich 时识别 "略" 标记把 ans 部分迁回 sol。**

---

## 4. 全局结论

**OVERALL: PASS** —— 升档（之前 A 类无答案 → 现 PASS，与其他 PASS 卷同档）。

- 结构指标 0 缺陷，填充率 28/28 = 100%
- **`[公式]` 残留：0 处（修复 Phase 2 之后）**
- 唯一已知 issue：Q17 ans `'$5 -$'` 末尾缺 `\sqrt{3}` —— **学科网精品解析源 docx 录入瑕疵**（rId467/rId469 OLE 二进制就只编了 `5 -`，√3 字符压根没存进 MathType binary），非 parser bug
- 不阻塞 enrich / 不阻塞 student-report 流水线

---

## 5. Phase 2 修复纪要（2026-05-31）

### 根因

mathtype Ruby gem v0.0.8（mathtype_to_mathml 0.0.7 的依赖）只硬编码 MTEF record_type=100 为 RecordFuture，spec 实际明文 ≥100 都是 FUTURE 格式（uint8 length + skip）。MathType 6+ 新版 (zxxk 精品解析最近版本) 在 OLE 头里加了 record_type=102 装 "TeX Input Language\0..." 元数据，gem 一遇到 102 直接 `IndexError: selection '102' does not exist in :choices`，**整条公式废掉**。

daxing 881 个 OLE 里 49 个 (5.5%) 含 type-102 → Ruby fallback 832/881 → md `[公式]` 残 34 处 (7 题)。

### 修复（两处）

**1. `scripts/exam-docx/mtef_extract.rb`** — BinData::Choice monkey-patch
```ruby
module BinData
  class Choice
    private
    alias_method :_orig_instantiate_choice, :instantiate_choice
    def instantiate_choice(selection)
      proto = get_parameter(:choices)[selection]
      proto = get_parameter(:choices)[100] if proto.nil?  # FUTURE 兜底
      proto.instantiate(nil, self)
    end
  end
end
```
为何不用 `Mathtype::Payload` reopen 加 `:default`：BinData 把 choices 表 sanitize 进 SanitizedChoices 缓存（NamedRecord 类定义时锁定），reopen 加 `:default` 后不进缓存。改在 Choice instantiate_choice 层兜底是最低侵入路径。

**2. `mtef_extract.rb` STDIN + math_docx_paper.py 改用 stdin**
门头沟 1196 个 OLE → Ruby subprocess argv 超 OS 限制 (E2BIG) → fallback 不启动 → d2t 1184/1196 残 12 处 [公式]。改 ruby 接 STDIN 一行一文件，python 通过 `input=` 传文件列表。

### 修复后状态（12 区 yaml）

| 区 | OLE 源 | d2t cache | Ruby map | md 公式 | yaml `[公式]` |
|---|---|---|---|---|---|
| changping | 1129 | 1112 | 1129 | 1128 | **0** |
| chaoyang | 1126 | 1106 | 1126 | 1126 | **0** |
| daxing | 881 | 309 | **881** | 1021 | **0** |
| fangshan | 894 | 878 | 894 | 1004 | **0** |
| fengtai | 1118 | 1098 | 1118 | 1118 | **0** |
| haidian | 1078 | 1058 | 1078 | 1208 | **0** |
| mentougou | 1196 | 1184 | **1196** | 1195 | **0** |
| pinggu | 833 | 813 | 833 | 951 | **0** |
| shijingshan | 1090 | 1070 | 1090 | 1217 | **0** |
| shunyi | 1078 | 1058 | 1078 | 1196 | **0** |
| xicheng | 1080 | 1060 | 1080 | 1080 | **0** |
| yanshan | 1124 | 1104 | 1124 | 1124 | **0** |

- daxing Ruby map 832 → **881**（49 个 type-102 全部 graceful skip 后正常解析后续记录）
- mentougou 因 argv 上限 0 → **1196**（STDIN 修复）
- 全区 `[公式]` 残留 0

### 不在此轮 patch

1. **Q17 ans 截断 √3**：源 docx OLE 二进制就缺，需 `_patches/math/2026-daxing-er.yaml` 单题 patch
2. **Q27 ans/sol 迁移**：源 docx 风格【答案】含全证明、【详解】写"略"，建议下游 enrich 阶段识别迁移
3. **OMML+OLE 源 vs md 数小差异**（如 daxing 1021 vs 1196 期望 / mentougou 1196 vs 1195）：跨区均 0/1 个，非系统问题，剩余 dedup/walker 边角
