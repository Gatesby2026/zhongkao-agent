#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path

from alibabacloud_ocr_api20210707.client import Client as OcrClient
from alibabacloud_ocr_api20210707 import models as ocr_models
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models


def parse_args():
    parser = argparse.ArgumentParser(description="Run Alibaba Cloud OCR and compare with PaddleOCR output.")
    parser.add_argument("--image", required=True, help="Local image path on the server.")
    parser.add_argument("--paddle-json", required=True, help="Existing PaddleOCR page JSON path.")
    parser.add_argument("--out-dir", required=True, help="Directory for Aliyun OCR and comparison artifacts.")
    return parser.parse_args()


def create_client():
    access_key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
    access_key_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    if not access_key_id or not access_key_secret:
        raise RuntimeError("Missing ALIBABA_CLOUD_ACCESS_KEY_ID or ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    config = open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )
    config.endpoint = "ocr-api.cn-hangzhou.aliyuncs.com"
    return OcrClient(config)


def run_aliyun_ocr(image_path: Path):
    client = create_client()
    runtime = util_models.RuntimeOptions()

    with image_path.open("rb") as body:
        request = ocr_models.RecognizeGeneralRequest(body=body)
        response = client.recognize_general_with_options(request, runtime)

    raw = response.body.to_map()
    data = raw.get("Data") or raw.get("data")
    if isinstance(data, str):
        try:
            raw["DataParsed"] = json.loads(data)
        except json.JSONDecodeError:
            raw["DataParsed"] = {"content": data}
    return raw


def normalize_aliyun(raw):
    data = raw.get("DataParsed") or {}
    words = data.get("prism_wordsInfo") or data.get("PrismWordsInfo") or []
    lines = []
    for index, item in enumerate(words, start=1):
        pos = item.get("pos") or item.get("Pos") or []
        prob = item.get("prob") or item.get("Prob")
        lines.append(
            {
                "index": index,
                "text": item.get("word") or item.get("Word") or "",
                "confidence": float(prob) / 100 if prob is not None else None,
                "box": [[point.get("x"), point.get("y")] for point in pos],
            }
        )

    return {
        "engine": "Alibaba Cloud OCR RecognizeGeneral",
        "content": data.get("content") or data.get("Content") or "",
        "width": data.get("width") or data.get("Width"),
        "height": data.get("height") or data.get("Height"),
        "org_width": data.get("orgWidth") or data.get("OrgWidth"),
        "org_height": data.get("orgHeight") or data.get("OrgHeight"),
        "lines": lines,
    }


def load_paddle(paddle_json: Path):
    payload = json.loads(paddle_json.read_text(encoding="utf-8"))
    return {
        "engine": payload.get("engine", "PaddleOCR"),
        "lines": payload["lines"],
        "content": "\n".join(line["text"] for line in payload["lines"]),
    }


def find_terms(content, terms):
    return {term: (term in content) for term in terms}


def compare(paddle, aliyun):
    terms = [
        "7.",
        "8.",
        "一次函数",
        "y=ax+3",
        "y=1/x",
        "9.",
        "10.",
        "11.",
        "2/(x+3)",
        "12.",
    ]
    return {
        "paddle": {
            "line_count": len(paddle["lines"]),
            "avg_confidence": average_confidence(paddle["lines"]),
            "term_hits": find_terms(paddle["content"], terms),
        },
        "aliyun": {
            "line_count": len(aliyun["lines"]),
            "avg_confidence": average_confidence(aliyun["lines"]),
            "term_hits": find_terms(aliyun["content"], terms),
        },
    }


def average_confidence(lines):
    values = [line.get("confidence") for line in lines if line.get("confidence") is not None]
    return round(sum(values) / len(values), 4) if values else None


def main():
    args = parse_args()
    image_path = Path(args.image)
    paddle_json = Path(args.paddle_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = run_aliyun_ocr(image_path)
    aliyun = normalize_aliyun(raw)
    paddle = load_paddle(paddle_json)
    summary = compare(paddle, aliyun)

    (out_dir / "aliyun.raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "aliyun.normalized.json").write_text(
        json.dumps(aliyun, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "aliyun.txt").write_text("\n".join(line["text"] for line in aliyun["lines"]) + "\n", encoding="utf-8")
    (out_dir / "compare-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
