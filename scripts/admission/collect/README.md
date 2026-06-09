# collect/ — 撒网采集脚本(原始入库)

各源抓取脚本放这里:抓回原始页面/PDF/图片 → 落 `knowledge-original/zhiyuan/raw/<source>/...` → 登记 `_raw_index.jsonl`(url/tier/sha/日期)。**只负责拿原始**,解析交给 `../normalize/`。

复用经验:gaokzx curl 直取(见 memory `skill_gaokzx_curl`)、zxxk 逐个下载、计划册图表 OCR(腾讯/qwen-vl,见相关 skill)、WebSearch/WebFetch 找线索。

采集优先级与信源分级见 `docs/design/ZHIYUAN-DATA-COLLECTION.md` §3。

待建脚本(按优先级):
- `lines_bjeea.py` — bjeea 历年录取线公告(T1)→ raw
- `yifenyiduan.py` — 一分一段表(T1)→ raw
- `gaokao_baogao.py` — 学校官微高考喜报(T2/T3)→ raw
