#!/usr/bin/env python3
"""B-P3 回归基线:对一组 (区, 排名) 跑 build_result,把关键输出归一化成 JSON 快照。
改 load_district 走 registry 后再跑一次,与基线 diff 必须一致(home=None 跳测距,保证确定性)。

用法:
  python regress_snapshot.py before > /tmp/reg_before.json
  python regress_snapshot.py after  > /tmp/reg_after.json
  python regress_snapshot.py diff    # 比较 before/after
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recommend  # noqa: E402

MATRIX = [
    ("chaoyang", 1500), ("chaoyang", 4500), ("chaoyang", 8000),
    ("haidian", 600), ("haidian", 3000), ("haidian", 11000),
    ("xicheng", 2000), ("dongcheng", 3000),
    ("fengtai", 3000), ("tongzhou", 2000), ("changping", 2500),
    ("daxing", 2000), ("shijingshan", 1500), ("fangshan", 3000), ("shunyi", 2500),
]


def card_sig(c):
    """卡片关键字段(去掉随运行变化的内部/距离字段)。"""
    return {
        "name": c.get("name"), "level": c.get("level"),
        "ref_rank": c.get("ref_rank"), "margin_pct": c.get("margin_pct"),
        "score_lines": c.get("score_lines"), "history": c.get("history"),
        "pred_2026": c.get("pred_2026"),
        "style": c.get("style"), "tags": c.get("tags"), "gaokao": c.get("gaokao"),
        "campus_life": bool(c.get("campus_life")),
        "id": c.get("id"),
    }


def snap_one(district, rank):
    r = recommend.build_result(rank=rank, district=district)   # home=None → 不测距,确定性
    bands = {b: [card_sig(c) for c in r["bands"].get(b, [])] for b in r.get("bands", {})}
    uni = sorted(
        ({"name": s.get("name"), "type": s.get("type"), "level": s.get("level"),
          "boarding": s.get("boarding"),
          "feat": bool((s.get("features") or {}).get("tags") or s.get("features_std")),
          "gk": bool(s.get("gaokao")), "cl": bool(s.get("campus_life")),
          "pred": (s.get("pred_2026") or {}).get("rank")}
         for s in (r.get("schools_unified") or [])),
        key=lambda x: (x["type"] or "", x["name"] or ""))
    return {"bands": bands, "unified": uni, "est_score": r.get("est_score")}


def snapshot():
    return {f"{d}:{rk}": snap_one(d, rk) for d, rk in MATRIX}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "before"
    if mode == "diff":
        a = json.load(open("/tmp/reg_before.json", encoding="utf-8"))
        b = json.load(open("/tmp/reg_after.json", encoding="utf-8"))
        import difflib
        sa = json.dumps(a, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
        sb = json.dumps(b, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
        diff = list(difflib.unified_diff(sa, sb, "before", "after", lineterm=""))
        if not diff:
            print("✅ 零差异:registry 改造后 build_result 与基线完全一致")
        else:
            print(f"⚠️ {len([d for d in diff if d.startswith(('+','-')) and not d.startswith(('++','--'))])} 行差异:")
            print("\n".join(diff[:120]))
    else:
        print(json.dumps(snapshot(), ensure_ascii=False, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
