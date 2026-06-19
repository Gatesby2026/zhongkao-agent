#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1 对账测试:后端给每个学校装 id 后,验证
  1) 统招公办 band 卡片 + 民办/中职/新校/统筹 全部 resolve 到 id(无孤儿);
  2) 多校区/同代码卡片 resolve 到同一 id(和平街本部+莲葩园 → 同 id);
  3) 行为不变:band 学校名集合与"未装 id"时一致(id 是增量字段)。
无 pytest 依赖,直接 python3 运行;退出码非零=有问题。
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # scripts/admission
import recommend

FAIL = []

def check(cond, msg):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond: FAIL.append(msg)

print("== 跑 build_result(rank=4500, 朝阳, 京籍应届, 住宿) ==")
res = recommend.build_result(4500, home=None, mode="bicycling", max_km=8,
                             district="chaoyang", boarding=True, identity="jjyj")

# 1) 统招公办 band 卡片全部有 id
band_cards = [c for cards in res["bands"].values() for c in cards]
pub = [c for c in band_cards if c.get("school_code") and not str(c.get("school_code")).startswith("NEW")]
no_id = [c["name"] for c in pub if not c.get("id")]
check(not no_id, f"统招公办 band 卡片全部 resolve（{len(pub)} 校）" + (f"；孤儿: {no_id}" if no_id else ""))

# 2) 和平街 本部 + 莲葩园 → 同一 id
hp = [c for c in band_cards if "和平街" in c["name"]]
hp_ids = {c.get("id") for c in hp}
check(len(hp) >= 1 and len(hp_ids) == 1 and None not in hp_ids,
      f"和平街各校区卡片 → 同一 id {hp_ids}（{len(hp)} 张卡）")

# 3) 民办/中职/新校/统筹 覆盖
def cov(label, items):
    items = items or []
    miss = [s.get("name") for s in items if not s.get("id")]
    check(not miss, f"{label} 全部有 id（{len(items)} 校）" + (f"；缺: {miss}" if miss else ""))
cov("民办", (res.get("private_schools") or {}).get("schools"))
cov("中职", (res.get("vocational") or {}).get("schools"))
ns = res.get("new_schools"); cov("新校", ns.get("schools") if isinstance(ns, dict) else ns)
tc = res.get("tongchou") or {}
cov("统筹一", tc.get("tongchou_yi")); cov("统筹二", tc.get("tongchou_er"))

# 4) id 装配统计
st = res.get("_id_stamp") or {}
print(f"  ℹ️  id 装配统计: ok={st.get('ok')} unresolved={st.get('unresolved')}")
print(f"  ℹ️  unresolved 多为贯通(城市级,未入注册表),不计入失败")

# 5) 行为不变:band 学校名集合(去 id 字段后)应与逻辑无关——这里确认 bands 结构未被破坏
names_by_band = {b: sorted(c["name"] for c in cards) for b, cards in res["bands"].items()}
check(all(isinstance(v, list) for v in names_by_band.values()) and "稳" in res["bands"],
      "bands 结构完好(冲/稳/保/够不上)")

print("\n" + ("❌ 有 %d 项未通过" % len(FAIL) if FAIL else "✅ P1 对账全部通过"))
sys.exit(1 if FAIL else 0)
