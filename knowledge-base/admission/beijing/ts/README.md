# ts/ — 跨年时序长表(分析主存)

把各年快照拍平成 tidy 长表,供趋势/预测/增值/回测分析。设计见 `docs/design/ZHIYUAN-DATA-COLLECTION.md`。

## 文件
- `schools.yaml` — 学校主表,**uid 主键**(招生编码,无则 `统招:name`)。跨年/跨源 join 全靠 uid。
- `lines.jsonl` — ★录取线时序。一行 = 学校×年×批次×来源。关键列:
  `uid, name, year, batch(统招|校额到校|市级统筹|贯通), campus, major_code, score, score_total(510/670), rank(区位次), source_url, source_tier(T1-T4), collected, confidence, note`
  - **跨年比用 `rank`(区位次)**;`score` 仅当年可比(总分变过)。
- `gaokao.jsonl` — 高考出口/增值原料(待采)。列:`uid,name,year,metric,value,denom,source_url,source_tier,confidence,note`。
- `plans.jsonl` — 招生计划时序(待采)。
- `yifenyiduan/<year>_<region>.csv` — 一分一段表(待采)。
- `provenance.jsonl` — 数据血缘/多源冲突审计(待建)。

## 加数据的方式(append,不覆盖别源)
1. 原始落 `knowledge-original/zhiyuan/raw/`(带 url/tier/sha,见 `_raw_index.jsonl`)。
2. 写 normalize 脚本(`scripts/admission/normalize/`)解析 → append 到对应 `ts/*.jsonl`,**每条带 uid + source + tier + confidence**。
3. 同一 `uid×year×指标` 多源 → 都留,resolved 值与方法记 `provenance.jsonl`。

## 重新生成本仓内置样板(chaoyang.yaml 历年统招线)
```
python3 scripts/admission/normalize/build_timeseries.py
```
当前内置:27 校 × 2023–2025 统招线+区位次(原始 bjeea,项目已核,tier=T1)。

## 红线
- 民间数据(尤其高考)标 T3/T4 + 低置信,不作唯一依据。
- 缺数据留空,不脑补;口径(总分/位次范围)随每条标注。
