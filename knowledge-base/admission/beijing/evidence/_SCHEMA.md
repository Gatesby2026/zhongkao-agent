# 证据层 Evidence Store

> 把"证据(raw·带出处)"与"事实(clean·可直接用)"分开。
> 事实层(`*_new2026.yaml` / `schools_unified` 等)的每个**不确定字段**用 `evidence_refs` 指回这里。
> **只增不删**:修正靠新增"取代"条目 + 改 `status`,旧证据永久留痕。

## 适用场景(通用层,非只为新校)
新校 est_rank / 校区地址核查 / 网传录取线 / 民间高考数据 / 统筹名额…… 凡是
"来源不唯一、可信度不满、需要标注出处"的信息,都进这里。

## 存储
- 按主体一文件:`evidence/<slug>.evidence.yaml`,顶层是 `records:` 列表。
- 与 `raw_extracts/`(整页 OCR 大块原文)分工:raw_extracts = 原始大块;evidence = **断言级**结构化条目。

## 记录 schema(每条 = 一个"谁说某主体的某属性是什么")
```yaml
- id: ev-<年>-<主体slug>-<序号>     # 全局唯一,被 evidence_refs 引用
  entity: 朝阳区燕京新源实验学校       # 主体(校名)
  entity_uid: 新校:朝阳区燕京新源实验学校  # 对齐 schools_unified uid(可空)
  claim: admission_qualification     # 断言维度(见下方常用 claim)
  value: 2026普高招生资格·朝阳第48位   # 抽出的值;查无则写 unknown
  confidence: T1                     # T1..T5(见下)
  status: confirmed                  # confirmed/unconfirmed/conflicting/negative/superseded
  source_type: 官媒                  # 官方/区招考/官网/官媒/百科/机构/搜索摘要/网传
  source_url: https://...
  source_title: 页面标题
  method: WebSearch                  # WebSearch/WebFetch/OCR/人工/API
  collected_at: 2026-06-19
  excerpt: "原文关键句,逐字不改写"
  expires: 2026-07                   # 何时须复核(如官方简章发布);可空
  supersedes: ev-...                 # 取代了哪条(可空)
  notes: ""
```

## 可信度分级(沿用 ADDRESS-VERIFICATION 的 T1–T4 + 补 T5)
| 级 | 信源 |
|---|---|
| T1 | bjeea / 市教委 / 区招考 官方 |
| T2 | 学校官网 / 官媒报道 |
| T3 | 二手转载(zhongkaobj / 机构站) |
| T4 | 百科 / 地图 / 单源网传 |
| T5 | 搜索引擎摘要 · 未核实 |

**定案规则**:`status=confirmed` 需 **≥2 独立源一致**。低于 T2 的值在前端**必带来源+可信度徽章**,T4/T5 显式标"务必自行核实"。

## 常用 claim 取值
`admission_qualification`(招生资格) / `nature`(公办民办) / `address` / `coords` /
`operator`(承办主体) / `system`(教育集团) / `plan`(招生计划) / `admission_mode`(招生方式:统招/1+3/统筹) /
`line`(录取线) / `rank`(录取位次) / `est_rank`(预测位次锚) /
`NOT_SAME_AS`(排除/防混淆,status=negative)

## 事实层如何引用
```yaml
# 例:chaoyang_new2026.yaml
est_rank: 6000
est_rank_conf: T5
evidence_refs: [ev-2026-yanjing-xinyuan-001, ev-2026-yanjing-xinyuan-anchor-001]
```

## 生命周期
`collected_at` + `expires` → 到点(如 7 月简章)触发复核 → 新证据 `supersedes` 旧条目、旧条目 `status: superseded`。
