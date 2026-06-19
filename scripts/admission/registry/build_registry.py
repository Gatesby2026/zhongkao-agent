#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 学校注册表生成器(只读旧文件 → 生成 registry/,零行为改动)。

把现有 10 个分散数据文件按"学校实体"合并:
- public 以 admission_codes 的 school_code 为合并键 → 同代码多 name 条目合并成
  一个 School 的多 campus + 多 major(和平街 01/02 即此);
- private / vocational / new2026 各自 name 为单位;
- 线/位次/pred 下沉到录取单元(code+major);campus 一等子实体。

原则:**不编造**。缺数据 → 写进覆盖率报告(_coverage_report.md),不填假值。
ID = 区-编号-拼音简写(见 docs/design/SCHOOL-ENTITY-MODEL.md §三)。

用法: python3 scripts/admission/registry/build_registry.py [--district chaoyang]
"""
import json, os, re, sys, argparse
from collections import defaultdict, OrderedDict
import yaml
from pypinyin import lazy_pinyin, Style

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
KB = os.path.join(ROOT, "knowledge-base", "admission", "beijing")
DISTRICT_PY = {"朝阳区": "cy", "海淀区": "hd", "西城区": "xc", "东城区": "dc",
               "丰台区": "ft", "石景山区": "sjs", "通州区": "tz"}

report = []  # (level, code_tag, message)
def flag(level, tag, msg): report.append((level, tag, msg))

def to_plain(o):
    """OrderedDict/嵌套 → 纯 dict/list(保留插入顺序),供 yaml.safe_dump。"""
    if isinstance(o, dict): return {k: to_plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [to_plain(v) for v in o]
    return o

def load_json(p):
    with open(p, encoding="utf-8") as f: return json.load(f)
def load_yaml(p):
    with open(p, encoding="utf-8") as f: return yaml.safe_load(f)

def py_abbr(s):
    """短名 → 拼音声母串(去非汉字)。"""
    s = re.sub(r"[（(].*?[)）]", "", s or "")
    s = re.sub(r"[^一-鿿]", "", s)
    return "".join(p[0] for p in lazy_pinyin(s, style=Style.FIRST_LETTER) if p) or "x"

def short_of(name):
    """去官方前后缀,得简称(显示+拼音用)。"""
    n = re.sub(r"[（(].*?[)）]", "", name or "").strip()
    n = re.sub(r"^北京市?", "", n)
    return n or name

def campus_slug(campus_text, name_entry):
    """校区 slug:本部→benbu;带(X校区)→ X 的拼音声母。"""
    m = re.search(r"[（(](.+?)[)）]", name_entry or "")
    if not m:
        return "benbu"
    token = re.sub(r"(高中)?校区$", "", m.group(1))
    return py_abbr(token) or "fenxiao"

def clean_campus_name(campus_text, name_entry):
    m = re.search(r"[（(](.+?)[)）]", name_entry or "")
    if m:
        return m.group(1)
    # 本部:从 coords campus 文案取前段
    if campus_text:
        return re.split(r"[（(]", campus_text)[0].strip()
    return "本部"

def major_hint_from_campus(campus_text):
    """从 location.campus 文案抽 '0N 专业' 提示,用于校验 major↔campus 关联。"""
    m = re.search(r"(\d{2})\s*专业", campus_text or "")
    return m.group(1) if m else None

# ---------- 载入所有源 ----------
adm = load_json(os.path.join(KB, "chaoyang_admission_codes.json"))["schools"]
coords = load_json(os.path.join(KB, "chaoyang_coords.json"))["schools"]
cy = {s["name"]: s for s in load_yaml(os.path.join(KB, "chaoyang.yaml"))["schools"]}
private = load_yaml(os.path.join(KB, "chaoyang_private.yaml"))["schools"]
vocational = load_yaml(os.path.join(KB, "chaoyang_vocational.yaml"))["schools"]
new2026 = load_yaml(os.path.join(KB, "chaoyang_new2026.yaml"))["schools"]
pred_raw = load_json(os.path.join(KB, "ts", "pred_2026.json"))["pred"]
# 人工维护的别名补充层(按 code),不被重生成覆盖
_supp_path = os.path.join(KB, "registry", "chaoyang", "_aliases_supplement.yaml")
alias_supp = {}
if os.path.exists(_supp_path):
    alias_supp = {str(k): v for k, v in (load_yaml(_supp_path) or {}).items()} or {}
# pred 按代码索引(key 形如 '105004:北京市…' 或 'NEW:…')
pred_by_code = {}
pred_by_name = {}
for k, v in pred_raw.items():
    code, _, nm = k.partition(":")
    pred_by_code.setdefault(code, v)
    pred_by_name.setdefault(nm, v)

schools = []  # 生成的 School 实体

# ---------- PUBLIC:按 school_code 合并 ----------
groups = defaultdict(list)  # code -> [name_entry,...]
for nm, rec in adm.items():
    groups[rec.get("school_code") or ("NOCODE:" + nm)].append(nm)

for code, name_entries in groups.items():
    # 本部优先(名称不含括号);否则取第一个
    base = next((n for n in name_entries if not re.search(r"[（(]", n)), name_entries[0])
    rec0 = adm[base]
    canonical = rec0.get("plan_school_name") or base
    short = short_of(base)
    aliases = set()
    campuses, admissions = [], []
    for ne in name_entries:
        rec = adm[ne]
        aliases.update([ne, short_of(ne), rec.get("plan_school_name") or ne])
        # campus
        cs = (coords.get(ne) or {}).get("campuses") or []
        cam_slug = campus_slug(cs[0]["campus"] if cs else "", ne)
        cam_obj = {"slug": cam_slug,
                   "name": clean_campus_name(cs[0]["campus"] if cs else "", ne)}
        if cs:
            c0 = cs[0]
            cam_obj.update({"lat": c0.get("lat"), "lon": c0.get("lon"),
                            "address": c0.get("address"),
                            "confidence": c0.get("addr_confidence")})
            if c0.get("lat") is None:
                flag("WARN", code, f"{ne} 校区无坐标")
        else:
            flag("WARN", code, f"{ne} 缺 coords(无校区坐标)")
        # 住宿:从 cy location/campus 文案推断
        cyrec = cy.get(ne) or {}
        loc_text = ((cyrec.get("location") or {}).get("campus") or "")
        boarding = ("住宿" in loc_text) or ("住" in (cs[0]["campus"] if cs else ""))
        cam_obj["boarding"] = bool(boarding)
        if not any(c["slug"] == cam_slug for c in campuses):
            campuses.append(cam_obj)
        # admissions(每个 name_entry 的 majors → 录取单元)
        scores = cyrec.get("scores") or {}
        majors = rec.get("majors") or []
        hint = major_hint_from_campus(loc_text)
        # chaoyang.yaml 只记"校级一条线"。单 major 时即该 major 线;多 major 时只能归到
        # 普通班(代表线),其余专业(创新/中英/中美…)真实线源数据没有 → 不复制(避免伪精确),flag 待采。
        rep_major = next((m.get("major_code") for m in majors
                          if "普通" in (m.get("major_name") or "")), None) \
                    or (majors[0].get("major_code") if majors else None)
        for mj in majors:
            mcode = mj.get("major_code")
            if hint and mcode and hint != mcode:
                flag("REVIEW", code, f"{ne}: location 文案提示专业 {hint} 与代码表 {mcode} 不一致")
            au = OrderedDict()
            au["channel"] = "统招"
            au["code"] = code if not code.startswith("NOCODE") else None
            au["major"] = mcode
            au["major_name"] = mj.get("major_name")
            au["campus"] = cam_slug
            au["plan_total"] = mj.get("plan_total")
            au["plan_district"] = mj.get("plan_chaoyang")
            # 线:仅归到代表专业(普通班);多专业校的非普通班线源数据缺 → 留空 + flag
            if scores and mcode == rep_major:
                au["lines"] = {str(y): {"score": d.get("score"), "rank": d.get("rank"),
                                        "total": d.get("total")}
                               for y, d in sorted(scores.items(), reverse=True)}
                if len(majors) > 1:
                    au["line_scope"] = "校级代表线(普通班);源数据未分专业"
            elif not scores:
                flag("WARN", code, f"{ne} 缺历史录取线(scores)")
            else:
                au["line_scope"] = "缺本专业线(源数据仅校级);待 P3 采集"
                flag("REVIEW", code, f"{canonical} 专业{mcode}({mj.get('major_name')}) 缺独立录取线(P3采)")
            schools_pred = pred_by_code.get(code) or pred_by_name.get(canonical) or pred_by_name.get(short)
            if schools_pred:
                au["pred_2026"] = schools_pred
                if len([m for m in (rec.get("majors") or [])]) and len(name_entries) > 1:
                    flag("REVIEW", code, f"{canonical}: pred 仅按校级,未分 major(P3 细化)")
            admissions.append(au)
    cyrec0 = cy.get(base) or {}
    schools.append({
        "_sort": ("1public", code),
        "type": "公办普高",
        "canonical_name": canonical,
        "short_name": short,
        "aliases": sorted(a for a in aliases if a and a != short),
        "level": cyrec0.get("level"),
        "note": cyrec0.get("note"),
        "campuses": campuses,
        "admissions": admissions,
        "rollup": {k: cyrec0.get(k) for k in ("features",) if cyrec0.get(k)},
        "_codes": [code],
    })

# ---------- PRIVATE ----------
for s in private:
    code = s.get("code")
    pred = pred_by_code.get(code) or pred_by_name.get(s["name"])
    au = OrderedDict([("channel", "民办"), ("code", code), ("major", None),
                      ("direction", s.get("direction")), ("curriculum", s.get("curriculum")),
                      ("tuition", s.get("tuition")), ("boarding", s.get("boarding"))])
    if s.get("score_2025") is not None:
        au["lines"] = {"2025": {"score": s.get("score_2025")}}
    if pred: au["pred_2026"] = pred
    loc = s.get("location") or {}
    if loc.get("lat") is None: flag("WARN", code or s["name"], f"{s['name']} 民办无坐标")
    schools.append({
        "_sort": ("2private", code or s["name"]),
        "type": "民办", "canonical_name": s["name"], "short_name": short_of(s["name"]),
        "aliases": sorted(set(s.get("aliases") or []) | {code} if code else set(s.get("aliases") or [])),
        "level": s.get("nature"), "note": s.get("admission_note"),
        "campuses": [{"slug": "main", "name": "校本部", "lat": loc.get("lat"), "lon": loc.get("lon"),
                      "address": loc.get("address"), "confidence": loc.get("confidence"),
                      "boarding": bool(s.get("boarding"))}],
        "admissions": [au], "rollup": {}, "_codes": [code] if code else [],
    })

# ---------- VOCATIONAL ----------
for s in vocational:
    au = OrderedDict([("channel", "中职"), ("code", None), ("major", None),
                      ("comp_high_2025", s.get("comp_high_2025")), ("five_year", s.get("five_year"))])
    if s.get("lat") is None: flag("WARN", s["name"], f"{s['name']} 中职无坐标")
    schools.append({
        "_sort": ("3voc", s["name"]),
        "type": "中职", "canonical_name": s["name"], "short_name": short_of(s["name"]),
        "aliases": [], "level": s.get("type"), "note": s.get("note"),
        "campuses": [{"slug": "main", "name": "校本部", "lat": s.get("lat"), "lon": s.get("lon"),
                      "address": s.get("address"), "confidence": s.get("addr_conf"),
                      "boarding": bool(s.get("boarding"))}],
        "admissions": [au], "rollup": {"specialties": s.get("specialties")}, "_codes": [],
    })

# ---------- NEW 2026 ----------
for s in new2026:
    pred = pred_by_name.get(s["name"]) or pred_by_code.get("NEW")
    au = OrderedDict([("channel", "统招"), ("code", None), ("major", None),
                      ("est_rank", s.get("est_rank")),
                      ("est_range", [s.get("est_rank_lo"), s.get("est_rank_hi")]),
                      ("est_conf", s.get("est_conf")),
                      ("enroll_2026_est", s.get("enroll_2026_est"))])
    if pred: au["pred_2026"] = pred
    if s.get("lat") is None: flag("WARN", s["name"], f"{s['name']} 新校无坐标(待址公开)")
    schools.append({
        "_sort": ("4new", s["name"]),
        "type": "新校", "canonical_name": s["name"], "short_name": short_of(s["name"]),
        "aliases": [], "level": s.get("level"), "note": s.get("note"),
        "campuses": [{"slug": "main", "name": "校本部", "lat": s.get("lat"), "lon": s.get("lon"),
                      "address": s.get("address"), "confidence": s.get("confidence"),
                      "boarding": (s.get("boarding") if isinstance(s.get("boarding"), bool) else None)}],
        "admissions": [au], "rollup": {"system": s.get("system"), "evidence_refs": s.get("evidence_refs")},
        "_codes": [], "_estimate": True,
    })

# ---------- 分配 ID + 去重拼音冲突 ----------
schools.sort(key=lambda x: x["_sort"])
dpy = "cy"
seen_id = {}
for i, s in enumerate(schools, 1):
    ab = py_abbr(s["short_name"])
    sid = f"{dpy}-{i:03d}-{ab}"
    if ab in seen_id:
        flag("REVIEW", sid, f"拼音简写 '{ab}' 与 {seen_id[ab]} 重复(编号已区分,可人工改简写)")
    seen_id[ab] = s["short_name"]
    s["id"] = sid
    # 合并人工别名补充层(按 code)
    extra = []
    for c in (s.get("_codes") or []):
        extra += alias_supp.get(str(c), [])
    if extra:
        s["aliases"] = sorted(set(s.get("aliases") or []) | set(extra) - {s["short_name"]})

# ---------- 写出 ----------
OUT = os.path.join(KB, "registry", "chaoyang")
os.makedirs(OUT, exist_ok=True)
index = []
for s in schools:
    sid = s["id"]
    out = OrderedDict()
    for k in ("id", "canonical_name", "short_name", "type", "level", "note", "aliases",
              "campuses", "admissions", "rollup"):
        v = s.get(k)
        if v not in (None, {}, []):
            out[k] = v
    if s.get("_estimate"): out["estimate"] = True
    with open(os.path.join(OUT, sid + ".yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(to_plain(out), f, allow_unicode=True, sort_keys=False, width=100)
    index.append({"id": sid, "short_name": s["short_name"], "type": s["type"],
                  "codes": s.get("_codes"), "campuses": len(s["campuses"]),
                  "admissions": len(s["admissions"])})
with open(os.path.join(OUT, "_index.yaml"), "w", encoding="utf-8") as f:
    yaml.safe_dump(to_plain({"district": "朝阳区", "generated_by": "build_registry.py",
                    "count": len(schools), "schools": index}),
                   f, allow_unicode=True, sort_keys=False, width=100)

# ---------- 覆盖率/冲突报告 ----------
by_level = defaultdict(list)
for lv, tag, msg in report: by_level[lv].append((tag, msg))
lines = ["# 注册表覆盖率/冲突报告（P0 自动生成，待人工核）", "",
         f"- 学校实体数: **{len(schools)}**",
         f"  - 公办 {sum(1 for s in schools if s['type']=='公办普高')} / "
         f"民办 {sum(1 for s in schools if s['type']=='民办')} / "
         f"中职 {sum(1 for s in schools if s['type']=='中职')} / "
         f"新校 {sum(1 for s in schools if s['type']=='新校')}",
         f"- 多校区(>1 campus)学校: {sum(1 for s in schools if len(s['campuses'])>1)}",
         f"- 多录取单元(>1 admission)学校: {sum(1 for s in schools if len(s['admissions'])>1)}",
         f"- 问题项: REVIEW {len(by_level['REVIEW'])} / WARN {len(by_level['WARN'])}", ""]
for lv in ("REVIEW", "WARN"):
    if by_level[lv]:
        lines.append(f"## {lv}（{len(by_level[lv])}）")
        for tag, msg in by_level[lv]:
            lines.append(f"- `{tag}` {msg}")
        lines.append("")
with open(os.path.join(OUT, "_coverage_report.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"✅ 生成 {len(schools)} 校 → {OUT}")
print(f"   多校区 {sum(1 for s in schools if len(s['campuses'])>1)} 校, "
      f"REVIEW {len(by_level['REVIEW'])} / WARN {len(by_level['WARN'])}")
print(f"   报告: {os.path.join(OUT,'_coverage_report.md')}")
