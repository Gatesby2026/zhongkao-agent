"""LLM 分析：单题错因 + 整卷综合诊断。

固化 prompt，避免每次手写。
"""
from __future__ import annotations
import re
from . import llm
from .schemas import Question, AnswerKeyItem, StudentAnswer, QuestionScore


# ============ 单题错因分析 ============

PER_QUESTION_SYSTEM = """你是一位资深初三任课老师，正在为家长准备孩子的学情分析。
任务：分析一道学生失分的题目，输出标准结构。

风格要求：
- 客观、专业、聚焦根因
- 不打击学生（避免"差""不会"等词），多用"漏掉""未注意""可加强"等
- 不写鸡汤、不空话
- 中文输出"""

PER_QUESTION_USER_TEMPLATE = """请分析下面这道学生失分的题目：

## 题目信息
- 题号：{qid}
- 题型：{qtype}（满分 {full_score} 分）
- 题干（含选项/原图描述）：
{stem}

## 标准答案
{correct}

## 学生作答
{student}

## 学生失分
扣 {lost} 分（得分 {scored}/{full_score}）

## 输出格式（JSON）

```json
{{
  "knowledgePoint": "涉及主要知识点（不超 20 字）",
  "errorType": "错误类型，从以下精确选一：概念错|计算错|审题漏|表述不规范|读图错|漏选|其他",
  "rootCause": "为什么错（80-150 字，要具体到选项/步骤/字眼）",
  "comparisonTable": [
    {{"item": "A", "studentJudgment": "排除/选", "correctJudgment": "对/错", "reason": "短句解释，可省略"}}
  ],
  "keyInsight": "这道题真正考的核心是什么（50-100 字）",
  "improvement": "具体提分动作（80-150 字，可执行的训练动作，避免空话）"
}}
```

注意：
- 仅选择题需输出 comparisonTable，填空/计算题 comparisonTable 留空数组
- rootCause 要点明扣分根因，不是题目难度
- 保留 LaTeX 公式
- 不要 markdown 代码块包裹 JSON"""


def analyze_question(
    *,
    question: Question,
    answer: AnswerKeyItem,
    student: StudentAnswer,
    score: QuestionScore,
    cache_key: str | None = None,
) -> dict:
    """对单道失分题做 LLM 分析。"""
    # 标准答案文本化
    correct = answer.get("correctSolution") or answer.get("correct")
    if isinstance(correct, list):
        correct_str = "、".join(correct) if not isinstance(correct[0], str) or len(correct[0]) > 1 else "".join(correct)
    else:
        correct_str = str(correct)

    # 学生答案文本化
    filled = student.get("filled")
    if filled is None:
        student_str = student.get("rawText", "（未作答）")
    elif isinstance(filled, list):
        student_str = "".join(filled)
    else:
        student_str = str(filled)

    # 题干（含选项渲染）
    stem = question.get("stem", "")
    options = question.get("options")
    if options:
        opts = "\n".join(f"- {o['label']}. {o['text']}" for o in options)
        stem = f"{stem}\n\n{opts}"

    user = PER_QUESTION_USER_TEMPLATE.format(
        qid=question["id"],
        qtype=question.get("type", "?"),
        full_score=score.get("fullScore", question.get("score", "?")),
        stem=stem,
        correct=correct_str,
        student=student_str,
        lost=int(score["fullScore"] - score["scored"]),
        scored=score["scored"],
    )

    result = llm.chat_json(
        system=PER_QUESTION_SYSTEM,
        user=user,
        cache_key=cache_key,
    )
    return _normalize_per_question(result, correct, question.get("type"))


def _normalize_per_question(result: dict, correct, qtype: str | None) -> dict:
    """修正 LLM 常见漂移：
    - 单选题：comparisonTable 中只有 correct 才是「对」，其他都是「错」（LLM 时会错判）
    - 多选题：correct 列表里的选项是「对」，其余是「错」
    """
    table = result.get("comparisonTable") or []
    if qtype == "choice" and isinstance(correct, str) and table:
        for row in table:
            label = row.get("item", "").strip()
            row["correctJudgment"] = "对" if label == correct else "错"
    elif qtype == "multi_choice" and isinstance(correct, list) and table:
        correct_set = set(correct)
        for row in table:
            label = row.get("item", "").strip()
            row["correctJudgment"] = "对" if label in correct_set else "错"
    result["comparisonTable"] = table
    return result


# ============ 整卷综合诊断 ============

OVERALL_SYSTEM = """你是一位资深班主任，正在为家长撰写本次考试的整体学情诊断。
基于已有的每题错因分析，提炼出共性、优先级和可执行计划。

风格：客观、温和、聚焦行动。中文输出。"""

OVERALL_USER_TEMPLATE = """## 考试基本信息

{exam_summary}

## 学生失分概况

{lost_summary}

## 每题错因卡（已分析）

{per_question_summary}

---

请输出 JSON：

```json
{{
  "overallVerdict": "整体定位（30-50 字，例如'高分段，基础扎实，主要失分集中在 XX'）",
  "lostMainCauses": [
    {{"cause": "失分主因 1（10 字内）", "lostPoints": 4, "involvedQuestions": ["Q12","Q25"]}}
  ],
  "improvementPriorities": [
    {{
      "priority": 1,
      "topic": "电学综合（10 字内）",
      "expectedGain": "3-4 分",
      "rationale": "为什么是优先级 1（50-100 字）",
      "actions": ["每天 1 道 XX 类题", "..."]
    }}
  ],
  "prepPlan4Weeks": [
    {{"week": 1, "focus": "XX 与 XX", "quantifiedTarget": "10 道 XX + 1 张模板"}},
    {{"week": 2, "focus": "..."}}
  ],
  "secondMockTarget": "65 / 70（提 5 分）",
  "positives": [
    "本次考试值得肯定的 3-4 条（鼓励学生）"
  ]
}}
```

注意：
- improvementPriorities 按 ROI（投入产出比）排序，给 2-4 条
- prepPlan4Weeks 给 4 周
- positives 是给学生信心的"肯定面"，要具体引用本次表现，不要空话
- 不要 markdown 代码块包裹 JSON"""


def analyze_overall(
    *,
    exam_summary: str,
    lost_summary: str,
    per_question_summary: str,
    cache_key: str | None = None,
) -> dict:
    user = OVERALL_USER_TEMPLATE.format(
        exam_summary=exam_summary,
        lost_summary=lost_summary,
        per_question_summary=per_question_summary,
    )
    result = llm.chat_json(
        system=OVERALL_SYSTEM,
        user=user,
        cache_key=cache_key,
        max_tokens=4096,
    )
    return _normalize_overall(result)


def _split_csv(value) -> list[str]:
    """把"Q12, Q25"或["Q12,Q25"]或["Q12","Q25"]统一为 list[str]。"""
    if isinstance(value, list):
        if len(value) == 1 and isinstance(value[0], str) and ("," in value[0] or "，" in value[0] or "、" in value[0]):
            return _split_csv(value[0])
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        parts = value.replace("，", ",").replace("、", ",").split(",")
        return [p.strip() for p in parts if p.strip()]
    return []


def _normalize_overall(result: dict) -> dict:
    """修正 LLM 不严格遵循 JSON 格式的常见漂移。"""
    # lostMainCauses[].involvedQuestions 必须是 list
    for c in result.get("lostMainCauses", []):
        c["involvedQuestions"] = _split_csv(c.get("involvedQuestions"))

    # improvementPriorities[].actions 必须是 list
    for p in result.get("improvementPriorities", []):
        actions = p.get("actions")
        if isinstance(actions, str):
            # 按句号/换行/分号切分
            parts = re.split(r"[；;。\n]+", actions)
            p["actions"] = [a.strip() for a in parts if a.strip()]
        elif not isinstance(actions, list):
            p["actions"] = []

    # positives 必须是 list
    pos = result.get("positives")
    if isinstance(pos, str):
        result["positives"] = _split_csv(pos) or [pos]
    return result
