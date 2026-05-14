"""Track B：让 Qwen-VL-Max 识别答题卡上的涂卡 bubble 位置，生成 OMRChecker template 草稿。

输入：一张答题卡照片
输出：
  - llm-template-draft.json：Qwen-VL 推断的 bubble 坐标
  - llm-template-visualization.png：在原图上画框
  - 控制台报告：题数、坐标范围
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

INPUT_IMG = Path("/tmp/omr-demo/real-card/chinese-card-page1.jpg")
OUT_DIR = Path("/tmp/omr-demo/llm-output")
OUT_DIR.mkdir(exist_ok=True)


PROMPT = """你是答题卡 OCR 工程师。任务：识别这张中国学生答题卡上**所有的填涂选择题区域**，输出每个 bubble 的精确像素坐标。

## 你看到的图是什么

北京朝阳一模九年级语文答题卡。一张 A4 纸照片，1280×1707 像素。其中包括：
- 题号区（如 "1." "2." "3." 等数字+点）
- 填涂选择题（A B C D 圆形/方形涂卡格）
- 手写答题区（学生用笔写）

## 仅识别填涂选择题

**请只输出"4 个 A/B/C/D 格子在一行"** 这类涂卡题。**忽略**：
- 手写区域（古诗文默写、阅读理解、作文）
- 表头区（"学校 姓名 准考证号"）
- 注意事项区
- QR 码区

## 坐标系

图片左上角是 (0,0)，向右 x 增大，向下 y 增大。
单位是像素（基于完整 1280×1707 图）。

## 输出 JSON（严格遵守，不要 ```markdown 包裹）

```json
{
  "image_size": [1280, 1707],
  "questions": [
    {
      "qid": "Q2",
      "bubbles": [
        {"label": "A", "cx": 290, "cy": 410, "r": 12},
        {"label": "B", "cx": 320, "cy": 410, "r": 12},
        {"label": "C", "cx": 350, "cy": 410, "r": 12},
        {"label": "D", "cx": 380, "cy": 410, "r": 12}
      ]
    }
  ]
}
```

说明：
- `cx, cy` 是每个 bubble 的**中心**像素坐标
- `r` 是 bubble 半径（约 8-15 像素，根据图调整）
- 同一题的 4 个 bubble 通常 cy 相同，cx 间距约 30-50 像素
- 题号顺序按图片从上到下、从左到右

仅识别**能清晰看到 A B C D 字母 + 圆/方框**的涂卡题。看不清就不要乱猜。"""


def call_qwen_vl(image_path: Path) -> dict:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY")
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    resp = client.chat.completions.create(
        model="qwen-vl-max",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
        temperature=0.0,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def visualize(image_path: Path, template: dict, out_path: Path):
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"❌ 读图失败 {image_path}"); return
    for q in template.get("questions", []):
        qid = q.get("qid", "?")
        for b in q.get("bubbles", []):
            cx, cy, r = b.get("cx", 0), b.get("cy", 0), b.get("r", 12)
            color = {"A": (0, 0, 255), "B": (0, 165, 255),
                     "C": (0, 255, 0), "D": (255, 0, 0)}.get(b.get("label"), (128, 128, 128))
            cv2.circle(img, (cx, cy), int(r) + 2, color, 2)
            cv2.putText(img, b.get("label", "?"), (cx - 8, cy - r - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        # 题号标
        if q.get("bubbles"):
            x0 = min(b["cx"] for b in q["bubbles"]) - 40
            y0 = q["bubbles"][0].get("cy", 0)
            cv2.putText(img, qid, (x0, y0 + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 0, 200), 2)
    cv2.imwrite(str(out_path), img)


if __name__ == "__main__":
    print(f"📷 读图: {INPUT_IMG}")
    if not INPUT_IMG.exists():
        print(f"❌ 输入图不存在"); sys.exit(1)
    img = cv2.imread(str(INPUT_IMG))
    print(f"  尺寸: {img.shape[1]}×{img.shape[0]}")

    print("\n🤖 调 Qwen-VL-Max ...")
    template = call_qwen_vl(INPUT_IMG)

    template_path = OUT_DIR / "llm-template-draft.json"
    template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {template_path}")

    questions = template.get("questions", [])
    bubble_total = sum(len(q.get("bubbles", [])) for q in questions)
    print(f"\n📊 LLM 输出：")
    print(f"  - 题目数: {len(questions)}")
    print(f"  - bubble 总数: {bubble_total}")
    for q in questions[:5]:
        bs = q.get("bubbles", [])
        if bs:
            print(f"    {q.get('qid')}: {len(bs)} 个 bubble, "
                  f"y={bs[0].get('cy')}, x={bs[0].get('cx')}–{bs[-1].get('cx')}")

    vis_path = OUT_DIR / "llm-template-visualization.png"
    visualize(INPUT_IMG, template, vis_path)
    print(f"\n🖼️  可视化: {vis_path}")
    print(f"  打开看 LLM 标的 bubble 位置准不准")
