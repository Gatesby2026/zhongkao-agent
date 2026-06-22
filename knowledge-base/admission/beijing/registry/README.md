# 学校实体注册表(registry) —— 运行时唯一数据源

**架构(B 重构后,2026-06):**

```
原始采集(各渠道) ──> 扁平文件(build 输入,不在运行时读) ──> build_registry*.py ──> registry/ ──> recommend.py(运行时只读这里)
```

- **registry/<区>/<id>.yaml** = 每校一个稳定实体:`id` + `canonical_name`/`short_name`/`aliases[]`(所有写法,根治字符串错配) + `campuses[]`(坐标/住宿) + `admissions[]`(统招/校额到校/市级统筹 的 code+major+lines+pred) + `rollup`(features/gaokao/campus_life + private_record/vocational_record/new2026_record 完整渠道记录) + `_codes[]`。
- **registry/<区>/_channel_meta.yaml** = 区级渠道数据:统筹(tongchou)/校额(xeddx)/各渠道 meta。
- **registry/_guantong.yaml** = 全市贯通项目。
- `recommend.py` 通过 `_USE_REGISTRY`(默认开;`REGISTRY_SOURCE=0` 回滚旧扁平)读 registry:load_district/private/vocational/new2026/xeddx/tongchou/guantong/admission_codes 全部来自此处;坐标由实体 campus 内嵌。

**扁平文件(`<区>.yaml` / `*_admission_codes.json` / `*_coords.json` / `*_private.yaml` / `*_vocational.yaml` / `*_new2026.yaml` / `*_xeddx.yaml` / `2025_sjtongchou_*.json` / `beijing_guantong.yaml`)= build 输入,运行时不再读取**。改数据 → 改采集/扁平 → 重跑 build_registry*.py → registry 更新。

**重建:** `python scripts/admission/registry/build_registry.py`(朝阳) + `build_registry_all.py`(其余15区);校验 `regress_snapshot.py`(by-id 回归)。

**同校多校区(统一方案):**
- **判定**:不同学校码 = 独立学校(哪怕叫"X分校",如四中房山分校/人朝石油分校),各自一等实体;**同一学校码 + 多招生单元指向不同校区** = 同校多校区(全市当前仅和平街一中:码105004,01本部/02北苑莲葩园)。
- **分层**:学校级共享(校名/品牌/办学层次/特色/高考出口/校额到校/直升);**校区级各异**(地址坐标→通勤、录取线+区位次、招生码/专业、计划数、住宿、班型、校园生活)。
- **落地**:registry 实体含多 `campuses[]`,`admissions[]` 每单元绑 campus 各挂 lines;`recommend._district_from_registry` 对"≥2 校区各有独立线"的实体**拆成多张卡**(本部沿用正名,余以校区名括号区分),各按**本校区自身录取线**判档(校级 2026 预估只代表本部,非本部校区改用自身历史线);坐标/住宿/距离各自独立,uid 含校名不碰撞。**by-id 回归:与扁平 0 差异**。
