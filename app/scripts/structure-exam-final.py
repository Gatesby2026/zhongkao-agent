#!/usr/bin/env python3

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SUBJECTS = ["chinese", "math", "physics", "english", "daofa"]
SUBJECT_LABELS = {
    "chinese": "语文",
    "math": "数学",
    "physics": "物理",
    "english": "英语",
    "daofa": "道德与法治",
}
EXPECTED_MAX = {
    "chinese": 27,
    "math": 28,
    "physics": 26,
    "english": 38,
    "daofa": 25,
}
SUBJECT_ENGINE_HINTS = {
    "chinese": [
        "PaddleOCR first pass",
        "Aliyun education OCR sidecar",
        "DashScope qwen-vl-ocr-latest for phonetics and passage repair",
        "manual critical notes for pronunciation traps",
    ],
    "math": [
        "PaddleOCR first pass",
        "Aliyun education OCR page 2 for formula recovery",
        "DashScope qwen-vl-ocr-latest page 2 for formula/table validation",
    ],
    "physics": ["PaddleOCR first pass"],
    "english": ["PaddleOCR first pass", "manual repair for matching/table and reading boundaries"],
    "daofa": ["PaddleOCR first pass"],
}
OPTION_RE = re.compile(r"(?m)^[A-D][.．、]\s*")
PAGE_FOOTER_RE = re.compile(r"(?m)^.*?试卷\s*第\s*\d+\s*页[（(]共\s*\d+\s*页[）)]\s*$")
FENCE_RE = re.compile(r"^```(?:json|text|markdown)?\s*|\s*```$", re.S)


def parse_args():
    parser = argparse.ArgumentParser(description="Build final structured exam JSON from OCR drafts.")
    parser.add_argument("--base-dir", default="data/chaoyang-2026-yimo")
    parser.add_argument("--subjects", default=",".join(SUBJECTS))
    return parser.parse_args()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def question_type(subject, number, text):
    if subject == "english":
        if number <= 33:
            return "choice"
        if number <= 37:
            return "reading_response"
        return "writing"
    if subject == "chinese":
        if OPTION_RE.search(text):
            return "choice"
        if number == 27:
            return "writing"
        if number >= 11:
            return "reading_response"
        return "fill_or_short_response"
    if subject == "math":
        if number <= 8:
            return "choice"
        if number <= 16:
            return "fill_blank"
        return "solution"
    if subject == "physics":
        if number <= 15:
            return "choice"
        return "experiment_or_calculation"
    if subject == "daofa":
        if number <= 10:
            return "judgement"
        if number <= 20:
            return "choice"
        return "short_response"
    return "question"


def clean_text(text):
    text = FENCE_RE.sub("", text.strip())
    text = PAGE_FOOTER_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_options(text):
    matches = list(OPTION_RE.finditer(text))
    if not matches:
        return []
    options = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        label = match.group(0)[0]
        value = text[match.end():end].strip()
        options.append({"label": label, "text": value})
    return options


def normalize_question(subject, question):
    text = clean_text(question.get("text", ""))
    number = question["number"]
    normalized = {
        "id": f"{subject}-q{number:02d}",
        "number": number,
        "type": question_type(subject, number, text),
        "text": text,
        "options": parse_options(text),
        "source_pages": question.get("source_pages"),
        "bbox": question.get("bbox"),
        "avg_confidence": question.get("avg_confidence"),
        "linked_passage_id": question.get("linked_passage_id"),
        "needs_review": bool(question.get("needs_review")),
        "review_reason": question.get("review_reason"),
        "provenance": question.get("ocr_provenance") or {"primary": "questions.draft.json"},
    }
    return {key: value for key, value in normalized.items() if value not in (None, [], "")}


def split_by_question_markers(text):
    text = clean_text(text)
    markers = list(re.finditer(r"(?m)^(\d{1,2})[.．]\s*", text))
    chunks = {}
    for index, marker in enumerate(markers):
        number = int(marker.group(1))
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        chunks[number] = text[marker.start():end].strip()
    return chunks


def patch_chinese(base_dir, draft):
    processed = base_dir / "processed" / "chinese"
    qwen_page3 = read_text(processed / "dashscope-qwen-vl-ocr" / "page-03.extracted.txt")
    qwen_page6 = read_text(processed / "dashscope-qwen-vl-ocr" / "page-06.extracted.txt")
    qwen_page8 = read_text(processed / "dashscope-qwen-vl-ocr" / "page-08.extracted.txt")
    page3_chunks = split_by_question_markers(qwen_page3)

    by_number = {q["number"]: q for q in draft["questions"]}

    # Q3 is a known pronunciation trap. The source text intentionally marks 矗 as zhù.
    q3 = by_number.get(3)
    if q3:
        q3["text"] = (
            "3. 你审核资料中标注的字音。下列判断不正确的一项是(2 分)\n"
            "A. 矗立\nB. 登载\nC. 赫然\nD. 汲取"
        )
        q3["needs_review"] = True
        q3["review_reason"] = (
            "Critical phonetic trap. Source text on page 1 is 北大红楼巍然矗（zhù）立; "
            "correct pronunciation is chù, so option A is the intended incorrect marked pronunciation."
        )
        q3["ocr_provenance"] = {
            "primary": "dashscope-qwen-vl-ocr/page-01 + manual image check",
            "critical_note": "processed/chinese/critical-notes.json",
        }

    for number in [8, 9, 10, 11, 12]:
        if number in page3_chunks:
            existing = by_number.get(number)
            if existing:
                existing["text"] = page3_chunks[number]
                existing["source_pages"] = {"start": 3, "end": 3}
                existing["needs_review"] = True
                existing["review_reason"] = "Repaired from DashScope Qwen OCR page 3 to fix missed/smeared ancient-poetry segmentation."
                existing["ocr_provenance"] = {"primary": "dashscope-qwen-vl-ocr/page-03.extracted.txt"}
            else:
                draft["questions"].append(
                    {
                        "id": f"chinese-q{number:02d}",
                        "type": "question",
                        "number": number,
                        "text": page3_chunks[number],
                        "source_pages": {"start": 3, "end": 3},
                        "bbox": None,
                        "avg_confidence": None,
                        "linked_passage_id": None,
                        "needs_review": True,
                        "review_reason": "Recovered from DashScope Qwen OCR page 3; PaddleOCR segmentation missed this question.",
                        "ocr_provenance": {"primary": "dashscope-qwen-vl-ocr/page-03.extracted.txt"},
                    }
                )

    q19 = by_number.get(19)
    if q19 and qwen_page6:
        chunk = split_by_question_markers(qwen_page6).get(19)
        if chunk:
            q19["text"] = chunk
            q19["source_pages"] = {"start": 6, "end": 6}
            q19["needs_review"] = True
            q19["review_reason"] = "Trimmed from Qwen page 6; old draft swallowed the next reading passage."
            q19["ocr_provenance"] = {"primary": "dashscope-qwen-vl-ocr/page-06.extracted.txt"}

    # Trim q23 if old Paddle segmentation swallowed the next passage.
    q23 = by_number.get(23)
    if q23 and "(三)阅读" in q23.get("text", ""):
        q23["text"] = q23["text"].split("(三)阅读", 1)[0].strip()
        q23["source_pages"] = {"start": 8, "end": 8}
        q23["needs_review"] = True
        q23["review_reason"] = "Trimmed; old draft swallowed the next reading passage."

    # If Qwen page 8 has the clean q23 prompt, prefer it.
    page8_chunks = split_by_question_markers(qwen_page8)
    if 23 in page8_chunks and q23:
        q23["text"] = page8_chunks[23].split("九年级语文试卷", 1)[0].strip()
        q23["ocr_provenance"] = {"primary": "dashscope-qwen-vl-ocr/page-08.extracted.txt"}

    draft["questions"].sort(key=lambda q: q["number"])
    return draft


def patch_english(draft):
    by_number = {q["number"]: q for q in draft["questions"]}
    repairs = {
        21: (
            "21. Liu Hao\n"
            "I love the natural world! I want to join the School Plant Watch. I'll look at different flowers and leaves, "
            "take photos of special plants, and help our science teacher make a school plant guide."
        ),
        22: (
            "22. Lingling\n"
            "I'd like to take part in the Star Watching Club. I'll learn to watch stars, recognize well-known star groups, "
            "and write reports about the different shapes of the moon for our class newspaper."
        ),
        23: (
            "23. Li Wei\n"
            "I care about our planet! I want to join the River Protection Group. I'll check the water quality near our school, "
            "and send my information to scientists to help protect local water."
        ),
    }
    for number, text in repairs.items():
        if number in by_number:
            by_number[number]["text"] = text
            by_number[number]["source_pages"] = {"start": 4, "end": 4}
            by_number[number]["needs_review"] = True
            by_number[number]["review_reason"] = "Repaired matching-table boundary; old draft merged adjacent rows/passages."
            by_number[number]["ocr_provenance"] = {"primary": "manual repair from PaddleOCR page-04.txt"}
        else:
            draft["questions"].append(
                {
                    "id": f"english-q{number:02d}",
                    "type": "question",
                    "number": number,
                    "text": text,
                    "source_pages": {"start": 4, "end": 4},
                    "bbox": None,
                    "avg_confidence": None,
                    "linked_passage_id": None,
                    "needs_review": True,
                    "review_reason": "Recovered matching-table item from PaddleOCR page-04.txt.",
                    "ocr_provenance": {"primary": "manual repair from PaddleOCR page-04.txt"},
                }
            )

    for number, next_marker in [(26, "九年级英语试卷"), (26, "Many people think")]:
        q = by_number.get(number)
        if q and next_marker in q.get("text", ""):
            q["text"] = q["text"].split(next_marker, 1)[0].strip()
            q["source_pages"] = {"start": 5, "end": 5}
            q["needs_review"] = True
            q["review_reason"] = "Trimmed; old draft swallowed the next reading passage."

    draft["questions"].sort(key=lambda q: q["number"])
    return draft


def patch_math(draft):
    for question in draft["questions"]:
        if question["number"] == 8:
            question["ocr_provenance"] = {
                "primary": "Aliyun education OCR + DashScope Qwen OCR page 2",
                "note": "Formula repaired to y=2/x (x>0).",
            }
        if question["number"] == 11:
            question["ocr_provenance"] = {
                "primary": "Aliyun education OCR + DashScope Qwen OCR page 2",
                "note": "Fractional equation recovered as 2/(x+3)=1/x.",
            }
    return draft


def apply_best_practice_patches(subject, base_dir, draft):
    if subject == "chinese":
        return patch_chinese(base_dir, draft)
    if subject == "english":
        return patch_english(draft)
    if subject == "math":
        return patch_math(draft)
    return draft


def quality(subject, questions):
    numbers = sorted(q["number"] for q in questions)
    expected = EXPECTED_MAX[subject]
    missing = [number for number in range(1, expected + 1) if number not in numbers]
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    return {
        "expected_question_count": expected,
        "question_count": len(numbers),
        "missing_numbers": missing,
        "duplicate_numbers": duplicates,
        "needs_review_count": sum(1 for q in questions if q.get("needs_review")),
        "complete_numbering": not missing and not duplicates,
    }


def build_subject(base_dir, subject):
    subject_dir = base_dir / "processed" / subject
    draft = read_json(subject_dir / "questions.draft.json")
    draft = apply_best_practice_patches(subject, base_dir, draft)
    questions = [normalize_question(subject, q) for q in sorted(draft["questions"], key=lambda item: item["number"])]
    payload = {
        "schema_version": "exam-structured-v1",
        "generated_at": now_iso(),
        "paper": {
            "id": "beijing-chaoyang-2026-yimo",
            "title": "2026 北京朝阳初三一模",
            "subject": subject,
            "subject_label": SUBJECT_LABELS[subject],
        },
        "ocr_strategy": SUBJECT_ENGINE_HINTS[subject],
        "source_files": {
            "draft": str(subject_dir / "questions.draft.json"),
            "paddle_raw": str(subject_dir / "raw.txt"),
            "answer_blocks": str(subject_dir / "questions.draft.json") + "#answer_blocks",
        },
        "questions": questions,
        "passage_groups": draft.get("passage_groups", []),
        "answer_blocks": draft.get("answer_blocks", []),
        "quality": quality(subject, questions),
    }
    if subject == "chinese" and (subject_dir / "critical-notes.json").exists():
        payload["critical_notes"] = read_json(subject_dir / "critical-notes.json")
    return payload, draft


def write_markdown(path, structured):
    lines = [
        f"# {structured['paper']['title']} {structured['paper']['subject_label']}结构化稿",
        "",
        f"- 题目数: {structured['quality']['question_count']} / {structured['quality']['expected_question_count']}",
        f"- 缺失题号: {structured['quality']['missing_numbers'] or '无'}",
        f"- 需复核: {structured['quality']['needs_review_count']}",
        "",
    ]
    for q in structured["questions"]:
        lines.append(f"## {q['number']}. {q['type']}")
        lines.append("")
        lines.append(q["text"])
        if q.get("review_reason"):
            lines.append("")
            lines.append(f"> Review: {q['review_reason']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    args = parse_args()
    base_dir = Path(args.base_dir)
    subjects = [item.strip() for item in args.subjects.split(",") if item.strip()]
    index = {
        "schema_version": "exam-structured-index-v1",
        "generated_at": now_iso(),
        "paper_id": "beijing-chaoyang-2026-yimo",
        "subjects": {},
    }
    for subject in subjects:
        structured, patched_draft = build_subject(base_dir, subject)
        out_dir = base_dir / "processed" / subject / "structured"
        write_json(out_dir / "final.json", structured)
        write_markdown(out_dir / "final.md", structured)
        # Save a patched draft copy for audit, but do not overwrite the raw OCR.
        write_json(out_dir / "questions.best-practice.json", patched_draft)
        index["subjects"][subject] = {
            "label": SUBJECT_LABELS[subject],
            "final_json": str(out_dir / "final.json"),
            "final_md": str(out_dir / "final.md"),
            "quality": structured["quality"],
        }
        print(
            f"[{subject}] questions={structured['quality']['question_count']} "
            f"missing={structured['quality']['missing_numbers']} "
            f"review={structured['quality']['needs_review_count']}"
        )
    write_json(base_dir / "processed" / "structured-index.json", index)


if __name__ == "__main__":
    main()
