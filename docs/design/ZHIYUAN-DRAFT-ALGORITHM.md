# 志愿填报算法设计文档（志愿草表 / 三批次）

> 本文档系统梳理"志愿草表"的填报建议算法,作为后续稳定迭代的基线。
> 范围 = 朝阳区、京籍应届为主;其他区/身份按相同框架扩展。
> **第一原则:涉及孩子升学,绝不编造录取数据;缺数据标"待核"、留空,不硬凑。**
> 配套基线设计见 `ZHIYUAN-SYSTEM-DESIGN.md`(§1–§12 数据/统一模型)。本文聚焦"草表填报算法"。

---

## 0. 一句话总览

把考生的**区排名**转成**估分**与**冲稳保档位**,在**三个批次**(①提前招生 → ②指标分配 → ③统一招生)各自给出**缺省填报建议 + 逐志愿理由**。三批次**顺序录取、前批录取即锁定后批作废**——这条规则决定了各批次算法方向的根本差异。

---

## 1. 批次模型与核心不变量（Invariants）

录取顺序:`① 提前招生 →[录取即锁定]→ ② 指标分配 →[录取即锁定]→ ③ 统一招生`

| 批次 | 内容 | 算法方向 | 原因 |
|---|---|---|---|
| ① 提前招生 | 特长/中职自主/登记入学(2026 贯通已并入③) | 手填 | 无官方结构化代码 |
| ② 指标分配 | 校额到校 + 市级统筹 | **upgrade-only**(只填"统招够不上、够一够"的) | 在③之前·录取即锁定 → 填"你统招本来就能上的"=把自己锁低 |
| ③ 统一招生 | 12 志愿 × 2 专业(含贯通) | **冲稳保梯度 + 保底** | 最后一批 → 需要保底托底 |

**七条不变量(任何改动必须保持):**
1. **批次方向**:③要保底(稳/保不可少);②是 upgrade-only(稳/保=陷阱,不自动填)。二者方向相反,不可混用。
2. **录取代码 = 志愿单位**:同一录取代码(含多校区)算**一个**志愿,校区作"专业"合并(见 §6.1)。
3. **通勤**:未选住宿时,**自动推荐严格 ≤ 通勤上限**;下拉仍列全(可手动选远校)。选住宿则放开距离(见 §6.2)。
4. **研判口径**:位次跨年可比(主)、分数当年可比(辅);保守;无线→"待核";**绝不编造**。
5. **身份资格**:非京籍只报中职;往届/回京不可报②指标分配与贯通;贯穿各批次灰显。
6. **数据诚实**:缺数据/单源→标注;够不到 12 就留空,不用劣质候选凑数(③的"够不上回填冲刺"是显式策略、且仍受通勤约束)。
7. **界面 = 复制文本**:草表 UI 与"复制全部"导出同源,理由一并带出。

---

## 2. 数据输入（来自后端 `build_result`）

后端 `scripts/admission/recommend.py::build_result(rank, home, mode, max_km, boarding, identity, interests)` 产出:

- `bands`:`{冲, 稳, 保, 够不上}` → 每档 `Card[]`。Card 关键字段:
  `name, level, ref_rank(2025录取位次), margin, margin_pct, volatility, history[], score_lines[], nearest{km,mins,over_max}, over_max, reportable, boarding, school_code, majors[], style, tags, gaokao, coop`。
- `est_score`:区排 → 一分一段插值估分(`rank_to_score`)。
- `public_list`:全区公办统招校(含够不上/超通勤,带 reportable)。
- `xeddx`:校额到校,按**初中**给 `by_school`(各优质高中名额)。
- `tongchou`:市级统筹 `{tongchou_yi(统筹一), tongchou_er(统筹二)}`,每校带 `quota_chaoyang(投朝阳名额)、score_2025_tongzhao/score_ref(线)、district、campus、dist、boarding、address`。
- `guantong / new_schools / private_schools / vocational / schools_unified`(见基线文档)。

> 估分依赖:`est_score` 随 `rank` 动态变化,不写死。

---

## 3. 研判档位（band）的两套口径

> ⚠️ 历史原因存在两套,需理解其分工(未来可考虑统一)。

### 3.1 后端·位次 margin 法（用于 ③统招 bands）
`margin = (ref_rank − student_rank) / ref_rank`(正=你比录取线靠前)
- `margin ≥ 0.15` → **保**
- `0 ≤ margin < 0.15` → **稳**
- `−0.25 ≤ margin < 0` → **冲**
- `margin < −0.25` → **够不上**
- 波动:`volatility = (max−min)/avg` of 历年位次,阈值 `VOLATILITY_THRESHOLD = 0.40`。

### 3.2 前端·分数 Δ 法（用于 ②市级统筹、详情面板、JudgeLegend）
`scoreBand(line)`:`Δ = est_score − line`
- `Δ ≥ +10` → **稳** / `−10 ≤ Δ < +10` → **冲** / `−20 ≤ Δ < −10` → **搏** / `Δ < −20` → **够不上** / 无 line → **待核**

> **待统一项**:
> - 两套 band 阈值不同(位次比例 vs 分数差),概念对齐但口径不一。
> - 前端 `slotReason` 波动风险阈值用 **0.25**,后端用 **0.40** → 应统一(建议统一到 0.40 或显式区分"轻/重波动")。

---

## 4. ③ 统一招生（12 志愿）—— 冲稳保梯度

入口:`buildUniPlan()` → `resetDraft()`(前端 `Zhiyuan.vue`)。

### 4.1 候选池 `bandPool(band)`
`bands[band]` 过滤:`有 school_code` ∧ `commuteOK`(§6.2) → `dedupeByCode`(§6.1) → 按 `ref_rank` 升序(强校在前)。

### 4.2 配比与回填(`STRAT = {冲:3, 稳:5, 保:4}`)
1. 每档取 `min(配额, 池量)`。
2. 不足 12:依 **稳 → 保 → 冲** 顺序补足。
3. 仍不足 12:用 **`够不上`**(同样经 commuteOK 过滤)回填"冲刺"——可通勤优先、再按位次最接近你。
4. **最终整体按 `ref_rank` 升序**:最硬的冲刺/冲在前,**保底在末**。
5. 够不到 12 则留空(不放劣质/超通勤候选)。

### 4.3 落表 `resetDraft()`
12 槽填入,每槽默认勾选**合并专业**(§6.1)前 2 个。

### 4.4 逐志愿理由 `slotReason(name)`
- 定性(按 `bandOf`):冲/稳/保;`够不上` 显示为 **"冲刺"**(cls `band-刺`)。
- 文案:位次差(`ref_rank` vs `rank`)+ 分差(有 `score_lines.2025` 时:`est_score − line`)。
- 因子:🚌通勤km(超限标注) / 🛏住宿 / 🏫特色(style 前 14 字) / 🎓高考(民间)。
- 风险:`volatility ≥ 0.25` → "近年线波动大、谨慎"。
- 随选校实时更新(不是写死在 plan 上)。

### 4.5 顶部总览 `uniSummary`
计 `刺/冲/稳/保` + 末位保底校名;说明"按分数优先、依志愿录取,冲刺/冲在前、末尾保底"。

---

## 5. ② 指标分配 —— upgrade-only（与③相反！）

> 核心:此批在③之前、**录取即锁定**。所以只填"**比你统招能上的更好、你统招够不上**"的;**你统招本来就够得着的(稳/保)绝不自动填**,否则锁定即作废统招、把自己锁低。

### 5.1 校额到校（8 志愿）
- 候选 `xedEligible`:该**初中**的官方校额名额 `by_school`(全列,下拉用,**不**做通勤过滤)。
- 研判 `xedRecommend`:join 公办 card → tag:
  - `worth` ✅值得冲:`ref ≤ rank×0.95`(统招位次比你靠前→统招够不上→校额=机会)
  - `waste` ⚠️统招本可达:`ref ≥ rank×1.1`(统招够得着→占校额浪费)
  - `similar` ≈相当 / `unknown`(位次未知)
  - 附 `over_max`(用于自动填的通勤过滤)。按 `ref` 升序。
- **缺省填 `prefillXed`**:仅 `tag==='worth'` **且** `commuteOK`(未选住宿则排除超通勤)。≈相当/统招本可达/超通勤 → 不自动填(下拉仍可手动加)。
- 理由 `xedReason`:tag + "统招位次≈X 比你靠前→统招够不上、校额(校内排名)才有机会" + caveat(校内排名+志愿顺序、无官方各校线、录取即锁定)。
- 录取性质:**校内竞争**(只和本初中同学比),非全区。

### 5.2 市级统筹（4 志愿）
- 候选 `tcEligible`:统筹二(`tcEr`)+ 统筹一(`tcYi`),每校 `tcJudge`(§3.2,比各校**统招线**,统筹实际线官方不公开、通常更低 → 偏保守)。
- **缺省填 `prefillTongchou`**:**只填 `Δ ≤ 0` 的 reach**(你估分 ≤ 其统招线 = 够一够的 upgrade;没中自动落到统招、无损失)。**排除稳/保**(Δ>0=你高于其线=会锁进比你弱的外区校=陷阱)与**待核**。
  - 入选优先级:**搏 → 冲 → 够不上(仅兜底回填空位)**;
  - 展示顺序:**从高到低**(够不上→搏→冲),`够不上` 显示为"冲刺"。
- 理由 `tcReason`:档(搏/冲/冲刺)+ "统筹X·区·投朝阳N名·统招线L·Δ" + caveat:
  - "没中不影响统招;一旦录取即锁定、放弃统招——确认你确实更想去这所外区校再保留";
  - "全市按分竞争;比统招线、统筹线通常更低(偏保守);**朝外能否报该校/分到名额须查简章**(待核)";统筹一另标"名校本部·门槛高"。
- **注意**:统筹是去外区/郊区的选择,**不套用本区通勤上限**(距离作信息显示,见 §6.2)。

### 5.3 提前招生（手填）
2026 贯通并入③;特长/中职自主/登记入学无结构化代码 → 手填 + 说明,不自动建议(诚实)。

---

## 6. 跨批次公共机制

### 6.1 录取代码去重 + 专业合并
- `dedupeByCode(cards)`:同 `school_code` 只留一条,**保留本部**(名称不含"校区/（")。
- `mergedMajorsByCode`:同代码各校区专业**并集**,校区专业名后标注(如 `普通班（北苑莲葩园）`)。
- `majorsOf(name)` 返回合并专业;`resetDraft` 默认取合并专业前 2。
- 范围:**仅草表**(③/校额);查学校/地图仍分校区显示(便于家长区分校址/住宿)。
- 案例:和平街一中(105004)本部01走读 + 北苑莲葩园02住宿 = 一个志愿、两专业。

### 6.2 通勤过滤(自动填报层施加,前端 `reachByCommute`)
正确规则(单一口径):
`reachByCommute(km, schoolBoarding) = (km ≤ max_km) || (form.boarding && schoolBoarding)`
- ≤通勤上限 → 可达。
- 超上限 → **只有"你接受住宿 ∧ 该校确实提供住宿"才可达**;远校不提供住宿 = 没法住校 = 照样每天通勤 → 排除。
- 用**原始 km**(`c.nearest.km`),不依赖 `over_max`——后端在 `boarding=true` 时 `effective_max_km=None` 会把所有校 `over_max` 清成 false,故 over_max 不可作为住宿模式下的判据。
- 应用于:③`bandPool`(含够不上回填)、校额`prefillXed`。
- **下拉永远列全**(`selectable`/校额下拉不过滤,可手动选远校)。
- **市级统筹不受此约束**(外区性质;`tcReason` 显示 🚌距离作参考)。
- ⚠️ 历史 bug(已修):曾用 `form.boarding || !over_max`,导致勾住宿时**不提供住宿的远校**(东方德才13.9km/二外23.3km/团结湖12.2km,boarding=False)也混进保底。

### 6.3 身份资格
`identity ∈ {jjyj 京籍应届, feijing 非京籍, wangjie 往届/回京}`
- `canPuhao = identity!=='feijing'`(非京籍只中职)
- `canIndicator = canGuantong = identity==='jjyj'`(②指标分配、贯通仅京籍应届)
- 各批次按资格灰显 + 说明。

---

## 7. 关键决策记录（为什么这么改 —— 迭代沉淀）

| # | 决策 | 原因 |
|---|---|---|
| D1 | ③ 从"冲全填→稳→保罗列"改为 **3/5/4 梯度 + 保底** | 原逻辑可能整屏全冲、无保底 |
| D2 | ③ 不足 12 用"**够不上**"回填**冲刺** | "空着也是空着";够不上是 reach,没中不影响后续 |
| D3 | ② **upgrade-only**(最关键修正) | 统筹原按"稳优先"填,把"你远高于其线的外区校(稳)"填最前→录取即锁定、放弃统招、锁进更差校。改为只填 Δ≤0 reach;校额去掉≈相当、只留✅值得冲 |
| D4 | 统筹排序 **搏→冲优先、够不上兜底**,展示从高到低 | "先搏后冲;没合格的再往上写够不着的" |
| D5 | **录取代码去重**(和平街一中 105004) | 同代码多校区算一个志愿,否则重复占位浪费 |
| D6 | **通勤过滤 gated on 住宿**(东方德才/工大附中等) | 未选住宿+设上限时,只能靠住宿够到的远校不该进自动推荐 |
| D7 | 抽 `JudgeLegend.vue` 统一研判图例 | 统筹表/查学校浏览器复用,口径只定义一次 |

---

## 8. 已知局限 / 待办 / 改进挂钩

- **两套 band 口径**(§3)与**波动阈值 0.25/0.40 不一致** → 待统一。
- **分差**仅在有 `score_lines.2025` 时显示;位次为主口径。
- **统筹"朝外能否报/分到名额"是简章级**,本系统标"待核"——有了朝外逐校统筹名额可升级研判。
- **校额"校内竞争优势"未建模**:✅值得冲基于统招位次,未量化校内排名概率(朝外强初中校内竞争激烈,实际更难)。
- **配比可调**:`STRAT` 现为定值 3/5/4;可做"保守↔进取"滑块(曾作为选项)。
- **①提前招生**无结构化数据,长期手填。
- **2026 简章刷新**:计划/代码/校额/统筹名额 7 月发布后须刷新;新校并入。
- **其他区扩展**:换 `<district>.yaml` + 对应 xeddx/tongchou/coords/codes 即可复用本算法。

---

## 9. 代码地图（实现位置）

**后端** `scripts/admission/recommend.py`:`classify`(band)、`rank_to_score`(估分)、`build_result`(bands/est_score/public_list/xeddx/tongchou/...)、`SAFETY_MARGIN/REACH_MARGIN/VOLATILITY_THRESHOLD`。

**前端** `web/src/zhiyuan/Zhiyuan.vue`:
- 公共:`scoreBand`、`dedupeByCode`、`mergedMajorsByCode`、`majorsOf`、`bandOf`、`findCard`、`commuteOK`(在 `bandPool` 内)。
- ③:`bandPool`、`STRAT`、`buildUniPlan`、`resetDraft`、`slotReason`、`uniSummary`、`selectable`。
- ②校额:`xedEligible`、`xedRecommend`、`prefillXed`、`xedReason`、`xedSummary`、`XED_TAG`、`XED_FULLNAME`。
- ②统筹:`tcEr/tcYi`、`tcJudge`、`tcEligible`、`prefillTongchou`、`tcReason`、`tcSummary`。
- 导出:`copyAll`(三批次 + 理由)。
- 组件:`JudgeLegend.vue`(研判图例)。

**数据** `knowledge-base/admission/beijing/`:`chaoyang.yaml`、`chaoyang_admission_codes.json`、`chaoyang_coords.json`、`chaoyang_xeddx.yaml`、`2025_sjtongchou_chaoyang.json`、`chaoyang_new2026.yaml`、`2025_tongzhao_plan.json`。

---

_最后更新:2026-06。基于当时线上算法(commit `cddfe5df` 附近)整理。_
