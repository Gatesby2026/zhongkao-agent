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

**已知边界:** 和平街一中(北苑莲葩园校区)在 registry 并为本部校区(单实体),扁平里曾作独立填报单元(自带线)——campus 多线建模待细化(影响 1 校)。
