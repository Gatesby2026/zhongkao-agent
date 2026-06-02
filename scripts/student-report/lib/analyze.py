"""LLM 分析：单题归因 + 整卷综合。**学生向**语气。

核心约束：失分原因必须基于事实——
  - 选择题：学生选项 vs 标准答案（确定性，程序已知）
  - 主观题：answer-card.json 的 grade.missedPoints / scoreReason（看图评分的事实）
LLM 只做"归纳 + 给可执行训练动作"，不允许编造学生没犯的错。
"""
from __future__ import annotations

import re

from . import llm
from .schemas import QView


# ─── 单题归因（学生向）──────────────────────────────────────────────────────

PER_Q_SYSTEM = """你是学生的中考学科私教，正在帮 TA 复盘一道做错的题。
直接对学生说话（用"你"），让学生看完就知道"我为什么错、下一步怎么做"。

风格：
- 直接、具体、不绕弯；像学长面对面讲题
- 不打击（不用"差/不会"），但也不灌鸡汤——只讲干货
- 失分原因必须基于给定事实，**不要编造学生没写的内容或没犯的错**
- 中文输出

**严禁通用空话**（whyWrong/solveCorrectly/keyInsight 都不能出现）：
"仔细审题"、"注意单位"、"规范术语"、"逐一核对"、"加强练习"、
"可能是时间管理不当"、"审题漏条件"（孤立写而不点哪个条件）、
"表述不够准确"（不指出哪里）等放之四海皆准的话。
要写就写具体到这道题：哪个条件、哪一步公式、哪个数值。

**严禁偏题**：solveCorrectly 必须**严格围绕本题给出的知识点**，
不要引入题目未涉及的其它公式/概念（如电学题里写浮力、几何题里写函数）。
若解题需要用到本题以外的预备知识，最多用一句话提一下，不展开推导。"""

PER_Q_USER = """复盘这道失分题，输出 JSON。

# 题目
{qid}（{type_cn}，满分 {score} 分，难度：{difficulty}）
知识点：{kps}

题干：
{stem}

# 标准答案
{std_answer}

# 评分要点 / 解析
{solution}

# 你的作答（事实，勿改写）
{student_answer}

# 失分事实
失 {lost} 分（得 {scored}/{score}）{grade_facts}

# 输出 JSON（不要 markdown 围栏，不要编造事实）
{{
  "knowledgePoint": "精确到「考法」级别，如「电学综合压轴」「滑轮组机械效率」「平面镜成像探究」——不要只写「电学」「力学」这种大类（≤16 字）",
  "errorType": "精确选一：概念不清|计算失误|审题漏条件|表述不规范|读图错|步骤跳跃|漏选/多选|未作答|其它",
  "comparisonTable": [
    {{"option": "A", "student": "选/排除", "correct": "对/错", "reason": "一句话点明这个选项为什么对/错（≤30 字）"}}
  ],
  "whyWrong": ["揭示你**为什么会掉进这个坑**（思维误区/认知断点），不是复述答案。每点必须点到本题的具体条件/概念，1 句话 2-3 点，禁通用空话"],
  "solveCorrectly": ["**正确该怎么做**——核心字段。3-5 步，必须用本题数据/条件代入；公式只用本题知识点（{kps}）相关的，不要跑题。LaTeX 公式用 $...$ 行内，自包含闭合（成对出现 $）"],
  "keyInsight": ["**这道题特有的**避坑点，1-2 条。禁止通用空话——必须是本题这个具体考点（{kps}）独有的提醒"]
}}

注意：
- comparisonTable 仅选择题输出（逐 A/B/C/D 一行）；非选择题给空数组 []
- **solveCorrectly 是核心**：学生看完这一节要能独立把这道题做对，必须有真正的解题过程，不是"先…再…最后…"的空壳
- 所有数组字段必须是字符串数组，分点
- 严格基于给定事实，学生没写的不要替 TA 补"""


def analyze_question(q: QView, *, cache_key: str | None = None) -> dict:
    """单失分题归因。事实输入：选择题用 filled vs answer；主观题用 grade。"""
    if q.is_choice:
        student_answer = q.student_filled or "（未作答）"
        grade_facts = ""
    else:
        if q.student_handwriting and q.student_handwriting.strip():
            student_answer = q.student_handwriting.strip()
        elif q.region_image:
            # 主观题用答题卡裁图展示作答（不转写文本）——绝不能判成「未作答」
            student_answer = ("（学生已作答；作答内容见答题卡裁切原图，未转写为文本。"
                              "请依据下方阅卷要点判断，errorType 不得选「未作答」）")
        else:
            student_answer = "（未识别到作答）"
        gf = []
        if q.grade:
            g = q.grade
            if g.get("missedPoints"):
                gf.append(f"未答出要点：{'；'.join(g['missedPoints'])}")
            if g.get("matchedPoints"):
                gf.append(f"已答对要点：{'；'.join(g['matchedPoints'])}")
            if g.get("scoreReason"):
                gf.append(f"评分依据：{g['scoreReason']}")
        grade_facts = ("\n看图阅卷事实：\n" + "\n".join(gf)) if gf else ""

    opts_str = ""
    if q.options:
        opts_str = "\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items())

    user = PER_Q_USER.format(
        qid=q.qid, type_cn=q.type_cn, score=q.score,
        difficulty=q.difficulty or "未标注",
        kps="、".join(q.knowledge_points) or "—",
        stem=(q.stem + opts_str)[:1200],
        std_answer=q.std_answer[:600],
        solution=(q.solution or "—")[:800],
        student_answer=student_answer[:600],
        lost=q.lost, scored=q.scored,
        grade_facts=grade_facts[:800],
    )
    r = llm.chat_json(system=PER_Q_SYSTEM, user=user,
                      cache_key=cache_key, temperature=0.2,
                      max_tokens=8192)        # 防 LaTeX 长 fix 被截断（数学 5+ 步证明题）
    return _normalize_per_q(r, q)


def _drop_unclosed_dollars(s: str) -> str:
    """LLM 输出公式被 max_tokens 截断 → 末尾 $ 不成对。

    若整段 $ 数为奇数，从末尾找最后一个 $ 截掉到行末（防 KaTeX 解析炸）。
    保守做法，不改正文。
    """
    if not isinstance(s, str) or s.count("$") % 2 == 0:
        return s
    idx = s.rfind("$")
    return s[:idx].rstrip()


def _normalize_per_q(r: dict, q: QView) -> dict:
    """LLM 输出防御 + 选择题对错判断硬纠正（标答确定，不信 LLM 的 correct 列）。"""
    r["whyWrong"] = [_drop_unclosed_dollars(x) for x in _as_list(r.get("whyWrong"))]
    r["keyInsight"] = [_drop_unclosed_dollars(x) for x in _as_list(r.get("keyInsight"))]
    r["solveCorrectly"] = [_drop_unclosed_dollars(x)
                            for x in _as_list(r.get("solveCorrectly"))]

    table = r.get("comparisonTable") or []
    if q.is_choice and table:
        correct_set = set(q.std_answer)            # "C" / "AD"
        student_set = set(q.student_filled or "")
        for row in table:
            if not isinstance(row, dict):
                continue
            opt = str(row.get("option", "")).strip()
            row["correct"] = "对" if opt in correct_set else "错"
            row["student"] = "选" if opt in student_set else "排除"
    r["comparisonTable"] = [x for x in table if isinstance(x, dict)]
    return r


# ─── 整卷综合（学生向）──────────────────────────────────────────────────────

_OVERALL_SYS = """你是学生的私教，基于本次考试客观数据 + 失分题复盘给总诊断。
直接对学生说话，先肯定亮点稳信心，再点薄弱，最后给可执行计划。中文。"""

# 数据块（两次调用共用）
_DATA_BLOCK = """# 本次考试客观数据
{stats_block}

# 模块掌握度（弱→强）
{module_block}

# 提分 ROI（按失分降序——补谁挽回最多分一目了然）
{roi_block}

# 难度维度
{difficulty_block}

# 失分知识点（按累计失分降序）
{kp_block}

# 每道失分题复盘摘要
{per_q_block}
"""

# 调用 A：诊断（结构浅，不易漂移）
_DIAG_USER = _DATA_BLOCK + """
---
只输出诊断 JSON（不要 markdown 围栏，不要其它字段）：
{{
  "verdict": "一句话定位（30-50 字）",
  "positives": ["你擅长的【题型/能力】+ 为何（如'选择题概念辨析稳，13/15 道一次选对，说明基础概念清晰'）——说题型/能力，不要只复述百分比数字"],
  "weakSpots": [
    {{"area": "薄弱点≤12字", "lostPoints": 4, "qs": "Q12、Q25", "evidence": "依据，引用模块/难度数据"}}
  ]
}}
要求：positives 3-4 条，每条点明【是哪类题型/能力强】+ 建议继续保持的做法，引用本卷真实表现但不止于数字；weakSpots 2-4 条；qs 用「、」分隔的字符串。"""

# 调用 B：行动计划（结构浅，drills 用分号串而非数组——数组对象嵌套是漂移重灾区）
_PLAN_USER = _DATA_BLOCK + """
---
只输出行动计划 JSON（不要 markdown 围栏，不要其它字段）：
{{
  "actionPlan": [
    {{"topic": "方向≤12字", "expectedGain": "3-4分", "why": "为何优先50-80字（基础题失分>中等题）", "drills": "动作1；动作2；动作3（分号分隔，具体到练什么/几道/什么方法）"}}
  ],
  "weekPlan": [
    {{"week": 1, "focus": "≤15字", "target": "量化目标"}}
  ],
  "nextTarget": "下次目标分 + 一句话怎么达成"
}}
**硬性要求**：actionPlan 恰好 3 条按【提分 ROI 块】的失分降序对应——
第 1 条对准失分最多的模块，expectedGain 数字从 ROI 块"可挽回 X 分"直接取
（可保守取 60-80%），why 必须**点名具体模块名 + 引用真实失分数字**而非空话；
weekPlan 恰好 4 条（week 1-4）；drills 是【分号分隔的字符串】不是数组；
所有字段填满不留空。"""


def analyze_overall(*, stats_block: str, module_block: str,
                    difficulty_block: str, kp_block: str,
                    per_q_block: str, roi_block: str = "（无）",
                    cache_key: str | None = None) -> dict:
    """拆两次简单调用（诊断 + 计划），各自结构浅，规避深嵌套 JSON 漂移。

    roi_block：按失分降序的模块 ROI（含"补 X 模块可挽回 Y 分"硬数字），
    用于让 actionPlan 引用具体数字而非空话（P1.2 单科增强）。
    """
    fmt = dict(stats_block=stats_block, module_block=module_block,
               difficulty_block=difficulty_block, kp_block=kp_block,
               per_q_block=per_q_block, roi_block=roi_block)
    diag = llm.chat_json(system=_OVERALL_SYS, user=_DIAG_USER.format(**fmt),
                         cache_key=f"{cache_key}-diag" if cache_key else None,
                         temperature=0.3, max_tokens=2048)
    plan = llm.chat_json(system=_OVERALL_SYS, user=_PLAN_USER.format(**fmt),
                         cache_key=f"{cache_key}-plan" if cache_key else None,
                         temperature=0.3, max_tokens=2048)
    return _normalize_overall({**diag, **plan})


def _as_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [p.strip() for p in re.split(r"[；;。\n]+", v) if p.strip()]
    return []


def _normalize_overall(r: dict) -> dict:
    """LLM 输出漂移防御：list 项可能是 str 而非预期 dict。"""
    r["positives"] = _as_list(r.get("positives"))

    weak = []
    for w in r.get("weakSpots", []) or []:
        if isinstance(w, str):
            w = {"area": w, "lostPoints": "?", "qs": [], "evidence": ""}
        w["qs"] = _as_list(w.get("qs"))
        weak.append(w)
    r["weakSpots"] = weak

    plan = []
    for i, p in enumerate(r.get("actionPlan", []) or [], 1):
        if isinstance(p, str):
            p = {"topic": p, "expectedGain": "?", "why": "", "drills": []}
        if not isinstance(p, dict) or not p.get("topic"):
            continue  # 畸形项（无 topic，如错位的 week*）剔除
        p.setdefault("priority", i)
        # drills：分号分隔字符串 → list（数组对象嵌套是漂移重灾区，故用串）
        d = p.get("drills")
        if isinstance(d, str):
            p["drills"] = [x.strip() for x in re.split(r"[；;]\s*", d) if x.strip()]
        else:
            p["drills"] = _as_list(d)
        plan.append(p)
    for i, p in enumerate(plan, 1):
        p["priority"] = i
    r["actionPlan"] = plan

    wk = []
    for x in r.get("weekPlan", []) or []:
        if isinstance(x, str):
            x = {"week": len(wk) + 1, "focus": x, "target": ""}
        if isinstance(x, dict) and x.get("focus"):
            wk.append(x)
    r["weekPlan"] = wk
    return r
