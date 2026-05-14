"""测试方案：用 OCR 找 ABCD 字母锚点 → 推断涂卡区。

OCR 引擎：DashScope qwen-vl-ocr-latest（专门 OCR，REST API）
逻辑：
1. 全图 OCR → 拿到所有"文本片段 + bbox"
2. 过滤出单字符 A / B / C / D
3. 按 y 中心坐标聚类（行容差 ±25px）
4. 每行内按 x 排序，检查是否成"A B C D" 序列
5. 可视化在原图上
"""
import base64
import json
import os
import sys
from pathlib import Path

import cv2
try:
    import openai
except ImportError:
    print("pip install openai"); sys.exit(1)

IMG_PATH = Path("/tmp/omr-demo/real-card/chinese-card-page1.jpg")
OUT_DIR = Path("/tmp/omr-demo/abcd-output")
OUT_DIR.mkdir(exist_ok=True)


PROMPT = """你是 OCR 引擎。任务：识别图中所有**文字片段**，包括：
- 单个英文字母（A、B、C、D 等）
- 数字（题号 1, 2, 3 等）
- 中文短词（"答题卡"、"姓名" 等）

每个片段输出其精确像素 bounding box（图像左上为 0,0，单位像素，基于原始 1280×1707 图）。

**绝对禁令**：不要解释、不要分析、不要做题。只输出 JSON 转录。

输出 JSON 格式（严格）：

```json
{
  "image_size": [1280, 1707],
  "text_fragments": [
    {"text": "A", "bbox": [x1, y1, x2, y2]},
    {"text": "B", "bbox": [x1, y1, x2, y2]},
    {"text": "2", "bbox": [x1, y1, x2, y2]},
    {"text": "答题卡", "bbox": [x1, y1, x2, y2]}
  ]
}
```

**重点**：图中**所有印刷的单字符 A、B、C、D**（无论涂没涂）都必须列出。

不要 markdown 代码块包裹。"""


def call_ocr(image_path: Path) -> dict:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY")
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    # 关键：必须用 qwen-vl-ocr-latest（专用 OCR，精度比 max 好）
    # 不用 response_format=json_object，因为 ocr-latest 输出格式不一定支持
    resp = client.chat.completions.create(
        model="qwen-vl-ocr-latest",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
        temperature=0.0,
        max_tokens=8192,
    )
    content = resp.choices[0].message.content
    # 容错：去掉 markdown 包裹
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    try:
        return json.loads(content)
    except Exception as e:
        print("RAW:", content[:500], file=sys.stderr)
        raise


def cluster_rows(letters, y_tolerance=25):
    """把 ABCD 字母按 y 中心聚到行。"""
    # 每个字母 (text, x_center, y_center, bbox)
    items = []
    for f in letters:
        bbox = f.get("bbox") or []
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        items.append({
            "text": f["text"],
            "x": (x1 + x2) / 2,
            "y": (y1 + y2) / 2,
            "bbox": bbox,
        })

    # 按 y 聚类
    items.sort(key=lambda i: i["y"])
    rows = []
    for it in items:
        if rows and abs(it["y"] - rows[-1]["y_avg"]) < y_tolerance:
            rows[-1]["items"].append(it)
            rows[-1]["y_avg"] = sum(i["y"] for i in rows[-1]["items"]) / len(rows[-1]["items"])
        else:
            rows.append({"y_avg": it["y"], "items": [it]})

    # 每行内按 x 排序
    for r in rows:
        r["items"].sort(key=lambda i: i["x"])
        r["texts"] = "".join(i["text"] for i in r["items"])
    return rows


def find_abcd_rows(rows):
    """筛出"ABCD"连续 4 字母行。"""
    abcd_rows = []
    for r in rows:
        texts = r["texts"]
        # 严格 ABCD 或 ABCDE
        if "ABCD" in texts:
            # 找 ABCD 4 个字母连续
            for i in range(len(r["items"]) - 3):
                if r["items"][i]["text"] == "A" and \
                   r["items"][i+1]["text"] == "B" and \
                   r["items"][i+2]["text"] == "C" and \
                   r["items"][i+3]["text"] == "D":
                    abcd_rows.append({
                        "y": r["y_avg"],
                        "letters": r["items"][i:i+4],
                    })
    return abcd_rows


def visualize(image_path, rows, abcd_rows, out_path):
    img = cv2.imread(str(image_path))
    # 先标所有 ABCD 单字符（弱标）
    for r in rows:
        for it in r["items"]:
            x1, y1, x2, y2 = [int(v) for v in it["bbox"]]
            cv2.rectangle(img, (x1, y1), (x2, y2), (200, 200, 200), 1)
            cv2.putText(img, it["text"], (x1, y1 - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, (100, 100, 100), 1)
    # 高亮"ABCD 涂卡行"
    for ab in abcd_rows:
        letters = ab["letters"]
        x0 = min(l["bbox"][0] for l in letters) - 10
        y0 = min(l["bbox"][1] for l in letters) - 5
        x1 = max(l["bbox"][2] for l in letters) + 10
        y1 = max(l["bbox"][3] for l in letters) + 5
        cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), (0, 0, 255), 2)
        cv2.putText(img, "ABCD-ROW", (int(x0), int(y0) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.imwrite(str(out_path), img)


if __name__ == "__main__":
    print(f"📷 {IMG_PATH}")
    print("🤖 OCR ...")
    result = call_ocr(IMG_PATH)

    raw_path = OUT_DIR / "ocr-raw.json"
    raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {raw_path}")

    fragments = result.get("text_fragments", [])
    print(f"\n📊 全部识别片段数: {len(fragments)}")

    abcd_letters = [f for f in fragments if f.get("text") in {"A", "B", "C", "D"}]
    print(f"  - ABCD 单字符候选: {len(abcd_letters)}")

    rows = cluster_rows(abcd_letters)
    print(f"  - 字母聚成 {len(rows)} 行")

    abcd_rows = find_abcd_rows(rows)
    print(f"  - 真正「ABCD 连续 4 字」行: {len(abcd_rows)}")

    for i, ab in enumerate(abcd_rows):
        ys = [int(l["y"]) for l in ab["letters"]]
        xs = [int(l["x"]) for l in ab["letters"]]
        print(f"    [{i+1}] y≈{int(ab['y'])}, x={xs}")

    vis = OUT_DIR / "abcd-rows.png"
    visualize(IMG_PATH, rows, abcd_rows, vis)
    print(f"\n🖼  {vis}")
