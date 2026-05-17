"""无小分表时的自动判分 → scores.json。

设计：小分表可选。家长没传时系统自动判：
  - 选择题/判断：answer-card OCR 涂卡 vs KB 标准答案 → 确定性判分
  - 主观题：qwen-vl-max 看答题卡照片 + 题干 + 标答 → 估分（批量一次调用）

老师小分（若有）才是权威；自动判分仅在无小分时兜底，结果标注 auto。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SR_DIR = ROOT / "scripts" / "answer-card-ocr"

CHOICE_TYPES = {"单选", "多选", "选择", "判断", "choice", "multi_choice"}


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


def _grade_subjective_batch(photos: list[Path], subj_qs: list[dict]) -> dict:
    """一次 qwen-vl-max 调用，看全部答题卡照片，给所有主观题估分。"""
    sys.path.insert(0, str(SR_DIR))
    import subjective_grade as sg  # noqa

    client = sg._client()
    import base64
    content = []
    for p in photos[:6]:
        b = base64.b64encode(p.read_bytes()).decode()
        content.append({"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b}"}})

    qlist = "\n".join(
        f"- 题号{_qnum(q['id'])}（{q.get('type','')}，{q.get('score',0)}分）"
        f" 标答：{str(q.get('answer',''))[:200]}"
        f" 解析：{str(q.get('solution',''))[:200]}"
        for q in subj_qs
    )
    prompt = f"""这是学生的中考物理答题卡照片（多页）。请逐题在图中找到该题的学生作答，
对照标准答案评分。**忠实学生原作**：没写就 0 分，写错不美化；评分仅供参考。

需评分的主观题：
{qlist}

严格输出 JSON：
{{"grades":[{{"qnum":16,"suggestedScore":2,"scoreReason":"命中X要点，缺Y","needsTeacherReview":false}}, ...]}}
每题都要有；找不到作答按 0 分并 needsTeacherReview=true。"""
    content.append({"type": "text", "text": prompt})

    resp = client.chat.completions.create(
        model="qwen-vl-max",
        messages=[{"role": "user", "content": content}],
        temperature=0.0, max_tokens=4096,
        response_format={"type": "json_object"}, timeout=180,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {"grades": []}
    out = {}
    for g in data.get("grades", []):
        out[int(g.get("qnum", 0))] = g
    return out


def auto_grade(student_dir: Path, yaml_path: Path) -> dict:
    """→ scores.json dict（含 _auto 标记 + 逐题 _reason）。"""
    ac = json.loads((student_dir / "answer-card.json").read_text(encoding="utf-8"))
    ac_by_num = {_qnum(a.get("qId")): a for a in ac.get("answers", [])}
    qs = _load_yaml_questions(yaml_path)

    subj_qs = [q for q in qs if q.get("type") not in CHOICE_TYPES]
    photos = sorted(
        p for p in (student_dir / "answer-card-photos").iterdir()
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png")
    )
    subj_grades = {}
    if subj_qs and photos:
        try:
            subj_grades = _grade_subjective_batch(photos, subj_qs)
        except Exception as e:
            subj_grades = {}
            print(f"  ⚠️ 主观题自动判分失败，记 0 待复核：{e}", file=sys.stderr)

    questions = []
    total = 0.0
    full_total = 0.0
    for q in qs:
        num = _qnum(q["id"])
        full = float(q.get("score", 0))
        full_total += full
        qtype = q.get("type", "")
        if qtype in CHOICE_TYPES:
            std = _norm(q.get("answer", ""))
            stu = _norm(ac_by_num.get(num, {}).get("filled", ""))
            scored = full if (std and stu and std == stu) else 0.0
            reason = f"涂卡={stu or '空'} 标答={std} → {'对' if scored else '错'}"
            review = not stu
        else:
            g = subj_grades.get(num, {})
            sc = g.get("suggestedScore", 0)
            try:
                scored = max(0.0, min(full, float(sc)))
            except (TypeError, ValueError):
                scored = 0.0
            reason = g.get("scoreReason", "未找到作答" if not g else "")
            review = bool(g.get("needsTeacherReview", True))
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
