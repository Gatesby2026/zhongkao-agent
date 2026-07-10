#!/usr/bin/env python3
"""
中考志愿填报 · 冲稳保推荐引擎（Phase 1 · CLI 验证版）

核心思路：录取按"区排名/位次"决定，位次跨年可比（见 scoring-system.yaml）。
家长手里有的是孩子一模/二模的区排名 —— 直接用位次做 rank-to-rank 匹配，
无需一分一段表（一分一段表只在中考真实出分后把分数换算成位次时才需要）。

约定：rank 越小越好；学校 scores[year].rank = 该校最后一名被录取者的区位次。
      学生位次 R ≤ 学校录取位次 C 即可录取。

用法：
  python scripts/admission/recommend.py --rank 2500
  python scripts/admission/recommend.py --district chaoyang --rank 2500 --all
"""
import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path

import yaml

import distance as dist_mod

# 学校实体解析(P1):脏名字/代码 → 稳定 school_id。注册表缺失时降级为 no-op,不拖垮主推荐。
sys.path.insert(0, str(Path(__file__).resolve().parent / "registry"))
try:
    from resolve import resolve as _resolve_id, get as _get_school
except Exception:
    _resolve_id = lambda name, district=None: None
    _get_school = lambda sid, district=None: None

_USE_REGISTRY = os.environ.get("REGISTRY_SOURCE", "1") != "0"  # 默认走registry;=0回滚旧扁平
ADMISSION_DIR = Path(__file__).resolve().parents[2] / "knowledge-base" / "admission" / "beijing"

# 官方学校代码 + 专业(班)列表（派生自 bjeea 计划册 OCR，经人工核对）。
# 按区缓存；缺失则返回空 dict（学校卡片不带 admission 字段，前端按无码处理）。
_ADMISSION_CODES_CACHE: dict = {}
_SCORE_BANDS_CACHE: dict = {}


def load_admission_codes(district: str) -> dict:
    """返回 {yaml校名: {school_code, plan_school_name, majors[], campus_major?}}。
    文件：<district>_admission_codes.json（无则空）。"""
    if district in _ADMISSION_CODES_CACHE:
        return _ADMISSION_CODES_CACHE[district]
    if _USE_REGISTRY:        # registry 源:专业(班)/码已随 schools 内嵌(_reg_majors),不读扁平codes
        _ADMISSION_CODES_CACHE[district] = {}
        return {}
    import json as _json
    path = ADMISSION_DIR / f"{district}_admission_codes.json"
    schools = {}
    if path.exists():
        try:
            schools = (_json.loads(path.read_text(encoding="utf-8"))
                       or {}).get("schools", {}) or {}
        except Exception:
            schools = {}
    _ADMISSION_CODES_CACHE[district] = schools
    return schools


_PRIVATE_CACHE: dict = {}


def _registry_channel(district, etype, record_key, meta_key):
    """从 registry 取某渠道的完整记录(rollup[record_key])+ 区级 meta。registry 为唯一源。"""
    reg = _PY2REG.get(district)
    regdir = ADMISSION_DIR / "registry" / (reg or "")
    if not reg or not regdir.exists():
        return None
    recs = []
    for fp in sorted(regdir.glob("*.yaml")):
        if fp.name.startswith("_"):
            continue
        e = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        if e.get("type") == etype and (e.get("rollup") or {}).get(record_key):
            recs.append(e["rollup"][record_key])
    if not recs:
        return None
    cm = {}
    mp = regdir / "_channel_meta.yaml"
    if mp.exists():
        cm = (yaml.safe_load(mp.read_text(encoding="utf-8")) or {}).get(meta_key) or {}
    return {"schools": recs, **cm}


def _registry_meta(district, key):
    """区级渠道数据(统筹/校额)存在 registry/<reg>/_channel_meta.yaml[key];registry 为唯一源。"""
    reg = _PY2REG.get(district)
    if not reg:
        return None
    mp = ADMISSION_DIR / "registry" / reg / "_channel_meta.yaml"
    if not mp.exists():
        return None
    return (yaml.safe_load(mp.read_text(encoding="utf-8")) or {}).get(key)


def load_private_schools(district: str):
    """民办/国际校结构化数据。REGISTRY_SOURCE=1 走 registry(唯一源),否则 <district>_private.yaml。"""
    if district in _PRIVATE_CACHE:
        return _PRIVATE_CACHE[district]
    data = None
    if _USE_REGISTRY:
        data = _registry_channel(district, "民办", "private_record", "private")
    if data is None:
        path = ADMISSION_DIR / f"{district}_private.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
    _PRIVATE_CACHE[district] = data
    return data


def build_private_list(district, district_cn, home, mode, mode_label, max_km, boarding):
    """民办/国际校清单（含到家通勤距离）。返回 {meta, schools[]} 或 None。"""
    data = load_private_schools(district)
    if not data:
        return None
    schools = data.get("schools", [])
    dist_map = {}
    if home:
        pseudo = [{"name": s["name"], "campuses": [{"name": "",
                  "lat": s["location"]["lat"], "lon": s["location"]["lon"]}]}
                  for s in schools if s.get("location", {}).get("lat")]
        _, dist_map = dist_mod.compute_distances(pseudo, home, district_cn, mode)
    out = []
    for s in schools:
        rows = dist_map.get(s["name"], [])
        rd = rows[0][2] if rows else None
        km = round(rd[0] / 1000, 1) if rd else None
        mins = round(rd[1] / 60) if rd else None
        # 寄宿模式不卡距离；非寄宿超上限标记（与公办一致口径）
        over = bool(max_km is not None and not boarding and km is not None and km > max_km)
        item = dict(s)
        item["dist"] = ({"km": km, "mins": mins, "over_max": over, "label": mode_label}
                        if km is not None else None)
        out.append(item)
    meta = {k: data.get(k) for k in ("data_warning", "source_T1", "collected", "count")}
    return {"meta": meta, "schools": out}


_VOCATIONAL_CACHE: dict = {}


def load_vocational(district: str):
    if district in _VOCATIONAL_CACHE:
        return _VOCATIONAL_CACHE[district]
    data = None
    if _USE_REGISTRY:
        data = _registry_channel(district, "中职", "vocational_record", "vocational")
    if data is None:
        path = ADMISSION_DIR / f"{district}_vocational.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
    _VOCATIONAL_CACHE[district] = data
    return data


def build_vocational_list(district, district_cn, home, mode, mode_label, max_km, boarding):
    """中职/职教校清单（含到家通勤距离）。返回 {meta, schools[]} 或 None。"""
    data = load_vocational(district)
    if not data:
        return None
    schools = data.get("schools", [])
    dist_map = {}
    if home:
        pseudo = [{"name": s["name"], "campuses": [{"name": "", "lat": s["lat"], "lon": s["lon"]}]}
                  for s in schools if s.get("lat")]
        _, dist_map = dist_mod.compute_distances(pseudo, home, district_cn, mode)
    out = []
    for s in schools:
        rows = dist_map.get(s["name"], [])
        rd = rows[0][2] if rows else None
        km = round(rd[0] / 1000, 1) if rd else None
        mins = round(rd[1] / 60) if rd else None
        over = bool(max_km is not None and not boarding and km is not None and km > max_km)
        item = dict(s)
        item["dist"] = ({"km": km, "mins": mins, "over_max": over, "label": mode_label}
                        if km is not None else None)
        out.append(item)
    meta = {k: data.get(k) for k in ("data_warning", "coverage_note", "guantong_note",
                                     "source_T1", "collected", "count")}
    return {"meta": meta, "schools": out}


_XEDDX_CACHE: dict = {}


def load_xeddx(district: str):
    """校额到校 初中→优质高中 名额分配表（<district>_xeddx.yaml；无则 None）。"""
    if district in _XEDDX_CACHE:
        return _XEDDX_CACHE[district]
    data = None
    if _USE_REGISTRY:
        data = _registry_meta(district, "xeddx")
    if data is None:
        path = ADMISSION_DIR / f"{district}_xeddx.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
    if data:
        # P3:把校额缩写(八十中/人朝…)解析到注册表 → 官方全名 + id,随块下发,前端不再硬编码简称表
        resolved = {}
        for r in (data.get("rows") or []):
            for abbr in (r.get("by_school") or {}):
                if abbr in resolved:
                    continue
                sid = _resolve_id(abbr)
                sc = _get_school(sid) if sid else None
                resolved[abbr] = {
                    "id": sid,
                    "name": (sc or {}).get("canonical_name") or abbr,   # 官方全名
                    "short": (sc or {}).get("short_name") or abbr,
                }
        data = dict(data)
        data["resolved"] = resolved
    _XEDDX_CACHE[district] = data
    return data


_TONGCHOU_CACHE: dict = {}


def _current_tongchou(base: dict) -> dict:
    """将独立的 2026 T1 覆盖层叠加到历史档案，保留画像/坐标/历史线而不覆盖 2025 快照。"""
    path = ADMISSION_DIR / "2026_sjtongchou_chaoyang.yaml"
    if not path.exists():
        return base
    overlay = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if int(overlay.get("year") or 0) <= int(base.get("year") or 0):
        return base
    out = {k: v for k, v in base.items()
           if k not in ("year", "source_authoritative", "verification_method",
                        "tongchou_yi", "tongchou_er", "totals", "verified_2026")}
    out.update({
        "year": overlay["year"], "plan": overlay["plan"], "scope": overlay["scope"],
        "source_authoritative": [overlay["source_url"]],
        "verification_method": overlay["verified"], "totals": overlay["totals"],
        "global_confidence": "T1·2026北京教育考试院官方计划逐页视觉核对",
    })
    for key in ("tongchou_yi", "tongchou_er"):
        old = {str(r.get("school_code")): r for r in base.get(key, [])}
        rows = []
        for patch in overlay.get(key, []):
            code = str(patch["school_code"])
            rec = dict(old.get(code) or {})
            rec.update(patch)
            rec["faces_chaoyang"] = int(rec.get("quota_chaoyang") or 0) > 0
            rec["confidence"] = "T1·2026官方计划"
            rec["sources"] = [overlay["source_url"]]
            rec["tongchou_major"] = {
                "major_code": str(patch["major_code"]), "major_name": "普通班",
                "full": code + str(patch["major_code"]),
            }
            rows.append(rec)
        out[key] = rows
    return out


def load_tongchou(district: str):
    """市级统筹（统筹一/二）面向本区招生清单；registry 为当前年度唯一运行时源。"""
    if district in _TONGCHOU_CACHE:
        return _TONGCHOU_CACHE[district]
    import json as _json
    data = None
    if _USE_REGISTRY:
        data = _registry_meta(district, "tongchou")
    if data is None and not _USE_REGISTRY:
        path = ADMISSION_DIR / f"2025_sjtongchou_{district}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = _json.load(f)
    if data and district == "chaoyang":
        data = _current_tongchou(data)
    _TONGCHOU_CACHE[district] = data
    return data


def tongchou_with_dist(district, home, district_cn, mode, mode_label, max_km):
    """加载统筹清单，home 非空时按各校坐标算到家通勤距离并附 dist 字段（不缓存到原始数据）。
    统筹校多在外区，距离仅作展示参考，不参与筛选。"""
    import copy
    data = load_tongchou(district)
    if not data:
        return data
    data = copy.deepcopy(data)
    rows = [s for tier in ("tongchou_yi", "tongchou_er") for s in data.get(tier, [])]
    # 朝阳口径预估(pred_2026_cy / tongchou_entry_cy / cy_equiv / below_control)由
    # compute_tongchou_pred.py 预先算好并写进 json,这里直接透传(旧"估统筹线−20"分数法已弃用)。
    if home:
        # 用唯一伪名避免同名（人大附本部/通州校区）距离串味
        pseudo = [{"name": f"__tc{i}", "campuses": [{"name": "", "lat": s["lat"], "lon": s["lon"]}]}
                  for i, s in enumerate(rows) if s.get("lat") and s.get("lon")]
        _, dist_map = dist_mod.compute_distances(pseudo, home, district_cn, mode)
        for i, s in enumerate(rows):
            r = dist_map.get(f"__tc{i}", [])
            rd = r[0][2] if r else None
            if rd:
                km = round(rd[0] / 1000, 1)
                s["dist"] = {"km": km, "mins": round(rd[1] / 60), "label": mode_label,
                             "over_max": bool(max_km is not None and km > max_km)}
    return data


_NEW2026_CACHE: dict = {}


def load_new2026(district: str):
    """2026 新增公办普高（无历史线）。文件 <district>_new2026.yaml；无则 None。"""
    if district in _NEW2026_CACHE:
        return _NEW2026_CACHE[district]
    data = None
    if _USE_REGISTRY:
        data = _registry_channel(district, "新校", "new2026_record", "new2026")
        # 已取得官方统招代码的首年招生学校会转正为公办实体；不得再从旧扁平暂存表重复注入。
        if data is None:
            _NEW2026_CACHE[district] = None
            return None
    if data is None:
        path = ADMISSION_DIR / f"{district}_new2026.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
    _NEW2026_CACHE[district] = data
    return data


def build_new_schools(district, home, district_cn, mode, mode_label, max_km):
    """2026 新增普高清单（无历史线、不做研判，只给体系/类比/选址等代理参考 + 到家通勤）。"""
    data = load_new2026(district)
    if not data:
        return None
    schools = data.get("schools", [])
    dist_map = {}
    if home:
        pseudo = [{"name": s["name"], "campuses": [{"name": "", "lat": s["lat"], "lon": s["lon"]}]}
                  for s in schools if s.get("lat") and s.get("lon")]
        _, dist_map = dist_mod.compute_distances(pseudo, home, district_cn, mode)
    out = []
    for s in schools:
        rows = dist_map.get(s["name"], [])
        rd = rows[0][2] if rows else None
        km = round(rd[0] / 1000, 1) if rd else None
        item = dict(s)
        item["dist"] = ({"km": km, "mins": round(rd[1] / 60), "label": mode_label,
                         "over_max": bool(max_km is not None and km is not None and km > max_km)}
                        if km is not None else None)
        out.append(item)
    meta = {k: data.get(k) for k in ("data_warning", "source_T1", "collected", "category")}
    return {"meta": meta, "schools": out}


def new_school_band_cards(district, rank, home, district_cn, mode, mode_label, max_km, boarding):
    """把"有预测位次(est_rank)"的 2026 新增普高，按 est_rank 归入冲/稳/保，做成卡片注入统招草表。
    新校无 school_code（2026 计划未发布）→ school_code 置 None，靠 is_estimate 标记可纳入草表；
    卡片带 is_estimate + 预测区间 + 可信度，前端醒目标注。无坐标的(如燕京新源)距离按未知=可达处理。"""
    data = load_new2026(district)
    if not data:
        return {}
    schools = [s for s in data.get("schools", []) if s.get("est_rank")]
    dist_map = {}
    if home:
        pseudo = [{"name": s["name"], "campuses": [{"name": "", "lat": s["lat"], "lon": s["lon"]}]}
                  for s in schools if s.get("lat") and s.get("lon")]
        if pseudo:
            _, dist_map = dist_mod.compute_distances(pseudo, home, district_cn, mode)
    cards = {"冲": [], "稳": [], "保": [], "够不上": []}
    for s in schools:
        try:
            er = int(s["est_rank"])
        except (TypeError, ValueError):
            er = 0
        if er <= 0:        # 估算位次缺失/为0(占位脏数据) → 跳过,不编造档位、不除零
            continue
        margin = (er - rank) / er
        band = ("保" if margin >= SAFETY_MARGIN else "稳" if margin >= 0
                else "冲" if margin >= REACH_MARGIN else "够不上")
        rows = dist_map.get(s["name"], [])
        rd = rows[0][2] if rows else None
        km = round(rd[0] / 1000, 1) if rd else None
        nearest = ({"campus": "", "km": km, "mins": round(rd[1] / 60),
                    "over_max": bool(max_km is not None and km > max_km)} if km is not None else None)
        bd = s.get("boarding") is True
        cards[band].append({
            "name": s["name"], "level": s.get("level", ""), "note": s.get("note", ""),
            "school_code": None,        # 无官方码（2026 计划未发布）；靠 is_estimate 纳入草表
            "ref_rank": er, "margin": round(margin, 3), "margin_pct": f"{margin:+.0%}",
            "volatility": 0, "history": [], "score_lines": [], "majors": [],
            "nearest": nearest, "boarding": bd,
            "campus": "", "address": s.get("address", ""), "address_exact": False,
            "address_confidence": s.get("est_conf", ""), "address_flag": "新校·预测",
            "style": s.get("style", ""), "tags": (s.get("features") or {}).get("tags") or [],
            "gaokao": "", "matched": [],
            # —— 新校预测标记（前端据此醒目标注）——
            "is_estimate": True, "est_rank": er,
            "est_range": [s.get("est_rank_lo"), s.get("est_rank_hi")],
            "est_conf": s.get("est_conf", ""), "est_basis": s.get("est_basis", ""),
        })
    return cards


_GUANTONG_CACHE: list = [None, False]


def load_guantong():
    """贯通培养项目（全市，非分区）。文件 beijing_guantong.yaml。"""
    if _GUANTONG_CACHE[1]:
        return _GUANTONG_CACHE[0]
    data = None
    if _USE_REGISTRY:
        rp = ADMISSION_DIR / "registry" / "_guantong.yaml"
        if rp.exists():
            data = yaml.safe_load(rp.read_text(encoding="utf-8"))
    if data is None:
        path = ADMISSION_DIR / "beijing_guantong.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
    _GUANTONG_CACHE[0] = data
    _GUANTONG_CACHE[1] = True
    return data

# 分档阈值（基于 margin = (录取位次 - 学生位次) / 录取位次，正值=学生比录取线更靠前）
SAFETY_MARGIN = 0.15   # 比录取线靠前 15%+ → 保底
REACH_MARGIN = -0.25   # 比录取线落后 25% 以内 → 可冲（放宽自 -0.12，让冲档不至于落空）
# 介于两者之间(0 ~ -0.25 不含、0~0.15) → 稳；落后超 25% → 够不上

# 录取位次三年极差 / 均值 超过此比例 → 标注"波动大"
VOLATILITY_THRESHOLD = 0.40


_PY2REG = {"chaoyang": "cy", "haidian": "hd", "xicheng": "xc", "dongcheng": "dc",
           "fengtai": "ft", "shijingshan": "sjs", "mentougou": "mtg", "fangshan": "fs",
           "tongzhou": "tz", "shunyi": "sy", "changping": "cp", "daxing": "dx",
           "huairou": "hr", "pinggu": "pg", "miyun": "my", "yanqing": "yq"}


def _district_from_registry(district: str) -> dict:
    """B-P3:从 registry 实体重建扁平 schools[](与 <district>.yaml 同形,供 build_result 消费)。
    registry 是唯一权威;扁平 yaml 退役为可选缓存。"""
    reg = _PY2REG.get(district)
    regdir = ADMISSION_DIR / "registry" / (reg or "")
    if not reg or not regdir.exists():
        return None
    schools = []

    def _flat_record(e, name, cam, rep, campus_adms, campuses_for_record):
        """把一个(实体, 校区, 代表录取单元)装成扁平 school 记录。
        campus_adms:归该记录的统招单元(出码/专业);campuses_for_record:该记录展示的校区坐标。"""
        roll = e.get("rollup") or {}
        s = {
            "name": name,
            "id": e.get("id"),
            "short_name": e.get("short_name"),
            "location": {"campus": cam.get("name"), "lat": cam.get("lat"), "lon": cam.get("lon"),
                         "confidence": cam.get("confidence"), "address": cam.get("address")},
            "level": e.get("level"),
            "note": e.get("note") or "",
            "features": roll.get("features") or {},
            "gaokao": roll.get("gaokao") or {},
            "phone": roll.get("phone") or (roll.get("new2026_record") or {}).get("phone"),
            "scores": dict((rep or {}).get("lines") or {}),
        }
        if roll.get("campus_life"):
            s["campus_life"] = roll["campus_life"]
        if rep and rep.get("pred_2026"):
            s["pred_2026"] = rep["pred_2026"]
        if rep and rep.get("lines_meta"):
            s["scores_meta"] = rep["lines_meta"]
        # 住宿:朝阳由 plan_district 文案("住N")驱动(同 flat 口径,blob 检测);非朝阳用 campus 确认值
        if district != "chaoyang" and cam.get("boarding") is not None:
            s["boarding"] = cam.get("boarding")
        # 嵌入统招专业(班)+码+计划区(含住信息),供 _school_card 直接用(免按名 join codes)
        s["_reg_code"] = next((a.get("code") for a in campus_adms if a.get("code")), None)
        s["_reg_majors"] = [{"major_code": a.get("major"), "major_name": a.get("major_name"),
                             "plan_total": a.get("plan_total"), "plan_chaoyang": a.get("plan_district"),
                             "note": a.get("note")}
                            for a in campus_adms if a.get("major")]
        # 嵌入各校区坐标,供 distance 直接用(免按名 join coords)
        s["_campuses"] = [{"name": c.get("name"), "lat": c.get("lat"), "lon": c.get("lon")}
                          for c in campuses_for_record if c.get("lat") is not None]
        return s

    for fp in sorted(regdir.glob("*.yaml")):
        if fp.name.startswith("_"):
            continue
        e = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        adms = e.get("admissions") or []
        # 含统招渠道的即本区公办(含被统筹视角先建、后并入统招的实体);纯民办/中职/统筹由各自 loader 出
        tongzhao = [a for a in adms if a.get("channel") == "统招"]
        if not tongzhao:
            continue
        campuses = e.get("campuses") or []
        cam_by_slug = {c.get("slug"): c for c in campuses}
        # 按校区归并统招单元;"自带独立录取线"的校区集合决定是否拆卡
        by_campus = OrderedDict()
        for a in tongzhao:
            by_campus.setdefault(a.get("campus"), []).append(a)
        lined = [cslug for cslug, al in by_campus.items() if any(x.get("lines") for x in al)]
        if len(lined) >= 2:
            # 同校多校区各挂独立线(如和平街本部 vs 北苑莲葩园):拆成多张卡,各按本校区线判档。
            # 首个(本部)沿用正名;其余以校区名加括号区分,避免按名 join 距离/坐标时撞键。
            for i, cslug in enumerate(lined):
                cam = cam_by_slug.get(cslug) or {}
                cadms = by_campus[cslug]
                rep = next((a for a in cadms if a.get("lines")), cadms[0])
                name = e["canonical_name"] if i == 0 else f"{e['canonical_name']}（{cam.get('name')}）"
                rec = _flat_record(e, name, cam, rep, cadms, [cam])
                # 校级 2026 预估只代表本部;非本部校区按本校区自身录取线判档(其历史线才反映该校区真实门槛)
                if i > 0:
                    rec.pop("pred_2026", None)
                    # 短名也加校区后缀,否则地图上两校区都显示同一短名无法区分
                    rec["short_name"] = f"{e.get('short_name')}·{(cam.get('name') or '').replace('校区', '')}"
                schools.append(rec)
        else:
            rep = next((a for a in tongzhao if a.get("lines")), tongzhao[0])
            cam = campuses[0] if campuses else {}
            schools.append(_flat_record(e, e["canonical_name"], cam, rep, tongzhao, campuses))
    return {"district": f"{district}", "region": "北京市", "schools": schools}


def load_district(district: str) -> dict:
    if _USE_REGISTRY:     # B-P3 开关:走 registry(默认关,回归绿后再开)
        d = _district_from_registry(district)
        if d and d["schools"]:
            return d
    path = ADMISSION_DIR / f"{district}.yaml"
    if not path.exists():
        avail = sorted(
            p.stem for p in ADMISSION_DIR.glob("*.yaml")
            if p.stem not in {"scoring-system", "math-target-mapping"}
        )
        sys.exit(f"找不到区数据：{path}\n已有区：{', '.join(avail)}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def school_rank_history(school: dict) -> list[tuple[int, int]]:
    """返回 [(年份, 录取位次), ...]，按年份升序，过滤无 rank 的年份。"""
    out = []
    for year, rec in sorted((school.get("scores") or {}).items()):
        rank = rec.get("rank") if isinstance(rec, dict) else None
        if rank is not None:
            out.append((int(year), int(rank)))
    return out


_PRED2026_CACHE: dict = {}


def load_pred2026(district: str) -> dict:
    """2026 录取位次预估(ts/pred_2026.json,键 'code:校名')→ {校名: {rank,lo,hi,pct,conf,...}}。
    仅朝阳有;其它区返回空。冲稳保判档以此为核心依据。"""
    if district in _PRED2026_CACHE:
        return _PRED2026_CACHE[district]
    out = {}
    if district == "chaoyang":
        path = ADMISSION_DIR / "ts" / "pred_2026.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                raw = json.load(f).get("pred", {})
            for key, v in raw.items():
                name = key.split(":", 1)[1] if ":" in key else key
                out[name] = v
    _PRED2026_CACHE[district] = out
    return out


def classify(student_rank: int, school: dict, pred_rank=None):
    """返回 (档位, margin, 参考位次C, 历史, 波动比) 或 None（数据缺失）。
    pred_rank 给定时，用 2026 预估位次做冲稳保判档（核心依据），历史仍保留供展示。"""
    history = school_rank_history(school)
    if pred_rank is None and not history:
        return None
    # 参考位次：优先 2026 预估(pred_2026)；否则取最新一年历史
    if pred_rank is not None:
        ref_rank = int(pred_rank)
    else:
        ref_year, ref_rank = history[-1]
    if not ref_rank or ref_rank <= 0:    # 位次缺失/脏数据(0/负) → 当数据缺失,不参与判档
        return None
    margin = (ref_rank - student_rank) / ref_rank

    ranks = [r for _, r in history if r] or [ref_rank]
    mean = sum(ranks) / len(ranks)
    volatility = (max(ranks) - min(ranks)) / mean if mean else 0.0

    if margin >= SAFETY_MARGIN:
        band = "保"
    elif margin >= 0:
        band = "稳"
    elif margin >= REACH_MARGIN:
        band = "冲"
    else:
        band = "够不上"
    return band, margin, ref_rank, history, volatility


def rank_to_score(district: str, rank):
    """把"区排名/位次→分数"。

    朝阳 2026 已有考试院官方分数段表时，优先用官方累计人数精确折算；
    其它区/缺官方表时，退回到最近一年学校线锚点的线性插值。
    """
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return None
    if rank <= 0:
        return None
    official = _rank_to_official_score(district, rank)
    if official is not None:
        return official
    data = load_district(district)
    anchors = []
    for s in data.get("schools", []):
        scores = s.get("scores") or {}
        # 取最近一年同时有 score+rank 的
        for y in sorted(scores.keys(), reverse=True):
            rec = scores[y]
            if isinstance(rec, dict) and rec.get("score") and rec.get("rank"):
                anchors.append((int(rec["rank"]), float(rec["score"])))
                break
    if len(anchors) < 2:
        return None
    anchors.sort()
    # 边界外用最近端点；区间内线性插值
    if rank <= anchors[0][0]:
        return round(anchors[0][1], 1)
    if rank >= anchors[-1][0]:
        return round(anchors[-1][1], 1)
    for i in range(1, len(anchors)):
        r0, s0 = anchors[i - 1]
        r1, s1 = anchors[i]
        if r0 <= rank <= r1:
            t = (rank - r0) / (r1 - r0) if r1 != r0 else 0
            return round(s0 + (s1 - s0) * t, 1)
    return None


def _load_score_bands(district: str) -> list[dict]:
    """读取官方一分一段/分数段累计表。返回按 score 降序排列的 rows。"""
    if district in _SCORE_BANDS_CACHE:
        return _SCORE_BANDS_CACHE[district]
    path = ADMISSION_DIR / "score_bands" / f"{district}_2026.yaml"
    rows = []
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            rows = data.get("rows") or []
            rows = sorted(
                [r for r in rows if r.get("score") is not None and r.get("cumulative") is not None],
                key=lambda r: int(r["score"]),
                reverse=True,
            )
        except Exception:
            rows = []
    _SCORE_BANDS_CACHE[district] = rows
    return rows


def _rank_to_official_score(district: str, rank):
    """用官方累计人数表把 rank 折算为最低对应分数。"""
    rows = _load_score_bands(district)
    if not rows:
        return None
    for r in rows:
        if int(r["cumulative"]) >= rank:
            return int(r["score"])
    return int(rows[-1]["score"])


def _enrich_pred_scores(district: str, pred: dict) -> dict:
    """给 pred_2026 追加 score / score_lo / score_hi，保持原对象不被原地污染。"""
    if not isinstance(pred, dict):
        return pred
    out = dict(pred)
    if out.get("rank") is not None:
        out["score"] = rank_to_score(district, out.get("rank"))
    # lo=更靠前位次，对应更高分；hi=更靠后位次，对应更低分
    if out.get("lo") is not None:
        out["score_hi"] = rank_to_score(district, out.get("lo"))
    if out.get("hi") is not None:
        out["score_lo"] = rank_to_score(district, out.get("hi"))
    if out.get("score") is not None:
        out["score_source"] = "2026官方分数段累计表"
    return out


def nearest_campus(rows):
    """从 [(校区名, 坐标, rd), ...] 取距离最近（rd 非空）的一项；全空返回 None。"""
    valid = [r for r in rows if r[2] is not None]
    if not valid:
        return None
    return min(valid, key=lambda r: r[2][0])


def fmt_dist(rows, mode_label: str, max_km) -> str:
    """rows = 某校各校区 [(校区名, 坐标, (米,秒)|None), ...]。文本显示最近校区。"""
    if not rows:
        return "  📍距离未知"
    best = nearest_campus(rows)
    if best is None:
        return "  📍距离未知"
    cname, _, (dist_m, dur_s) = best
    km, mins = dist_m / 1000, round(dur_s / 60)
    multi = len([r for r in rows if r[2] is not None]) > 1
    campus_tag = f"（{cname}最近）" if (multi and cname) else ""
    far = "  ⚠️偏远/超通勤上限" if (max_km is not None and km > max_km) else ""
    return f"  📍{mode_label}{km:.1f}km/{mins}分钟{campus_tag}{far}"


def fmt_history(history: list[tuple[int, int]], school: dict) -> str:
    parts = []
    for year, rank in history:
        score = (school.get("scores") or {}).get(year, {}).get("score")
        parts.append(f"{year}:{score}分/{rank}名" if score else f"{year}:{rank}名")
    return "  ".join(parts)


BAND_COLOR = {"冲": "#e74c3c", "稳": "#f1c40f", "保": "#2ecc71"}


SMALL_COLOR = {"够不上": "#9b59b6", "太远": "#e67e22", "民办": "#3498db"}


def _dist_txt(rd, mode_label):
    return f"{mode_label} {rd[0]/1000:.1f}km / {round(rd[1]/60)}分钟" if rd else "距离未知"


# 兴趣标签词表（与学校 features.tags 对齐；--interests 可传任意词，子串双向匹配）
INTEREST_TAGS = [
    "理科见长", "科技创新", "外语特色", "文科人文", "艺术特长",
    "体育特长", "国际方向", "课程改革", "学科竞赛", "综合均衡", "寄宿制",
]


def match_interests(school: dict, interests: list) -> list:
    """返回学校 tags 中与用户兴趣命中的标签（子串双向匹配，宽松）。"""
    if not interests:
        return []
    tags = ((school.get("features") or {}).get("tags")) or []
    hit = []
    for t in tags:
        if any(it and (it in t or t in it) for it in interests):
            hit.append(t)
    return hit


def _gaokao_years_str(school: dict) -> str:
    """学校 gaokao 逐年自由文本拼成一行（不含 note/source）；无数据返回空串。"""
    g = school.get("gaokao") or {}
    years = {k: v for k, v in g.items() if k not in ("note", "source")}
    if not years:
        return ""
    return "；".join(f"{y} {v}" for y, v in sorted(years.items(), reverse=True))


def features_txt(school: dict) -> str:
    f = school.get("features") or {}
    style, tags = f.get("style"), f.get("tags") or []
    if not style and not tags:
        return ""
    parts = [style] if style else []
    if tags:
        parts.append("  ".join(f"#{t}" for t in tags))
    return "        🏫特色：" + "  ".join(parts)


def gaokao_txt(school: dict) -> str:
    s = _gaokao_years_str(school)
    return f"        🎓高考(民间·非官方仅参考)：{s}" if s else ""


def _hist_of(s, history):
    return "  ".join(
        f"{y}年:{(s.get('scores') or {}).get(y, {}).get('score','?')}分(位次{r})"
        for y, r in history)


def build_public_points(buckets, dist_campus, mode_label, max_km, interests=None,
                         boarding_names=None):
    """统招公办全部点位（含够不上/超通勤的小图标）；多校区每校区一个点。
    boarding_names：可寄宿校名集合——远但可寄宿仍按正常 pin 展示（不标"太远"）。"""
    boarding_names = boarding_names or set()
    points = []
    for band in ("冲", "稳", "保", "够不上"):
        for s, margin, ref_rank, history, vol in buckets[band]:
            rows = dist_campus.get(s["name"], [])
            if not rows:
                continue
            multi = len(rows) > 1
            for cname, ccoord, rd in rows:
                if not ccoord:
                    continue
                km = rd[0] / 1000 if rd else None
                too_far = (max_km is not None and km is not None and km > max_km
                           and s["name"] not in boarding_names)
                if band == "够不上":
                    kind, color, reason = "small", SMALL_COLOR["够不上"], "位次够不上（录取线远高于孩子）"
                elif too_far:
                    kind, color, reason = "small", SMALL_COLOR["太远"], f"超通勤上限（>{max_km}km）"
                else:
                    kind, color, reason = "full", BAND_COLOR[band], ""
                disp = f"{s['name']}·{cname}" if (multi and cname) else s["name"]
                sn = s.get("short_name") or s["name"]
                disp_short = f"{sn}·{cname}" if (multi and cname) else sn
                feat = s.get("features") or {}
                points.append({
                    "name": disp, "short_name": disp_short, "lat": ccoord[0], "lon": ccoord[1],
                    "kind": kind, "color": color, "band": band,
                    "level": s.get("level", ""), "rank": ref_rank,
                    "margin": f"{margin:+.0%}", "dist": _dist_txt(rd, mode_label),
                    "hist": _hist_of(s, history), "note": s.get("note", ""),
                    "reason": reason,
                    "style": feat.get("style", ""), "tags": feat.get("tags") or [],
                    "gaokao": _gaokao_years_str(s),
                    "matched": match_interests(s, interests or []),
                })
    return points


def build_private_points(priv, priv_dist, mode_label, max_km):
    """民办/国际校点位（统一小蓝图标，不参加统招）。"""
    out = []
    for p in priv:
        rows = priv_dist.get(p["name"], [])
        rd = rows[0][2] if rows else None
        km = rd[0] / 1000 if rd else None
        reason = "民办/国际，不参加统招志愿"
        if max_km is not None and km is not None and km > max_km:
            reason += f"；且超通勤上限（>{max_km}km）"
        out.append({
            "name": p["name"], "short_name": p.get("short_name") or p["name"],
            "lat": p["lat"], "lon": p["lon"],
            "kind": "small", "color": SMALL_COLOR["民办"], "band": "民办",
            "level": "民办/国际", "rank": "—", "margin": "—",
            "dist": _dist_txt(rd, mode_label), "hist": "", "note": "",
            "reason": reason,
            "style": "", "tags": [], "gaokao": "", "matched": [],
        })
    return out


def _school_card(s, margin, ref_rank, history, vol, dist_campus, mode_label, max_km,
                 interests, admission_codes=None):
    """单校结构化卡片（文本/前端共用）。nearest 取最近校区。
    admission_codes 命中则带 school_code + majors[]（官方计划册派生），供志愿草表用。"""
    best = nearest_campus(dist_campus.get(s["name"], []))
    nearest = None
    if best:
        cname, _, (m, sec) = best
        nearest = {"campus": cname, "km": round(m / 1000, 1), "mins": round(sec / 60),
                   "over_max": bool(max_km is not None and m / 1000 > max_km)}
    feat = s.get("features") or {}
    # 历年分数线（含分数+位次），按年份降序（2025→2024→2023…）供前端结构化展示
    scores = s.get("scores") or {}
    score_lines = []
    for y in sorted(scores.keys(), reverse=True):
        rec = scores[y]
        if not isinstance(rec, dict):
            continue
        score_lines.append({"year": int(y), "score": rec.get("score"), "rank": rec.get("rank")})
    # 地址（含核验提示）：address 优先，缺则用 address_rough；附 confidence/flag 让前端如实标注
    loc = s.get("location") or {}
    card = {
        "name": s["name"], "short_name": s.get("short_name") or s["name"],
        "level": s.get("level", ""), "note": s.get("note", ""),
        "ref_rank": ref_rank, "margin": round(margin, 3), "margin_pct": f"{margin:+.0%}",
        "volatility": round(vol, 2), "history": [[y, r] for y, r in history],
        "score_lines": score_lines,
        "nearest": nearest,
        "campus": loc.get("campus") or "",
        "address": loc.get("address") or loc.get("address_rough") or "",
        "address_exact": bool(loc.get("address")),
        "address_confidence": loc.get("confidence") or "",
        "address_flag": loc.get("flag") or "",
        "phone": s.get("phone"),
        "style": feat.get("style", ""), "tags": feat.get("tags") or [],
        "gaokao": _gaokao_years_str(s),
        "matched": match_interests(s, interests or []),
    }
    adm = (admission_codes or {}).get(s["name"])
    if not adm and s.get("_reg_majors") is not None:   # registry 源:用学校自带专业/码
        adm = {"school_code": s.get("_reg_code"), "majors": s["_reg_majors"]}
    if adm:
        majors = adm.get("majors") or []
        card["school_code"] = adm.get("school_code")
        card["majors"] = majors
        if adm.get("campus_major"):
            card["campus_major"] = adm["campus_major"]
        # 官方计划派生标签：是否有住宿名额 / 是否含中外合作(国际)班
        blob = " ".join((m.get("plan_chaoyang", "") or "") + (m.get("note", "") or "")
                        for m in majors)
        card["boarding"] = "住" in blob
        # 去 OCR 空格伪影后匹配中外合作/国际班关键词（"中美高中课程合 作项目班" 等）
        names = re.sub(r"\s+", "", " ".join(m.get("major_name", "") or "" for m in majors))
        card["coop"] = any(k in names for k in ("中外", "中美", "中英", "国际", "合作", "AP"))
    return card


def _campus_coords_only(schools, district_cn):
    """仅取各校（含多校区）坐标，不算到家距离。
    用于地图优先布局——没填住址也能展示全区学校分布。
    返回 {校名: [(校区名, (lat,lon)), ...]}。"""
    geo_cache = dist_mod._load_cache(dist_mod.GEO_CACHE)
    coords_idx = dist_mod.build_coords_index()
    kb_coords = dist_mod.load_kb_coords(district_cn)
    out = {}
    for s in schools:
        out[s["name"]] = dist_mod.get_campuses(
            s, district_cn, coords_idx, geo_cache, kb_coords)
    return out


def eligibility_for(identity: str) -> dict:
    """按考生身份返回各升学渠道的可报资格（与前端 canIndicator/canGuantong/canPuhao 一致）。
    identity: jjyj=京籍应届 / feijing=非京籍随迁 / wangjie=往届·回户籍·外省回京。"""
    identity = identity or "jjyj"
    can_puhao = identity != "feijing"          # 非京籍随迁不能报普通高中
    can_indicator = identity == "jjyj"         # 校额到校/市级统筹：仅京籍应届
    can_guantong = identity == "jjyj"          # 贯通：仅京籍应届
    notes = {
        "feijing": "非京籍随迁子女不能报普通高中（统招/校额到校/统筹/贯通），只能报中职类。",
        "wangjie": "往届/回户籍/外省回京考生不能报指标分配(校额到校/统筹)与贯通；普高统招可报。",
    }
    return {
        "identity": identity,
        "puhao_tongzhao": can_puhao,   # 普高统一招生
        "indicator": can_indicator,    # 指标分配=校额到校+市级统筹
        "guantong": can_guantong,      # 贯通培养
        "vocational": True,            # 中职各身份均可报
        "note": notes.get(identity, ""),
    }


def build_result(rank, home=None, mode="driving", max_km=None, interests=None,
                 district="chaoyang", boarding=False, identity="jjyj"):
    """纯函数：返回结构化推荐结果（CLI 文本 / 地图 / Web API 共用）。
    home 为空则不算距离（但仍返回学校坐标，供地图展示）；home 无法定位时抛 ValueError。
    boarding=True（孩子接受住宿）时，距离不再参与筛选/排序——超通勤上限不标记、
    范围放开（距离仍照常展示作参考）。
    identity 决定各渠道可报资格（见 eligibility_for），随结果返回，供前端按身份提示/过滤。"""
    interests = interests or []
    data = load_district(district)
    district_name = data.get("district", district)
    schools = data.get("schools", [])
    priv = dist_mod.private_schools(district_name, {s["name"] for s in schools})
    mode_label = dist_mod.MODES[mode][1]

    # 寄宿模式：距离不参与筛选 → 超通勤上限失效（距离仍展示）
    effective_max_km = None if boarding else max_km

    dist_campus, priv_dist, home_coord = {}, {}, None
    if home:
        home_coord, dist_campus = dist_mod.compute_distances(schools, home, district_name, mode)
        if home_coord is None:
            raise ValueError(f"无法定位家庭住址：{home}")
        _, priv_dist = dist_mod.compute_distances(
            [{"name": p["name"], "campuses": [{"name": "", "lat": p["lat"], "lon": p["lon"]}]}
             for p in priv], home, district_name, mode)
    else:
        # 无住址：只取坐标（rd=None），让地图仍能展示全区学校分布（地图优先布局）
        coords = _campus_coords_only(schools, district_name)
        dist_campus = {n: [(cn, cc, None) for cn, cc in rows] for n, rows in coords.items()}
        priv_dist = {p["name"]: [("", (p["lat"], p["lon"]), None)] for p in priv}

    pred2026 = load_pred2026(district)       # {校名: {rank,lo,hi,conf,...}} 2026预估,冲稳保核心依据
    # 非朝阳:无模型预测,用 yaml 里按最近年份位次合成的 pred_2026 兜底(method='hist')
    yaml_pred = {s["name"]: s["pred_2026"] for s in schools if s.get("pred_2026")}
    yaml_camp = {s["name"]: s["campus_life"] for s in schools if s.get("campus_life")}
    yaml_boarding = {s["name"] for s in schools if s.get("boarding") is True}  # 校园生活确认可住宿
    pred_rank_map = {n: v.get("rank") for n, v in pred2026.items()}
    buckets = {"冲": [], "稳": [], "保": [], "够不上": []}
    for s in schools:
        # 预估位次优先用学校自带(registry/yaml 已挂),否则回退按名取 ts 模型(朝阳旧口径)
        pr = (s.get("pred_2026") or {}).get("rank") or pred_rank_map.get(s["name"])
        res = classify(rank, s, pred_rank=pr)
        if res is None:
            continue
        band, margin, ref_rank, history, vol = res
        buckets[band].append((s, margin, ref_rank, history, vol))
    for band in buckets:
        buckets[band].sort(key=lambda t: (-len(match_interests(t[0], interests)), t[2]))

    admission_codes = load_admission_codes(district)
    # 先全量构卡（含 boarding 派生），再剔除"超通勤上限且不可寄宿"的冲稳保学校。
    # 可寄宿的远校保留（住宿可解决通勤）；够不上不受距离影响照常展示。
    raw_bands = {band: [_school_card(*t, dist_campus, mode_label, effective_max_km, interests,
                                     admission_codes)
                        for t in buckets[band]] for band in buckets}
    # 挂 2026 预估位次到卡片(前端"📍2026预估位次"用;冲稳保已按它判档)
    for cards in raw_bands.values():
        for c in cards:
            p = pred2026.get(c["name"]) or yaml_pred.get(c["name"])
            if p:
                c["pred_2026"] = _enrich_pred_scores(district, p)
            cl = yaml_camp.get(c["name"])
            if cl:
                c["campus_life"] = cl
            if c.get("boarding") is not True and c["name"] in yaml_boarding:
                c["boarding"] = True   # 官方计划未标但校园生活确认可住宿 → 消解待核
    # 可寄宿校名集合（供地图判定：远但可寄宿→正常 pin，不标"太远"）
    boarding_names = {c["name"] for cards in raw_bands.values()
                      for c in cards if c.get("boarding")}

    def _reachable(c):
        n = c.get("nearest")
        # 超通勤上限 且 不可寄宿 → 不可达，剔出冲稳保
        return not (n and n.get("over_max") and not c.get("boarding"))

    bands = {}
    for band, cards in raw_bands.items():
        bands[band] = [c for c in cards if _reachable(c)] if band in ("冲", "稳", "保") else cards

    # 注入 2026 新增普高(有 est_rank 的)：按预测位次归入冲/稳/保，前端醒目标注；同口径过滤太远
    new_cards = new_school_band_cards(district, rank, home, district_name, mode, mode_label, max_km, boarding)
    for band in ("冲", "稳", "保"):
        bands[band] = bands[band] + [c for c in new_cards.get(band, []) if _reachable(c)]
        bands[band].sort(key=lambda c: (c.get("ref_rank") or 9_999_999))
    bands["够不上"] = bands.get("够不上", []) + new_cards.get("够不上", [])

    # 普高（统招公办）全量清单：含所有档位，按录取位次升序；标注档位/是否可达
    public_list = []
    for band in ("冲", "稳", "保", "够不上"):
        for c in raw_bands[band]:
            item = dict(c)
            item["band"] = band
            n = c.get("nearest")
            item["over_max"] = bool(n and n.get("over_max"))
            # 不在报名范围 = 够不上 或（超通勤上限且不可寄宿）
            item["reportable"] = band != "够不上" and _reachable(c)
            public_list.append(item)
    public_list.sort(key=lambda x: x["ref_rank"])

    result = {
        "district": district_name, "rank": rank, "home": home,
        "home_coord": list(home_coord) if home_coord else None,
        "mode": mode, "mode_label": mode_label, "max_km": max_km,
        "boarding": boarding,
        "identity": identity,
        "eligibility": eligibility_for(identity),
        "est_score": rank_to_score(district, rank),
        "interests": interests,
        "admission_source": (
            "学校代码、专业(班)及计划人数来自北京教育考试院 2026 官方招生计划；"
            "预测分数按北京教育考试院 2026 朝阳区官方分数段表折算；"
            "首年招生学校的录取位次仍为估算" if district == "chaoyang" else
            "学校代码、专业(班)及计划人数来自北京教育考试院 2026 官方招生计划"),
        "bands": bands,
        "public_list": public_list,
        "private_schools": build_private_list(district, district_name, home, mode,
                                              mode_label, max_km, boarding),
        "vocational": build_vocational_list(district, district_name, home, mode,
                                            mode_label, max_km, boarding),
        "guantong": load_guantong(),
        "tongchou": tongchou_with_dist(district, home, district_name, mode, mode_label, max_km),
        "new_schools": build_new_schools(district, home, district_name, mode, mode_label, max_km),
        "xeddx": load_xeddx(district),
        # 地图"太远"判定与草表同口径:用真实 max_km;仅"用户接受住宿 且 该校真提供住宿"才豁免距离
        # (此前用 effective_max_km=None 把整图距离判断关掉,导致远校无住宿也照画冲/保)
        "points": build_public_points(buckets, dist_campus, mode_label, max_km,
                                      interests, boarding_names if boarding else set()),
        "private": build_private_points(priv, priv_dist, mode_label, effective_max_km),
        "quota_allocation": data.get("quota_allocation"),
        "_buckets": buckets, "_dist_campus": dist_campus,
        "_priv": priv, "_priv_dist": priv_dist, "_home_coord": home_coord,
    }
    # P1：给每个学校对象装上稳定 school_id（resolve 脏名字/代码 → 注册表 id）。
    # 增量、不改既有字段：name 等全保留;前端 P2 起改用 id 去重/匹配,告别字符串拼接。
    _stamp_school_ids(result)

    # §12 统一模型：规范化适配层（增量，前端逐步迁移；school_额到校 channel 由前端按初中追加）
    try:
        import unified
        result["schools_unified"] = unified.build_unified(result)
        # unified 由 result 装配 → 其条目同样补 id
        for u in (result.get("schools_unified") or []):
            if isinstance(u, dict) and not u.get("id"):
                u["id"] = _resolve_id(u.get("name"))
    except Exception as e:  # 适配层不可因异常拖垮主推荐
        result["schools_unified"] = None
        result["_unified_err"] = str(e)
    return result


def _stamp_school_ids(result: dict) -> dict:
    """给 result 里所有学校对象补 `id`(+`id_status`)。集中一处、幂等、不改其他字段。
    覆盖:bands/public_list/private_schools/vocational/new_schools/tongchou(yi/er)。
    贯通(城市级,未入注册表)→ id_status='unresolved',不报错(后续阶段再纳)。"""
    stats = {"ok": 0, "unresolved": 0}

    def stamp(obj):
        if not isinstance(obj, dict):
            return
        nm = obj.get("name") or obj.get("school_name")
        sid = _resolve_id(nm) if nm else None
        obj["id"] = sid
        obj["id_status"] = "ok" if sid else "unresolved"
        stats["ok" if sid else "unresolved"] += 1

    for band_cards in (result.get("bands") or {}).values():
        for c in band_cards:
            stamp(c)
    for c in (result.get("public_list") or []):
        stamp(c)
    for key in ("private_schools", "vocational"):
        for s in ((result.get(key) or {}).get("schools") or []):
            stamp(s)
    ns = result.get("new_schools")
    for s in (ns.get("schools") if isinstance(ns, dict) else ns) or []:
        stamp(s)
    tc = result.get("tongchou") or {}
    for k in ("tongchou_yi", "tongchou_er", "schools"):
        for s in (tc.get(k) or []):
            stamp(s)
    result["_id_stamp"] = stats
    return result


def generate_map(out_path, district_name, student_rank, home_addr, home_coord,
                 mode_label, buckets, dist_campus, priv, priv_dist, max_km, interests=None):
    """生成自包含交互式地图 HTML（Leaflet + 高德底图，GCJ-02 坐标一致）。

    - 全部统招校都打点：冲稳保=大彩色pin；够不上/超通勤=小图标（不在报名范围）
    - 多校区每校区各一个marker、各自距离
    - 民办/国际作为可切换图层（默认关）
    """
    import json as _json

    points = build_public_points(buckets, dist_campus, mode_label, max_km, interests)
    priv_points = build_private_points(priv, priv_dist, mode_label, max_km)

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:-apple-system,"PingFang SC",sans-serif}
  #map{height:100%}
  .hdr{position:absolute;top:10px;left:10px;z-index:1000;background:#fff;
       padding:10px 14px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.3);font-size:14px}
  .hdr b{font-size:15px}
  .legend{position:absolute;bottom:18px;left:10px;z-index:1000;background:#fff;
          padding:8px 12px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.3);font-size:13px}
  .dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
  .sm{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 7px 0 2px;vertical-align:middle}
  .lbl{font-size:11px;font-weight:bold;color:#fff;text-align:center;line-height:1.1;
       text-shadow:0 0 2px rgba(0,0,0,.6)}
  .pop b{font-size:14px} .pop .meta{color:#555;font-size:12px;margin-top:4px}
</style></head><body>
<div class="hdr"><b>__DISTRICT__ 志愿地图</b><br>孩子区排名 第 __RANK__ 名 ｜ 家：__HOME__<br>
  通勤：__MODE__（路网距离）</div>
<div class="legend">
  <div><span class="dot" style="background:#e74c3c"></span>冲（略低于录取线）</div>
  <div><span class="dot" style="background:#f1c40f"></span>稳（略高于录取线）</div>
  <div><span class="dot" style="background:#2ecc71"></span>保（明显高于录取线）</div>
  <hr style="margin:5px 0;border:none;border-top:1px solid #eee">
  <div style="color:#666">下面为不在报名范围（小图标）：</div>
  <div><span class="sm" style="background:#9b59b6"></span>位次够不上</div>
  <div><span class="sm" style="background:#e67e22"></span>超通勤上限</div>
  <div><span class="sm" style="background:#3498db"></span>民办/国际（右上角勾选显示）</div>
  <div><span class="dot" style="background:#2c3e50"></span>家</div>
</div>
<div id="map"></div>
<script>
var HOME=__HOME_COORD__, PTS=__POINTS__, PRIV=__PRIV__;
var map=L.map('map',{zoomControl:false}).setView(HOME,12);
L.control.zoom({position:'topright'}).addTo(map);
L.tileLayer('https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}',
  {subdomains:['1','2','3','4'],maxZoom:18,attribution:'高德地图'}).addTo(map);

function pin(color,txt){return L.divIcon({className:'',iconSize:[34,34],iconAnchor:[17,34],
  html:'<div style="background:'+color+';width:34px;height:34px;border-radius:50% 50% 50% 0;'+
  'transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);'+
  'display:flex;align-items:center;justify-content:center;">'+
  '<span class="lbl" style="transform:rotate(45deg)">'+txt+'</span></div>'});}
function smallIcon(color){return L.divIcon({className:'',iconSize:[14,14],iconAnchor:[7,7],
  html:'<div style="background:'+color+';width:14px;height:14px;border-radius:50%;'+
  'border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4);opacity:.9"></div>'});}

function popup(p){
  var head='<div class="pop"><b>'+p.name+'</b> <span style="color:'+p.color+'">['+p.band+']</span>';
  if(p.matched&&p.matched.length) head+=' <span style="color:#16a085">🎯'+p.matched.join('·')+'</span>';
  var meta='<div class="meta">'+p.level;
  if(p.rank!=='—') meta+=' ｜ 录取位次≈'+p.rank+'名 (margin '+p.margin+')';
  meta+='<br>通勤 '+p.dist;
  if(p.style) meta+='<br>🏫 '+p.style;
  if(p.tags&&p.tags.length) meta+='<br>'+p.tags.map(function(t){return '#'+t;}).join(' ');
  if(p.gaokao) meta+='<br>🎓 高考(民间·非官方)：'+p.gaokao;
  if(p.hist) meta+='<br>'+p.hist;
  if(p.note) meta+='<br>'+p.note;
  if(p.reason) meta+='<br>🚫 <b style="color:#c0392b">不在报名范围：</b>'+p.reason;
  return head+meta+'</div></div>';
}

L.marker(HOME,{icon:pin('#2c3e50','家'),zIndexOffset:1000}).addTo(map)
  .bindPopup('<div class="pop"><b>家</b><br>__HOME__</div>');

var bounds=[HOME];
var publicLayer=L.layerGroup().addTo(map);
PTS.forEach(function(p){
  bounds.push([p.lat,p.lon]);
  var icon=(p.kind==='full')?pin(p.color,p.band):smallIcon(p.color);
  L.marker([p.lat,p.lon],{icon:icon}).addTo(publicLayer).bindPopup(popup(p));
});
var privateLayer=L.layerGroup();   // 默认不加到 map（关）
PRIV.forEach(function(p){
  L.marker([p.lat,p.lon],{icon:smallIcon(p.color)}).addTo(privateLayer).bindPopup(popup(p));
});
L.control.layers(null,{'统招公办（含够不上/超通勤）':publicLayer,
  '民办/国际校':privateLayer},{position:'topright',collapsed:false}).addTo(map);
map.fitBounds(bounds,{padding:[50,50]});
</script></body></html>"""

    repl = {
        "__TITLE__": f"{district_name}志愿地图",
        "__DISTRICT__": district_name,
        "__RANK__": str(student_rank),
        "__HOME__": home_addr,
        "__MODE__": mode_label,
        "__HOME_COORD__": _json.dumps([home_coord[0], home_coord[1]]),
        "__POINTS__": _json.dumps(points, ensure_ascii=False),
        "__PRIV__": _json.dumps(priv_points, ensure_ascii=False),
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    Path(out_path).write_text(html, encoding="utf-8")
    return len(points), len(priv_points)


def main():
    ap = argparse.ArgumentParser(description="中考志愿冲稳保推荐（位次匹配）")
    ap.add_argument("--district", default="chaoyang", help="区拼音（默认 chaoyang）")
    ap.add_argument("--rank", type=int, required=True, help="孩子的区排名/位次（来自一模或二模）")
    ap.add_argument("--all", action="store_true", help="同时列出'够不上'的学校")
    ap.add_argument("--home", help="家庭住址（小区名/地铁站/街道即可），给了就算通勤距离")
    ap.add_argument("--mode", default="driving", choices=list(dist_mod.MODES),
                    help="通勤方式：driving驾车/walking步行/bicycling骑行/transit公交（默认driving）")
    ap.add_argument("--max-distance", type=float, metavar="KM",
                    help="超过该公里数（按最近校区）的学校标注为'偏远/不在报名范围'")
    ap.add_argument("--map", metavar="OUT.html", help="同时生成交互式地图 HTML（需配合 --home）")
    ap.add_argument("--include-private", action="store_true",
                    help="文本里也列出民办/国际校（地图默认作为可切换图层，无需此参数）")
    ap.add_argument("--interests", metavar="兴趣",
                    help="孩子兴趣偏好(逗号分隔)做软匹配排序，如：外语,科技。可用标签：" + "/".join(INTEREST_TAGS))
    args = ap.parse_args()

    interests = [x.strip() for x in (args.interests or "").split(",") if x.strip()]

    data = load_district(args.district)
    district_name = data.get("district", args.district)
    schools = data.get("schools", [])

    # 民办/国际校（不参加统招）
    priv = dist_mod.private_schools(district_name, {s["name"] for s in schools})

    # 通勤距离（路网，非直线，按校区分别算）
    dist_campus = {}     # 校名 -> [(校区名, (lat,lon), (米,秒)|None), ...]
    priv_dist = {}
    home_coord = None
    if args.home:
        mode_label = dist_mod.MODES[args.mode][1]
        print(f"\n正在用高德算 [{mode_label}] 路网距离：{args.home} → 各校 …", file=sys.stderr)
        home_coord, dist_campus = dist_mod.compute_distances(
            schools, args.home, district_name, args.mode)
        if home_coord is None:
            sys.exit(f"无法定位家庭住址：{args.home}（换个更具体的小区名/地铁站试试）")
        _, priv_dist = dist_mod.compute_distances(
            [{"name": p["name"], "campuses": [{"name": "", "lat": p["lat"], "lon": p["lon"]}]}
             for p in priv], args.home, district_name, args.mode)

    buckets = {"冲": [], "稳": [], "保": [], "够不上": []}
    for s in schools:
        res = classify(args.rank, s)
        if res is None:
            continue
        band, margin, ref_rank, history, vol = res
        buckets[band].append((s, margin, ref_rank, history, vol))

    # 每档内：先按兴趣匹配数降序（软匹配，命中的往前提），再按录取位次升序
    for band in buckets:
        buckets[band].sort(key=lambda t: (-len(match_interests(t[0], interests)), t[2]))

    print(f"\n{'='*60}")
    print(f"  {district_name} · 中考志愿推荐  |  孩子区排名：第 {args.rank} 名")
    print(f"{'='*60}")
    print("  分档依据：你的位次 vs 各校最近一年录取位次")
    print("  保=稳进 / 稳=略高于线 / 冲=略低于线可博 / 够不上=差距较大\n")

    band_labels = {
        "冲": "🔴 冲（略低于录取线，可博但风险高）",
        "稳": "🟡 稳（已高于录取线，较有把握）",
        "保": "🟢 保（明显高于录取线，基本稳进）",
    }
    order = ["冲", "稳", "保"]
    if args.all:
        order.append("够不上")
        band_labels["够不上"] = "⚫ 够不上（位次差距 >12%，仅供参考）"

    for band in order:
        items = buckets[band]
        print(f"{band_labels[band]}  —— {len(items)} 所")
        if not items:
            print("    （无）\n")
            continue
        for s, margin, ref_rank, history, vol in items:
            level = s.get("level", "")
            note = s.get("note", "")
            vol_flag = "  ⚠️录取位次年际波动大" if vol > VOLATILITY_THRESHOLD else ""
            mode_label = dist_mod.MODES[args.mode][1]
            dist_str = fmt_dist(dist_campus.get(s["name"], []), mode_label, args.max_distance) if args.home else ""
            matched = match_interests(s, interests)
            match_str = f"  🎯兴趣匹配：{'·'.join(matched)}" if matched else ""
            print(f"    • {s['name']}  [{level}]  录取位次≈{ref_rank}名 (margin {margin:+.0%}){dist_str}{vol_flag}{match_str}")
            print(f"        历年：{fmt_history(history, s)}")
            ft = features_txt(s)
            if ft:
                print(ft)
            gt = gaokao_txt(s)
            if gt:
                print(gt)
            if note:
                print(f"        备注：{note}")
        print()

    # 校额到校提示（数据里有就提示）
    quota = data.get("quota_allocation")
    if quota and quota.get("policy_summary"):
        print(f"{'-'*60}")
        print("📌 校额到校提示（可能是普通初中孩子进好高中的最佳机会）：")
        for line in quota["policy_summary"].strip().splitlines():
            print(f"    {line.strip()}")
        print("    ⚠️ 校额到校看的是【本校内排名】而非全区排名，本工具暂不计算。\n")

    print(f"{'-'*60}")
    print("⚠️ 重要说明：")
    print("  1. 假设一模/二模区排名 ≈ 中考录取区排名（位次相对稳定，但非绝对）。")
    print("  2. 录取位次每年有波动，标⚠️的学校尤其需谨慎，多看历年区间。")
    print("  3. 本结果仅辅助参考，最终志愿请结合官方招生简章与学校老师建议。")
    print(f"{'='*60}\n")

    # 交互式地图
    if args.map:
        if not args.home:
            sys.exit("生成地图需要 --home（家庭住址）")
        n, npv = generate_map(args.map, district_name, args.rank, args.home, home_coord,
                              dist_mod.MODES[args.mode][1], buckets, dist_campus, priv, priv_dist,
                              args.max_distance, interests)
        print(f"🗺️  地图已生成：{args.map}（{n} 个统招点位 + {npv} 民办 + 家）")


if __name__ == "__main__":
    main()
