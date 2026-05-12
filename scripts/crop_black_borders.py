#!/usr/bin/env python3
"""批量裁掉 iPhone 截屏上下/左右的纯黑边。"""
from pathlib import Path
from PIL import Image
import numpy as np

SRC = Path("/Users/jiakui/daily-work/初三一模-语文/试卷及答案-origin")
DST = Path("/Users/jiakui/daily-work/初三一模-语文/试卷及答案")
DST.mkdir(parents=True, exist_ok=True)

# 用"亮像素占比"判断是否内容行：
# - 正文（白底黑字）：亮像素占 80%+
# - 黑边 / 黑底白字状态栏（如 "X 2/13"）：亮像素 < 5%
BRIGHT_THRESHOLD = 128   # 像素值 >= 128 算"亮"
RATIO_THRESHOLD = 0.30   # 亮像素占比 >= 30% 才算内容行

def find_content_bounds(arr_gray: np.ndarray) -> tuple[int, int, int, int]:
    """返回 (top, bottom, left, right) — 内容区边界（含）。"""
    bright = arr_gray >= BRIGHT_THRESHOLD
    row_ratio = bright.mean(axis=1)
    col_ratio = bright.mean(axis=0)
    row_keep = np.where(row_ratio > RATIO_THRESHOLD)[0]
    col_keep = np.where(col_ratio > RATIO_THRESHOLD)[0]
    if not len(row_keep) or not len(col_keep):
        return -1, -1, -1, -1
    return row_keep[0], row_keep[-1], col_keep[0], col_keep[-1]


def crop(img_path: Path, out_path: Path) -> None:
    img = Image.open(img_path)
    arr = np.array(img.convert("L"))
    t, b, l, r = find_content_bounds(arr)
    if t < 0:
        print(f"  ⚠ {img_path.name} 整张黑，跳过")
        return
    h, w = arr.shape
    # 裁切（含右下边界）
    cropped = img.crop((l, t, r + 1, b + 1))
    cropped.save(out_path, optimize=True)
    print(f"  ✓ {img_path.name}: {w}×{h} → {cropped.width}×{cropped.height}  (上裁 {t}, 下裁 {h-b-1}, 左裁 {l}, 右裁 {w-r-1})")


def main() -> None:
    pngs = sorted(SRC.glob("IMG_*.PNG"))
    print(f"共 {len(pngs)} 张")
    for p in pngs:
        crop(p, DST / p.name)
    print(f"\n完成。输出：{DST}")


if __name__ == "__main__":
    main()
