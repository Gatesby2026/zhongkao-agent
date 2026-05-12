#!/usr/bin/env python3

import argparse
import json
import subprocess
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Run Alibaba Cloud handwriting OCR through temporary private OSS URLs.")
    parser.add_argument("images", nargs="+", help="Local image files to OCR.")
    parser.add_argument("--out-dir", required=True, help="Directory for OCR JSON outputs.")
    parser.add_argument("--bucket-prefix", default="zhongkao-answercard-poc")
    parser.add_argument("--oss-endpoint", default="oss-cn-shanghai.aliyuncs.com")
    parser.add_argument("--ocr-region", default="cn-shanghai")
    parser.add_argument("--timeout", type=int, default=600, help="Signed URL expiry in seconds.")
    parser.add_argument("--keep-bucket", action="store_true", help="Do not delete temporary OSS bucket.")
    return parser.parse_args()


def run(cmd, capture=True):
    result = subprocess.run(cmd, text=True, capture_output=capture, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout if capture else ""


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


def handwriting_ocr(url, region):
    raw = run([
        "aliyun",
        "ocr-api",
        "recognize-handwriting",
        "--url",
        url,
        "--need-rotate",
        "true",
        "--need-sort-page",
        "true",
        "--output-char-info",
        "true",
        "--region",
        region,
    ])
    return json.loads(raw)


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


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bucket = f"{args.bucket_prefix}-{int(time.time())}"
    objects = []
    manifest = {"bucket": bucket, "outputs": [], "cleanup": not args.keep_bucket}
    try:
        make_bucket(bucket, args.oss_endpoint)
        for image in args.images:
            image_path = Path(image)
            object_name = f"handwriting/{image_path.stem}-{int(time.time() * 1000)}{image_path.suffix.lower()}"
            objects.append(object_name)
            upload(image_path, bucket, object_name, args.oss_endpoint)
            url = sign_url(bucket, object_name, args.oss_endpoint, args.timeout)
            result = handwriting_ocr(url, args.ocr_region)
            output_path = out_dir / f"{image_path.stem}.aliyun-handwriting.json"
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            data = result.get("Data")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    data = {}
            manifest["outputs"].append({
                "image": str(image_path),
                "output": str(output_path),
                "content": data.get("content") if isinstance(data, dict) else None,
            })
    finally:
        if not args.keep_bucket:
            cleanup(bucket, objects, args.oss_endpoint)
    (out_dir / "aliyun-handwriting-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"bucket": bucket, "outputs": len(manifest["outputs"]), "cleanup": not args.keep_bucket}, ensure_ascii=False))


if __name__ == "__main__":
    main()
