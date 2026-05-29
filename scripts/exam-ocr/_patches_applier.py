"""共用 patch 应用器 — 给 4 学科 image_paper.py 共用。
chinese 已有内嵌实现，physics/math/english 引这个模块。
"""
from __future__ import annotations
from pathlib import Path


def apply_patches_to_final(patches: dict, result: dict) -> int:
    """对 final.json 结构（questions 用 `number` 字段）应用 patches。
    支持 question 层 create/stem/options/answer/solution/score/type，
    支持 answers[] 同步（enrich 用 answers[].solution/correct），
    支持 passages 层 create/body/q_range/figure/type/body_replace/body_append。
    返回应用的 patch 数。
    """
    n = 0
    # passages
    for pid, patch in (patches.get("passages") or {}).items():
        if patch.get("create"):
            existing = next((ps for ps in result.get("passages", []) if ps["id"] == pid), None)
            if existing is None:
                result.setdefault("passages", []).append({
                    "id": pid,
                    "type": patch.get("type", pid),
                    "q_range": patch.get("q_range") or [1, 1],
                    "body": patch.get("body", ""),
                    "figure": patch.get("figure"),
                })
                n += 1
                continue
        for ps in result.get("passages", []):
            if ps["id"] != pid: continue
            for rep in patch.get("body_replace") or []:
                if rep.get("from") and rep["from"] in ps.get("body",""):
                    ps["body"] = ps["body"].replace(rep["from"], rep.get("to",""))
                    n += 1
            if patch.get("body_append"):
                ps["body"] = (ps.get("body","") + patch["body_append"]); n += 1
            if "figure" in patch: ps["figure"] = patch["figure"]; n += 1
            if "body" in patch:   ps["body"]   = patch["body"]; n += 1
            if "q_range" in patch: ps["q_range"] = patch["q_range"]; n += 1
            if "type" in patch:   ps["type"]   = patch["type"]; n += 1
            break
    # questions
    for qid_raw, patch in (patches.get("questions") or {}).items():
        qid = int(qid_raw)
        target = next((q for q in result.get("questions", []) if q.get("number") == qid), None)
        if target is None and patch.get("create"):
            new_q = {
                "number": qid,
                "type": patch.get("type", "subjective_blank"),
                "stem": patch.get("stem", ""),
                "options": patch.get("options"),
                "answer": patch.get("answer", ""),
                "solution": patch.get("solution", ""),
                "score": patch.get("score", 0),
                "section": patch.get("section", ""),
            }
            insert_at = next((i for i, q in enumerate(result["questions"])
                              if q.get("number", 0) > qid), len(result["questions"]))
            result["questions"].insert(insert_at, new_q)
            # 同步加 answers[]（enrich 真正读这里）
            ans_new = {"number": qid,
                        "correct": patch.get("answer", ""),
                        "solution": patch.get("solution", ""),
                        "score": patch.get("score", 0)}
            answers = result.setdefault("answers", [])
            insert_at_ans = next((i for i, a in enumerate(answers)
                                   if a.get("number", 0) > qid), len(answers))
            answers.insert(insert_at_ans, ans_new)
            n += 1
            continue
        if target is None: continue
        q = target
        # 'in patch' 区分 missing vs explicit null/空串
        if "stem" in patch:
            q["stem"] = patch["stem"]; n += 1
        if patch.get("stem_append"):
            q["stem"] = q.get("stem","") + patch["stem_append"]; n += 1
        if "options" in patch:
            q["options"] = patch["options"]; n += 1
        if "solution" in patch:
            q["solution"] = patch["solution"]; n += 1
            ans = next((a for a in result.get("answers", []) if a.get("number") == qid), None)
            if ans is not None:
                ans["solution"] = patch["solution"]
        if "answer" in patch:
            q["answer"] = patch["answer"]; n += 1
            ans = next((a for a in result.get("answers", []) if a.get("number") == qid), None)
            if ans is not None:
                ans["correct"] = patch["answer"]
            else:
                # 若 answers 缺这条，补一条（enrich 才能读到）
                ans_new = {"number": qid, "correct": patch["answer"],
                            "solution": patch.get("solution", q.get("solution", "")),
                            "score": q.get("score", 0)}
                result.setdefault("answers", []).append(ans_new)
        if patch.get("type"):
            q["type"] = patch["type"]; n += 1
        if "score" in patch:
            q["score"] = patch["score"]; n += 1
        # has_image_options（physics/math Q1/Q4 等图选项题，enrich 需此 flag
        # 否则误标 'needs_review: 选择题缺少 options'）
        if "has_image_options" in patch:
            q["has_image_options"] = patch["has_image_options"]; n += 1
        # 通用兜底：透传 patch 任意其他字段
        for k in patch:
            if k in ("stem","stem_append","options","solution","answer","type","score",
                      "has_image_options","create","section","passage_id"):
                continue
            q[k] = patch[k]; n += 1
    # 重算 full_score
    if n:
        result["full_score"] = sum(q.get("score", 0) or 0 for q in result.get("questions", []))
    return n


def load_and_apply_patches(slug: str, subject: str, result: dict, repo_root: Path) -> int:
    """加载 _patches/<subject>/<slug>.yaml 并应用。返回 patch 数。"""
    try:
        import yaml
    except ImportError: return 0
    patch_path = repo_root / "knowledge-base" / "exams" / "_patches" / subject / f"{slug}.yaml"
    if not patch_path.exists(): return 0
    try:
        patches = yaml.safe_load(patch_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"⚠ patch 加载失败 {patch_path.name}: {e}"); return 0
    return apply_patches_to_final(patches, result)
