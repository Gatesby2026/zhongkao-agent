#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""志愿草表 · 大模型顾问(P1 MVP)。

设计见 docs/design/ZHIYUAN-LLM-ADVISOR-DESIGN.md。
- LLM 改良规则稿:输入 = 规则引擎产出(build_result)+ 候选校结构化数据 + 孩子画像。
- LLM 只对喂入数据做判断/表达,绝不发明学校/代码/线;缺数据说"待核"。
- provider 可切:LLM_PROVIDER=deepseek|qwen(P1 先用国内模型;Anthropic 通路就绪再加 anthropic)。
- 输出 = 六段分析报告(markdown);后置轻量校验(提到的校须在候选集内)。

CLI:
  DEEPSEEK_API_KEY=... python llm_report.py --rank 4500 --home "朝阳区紫玉山庄" \
      --chuzhong "北京市朝阳外国语学校" --provider deepseek
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recommend  # noqa: E402

# ── provider 抽象 ──────────────────────────────────────────────
PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/chat/completions", "deepseek-chat", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-max", "DASHSCOPE_API_KEY"),
    # "anthropic": 待通路就绪接入(见设计文档 §7.1)
}


def call_llm(provider: str, system: str, user: str, timeout: int = 180) -> str:
    if provider not in PROVIDERS:
        raise ValueError(f"未知 provider: {provider};可选 {list(PROVIDERS)}")
    url, model, keyenv = PROVIDERS[provider]
    key = os.environ.get(keyenv)
    if not key:
        raise RuntimeError(f"缺 {keyenv}(provider={provider})")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.3,
        "max_tokens": 4096,   # 六段报告需足够长度,默认上限会截断
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"]


# ── 上下文装配:把规则稿压成 LLM 喂得动的精简结构 ────────────────
def _card_brief(c: dict) -> dict:
    """单校提炼喂 LLM 的关键事实(全来自 KB,不编造)。"""
    p = c.get("pred_2026") or {}
    n = c.get("nearest") or {}
    g = c.get("gaokao")
    feat = c.get("features") or {}
    return {
        "校名": recommend.cleanName(c["name"]) if hasattr(recommend, "cleanName") else c["name"],
        "档位": c.get("band"),
        "2026预估录取位次": p.get("rank") or c.get("ref_rank"),
        "近年录取位次": c.get("ref_rank"),
        "层次": c.get("level") or "",
        "高考出口": (g if isinstance(g, str) else "") or "",
        "通勤km": n.get("km"),
        "可住宿": bool(c.get("boarding")),
        "特色": feat.get("style") or c.get("style") or "",
        "学校代码": c.get("school_code") or "",
    }


def build_context(result: dict, profile: dict) -> dict:
    """从 build_result + 画像装配 LLM 上下文(精简、只留判断需要的事实)。"""
    bands = result.get("bands", {})
    SLOTS = recommend.ZHIYUAN_SLOTS if hasattr(recommend, "ZHIYUAN_SLOTS") else 12

    def _sorted(band):
        return sorted(bands.get(band, []), key=lambda c: (c.get("ref_rank") or 9_999_999))

    # 规则版已选的 12 个统招志愿(梯度):冲全要 → 稳全要 → 保填满至 11 + 末位 1 所最稳铁保底。
    # 这就是"规则稿",喂给 LLM 去改良(改顺序/替换并解释),而不是让它从全池里自己挑(易超 12)。
    chong, wen, bao = _sorted("冲"), _sorted("稳"), _sorted("保")
    picked = (chong + wen)[:SLOTS]
    if len(picked) < SLOTS and bao:
        room = SLOTS - len(picked)
        picked += bao[:max(0, room - 1)]           # 最强的几所保
        if bao and picked[-1] is not bao[-1]:
            picked.append(bao[-1])                   # 末位 = 最稳铁保底(ref_rank 最大)
    picked = picked[:SLOTS]
    rule_draft = []
    for c in picked:
        c = dict(c); rule_draft.append(_card_brief(c))

    # 完整候选池(供 LLM 调整时替换用),含够不上最接近的几所(冲刺参考)
    cand = []
    for band in ("冲", "稳", "保"):
        for c in _sorted(band):
            c = dict(c); c["band"] = band; cand.append(_card_brief(c))
    for c in (_sorted("够不上"))[:6]:
        c = dict(c); c["band"] = "够不上"; cand.append(_card_brief(c))

    # 校额到校:从整表抽出"本初中"那一行(逐高中名额),喂精——这是中低位次最值钱的杠杆
    chuzhong = (profile.get("chuzhong") or "").strip()
    xeddx_full = result.get("xeddx") or {}
    xeddx_mine = None
    rows = xeddx_full.get("rows") or []
    if chuzhong and rows:
        row = (next((r for r in rows if r.get("name") == chuzhong), None)
               or next((r for r in rows if chuzhong and (chuzhong in r.get("name", "")
                                                         or r.get("name", "") in chuzhong)), None))
        if row:
            xeddx_mine = {
                "本初中": row.get("name"), "校额总名额": row.get("total"),
                "各优质高中名额": {k: v for k, v in (row.get("by_school") or {}).items() if v},
                "门槛": "中考总分≥430/510 + 综合素质B + 同一初中连续三年学籍;按校内排名+志愿录取;往届/回京不可报。2026计划发布后须刷新。",
            }
    tongchou = result.get("tongchou") or {}

    # 民办/国际(统招批内填报)+ 中职/职教(可办普高学籍·中低位次保底)——压成精简清单
    def _priv(p):
        return {"校名": p.get("name"), "性质": p.get("nature"), "方向": p.get("direction"),
                "学费": p.get("tuition"), "2025线": p.get("score_2025"),
                "可住宿": p.get("boarding"), "出口": p.get("study_abroad") or p.get("exit_type") or ""}

    def _voc(v):
        return {"校名": v.get("name"), "类型": v.get("type"),
                "专业": (v.get("specialties") or [])[:4],
                "综合高中班线2025": v.get("comp_high_2025"),
                "升学路径": v.get("exit_paths") or v.get("comp_high_note") or "",
                "五年制": v.get("five_year"), "可住宿": v.get("boarding")}

    pv = result.get("private_schools") or {}
    vc = result.get("vocational") or {}
    priv_items = (pv.get("schools") if isinstance(pv, dict) else pv) or []
    voc_items = (vc.get("schools") if isinstance(vc, dict) else vc) or []

    return {
        "统招志愿上限": SLOTS,
        "规则版统招草表(已选好的12志愿·你在此基础上改良)": rule_draft,
        "学生": {
            "区": result.get("district"),
            "中考区排名": result.get("rank"),
            "估分": result.get("est_score"),
            "身份": result.get("identity"),
            "通勤方式": result.get("mode_label"),
            "通勤上限km": result.get("max_km"),
            "接受住宿": result.get("boarding"),
            "初中": profile.get("chuzhong") or "",
        },
        "孩子画像": profile,
        "可报资格": result.get("eligibility"),
        "统招候选池(供你替换/调整用·非最终名单)": cand,
        "校额到校(本初中逐高中名额·指标分配批)": xeddx_mine or "本初中未匹配到校额名额表(待核)",
        "市级统筹(指标分配批)": tongchou,
        "民办_国际(统招批内填报·留京高考或出国)": [_priv(p) for p in priv_items[:15]],
        "中职_职教(可办普高学籍可高考·中低位次保底)": [_voc(v) for v in voc_items[:6]],
        "数据说明": result.get("admission_source"),
    }


SYSTEM_PROMPT = """你是北京中考志愿填报的资深规划师(朝阳区,京籍应届为主)。
你拿到的是"规则引擎已生成的草表 + 候选学校的结构化数据 + 这个孩子的画像"。

【铁律】
1. 你只能使用我提供的数字与事实(录取线/位次/距离/名额/高考出口)。绝不发明任何学校、代码、分数线、位次或名额。缺数据就明确说"待核",不要猜。
2. 你可以调整规则稿的排序/取舍,但每次调整必须给出基于所给数据 + 孩子画像的理由。
3. 录取规则要遵守:三批次顺序录取、被前一批次录取即锁定;②指标分配(校额到校/市级统筹)只填"③统招够不上、但够一够"的目标(填统招本可达的会把自己锁低);③统招是平行志愿(分数优先、遵循志愿),冲在前零成本、末位必有铁保底。
4. **你的统招任务 = 改良"规则版统招草表(12志愿)":在那12个基础上调整顺序、必要时用"候选池"里的学校替换,并解释每处改动。最终仍是 ≤12 个,绝不把候选池全列出来。**
5. **中低位次(估分低、统招多为"够不上")务必把民办/中职综合高中班/贯通纳入保底**;校额到校门槛是估分需达普高线(≥430/510),若孩子估分低于门槛要明确提示校额可能不可用。
6. 面向家长,讲人话,讲清楚"为什么",而不是只列学校。

【用好"孩子画像"】画像里给了什么就用什么,没给的别假设:
- 文理倾向/强科/弱科 → 优先匹配对应见长的学校(如偏理强物理→理科见长校),弱科明显→提示该校是否补弱。
- 发挥稳定性"起伏较大" → 保底加厚、慎冲;"稳定" → 可适当多冲。
- 学习自驱"需要盯" → 倾向管理严格校;"自驱强" → 自由氛围也可。
- 适应环境"偏好节奏平稳" → 慎填竞争最激烈的顶校,即便分够;"能扛高竞争" → 可冲到顶。
- 特长(体育/艺术/科技竞赛) → 关联特长招生/特色班/特色校(若数据里有)。
- 家庭最看重(≤2项) → 作为"三、关键权衡"的排序加权依据,明确说明你按这些权重取舍。
- 中考目标/学费预算 → 校准冲稳保力度;预算用于民办/国际取舍。

【输出格式】markdown,严格六段,标题用 ##:
## 一、个性化总判
(一段话:整体该冲还是该稳、最大机会点、最大风险点——结合该孩子的位次/住址/画像)
## 二、逐志愿建议与对规则版的调整
(给出统招志愿的推荐顺序;指出哪几处相对规则版做了调换及理由)
## 三、关键权衡
(通勤vs层次 / 住宿换更好校 / 强弱科与特色班匹配 / 大小年波动等,结合画像)
## 四、情形预演
(超常发挥位次提升X→怎么调;失常→保底够不够)
## 五、跨批次组合策略
(校额到校 / 市级统筹 如何与统招配合;结合该孩子初中的名额)
## 六、行动清单与待核
(要打电话核的校区、要查的简章、低可信数据提示)
"""


def generate_report(rank, home=None, mode="bicycling", max_km=8, boarding=True,
                    identity="jjyj", profile=None, district="chaoyang",
                    provider="deepseek"):
    """生成大模型志愿分析报告。返回 {report, context, candidates, provider}。"""
    profile = profile or {}
    result = recommend.build_result(
        rank=rank, home=home, mode=mode, max_km=max_km,
        interests=profile.get("interests"), district=district,
        boarding=boarding, identity=identity)
    ctx = build_context(result, profile)
    user_msg = ("以下是这个孩子的情况、规则版草表与候选校数据(JSON)。"
                "请据此产出六段分析报告。\n\n```json\n"
                + json.dumps(ctx, ensure_ascii=False) + "\n```")
    report = call_llm(provider, SYSTEM_PROMPT, user_msg)
    return {"report": report, "context": ctx, "provider": provider}


def validate(report: str, context_blob: str) -> list:
    """轻量后置校验(防幻觉):报告里**加粗**的、像校名的词,若在喂入上下文里找不到
    → 疑似编造,标出供人工核实(不阻断)。模型会把推荐校名加粗,加粗 token 干净、不含散文串。
    context_blob = 喂给 LLM 的上下文 JSON(含统招/统筹/校额所有校名)。
    注:这是 MVP 兜底;正式版应让 LLM 输出带 school_code 的结构化志愿,按代码核验(设计 §8)。"""
    warns = []
    for tok in set(re.findall(r"\*\*([^*]+?)\*\*", report)):
        tok = tok.strip("：: 　")
        if not re.search(r"(中学|学校|附中|一中|分校|附属实验)$", tok):
            continue
        base = tok.split("（")[0].split("·")[0]
        if base and base not in context_blob and tok not in context_blob:
            warns.append(tok)
    return sorted(set(warns))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, required=True)
    ap.add_argument("--home", default="")
    ap.add_argument("--chuzhong", default="")
    ap.add_argument("--max-km", type=float, default=8)
    ap.add_argument("--boarding", action="store_true", default=True)
    ap.add_argument("--provider", default=os.environ.get("LLM_PROVIDER", "deepseek"))
    ap.add_argument("--profile", default="", help="JSON 画像;留空用内置样例")
    args = ap.parse_args()

    if args.profile:
        profile = json.loads(args.profile)
    else:  # 样例画像(贾小淇风格)
        profile = {
            "chuzhong": args.chuzhong or "北京市朝阳外国语学校",
            "文理倾向": "偏理", "强科": ["数学", "物理"], "弱科": ["英语"],
            "发挥稳定性": "稳定", "学习自驱": "一般",
            "适应环境": "能扛高竞争强校", "特长": [],
            "家庭最看重": ["升学率", "通勤距离"], "学费预算上限": None,
        }
    out = generate_report(rank=args.rank, home=args.home or None,
                          max_km=args.max_km, boarding=args.boarding,
                          profile=profile, provider=args.provider)
    print(out["report"])
    warns = validate(out["report"], json.dumps(out["context"], ensure_ascii=False))
    if warns:
        print("\n\n⚠️ 后置校验:报告提到但不在候选集的疑似校名(需人工核实是否编造):", warns,
              file=sys.stderr)


if __name__ == "__main__":
    main()
