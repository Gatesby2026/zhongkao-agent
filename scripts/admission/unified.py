"""统一学校数据模型适配层（设计文档 §12·步骤1）。

把 build_result 已产出的各类型数据（public_list/private_schools/vocational/
guantong/tongchou/new_schools）规范化成同一个 School 记录：
  公共层 + channels[](录取渠道,各带统一 band/metric) + extra{}(类型专属)
增量、不改原数据文件；前端逐步改用 schools_unified[] 后再替换 per-type 分支。

注：校额到校是"渠道"(挂在公办校上)，但它依赖前端选定的初中，故 channel 由前端
按 xedJudgeByName 追加；本层只产出 统招 / 统筹 / 自主 / 中职 / 贯通 / 新校 渠道。
"""
from __future__ import annotations


def _school(name, type_, district, lat, lon, address, conf, boarding,
            level=None, style=None, tags=None, gaokao=None, dist=None):
    return {
        "id": f"{type_}:{name}",
        "name": name, "type": type_, "district": district,
        "geo": {"lat": lat, "lon": lon, "address": address, "confidence": conf},
        "boarding": boarding,
        "level": level,
        "features": {"style": style, "tags": tags or [], "gaokao": gaokao},
        "commute": dist,                 # {km,mins,over_max,label} 或 None
        "channels": [],
        "extra": {},
    }


def _ch(channel, band, kind, **m):
    """构造一个录取渠道：channel 名 + band(冲/稳/保/搏/够不上/待核/不适用) + metric。"""
    return {"channel": channel, "band": band,
            "metric": {"kind": kind, **{k: v for k, v in m.items() if v is not None}},
            "lines": m.get("lines"), "quota": m.get("quota"), "caveat": m.get("caveat")}


def _norm(n: str) -> str:
    return (n or "").replace("北京市", "").replace("（", "(").replace("）", ")").strip()


def build_unified(result: dict) -> list:
    """从 build_result 的结果片段拼出 schools_unified[]。"""
    out, by_name = [], {}

    # ① 公办普高（统招渠道；后续可能再挂 统筹/校额）
    for c in result.get("public_list", []):
        n = c.get("nearest") or {}
        s = _school(c["name"], "公办普高", result.get("district"),
                    None, None, c.get("address"), c.get("address_confidence"),
                    c.get("boarding"), c.get("level"), c.get("style"),
                    c.get("tags"), c.get("gaokao"),
                    {"km": n.get("km"), "mins": n.get("mins"), "over_max": c.get("over_max")} if n else None)
        s["channels"].append(_ch("统招", c.get("band"), "district_rank",
                                 refRank=c.get("ref_rank"), lines=c.get("score_lines"),
                                 caveat=("不在报名范围" if not c.get("reportable") else None)))
        if c.get("coop"):
            s["extra"]["coop"] = True
        out.append(s); by_name[_norm(c["name"])] = s

    # ② 市级统筹：本区校并入已有公办记录(加统筹 channel)，外区校单独成记录
    tc = result.get("tongchou") or {}
    for tier_key, tier in (("tongchou_yi", "统筹一"), ("tongchou_er", "统筹二")):
        for t in tc.get(tier_key, []):
            if not t.get("faces_chaoyang"):
                continue
            line = t.get("score_2025_tongzhao") if isinstance(t.get("score_2025_tongzhao"), (int, float)) else t.get("score_ref")
            ch = _ch("市级统筹", None, "city_score", refLine=line, lines=t.get("score_lines"),
                     quota=t.get("quota_chaoyang"),
                     caveat="比的是统招线(非统筹实际线,统筹线通常更低,偏保守);band 前端按估分研判")
            ch["tier"] = tier
            host = by_name.get(_norm(t["name"]))
            if host and t.get("district") == "朝阳":      # 本区校：并入公办记录
                host["channels"].append(ch)
            else:                                          # 外区/郊区校：独立记录
                # 同一校名多校区(如人大附本部+通州校区、清华附本部+将台路校区)须带校区区分，否则 name/id 撞键
                campus = t.get("campus")
                disp = t["name"] + (f"·{campus}" if campus else "")
                s = _school(disp, "市级统筹", t.get("district"), t.get("lat"), t.get("lon"),
                            t.get("address"), None, t.get("boarding"), t.get("level"),
                            t.get("style"), t.get("tags"), t.get("gaokao"), t.get("dist"))
                s["extra"] = {"campus": campus, "quota_chaoyang": t.get("quota_chaoyang")}
                s["channels"].append(ch)
                out.append(s)

    # ③ 民办 / 国际（自主渠道·非分数路线）
    for p in (result.get("private_schools") or {}).get("schools", []):
        loc = p.get("location") or {}
        types = []
        if p.get("in_minban_list"):
            types.append("民办普高")
        if p.get("in_intl_list"):
            types.append("国际/双语")
        s = _school(p["name"], "/".join(types) or "民办/国际", result.get("district"),
                    loc.get("lat"), loc.get("lon"), loc.get("address"), loc.get("confidence"),
                    p.get("boarding"), p.get("nature"), None, None, None, p.get("dist"))
        s["extra"] = {"tuition": p.get("tuition"), "curriculum": p.get("curriculum"),
                      "direction": p.get("direction"), "in_minban": p.get("in_minban_list"),
                      "in_intl": p.get("in_intl_list")}
        s["channels"].append(_ch("自主", "不适用", "route_choice",
                                 caveat="多为自主招生/面试,无公开统一录取线;路线(出国/双轨)选择为主"))
        out.append(s)

    # ④ 中职 / 职教（按分·threshold）
    for v in (result.get("vocational") or {}).get("schools", []):
        s = _school(v["name"], "中职/职教", result.get("district"), v.get("lat"), v.get("lon"),
                    v.get("address"), v.get("addr_conf"), v.get("boarding"), v.get("type"),
                    None, None, None, v.get("dist"))
        s["extra"] = {"specialties": v.get("specialties"), "five_year": v.get("five_year")}
        s["channels"].append(_ch("中职", "不适用", "threshold", caveat="统一招生中职类,按分填报"))
        out.append(s)

    # ⑤ 贯通承办院校（全市·380 门槛）
    gt = result.get("guantong") or {}
    projects = gt.get("projects") or []
    for nm, c in (gt.get("school_coords") or {}).items():
        projs = [p for p in projects if p.get("school") == nm]
        s = _school(nm, "贯通", c.get("district"), c.get("lat"), c.get("lon"),
                    None, ("approx" if c.get("geo") == "approx" else None), None,
                    "贯通承办院校", None, None, None, None)
        s["extra"] = {"projects": [{"type": p.get("type"), "major": p.get("major"),
                                    "benke": p.get("benke"), "plan": p.get("plan")} for p in projs],
                      "note": c.get("note")}
        s["channels"].append(_ch("贯通", "不适用", "threshold", refLine=gt.get("overall", {}).get("min_score"),
                                 caveat="7年→本科,380门槛,仅限京籍,2026并入统招"))
        out.append(s)

    # ⑥ 2026 新校（无历史线·代理参考）
    for w in (result.get("new_schools") or {}).get("schools", []):
        s = _school(w["name"], "2026新校", result.get("district"), w.get("lat"), w.get("lon"),
                    w.get("address"), w.get("confidence"), w.get("boarding"),
                    w.get("level"), w.get("style"), None, None, w.get("dist"))
        s["extra"] = {"system": w.get("system"), "analog": w.get("analog"),
                      "direction": w.get("direction")}
        s["channels"].append(_ch("新校待定", "待核", "none",
                                 caveat="新校无历史线,不做研判;看体系+可类比校+说明会"))
        out.append(s)

    return out
