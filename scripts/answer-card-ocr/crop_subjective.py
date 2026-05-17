#!/usr/bin/env python3
"""答题卡主观题作答区裁切（v2：腾讯云 QuestionSplitLayoutOCR）。

流水线（无 vl 像素估算，纯几何 + OCR 文字）：
  1. 腾讯云 QuestionSplitLayoutOCR 直接返回每题方框 bbox（像素级准确）
  2. PIL 按 bbox 裁切
  3. 讯飞手写 OCR 读每框内的印刷题号（"16. (3 分)"）
  4. 按题号命名最终 q{NN}.png

旧 vl-max 估 y% 方案见 git 历史。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("pip install pillow", file=sys.stderr); sys.exit(1)


# 在 .venv-paddle 没装 tencentcloud-sdk-python-ocr 时，把 import 延迟
def _import_tencent():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tencent_split import split_question_regions
    return split_question_regions


def _import_xfyun():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from xfyun_ocr import recognize_handwriting
    return recognize_handwriting


# 题号正则：从 OCR 文本中提取 "16. (3分)" / "16." / "16、" 等
QID_FROM_OCR_RE = re.compile(r"(?:^|\D)(\d{1,2})\s*[.．、)]\s*[\(（]?\s*[0-9一二三四五]?\s*分?\s*[\)）]?")


def _extract_qid_from_ocr_text(text: str, candidate_qnums: set[int]) -> int | None:
    """从 OCR 文本里抓首个出现的合法题号（必须在 candidate 集合内）。"""
    if not text:
        return None
    for m in QID_FROM_OCR_RE.finditer(text):
        n = int(m.group(1))
        if n in candidate_qnums:
            return n
    return None


def crop_subjective(
    photos: list[Path],
    subjective_qnums: list[int],
    out_dir: Path,
    bottom_pad_pct: float = 2.0,
    side_pad_px: int = 8,
) -> dict[int, dict]:
    """对一组答题卡图做主观题区裁切。

    Args:
        photos: 答题卡照片列表
        subjective_qnums: 主观题题号集合（如 [16,17,...,26]）
        out_dir: 裁切图输出目录
        bottom_pad_pct: 每框底部追加 % 高度，吃掉学生答案可能溢出的部分
        side_pad_px: 左右扩张像素（吃掉框边线）

    Returns:
        {qid: {"image_path": "cropped/q{NN}.png", "page_image": ...,
               "bbox": [x1,y1,x2,y2]}}
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    split_fn = _import_tencent()
    recog_hw = _import_xfyun()

    candidate_set = set(subjective_qnums)

    # 1. 每张图调腾讯云拿方框
    page_regions: list[dict] = []  # {orig_path, w, h, regions: [{bbox, y_center}]}
    for p in photos:
        img = Image.open(p)
        w, h = img.size
        print(f"  📐 {p.name} ({w}×{h}) → 腾讯云方框检测 ...", file=sys.stderr)
        try:
            regions = split_fn(p)
            print(f"     找到 {len(regions)} 个方框", file=sys.stderr)
        except Exception as e:
            print(f"     ❌ 腾讯云调用失败: {e}", file=sys.stderr)
            regions = []
        page_regions.append({"orig_path": p, "w": w, "h": h, "regions": regions})

    # 2. 对每个方框裁出临时图 + 调讯飞 OCR 找题号
    print(f"\n  ✍️  讯飞 OCR 识别每框题号 ...", file=sys.stderr)

    region_jobs = []  # [(page_idx, region_idx, region, orig_path)]
    for pi, page in enumerate(page_regions):
        for ri, r in enumerate(page["regions"]):
            region_jobs.append((pi, ri, r, page["orig_path"]))

    def _ocr_qid(job):
        pi, ri, r, orig_path = job
        # 每线程独立打开（PIL 不是线程安全的）
        img = Image.open(orig_path)
        x1, y1, x2, y2 = r["bbox"]
        crop = img.crop((max(0, x1 - side_pad_px), y1,
                          min(img.size[0], x2 + side_pad_px), y2))
        # 临时存盘给讯飞 OCR
        tmp = out_dir / f"_tmp_p{pi}_r{ri}.png"
        crop.save(tmp)
        try:
            res = recog_hw(tmp)
            text = res.get("text", "")
        except Exception as e:
            text = ""
            print(f"     ⚠️ p{pi}r{ri} 讯飞 OCR 失败: {e}", file=sys.stderr)
        qid = _extract_qid_from_ocr_text(text, candidate_set)
        tmp.unlink(missing_ok=True)
        return (pi, ri, qid, text[:50])

    qid_per_region: dict[tuple[int, int], int] = {}
    region_ocr_texts: dict[tuple[int, int], str] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_ocr_qid, job) for job in region_jobs]
        for fut in as_completed(futs):
            pi, ri, qid, preview = fut.result()
            region_ocr_texts[(pi, ri)] = preview
            if qid:
                qid_per_region[(pi, ri)] = qid

    # 3. 同一题号在多框出现时取 y 最小（最先出现）
    best_per_qid: dict[int, tuple[int, int]] = {}
    for (pi, ri), qid in qid_per_region.items():
        y = page_regions[pi]["regions"][ri]["y_center"]
        if qid not in best_per_qid:
            best_per_qid[qid] = (pi, ri)
        else:
            old_pi, old_ri = best_per_qid[qid]
            old_y = page_regions[old_pi]["regions"][old_ri]["y_center"]
            if y < old_y:
                best_per_qid[qid] = (pi, ri)

    # 3.5 Fallback：未识别题号的方框，按 y 升序填该图"位置缺口"的候选题号
    # （讯飞 OCR 偶尔漏读印刷题号 "N.(M 分)"——靠几何位置推断）
    sorted_candidates = sorted(subjective_qnums)
    for pi, page in enumerate(page_regions):
        # 该图所有方框按 ri（已按 y 升序）
        ris_with_qid = [(ri, qid_per_region.get((pi, ri)))
                          for ri in range(len(page["regions"]))]
        for i, (ri, qid) in enumerate(ris_with_qid):
            if qid is not None:
                continue
            # 前一个已识别题号
            prev_qid = next((q for _, q in ris_with_qid[i-1::-1] if q), None)
            # 后一个已识别题号
            next_qid = next((q for _, q in ris_with_qid[i+1:] if q), None)
            lo = prev_qid if prev_qid is not None else 0
            hi = next_qid if next_qid is not None else 999
            fill = [q for q in sorted_candidates
                    if lo < q < hi and q not in best_per_qid]
            if fill:
                target = fill[0]
                qid_per_region[(pi, ri)] = target
                best_per_qid[target] = (pi, ri)
                print(f"     🔧 fallback: {page['orig_path'].name} #{ri} → Q{target}"
                      f" (prev=Q{prev_qid} next=Q{next_qid})", file=sys.stderr)

    # 4. 输出归属表
    print(f"\n  📋 题号归属:", file=sys.stderr)
    for pi, page in enumerate(page_regions):
        for ri, r in enumerate(page["regions"]):
            qid = qid_per_region.get((pi, ri))
            tag = f"→ Q{qid}" if qid else "未识别"
            preview = region_ocr_texts.get((pi, ri), "")
            print(f"     {page['orig_path'].name} #{ri}: yc={r['y_center']} "
                  f"{tag}  '{preview[:30]}'", file=sys.stderr)

    # 5. 裁切并保存最终图
    result: dict[int, dict] = {}
    for qid, (pi, ri) in best_per_qid.items():
        page = page_regions[pi]
        r = page["regions"][ri]
        img = Image.open(page["orig_path"])
        x1, y1, x2, y2 = r["bbox"]
        # 底部追加 pad（学生答案常溢出框底）
        bot_pad = int(page["h"] * bottom_pad_pct / 100)
        bbox = (
            max(0, x1 - side_pad_px),
            y1,
            min(page["w"], x2 + side_pad_px),
            min(page["h"], y2 + bot_pad),
        )
        crop = img.crop(bbox)
        out_path = out_dir / f"q{qid:02d}.png"
        crop.save(out_path)
        result[qid] = {
            "image_path": f"cropped/q{qid:02d}.png",
            "page_image": page["orig_path"].name,
            "bbox": list(bbox),
            "size": list(crop.size),
        }
        print(f"  ✅ Q{qid} → {out_path.name}  {crop.size[0]}×{crop.size[1]}px",
              file=sys.stderr)

    missing = [q for q in subjective_qnums if q not in result]
    if missing:
        print(f"\n  ⚠️ 未裁切到的主观题: {missing}", file=sys.stderr)
    return result


def main():
    p = argparse.ArgumentParser(description="答题卡主观题裁切（腾讯云方框检测）")
    p.add_argument("photos", nargs="+", help="答题卡照片")
    p.add_argument("--qnums", required=True, help="主观题题号，逗号分隔")
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--manifest", type=Path, help="可选：输出 manifest.json")
    args = p.parse_args()

    photos = [Path(x) for x in args.photos]
    qnums = [int(x) for x in args.qnums.split(",")]
    result = crop_subjective(photos, qnums, args.out_dir)

    if args.manifest:
        args.manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"\n📄 manifest → {args.manifest}", file=sys.stderr)

    print(f"\n📊 {len(result)}/{len(qnums)} 题成功", file=sys.stderr)


if __name__ == "__main__":
    main()
