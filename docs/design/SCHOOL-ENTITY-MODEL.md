# 学校实体模型 · RFC（系统基础数据重构）

> 目标:把"学校"做成**稳定、结构化、单一事实源**的实体,彻底取代全系统用"名字字符串"
> 做主键/连接键/去重键的现状。线/位次/pred 下沉到最细粒度(录取单元),校区为一等子实体。
> 决策已定:**① 全量四阶段 ② ID=区-编号-拼音简写 ③ campus 一等子实体(线挂 major、major 绑 campus)**。

---

## 一、为什么必须重构(问题本质)

全系统现用**学校名字符串**做连接键,而名字是**易变的展示字段**,同一所学校在不同文件有 3~5 种写法:

| 同一所学校(和平街一中, 代码 105004) | 写法 | 出处 |
|---|---|---|
| 内部展示 | `和平街一中` / `和平街一中（北苑莲葩园校区）`(拆两条) | chaoyang.yaml, 草表 |
| 官方计划书 | `北京市和平街第一中学` | plan_school_name |
| 校额缩写 | `和平街(莲葩园)` | xeddx.yaml |
| 复合键 | `105004:北京市第…` | gaokao.jsonl, pred_2026 |

由此产生四类必然故障(均已踩到或潜伏):
1. **连接漏接**——`get(s["name"])` 严格匹配,差一字→丢代码/丢专业。
2. **去重打架**——`dedupeByName`(基名)与 `dedupeByCode`(代码)挑出不同代表名 → `<select>` 空白(莲葩园 bug)。
3. **误并/误分**——`baseSchoolName` 砍括号,有把"北京中学"vs"北京中学科技分校"、"人朝(公办)"vs"人朝分(民办)"混淆之险。
4. **缩写映射手维护**——`distance.py` 的 `ABBR`/`_norm` 散落、无权威对照。

**根因:没有"学校实体"概念。** 名字同时承担显示+主键+连接+去重四职。补丁(如 `toSelName`)只灭症状,类 bug 会从别的入口再发。

---

## 二、目标实体模型

```
School(学校实体)                       ← 稳定 id 是全系统唯一连接键
 ├─ id: "cy-018-hpjyz"                 区-编号-拼音简写(见 §三),永不变
 ├─ canonical_name: 北京市和平街第一中学   官方全名(显示)
 ├─ short_name: 和平街一中               列表/草表显示
 ├─ aliases: [和平街一中, 和平街, 和平街一中（北苑莲葩园校区）, 北京市和平街第一中学, 105004, …]
 │                                      ← 收编所有历史写法+缩写+代码,供 resolve()
 ├─ type: 公办普高|民办|中职|贯通|新校
 ├─ level / district / note
 │
 ├─ campuses[]:                        校区=物理位置(一等子实体,有自己坐标/距离/住宿)
 │   ├─ {slug: benbu,  name: 和平街校区,   lat,lon, address, confidence, boarding:false}
 │   └─ {slug: lianpa, name: 北苑莲葩园校区, lat,lon, address, confidence, boarding:true}
 │
 ├─ admissions[]:                      录取单元=(channel, code, major);线/位次/pred 挂这里
 │   ├─ {channel:统招, code:"105004", major:"01", major_name:普通班, campus:benbu,
 │   │     plan_total:125, plan_district:125,
 │   │     lines:{2025:{score:454,rank:4635}, 2024:{score:608,rank:5766}, 2023:{…}},
 │   │     pred_2026:{rank,lo,hi,pct,conf}}
 │   ├─ {channel:统招, code:"105004", major:"02", major_name:普通班, campus:lianpa, boarding:true,
 │   │     plan_total:117, lines:{2025:{453,4762}, 2024:{602,6420}}, pred_2026:{…}}
 │   ├─ {channel:校额到校, code:…, …}
 │   └─ {channel:市级统筹, code:…, major:"20/30", …}
 │
 └─ rollup(仅显示,不参与 join): gaokao / features / features_std / value_added /
                                campus_life / evidence_refs[]
```

**关键修正(回答"不同校区是否不同线"):** 北京统招按 `录取代码+专业(班)` 平行投档、各自出线
→ **线/位次/pred 的最细粒度 = 录取单元(code+major)**,实证和平街 01=4635 / 02=4762。
校区是录取单元的物理属性。**School/campus 层不存线,只做 rollup 显示。**

---

## 三、ID 规范 `{区}-{NNN}-{拼音简写}`

- **区段** = 区拼音首字母:朝阳`cy` / 海淀`hd` / 西城`xc` / 东城`dc` / 丰台`ft` / 石景山`sjs` / 通州`tz` / …
- **编号** = 区内 **3 位流水号**,首次分配后**永久冻结**,不复用、不重排(删校也不回收号)。
- **拼音简写** = `short_name` 的声母串(pypinyin FIRST_LETTER),如 和平街一中→`hpjyz`、北京中学→`bjzx`、陈经纶→`cjlzx`。多音字/重名由 §六 人工核。
- **示例**:`cy-018-hpjyz`
- **子标识**:
  - 校区:`{id}::{campus_slug}` → `cy-018-hpjyz::lianpa`
  - 录取单元:`{code}-{major}` → `105004-02`(无代码的新校用 `NEW`,如 `NEW:民大附中`)
- **为何不用录取代码当 id**:新校无代码;同校各批次代码不同(统招/校额/提前批);一校可多代码;代码逐年可变。→ **代码降级为 `admissions[].code` 属性**。

---

## 四、别名解析层(脏名字挡在边界)

唯一入口 `resolve(name_or_code) -> school_id`:
- 数据源 = 各 School 的 `aliases`(全写法+缩写+代码+plan_school_name)。
- **构建期校验** `validate_registry.py`:扫所有数据文件出现的每个学校名/代码,**必须全部 resolve**,否则构建失败 → 名字写错当场暴露,不再线上变空白。
- `distance.py` 的 `ABBR`、xeddx 缩写表 → 全部并入 aliases,删散落归一化。

---

## 五、四阶段落地(系统全程不停摆,每步可回滚)

| 阶段 | 内容 | 风险 |
|---|---|---|
| **P0** | 建注册表(只读):生成器从现有 10 文件**自动合并** `registry/<区>/*.yaml`(id+aliases+campuses+admissions+lines),产出**覆盖率/冲突报告**,人工核 89 校。加 `validate_registry.py`。**纯新增、零行为改动**。 | 无 |
| **P1** | 后端切 id 装配:`recommend.py`/`unified.py` 改 `resolve→id→assemble`,API 加 `id`/`campus`/`major`(name 保留兼容)。单测对账新老 bands 学校集合一致。 | 低(可回滚) |
| **P2** | 前端切 id:草表 slot=`{school_id,code,major}`、`<select v-model="school_id">`、面板/距离/pred 跟随所选 major。**删** `baseSchoolName/dedupeByName/dedupeByCode/toSelName/selNameIndex/findCard(按名)/nonPubByName(按名)/bandOf(遍历)`。`cleanName` 仅展示。 | 中 |
| **P3** | 各维度文件补 `school_id`,去名字 join;pred 细化到 major;evidence 引用 id。 | 低 |
| **P4** | 扩区:海淀等只需按同 schema 建注册表 → SOP 化。 | 低 |

---

## 六、生成器策略(P0,不编造)

1. **合并键**:public 以 `admission_codes.schools[*].school_code` 为准——**同代码的多个 name 条目合并为一个 School 的多个 campus+major**(和平街 01/02 即此)。private/voc/new 各自 name 为单位。
2. **campuses**:取 coords.schools[name].campuses[] ∪ chaoyang.yaml location;按 location.campus 文案里的"01/02 专业"提示**关联 major↔campus**;无法确信关联的 → 报告 `AMBIGUOUS_CAMPUS_MAJOR`,不瞎连。
3. **lines**:chaoyang.yaml scores 是**按条目(即按校区)**记的 → 落到对应 major 的 `lines`;关联不确定则落 School 级并标 `LINE_AT_SCHOOL_LEVEL` 待人工下沉。
4. **pred**:pred_2026.json(code:name)落对应录取单元;多 major 仅有单一 pred 的,报告 `PRED_NOT_PER_MAJOR`(P3 细化)。
5. **id**:自动算拼音简写 + 区内流水号;重名/多音 → 报告 `ID_REVIEW`。
6. **覆盖率报告**列出:缺坐标 campus、缺线 admission、未 resolve 的外部名、可疑合并、id 待核。**所有缺口如实列出,绝不填假值。**
7. **校额到校**:关系表(初中→{高中:名额})保持原样(P3 迁 id);生成器把每所朝阳高中
   的总名额聚合成一条 `校额到校` channel(`metric:校内排名` / `slots_2025_total`)。
8. **市级统筹**:统筹校多为外区 → **按归属区(home_district)建实体**(id 用该区前缀
   `dc-/xc-/hd-/ft-…`),挂 `市级统筹` channel(tier/quota_chaoyang/major 20·30/线)。
   注册表按区分目录 `registry/<区>/`;`resolve()` 默认**跨全区**加载,朝阳可命中外区统筹校。
   这些外区校先有统筹维度,P4 建对应区时再补全其本区统招等。

---

## 七、收益

- 莲葩园类 bug **机制上不可能再发生**(无名字匹配)。
- 加数据/扩区有 schema+校验,不再"拼串猜对错"。
- 校区/距离/住宿/线/pred **精确到所选专业**。
- 与既有 evidence 证据层、test-data 命名规范天然对齐。

---

## 八、产物清单

- 注册表:`knowledge-base/admission/beijing/registry/chaoyang/*.yaml`(每校一文件)+ `_index.yaml`
- 生成器:`scripts/admission/registry/build_registry.py`
- 校验器:`scripts/admission/registry/validate_registry.py`
- 解析库:`scripts/admission/registry/resolve.py`(P1 起后端引用)
- 报告:`scripts/admission/registry/_coverage_report.md`(每次生成刷新)
