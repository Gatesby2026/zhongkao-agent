#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SUBJECTS = ["chinese", "math", "physics", "english", "daofa"]
ALIYUN_SUBJECT = {
    "chinese": "JHighSchool_Chinese",
    "math": "JHighSchool_Math",
    "physics": "JHighSchool_Physics",
    "english": "JHighSchool_English",
    "daofa": "JHighSchool_Politics",
}
QWEN_MODEL = "qwen-vl-ocr-latest"
QWEN_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def parse_args():
    parser = argparse.ArgumentParser(description="Run cloud OCR for exam paper images by URL.")
    parser.add_argument("--url-dir", required=True, help="Directory containing <subject>.urls files.")
    parser.add_argument("--out-dir", required=True, help="Output directory for cloud OCR artifacts.")
    parser.add_argument("--subjects", default=",".join(SUBJECTS))
    parser.add_argument("--engines", default="qwen,aliyun-ocr,aliyun-cut")
    parser.add_argument("--profile", default="wmj", help="Aliyun CLI profile.")
    parser.add_argument("--region", default="cn-shanghai", help="Aliyun CLI region.")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.25)
    return parser.parse_args()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_urls(url_dir, subject):
    path = Path(url_dir) / f"{subject}.urls"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def qwen_prompt(subject, page):
    common = (
        "你是中考试卷 OCR 引擎。请逐字识别这页试卷。严格要求：\n"
        "1. 保留题号、选项、文章/材料标题、表格、答案评分参考等结构。\n"
        "2. 不要改写题面，不要补答案，不要把题号重新编号。\n"
        "3. 公式用行内 LaTeX；表格可用 Markdown 表格；图片/图形用 [图] 占位。\n"
        "4. 输出 JSON：{\"page\":%d,\"subject\":\"%s\",\"text\":\"完整OCR文本\","
        "\"key_items\":[{\"type\":\"phonetic|formula|table|figure|uncertain\","
        "\"text\":\"关键内容\",\"context\":\"上下文\"}],\"uncertain_notes\":[]}。\n"
    ) % (page, subject)
    if subject == "chinese":
        return (
            common
            + "特别注意：语文试卷会考查错误注音。必须保留汉字后的拼音注音和声调；"
            "如果图片里注音是错误的，也必须照原样输出。"
        )
    if subject == "math":
        return common + "特别注意：数学公式、分式、函数解析式、几何图形标注必须尽量准确。"
    if subject == "english":
        return common + "特别注意：英文阅读文章、匹配题表格、选项和作文提示必须保持原顺序。"
    if subject == "physics":
        return common + "特别注意：单位、实验表格、电路图/光路图标注、选择题选项必须保留。"
    return common + "特别注意：材料题、判断题符号、选择题选项和答案评分参考必须保留。"


def coerce_content_text(content):
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, indent=2)


def qwen_text_from_payload(payload, fallback):
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text
    if isinstance(text, dict):
        nested_text = qwen_text_from_payload(text, "")
        if nested_text.strip():
            payload.setdefault("uncertain_notes", [])
            payload["uncertain_notes"].append("qwen_text_recovered_from_nested_text_payload")
            return nested_text

    chunks = []
    key_items = payload.get("key_items")
    if not key_items and isinstance(text, dict):
        key_items = text.get("key_items")
    for item in key_items or []:
        if not isinstance(item, dict):
            continue
        item_text = item.get("text") or item.get("context")
        if isinstance(item_text, str) and item_text.strip():
            chunks.append(item_text.strip())
    if chunks:
        payload.setdefault("uncertain_notes", [])
        payload["uncertain_notes"].append("qwen_text_recovered_from_key_items")
        return "\n\n".join(chunks)
    return fallback


def parse_relaxed_json(body):
    try:
        return json.loads(body)
    except Exception:
        pass
    decoder = json.JSONDecoder()
    try:
        parsed, _ = decoder.raw_decode(body)
        return parsed
    except Exception:
        pass
    trimmed = body.rstrip()
    while trimmed.endswith("}"):
        trimmed = trimmed[:-1].rstrip()
        try:
            return json.loads(trimmed)
        except Exception:
            continue
    raise ValueError("invalid JSON payload")


def recover_text_field_from_loose_json(body):
    match = re.search(r'"text"\s*:\s*"(.*)"\s*\n\s*}\s*$', body, re.S)
    if not match:
        return ""
    text = match.group(1)
    try:
        return json.loads(f'"{text}"')
    except Exception:
        return text.replace(r"\\", "\\").replace(r"\"", '"')


def normalize_qwen_content(content, subject, page):
    content_text = coerce_content_text(content)
    parsed = content if isinstance(content, dict) else None
    body = FENCE_RE.sub("", content_text.strip()).strip()
    try:
        parsed = parsed or parse_relaxed_json(body)
        if isinstance(parsed, dict):
            parsed.setdefault("page", page)
            parsed.setdefault("subject", subject)
            parsed.setdefault("text", "")
            parsed.setdefault("key_items", [])
            parsed.setdefault("uncertain_notes", [])
            parsed["text"] = qwen_text_from_payload(parsed, content_text)
            return parsed
    except Exception:
        recovered = recover_text_field_from_loose_json(body)
        if recovered.strip():
            return {
                "page": page,
                "subject": subject,
                "text": recovered,
                "key_items": [],
                "uncertain_notes": ["qwen_text_recovered_from_loose_json"],
            }
    return {
        "page": page,
        "subject": subject,
        "text": content_text,
        "key_items": [],
        "uncertain_notes": ["qwen_json_parse_failed"],
    }


def run_qwen(api_key, subject, page, url, out_dir):
    raw_path = out_dir / "qwen" / f"page-{page:02d}.json"
    txt_path = out_dir / "qwen" / f"page-{page:02d}.txt"
    norm_path = out_dir / "qwen" / f"page-{page:02d}.normalized.json"
    extracted_path = out_dir / "qwen" / f"page-{page:02d}.extracted.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": qwen_prompt(subject, page)},
                ],
            }
        ],
        "max_tokens": 4096,
        "temperature": 0,
    }
    req = urllib.request.Request(
        QWEN_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
    content_text = coerce_content_text(content)
    normalized = normalize_qwen_content(content, subject, page)
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    txt_path.write_text(content_text, encoding="utf-8")
    norm_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    extracted_path.write_text(normalized.get("text", content_text), encoding="utf-8")
    return {"ok": True, "chars": len(normalized.get("text", "")), "request_id": raw.get("id") or raw.get("request_id")}


def run_aliyun(engine, subject, page, url, out_dir, profile, region):
    action = "recognize-edu-paper-ocr" if engine == "aliyun-ocr" else "recognize-edu-paper-cut"
    raw_path = out_dir / engine / f"page-{page:02d}.json"
    txt_path = out_dir / engine / f"page-{page:02d}.txt"
    norm_path = out_dir / engine / f"page-{page:02d}.normalized.json"
    err_path = out_dir / engine / f"page-{page:02d}.error.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "aliyun",
        "ocr-api",
        action,
        "--image-type",
        "scan",
        "--subject",
        ALIYUN_SUBJECT[subject],
        "--output-oricoord",
        "true",
        "--url",
        url,
        "--profile",
        profile,
        "--region",
        region,
    ]
    if engine == "aliyun-cut":
        cmd.insert(cmd.index("--image-type"), "question")
        cmd.insert(cmd.index("question"), "--cut-type")

    result = subprocess.run(cmd, text=True, capture_output=True, timeout=90)
    if result.returncode != 0:
        err_path.write_text(result.stderr + result.stdout, encoding="utf-8")
        return {"ok": False, "error": (result.stderr or result.stdout).splitlines()[:4]}

    raw_path.write_text(result.stdout, encoding="utf-8")
    outer = json.loads(result.stdout)
    data = json.loads(outer["Data"]) if isinstance(outer.get("Data"), str) else outer.get("Data", {})
    norm_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if engine == "aliyun-ocr":
        text = data.get("content", "")
    else:
        chunks = []
        for page_payload in data.get("page_list", []):
            for item in page_payload.get("subject_list", []):
                ids = ",".join(item.get("ids") or [])
                words = "".join(word.get("word", "") for word in item.get("prism_wordsInfo", []))
                chunks.append(f"[{ids}] {words}".strip())
        text = "\n\n".join(chunks)
    txt_path.write_text(text, encoding="utf-8")
    return {"ok": True, "chars": len(text), "request_id": outer.get("RequestId")}


def main():
    args = parse_args()
    subjects = [item.strip() for item in args.subjects.split(",") if item.strip()]
    engines = [item.strip() for item in args.engines.split(",") if item.strip()]
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if "qwen" in engines and not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is required for qwen engine")

    out_root = Path(args.out_dir)
    manifest = {
        "generated_at": now_iso(),
        "url_dir": str(args.url_dir),
        "subjects": {},
        "engines": engines,
    }
    for subject in subjects:
        urls = load_urls(args.url_dir, subject)
        subject_dir = out_root / subject
        manifest["subjects"][subject] = {"pages": len(urls), "results": []}
        for page, url in enumerate(urls, 1):
            for engine in engines:
                if args.skip_existing:
                    expected = subject_dir / engine / f"page-{page:02d}.json"
                    if expected.exists():
                        continue
                try:
                    if engine == "qwen":
                        result = run_qwen(api_key, subject, page, url, subject_dir)
                    elif engine in {"aliyun-ocr", "aliyun-cut"}:
                        result = run_aliyun(engine, subject, page, url, subject_dir, args.profile, args.region)
                    else:
                        raise ValueError(f"unknown engine: {engine}")
                except Exception as exc:
                    result = {"ok": False, "error": repr(exc)}
                    err_dir = subject_dir / engine
                    err_dir.mkdir(parents=True, exist_ok=True)
                    (err_dir / f"page-{page:02d}.error.txt").write_text(repr(exc), encoding="utf-8")
                record = {"subject": subject, "page": page, "engine": engine, **result}
                manifest["subjects"][subject]["results"].append(record)
                print(json.dumps(record, ensure_ascii=False))
                time.sleep(args.sleep)
    (out_root / "cloud-ocr-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
