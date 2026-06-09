#!/usr/bin/env python3
"""用 DeepSeek + 阿里 Qwen 双模型交叉补全/核对朝阳 27 公办普高高考数据。

策略(用户拍板):缺失/存疑数据用大模型补充与核对;两模型互为交叉源。
  - 两模型都给值且接近 → 取均值, qual='~'(高度一致用'='), 较可信
  - 仅单模型给值 → qual='?'(若该模型自评 low)否则 '~', 低置信
  - 两模型冲突 → 取均值但 qual='?'(存疑), note 记两值
  - 都为 null → 跳过(不编造)
产出(对齐 build_timeseries 的 raw_extracts/*gaokao*.json 格式,每年一文件):
  raw_extracts/chaoyang_gaokao_<year>_llm.json   ← 被 build_timeseries glob 入 gaokao.jsonl
                                                    (字母序 'llm' < 源名, 已有 curated 覆盖之, 只补空)
  raw_extracts/chaoyang_llm_gk_audit.json        ← 全量审计(两模型原始+裁决), 不被 glob
全部 source_tier=T3 / basis=LLM(ds+qw) / 仅参考·待人工核。
"""
import concurrent.futures as cf
import json
import os
import re
import urllib.request
from pathlib import Path

import yaml

KB = Path(__file__).resolve().parents[3] / "knowledge-base/admission/beijing"
RAW = KB / "raw_extracts"
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
QW_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

# 指标 → (raw_extracts key, 类型 ratio|count, 一致阈值)
METRICS = {
    "yiben":   ("tk",   "ratio", 0.06),
    "benke":   ("bk",   "ratio", 0.06),
    "qingbei": ("qb",   "count", 0.20),
    "n685":    ("n685", "count", 0.25),
    "n700":    ("n700", "count", 0.25),
    "top":     ("top",  "count", 0.01),   # 最高分:绝对≤5
    "avg":     ("avg",  "count", 0.05),
    "np":      ("np",   "count", 0.15),
}
YEARS = [2022, 2023, 2024, 2025]

PROMPT = """你是北京中考/高考数据研究员。请给出【北京市朝阳区·{name}】的历年高考成绩硬数据。

只回答你确实知道的、来自学校喜报/官网/正规媒体的数据;不知道就填 null,**绝对不要编造或估算**。
需要的指标(每年 2022-2025 各给一组,没有的年份/指标填 null):
- yiben: 特控率/一本率(小数, 如 0.95 表示95%)
- benke: 本科率(小数)
- qingbei: 清华+北大录取人数(整数)
- n685: 685分以上人数(整数; 近年清北裸分线档)
- n700: 700分以上人数(整数)
- top: 全校最高分(整数)
- avg: 文理科年级平均分(整数, 模糊可填代表值)
- np: 参加高考人数(整数)

每个有值的指标用对象 {{"v": 数值, "conf": "high|medium|low", "src": "简短依据"}}。
conf 表示你对该数字的把握; src 写来源类型(如"学校喜报"/"官网"/"媒体报道"/"印象不确定")。

严格输出 JSON,结构:
{{"school":"{name}","years":{{"2022":{{"yiben":{{"v":..,"conf":..,"src":..}},...}},"2023":{{...}},"2024":{{...}},"2025":{{...}}}}}}
没有数据的指标整个键省略或填 null。不要输出任何 JSON 以外的文字。"""


def call(url, key, model, msg):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": msg}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"]


def parse_json(txt):
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {}


def ask_deepseek(name):
    return parse_json(call("https://api.deepseek.com/chat/completions", DS_KEY,
                           "deepseek-chat", PROMPT.format(name=name)))


def ask_qwen(name):
    return parse_json(call("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                           QW_KEY, "qwen-max", PROMPT.format(name=name)))


def getv(doc, year, metric):
    """从模型 doc 取 (value, conf) 或 (None,None)。"""
    try:
        cell = (doc.get("years") or {}).get(str(year), {}).get(metric)
    except Exception:
        return None, None
    if cell is None:
        return None, None
    if isinstance(cell, dict):
        v = cell.get("v")
        return (v, cell.get("conf", "low")) if v is not None else (None, None)
    if isinstance(cell, (int, float)):
        return cell, "low"
    return None, None


def reconcile(dv, dc, qv, qc, kind, thr):
    """两模型一个指标的裁决 → (value, qual, note) 或 None。"""
    if dv is None and qv is None:
        return None
    if dv is not None and qv is not None:
        if kind == "ratio":
            close = abs(dv - qv) <= thr
        elif thr < 1:        # top: 绝对阈值用 thr 当比例? 这里 top thr=0.01→用相对
            close = abs(dv - qv) <= max(5, abs(qv) * thr)
        else:
            close = abs(dv - qv) <= max(2, abs(qv) * thr)
        val = round((dv + qv) / 2, 3) if kind == "ratio" else round((dv + qv) / 2)
        if close:
            qual = "=" if (kind == "ratio" and abs(dv - qv) <= thr / 2) else "~"
            return val, qual, "ds+qw一致"
        return val, "?", f"ds={dv}/qw={qv}冲突取均"
    # 单模型
    v, c = (dv, dc) if dv is not None else (qv, qc)
    who = "ds" if dv is not None else "qw"
    return (round(v, 3) if kind == "ratio" else round(v)), ("~" if c in ("high", "medium") else "?"), f"仅{who}({c})"


def school_names():
    """27 公办名(chaoyang.yaml)。校区合并:北苑莲葩园 与 和平街一中 同校高考数据,查一次复制。"""
    cy = yaml.safe_load(open(KB / "chaoyang.yaml", encoding="utf-8"))
    names = [s["name"] for s in cy.get("schools", []) if s.get("name")]
    dup = {}   # 查询名 → 额外要写入的同校校区名
    query = []
    for n in names:
        if "校区" in n:           # 和平街一中（北苑莲葩园校区）
            base = re.sub(r"（.*?校区）", "", n)
            dup.setdefault(base, []).append(n)
        else:
            query.append(n)
    return query, dup


def main():
    assert DS_KEY and QW_KEY, "需 DEEPSEEK_API_KEY + DASHSCOPE_API_KEY"
    query, dup = school_names()
    print(f"查询 {len(query)} 校(校区合并 {sum(len(v) for v in dup.values())} 个) × 2 模型 …")

    def work(name):
        out = {"name": name}
        for who, fn in (("ds", ask_deepseek), ("qw", ask_qwen)):
            try:
                out[who] = fn(name)
            except Exception as e:
                out[who] = {"_err": repr(e)[:200]}
        return out

    raw = {}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(work, query):
            raw[r["name"]] = r
            de = "✗" if r["ds"].get("_err") else "✓"
            qe = "✗" if r["qw"].get("_err") else "✓"
            print(f"  {de}ds {qe}qw  {r['name']}")

    # 裁决 → per-year rows
    audit = {}
    per_year = {y: {} for y in YEARS}   # year -> name -> {tk:..,tk_qual:..}
    for name, r in raw.items():
        ds, qw = r.get("ds", {}), r.get("qw", {})
        audit[name] = {"ds": ds, "qw": qw, "decided": {}}
        for y in YEARS:
            row = {}
            for metric, (rk, kind, thr) in METRICS.items():
                dv, dc = getv(ds, y, metric)
                qv, qc = getv(qw, y, metric)
                dec = reconcile(dv, dc, qv, qc, kind, thr)
                if dec is None:
                    continue
                val, qual, note = dec
                row[rk] = val
                row[rk + "_qual"] = qual
                row[rk + "_note"] = note
                audit[name]["decided"][f"{y}.{metric}"] = {"ds": dv, "qw": qv, "value": val, "qual": qual, "note": note}
            if row:
                row["abbr"] = name
                row["note"] = "LLM(ds+qw)交叉·待人工核"
                per_year[y][name] = row
                for d in dup.get(name, []):     # 校区复制同校数据
                    drow = dict(row); drow["abbr"] = d
                    per_year[y].setdefault("__dup__", []).append(drow)

    # 写每年 raw_extracts 文件
    for y in YEARS:
        rows = []
        names = {}
        for k, v in per_year[y].items():
            if k == "__dup__":
                for dr in v:
                    rows.append(dr); names[dr["abbr"]] = dr["abbr"]
            else:
                rows.append(v); names[v["abbr"]] = v["abbr"]
        if not rows:
            continue
        doc = {
            "year": y, "source_name": "LLM交叉(DeepSeek+Qwen)", "source_tier": "T3",
            "source_url": "llm://deepseek+qwen", "collected": "2026-06",
            "warning": "大模型交叉补全·非官方·待人工核; qual: '='强一致 '~'近似/单源 '?'存疑/冲突",
            "alias_to_name": names, "rows": rows,
        }
        p = RAW / f"chaoyang_gaokao_{y}_llm.json"
        json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"写 {p.name}: {len(rows)} 校")

    json.dump(audit, open(RAW / "chaoyang_llm_gk_audit.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"写 chaoyang_llm_gk_audit.json: {len(audit)} 校审计")


if __name__ == "__main__":
    main()
