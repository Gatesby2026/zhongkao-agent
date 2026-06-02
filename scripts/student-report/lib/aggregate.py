"""程序层聚合（零 LLM）：模块掌握度 / 难度维度 / 知识点失分 / 大题得分率。

所有数字都是从 join 后的 QView 直接算出的事实，作为报告"总览/诊断"两节的硬数据，
也作为 LLM 分析的事实输入（约束 LLM 不要编造）。
"""
from __future__ import annotations

from collections import defaultdict

from .schemas import ExamView, QView


def module_mastery(exam: ExamView) -> list[dict]:
    """各模块得分率。返回按得分率升序（最弱在前）。

    [{"module_cn","scored","full","rate","lost_qs":[Q..]}]
    """
    agg: dict[str, dict] = defaultdict(
        lambda: {"scored": 0.0, "full": 0, "lost_qs": []})
    for q in exam.questions:
        m = q.module_cn
        agg[m]["scored"] += q.scored
        agg[m]["full"] += q.score
        if q.is_lost:
            agg[m]["lost_qs"].append(q.qid)
    out = []
    for m, d in agg.items():
        rate = d["scored"] / d["full"] if d["full"] else 0
        out.append({
            "module_cn": m,
            "scored": round(d["scored"], 1),
            "full": d["full"],
            "rate": round(rate, 3),
            "lost_qs": d["lost_qs"],
        })
    out.sort(key=lambda x: x["rate"])
    return out


def module_roi(exam: ExamView) -> list[dict]:
    """提分边际：按模块失分降序——失分多的模块就是提分性价比最高的。

    [{"module_cn","lost","scored","full","rate","n_questions","lost_qs"}]
    供 analyze.analyze_overall 作为硬数字事实输入，让 actionPlan 引用
    "补 X 模块预估可挽回 Y 分"而不是空话。
    """
    agg: dict[str, dict] = defaultdict(
        lambda: {"scored": 0.0, "full": 0, "lost": 0.0, "n": 0, "lost_qs": []})
    for q in exam.questions:
        m = q.module_cn
        agg[m]["scored"] += q.scored
        agg[m]["full"] += q.score
        agg[m]["lost"] += q.lost
        agg[m]["n"] += 1
        if q.is_lost:
            agg[m]["lost_qs"].append(q.qid)
    out = []
    for m, d in agg.items():
        rate = d["scored"] / d["full"] if d["full"] else 0
        out.append({
            "module_cn": m,
            "lost": round(d["lost"], 1),
            "scored": round(d["scored"], 1),
            "full": d["full"],
            "rate": round(rate, 3),
            "n_questions": d["n"],
            "lost_qs": d["lost_qs"],
        })
    out.sort(key=lambda x: -x["lost"])
    return out


def difficulty_breakdown(exam: ExamView) -> list[dict]:
    """难度维度：基础/中等/能力 各档得分率。基础题失分最该优先补。"""
    order = {"基础": 0, "中等": 1, "能力": 2}
    agg: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "scored": 0.0, "full": 0, "lost_qs": []})
    for q in exam.questions:
        d = q.difficulty or "未标注"
        agg[d]["n"] += 1
        agg[d]["scored"] += q.scored
        agg[d]["full"] += q.score
        if q.is_lost:
            agg[d]["lost_qs"].append(q.qid)
    out = []
    for d, v in agg.items():
        rate = v["scored"] / v["full"] if v["full"] else 0
        out.append({
            "difficulty": d, "n": v["n"],
            "scored": round(v["scored"], 1), "full": v["full"],
            "rate": round(rate, 3), "lost_qs": v["lost_qs"],
        })
    out.sort(key=lambda x: order.get(x["difficulty"], 9))
    return out


def section_breakdown(exam: ExamView) -> list[dict]:
    """大题维度。**优先用 scores.json 的 sections**（人工填，准确）。
    auto 模式无 sections 时 fallback 按 type_cn 聚合所有题（保证表非空）。
    """
    seen_order: list[str] = []
    agg: dict[str, dict] = defaultdict(lambda: {"scored": 0.0, "full": 0})
    for s in exam.raw_sections:
        name = s.get("section", "").strip()
        if not name:
            continue
        if name not in seen_order:
            seen_order.append(name)
        agg[name]["scored"] += s.get("scored", 0)
        agg[name]["full"] += s.get("fullScore", 0)

    # Fallback：raw_sections 空 → 按「大题」聚合（subject 专属中文分法，
    # 英语阅读还会分 A/B 篇与 C/D 篇）
    if not seen_order:
        from . import subject_profile
        for q in exam.questions:
            name = subject_profile.section_name(exam.subject, q)
            if name not in seen_order:
                seen_order.append(name)
            agg[name]["scored"] += q.scored
            agg[name]["full"] += q.score

    out = []
    for name in seen_order:
        v = agg[name]
        out.append({
            "type_cn": name,
            "scored": round(v["scored"], 1),
            "full": v["full"],
            "rate": round(v["scored"] / v["full"], 3) if v["full"] else 0,
        })
    return out


def lost_knowledge_points(exam: ExamView) -> list[dict]:
    """失分知识点清单。一个知识点可能跨多题。按累计失分降序。

    [{"kp","lost_total","qs":[Q..]}]
    """
    agg: dict[str, dict] = defaultdict(lambda: {"lost": 0.0, "qs": []})
    for q in exam.questions:
        if not q.is_lost:
            continue
        for kp in q.knowledge_points:
            agg[kp]["lost"] += q.lost
            agg[kp]["qs"].append(q.qid)
    out = [{"kp": k, "lost_total": round(v["lost"], 1), "qs": v["qs"]}
           for k, v in agg.items()]
    out.sort(key=lambda x: -x["lost_total"])
    return out


def lost_questions(exam: ExamView) -> list[QView]:
    """所有失分题（含部分失分），按题号升序——与试卷顺序一致便于核对。"""
    return sorted([q for q in exam.questions if q.is_lost],
                  key=lambda q: q.num)


def overall_stats(exam: ExamView) -> dict:
    """总览数字。"""
    qs = exam.questions
    choice = [q for q in qs if q.is_choice]
    subj = [q for q in qs if not q.is_choice]
    return {
        "total_scored": round(exam.total_scored, 1),
        "full_score": exam.full_score,
        "rate": round(exam.total_scored / exam.full_score, 3)
                if exam.full_score else 0,
        "n_questions": len(qs),
        "n_lost": sum(1 for q in qs if q.is_lost),
        "choice_scored": round(sum(q.scored for q in choice), 1),
        "choice_full": sum(q.score for q in choice),
        "subj_scored": round(sum(q.scored for q in subj), 1),
        "subj_full": sum(q.score for q in subj),
        "lost_total": round(sum(q.lost for q in qs), 1),
    }
