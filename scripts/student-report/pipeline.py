#!/usr/bin/env python3
"""学情报告生成 pipeline — 端到端：4 JSON 输入 → Markdown + PDF。

用法：
    python3 pipeline.py \
        --student-dir students/jiaxiaoqi/chaoyang-2026-yimo-physics \
        --out-dir "learning situation"

需环境变量 DASHSCOPE_API_KEY（Qwen-max）。
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "student-report"))
sys.path.insert(0, str(ROOT / "scripts" / "answer-card-ocr"))

from lib import analyze, render, pdf  # noqa: E402


SUBJECT_LABEL = {"语文": "语文", "数学": "数学", "英语": "英语", "物理": "物理", "化学": "化学", "道法": "道法"}


def maybe_generate_answer_card(student_dir: Path) -> Path:
    """如果 answer-card.json 不存在但同目录有 answer-card-photos/，
    自动调 detect.py 生成。

    Returns: answer-card.json 路径
    """
    target = student_dir / "answer-card.json"
    if target.exists():
        return target

    photos_dir = student_dir / "answer-card-photos"
    if not photos_dir.exists():
        raise FileNotFoundError(
            f"找不到 {target}，也没找到 {photos_dir} 目录可供 OCR。\n"
            f"请提供 answer-card.json 或把答题卡照片放到 answer-card-photos/ 下。"
        )

    # 收集照片（jpg/png/heic）
    photos = sorted([
        p for p in photos_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}
    ])
    if not photos:
        raise FileNotFoundError(f"{photos_dir} 为空")

    print(f"\n🔍 未找到 answer-card.json，从 {len(photos)} 张照片自动 OCR ...")
    import detect  # type: ignore
    # 从可选的 student.json 取学生姓名（若无则匿名）
    student_meta = {}
    student_json = student_dir / "student.json"
    if student_json.exists():
        student_meta = json.loads(student_json.read_text(encoding="utf-8"))
    result = detect.detect_card(
        photos,
        student_name=student_meta.get("name", student_dir.name),
        student_id=student_meta.get("examId", ""),
    )
    out = {"student": result.student, "answers": result.answers}
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → 生成 {target.name}（{len(result.answers)} 题）")
    return target


def load_inputs(student_dir: Path):
    """读 4 个 JSON。如 answer-card.json 缺失则自动 OCR 生成。"""
    maybe_generate_answer_card(student_dir)
    return {
        "paper": json.loads((student_dir / "paper.json").read_text(encoding="utf-8")),
        "answer_key": json.loads((student_dir / "answer-key.json").read_text(encoding="utf-8")),
        "answer_card": json.loads((student_dir / "answer-card.json").read_text(encoding="utf-8")),
        "scores": json.loads((student_dir / "scores.json").read_text(encoding="utf-8")),
    }


def join_by_qid(paper, answer_key, answer_card, scores):
    """按 qId 对齐 4 个数据源。"""
    q_by_id = {q["id"]: q for q in paper["questions"]}
    ak_by_id = {a["id"]: a for a in answer_key["answers"]}
    sa_by_id = {a["qId"]: a for a in answer_card["answers"]}
    sc_by_id = {s["qId"]: s for s in scores["questions"]}

    # 仅返回失分题（错或部分对）
    lost_qs = []
    for sc in scores["questions"]:
        if not (sc.get("isWrong") or sc.get("isPartial")):
            continue
        qid = sc["qId"]
        if qid not in q_by_id:
            print(f"⚠️  失分题 {qid} 在 paper.json 中没找到，跳过", file=sys.stderr)
            continue
        lost_qs.append({
            "question": q_by_id[qid],
            "answer": ak_by_id.get(qid, {}),
            "student": sa_by_id.get(qid, {}),
            "score": sc,
        })
    return lost_qs


def analyze_all_lost(lost_qs, cache_prefix: str):
    """对所有失分题逐一调 LLM 分析。"""
    results = []
    for i, item in enumerate(lost_qs):
        qid = item["question"]["id"]
        print(f"  [{i+1}/{len(lost_qs)}] 分析 {qid} ...", flush=True)
        analysis = analyze.analyze_question(
            question=item["question"],
            answer=item["answer"],
            student=item["student"],
            score=item["score"],
            cache_key=f"{cache_prefix}-{qid}",
        )
        results.append({**item, "analysis": analysis})
    return results


def build_score_table(scores):
    """渲染得分总览表。"""
    rows = []
    for s in scores["sections"]:
        full = s["fullScore"]
        scored = s["scored"]
        lost = full - scored
        if lost == 0:
            label = "0 ✅"
        elif scored == 0:
            label = f"**−{lost}** ❌"
        else:
            label = f"**−{lost}** ⚠️"
        rows.append({
            "section": s["section"],
            "qRange": s["qRange"],
            "scored": scored,
            "full": full,
            "lostLabel": label,
        })
    return rows


def build_overall(analyzed, paper, scores, cache_key):
    """整卷综合分析。"""
    exam_total = scores["examTotal"]
    exam_summary = (
        f"科目：{paper['meta']['exam']['subject']}\n"
        f"总分：{exam_total['scored']} / {exam_total['fullScore']}\n"
        f"考试：{paper['meta'].get('examFullName', '')}\n"
        f"时长：{paper['meta'].get('duration', '?')} 分钟"
    )
    lost_lines = []
    for item in analyzed:
        q = item["question"]
        sc = item["score"]
        lost = sc["fullScore"] - sc["scored"]
        lost_lines.append(f"- {q['id']}（{q.get('section', '')}）: 扣 {lost} 分（{sc['scored']}/{sc['fullScore']}）")
    lost_summary = "\n".join(lost_lines)

    per_q_lines = []
    for item in analyzed:
        a = item["analysis"]
        per_q_lines.append(
            f"- {item['question']['id']}: [{a.get('errorType','?')}] {a.get('knowledgePoint','')} — {a.get('rootCause','')[:80]}..."
        )
    per_q_summary = "\n".join(per_q_lines)

    return analyze.analyze_overall(
        exam_summary=exam_summary,
        lost_summary=lost_summary,
        per_question_summary=per_q_summary,
        cache_key=cache_key,
    )


# 题号 Q12 → 12
def _qid_num(qid: str) -> int:
    m = re.search(r"\d+", qid)
    return int(m.group(0)) if m else 0


def build_context(student_name, paper, scores, analyzed, overall) -> dict:
    """组装 Jinja2 模板上下文。"""
    exam = paper["meta"]["exam"]
    exam_label = f"{exam['year']} {exam['district']}{exam['examType']}"
    subject = exam["subject"]

    # 失分题渲染：选项展开 + 学生/标答标签化
    wrong = []
    for item in analyzed:
        q = item["question"]
        a = item["answer"]
        s = item["student"]
        sc = item["score"]

        correct = a.get("correct") or a.get("correctSolution", "")
        if isinstance(correct, list):
            correct_label = "".join(correct) if all(len(c) == 1 for c in correct) else "、".join(correct)
        else:
            correct_label = str(correct)

        filled = s.get("filled")
        if filled is None:
            student_label = s.get("rawText", "（未作答）")[:60] + ("..." if len(s.get("rawText",""))>60 else "")
        elif isinstance(filled, list):
            student_label = "".join(filled)
        else:
            student_label = str(filled)

        type_map = {
            "choice": "单选", "multi_choice": "多选",
            "fill_blank": "填空", "calculation": "计算",
            "experiment": "实验探究", "essay": "大题/科普"
        }

        wrong.append({
            "id": q["id"],
            "id_num": _qid_num(q["id"]),
            "type_label": f"{type_map.get(q.get('type'), q.get('type', '?'))} · {q.get('section', '')}",
            "lost": sc["fullScore"] - sc["scored"],
            "full": sc["fullScore"],
            "stem": q.get("stem", ""),
            "options": q.get("options", []),
            "correct_label": correct_label,
            "student_label": student_label,
            "analysis": item["analysis"],
        })
    wrong.sort(key=lambda x: x["id_num"])

    return {
        "student_name": student_name,
        "student_id": "（脱敏）",
        "exam_label": exam_label,
        "subject": subject,
        "exam_full_name": paper["meta"].get("examFullName", ""),
        "duration": paper["meta"].get("duration", "?"),
        "total_scored": scores["examTotal"]["scored"],
        "total_full": scores["examTotal"]["fullScore"],
        "total_lost": scores["examTotal"]["fullScore"] - scores["examTotal"]["scored"],
        "score_table": build_score_table(scores),
        "wrong_count": len(wrong),
        "wrong_questions": wrong,
        "overall": overall,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--student-dir", required=True, help="含 paper/answer-key/answer-card/scores.json")
    parser.add_argument("--out-dir", default="learning situation")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--cache-prefix", default=None, help="LLM 缓存前缀，默认按 student-dir basename")
    args = parser.parse_args()

    student_dir = (ROOT / args.student_dir).resolve()
    out_dir = (ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_prefix = args.cache_prefix or student_dir.name

    print(f"📂 输入: {student_dir}")
    inputs = load_inputs(student_dir)

    paper = inputs["paper"]
    scores = inputs["scores"]
    exam = paper["meta"]["exam"]
    subject = exam["subject"]
    student_name = inputs["answer_card"]["student"]["name"]
    exam_slug = f"{exam['year']}-{exam['district']}-{exam['examType']}-{subject}"

    print(f"📊 学生: {student_name}　考试: {exam_slug}")

    print("\n=== 步骤 1：对齐失分题 ===")
    lost = join_by_qid(paper, inputs["answer_key"], inputs["answer_card"], scores)
    print(f"  发现 {len(lost)} 道失分题")

    print("\n=== 步骤 2：逐题 LLM 分析（含 .cache 复用） ===")
    analyzed = analyze_all_lost(lost, cache_prefix)

    print("\n=== 步骤 3：整卷综合诊断 LLM ===")
    overall = build_overall(analyzed, paper, scores, cache_key=f"{cache_prefix}-overall")

    print("\n=== 步骤 4：渲染 Markdown ===")
    context = build_context(student_name, paper, scores, analyzed, overall)
    md = render.render_report(context)

    out_md = out_dir / f"{student_name}_{exam_slug}_失分分析与提分建议_v2.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"  → {out_md.relative_to(ROOT)} ({len(md)} chars)")

    if not args.skip_pdf:
        print("\n=== 步骤 5：转 PDF ===")
        out_pdf = out_md.with_suffix(".pdf")
        pdf.md_to_pdf(md, out_pdf, title=f"{student_name} 学情报告")
        print(f"  → {out_pdf.relative_to(ROOT)} ({out_pdf.stat().st_size} bytes)")

    print("\n✅ 完成")


if __name__ == "__main__":
    main()
