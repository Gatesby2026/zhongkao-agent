#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市级统筹校 → 朝阳口径 2026 预估 + 统筹门槛(经验折让)。把统筹校归到与区内普高同一把尺。

链路:
  外区统招线(历年) → 外区位次(本区) → ×(朝阳池/外区池) = 朝阳等效统招位次(=学校档次,可与区内校比)
  → ×生源系数(2026参加/2025参加) = pred_2026(朝阳口径位次)
  → ×(1+经验折让) = 统筹门槛(朝阳口径位次;统筹定向名额、竞争小,门槛低于等效统招档)

折让(经验·位次空间·全部标注):base 8% + 名额(每朝阳名额 0.5%,上限12%) + 远近郊(城区0/近郊4%/远郊8%),封顶30%。
写回 2025_sjtongchou_chaoyang.json 每条:cy_equiv_2025 / pred_2026_cy / tongchou_entry_cy / discount_pct / pred_conf / pred_basis。
不编造:无外区位次的(4所无线校)→ 只标控制线兜底,不给等效/pred。
"""
import json, os, re
import yaml

KB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge-base", "admission", "beijing"))
N_CY_2025 = 10729
N_CY_2026 = 12000            # 朝阳 2026 参加中考估(生源高峰,见 RANK-PREDICTION 设计)
SHENGYUAN = N_CY_2026 / N_CY_2025

pool = json.load(open(os.path.join(KB, "district_pool_sizes.json")))["pool"]["2025"]
DPOOL = {"海淀": pool["haidian"], "西城": pool["xicheng"], "东城": pool["dongcheng"],
         "丰台": pool["fengtai"], "通州": pool["tongzhou"], "顺义": pool["shunyi"],
         "石景山": pool["shijingshan"], "昌平": pool["changping"], "朝阳": N_CY_2025}

def dyaml(fn):
    p = os.path.join(KB, fn + ".yaml")
    return {s["name"]: s.get("scores") or {} for s in yaml.safe_load(open(p))["schools"]} if os.path.exists(p) else {}
HD, XC, DC, CY = dyaml("haidian"), dyaml("xicheng"), dyaml("dongcheng"), dyaml("chaoyang")
# 本部名校外区位次取自区档案(统筹官方名 → (区dict, 区内简称))
MAP = {"中国人民大学附属中学": (HD, "人大附中"), "清华大学附属中学": (HD, "清华附中"),
       "北京大学附属中学": (HD, "北大附中"), "北京市第一〇一中学": (HD, "101中学"),
       "北京市第四中学": (XC, "北京四中"), "北京市第八中学": (XC, "北京八中"),
       "北京师范大学附属实验中学": (XC, "北师大实验中学"), "北京师范大学附属中学": (XC, "北师大附中"),
       "北京师范大学第二附属中学": (XC, "北师大二附中"),
       "北京市第五中学": (DC, "北京五中"), "北京汇文中学": (DC, "汇文中学"),
       "北京市第八十中学": (CY, "北京市第八十中学"), "北京市陈经纶中学": (CY, "陈经纶中学")}
FARQ = {"门头沟", "平谷", "昌平", "怀柔", "密云", "延庆"}      # 远郊
NEARQ = {"通州", "顺义", "大兴", "房山", "石景山"}             # 近郊

def waidi_rank_2025(rec):
    """外区2025位次:优先 score_lines[2025].rank(已采的8所),否则区档案本部名校。"""
    for L in (rec.get("score_lines") or []):
        if L.get("year") == 2025 and L.get("rank") is not None:
            return L["rank"], (L.get("rank_scope") or "").replace("区", "") or rec.get("district")
    nm = rec["name"]
    if nm in MAP and (not rec.get("campus") or "本部" in (rec.get("campus") or "")):
        sc = MAP[nm][0].get(MAP[nm][1], {}).get(2025) or {}
        if sc.get("rank"):
            return sc["rank"], rec.get("district")
    return None, None

# 无统招线校的锚定法(本校只招1+3/统筹二,无统招位次可映射 → 用名校本部朝阳等效×折让倍数)。
# (匹配子串, 本部朝阳等效位次, 折让倍数, 依据)。倍数=直属/一体化校区生源弱于本部统招的经验放大。
ANCHOR = [
    ("将台路", 696, 3.5, "清华附中直属校区·共享本部师资,但统筹二/1+3生源弱于本部统招(本部等效696×3.5)"),
    ("京西", 1265, 2.6, "北京八中一体化管理校区·门头沟·统筹二(本部等效1265×2.6)"),
    ("未来科学城", 1681, 2.2, "师大二附承办校区·昌平·2024本科93%/一本40%中等实绩(本部等效1681×2.2)"),
]
CONTROL_FLOOR_CY = 3741   # 控制线460分→朝阳2025位次(工大附中460/3741锚);无线郊区保底校贴此

def discount(rec):
    d = 0.08
    q = rec.get("quota_chaoyang") or 0
    d += min(0.12, q * 0.005)
    dist = rec.get("district")
    d += 0.08 if dist in FARQ else (0.04 if dist in NEARQ else 0.0)
    return round(min(d, 0.30), 3)

def main():
    p = os.path.join(KB, "2025_sjtongchou_chaoyang.json")
    data = json.load(open(p))
    done = []
    for tier_key, tier in (("tongchou_yi", "统筹一"), ("tongchou_er", "统筹二")):
        for rec in data.get(tier_key, []):
            wr, wd = waidi_rank_2025(rec)
            npl = DPOOL.get(wd) if wd else None
            if wr is None or not npl:
                # 无统招线 → 锚定法(名校本部×折让)或控制线兜底,绝不留空(大机会点必须可决策)
                tag = (rec.get("name") or "") + (rec.get("campus") or "")
                anc = next((a for a in ANCHOR if a[0] in tag), None)
                if anc:
                    equiv = round(anc[1] * anc[2])
                    conf = "估·锚定(名校本部×折让·非线映射·务必核实)"
                    basis_pre = anc[3]
                else:
                    equiv = CONTROL_FLOOR_CY                  # 郊区保底校:贴控制线
                    conf = "估·控制线锚定占位(信息少·务必核实)"
                    basis_pre = "无本部可锚·郊区保底校→贴控制线460(朝阳≈3741位)"
                pred = round(equiv * SHENGYUAN)
                disc = discount(rec)
                entry = min(round(pred * (1 + disc)), round(CONTROL_FLOOR_CY * SHENGYUAN))  # 门槛不松于控制线
                rec["cy_equiv_2025"] = equiv
                rec["pred_2026_cy"] = {"rank": pred, "lo": round(pred * 0.75), "hi": round(pred * 1.25),
                                       "pct": round(pred / N_CY_2026 * 100, 1)}
                rec["tongchou_entry_cy"] = {"rank": entry, "pct": round(entry / N_CY_2026 * 100, 1)}
                rec["discount_pct"] = disc
                rec["pred_conf"] = conf
                rec["pred_basis"] = f"{basis_pre}=等效{equiv}→×生源{SHENGYUAN:.3f}=预估{pred};门槛{entry}(不松于控制线)"
                continue
            equiv = round(wr * N_CY_2025 / npl)              # 朝阳等效统招位次(2025)
            pred = round(equiv * SHENGYUAN)                  # 2026 朝阳口径位次
            disc = discount(rec)
            entry = round(pred * (1 + disc))                 # 统筹门槛(更易,位次更大)
            official = any(L.get("year") == 2025 and L.get("conf") in ("双源确认",) for L in (rec.get("score_lines") or [])) \
                       or rec["name"] in MAP
            conf = "估·外区线官方+映射" if official else "估·外区线网传+映射"
            rec["cy_equiv_2025"] = equiv
            rec["pred_2026_cy"] = {"rank": pred, "lo": round(pred * 0.82), "hi": round(pred * 1.18),
                                   "pct": round(pred / N_CY_2026 * 100, 1)}
            rec["tongchou_entry_cy"] = {"rank": entry, "pct": round(entry / N_CY_2026 * 100, 1)}
            rec["discount_pct"] = disc
            rec["pred_conf"] = conf
            rec["pred_basis"] = (f"外区{wd}位次{wr}×(朝阳{N_CY_2025}/{wd}池{npl})=等效{equiv}"
                                 f"→×生源{SHENGYUAN:.3f}=2026预估{pred};门槛=×(1+折让{disc})={entry}")
            done.append((pred, rec["name"] + (("·" + rec["campus"]) if rec.get("campus") and rec["campus"] != "本部" else ""),
                         tier, equiv, pred, entry, disc, conf))
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    done.sort()
    print(f"{'预估':>5} {'等效':>5} {'门槛':>5} {'折让':>5}  学校")
    print("-" * 60)
    for pr, nm, t, eq, pred, entry, disc, conf in done:
        print(f"{pred:>5} {eq:>5} {entry:>5} {disc*100:>4.0f}%  统筹{t} {nm}  [{conf}]")
    nofill = sum(1 for tk in ("tongchou_yi", "tongchou_er") for r in data.get(tk, []) if r.get("pred_conf") == "控制线兜底")
    print(f"\n已算 {len(done)} 校 / 控制线兜底(无等效) {nofill} 校")

if __name__ == "__main__":
    main()
