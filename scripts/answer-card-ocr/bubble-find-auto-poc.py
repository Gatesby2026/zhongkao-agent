"""完全自动找出图中所有"被涂黑"的小方块/小圆形。

思路：
1. 二值化 → 找轮廓
2. 过滤：面积在 100-1000 像素²、形状近矩形/圆形
3. 黑色区域 = 涂了的 bubble

无需手工坐标。
"""
import cv2
import numpy as np
from pathlib import Path

IMG = Path("/tmp/omr-demo/real-card/chinese-card-page1.jpg")
OUT = Path("/tmp/omr-demo/real-card/auto-detected.png")


def find_filled_bubbles(image_path):
    img = cv2.imread(str(image_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print(f"图: {img.shape[1]}×{img.shape[0]}")

    # 自适应阈值
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 51, 10
    )

    # 形态学开闭（去噪点 + 填小孔）
    kernel = np.ones((3, 3), np.uint8)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)

    # 找连通域
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    print(f"  总轮廓数: {len(contours)}")

    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        aspect = w / max(h, 1)
        # bubble 一般是小方块：100-800 像素²，长宽比 0.5-2，宽高 10-35
        if 100 < area < 1000 and 0.5 < aspect < 2.0 and 8 < w < 40 and 8 < h < 40:
            # 检查实际填充率（contour 面积 / bbox 面积，越大越实心）
            cnt_area = cv2.contourArea(c)
            fill = cnt_area / area if area > 0 else 0
            if fill > 0.5:  # 实心 > 50% 视为"涂了"
                candidates.append({
                    "bbox": (x, y, w, h),
                    "area": area,
                    "fill": fill,
                    "cx": x + w // 2,
                    "cy": y + h // 2,
                })

    print(f"  涂卡 bubble 候选: {len(candidates)} 个")

    # 可视化
    vis = img.copy()
    for c in candidates:
        x, y, w, h = c["bbox"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.circle(vis, (c["cx"], c["cy"]), 3, (0, 255, 0), -1)

    cv2.imwrite(str(OUT), vis)
    print(f"  可视化: {OUT}")

    # 按 y 排序，看分布
    candidates.sort(key=lambda c: (c["cy"], c["cx"]))
    print("\n  按位置排序的前 20 个候选：")
    for c in candidates[:20]:
        print(f"    ({c['cx']:4d}, {c['cy']:4d}) {c['bbox'][2]}×{c['bbox'][3]} fill={c['fill']:.2f}")
    return candidates


if __name__ == "__main__":
    find_filled_bubbles(IMG)
