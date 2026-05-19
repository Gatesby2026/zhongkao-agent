#!/usr/bin/env python3
"""mock-exam slug → 完整试卷 PDF（含答案页，原卷扫描 100% 保真）。

供小程序下载链接用。gaokzx 抓到的 page-*.png 本身已包含答案页（参考答案与评分标准），
所以一份 PDF 足够。

用法：
    # 单卷
    python3 mock_exam_to_pdf.py knowledge-base/exams/mock/physics/beijing/2026-chaoyang-yi.yaml

    # 批量
    python3 mock_exam_to_pdf.py --all --out-dir out/papers

输出：
    out/papers/<slug>.pdf
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml
from PIL import Image


def derive_images_dir(slug: str) -> Path:
    """`2026-chaoyang-yi-physics` → knowledge-original/.../images/。"""
    m = re.match(r"(\d{4})-([a-z]+)-(yi|er|san)-([a-z]+)$", slug)
    if not m:
        raise ValueError(f"slug 格式不对: {slug}")
    year, district, exam, subject = m.groups()
    folder = {"yi": "yimo", "er": "ermo", "san": "sanmo"}[exam]
    return Path("knowledge-original") / f"beijing-mock-{year}" / folder / district / subject / "images"


def stitch_paper_pdf(images_dir: Path, out_pdf: Path) -> int:
    """page-*.png 顺序拼为 PDF，每页一张图。"""
    pages = sorted(images_dir.glob("page-*.png"))
    if not pages:
        raise FileNotFoundError(f"无 page-*.png: {images_dir}")

    imgs = []
    for p in pages:
        im = Image.open(p)
        if im.mode != "RGB":
            im = im.convert("RGB")
        imgs.append(im)

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(
        out_pdf, "PDF", resolution=150.0,
        save_all=True, append_images=imgs[1:],
    )
    return len(pages)


def process_yaml(yaml_path: Path, out_dir: Path):
    slug = yaml_path.stem
    images_dir = derive_images_dir(slug)
    out_pdf = out_dir / f"{slug}.pdf"
    n = stitch_paper_pdf(images_dir, out_pdf)
    print(f"  ✅ {out_pdf} ({n}页, {out_pdf.stat().st_size//1024}KB)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("yaml_path", type=Path, nargs="?")
    p.add_argument("--all", action="store_true",
                   help="批量处理 knowledge-base/exams/mock/ 下所有 2026 一模 YAML")
    p.add_argument("--out-dir", type=Path, default=Path("out/papers"))
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        yamls = sorted(Path("knowledge-base/exams/mock").rglob("2026-*-yi*.yaml"))
        print(f"📦 found {len(yamls)} YAMLs")
        ok, fail = 0, 0
        for y in yamls:
            try:
                process_yaml(y, args.out_dir)
                ok += 1
            except Exception as e:
                print(f"  ❌ {y.stem}: {e}", file=sys.stderr)
                fail += 1
        print(f"\n📊 done: {ok} ok / {fail} failed")
    else:
        if not args.yaml_path:
            p.error("provide YAML or --all")
        process_yaml(args.yaml_path, args.out_dir)


if __name__ == "__main__":
    main()
