# scripts/answer-card-ocr/ — 答题卡识别

把家长拍的答题卡照片 → 标准 `answer-card.json`，喂给下游学情报告流水线。

## 🎯 核心方法：缺字母法（已验证 29/29，2026-05-14）

**思路**：用 Qwen-VL-OCR 读印刷字符 → 学生涂黑的字母 OCR 读不到 → "缺哪个 = 涂哪个"

```
答题卡印刷:    "1. A B C D"
学生涂了 C:   "1. A B ▓ D"
OCR 读到:    "1. A B D"
推断:        缺 C = 学生涂 C
```

**优势**：零 template、零 bubble 检测、零像素坐标、抗倾斜、跨任意中国答题卡格式。

详见：[`../../docs/product/ANSWER-CARD-OCR-BREAKTHROUGH.md`](../../docs/product/ANSWER-CARD-OCR-BREAKTHROUGH.md)

## 主入口

### `detect.py` — 生产级 CLI / 模块

```bash
# CLI
python3 detect.py photo1.jpg photo2.jpg \
    --student-name "贾小淇" --student-id 17020950 \
    --output answer-card.json

# 自动支持 HEIC（用 macOS sips 转 JPG）
python3 detect.py IMG_1929.HEIC IMG_1930.HEIC \
    --output answer-card.json

# 多张照片视为同一份卷子（不同区域 / 不同页），结果合并
```

```python
# 作为模块导入
from scripts.answer_card_ocr.detect import detect_card
result = detect_card(
    image_paths=[Path("IMG_1929.jpg"), Path("IMG_1930.jpg")],
    student_name="贾小淇",
    student_id="17020950",
)
# result.answers = [{"qId":"Q1", "filled":"C", ...}, ...]
```

### 输出 JSON Schema

```json
{
  "student": {"name": "贾小淇", "examId": "17020950"},
  "answers": [
    {"qId": "Q1",  "type": "choice",       "filled": "C",      "confidence": 0.95, "ocrSeen": "ABD"},
    {"qId": "Q13", "type": "multi_choice", "filled": ["A","D"], "confidence": 0.90, "ocrSeen": "BC"}
  ]
}
```

匹配 [`../student-report/lib/schemas.py:AnswerCard`](../student-report/lib/schemas.py)。

## 与下游的整合

`detect.py` 输出的 JSON 可以直接喂给 [`scripts/student-report/pipeline.py`](../student-report/pipeline.py)：

```bash
# 端到端：照片 → 学情报告 PDF
python3 scripts/answer-card-ocr/detect.py \
    students/jiaxiaoqi/初三一模-物理/.rotated/*.jpg \
    --student-name "贾小淇" --student-id 17020950 \
    --output students/jiaxiaoqi/chaoyang-2026-yimo-physics/answer-card.json

python3 scripts/student-report/pipeline.py \
    --student-dir students/jiaxiaoqi/chaoyang-2026-yimo-physics
```

或者 `pipeline.py` 也支持**自动检测**：如果 `answer-card.json` 不存在但同目录有 `answer-card-photos/` 文件夹，会自动调 detect.py 生成。

## 准确率（已验证）

| 卡 | 题数 | 正确率 | 备注 |
|---|---|---|---|
| 朝阳一模 语文 | 6 单选 | 6/6 ✅ | 正拍 |
| 朝阳一模 数学 | 8 单选 | 8/8 ✅ | 严重倾斜横拍 |
| 朝阳一模 物理 | 12 单选 + 3 多选 | 15/15 ✅ | 含多选 + 自动检测错涂/漏选 |
| **累计** | **29 题** | **29/29 = 100%** | 跨 3 个科目 |

## 已知限制

| 场景 | 行为 |
|------|------|
| 学生涂得太浅，OCR 仍读到字母 | 识别为"未作答"（confidence 0.5）—— 由 pipeline 兜底 UI 让家长确认 |
| 学生用橡皮擦改过 | 残留可能导致误读 —— 兜底 UI |
| 答题卡折角 / 油渍遮挡 | OCR 整段失败 —— 跳过这页，提示用户重拍 |
| 嵌套子题（如 Q15.①.ABCD ②.ABCD） | 当前 regex 不支持，会跳过子题号 —— 待扩展 |
| ABCDE 5 选项 | 用 `--options-per-question 5` |

## 历史 PoC 脚本（保留作教训）

| 脚本 | 状态 | 教训 |
|------|------|------|
| `llm-template-gen-poc.py` | ❌ 失败 | Qwen-VL-Max 标 bubble 坐标偏离 200+ 像素 |
| `bubble-detect-manual-poc.py` | ⚠️ 部分 | 手工坐标不够精确，置信间距小 |
| `bubble-find-auto-poc.py` | ⚠️ 部分 | 自动找黑色方块，100+ 假阳性 |
| `abcd-anchor-detect-failed.py` | ❌ 失败 | 同 LLM 坐标问题 |
| `aruco-perspective-demo.py` | ✅ 工作 | ArUco 矫正在合成数据 100% — 但实际可以省略（OCR 抗倾斜） |
| `qwen-answer-card-ocr.py` | 🟡 | 旧版 Qwen-VL 答题卡 OCR，已被 detect.py 取代 |
| `answer-card-poc.py` | 🟡 | 旧版多引擎 PoC |
| `aliyun-handwriting-ocr.py` | 🟡 | 阿里云手写 OCR 单独路径 |

## 关键依赖

```
openai          # DashScope OpenAI 兼容接口
DASHSCOPE_API_KEY  # 环境变量
sips            # macOS 自带，用于 HEIC → JPG（HEIC 输入时才需要）
```

依赖**不需要** `opencv-python`、`paddlepaddle` 等大型 ML 库。100 行 Python 全 stdlib + openai。
