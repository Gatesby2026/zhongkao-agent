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
_supp_path = os.path.join(KB, "registry", "cy", "_aliases_supplement.yaml")
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

# 以上均朝阳本区
for s in schools:
    s.setdefault("_district", "cy")

# ---------- 合并人工别名补充层(按 code),供后续本地解析 ----------
for s in schools:
    extra = []
    for c in (s.get("_codes") or []):
        extra += alias_supp.get(str(c), [])
    if extra:
        s["aliases"] = sorted(set(s.get("aliases") or []) | set(extra) - {s["short_name"]})

# ---------- 本地解析器(内存版,用于校额缩写→实体) ----------
_local = {}
def _idx(key, s):
    if key: _local.setdefault(str(key), s)
for s in schools:
    _idx(s.get("canonical_name"), s); _idx(s.get("short_name"), s)
    for a in (s.get("aliases") or []): _idx(a, s)
    for c in (s.get("_codes") or []): _idx(c, s)
def local_resolve(name):
    return _local.get(str(name))

# ---------- 校额到校:聚合每所朝阳高中的总名额,挂一条 channel ----------
try:
    xed = load_yaml(os.path.join(KB, "chaoyang_xeddx.yaml"))
    xed_total = defaultdict(int)      # school obj id(python) -> 名额合计
    xed_unresolved = set()
    for r in xed.get("rows", []):
        for hs, q in (r.get("by_school") or {}).items():
            tgt = local_resolve(hs)
            if tgt is None:
                xed_unresolved.add(hs); continue
            try: xed_total[id(tgt)] += int(q)
            except (TypeError, ValueError): pass
    for s in schools:
        tot = xed_total.get(id(s))
        if tot:
            s["admissions"].append(OrderedDict([
                ("channel", "校额到校"), ("code", None), ("major", None),
                ("metric", "校内排名"), ("slots_2025_total", tot),
                ("note", "名额按本初中校内排名分配;逐初中明细见 chaoyang_xeddx.yaml(P3 迁 id)"),
                ("source", xed.get("source_T1"))]))
    for hs in sorted(xed_unresolved):
        flag("REVIEW", "xeddx", f"校额缩写未解析: {hs}(补 _aliases_supplement.yaml)")
except FileNotFoundError:
    flag("WARN", "xeddx", "chaoyang_xeddx.yaml 缺失,校额 channel 未生成")

# ---------- 市级统筹:外区校 → 按归属区生成实体 + 统筹 channel ----------
DPY_BY_CN = {"东城": "dc", "西城": "xc", "海淀": "hd", "丰台": "ft", "石景山": "sjs",
             "朝阳": "cy", "通州": "tz", "顺义": "sy", "昌平": "cp", "大兴": "dx",
             "房山": "fs", "门头沟": "mtg", "平谷": "pg", "怀柔": "hr", "密云": "my",
             "延庆": "yq"}
try:
    tc = load_json(os.path.join(KB, "2025_sjtongchou_chaoyang.json"))
    # 同一所校可同时在统筹一+统筹二(如人大附中/清华附中)→ 合并为一个实体、两条统筹 channel
    # (而非两个实体撞同一 id)。合并键:school_code 优先,无码用 name。
    tc_groups = OrderedDict()
    for tier_key, tier_cn in (("tongchou_yi", "统筹一"), ("tongchou_er", "统筹二")):
        for r in tc.get(tier_key, []):
            gk = r.get("school_code") or r.get("name")
            tc_groups.setdefault(gk, []).append((tier_cn, r))
    for gk, recs in tc_groups.items():
        r0 = recs[0][1]
        home_cn = (r0.get("district") or "").strip()
        dpy_h = DPY_BY_CN.get(home_cn)
        if not dpy_h:
            flag("REVIEW", "tongchou", f"{r0.get('name')} 归属区未知({home_cn!r}),未建实体")
            continue
        admissions = []
        for tier_cn, r in recs:
            lines = {}
            for L in (r.get("score_lines") or []):
                if L.get("year") is not None:
                    ln = {"score": L.get("score") or L.get("line")}
                    if L.get("rank") is not None:
                        ln["rank"] = L["rank"]; ln["rank_scope"] = L.get("rank_scope")
                    lines[str(L["year"])] = ln
            if r.get("score_2025_tongzhao") is not None:
                lines.setdefault("2025", {"score": r.get("score_2025_tongzhao")})
            au = OrderedDict([
                ("channel", "市级统筹"), ("tier", tier_cn),
                ("code", r.get("school_code")), ("major", r.get("tongchou_major")),
                ("faces_chaoyang", r.get("faces_chaoyang")),
                ("quota_chaoyang", r.get("quota_chaoyang")),
                ("boarding", r.get("boarding"))])
            if lines: au["lines"] = lines
            admissions.append(au)
        if r0.get("lat") is None:
            flag("WARN", "tongchou", f"{r0.get('name')} 统筹校无坐标")
        schools.append({
            "_sort": (f"5tc{dpy_h}", r0.get("school_code") or r0.get("name")),
            "_district": dpy_h,
            "type": "市级统筹", "canonical_name": r0.get("name"),
            "short_name": short_of(r0.get("name")),
            "aliases": [x for x in [r0.get("school_code")] if x],
            "level": r0.get("level"), "note": (r0.get("style") or None),
            "campuses": [{"slug": "main", "name": r0.get("campus") or "本部",
                          "lat": r0.get("lat"), "lon": r0.get("lon"),
                          "address": r0.get("address"),
                          "confidence": r0.get("score_conf"),
                          "boarding": bool(r0.get("boarding"))}],
            "admissions": admissions,
            "rollup": {k: r0.get(k) for k in ("gaokao", "tags") if r0.get(k)},
            "_codes": [r0.get("school_code")] if r0.get("school_code") else [],
            "_home_cn": home_cn,
        })
except FileNotFoundError:
    flag("WARN", "tongchou", "市级统筹文件缺失,统筹实体未生成")

# ---------- 分配 ID（编号永久冻结：台账 _id_ledger.yaml）----------
# 关键:编号不靠排序位置(否则加/删校会错位),而靠"自然键→id"台账。台账缺失则按当前
# 排序首建(复现现有编号),此后只增不改;新校取该区最小空闲号。短名/拼音变了 id 也不变。
LEDGER_PATH = os.path.join(KB, "registry", "_id_ledger.yaml")
ledger = (load_yaml(LEDGER_PATH) or {}) if os.path.exists(LEDGER_PATH) else {}

def natural_key(s):
    """稳定自然键:公办/统筹/民办优先录取代码,无码用 类型+canonical_name。"""
    code = next((c for c in (s.get("_codes") or []) if c), None)
    return f"{s['type']}:{code or s['canonical_name']}"

schools.sort(key=lambda x: (x["_district"], x["_sort"]))   # 仅决定"首建"时的初始编号顺序
used = defaultdict(set)
for _nk, _sid in ledger.items():
    m = re.match(r"([a-z]+)-(\d+)-", str(_sid))
    if m:
        used[m.group(1)].add(int(m.group(2)))
seen_ab = {}
for s in schools:
    dpy = s["_district"]
    nk = natural_key(s)
    if nk in ledger:
        s["id"] = ledger[nk]                 # 冻结:沿用台账 id(含原编号与拼音)
    else:
        n = 1
        while n in used[dpy]:
            n += 1
        used[dpy].add(n)
        s["id"] = f"{dpy}-{n:03d}-{py_abbr(s['short_name'])}"
        ledger[nk] = s["id"]                  # 新校:登记并冻结
    ab = re.sub(r"^[a-z]+-\d+-", "", s["id"])
    if ab in seen_ab and seen_ab[ab] != s["short_name"]:
        flag("REVIEW", s["id"], f"拼音简写 '{ab}' 与 {seen_ab[ab]} 重复(编号已区分)")
    seen_ab[ab] = s["short_name"]

with open(LEDGER_PATH, "w", encoding="utf-8") as f:
    yaml.safe_dump({"_doc": "学校 id 永久台账:自然键(类型:代码|校名)→冻结 id。只增不改;勿手删。",
                    **{k: ledger[k] for k in sorted(ledger)}},
                   f, allow_unicode=True, sort_keys=False, width=100)

# ---------- 写出(按区分目录) ----------
REG = os.path.join(KB, "registry")
dists = sorted({s["_district"] for s in schools})
# 清理上次生成的学校 yaml(保留 _ 开头的人工/索引文件)
import glob as _glob
for d in dists:
    for fp in _glob.glob(os.path.join(REG, d, "*.yaml")):
        if not os.path.basename(fp).startswith("_"):
            os.remove(fp)
index_by_dist = defaultdict(list)
for s in schools:
    sid = s["id"]; dpy = s["_district"]
    out = OrderedDict()
    out_keys = ("id", "canonical_name", "short_name", "type", "level", "note", "aliases",
                "campuses", "admissions", "rollup")
    for k in out_keys:
        v = s.get(k)
        if v not in (None, {}, []):
            out[k] = v
    if s["_district"] != "cy":
        out["home_district"] = s.get("_home_cn")    # 外区(统筹)校标注归属区
    if s.get("_estimate"): out["estimate"] = True
    dd = os.path.join(REG, dpy); os.makedirs(dd, exist_ok=True)
    with open(os.path.join(dd, sid + ".yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(to_plain(out), f, allow_unicode=True, sort_keys=False, width=100)
    index_by_dist[dpy].append({"id": sid, "short_name": s["short_name"], "type": s["type"],
                  "codes": s.get("_codes"), "campuses": len(s["campuses"]),
                  "admissions": [a.get("channel") for a in s["admissions"]]})
for dpy, idx in index_by_dist.items():
    with open(os.path.join(REG, dpy, "_index.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(to_plain({"district": dpy, "generated_by": "build_registry.py",
                        "count": len(idx), "schools": idx}),
                       f, allow_unicode=True, sort_keys=False, width=100)
OUT = os.path.join(REG, "cy")

# ---------- 覆盖率/冲突报告 ----------
by_level = defaultdict(list)
for lv, tag, msg in report: by_level[lv].append((tag, msg))
def cnt(t): return sum(1 for s in schools if s["type"] == t)
dist_breakdown = ", ".join(f"{d}:{sum(1 for s in schools if s['_district']==d)}"
                           for d in sorted({s["_district"] for s in schools}))
lines = ["# 注册表覆盖率/冲突报告（P0 自动生成，待人工核）", "",
         f"- 学校实体数: **{len(schools)}**（按区: {dist_breakdown}）",
         f"  - 公办 {cnt('公办普高')} / 民办 {cnt('民办')} / 中职 {cnt('中职')} / "
         f"新校 {cnt('新校')} / 市级统筹(外区) {cnt('市级统筹')}",
         f"- 多校区(>1 campus)学校: {sum(1 for s in schools if len(s['campuses'])>1)}",
         f"- 多录取单元(>1 admission)学校: {sum(1 for s in schools if len(s['admissions'])>1)}",
         f"- 含「校额到校」channel: {sum(1 for s in schools if any(a.get('channel')=='校额到校' for a in s['admissions']))}",
         f"- 含「市级统筹」channel: {sum(1 for s in schools if any(a.get('channel')=='市级统筹' for a in s['admissions']))}",
         f"- 问题项: REVIEW {len(by_level['REVIEW'])} / WARN {len(by_level['WARN'])}", ""]
for lv in ("REVIEW", "WARN"):
    if by_level[lv]:
        lines.append(f"## {lv}（{len(by_level[lv])}）")
        for tag, msg in by_level[lv]:
            lines.append(f"- `{tag}` {msg}")
        lines.append("")
with open(os.path.join(OUT, "_coverage_report.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"✅ 生成 {len(schools)} 校(按区 {dist_breakdown}) → {REG}")
print(f"   校额channel {sum(1 for s in schools if any(a.get('channel')=='校额到校' for a in s['admissions']))} 校 / "
      f"统筹外区校 {cnt('市级统筹')} 所")
print(f"   REVIEW {len(by_level['REVIEW'])} / WARN {len(by_level['WARN'])}  报告: {os.path.join(OUT,'_coverage_report.md')}")
