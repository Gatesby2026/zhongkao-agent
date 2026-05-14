"""ArUco fiducial marker 生成 + 检测 + 透视矫正 demo。

验证：是否可以用 ArUco 把任意角度拍摄的「贴有四角标记的答题卡」自动矫正成正面 A4 图。
"""
import cv2
import numpy as np
from pathlib import Path

OUT = Path("/tmp/omr-demo/aruco-output")
OUT.mkdir(exist_ok=True)


def gen_markers():
    """生成 4 个 ArUco marker（id 0,1,2,3，DICT_4X4_50）。"""
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    for i in range(4):
        img = aruco.generateImageMarker(dictionary, i, 200)
        cv2.imwrite(str(OUT / f"marker_{i}.png"), img)
        print(f"  生成 marker_{i}.png 200x200")
    print("✅ 4 个 ArUco markers 已生成")


def make_synthetic_card():
    """合成一张「贴了四角标记的 A4 答题卡」模拟图（白底+四角 marker+若干 bubble）。"""
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)

    # A4 长宽比 1:1.414，做一张 800x1131 的白纸
    W, H = 800, 1131
    page = np.ones((H, W, 3), dtype=np.uint8) * 255

    margin, marker_size = 30, 90
    # 4 个角贴 marker
    positions = [(margin, margin), (W - margin - marker_size, margin),
                 (margin, H - margin - marker_size), (W - margin - marker_size, H - margin - marker_size)]
    for i, (x, y) in enumerate(positions):
        m = aruco.generateImageMarker(dictionary, i, marker_size)
        m3 = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
        page[y:y+marker_size, x:x+marker_size] = m3

    # 中间放几行模拟 bubble（圆形）
    for row in range(15):
        y = 200 + row * 50
        for col, label in enumerate("ABCD"):
            x = 150 + col * 100
            # 第 row+1 题，模拟「涂」row%4 对应的那个
            filled = (col == row % 4)
            color = (50, 50, 50) if filled else (200, 200, 200)
            thickness = -1 if filled else 2
            cv2.circle(page, (x, y), 18, color, thickness)
            cv2.putText(page, label, (x - 30, y + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
        cv2.putText(page, f"Q{row+1}.", (50, y + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 50, 50), 2)

    cv2.imwrite(str(OUT / "synthetic_card.png"), page)
    print(f"✅ 合成原始答题卡 (W={W}, H={H}) → synthetic_card.png")
    return page


def distort(page):
    """模拟「手机斜拍」的透视畸变：把矩形答题卡映射成倾斜四边形。"""
    h, w = page.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    # 倾斜：右上角往内收、左下角往外撑
    dst = np.float32([[80, 50], [w - 30, 150], [w - 70, h - 30], [40, h - 100]])
    M = cv2.getPerspectiveTransform(src, dst)
    out_w, out_h = w, h + 100
    distorted = cv2.warpPerspective(page, M, (out_w, out_h),
                                    borderValue=(180, 180, 180))
    cv2.imwrite(str(OUT / "synthetic_card_distorted.png"), distorted)
    print(f"✅ 模拟手机斜拍 → synthetic_card_distorted.png")
    return distorted


def correct_perspective(distorted):
    """从畸变图中检测 ArUco markers → 透视矫正回正面 A4。"""
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    params = aruco.DetectorParameters()
    detector = aruco.ArucoDetector(dictionary, params)

    gray = cv2.cvtColor(distorted, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)

    if ids is None or len(ids) < 4:
        print(f"❌ 仅检测到 {0 if ids is None else len(ids)} 个 markers，需要 4 个")
        return None

    print(f"✅ 检测到 {len(ids)} 个 markers: ids={ids.flatten().tolist()}")

    # 取每个 marker 的中心点
    centers = {}
    for i, corner_set in enumerate(corners):
        marker_id = int(ids[i][0]) if ids[i].ndim > 0 else int(ids[i])
        cx = np.mean(corner_set[0][:, 0])
        cy = np.mean(corner_set[0][:, 1])
        centers[marker_id] = (cx, cy)

    # ID 0=左上, 1=右上, 2=左下, 3=右下（按生成时顺序）
    src = np.float32([centers[0], centers[1], centers[3], centers[2]])
    target_w, target_h = 800, 1131
    dst = np.float32([[0, 0], [target_w, 0], [target_w, target_h], [0, target_h]])
    M = cv2.getPerspectiveTransform(src, dst)
    corrected = cv2.warpPerspective(distorted, M, (target_w, target_h))
    cv2.imwrite(str(OUT / "corrected.png"), corrected)
    print(f"✅ 透视矫正回 800×1131 → corrected.png")
    return corrected


if __name__ == "__main__":
    print("=== 1. 生成 4 个 ArUco markers ===")
    gen_markers()
    print()
    print("=== 2. 合成「贴了四角 marker 的答题卡」 ===")
    page = make_synthetic_card()
    print()
    print("=== 3. 模拟手机斜拍（透视畸变） ===")
    distorted = distort(page)
    print()
    print("=== 4. 检测 markers + 透视矫正回正 ===")
    corrected = correct_perspective(distorted)
    print()
    if corrected is not None:
        # 对比矫正前后的差异（绝对像素差）
        diff = np.mean(np.abs(corrected.astype(int) - page.astype(int)))
        print(f"矫正后图 vs 原图 平均像素差：{diff:.2f}/255")
        print(f"（< 30 算成功；越接近 0 越好）")
