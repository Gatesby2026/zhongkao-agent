#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学校解析库:把任意"脏名字/代码"解析到稳定 school_id。全系统唯一身份入口。
注册表是唯一事实源(registry/<区>/*.yaml)。P1 起后端 import 此模块替代字符串匹配。
"""
import os, re, glob, functools
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REG = os.path.join(ROOT, "knowledge-base", "admission", "beijing", "registry")

def _norm(s):
    """归一:去空白/括号后缀/北京市前缀,统一别名书写差异。仅用于兜底匹配,不做语义改写。"""
    s = str(s or "")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"^北京市?", "", s)
    return s

@functools.lru_cache(maxsize=None)
def _load(district=None):
    """district=None → 加载全部区(跨区 resolve,统筹外区校可命中);否则只该区。"""
    by_id, alias2id, norm2id = {}, {}, {}
    pat = os.path.join(REG, district if district else "*", "*.yaml")
    for fp in glob.glob(pat):
        if os.path.basename(fp).startswith("_"):
            continue
        with open(fp, encoding="utf-8") as f:
            s = yaml.safe_load(f)
        sid = s["id"]; by_id[sid] = s
        keys = {s.get("canonical_name"), s.get("short_name"), *(s.get("aliases") or [])}
        for a in (s.get("admissions") or []):
            if a.get("code"):
                keys.add(str(a["code"]))
        for k in keys:
            if not k:
                continue
            alias2id[str(k)] = sid
            norm2id.setdefault(_norm(k), sid)
    return by_id, alias2id, norm2id

def resolve(name_or_code, district=None):
    """-> school_id 或 None。优先精确(别名/代码),再归一兜底。默认跨全区。"""
    by_id, alias2id, norm2id = _load(district)
    k = str(name_or_code or "").strip()
    if k in by_id:
        return k
    if k in alias2id:
        return alias2id[k]
    return norm2id.get(_norm(k))

def get(school_id, district=None):
    return _load(district)[0].get(school_id)

if __name__ == "__main__":
    import sys
    for q in sys.argv[1:]:
        print(f"{q!r} -> {resolve(q)}")
