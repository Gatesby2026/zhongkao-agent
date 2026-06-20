#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市级统筹校 → 朝阳口径 2026 预估 + 统筹门槛。归到与区内普高同一把尺(朝阳位次)。

★方法(用户校正):中考全市统一卷 → **分数全市可比,位次百分位不可比**。
  旧"外区位次→百分位→朝阳同百分位"会系统性夸大郊区校(郊区生源弱、同位次分数低)。
  改为 **线分 → 朝阳一分一段 → 朝阳位次**:该校线分 X = "朝阳考 X 分排第几" = 真实档次。
  例:人大附中通州校区线465 → 朝阳第2966位(而非旧百分位法的1604,虚高)。

链路:
  该校2025统招线分 → 朝阳一分一段累计 = 朝阳等效位次(档次) → ×生源系数 = pred_2026(朝阳口径)
  → ×(1+经验折让:base8%+名额+远近郊) = 统筹门槛(统筹定向、需求低 → 门槛比档次松)
无统招线校(只招1+3/统筹二)→ 锚定法:名校本部线分→朝阳位次 ×折让倍数;郊区保底贴控制线。
全部估算标 conf+basis,不编造。
"""
import json, os
import yaml

KB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge-base", "admission", "beijing"))
N_CY_2025 = 10729
N_CY_2026 = 12000
SHENGYUAN = N_CY_2026 / N_CY_2025

# 朝阳 2025 一分一段(分→累计人数=该分及以上)。源:gaokzx 2025朝阳一分一段。
CY2025 = {410: 8741, 420: 8229, 423: 8016, 430: 7479, 432: 7272, 434: 7077, 438: 6617,
          444: 5964, 448: 5438, 452: 4914, 454: 4635, 455: 4487, 459: 3897, 461: 3604,
          463: 3301, 465: 2966, 466: 2830, 468: 2533, 469: 2376, 471: 2070, 474: 1623,
          475: 1483, 476: 1357, 477: 1221, 478: 1097, 481: 783, 482: 685, 484: 541,
          487: 338, 488: 282, 491: 153}
_KS = sorted(CY2025)

def cy_rank(score):
    """朝阳考该分→朝阳位次(累计);非整表点线性插值,范围外夹取。"""
    if score is None:
        return None
    if score in CY2025:
        return CY2025[score]
    if score <= _KS[0]:
        return CY2025[_KS[0]]
    if score >= _KS[-1]:
        return CY2025[_KS[-1]]
    lo = max(k for k in _KS if k < score)
    hi = min(k for k in _KS if k > score)
    f = (score - lo) / (hi - lo)
    return round(CY2025[lo] + f * (CY2025[hi] - CY2025[lo]))

CONTROL_LINE = 460                          # 朝阳指标分配最低控制线/510
CONTROL_FLOOR = cy_rank(CONTROL_LINE)       # ≈3750 朝阳位次(无线郊区保底贴此)
# 无统招线校锚定:(匹配子串, 名校本部线分, 折让倍数, 依据)
ANCHOR = [
    ("将台路", 487, 7.0, "清华附中直属校区·共享本部师资,但统筹二/1+3生源远弱于本部统招(本部线487→朝阳338×7)"),
    ("京西", 481, 4.0, "北京八中一体化管理校区·门头沟·统筹二(本部线481→朝阳783×4)"),
    ("未来科学城", 478, 3.0, "师大二附承办校区·昌平·2024本科93%/一本40%中等实绩(本部线478→朝阳1097×3)"),
]
FARQ = {"门头沟", "平谷", "昌平", "怀柔", "密云", "延庆"}
NEARQ = {"通州", "顺义", "大兴", "房山", "石景山"}

def line_score(rec):
    s = rec.get("score_2025_tongzhao")
    if isinstance(s, (int, float)):
        return s, "official"
    s = rec.get("score_ref")
    if isinstance(s, (int, float)):
        return s, "网传单源"
    return None, None

def discount(rec):
    d = 0.08
    d += min(0.12, (rec.get("quota_chaoyang") or 0) * 0.005)
    dist = rec.get("district")
    d += 0.08 if dist in FARQ else (0.04 if dist in NEARQ else 0.0)
    return round(min(d, 0.30), 3)

def main():
    p = os.path.join(KB, "2025_sjtongchou_chaoyang.json")
    data = json.load(open(p))
    done = []
    for tier_key, tier in (("tongchou_yi", "统筹一"), ("tongchou_er", "统筹二")):
        for rec in data.get(tier_key, []):
            ls, lconf = line_score(rec)
            disc = discount(rec)
            if ls is not None:                                  # 有统招线 → 分数锚定(主路径)
                equiv = cy_rank(ls)
                conf = f"估·{'官方' if lconf=='official' else '网传'}线分→朝阳一分一段"
                basis_pre = f"线{ls}分→朝阳考此分位次{equiv}"
            else:                                               # 无统招线 → 名校本部锚定/控制线兜底
                tag = (rec.get("name") or "") + (rec.get("campus") or "")
                anc = next((a for a in ANCHOR if a[0] in tag), None)
                if anc:
                    equiv = round(cy_rank(anc[1]) * anc[2])
                    conf = "估·锚定(名校本部×折让·非线·务必核实)"
                    basis_pre = anc[3]
                else:
                    equiv = CONTROL_FLOOR
                    conf = "估·控制线锚定占位(信息少·务必核实)"
                    basis_pre = f"无本部可锚·郊区保底→贴控制线{CONTROL_LINE}(朝阳≈{CONTROL_FLOOR})"
            D = round(equiv * SHENGYUAN)                                 # 学校档次(2026朝阳位次)
            floor = round(CONTROL_FLOOR * SHENGYUAN)                     # 控制线对应2026朝阳位次≈4194
            E = min(round(D * (1 + disc)), floor)                        # 统筹门槛(录取位次):定向比档次松,但不低于控制线
            below = D > E                                                # 校档次弱于门槛(线<控制线460)→ 走统筹"不值"
            # pred_2026 = 录取门槛(与区内校 pred 同义:能否被录取的位次)
            rec["pred_2026_cy"] = {"rank": E, "lo": round(E * 0.85), "hi": round(E * 1.15),
                                   "pct": round(E / N_CY_2026 * 100, 1)}
            rec["cy_equiv"] = D                                          # 学校档次(判物有所值)
            rec["tongchou_entry_cy"] = {"rank": E, "pct": round(E / N_CY_2026 * 100, 1)}
            rec["below_control"] = below
            rec["discount_pct"] = disc
            rec["pred_conf"] = conf
            rec["pred_basis"] = (f"{basis_pre}→×生源{SHENGYUAN:.3f}=档次{D};统筹门槛×(1+折让{disc})不低于控制线={E}"
                                 + ("。⚠校档次低于控制线460,朝阳走统筹需≈460反不如统招,通常不值" if below else ""))
            done.append((E, rec["name"] + (("·" + rec["campus"]) if rec.get("campus") and rec["campus"] != "本部" else ""),
                         tier, ls, D, E, below, conf))
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    done.sort()
    print(f"{'门槛':>5} {'档次':>5} {'线分':>5}  值?  学校")
    print("-" * 60)
    for E, nm, t, ls, D, e2, below, conf in done:
        print(f"{E:>5} {D:>5} {str(ls):>5}  {'⚠不值' if below else '  ✓'}  统筹{t} {nm[:22]}")
    print(f"\n已算 {len(done)} 校 / 控制线≈{CONTROL_FLOOR}(2025) / 不值(档次<门槛) {sum(1 for x in done if x[6])} 校")

if __name__ == "__main__":
    main()
