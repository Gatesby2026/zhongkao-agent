#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from urllib.error import HTTPError
from pathlib import Path


QWEN_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def parse_args():
    parser = argparse.ArgumentParser(description="Run DashScope Qwen OCR on answer-card images through temporary OSS URLs.")
    parser.add_argument("images", nargs="+", help="Local image files to OCR.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--subject", default="math")
    parser.add_argument("--scope", default="answer-card")
    parser.add_argument("--model", default="qwen-vl-ocr-latest")
    parser.add_argument("--bucket-prefix", default="zhongkao-qwen-answercard")
    parser.add_argument("--oss-endpoint", default="oss-cn-shanghai.aliyuncs.com")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--keep-bucket", action="store_true")
    return parser.parse_args()


def run(cmd):
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout


def make_bucket(bucket, endpoint):
    run(["aliyun", "oss", "mb", f"oss://{bucket}", "--acl", "private", "--endpoint", endpoint])


def upload(local_path, bucket, object_name, endpoint):
    run(["aliyun", "oss", "cp", str(local_path), f"oss://{bucket}/{object_name}", "--endpoint", endpoint])


def sign_url(bucket, object_name, endpoint, timeout):
    raw = run([
        "aliyun",
        "oss",
        "sign",
        f"oss://{bucket}/{object_name}",
        "--timeout",
        str(timeout),
        "--endpoint",
        endpoint,
    ])
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("http"):
            return line
    raise RuntimeError("failed to parse signed URL")


def cleanup(bucket, objects, endpoint):
    for object_name in objects:
        subprocess.run(
            ["aliyun", "oss", "rm", f"oss://{bucket}/{object_name}", "--endpoint", endpoint, "--force"],
            text=True,
            capture_output=True,
            check=False,
        )
    subprocess.run(
        ["aliyun", "oss", "rm", f"oss://{bucket}", "-b", "--endpoint", endpoint, "--force"],
        text=True,
        capture_output=True,
        check=False,
    )


def prompt(subject, scope):
    return f"""你是中考学生答题卡 OCR 与结构化抽取引擎。

任务：识别图片中的学生手写作答内容，而不是抄录印刷题干。当前科目：{subject}。当前图片范围：{scope}。

严格要求：
1. 如果图片是整页或大区块，请先定位选择题、填空题、解答题区域，再抽取学生实际作答。
2. 数学公式保留符号，能标准化则写入 normalized_answer，例如 x>=1、3(a+b)^2、x=3、-10。
3. 不要把印刷题号、题干、横线、栏目标题当成学生答案。
4. 看不清、被遮挡、涂改严重或只靠猜测时，needs_review=true。
5. 输出必须是 JSON，不要 Markdown，不要解释。

JSON 结构：
{{
  "subject": "{subject}",
  "scope": "{scope}",
  "answers": [
    {{
      "number": "题号",
      "subpart": "小问或空号，没有则为空字符串",
      "handwritten_text": "按图像读到的原始手写内容",
      "normalized_answer": "便于后续分析的标准化答案",
      "confidence": 0.0,
      "needs_review": true,
      "evidence": "简短说明依据，例如位于填空题第9题横线上"
    }}
  ],
  "unassigned_handwriting": [],
  "notes": []
}}"""


def coerce_text(content):
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, indent=2)


def parse_json_text(text):
    body = FENCE_RE.sub("", text.strip()).strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            return json.loads(body[start : end + 1])
        raise


def qwen_ocr(api_key, model, image_url, subject, scope, max_tokens):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt(subject, scope)},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        QWEN_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"qwen request failed: HTTP {exc.code}: {body}") from exc
    content = raw["choices"][0]["message"]["content"]
    text = coerce_text(content)
    try:
        parsed = parse_json_text(text)
    except Exception as exc:
        parsed = {
            "subject": subject,
            "scope": scope,
            "answers": [],
            "unassigned_handwriting": [],
            "notes": [f"json_parse_failed: {exc}"],
            "raw_text": text,
        }
    return raw, text, parsed


def main():
    args = parse_args()
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is required")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bucket = f"{args.bucket_prefix}-{int(time.time())}"
    objects = []
    manifest = {"bucket": bucket, "model": args.model, "outputs": [], "cleanup": not args.keep_bucket}
    try:
        make_bucket(bucket, args.oss_endpoint)
        for image in args.images:
            image_path = Path(image)
            stem = image_path.stem
            object_name = f"qwen-answer-card/{stem}-{int(time.time() * 1000)}{image_path.suffix.lower()}"
            objects.append(object_name)
            upload(image_path, bucket, object_name, args.oss_endpoint)
            url = sign_url(bucket, object_name, args.oss_endpoint, args.timeout)
            raw, text, parsed = qwen_ocr(api_key, args.model, url, args.subject, args.scope, args.max_tokens)

            raw_path = out_dir / f"{stem}.qwen-raw.json"
            txt_path = out_dir / f"{stem}.qwen.txt"
            parsed_path = out_dir / f"{stem}.qwen.parsed.json"
            raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            txt_path.write_text(text, encoding="utf-8")
            parsed_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            manifest["outputs"].append({
                "image": str(image_path),
                "raw": str(raw_path),
                "text": str(txt_path),
                "parsed": str(parsed_path),
                "answers": len(parsed.get("answers", [])) if isinstance(parsed, dict) else 0,
                "notes": parsed.get("notes", []) if isinstance(parsed, dict) else [],
            })
    finally:
        if not args.keep_bucket:
            cleanup(bucket, objects, args.oss_endpoint)

    manifest_path = out_dir / "qwen-answer-card-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outputs": len(manifest["outputs"]), "manifest": str(manifest_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
