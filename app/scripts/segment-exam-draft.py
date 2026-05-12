#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


PASSAGE_SUBJECTS = {"chinese", "english"}
EXPECTED_MAX_QUESTION = {
    "chinese": 27,
    "math": 28,
    "physics": 26,
    "english": 38,
    "daofa": 25,
}
SECTION_RE = re.compile(r"^[一二三四五六七八九十]+[、.．]\s*")
QUESTION_RE = re.compile(r"^(\d{1,2})[.．、]\s*")
RANGE_RE = re.compile(r"完成\s*(\d{1,2})\s*[-－—至]\s*(\d{1,2})\s*题")
EN_READING_RE = re.compile(r"阅读(下面|下列|短文)|Read\b|passage", re.IGNORECASE)
ZH_READING_RE = re.compile(r"阅读|材料[一二三四五六七八九十]|名著|写作")
JUNK_RE = re.compile(r"^(学校|班级|姓名|考号|考|生|须|知)$")
ANSWER_SECTION_RE = re.compile(r"(答案及评分|参考答案|答案及评分标准|试卷答案)")


def parse_args():
    parser = argparse.ArgumentParser(description="Create conservative draft question segmentation from OCR text.")
    parser.add_argument("--base-dir", default="data/chaoyang-2026-yimo")
    parser.add_argument("--subjects", default="chinese,math,physics,english,daofa")
    return parser.parse_args()


def load_lines(subject_dir: Path):
    rows = []
    for json_path in sorted((subject_dir / "pages").glob("page-*.ocr.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        page_match = re.search(r"page-(\d+)", json_path.name)
        page = payload.get("page") or int(page_match.group(1))
        for line in payload["lines"]:
            text = line["text"].strip()
            if not text:
                continue
            rows.append(
                {
                    "page": page,
                    "line_index": line["index"],
                    "text": text,
                    "confidence": line["confidence"],
                    "box": line["box"],
                }
            )
    return rows


def page_ref(rows):
    pages = sorted({row["page"] for row in rows})
    return {"start": pages[0], "end": pages[-1]} if pages else None


def bbox_ref(rows):
    points = []
    for row in rows:
        points.extend(row["box"])
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def make_question(subject, number, rows, linked_passage_id=None):
    text = "\n".join(row["text"] for row in rows).strip()
    return {
        "id": f"{subject}-q{number:02d}",
        "type": "question",
        "number": number,
        "text": text,
        "linked_passage_id": linked_passage_id,
        "source_pages": page_ref(rows),
        "bbox": bbox_ref(rows),
        "avg_confidence": average_confidence(rows),
        "needs_review": subject in PASSAGE_SUBJECTS,
    }


def make_question_from_text(subject, number, text, source_pages, needs_review=True, reason=None):
    question = {
        "id": f"{subject}-q{number:02d}",
        "type": "question",
        "number": number,
        "text": text.strip(),
        "linked_passage_id": None,
        "source_pages": source_pages,
        "bbox": None,
        "avg_confidence": None,
        "needs_review": needs_review,
    }
    if reason:
        question["review_reason"] = reason
    return question


def make_passage(subject, index, rows, expected_question_range=None):
    text = "\n".join(row["text"] for row in rows).strip()
    return {
        "id": f"{subject}-passage-{index:02d}",
        "type": "passage",
        "text": text,
        "expected_question_range": expected_question_range,
        "source_pages": page_ref(rows),
        "bbox": bbox_ref(rows),
        "avg_confidence": average_confidence(rows),
        "needs_review": True,
    }


def average_confidence(rows):
    return round(sum(row["confidence"] for row in rows) / len(rows), 4) if rows else None


def passage_marker(subject, text):
    if subject == "chinese":
        return bool(ZH_READING_RE.search(text))
    if subject == "english":
        return bool(EN_READING_RE.search(text))
    return False


def question_number(text):
    match = QUESTION_RE.match(text)
    return int(match.group(1)) if match else None


def expected_range(text):
    match = RANGE_RE.search(text)
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    return [min(start, end), max(start, end)]


def flush_question(subject, number, rows, questions, linked_passage_id=None):
    if number is not None and rows:
        questions.append(make_question(subject, number, rows, linked_passage_id))


def segment_subject(subject, rows):
    blocks = []
    questions = []
    answer_rows = []
    current_question_number = None
    current_question_rows = []
    current_passage_rows = []
    current_passage_id = None
    current_passage_range = None
    passage_index = 0
    section_rows = []
    seen_section = False
    in_answer_section = False
    last_question_number = 0

    def flush_passage():
        nonlocal current_passage_rows, current_passage_id, current_passage_range, passage_index
        if current_passage_rows:
            passage_index += 1
            passage = make_passage(subject, passage_index, current_passage_rows, current_passage_range)
            blocks.append(passage)
            current_passage_id = passage["id"]
            current_passage_rows = []

    for row in rows:
        text = row["text"]
        if JUNK_RE.match(text):
            continue

        if ANSWER_SECTION_RE.search(text):
            flush_question(subject, current_question_number, current_question_rows, questions, current_passage_id)
            current_question_number = None
            current_question_rows = []
            flush_passage()
            in_answer_section = True

        if in_answer_section:
            answer_rows.append(row)
            continue

        number = question_number(text)
        is_section = bool(SECTION_RE.match(text))
        is_passage_marker = subject in PASSAGE_SUBJECTS and passage_marker(subject, text)

        if is_section:
            seen_section = True
            flush_question(subject, current_question_number, current_question_rows, questions, current_passage_id)
            current_question_number = None
            current_question_rows = []
            flush_passage()
            section_rows.append(row)
            blocks.append(
                {
                    "id": f"{subject}-section-{len(section_rows):02d}",
                    "type": "section",
                    "text": text,
                    "source_pages": page_ref([row]),
                    "bbox": bbox_ref([row]),
                    "avg_confidence": row["confidence"],
                }
            )
            continue

        if number is not None:
            if not seen_section:
                blocks.append(
                    {
                        "id": f"{subject}-note-{len(blocks) + 1:02d}",
                        "type": "note",
                        "text": text,
                        "source_pages": page_ref([row]),
                        "bbox": bbox_ref([row]),
                        "avg_confidence": row["confidence"],
                    }
                )
                continue

            max_question = EXPECTED_MAX_QUESTION.get(subject)
            if (
                max_question is not None
                and (number > max_question or number <= last_question_number)
            ):
                if current_question_number is not None:
                    current_question_rows.append(row)
                else:
                    blocks.append(
                        {
                            "id": f"{subject}-note-{len(blocks) + 1:02d}",
                            "type": "note",
                            "text": text,
                            "source_pages": page_ref([row]),
                            "bbox": bbox_ref([row]),
                            "avg_confidence": row["confidence"],
                        }
                    )
                continue

            if current_question_number is not None:
                flush_question(subject, current_question_number, current_question_rows, questions, current_passage_id)
                current_question_rows = []
            elif current_passage_rows:
                flush_passage()

            current_question_number = number
            last_question_number = number
            current_question_rows = [row]
            if current_passage_range and not (
                current_passage_range[0] <= number <= current_passage_range[1]
            ):
                current_passage_id = None
                current_passage_range = None
            continue

        if is_passage_marker and current_question_number is None:
            if current_passage_rows:
                flush_passage()
            current_passage_rows = [row]
            current_passage_range = expected_range(text)
            continue

        if current_question_number is not None:
            current_question_rows.append(row)
        elif subject in PASSAGE_SUBJECTS and (current_passage_rows or is_passage_marker):
            current_passage_rows.append(row)
        else:
            blocks.append(
                {
                    "id": f"{subject}-note-{len(blocks) + 1:02d}",
                    "type": "note",
                    "text": text,
                    "source_pages": page_ref([row]),
                    "bbox": bbox_ref([row]),
                    "avg_confidence": row["confidence"],
                }
            )

    flush_question(subject, current_question_number, current_question_rows, questions, current_passage_id)
    flush_passage()

    # Add passage groups for easier downstream use.
    passage_by_id = {block["id"]: block for block in blocks if block["type"] == "passage"}
    passage_groups = []
    for passage in passage_by_id.values():
        linked = [question for question in questions if question["linked_passage_id"] == passage["id"]]
        if linked:
            passage_groups.append(
                {
                    "id": passage["id"].replace("passage", "group"),
                    "type": "passage_group",
                    "passage": passage,
                    "questions": linked,
                    "needs_review": True,
                }
            )

    questions = repair_missing_questions(subject, questions)

    return {
        "subject": subject,
        "blocks": blocks,
        "questions": questions,
        "answer_blocks": [
            {
                "id": f"{subject}-answers",
                "type": "answers",
                "text": "\n".join(row["text"] for row in answer_rows).strip(),
                "source_pages": page_ref(answer_rows),
                "bbox": bbox_ref(answer_rows),
                "avg_confidence": average_confidence(answer_rows),
                "needs_review": True,
            }
        ]
        if answer_rows
        else [],
        "passage_groups": passage_groups,
        "stats": {
            "blocks": len(blocks),
            "questions": len(questions),
            "answer_lines": len(answer_rows),
            "passage_groups": len(passage_groups),
            "needs_review_questions": sum(1 for question in questions if question.get("needs_review")),
        },
    }


def repair_missing_questions(subject, questions):
    if subject != "math":
        return questions

    by_number = {question["number"]: question for question in questions}
    repaired = []

    for number in range(1, EXPECTED_MAX_QUESTION["math"] + 1):
        question = by_number.get(number)
        if question:
            repaired.append(question)
            continue

        previous = by_number.get(number - 1)
        next_question = by_number.get(number + 1)
        if not previous:
            continue

        split = split_math_missing_question(number, previous)
        if split:
            previous["text"] = split["previous_text"]
            previous["needs_review"] = True
            previous["review_reason"] = "previous question was split to recover an OCR-missed question number"
            repaired[-1] = previous
            repaired.append(
                make_question_from_text(
                    subject,
                    number,
                    split["missing_text"],
                    previous.get("source_pages") or (next_question or {}).get("source_pages"),
                    needs_review=True,
                    reason="question number/header was missed by OCR; recovered from surrounding lines",
                )
            )

    return repaired


def split_math_missing_question(missing_number, previous):
    lines = [line for line in previous["text"].splitlines() if line.strip()]
    if missing_number == 8:
        # Page 2 OCR missed the line starting with "8."; after q7's D option, the next
        # paragraph is the full q8 body.
        for index, line in enumerate(lines):
            if re.match(r"^\(?D\)?[.．、]?\s*40°", line):
                if index + 1 < len(lines):
                    recovered_prefix = (
                        "8. 如图，在平面直角坐标系 xOy 中，一次函数 y=ax+3 的图象"
                        "与函数 y=2/x (x>0) 的图象"
                    )
                    return {
                        "previous_text": "\n".join(lines[: index + 1]),
                        "missing_text": "\n".join([recovered_prefix, *lines[index + 1 :]]),
                    }

    if missing_number == 11:
        # OCR kept q10's one-line factorisation item, then only captured the tail of q11.
        if lines and lines[0].startswith("10.") and len(lines) > 1:
            return {
                "previous_text": lines[0],
                "missing_text": "11. 方程 2/(x+3) = 1/x 的解为____.",
            }

    return None


def main():
    args = parse_args()
    base_dir = Path(args.base_dir)
    subjects = [item.strip() for item in args.subjects.split(",") if item.strip()]

    for subject in subjects:
        subject_dir = base_dir / "processed" / subject
        rows = load_lines(subject_dir)
        draft = segment_subject(subject, rows)
        out_path = subject_dir / "questions.draft.json"
        out_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stats = draft["stats"]
        print(
            f"[{subject}] questions={stats['questions']} "
            f"passage_groups={stats['passage_groups']} blocks={stats['blocks']}"
        )


if __name__ == "__main__":
    main()
