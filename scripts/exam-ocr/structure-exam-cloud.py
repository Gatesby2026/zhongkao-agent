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
PAPER_PAGES = {
    "chinese": 10,
    "math": 8,
    "physics": 8,
    "english": 10,
    "daofa": 8,
}
ANSWER_RE = re.compile(r"答案|评分参考|参考答案")
FOOTER_RE = re.compile(r"(?:九年级|北京市)?[^\n。；;]{0,30}试卷\s*第\s*\d+\s*页[（(]共\s*\d+\s*页[）)]")
FENCE_RE = re.compile(r"^```(?:json|text|markdown)?\s*|\s*```$", re.S)
QUESTION_MARKER_RE = re.compile(r"(?m)(?<![\d.])(?:^|\n|\s)(?:\[\d+(?:,\d+)*\]\s*)?(\d{1,2})[.．、]\s*(?=[\u4e00-\u9fffA-Za-z0-9_(（_“\"'\\-])")
OPTION_RE = re.compile(r"(?m)(?:^|\s)([A-D])[.．、]\s*")


def parse_args():
    parser = argparse.ArgumentParser(description="Build structured exam docs from cloud OCR artifacts.")
    parser.add_argument("--cloud-dir", required=True, help="Directory produced by cloud-ocr-exam.py.")
    parser.add_argument("--out-dir", required=True, help="Directory for structured outputs.")
    parser.add_argument("--subjects", default=",".join(SUBJECTS))
    return parser.parse_args()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(text):
    text = FENCE_RE.sub("", text.strip()).strip()
    footer = FOOTER_RE.search(text)
    if footer:
        text = text[:footer.start()]
    text = re.sub(r"(?m)^\[\d+(?:,\d+)*\]\s*", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def trim_to_exam_body(text):
    section = re.search(r"[一二三四五六七八九十]、", text)
    question = QUESTION_MARKER_RE.search("\n" + text)
    if section and (not question or section.start() < max(0, question.start() - 1)):
        return text[section.start():]
    return text


def is_suspicious_qwen(text, subject):
    if not text.strip():
        return True
    if text.lstrip().startswith("```json"):
        return True
    markers = [int(item) for item in re.findall(r"(?m)^(\d{1,3})[.．、]\s*", text)]
    if markers and max(markers) > EXPECTED_MAX[subject] + 10:
        return True
    repeated_lines = len(re.findall(r"扩散现象表明分子在不停地做无规则运动", text))
    if repeated_lines > 2:
        return True
    return False


def load_engine_texts(cloud_dir, subject, page):
    subject_dir = Path(cloud_dir) / subject
    candidates = [
        ("qwen-vl-ocr-latest", read_text(subject_dir / "qwen" / f"page-{page:02d}.extracted.txt")),
        ("aliyun-education-cut", read_text(subject_dir / "aliyun-cut" / f"page-{page:02d}.txt")),
        ("aliyun-education-ocr", read_text(subject_dir / "aliyun-ocr" / f"page-{page:02d}.txt")),
    ]
    texts = []
    for engine, text in candidates:
        text = clean_text(text)
        if not text:
            continue
        if engine == "qwen-vl-ocr-latest" and is_suspicious_qwen(text, subject):
            continue
        texts.append((engine, text))
    return texts


def load_page_text(cloud_dir, subject, page):
    texts = load_engine_texts(cloud_dir, subject, page)
    if texts:
        engine, text = texts[0]
        return text, engine
    return "", "missing"


def page_count(cloud_dir, subject):
    subject_dir = Path(cloud_dir) / subject
    pages = set()
    for engine in ["qwen", "aliyun-ocr", "aliyun-cut"]:
        for path in (subject_dir / engine).glob("page-*.txt"):
            match = re.search(r"page-(\d+)", path.name)
            if match:
                pages.add(int(match.group(1)))
    return max(pages) if pages else 0


def split_questions(page_text):
    page_text = trim_to_exam_body(page_text)
    matches = list(QUESTION_MARKER_RE.finditer("\n" + page_text))
    chunks = []
    for idx, match in enumerate(matches):
        number = int(match.group(1))
        start = match.start(1)
        end = matches[idx + 1].start(1) if idx + 1 < len(matches) else len(page_text) + 1
        chunk = ("\n" + page_text)[start:end].strip()
        chunks.append((number, clean_text(chunk)))
    return chunks


def infer_type(subject, number, text):
    if subject == "math":
        if number <= 8:
            return "choice"
        if number <= 16:
            return "fill_blank"
        return "solution"
    if subject == "english":
        if number <= 33:
            return "choice"
        if number <= 37:
            return "reading_response"
        return "writing"
    if subject == "chinese":
        if number == 27:
            return "writing"
        if OPTION_RE.search(text):
            return "choice"
        return "short_response"
    if subject == "physics":
        return "choice" if number <= 15 else "experiment_or_calculation"
    if subject == "daofa":
        if number <= 10:
            return "judgement"
        if number <= 20:
            return "choice"
        return "short_response"
    return "question"


def parse_options(text):
    matches = list(OPTION_RE.finditer(text))
    options = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        option_text = text[match.end():end].strip()
        if option_text:
            options.append({"label": match.group(1), "text": option_text})
    return options


def build_questions(cloud_dir, subject):
    expected = EXPECTED_MAX[subject]
    by_number = {}
    duplicates = []
    pages = []
    for page in range(1, page_count(cloud_dir, subject) + 1):
        engine_texts = load_engine_texts(cloud_dir, subject, page)
        if not engine_texts:
            pages.append({"page": page, "engine": "missing", "chars": 0, "skipped": True})
            continue
        primary_engine, primary_text = engine_texts[0]
        is_answer_page = page > PAPER_PAGES[subject] or bool(re.search(r"答案及评分参考|参考答案|评分参考", primary_text[:500]))
        pages.append({
            "page": page,
            "engine": primary_engine,
            "available_engines": [engine for engine, _ in engine_texts],
            "chars": len(primary_text),
            "answer_page": is_answer_page,
        })
        if is_answer_page:
            continue
        for engine, text in engine_texts:
            for number, chunk in split_questions(text):
                if number < 1 or number > expected:
                    continue
                if number in by_number:
                    if by_number[number]["source_page"] != page:
                        duplicates.append({"number": number, "existing_page": by_number[number]["source_page"], "duplicate_page": page})
                    current_rank = 0 if by_number[number]["provenance"]["primary"] == "qwen-vl-ocr-latest" else 1
                    new_rank = 0 if engine == "qwen-vl-ocr-latest" else 1
                    if new_rank > current_rank or (new_rank == current_rank and len(chunk) <= len(by_number[number]["text"])):
                        continue
                by_number[number] = {
                    "id": f"{subject}-q{number:02d}",
                    "number": number,
                    "type": infer_type(subject, number, chunk),
                    "text": chunk,
                    "options": parse_options(chunk),
                    "source_page": page,
                    "provenance": {"primary": engine, "cloud_ocr_page": f"page-{page:02d}"},
                }
    questions = [by_number[number] for number in sorted(by_number)]
    return questions, duplicates, pages


def critical_checks(subject, questions, page_texts):
    joined = "\n\n".join(page_texts)
    checks = []
    if subject == "chinese":
        checks.append({
            "id": "chinese-phonetic-chuli",
            "ok": bool(re.search(r"矗[（(]\s*zh[ùu]\s*[）)]", joined, re.I)),
            "detail": "检查 page 1 是否保留“矗（zhù）”这个错误注音陷阱。",
        })
        q3 = next((q for q in questions if q["number"] == 3), None)
        checks.append({
            "id": "chinese-q3-options",
            "ok": bool(q3 and all(item in q3["text"] for item in ["矗立", "登载", "赫然", "汲取"])),
            "detail": "检查语文第 3 题四个选项是否完整。",
        })
    if subject == "math":
        q8 = next((q for q in questions if q["number"] == 8), None)
        q11 = next((q for q in questions if q["number"] == 11), None)
        q11_compact = re.sub(r"\s+", "", q11["text"]) if q11 else ""
        checks.append({
            "id": "math-q8-formula",
            "ok": bool(q8 and "y = ax + 3" in q8["text"] and ("\\frac{2}{x}" in q8["text"] or "2/x" in q8["text"])),
            "detail": "检查数学第 8 题 y=ax+3 与 2/x 是否保留。",
        })
        checks.append({
            "id": "math-q11-formula",
            "ok": bool(q11 and ("\\frac{2}{x+3}" in q11_compact or "2/(x+3)" in q11_compact) and ("\\frac{1}{x}" in q11_compact or "1/x" in q11_compact)),
            "detail": "检查数学第 11 题两个反比例函数表达式。",
        })
    if subject == "english":
        present = {q["number"]: q for q in questions}
        checks.append({
            "id": "english-21-23-separated",
            "ok": all(num in present for num in [21, 22, 23]) and "Lingling" in present.get(22, {}).get("text", ""),
            "detail": "检查英语 21-23 匹配题是否拆开，且第 22 题含 Lingling。",
        })
    return checks


def apply_subject_repairs(subject, questions, page_texts):
    if subject == "chinese" and any(re.search(r"矗[（(]\s*zh[ùu]\s*[）)]", text, re.I) for text in page_texts):
        q3 = next((q for q in questions if q["number"] == 3), None)
        if q3:
            q3["text"] = re.sub(r"[盗盘][立]", "矗立", q3["text"])
            q3["provenance"]["critical_repair"] = "page-01 preserved 矗（zhù）; repaired q3 option text."
    return questions


def recover_missing_questions(cloud_dir, subject, questions):
    present = {q["number"] for q in questions}
    expected = EXPECTED_MAX[subject]
    for number in range(1, expected + 1):
        if number in present:
            continue
        marker = re.compile(rf"(?<!\d){number}[.．、]\s*(?=[\u4e00-\u9fffA-Za-z0-9_(（_“\"'\\-])")
        next_marker = re.compile(rf"(?<!\d){number + 1}[.．、]\s*(?=[\u4e00-\u9fffA-Za-z0-9_(（_“\"'\\-])") if number < expected else None
        for page in range(1, PAPER_PAGES[subject] + 1):
            for engine, text in load_engine_texts(cloud_dir, subject, page):
                match = marker.search(text)
                if not match:
                    continue
                end_match = next_marker.search(text, match.end()) if next_marker else None
                chunk = clean_text(text[match.start(): end_match.start() if end_match else len(text)])
                if len(chunk) < 20:
                    continue
                questions.append({
                    "id": f"{subject}-q{number:02d}",
                    "number": number,
                    "type": infer_type(subject, number, chunk),
                    "text": chunk,
                    "options": parse_options(chunk),
                    "source_page": page,
                    "provenance": {
                        "primary": engine,
                        "cloud_ocr_page": f"page-{page:02d}",
                        "recovery": "loose inline marker recovery",
                    },
                })
                present.add(number)
                break
            if number in present:
                break
    return sorted(questions, key=lambda item: item["number"])


def build_subject(cloud_dir, out_root, subject):
    questions, duplicates, pages = build_questions(cloud_dir, subject)
    all_page_texts = [load_page_text(cloud_dir, subject, page)[0] for page in range(1, page_count(cloud_dir, subject) + 1)]
    expected = EXPECTED_MAX[subject]
    questions = recover_missing_questions(cloud_dir, subject, questions)
    questions = apply_subject_repairs(subject, questions, all_page_texts)
    numbers = [q["number"] for q in questions]
    missing = [num for num in range(1, expected + 1) if num not in numbers]
    checks = critical_checks(subject, questions, all_page_texts)
    report = {
        "subject": subject,
        "expected_questions": expected,
        "question_count": len(questions),
        "missing_numbers": missing,
        "duplicates": duplicates,
        "critical_checks": checks,
        "passed": not missing and all(item["ok"] for item in checks),
        "pages": pages,
    }
    payload = {
        "exam": "2026 北京朝阳区中考一模",
        "subject": subject,
        "subject_label": SUBJECT_LABELS[subject],
        "generated_at": now_iso(),
        "method": {
            "primary": "Qwen OCR full-paper page text",
            "cross_check": ["Aliyun Education OCR", "Aliyun Education Cut"],
            "fallback_policy": "Use Aliyun Education OCR when Qwen output is empty, fenced/malformed, or visibly hallucinated.",
            "paddleocr": "not used in default cloud-first path",
        },
        "questions": questions,
        "validation": report,
    }
    subject_out = out_root / subject / "structured-cloud"
    write_json(subject_out / "final.json", payload)
    write_json(subject_out / "validation-report.json", report)
    write_markdown(subject_out / "final.md", payload)
    return report


def write_markdown(path, payload):
    lines = [
        f"# {payload['exam']} {payload['subject_label']}",
        "",
        f"- method: {payload['method']['primary']} + Aliyun cross-check",
        f"- validation_passed: {payload['validation']['passed']}",
        f"- question_count: {payload['validation']['question_count']}/{payload['validation']['expected_questions']}",
        "",
    ]
    for question in payload["questions"]:
        lines.append(f"## {question['number']}. {question['type']}")
        lines.append("")
        lines.append(question["text"])
        lines.append("")
        lines.append(f"_source: {question['provenance']['primary']} {question['provenance']['cloud_ocr_page']}_")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    args = parse_args()
    subjects = [item.strip() for item in args.subjects.split(",") if item.strip()]
    out_root = Path(args.out_dir)
    reports = []
    for subject in subjects:
        reports.append(build_subject(args.cloud_dir, out_root, subject))
    write_json(out_root / "structured-cloud-index.json", {"generated_at": now_iso(), "reports": reports})
    print(json.dumps({"subjects": len(reports), "passed": all(report["passed"] for report in reports)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
