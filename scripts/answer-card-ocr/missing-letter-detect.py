"""核心思路：涂卡 = OCR 看不到的字母。

OCR 读 "1. xxx 2. B C D 3. A C D 5. A B D 7. A C D"
→ Q2 缺 A → 学生涂 A
→ Q3 缺 B → 学生涂 B
→ Q5 缺 C → 学生涂 C
→ Q7 缺 B → 学生涂 B

零 template、零 bubble 检测、零像素坐标。
"""
import base64
import json
import os
import re
import sys
from pathlib import Path

try:
    import openai
except ImportError:
    print("pip install openai"); sys.exit(1)


IMG = Path("/tmp/omr-demo/real-card/chinese-card-page1.jpg")
OUT_DIR = Path("/tmp/omr-demo/missing-letter-output")
OUT_DIR.mkdir(exist_ok=True)


def call_ocr(image_path: Path) -> dict:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    PROMPT = """你是 OCR 转录器。把图中**所有印刷文字**逐行抄录下来，纯文本输出，不要 JSON、不要任何解释。

格式：每行一行文字。

涂卡选择题部分必须**逐字符抄录所有可见的 A B C D 字母**——
**如果某个字母被涂黑/遮挡看不见，直接跳过不写**。
不要"猜测"或"补全"。

示例：如果图里写着 "2. A▓ C D"（B 被涂黑遮挡），抄录为：
2. A C D

不要 markdown 包裹，不要 JSON 包裹，直接纯文本。"""
    resp = client.chat.completions.create(
        model="qwen-vl-ocr-latest",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
        temperature=0.0,
        max_tokens=8192,
    )
    raw = resp.choices[0].message.content
    # 直接按行分割
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    return {"lines": lines}


PATTERN = re.compile(r"(\d+)\s*[.．、]\s*([A-D\s]+?)(?=\d+\s*[.．、]|$|[一-鿿])")


def parse_choices(lines):
    """从 OCR 行里抽取「题号 + 看到的字母」。"""
    results = {}
    text = " ".join(lines)
    # 匹配 "数字. ABCD字母组合"，可能带空格
    for m in re.finditer(r"(\d+)\s*[.．、]\s*([A-D]\s*(?:[A-D]\s*)*)(?=\D|$)", text):
        qid = int(m.group(1))
        letters = re.sub(r"\s+", "", m.group(2))
        # 只接受长度 1-4 的纯 ABCD 序列
        if 1 <= len(letters) <= 4 and all(c in "ABCD" for c in letters):
            results[qid] = letters
    return results


def infer_answer(seen_letters: str, full_options=("A", "B", "C", "D")) -> dict:
    """OCR 看到的字母 vs 完整 4 字母 → 推断学生涂了哪个。"""
    seen = set(seen_letters)
    missing = sorted(set(full_options) - seen, key=lambda c: full_options.index(c))
    # 类型判断：
    # missing 0 = 学生没涂 / 涂得太浅没被遮
    # missing 1 = 单选涂了一个
    # missing 2+ = 多选 或 漏选
    return {
        "seen": seen_letters,
        "filled": missing,
        "verdict": (
            "未作答" if len(missing) == 0
            else f"单选: {missing[0]}" if len(missing) == 1
            else f"多选: {''.join(missing)}"
        ),
    }


if __name__ == "__main__":
    print(f"📷 {IMG}")
    print("🤖 OCR ...")
    result = call_ocr(IMG)
    lines = result.get("lines", [])
    print(f"  OCR 行数: {len(lines)}")

    raw_path = OUT_DIR / "ocr-raw.json"
    raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 看一遍 OCR 的原始行
    print("\n📋 OCR 原始转录（前 25 行）：")
    for i, l in enumerate(lines[:25]):
        print(f"  {i+1:2d}. {l[:100]}")

    print("\n🔍 解析选择题：")
    choices = parse_choices(lines)
    if not choices:
        print("  ⚠️  没匹配到 ABCD 选择题模式")
        sys.exit(0)

    print(f"  匹配到 {len(choices)} 题：\n")
    print(f"  {'题号':<6} {'OCR看到':<12} {'推断涂卡':<15} {'类型'}")
    print(f"  {'---':<6} {'-----':<12} {'-----':<15} {'-----'}")
    for qid in sorted(choices.keys()):
        seen = choices[qid]
        inf = infer_answer(seen)
        print(f"  Q{qid:<5} {seen:<12} {''.join(inf['filled']) or '(空)':<15} {inf['verdict']}")
