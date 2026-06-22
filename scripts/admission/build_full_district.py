#!/usr/bin/env python3
"""装配某区「对标朝阳」的完整 <district>.yaml。

数据来源(全部已存在/可增量补):
  1. districts/<py>_admission_codes.json  —— 正名 + 专业(班) + 学校码(权威校名表)
  2. districts/<py>_coords.json           —— GCJ-02 坐标 → location
  3. knowledge-base/admission/beijing/<py>.yaml(若已存在)—— 历史 scores/level/note
       (东西海是官方 3 年线;名称为简称,经 alias_resolve join 到正名)
  4. districts/<py>_enrich.yaml(可选,研究 Agent 产出)—— features/gaokao/note/scores 增补
       结构: {schools: {正名: {level?, note?, features?{style,tags,source}, gaokao?{年:文本,source},
                              scores?{年:{total,score,rank}}, scores_source?, scores_conf?}}}

输出: knowledge-base/admission/beijing/<py>.yaml(朝阳 schema)。
原则: scores 只在能 resolve 到正名时挂;resolve 不了→不挂(标 unresolved 打印),绝不错配。

用法: python scripts/admission/build_full_district.py haidian xicheng dongcheng
      python scripts/admission/build_full_district.py --all
"""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from alias_resolve import build_resolver  # noqa: E402

KB = Path(__file__).resolve().parents[2] / "knowledge-base/admission/beijing"
DIST = KB / "districts"

CN = {"dongcheng": "东城", "xicheng": "西城", "haidian": "海淀", "fengtai": "丰台",
      "shijingshan": "石景山", "mentougou": "门头沟", "fangshan": "房山",
      "tongzhou": "通州", "shunyi": "顺义", "changping": "昌平", "daxing": "大兴",
      "huairou": "怀柔", "pinggu": "平谷", "miyun": "密云", "yanqing": "延庆",
      "chaoyang": "朝阳"}


def _snm():
    p = Path(__file__).resolve().parents[2] / \
        "knowledge-original/beijing-highschools/score_name_mapping.json"
    if not p.exists():
        return {}
    m = json.load(open(p, encoding="utf-8"))
    return {k.split("|", 1)[-1]: v["matched_name"]
            for k, v in m.items() if v.get("confidence", 0) >= 1.0}


def _aliases(py):
    p = DIST / "_name_aliases.json"
    return json.load(open(p, encoding="utf-8")).get(py, {}) if p.exists() else {}


def _level_from_code(code):
    return "优质高中（示范/特色）" if str(code).startswith("1") else "普通高中"


_CONF_ORD = {"low": 0, "medium": 1, "high": 2}
# 北京中考各年满分(与朝阳口径一致):2023=660 / 2024=670 / 2025=510
YEAR_TOTAL = {"2022": 580, "2023": 660, "2024": 670, "2025": 510}


def _src_names(src):
    """source 可能是 str / [{name,url}] / [str]，统一成一行文本。"""
    if not src:
        return ""
    if isinstance(src, str):
        return src
    out = []
    for x in src:
        if isinstance(x, dict):
            out.append(x.get("name") or x.get("url") or "")
        else:
            out.append(str(x))
    return "; ".join(p for p in out if p)


# agent 产出字段名不统一,做别名归一(分数线尤其多变体)
_SCORE_KEYS = ("score", "admit_min", "min_score", "admission_min", "admit_min_score",
               "admission_score", "cutoff", "lowest", "min", "min_admit")
_TOTAL_KEYS = ("total", "total_score", "full", "full_score")


def _pick(it, keys):
    for k in keys:
        if it.get(k) is not None:
            return it[k]
    return None


def _one_rec(it):
    """从一个 score 条目里抽 {total,score,rank}(容字段别名);至少要有 score。"""
    sc = _pick(it, _SCORE_KEYS)
    if sc is None:
        return None
    rec = {"score": sc}
    tot = _pick(it, _TOTAL_KEYS)
    if tot is not None:
        rec["total"] = tot
    if it.get("rank") is not None:
        rec["rank"] = it["rank"]
    return rec


def _norm_scores(en):
    """把 enrich 的 scores 归一成 ({年str:{total,score,rank}}, source_str, conf)。
    兼容 dict(年→{..}) 或 list([{year,..}]) 两种结构 + 多种分数/来源字段别名。
    返回 (scores, source, conf);无则 (None,None,None)。"""
    raw = en.get("scores")
    if not raw:
        return None, None, None
    scores, srcs, confs = {}, [], []
    if isinstance(raw, list):
        for it in raw:
            if not isinstance(it, dict) or it.get("year") is None:
                continue
            rec = _one_rec(it)
            if rec:
                scores[str(it["year"])] = rec
            if it.get("conf"):
                confs.append(it["conf"])
            srcs.append(_src_names(it.get("source") or it.get("sources")))
    elif isinstance(raw, dict):
        for y, v in raw.items():
            if isinstance(v, dict):
                rec = _one_rec(v)
                if rec:
                    scores[str(y)] = rec
                if v.get("conf"):
                    confs.append(v["conf"])
                if v.get("source") or v.get("sources"):
                    srcs.append(_src_names(v.get("source") or v.get("sources")))
    if not scores:
        return None, None, None
    for y, rec in scores.items():        # 满分按朝阳口径强制(纠正 agent 的 660/670 口径)
        if y in YEAR_TOTAL:
            rec["total"] = YEAR_TOTAL[y]
    src = en.get("scores_source") or "; ".join(s for s in dict.fromkeys(srcs) if s)
    conf = en.get("scores_conf")
    if not conf and confs:
        conf = min(confs, key=lambda c: _CONF_ORD.get(c, 0))   # 取最保守
    return scores, src or None, conf or "low"


def build(py):
    cn = CN[py]
    codes_p = DIST / f"{py}_admission_codes.json"
    if not codes_p.exists():
        print(f"  ✗ {py}: 无 admission_codes,跳过")
        return None
    codes = json.load(open(codes_p, encoding="utf-8"))["schools"]
    coords = json.load(open(DIST / f"{py}_coords.json", encoding="utf-8")).get("schools", {}) \
        if (DIST / f"{py}_coords.json").exists() else {}

    zheng = [s["name"] for s in codes.values()]
    R = build_resolver(zheng, overrides=_aliases(py), snm=_snm())

    # ---- 历史 scores/level/note(老 yaml,简称)→ 按正名归集 ----
    hist = {}  # 正名 -> {scores, level, note}
    unresolved = []
    old_p = KB / f"{py}.yaml"
    if old_p.exists():
        old = yaml.safe_load(open(old_p, encoding="utf-8")) or {}
        for s in old.get("schools", []):
            zn = R(s.get("name"))
            if not zn:
                if s.get("scores"):
                    unresolved.append(s.get("name"))
                continue
            cur = hist.get(zn)
            cand = {"scores": s.get("scores") or {}, "level": s.get("level"),
                    "note": s.get("note"), "_orig": s.get("name")}
            # 撞车(校区)取 score 年份多者,平局取原名短者(主校)
            if cur is None or (len(cand["scores"]) > len(cur["scores"])) or \
               (len(cand["scores"]) == len(cur["scores"]) and len(cand["_orig"]) < len(cur["_orig"])):
                hist[zn] = cand

    # ---- enrich(正名键)----
    enrich = {}
    ep = DIST / f"{py}_enrich.yaml"
    if ep.exists():
        enrich = (yaml.safe_load(open(ep, encoding="utf-8")) or {}).get("schools", {}) or {}

    # ---- 组装 schools(以 codes 正名为准)----
    schools = []
    for s in sorted(codes.values(), key=lambda x: x["name"]):
        zn = s["name"]
        co = coords.get(zn) or {}
        en = enrich.get(zn) or {}
        h = hist.get(zn) or {}
        # enrich 优先(网传 T3),否则历史官方线;年份键统一成字符串
        en_scores, en_src, en_conf = _norm_scores(en)
        if en_scores:
            scores, sc_src, sc_conf, sc_official = en_scores, en_src, en_conf, False
        else:
            scores = {str(k): v for k, v in (h.get("scores") or {}).items()}
            sc_src, sc_conf, sc_official = None, None, True
        loc = None
        if co:
            loc = {"campus": co.get("formatted") or zn,
                   "lat": co.get("lat"), "lon": co.get("lon"),
                   "confidence": co.get("conf", "medium"),
                   "source": "高德 geocode（统招报到校区，待电话核实）"}
        rec = {
            "name": zn,
            "school_code": s.get("school_code"),
            "location": loc,
            "level": en.get("level") or h.get("level") or _level_from_code(s.get("school_code")),
            "note": en.get("note") or h.get("note") or "",
            "features": en.get("features") or {},
            "gaokao": {str(k): v for k, v in (en.get("gaokao") or {}).items()},
            "scores": scores,
        }
        if en.get("scores_source"):
            rec["scores_meta"] = {"source": en["scores_source"],
                                  "confidence": en.get("scores_conf", "low")}
        elif h.get("scores"):
            rec["scores_meta"] = {"source": "官方录取分数线（历史 3 年）", "confidence": "high"}
        schools.append(rec)

    n_score = sum(1 for s in schools if s["scores"])
    n_coord = sum(1 for s in schools if s["location"])
    n_feat = sum(1 for s in schools if s["features"])
    n_gk = sum(1 for s in schools if s["gaokao"])

    out = {
        "meta": {
            "quality_status": "assembled",
            "source": "统招计划(codes)+高德坐标+历史录取线(官方/网传)+民间特色/高考",
            "updated": "2026-06-22",
            "builder": "build_full_district.py",
            "note": "对标朝阳 schema 自动装配;录取线缺失或低置信处以 scores_meta 标注。",
        },
        "district": f"{cn}区",
        "region": "北京市",
        "schools": schools,
    }
    out_p = KB / f"{py}.yaml"
    with open(out_p, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False, width=120)
    flag = "✓有线" if n_score else "·校库(无线)"
    print(f"  {flag} {py}: {len(schools)}校 | 线{n_score} 坐标{n_coord} 特色{n_feat} 高考{n_gk}"
          + (f" | ⚠未挂线(resolve失败): {unresolved}" if unresolved else ""))
    return {"py": py, "schools": len(schools), "scores": n_score, "coords": n_coord,
            "features": n_feat, "gaokao": n_gk, "has_lines": n_score > 0}


def main():
    args = sys.argv[1:]
    if not args or args == ["--all"]:
        pys = [p.stem.replace("_admission_codes", "")
               for p in sorted(DIST.glob("*_admission_codes.json"))
               if p.stem.replace("_admission_codes", "") in CN]
    else:
        pys = args
    print(f"装配 {len(pys)} 区:")
    summ = [build(py) for py in pys]
    return [s for s in summ if s]


if __name__ == "__main__":
    main()
