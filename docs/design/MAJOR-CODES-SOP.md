# 学校「可填报专业(班)」数据 SOP — 2025 定准 + 2026 一次性更新

> 目的:把「每校可填报的专业(班)代码+名称」做准、把方法固定下来,2026 计划发布后一次跑通、一次替换。
> 第一原则:专业代码/名称/计划数全部来自 **bjeea 官方《统招计划册》(T1)**,不臆造;低可信处标注。

## 0. 关键结论:专业不区分「住宿/走读」

- 2025 全市统招计划 648 行,专业名里 **0 处**含「住宿/走读/寄宿/通宿」。
- 专业(班)代码区分的是 **班型**:普通班 / 实验班(科学创新等) / 中外项目班(中美/中英) / 外语特色班 等,**不区分住宿与走读**。
- **住宿是「校级」属性**(某校提不提供住宿、是否仅限远距离生),建模在校级字段 `boarding`
  (来源:`chaoyang_private.yaml` / `chaoyang_vocational.yaml` / `campus_life.json` / 统筹 json),
  **不进专业代码**。家长填的是专业(班)码;住宿单独按学校政策安排。
- ⇒ 草表/前端展示专业时**不需要、也不应该**按住宿/走读拆专业。

## 1. 数据流(固定管道)

```
bjeea《统招计划册》JPG (T1 官方唯一权威)
   │  extract_plan_tencent.py  (腾讯表格 OCR;已含 P2-12 代码↔校名错配侦测 missed_code_suspect)
   ▼
2025_tongzhao_plan.json   (全市 学校×专业 行;带 warning + name_raw + flags)
   │  link_chaoyang_codes.py  (CODE_MAP 人工核对 name→code;_clean_major 规范汉字间空格)
   ▼
chaoyang_admission_codes.json  (27 校 → school_code + majors[]; plan_year/source_tier/warning)
   │  recommend.build_result → 草表「专业(班)」chip(每校自动选前 2 个推荐专业)
   ▼
前端 DraftRow 展示;最终以官方网报系统为准
```

## 2. 2025 现状(本次已定准的部分)

- 27/27 校全部链上 school_code,共 36 个专业(班)行。
- 已修:OCR 把 2 字词拆开的空格(「合 作」→「合作」、「实 验」→「实验」)——`_clean_major` 汉字间空格规范化,2026 重跑自动生效。
- 已修:`和平街一中（北苑莲葩园校区）` 因 CODE_MAP 用旧名「莲葩园中学」而漏链 → 改用现名,27/27。
- 已标:`plan_year:2025` / `source_tier:T1` provenance。

**仍待做(需官方册)**:逐校核对「专业是否齐、代码是否对、学制/加试是否准」——OCR 未逐行人工复核,
属完整性/正确性核验,须拿 bjeea 2025/2026 官方册逐校比对。

## 3. 逐校核对清单(accuracy checklist)

对每所学校,对照官方册确认:
1. **学校代码** 6 位正确(105xxx 区示范/优质、205xxx 一般/分校/民办)。
2. **专业(班)无遗漏**:官方册该校有几个专业码,就有几行(漏码会被 `missed_code_suspect` 标出,重点查)。
3. **专业代码+名称** 一致(名称经汉字间空格规范化后比对)。
4. **多校区**:同码多校区按 `campus_major` 区分(如和平街一中 01本部/02北苑莲葩园)。
5. **学制/加试/计划数** 与册一致(展示用,非判档)。

## 4. 2026 一次性更新步骤(到点照做)

1. 7 月初 bjeea 发布 2026《统招计划册》→ 抓取 JPG(同 2025 路径)。
2. `python extract_plan_tencent.py`(逐页 OCR)→ 新 `2026_tongzhao_plan.json`;**先看 flags**:
   `missed_code_suspect` / `no_school_code` 的行逐一核源订正。
3. 更新 `link_chaoyang_codes.py`:`PLAN` 指向 2026 文件、`out["plan_year"]=2026`;CODE_MAP 若有
   新校/改名按现 yaml 名补;`python link_chaoyang_codes.py` → 看「27/27 校」无 FLAG。
4. 按 §3 清单逐校核对(27 校工作量小),订正后重跑。
5. 构建 + 部署(recommend 运行时读 `chaoyang_admission_codes.json`)。

> 把方法固定在脚本里(OCR 错配侦测 + 汉字空格规范化 + CODE_MAP 现名 + provenance),
> 2026 只是「换册子、跑管道、过清单」,一次到位。
