#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from paddleocr import PaddleOCR


DEFAULT_SUBJECTS = ["chinese", "math", "physics", "english", "daofa"]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args():
    parser = argparse.ArgumentParser(description="Run PaddleOCR over exam page images.")
    parser.add_argument(
        "--base-dir",
        default="data/chaoyang-2026-yimo",
        help="Exam artifact directory containing <subject>-images folders.",
    )
    parser.add_argument(
        "--subjects",
        default=",".join(DEFAULT_SUBJECTS),
        help="Comma-separated subjects to process.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing page OCR JSON files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional per-subject page limit for sampling.",
    )
    return parser.parse_args()


def image_pages(image_dir: Path):
    return [
        path
        for path in sorted(image_dir.iterdir())
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    ]


def run_page(ocr: PaddleOCR, subject: str, image_path: Path, page_index: int):
    result = ocr.ocr(str(image_path), cls=False)[0] or []
    lines = []

    for index, line in enumerate(result, start=1):
        box, (text, score) = line
        lines.append(
            {
                "index": index,
                "text": text,
                "confidence": float(score),
                "box": [[float(x), float(y)] for x, y in box],
            }
        )

    return {
        "subject": subject,
        "page": page_index,
        "source_image": str(image_path),
        "engine": "PaddleOCR 2.7.3 / PP-OCRv4 ch",
        "lines": lines,
    }


def write_page_outputs(page_payload: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    page_no = page_payload["page"]
    json_path = out_dir / f"page-{page_no:02d}.ocr.json"
    txt_path = out_dir / f"page-{page_no:02d}.txt"

    json_path.write_text(
        json.dumps(page_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    txt_path.write_text(
        "\n".join(line["text"] for line in page_payload["lines"]) + "\n",
        encoding="utf-8",
    )


def rebuild_raw_text(subject_dir: Path):
    page_texts = []
    for txt_path in sorted((subject_dir / "pages").glob("page-*.txt")):
        page_no = txt_path.stem.replace(".ocr", "")
        page_texts.append(f"\n\n===== {page_no} =====\n")
        page_texts.append(txt_path.read_text(encoding="utf-8"))

    (subject_dir / "raw.txt").write_text("".join(page_texts).strip() + "\n", encoding="utf-8")


def main():
    args = parse_args()
    base_dir = Path(args.base_dir)
    subjects = [item.strip() for item in args.subjects.split(",") if item.strip()]

    ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)

    for subject in subjects:
        image_dir = base_dir / f"{subject}-images"
        if not image_dir.exists():
            print(f"[{subject}] skip: missing {image_dir}")
            continue

        pages = image_pages(image_dir)
        if args.limit:
            pages = pages[: args.limit]

        subject_dir = base_dir / "processed" / subject
        pages_dir = subject_dir / "pages"
        completed = 0

        for page_index, image_path in enumerate(pages, start=1):
            json_path = pages_dir / f"page-{page_index:02d}.ocr.json"
            if json_path.exists() and not args.force:
                completed += 1
                continue

            payload = run_page(ocr, subject, image_path, page_index)
            write_page_outputs(payload, pages_dir)
            completed += 1

            line_count = len(payload["lines"])
            avg_conf = (
                sum(line["confidence"] for line in payload["lines"]) / line_count
                if line_count
                else 0
            )
            print(f"[{subject}] page-{page_index:02d}: {line_count} lines avg={avg_conf:.3f}")

        rebuild_raw_text(subject_dir)
        print(f"[{subject}] done: {completed}/{len(pages)} pages")


if __name__ == "__main__":
    main()
