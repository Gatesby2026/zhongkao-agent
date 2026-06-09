# 志愿填报·数据采集与存储方案

> 目的:为"分析录取线变化 → 预测 2026 线 → 评估学校高考产出/增值"撒网采集数据,并以**可追溯、可分析、可复核**的方式长期保存。
> 关联:`ZHIYUAN-PRECISION-RESEARCH.md`(为什么要这些数据)、`ZHIYUAN-DRAFT-ALGORITHM.md`(uid 主键)。

---

## 0. 原则(避免"乱收一堆没法用")

1. **schema 先行,再撒网**:先定"分析需要哪些字段",按表去采,而不是先囤再发愁。
2. **raw 与 derived 分层**:原始快照不可变(可重跑/审计);派生为规范化长表(喂分析)。
3. **uid 做主键**:用已建的 `school_code:name` / `type:name` uid 跨年跨源 join,**绝不靠学校名匹配**(名字逐年/逐源写法不一)。
4. **每条数据带血缘**:`source_url + source_tier(T1–T4) + collected(采集日) + confidence`。冲突保留多源 + 标"resolved 值 + 方法"(沿用 `addresses_audit` 模式)。
5. **长表(tidy)而非嵌套**:一行 = 一个 (学校×年×指标×来源),便于 pandas/SQL 做 groupby/趋势。
6. **口径随值走**:总分(510/670)、位次口径(区/校)随每条标注,跨年统一用**区位次**比。
7. **append-only + 批次时间戳**:每次采集留痕,可回溯"当时抓到的是什么"。

信源分级(沿用项目 SOP):T1 bjeea/市教委官方 > T2 区招考/学校官网官微 > T3 升学平台(zhongkaobj/gaokzx/xscxx/本地宝)> T4 论坛/知乎/家长群(仅线索,必须 T1–T2 或多 T3 印证)。

---

## 1. 目录结构

```
knowledge-original/zhiyuan/raw/           # ① 原始快照(不可变)
  bjeea/<year>/录取线公告.html|pdf
  quzhaokao/<year>/朝阳计划册.pdf
  school-sites/<uid>/喜报<year>.png|html
  platforms/<source>/<date>/<slug>.html
  forums/<date>/<slug>.md
  _raw_index.jsonl                        # 每个 raw 文件一行(见 §2.5)

knowledge-base/admission/beijing/
  schools.yaml          # ② 学校主表(uid 主键)— 已部分存在,补全为权威主表
  ts/lines.jsonl        # ③ 录取线时序(分析主表)
  ts/gaokao.jsonl       # ④ 高考出口/增值原料
  ts/plans.jsonl        # ⑤ 招生计划时序
  ts/yifenyiduan/<year>_<region>.csv   # ⑥ 一分一段表
  ts/provenance.jsonl   # ⑦ 数据血缘/冲突审计
```

> 现有 `chaoyang.yaml / *_admission_codes.json / *_coords.json / *_xeddx.yaml / 2025_sjtongchou_chaoyang.json` 继续保留(它们是当年快照);新增的 `ts/*` 是**跨年长表**,把这些快照"拍平"进来供分析。

---

## 2. 各表 schema

### 2.1 学校主表 `schools.yaml`(uid 主键)
```yaml
- uid: "105004"                # 招生编码;无编码用 "市级统筹:中国人民大学附属中学·通州校区"
  name: 北京市第八十中学
  aliases: [八十中, 80中]       # 各源别名→归一
  school_code: "105004"
  type: 公办普高
  district: 朝阳
  campus: 本部
  lat: 40.0098
  lon: 116.4766
  boarding: false
  system: 八十中教育集团         # 集团/体系
  tags: [理科强, 科技特色]
```

### 2.2 录取线时序 `ts/lines.jsonl`(★分析主表,一行一记录)
```json
{"uid":"105004","name":"北京市第八十中学","year":2025,"batch":"统招",
 "campus":"本部","major_code":"01","major_name":"普通班",
 "score":null,"score_total":510,"rank":1200,"rank_scope":"区",
 "plan":null,"source_url":"https://bjeea.cn/...","source_tier":"T1",
 "collected":"2026-06-10","confidence":"high","note":""}
```
- `rank` = **区位次**(跨年可比的核心);`score` 仅当年可比(总分变过)。
- `batch ∈ {统招,校额到校,市级统筹,贯通}`;能拆到 `major` 就拆(实验班/普通班线差大)。

### 2.3 高考出口/增值 `ts/gaokao.jsonl`
```json
{"uid":"105004","name":"北京市第八十中学","year":2024,
 "metric":"特控率","value":0.92,"denom":420,
 "source_url":"...","source_tier":"T3","confidence":"low","note":"民间喜报"}
```
- metric ∈ {本科率, 特控(一本)率, 600+率/高分段, 985率, 211率, 清北数, 强基数, 均分...}。
- **增值**不存原始、由分析阶段算:`增值 = 出口指标 vs 同年入口位次档` 的超额(见研究报告 §2)。

### 2.4 招生计划 `ts/plans.jsonl`
```json
{"uid":"105004","year":2026,"batch":"统招","major_code":"01","major_name":"普通班",
 "plan":125,"plan_chaoyang":125,"source_url":"...","source_tier":"T1","collected":"..."}
```

### 2.5 原始索引 `_raw_index.jsonl` / 血缘 `ts/provenance.jsonl`
```json
{"path":"bjeea/2025/录取线公告.pdf","url":"...","source":"bjeea","tier":"T1",
 "collected":"2026-06-10","sha256":"...","about":["lines:2025:统招:朝阳"],"note":""}
```
- provenance 记录"哪条派生值来自哪些 raw + 用什么方法 resolve 的冲突"。

---

## 3. 采集范围与优先级(撒网清单)

| 优先 | 采什么 | 来源(优先级) | 方法 |
|---|---|---|---|
| **P0** | 逐校×专业× **近 5 年** 录取线+区位次(统招/校额/统筹/贯通) | bjeea 录取线公告(T1)、区招考(T2)、平台交叉(T3) | 抓取/OCR(已有 gaokzx curl + 计划册 OCR 流程) |
| **P0** | **一分一段表** 逐年(朝阳+全市) | bjeea/考试院(T1) | 抓取/OCR |
| **P0+** | **逐校高考出口** 逐年(本科/特控/名校率/清北) | 学校官微喜报(T2)、平台/知乎(T3/T4) | 抓取+人工核;**多源交叉**,标低置信 |
| P1 | 招生计划册 逐年(各批次专业计划) | bjeea/区招考(T1) | OCR |
| P1 | 学校基础(坐标/住宿/体系/集团) | 官网(T2)、本地宝(T3) | 抓取 |
| P2 | 新校信息(入口类型/说明会) | 官微/区教委(T2)、平台(T3) | WebSearch(本轮已起步) |
| P2 | 二模↔中考对照(若可得) | 家长群/区统计(T4) | 谨慎,仅作漂移参数参考 |

> 起步建议:**先把"录取线近 5 年 × 全朝阳"灌满 `ts/lines.jsonl`**(趋势分析的命脉),同时并行采高考喜报建 U 轴。

---

## 4. 采集→入库 流程(可重跑)

```
撒网(WebSearch/WebFetch/curl/OCR)
  → 落 raw 快照 + _raw_index.jsonl(带 url/tier/sha/日期)
  → 解析脚本 normalize 到 ts/*.jsonl(每条带 uid/source/tier/conf)
  → 多源 reconcile(同一 uid×year×指标多源 → resolved + 冲突记 provenance)
  → 校验(uid 在 schools.yaml、口径合法、位次单调性 sanity)
```
- 脚本放 `scripts/admission/collect/`(抓取)与 `scripts/admission/normalize/`(入库),与现有流程并列。
- 每条数据可溯源到 raw;raw 可重新解析 → 全流程可复现。

---

## 5. 为什么这样存能直接支撑后续分析

- **趋势/预测**:`lines.jsonl` 按 `uid` groupby、按 `year` 排序 → 直接回归外推 2026 + 算波动带(研究报告 §3)。
- **高考/增值**:`gaokao.jsonl` 与 `lines.jsonl` 按 `uid+year` join → 算"出口相对入口"的增值,识别捡漏校(§2)。
- **回测**:有了多年 lines + 结果,可用 2023/24 预测 2025 验证模型(§8)。
- **不靠名字**:全程 uid join,跨源/跨年/多校区都不会错配(本会话踩过的名字坑根除)。
- **可信度可加权**:每条带 tier/confidence,分析时官方权重高、民间标注参考。

---

## 6. 数据诚实红线

- 民间高考数据**口径不一、可能夸大**,一律标 T3/T4 + low confidence,**不作为唯一依据**,UI 标"民间·非官方"。
- 缺数据留空,不脑补;冲突保留多源不强行抹平。
- 涉及个体(校内排名等)需用户/学校提供,不抓取隐私。

---

_2026-06。数据采集与存储方案;落地先 scaffold 目录+schema,再按 §3 优先级分批采。_
