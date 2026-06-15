# 学校实体 Schema（统一学校模型 §12）

> 单一数据源 = `schools_unified[]`，由 `scripts/admission/unified.py` 的 `build_unified(result)` 产出。
> 核心原则：**一所学校一条记录，多条录取渠道挂在 `channels[]` 里**（"学校唯一·渠道多个"）。
> 本文档由 `unified.py` 代码固化而来；改 schema 时请同步更新本文件。

---

## 1. 顶层公共字段（每条记录都有）

| 字段 | 类型 | 说明 |
|---|---|---|
| `uid` | string | **稳定主键**。有招生编码=`"{school_code}:{name}"`，无码=`"{type}:{name}"`。地图标记、详情面板、`ts/gaokao_score.json`、`ts/lines.jsonl` 的 join 全用它。<br>**铁律**：`unified._uid()` 与 `normalize/build_timeseries.uid_of()` 必须保持一致，否则产品 join 不到数据。 |
| `id` | string | 旧键 `"{type}:{name}"`。遗留字段，逐步弃用，新代码用 `uid`。 |
| `name` | string | 学校名（同代码多校区会带 `·校区` 后缀以保证 uid 唯一）。 |
| `type` | enum | 学校类型，见 §2。 |
| `district` | string | 区（如 `朝阳`）。 |
| `geo` | object | `{ lat, lon, address, confidence }`。`confidence` ∈ `high/medium/low/approx`，`lat/lon` 可为 null。 |
| `boarding` | bool/null | 是否提供住宿。 |
| `level` | string/null | 办学层次（如 `市级示范性高中` / `贯通承办院校`）。 |
| `school_code` | string/null | bjeea 招生编码（公办/民办有；统筹外区校/贯通/新校可能无）。 |
| `commute` | object/null | 到家路网距离 `{ km, mins, over_max, label }`。无家庭住址或无坐标时为 null。 |
| `features` | object | `{ style, tags[], gaokao }`。`tags` 取自固定特色词表；`features.gaokao` 是**旧的自由文本**字段（新高考分在顶层 `gaokao`）。 |
| `map` | object | 地图渲染属性 `{ color, band, kind }`（主要公办填充）。 |
| `gaokao` | object/null | **高考出口 U 分**，见 §4。仅当 `uid` 命中 `ts/gaokao_score.json` 时挂载（主要公办）。 |
| `line_trend` | object/null | **录取位次趋势**（uid 命中 `ts/line_trend.json`）`{ ranks{23,24,25}, latest, volatility, volatile, ref_2026, ref_2026_lo/hi }`。T3·中央取最近年、区间取三年包络、不外推。 |
| `value_added` | object/null | **增值**（uid 命中 `ts/value_added.json`）`{ entrance_rank, yiben_real, yiben_expected, residual, label(高增值/符合预期/偏低/顶部饱和), basis }`。入口位次→出口一本率 residual；顶部饱和=一本率近满不区分(看清北)。 |
| `campus_life` | object/null | **校园生活/班型**（按校名命中 `campus_life.json`）`{ class_system, schedule, management, boarding_detail, dining, activities, voices }`。白皮书 T3。 |
| `features_std` | object/null | **标准特色**（按校名命中 `features_std.json`）`{ tags[](闭集9类:科技创新/学科竞赛/外语特色/文科人文/艺术特长/体育特长/国际方向/课程改革/综合均衡), highlight }`。供"按特长选校"筛选。 |
| `channels` | array | **录取渠道列表**，见 §3。 |
| `extra` | object | **类型专属字段**，见 §5。 |

---

## 2. `type` 取值

| 值 | 含义 |
|---|---|
| `公办普高` | 区属/市属公办普通高中 |
| `市级统筹` | 外区/郊区面向本区招生的统筹校（本区统筹并入对应公办记录的 channel） |
| `民办普高` / `国际/双语` / `民办普高/国际/双语` | 民办校；`/` 连接表示同时在民办名单与国际名单 |
| `中职/职教` | 中职/职高 |
| `贯通` | 贯通培养承办院校（全市） |
| `2026新校` | 2026 新建校（无历史线，代理参考） |

---

## 3. `channels[]` — 一校多渠道

每个录取渠道一个对象，各自独立研判：

```jsonc
{
  "channel": "统招",          // 统招 / 市级统筹 / 校额到校 / 自主 / 中职 / 贯通 / 新校待定
  "band":    "稳",            // 冲 / 稳 / 保 / 搏 / 够不上 / 待核 / 不适用
  "metric": {
    "kind": "district_rank",  // 见下表
    "refRank": 1357,          // 视 kind 而定的字段
    "refLine": 476,
    "lines": {...},
    "quota": 47
  },
  "lines": {...}, "quota": 47, "caveat": "不在报名范围",
  "tier": "统筹一"            // 仅市级统筹渠道
}
```

`metric.kind`：

| kind | 用于 | 关键数 |
|---|---|---|
| `district_rank` | 公办统招 | `refRank`（录取区位次）、`lines` |
| `city_score` | 市级统筹 | `refLine`（比统招线，偏保守）、`quota` |
| `route_choice` | 民办/国际 | 无统一录取线，路线选择为主 |
| `threshold` | 中职 / 贯通 | 门槛分（贯通≥380） |
| `none` | 2026新校 | 无历史线，不做研判 |

> 注：**校额到校**渠道由前端按选定初中（`xedJudgeByName`）动态追加，不在本层产出。

---

## 4. `gaokao` — 高考出口 U 分（公办）

来源 `ts/gaokao_score.json`（T3·民间/机构汇编·待核）。

```jsonc
{
  "score": 91,              // U 分 0~100，新校为 null
  "tier": "优质",          // 顶尖≥93 / 优质≥85 / 中上≥72 / 中等≥58 / 一般；新校="新校"
  "yiben": 0.99,           // 真实一本率(特控率)，估算校为 null
  "yiben_est": null,       // 位次回归估算的一本率（真实值缺失时）
  "qingbei": 7,            // 清北人数
  "basis": "一本率99%(2024)；685+7",
  "confidence": "medium"   // medium(多源真实) / low(单源) / very_low(估算/存疑) / na(新校)
}
```

U 分公式：`一本率底×88 + min(清北/高分段声望,24)×0.5`；头部校（不报一本率）按≈100% 托底；无采集值的校用录取位次回归估算（very_low）；新建高中部（首届未毕业）标 `tier="新校"`、`score=null`，不伪造。

---

## 5. `extra{}` — 类型专属字段

`extra` 是"逃生舱"：类型专属、不强求统一，用于容纳异构信息。

### 公办普高
| 字段 | 说明 |
|---|---|
| `coop` | 是否有中外合作班 |

### 市级统筹
| 字段 | 说明 |
|---|---|
| `campus` | 校区 |
| `quota_chaoyang` | 投本区（朝阳）名额 |

### 民办 / 国际
| 字段 | 说明 |
|---|---|
| `tuition` / `tuition` 口径 | 学费（各校招生口径，分项目/班型，波动大） |
| `curriculum` / `wp_curriculum` | 课程体系（国内普高/A-Level/IB/AP/美高/OSSD…） |
| `direction` | 方向（国际/双轨…） |
| `in_minban` / `in_intl` | 是否在民办名单 / 国际名单 |
| `exit_type` | **升学出口分类**：`留学` / `高考` / `混合` / `暂无毕业生` / `未公布` |
| `study_abroad` | **留学走向**（国际校：国家方向 + G5/前30/前50 比例 + 代表 offer） |
| `exit_domestic` | 高考出口（走高考的校：本科率/特控率/最高分） |
| `enroll_2025` | 2025 统招招生人数 |
| `class_info` | 班型/规模 |
| `line_note` | 录取线说明（民办多为"电话咨询"） |

### 中职 / 职教
| 字段 | 说明 |
|---|---|
| `specialties` | 专业 |
| `five_year` | 五年制项目 |
| `comp_high_2025` | 综合高中班 2025 招生人数 |
| `comp_high_note` | 综合高中班说明（职普融通/普高学籍/可参加高考） |
| `voc_line_note` | 录取线（如 劲松 548/2023） |
| `exit_paths` | 升学路径（本科率/单招升本/就业） |
| `campuses` | 校区列表 |

### 贯通
| 字段 | 说明 |
|---|---|
| `projects[]` | `{ type(中本/高本贯通), major, benke(对接本科), plan, years, threshold }` |
| `note` | 备注 |
| `type_meta{}` | 按类型：`{ entry, years, stage, transfer(转段), tuition }` |
| `policy_note` | 京籍/提前批/≥380/2026并入统招 等政策 |

### 2026 新校
| 字段 | 说明 |
|---|---|
| `system` | 教育体系/集团 |
| `analog` | 可类比校 |
| `direction` | 方向 |

---

## 6. 数据流（uid 贯穿）

```
源 yaml (chaoyang.yaml / chaoyang_private.yaml / chaoyang_vocational.yaml / beijing_guantong.yaml ...)
  │  recommend.build_result()  ← 整条 dict(s) 透传，含通勤
  ▼
result{ public_list, private_schools, vocational, guantong, tongchou, new_schools, points }
  │  unified.build_unified()   ← 拼公共层 + channels[] + extra{}；按 uid 挂 gaokao
  ▼
schools_unified[]  ──→  /api/zhiyuan/recommend  ──→  前端地图/查学校/草表（全部以 uid 为锚）

派生长表（趋势/打分）：normalize/build_timeseries.py → ts/{schools.yaml, lines.jsonl, gaokao.jsonl}
                       analyze/compute_gaokao_score.py → ts/gaokao_score.json（uid→U分）
```

---

## 7. 维护约定

- **改 schema 必须同步本文件**；新增 `extra` 字段在 §5 对应类型下登记。
- `uid` 口径若调整，`unified._uid()` 与 `build_timeseries.uid_of()` 必须一起改。
- 数据置信度分级：T1(bjeea 官方) > T2(机构结构化) > T3(网传/民间/LLM估算)；面板需显式标注 T3/估算/待核。
