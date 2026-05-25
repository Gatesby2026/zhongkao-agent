"""无小分表时的自动判分 → scores.json。

设计：小分表可选。家长没传时系统自动判：
  - 选择题/判断：answer-card OCR 涂卡 vs KB 标准答案 → 确定性判分
  - 主观题：直接复用 answer-card.json 里 Phase C（qwen-vl-max 看图阅卷，
    技能「方案 B」）已产出的 grade.suggestedScore —— 不再单独二次判分

为什么不再二次判分：scores.json 与报告引用的 grade 必须同源，
否则会出现「scores 说扣 1 分、grade.missedPoints 为空」的系统性矛盾
（skill_student_learning_report P0 红线 #1：一处矛盾 → 整份报告信任归零）。

老师小分（若有）才是权威；自动判分仅在无小分时兜底，结果标注 auto。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SR_DIR = ROOT / "scripts" / "answer-card-ocr"

CHOICE_TYPES = {"单选", "多选", "选择", "判断", "choice", "multi_choice"}
_ESSAY_KEYWORDS = ("作文", "essay", "composition", "写作")


def _is_essay(qtype: str) -> bool:
    if not qtype:
        return False
    low = qtype.lower()
    return any(k in low or k in qtype for k in _ESSAY_KEYWORDS)


def _norm(s) -> str:
    if isinstance(s, list):
        s = "".join(str(x) for x in s)
    return re.sub(r"[\s，,、；;]+", "", str(s or "")).upper()


def _load_yaml_questions(yaml_path: Path) -> list[dict]:
    d = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return d.get("questions", [])


def _qnum(qid) -> int:
    m = re.search(r"\d+", str(qid))
    return int(m.group(0)) if m else 0


def auto_grade(student_dir: Path, yaml_path: Path) -> dict:
    """→ scores.json dict（含 _auto 标记 + 逐题 _reason）。

    选择题：涂卡 vs KB 标答确定性判分。
    主观题：直接取 answer-card.json 里 Phase C 已写入的 grade.suggestedScore
            （与报告错因引用的 grade.missedPoints 同源，保证不矛盾）。
    """
    ac = json.loads((student_dir / "answer-card.json").read_text(encoding="utf-8"))
    ac_by_num = {_qnum(a.get("qId")): a for a in ac.get("answers", [])}
    qs = _load_yaml_questions(yaml_path)

    questions = []
    total = 0.0
    full_total = 0.0
    for q in qs:
        num = _qnum(q["id"])
        full = float(q.get("score", 0))
        full_total += full
        qtype = q.get("type", "")
        a = ac_by_num.get(num, {})
        if qtype in CHOICE_TYPES:
            std = _norm(q.get("answer", ""))
            stu = _norm(a.get("filled", ""))
            scored = full if (std and stu and std == stu) else 0.0
            reason = f"涂卡={stu or '空'} 标答={std} → {'对' if scored else '错'}"
            review = not stu
        else:
            # 复用 Phase C（detect_card 看图阅卷）已产出的 grade
            g = a.get("grade") or {}
            sc = g.get("suggestedScore")
            try:
                sc_f = float(sc)
                sc_valid = 0 <= sc_f <= full
            except (TypeError, ValueError):
                sc_valid = False
            if sc_valid:
                scored = sc_f
                reason = g.get("scoreReason", "")
                review = bool(g.get("needsTeacherReview", True))
            elif _is_essay(qtype):
                # 作文兜底口径：能评则评，不能评按满分占位（不蒙数也不压低总分）
                scored = full
                reason = (g.get("scoreReason")
                          or "作文 AI 未评分，按满分占位等老师小分校准")
                review = True
            else:
                scored = 0.0
                reason = "Phase C 未产出评分（裁切/看图失败），记 0 待复核"
                review = True
        total += scored
        questions.append({
            "qId": f"Q{num}", "scored": _i(scored), "fullScore": _i(full),
            "_reason": reason, "_needsReview": review,
        })

    return {
        "examTotal": {"scored": _i(total), "fullScore": _i(full_total)},
        "questions": questions,
        "sections": [],
        "_auto_graded": True,
    }


def _i(x):
    return int(x) if float(x).is_integer() else round(float(x), 2)


def write_auto_scores(student_dir: Path, yaml_path: Path) -> dict:
    data = auto_grade(student_dir, yaml_path)
    out = {k: v for k, v in data.items() if not k.startswith("_")}
    # 逐题去掉 _ 前缀的内部字段（build_report 只需 qId/scored/fullScore）
    out["questions"] = [
        {"qId": q["qId"], "scored": q["scored"], "fullScore": q["fullScore"]}
        for q in data["questions"]
    ]
    (student_dir / "scores.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
