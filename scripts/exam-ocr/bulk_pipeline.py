#!/usr/bin/env python3
"""批量端到端流水线：试卷扫描 + 已有 OCR 工具 + LLM enrich → mock-exam YAML。

6 步：
  1. 抓取试卷扫描页（gaokzx adapter）—— 待写，目前手工提供 URL
  2. OCR 试卷题目（exam-ocr.cloud-ocr-exam.py 或现有 final.json）
  3. final.json → paper.json（final_to_paper.py）
  4. 答案页 OCR + 抽取（extract_answer_key.py）
  5. LLM enrich（enrich_to_mock_exam.py）
  6. 入库 knowledge-base/mock-exams/<科目>/beijing/

Manifest 格式（JSON）：
[
  {
    "exam_slug": "2026-chaoyang-yi-physics",
    "subject": "物理",
    "subject_en": "physics",
    "exam_meta": {"city":"北京","district":"朝阳","grade":"初三",
                  "examType":"一模","year":2026,"subject":"物理"},
    "paper_pages_dir": "/abs/path/to/page-*.png",
    "paper_final_json": "/abs/path/to/structured-cloud/final.json"
  },
  ...
]

每条 job 跑完产出：
  knowledge-base/mock-exams/<subject_en>/beijing/<exam_slug>.yaml

幂等：每步都有缓存，重跑只补缺失。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "exam-ocr"))
sys.path.insert(0, str(ROOT / "scripts" / "knowledge-base"))

import final_to_paper  # noqa: E402
import extract_answer_key  # noqa: E402
import enrich_to_mock_exam  # noqa: E402


SUBJECT_EN = {
    "物理": "physics",
    "数学": "math",
    "语文": "chinese",
    "英语": "english",
    "道法": "politics",
}


def run_job(job: dict, data_dir: Path, kb_dir: Path, dry_run: bool = False):
    """对一份 job（一份试卷）跑完整 6 步流水线。"""
    slug = job["exam_slug"]
    subject = job["subject"]
    subject_en = job.get("subject_en") or SUBJECT_EN.get(subject, subject)
    exam_meta = job.get("exam_meta", {})

    print(f"\n{'='*60}")
    print(f"📋 JOB: {slug}（{subject}）")
    print(f"{'='*60}")

    # L2 缓存目录
    work_dir = data_dir / slug
    work_dir.mkdir(parents=True, exist_ok=True)

    # === Step 1+2: 找试卷扫描 + OCR ===
    # 暂时跳过自动下载和 OCR：要求 job 已提供 paper_final_json
    final_json_path = Path(job["paper_final_json"])
    paper_pages = sorted(Path(job["paper_pages_dir"]).glob("page-*.png"))
    if not final_json_path.exists():
        raise FileNotFoundError(f"待开发 step 1+2，目前需提供已有 final.json: {final_json_path}")
    print(f"📄 final.json: {final_json_path.relative_to(ROOT) if final_json_path.is_relative_to(ROOT) else final_json_path}")
    print(f"📷 paper pages: {len(paper_pages)} 张")

    # === Step 3: final.json → paper.json ===
    paper_path = work_dir / "paper.json"
    if paper_path.exists():
        print(f"⏭  step 3 缓存命中：{paper_path.relative_to(ROOT)}")
    else:
        print(f"🔧 step 3: final.json → paper.json")
        if not dry_run:
            final = json.loads(final_json_path.read_text(encoding="utf-8"))
            paper = final_to_paper.convert_final_to_paper(
                final, subject=subject_en, exam_meta=exam_meta,
            )
            paper_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            print(f"   → {paper_path.relative_to(ROOT)}（{paper['meta']['questionCount']} 题）")

    # === Step 4: 答案抽取 ===
    answer_key_path = work_dir / "answer-key.json"
    if answer_key_path.exists():
        print(f"⏭  step 4 缓存命中：{answer_key_path.relative_to(ROOT)}")
    else:
        print(f"🔧 step 4: 答案页 OCR + 抽取 → answer-key.json")
        if not dry_run:
            extract_answer_key.extract_answer_key(
                paper_path=paper_path,
                page_images=paper_pages,
                output_path=answer_key_path,
            )

    # === Step 5: enrich → mock-exam YAML ===
    mock_yaml = kb_dir / "mock-exams" / subject_en / "beijing" / f"{slug}.yaml"
    if mock_yaml.exists():
        print(f"⏭  step 5 缓存命中：{mock_yaml.relative_to(ROOT)}")
        return mock_yaml
    print(f"🔧 step 5: LLM enrich → mock-exam YAML")
    if dry_run:
        print(f"   (dry-run，会输出到 {mock_yaml.relative_to(ROOT)})")
        return mock_yaml

    paper = json.loads(paper_path.read_text(encoding="utf-8"))
    answer_key = json.loads(answer_key_path.read_text(encoding="utf-8"))
    result = enrich_to_mock_exam.enrich_to_mock_exam(
        paper=paper, answer_key=answer_key,
        exam_meta=exam_meta, subject=subject,
        cache_prefix=slug,
    )

    mock_yaml.parent.mkdir(parents=True, exist_ok=True)
    import yaml as yaml_mod
    with mock_yaml.open("w", encoding="utf-8") as f:
        f.write(f"# ============================================================\n")
        f.write(f"# {result['year']}年北京{result['district']}{result['exam_type']}{result['subject']} — 自动生成\n")
        f.write(f"# ============================================================\n")
        f.write(f"# 流水线：gaokzx OCR + Qwen-VL-OCR + qwen-max enrich\n")
        f.write(f"# 满分: {result['full_score']} 分 时长: {result['duration_minutes']} 分钟\n\n")
        yaml_mod.safe_dump(result, f, allow_unicode=True, sort_keys=False, width=200)
    print(f"   → {mock_yaml.relative_to(ROOT)}")
    print(f"   {result['total_questions']} 题, {result['structure']}")
    return mock_yaml


def main():
    parser = argparse.ArgumentParser(description="批量端到端 mock-exam 生成")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="JSON list of jobs")
    parser.add_argument("--data-dir", type=Path,
                        default=ROOT / "data" / "exams",
                        help="L2 缓存目录")
    parser.add_argument("--kb-dir", type=Path,
                        default=ROOT / "knowledge-base",
                        help="L4 knowledge-base 根")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", help="只跑某个 exam_slug")
    args = parser.parse_args()

    jobs = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.only:
        jobs = [j for j in jobs if j["exam_slug"] == args.only]

    print(f"📦 manifest: {len(jobs)} jobs")
    args.data_dir.mkdir(parents=True, exist_ok=True)

    succeeded, failed = [], []
    for job in jobs:
        try:
            mock_yaml = run_job(job, args.data_dir, args.kb_dir, dry_run=args.dry_run)
            succeeded.append((job["exam_slug"], mock_yaml))
        except Exception as e:
            print(f"❌ {job['exam_slug']} 失败: {type(e).__name__}: {e}", file=sys.stderr)
            failed.append((job["exam_slug"], str(e)))

    print(f"\n{'='*60}")
    print(f"📊 总结: 成功 {len(succeeded)}, 失败 {len(failed)}")
    for slug, _ in succeeded:
        print(f"  ✅ {slug}")
    for slug, err in failed:
        print(f"  ❌ {slug}: {err[:100]}")


if __name__ == "__main__":
    main()
