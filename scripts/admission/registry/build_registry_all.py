#!/usr/bin/env python3
"""B-P1: 把非朝阳各区的扁平数据装配成 registry 实体(与朝阳 registry 同 schema)。

合并键 = school_code(统招计划册的 6 位码,稳定);所有来源出现过的校名 union 进 aliases
→ 根治"同一校多种写法对不上"(今天校额漏判那类 bug)。

输入(每区,缺则跳过该来源):
  districts/<py>_admission_codes.json  统招码+正名+专业(plan_total)
  districts/<py>_coords.json           GCJ-02 坐标 → campus
  <py>.yaml                            scores/level/note/features/gaokao/campus_life/pred_2026/boarding
  districts/_name_aliases.json[py]     正名↔简称(反挂为 aliases)

输出: registry/<regcode>/<id>.yaml  (id = <regcode>-<NNN>-<拼音声母>)
朝阳(cy)有自己的 build_registry.py(更全:含民办/中职/贯通/校额),本脚本不动 cy。
"""
import json
import os
import re
import sys
from collections import defaultdict

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.abspath(os.path.join(HERE, "..", "..", "..", "knowledge-base", "admission", "beijing"))
DIST = os.path.join(KB, "districts")
REG = KB  # registry 根 = .../beijing/registry

PY2REG = {"haidian": "hd", "xicheng": "xc", "dongcheng": "dc", "fengtai": "ft",
          "shijingshan": "sjs", "mentougou": "mtg", "fangshan": "fs", "tongzhou": "tz",
          "shunyi": "sy", "changping": "cp", "daxing": "dx", "huairou": "hr",
          "pinggu": "pg", "miyun": "my", "yanqing": "yq"}

_PYIN = {}  # 懒加载 pypinyin;无则用名字 hash 兜底


def py_abbr(s):
    """汉字串 → 拼音声母串;无 pypinyin 库则取每字 unicode 兜底(保证 id 稳定可重现)。"""
    s = re.sub(r"[^一-龥A-Za-z0-9]", "", s or "")
    try:
        from pypinyin import lazy_pinyin, Style
        return "".join(p[0] for p in lazy_pinyin(s, style=Style.FIRST_LETTER) if p)[:12] or "x"
    except Exception:
        return ("x" + "".join(f"{ord(c) % 36:x}" for c in s[:6])) or "x"


_SUF = re.compile(r"(北京市?|北京)?(.*?)(学校|中学|实验学校)?$")


def short_of(name):
    n = re.sub(r"^北京市?", "", name or "")
    return n or name


def load(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f) if p.endswith(".json") else yaml.safe_load(f)


def glob_yaml(d):
    import glob
    return [p for p in glob.glob(os.path.join(d, "*.yaml"))
            if not os.path.basename(p).startswith("_")]


def build_district(py):
    reg = PY2REG[py]
    codes_raw = (load(os.path.join(DIST, f"{py}_admission_codes.json")) or {}).get("schools", {})
    if not codes_raw:
        return None
    # districts codes 以 school_code 为键 → 统一成 name 键(与本builder其余逻辑一致)
    codes = {}
    for k, v in codes_raw.items():
        nm = v.get("name") or v.get("plan_school_name") or k
        v = dict(v)
        v.setdefault("school_code", k)
        codes[nm] = v
    coords = (load(os.path.join(DIST, f"{py}_coords.json")) or {}).get("schools", {})
    cy = load(os.path.join(KB, f"{py}.yaml")) or {}
    by_name = {s["name"]: s for s in cy.get("schools", [])}
    alias_map = (load(os.path.join(DIST, "_name_aliases.json")) or {}).get(py, {})
    # 正名 → [简称...]
    rev_alias = defaultdict(list)
    for short, zheng in alias_map.items():
        rev_alias[zheng].append(short)

    # 按 school_code 合并(同码多 name → 一实体)
    groups = defaultdict(list)
    for nm, rec in codes.items():
        groups[rec.get("school_code") or ("NOCODE:" + nm)].append(nm)

    out = []
    seq = 0
    for code, names in sorted(groups.items(), key=lambda kv: kv[0]):
        seq += 1
        base = next((n for n in names if not re.search(r"[（(]", n)), names[0])
        rec0 = codes[base]
        canonical = rec0.get("plan_school_name") or base
        aliases = set()
        campuses, admissions = [], []
        cyrec = {}
        for ne in names:
            rec = codes[ne]
            aliases.update([ne, rec.get("plan_school_name") or ne, *rev_alias.get(ne, [])])
            co = coords.get(ne) or {}
            cam = {"slug": "benbu",
                   "name": co.get("formatted") or ne,
                   "lat": co.get("lat"), "lon": co.get("lon"),
                   "confidence": co.get("conf"),
                   "source": "高德 geocode（待电话核实）"}
            cyrec = by_name.get(ne) or cyrec
            bd = (cyrec.get("boarding") is True)
            cam["boarding"] = bool(bd)
            if not any(c["name"] == cam["name"] for c in campuses):
                campuses.append(cam)
            scores = cyrec.get("scores") or {}
            majors = rec.get("majors") or []
            rep = next((m.get("major_code") for m in majors if "普通" in (m.get("major_name") or "")),
                       (majors[0].get("major_code") if majors else None))
            for mj in majors:
                au = {"channel": "统招", "code": code if not str(code).startswith("NOCODE") else None,
                      "major": mj.get("major_code"), "major_name": mj.get("major_name"),
                      "campus": "benbu", "plan_total": mj.get("plan_total")}
                if scores and mj.get("major_code") == rep:
                    au["lines"] = {str(y): {"score": d.get("score"), "rank": d.get("rank"),
                                            "total": d.get("total")}
                                   for y, d in scores.items() if isinstance(d, dict)}
                    if cyrec.get("scores_meta"):
                        au["lines_meta"] = cyrec["scores_meta"]
                    if cyrec.get("pred_2026"):
                        au["pred_2026"] = cyrec["pred_2026"]
                admissions.append(au)
        rollup = {}
        for k in ("features", "gaokao", "campus_life"):
            if cyrec.get(k):
                rollup[k] = cyrec[k]
        out.append({
            "id": f"{reg}-{seq:03d}-{py_abbr(short_of(canonical))}",
            "type": "公办普高",
            "canonical_name": canonical,
            "short_name": short_of(base),
            "aliases": sorted(a for a in aliases if a and a != canonical),
            "level": cyrec.get("level"),
            "note": cyrec.get("note") or "",
            "campuses": campuses,
            "admissions": admissions,
            "rollup": rollup,
            "_codes": [code] if not str(code).startswith("NOCODE") else [],
        })
    # 写出——若已存在同名实体(如市级统筹视角的人朝),合并而非覆盖:
    # 保留原 id;把本区"统招"等渠道并入其 admissions;union aliases;补 rollup。
    odir = os.path.join(REG, "registry", reg)
    os.makedirs(odir, exist_ok=True)
    existing = {}
    for fp in glob_yaml(odir):
        e = load(fp)
        if e and e.get("canonical_name"):
            existing[e["canonical_name"]] = (fp, e)
    import glob as _g
    for s in out:
        if s["canonical_name"] in existing:
            fp, e = existing[s["canonical_name"]]
            def akey(a):
                return (a.get("channel"), str(a.get("code")), str(a.get("major")))
            have = {akey(a) for a in (e.get("admissions") or [])}
            for a in s["admissions"]:
                if akey(a) not in have:
                    e.setdefault("admissions", []).append(a)
            e["aliases"] = sorted(set(e.get("aliases") or []) | set(s["aliases"]) | {s["canonical_name"]}
                                  - {e.get("canonical_name")})
            for k, v in (s.get("rollup") or {}).items():
                e.setdefault("rollup", {}).setdefault(k, v)
            if not e.get("campuses") or e["campuses"][0].get("lat") is None:
                e["campuses"] = s["campuses"]
            e.setdefault("level", s.get("level")); e["note"] = e.get("note") or s.get("note")
            path = fp
            data = e
        else:
            path = os.path.join(odir, s["id"] + ".yaml")
            data = s
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=120)
    n_line = sum(1 for s in out for a in s["admissions"] if a.get("lines"))
    n_feat = sum(1 for s in out if s["rollup"].get("features"))
    print(f"  {py}({reg}): {len(out)}校 | 有线{n_line} 特色{n_feat} "
          f"坐标{sum(1 for s in out if s['campuses'][0].get('lat'))}")
    return out


def main():
    args = sys.argv[1:] or list(PY2REG)
    print(f"装配 registry(全市非朝阳) {len(args)} 区:")
    for py in args:
        if py in PY2REG:
            build_district(py)


if __name__ == "__main__":
    main()
