#!/usr/bin/env python3
"""把 exam-ocr 流水线产出的 final.json → 学情报告流水线用的 paper.json。

CLI:
    python final_to_paper.py \\
        --final structured-cloud/final.json \\
        --output paper.json

模块:
    from scripts.exam_ocr.final_to_paper import convert_final_to_paper
    paper = convert_final_to_paper(final, exam_meta=...)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# 北京中考各科典型分数布局（meta 用，可被 answer-key 覆盖）
DEFAULT_SCORE_HINTS = {
    "physics": {
        "totalScore": 70,
        "duration": 70,
        "subject_label": "物理",
        # 题号 → (section, type, score)
        "layout": {
            **{i: ("一、单项选择题", "choice",        2) for i in range(1, 13)},
            **{i: ("二、多项选择题", "multi_choice",  2) for i in range(13, 16)},
            16: ("三、实验探究题", "experiment", 3),
            17: ("三、实验探究题", "experiment", 3),
            18: ("三、实验探究题", "experiment", 4),
            19: ("三、实验探究题", "experiment", 3),
            20: ("三、实验探究题", "experiment", 4),
            21: ("三、实验探究题", "experiment", 4),
            22: ("三、实验探究题", "experiment", 4),
            23: ("三、实验探究题", "experiment", 3),
            24: ("四、科普阅读题", "essay",      4),
            25: ("五、计算题",     "calculation", 4),
            26: ("五、计算题",     "calculation", 4),
        },
    },
    "math": {
        "totalScore": 100,
        "duration": 120,
        "subject_label": "数学",
        "layout": {
            **{i: ("一、选择题", "choice", 2) for i in range(1, 9)},
            **{i: ("二、填空题", "fill_blank", 2) for i in range(9, 17)},
            **{i: ("三、解答题", "essay", 5) for i in range(17, 23)},
            23: ("三、解答题", "essay", 6),
            24: ("三、解答题", "essay", 6),
            25: ("三、解答题", "essay", 5),
            26: ("三、解答题", "essay", 6),
            27: ("三、解答题", "essay", 7),
            28: ("三、解答题", "essay", 8),
        },
    },
    "chinese": {
        "totalScore": 100,
        "duration": 150,
        "subject_label": "语文",
        "layout": {},  # 语文版面复杂，暂留空（用 final.json 原始 type）
    },
}


def convert_final_to_paper(
    final: dict,
    subject: str | None = None,
    exam_meta: dict | None = None,
) -> dict:
    """final.json (exam-ocr output) → paper.json (student-report input)。

    Args:
        final: exam-ocr 流水线产出（含 questions[].number, type, text, options）
        subject: 学科 ('physics' / 'math' / ...)；若 None 则从 final 推断
        exam_meta: 可选 exam 字段（city, district, year 等）。覆盖默认值。
    """
    subject = subject or final.get("subject", "")
    hints = DEFAULT_SCORE_HINTS.get(subject, {})
    layout = hints.get("layout", {})

    # 构造 meta
    meta_exam = exam_meta or {}
    meta = {
        "exam": {
            "city": meta_exam.get("city", "北京"),
            "district": meta_exam.get("district", ""),
            "grade": meta_exam.get("grade", "初三"),
            "examType": meta_exam.get("examType", ""),
            "year": meta_exam.get("year", 2026),
            "subject": meta_exam.get("subject", hints.get("subject_label", subject)),
        },
        "examFullName": meta_exam.get("examFullName", final.get("exam", "")),
        "totalScore": hints.get("totalScore", 0),
        "duration": hints.get("duration", 0),
        "questionCount": len(final.get("questions", [])),
    }

    # 转换 questions
    questions_out = []
    for q in final.get("questions", []):
        n = q.get("number")
        if n is None:
            # 从 id "physics-q01" 抽数字
            qid_str = q.get("id", "")
            digits = "".join(c for c in qid_str if c.isdigit())
            n = int(digits) if digits else 0

        # layout 推断 section/type/score
        sec, typ, score = layout.get(n, (None, None, None))

        item = {
            "id": f"Q{n}",
            "type": typ or q.get("type", "essay"),
            "section": sec or "",
            "score": score or 0,
            "stem": q.get("text", ""),
        }
        if q.get("options"):
            # 标准化 options 格式
            opts = []
            for o in q["options"]:
                if isinstance(o, dict):
                    opts.append({"label": o.get("label", ""), "text": o.get("text", "")})
                elif isinstance(o, str):
                    opts.append({"label": "", "text": o})
            item["options"] = opts
        if q.get("source_page"):
            item["sourcePages"] = [f"page-{int(q['source_page']):02d}"]
        questions_out.append(item)

    return {"meta": meta, "questions": questions_out}


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(description="final.json → paper.json 适配器")
    parser.add_argument("--final", type=Path, required=True,
                        help="exam-ocr 输出的 final.json")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="输出 paper.json")
    parser.add_argument("--subject", help="学科（physics/math/chinese 等），默认从 final.json 读")
    parser.add_argument("--exam-meta", type=Path,
                        help="可选 JSON 文件，包含 exam 字段（district/year/examType 等）")
    args = parser.parse_args()

    final = json.loads(args.final.read_text(encoding="utf-8"))
    exam_meta = None
    if args.exam_meta:
        exam_meta = json.loads(args.exam_meta.read_text(encoding="utf-8"))

    paper = convert_final_to_paper(
        final, subject=args.subject, exam_meta=exam_meta,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✅ {args.output}", file=sys.stderr)
    print(f"   {paper['meta']['questionCount']} 题, 总分 {paper['meta']['totalScore']}",
          file=sys.stderr)
    # 摘要
    for q in paper["questions"][:10]:
        print(f"   {q['id']:<6} {q['type']:<15} {q['score']}分 - {q['stem'][:50]}",
              file=sys.stderr)
    if len(paper["questions"]) > 10:
        print(f"   ... 还有 {len(paper['questions']) - 10} 题", file=sys.stderr)


if __name__ == "__main__":
    main()
