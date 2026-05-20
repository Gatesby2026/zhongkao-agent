#!/usr/bin/env python3
"""从整页试卷图中裁剪出各题的图片区域（v2：基于 PaddleOCR + 程序匹配）。

流水线：
  1. PaddleOCR LayoutDetection 检测每页所有 image bbox（CV 模型，离线，确定性）
  2. OCR 文本里题号锚点 → 该题在页面的 y 区间（程序规则）
  3. OCR 文本里 [图]/如图 → 每题"含图证据"作为分配 demand（程序规则）
  4. 全局贪心匹配（按 y-IoU 排序）把 image bbox 分配到题号
  5. 同题多 bbox 合并为外接矩形
  6. 扩张 + 文字边缘剥离 + 裁切落地

**无 LLM 调用**。完全基于 paddle CV 模型 + 程序规则。
旧 qwen-vl-max 实现见 `extract_figures.legacy.py`（备份）。

CLI:
    python3 extract_figures.py <src_dir> --subject physics [--out-dir <staging>]

读取:  <src_dir>/images/page-*.png                 （原始件，knowledge-original）
       <out_dir>/pages/page-*.ocr.txt              （派生件，knowledge-base）
       <out_dir>/structured-cloud/final.json
写入:  <out_dir>/figures/q{NN}.png
       <out_dir>/structured-cloud/final.json       （加 figure_path 字段）
out_dir 缺省由 paths.derive_out_dir(src_dir) 映射到 knowledge-base。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("pip install pillow", file=sys.stderr); sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("pip install numpy", file=sys.stderr); sys.exit(1)

# 复用本目录内的模块
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assign_figures import (  # noqa: E402
    classify_pages,
    question_y_intervals,
    question_figure_demand,
    assign_images_to_questions,
)
from paths import derive_out_dir  # noqa: E402


# ========================= CV 后处理（保留自 legacy）=========================

def _expand_bbox(bbox, img_size, pct=10, min_px=15):
    """向外扩张 bbox（按 bbox 边长百分比，至少 min_px）。

    所有坐标强制转 int（paddle 输出是 float，PIL 切片需要 int）。
    """
    x1, y1, x2, y2 = (int(v) for v in bbox)
    img_w, img_h = img_size
    bw, bh = x2 - x1, y2 - y1
    ex = max(min_px, int(bw * pct / 100))
    ey = max(min_px, int(bh * pct / 100))
    x1e = max(0, x1 - ex)
    y1e = max(0, y1 - ey)
    x2e = min(img_w, x2 + ex)
    y2e = min(img_h, y2 + ey)
    pad = (y1 - y1e, x1 - x1e, y2e - y2, x2e - x2)
    return (x1e, y1e, x2e, y2e), pad


def _find_blank_bands(is_blank, min_band):
    """1D 连续 True 段长度 ≥ min_band → [(start, end)]。"""
    bands = []
    in_b = False; start = 0
    n = len(is_blank)
    for i in range(n):
        if is_blank[i]:
            if not in_b:
                start = i; in_b = True
        else:
            if in_b:
                if i - start >= min_band:
                    bands.append((start, i))
                in_b = False
    if in_b and n - start >= min_band:
        bands.append((start, n))
    return bands


def _trim_one_axis(is_blank, axis_len, bbox_lo, bbox_hi, min_blank_band):
    """1D 边缘剥离：只在 [0, bbox_lo) 和 [bbox_hi, axis_len) 找空白带剥除，
    bbox 内部 [bbox_lo, bbox_hi) 永远保留（保护多子图组合）。"""
    new_lo = 0
    new_hi = axis_len
    bands = _find_blank_bands(is_blank[:bbox_lo], min_blank_band)
    if bands:
        new_lo = bands[-1][1]
    if bbox_hi < axis_len:
        bands = _find_blank_bands(is_blank[bbox_hi:], min_blank_band)
        if bands:
            new_hi = bbox_hi + bands[0][0]
    return new_lo, new_hi


def _trim_text_edges(crop_img, bbox_pad, threshold=140, min_blank_band=4):
    """从裁剪图的四周剥离边缘文字行/列。剥离只在原 bbox 外的扩张区进行。

    bbox_pad: (top, left, bot, right) — _expand_bbox 返回的扩张像素数
    """
    arr = np.array(crop_img.convert("L"))
    h, w = arr.shape
    if h < 30 or w < 30:
        return crop_img

    top_pad, left_pad, bot_pad, right_pad = bbox_pad
    bbox_top = top_pad
    bbox_bot = h - bot_pad
    bbox_left = left_pad
    bbox_right = w - right_pad

    binary = arr < threshold
    row_blank_thresh = max(3, int(w * 0.015))
    col_blank_thresh = max(3, int(h * 0.015))
    is_blank_row = (binary.sum(axis=1) < row_blank_thresh)
    is_blank_col = (binary.sum(axis=0) < col_blank_thresh)

    top, bottom = _trim_one_axis(is_blank_row, h, bbox_top, bbox_bot, min_blank_band)
    left, right = _trim_one_axis(is_blank_col, w, bbox_left, bbox_right, min_blank_band)

    if bottom - top < max(30, h // 4) or right - left < max(30, w // 4):
        return crop_img
    return crop_img.crop((left, top, right, bottom))


def crop_and_save(page_img: Path, bbox: tuple, out_path: Path,
                   refine: bool = True, expand_pct: int = 10) -> bool:
    """裁剪 + CV 后处理 + 保存。refine=True 启用扩张 + 文字边缘剥离。"""
    try:
        img = Image.open(page_img)
        if refine:
            expanded, pad = _expand_bbox(bbox, img.size, pct=expand_pct)
            cropped = img.crop(expanded)
            orig_size = cropped.size
            cropped = _trim_text_edges(cropped, pad)
            if cropped.size != orig_size:
                print(f"    ✂️ 边缘剥离 {orig_size} → {cropped.size}",
                      file=sys.stderr)
        else:
            cropped = img.crop(bbox)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(out_path, "PNG")
        return True
    except Exception as e:
        print(f"    ⚠️ 裁剪保存失败 {out_path.name}: {e}", file=sys.stderr)
        return False


# ========================= 主流程 =========================

# 与 ocr_paper._normalize_md_noise 同源：清掉 ```围栏 / # 标题前缀 / 第N页页脚——
# 否则页内题号被写成 "## 17." 致 NUM_ANCHOR_RE（要求行首数字）整页失配 →
# extract_figures 误判该页"无含图题"跳过 paddle，q17/q18 永远缺失。
_MD_FENCE_RE = re.compile(r"(?m)^\s*```[A-Za-z0-9_-]*\s*$\n?")
_MD_HEAD_RE = re.compile(r"(?m)^\s*#{1,6}[ \t]+")
_PAGE_FOOTER_RE = re.compile(r"(?m)^\s*第\s*\d+\s*页\s*/?\s*共?\s*\d*\s*页?\s*$\n?")


def _normalize_md_noise(text: str) -> str:
    t = _MD_FENCE_RE.sub("", text)
    t = _MD_HEAD_RE.sub("", t)
    t = _PAGE_FOOTER_RE.sub("", t)
    return t


def _load_pages_text(paper_dir: Path) -> dict[str, str]:
    """读 pages/ 下 OCR 缓存。返回 {page-NN: text}（已 md-normalize）。"""
    out = {}
    pages = paper_dir / "pages"
    if pages.exists():
        for f in sorted(pages.glob("page-*.ocr.txt")):
            key = f.name.replace(".ocr.txt", "")  # page-01
            out[key] = _normalize_md_noise(f.read_text(encoding="utf-8"))
    return out


def _load_layout_for_page(page_img: Path, cache_dir: Path) -> list[dict]:
    """对一页图做 paddle layout detection，结果缓存到 cache_dir。

    cache 文件: cache_dir/{page-NN}.layout.json
    """
    cache = cache_dir / f"{page_img.stem}.layout.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    # 延迟 import paddle（首次 import 慢、内存重）
    from paddle_layout import get_detector
    det = get_detector()
    boxes = det.detect(str(page_img))

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(boxes, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return boxes


def extract_figures(src_dir: Path, out_dir: Path, subject: str = "",
                     dry_run: bool = False, force: bool = False) -> None:
    """主入口：从 final.json 读题目，paddle 检测 + 分配 + 裁切，更新 final.json。

    src_dir: 原始卷目录（只读 images/）。
    out_dir: 派生 staging 目录（pages/structured-cloud/figures/layout-cache）。
    """
    final_json = out_dir / "structured-cloud" / "final.json"
    images_dir = src_dir / "images"
    figures_dir = out_dir / "figures"
    layout_cache_dir = out_dir / "layout-cache"

    if not final_json.exists():
        raise FileNotFoundError(f"找不到 final.json: {final_json}")

    data = json.loads(final_json.read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    # 选择题集合（含单选+多选），用于"4 选项图组"分配
    choice_qs = {q["number"] for q in questions
                 if q.get("type") in ("choice", "multi_choice")}

    # 加载 OCR 文本（每题 demand + y 区间的输入）
    pages_text = _load_pages_text(out_dir)
    if not pages_text:
        raise FileNotFoundError(f"无 OCR 缓存: {out_dir / 'pages'}")

    # 各页是否答案页
    page_names = sorted(pages_text.keys())
    page_text_list = [pages_text[p] for p in page_names]
    is_ans = classify_pages(page_text_list)

    # 题号 y 区间 + demand
    intervals_per_page: dict[str, dict[int, tuple[float, float]]] = {}
    demand_per_page: dict[str, dict[int, int]] = {}
    for i, page in enumerate(page_names):
        if is_ans[i]:
            continue
        is_first = (page == "page-01")
        intervals_per_page[page] = question_y_intervals(pages_text[page], is_first)
        demand_per_page[page] = question_figure_demand(pages_text[page], is_first)

    # 统计含图题（demand > 0 的总集合）
    fig_qs: set[int] = set()
    for p, d in demand_per_page.items():
        for q, c in d.items():
            if c > 0:
                fig_qs.add(q)
    print(f"📑 {len(questions)} 题，OCR 标记含图: {sorted(fig_qs)} ({len(fig_qs)} 题)")

    # 页号映射：page-01 → Path
    page_img_map: dict[str, Path] = {}
    for img in sorted(images_dir.glob("page-*.png")):
        page_img_map[img.stem] = img

    # 逐页：paddle 检测 + 分配 + 裁切
    figure_paths: dict[int, str] = {}

    for page in page_names:
        if is_ans[page_names.index(page)]:
            continue
        if page not in page_img_map:
            print(f"  ⚠️ {page} 图片不存在，跳过")
            continue

        page_img = page_img_map[page]
        intervals = intervals_per_page.get(page, {})
        demands = demand_per_page.get(page, {})

        if not any(d > 0 for d in demands.values()):
            continue  # 该页无含图题

        with Image.open(page_img) as img:
            page_w, page_h = img.size

        print(f"\n📄 {page} (页面 {page_w}×{page_h})")
        if dry_run:
            print(f"   [dry-run] 跳过 paddle 检测")
            continue

        # paddle layout detection
        boxes = _load_layout_for_page(page_img, layout_cache_dir)
        # paddle 全 label 中，image+table 都是题图候选（数据表也是题的视觉载体，
        # 如比热容实验数据表；之前只取 image 把 table 题永远漏掉）
        images = [b for b in boxes if b["label"] in ("image", "table")]
        print(f"   paddle 检测: {len(boxes)} 个 box, 其中 image+table {len(images)} 个")

        # 全局匹配（图号硬匹配主键 + 选择题 4 图组 + 几何兜底）
        assigned = assign_images_to_questions(
            images, intervals, demands, page_h,
            choice_qs=choice_qs,
            page_text=pages_text.get(page, ""),
            is_first_page=(page == "page-01"))

        # 同题多 bbox 合并为外接矩形，裁切落地
        for q_num in sorted(assigned):
            bboxes = [b["bbox"] for b in assigned[q_num]]
            x1 = min(b[0] for b in bboxes)
            y1 = min(b[1] for b in bboxes)
            x2 = max(b[2] for b in bboxes)
            y2 = max(b[3] for b in bboxes)
            note = f" ({len(bboxes)} 子图合并)" if len(bboxes) > 1 else ""
            print(f"   Q{q_num}: bbox=({x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}) "
                  f"{x2-x1:.0f}×{y2-y1:.0f}{note}")

            out_path = figures_dir / f"q{q_num:02d}.png"
            if crop_and_save(page_img, (x1, y1, x2, y2), out_path):
                figure_paths[q_num] = f"figures/q{q_num:02d}.png"
                print(f"   ✅ Q{q_num} → {out_path.name}")
            else:
                print(f"   ❌ Q{q_num} 裁切失败")

    # 更新 final.json：figure_path（始终覆盖，防止旧版残留）
    for q in questions:
        num = q.get("number")
        q["figure_path"] = figure_paths.get(num)

    if not dry_run:
        final_json.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        print(f"\n✅ final.json 更新完毕")

    # 汇总
    print(f"\n=== 汇总 ===")
    print(f"  OCR 标记含图: {len(fig_qs)} 题")
    print(f"  paddle 成功裁切: {len(figure_paths)} 题")
    miss = sorted(fig_qs - set(figure_paths))
    if miss:
        print(f"  未分配（建议在 exam-review 工具里人工补）: {miss}")


def main():
    p = argparse.ArgumentParser(
        description="paddle CV 模型 + 程序匹配：从试卷页裁切各题图片"
    )
    p.add_argument("src_dir", type=Path,
                   help="原始卷目录（knowledge-original/...），含 images/page-*.png")
    p.add_argument("--out-dir", type=Path, default=None,
                   help="派生 staging 目录；缺省按 paths.derive_out_dir 映射")
    p.add_argument("--subject", default="",
                   help="科目（仅用于日志，可选）")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印分配结果，不裁切也不写 final.json")
    p.add_argument("--force", action="store_true",
                   help="强制重跑 paddle layout 检测（忽略缓存）")
    args = p.parse_args()

    src_dir = args.src_dir.resolve()
    if not src_dir.is_dir():
        print(f"目录不存在: {src_dir}", file=sys.stderr); sys.exit(1)
    out_dir = (args.out_dir or derive_out_dir(src_dir)).resolve()

    if args.force:
        cache = out_dir / "layout-cache"
        if cache.exists():
            for f in cache.glob("*.json"):
                f.unlink()
            print(f"🗑  清理 layout 缓存: {cache}")

    extract_figures(src_dir, out_dir, subject=args.subject,
                     dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
