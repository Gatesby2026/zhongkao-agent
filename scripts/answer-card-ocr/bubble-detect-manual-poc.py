"""真实答题卡上"bubble 填涂检测"最小 PoC（手工标定 + OpenCV）。

任务：识别 Q2/Q5/Q7 学生涂了哪个 ABCD（每题 1 个）。
方法：手工目测每个 bubble 的像素坐标 → 计算 ROI 灰度平均值 → 最暗的就是被涂的那个。
"""
import cv2
import numpy as np
from pathlib import Path

IMG_PATH = Path("/tmp/omr-demo/real-card/chinese-card-page1.jpg")
OUT_PATH = Path("/tmp/omr-demo/real-card/bubble-detection-result.png")

# 手工标定（在 1280×1707 原图上的像素坐标）
# 通过看 bubble-region-1.5x.png 推断；每个 bubble 半径约 15 像素
TEMPLATE = [
    {
        "qid": "Q2",
        "bubbles": [
            {"label": "A", "cx": 138, "cy": 631},
            {"label": "B", "cx": 175, "cy": 631},
            {"label": "C", "cx": 213, "cy": 631},
            {"label": "D", "cx": 250, "cy": 631},
        ],
    },
    {
        "qid": "Q5",
        "bubbles": [
            {"label": "A", "cx": 138, "cy": 810},
            {"label": "B", "cx": 175, "cy": 810},
            {"label": "C", "cx": 213, "cy": 810},
            {"label": "D", "cx": 250, "cy": 810},
        ],
    },
    {
        "qid": "Q7",
        "bubbles": [
            {"label": "A", "cx": 138, "cy": 875},
            {"label": "B", "cx": 175, "cy": 875},
            {"label": "C", "cx": 213, "cy": 875},
            {"label": "D", "cx": 250, "cy": 875},
        ],
    },
]
RADIUS = 12   # bubble 半径


def measure_fill(gray, cx, cy, r=RADIUS):
    """计算以 (cx,cy) 为中心半径 r 的 ROI 的"填涂度"（0-1，越大越黑）。"""
    h, w = gray.shape
    x0, y0 = max(0, cx - r), max(0, cy - r)
    x1, y1 = min(w, cx + r), min(h, cy + r)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    # 灰度反转 + 平均：越黑 → 平均越高 → 填涂度大
    return 1.0 - (roi.mean() / 255.0)


def detect_filled(image_path, template):
    img = cv2.imread(str(image_path))
    if img is None:
        raise RuntimeError(f"读图失败 {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print(f"图: {img.shape[1]}×{img.shape[0]}")

    vis = img.copy()
    results = []
    for q in template:
        fills = []
        for b in q["bubbles"]:
            fill = measure_fill(gray, b["cx"], b["cy"])
            fills.append((b["label"], fill, b["cx"], b["cy"]))

        # 最暗的 = 涂的
        fills_sorted = sorted(fills, key=lambda x: -x[1])
        picked = fills_sorted[0]
        runnerup = fills_sorted[1]
        confidence = picked[1] - runnerup[1]  # gap

        # 画框
        for label, fill, cx, cy in fills:
            color = (0, 255, 0) if label == picked[0] else (200, 200, 200)
            cv2.circle(vis, (cx, cy), RADIUS + 3, color, 2)
            cv2.putText(vis, f"{label}:{fill:.2f}", (cx - 25, cy - RADIUS - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        cv2.putText(vis, f"{q['qid']} → {picked[0]}",
                    (50, q["bubbles"][0]["cy"] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2)

        results.append({
            "qid": q["qid"],
            "picked": picked[0],
            "fills": {l: f for l, f, _, _ in fills},
            "confidence": confidence,
        })

    cv2.imwrite(str(OUT_PATH), vis)
    print(f"\n📊 检测结果：")
    for r in results:
        gap = r["confidence"]
        verdict = "✅ 高置信" if gap > 0.10 else ("⚠️  歧义" if gap > 0.03 else "❌ 不可信")
        print(f"  {r['qid']} → {r['picked']}   (置信间距 {gap:+.3f}, {verdict})")
        print(f"      fill ratios: {', '.join(f'{l}={v:.2f}' for l, v in r['fills'].items())}")
    print(f"\n🖼️  可视化: {OUT_PATH}")
    return results


if __name__ == "__main__":
    detect_filled(IMG_PATH, TEMPLATE)
