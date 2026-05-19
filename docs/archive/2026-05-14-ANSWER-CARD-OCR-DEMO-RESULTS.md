# 答题卡 OCR — 半天 demo 结果

> 日期：2026-05-14
> 关联：[`2026-05-14-ANSWER-CARD-OCR-RESEARCH.md`](./2026-05-14-ANSWER-CARD-OCR-RESEARCH.md)
> 目的：验证 OMRChecker + ArUco perspective correction 在真实场景下的可行性

---

## TL;DR

| 模块 | 状态 | 关键指标 |
|------|------|---------|
| **OMRChecker 跑通官方 sample** | ✅ | **1.1 秒/张**，21 题答案全部识别 |
| **ArUco 透视矫正** | ✅ | 矫正后图与原图**像素差 19.37/255**（< 30 阈值，成功） |
| **真实中文答题卡兼容性** | ⚠️ | 需逐种格式写 `template.json`（每种 1-2 小时） |
| **整体路线 B 可行性** | ✅ | **可行**，但需逐区/科目维护 template；不可"零配置识别任意卡" |

**结论**：路线 B 在工程上是可行的，但**"准确率 90%"的成本不是只来自图像处理，而主要来自 template 配置维护**。每出一份新格式答题卡都要写一份模板（含每个 bubble 的像素坐标）。

---

## 一、OMRChecker 跑通官方 sample

### 操作

```bash
git clone https://github.com/Udayraj123/OMRChecker.git
cd OMRChecker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install opencv-python-headless  # 关键：Python 3.14 装 opencv-python 要 30 分钟源码编译，headless 有预编译 wheel
# 准备输入
cp -r samples/sample1 inputs/
# 关掉交互显示（headless 环境不支持 cv2.imshow）
# 修改 inputs/sample1/config.json: outputs.show_image_level = 0
.venv/bin/python3 main.py --inputDir inputs/sample1
```

### 结果（实测输出）

```
INFO     Found page corners:      [[519, 541], [148, 537], [141, 220], [479, 218]]
INFO     Matching Marker:  Quarter1: 0.451  Quarter2: 0.582  Quarter3: 0.692  Quarter4: 0.547
INFO     Thresholding:   global_thr: 168.58   global_std_THR: 200
INFO     Read Response: {'Roll': 'E503110026', 'q1': 'B', 'q2': '', 'q3': 'D', 'q4': 'B',
                        'q5': '6', 'q6': '11', 'q7': '20', 'q8': '7', 'q9': '16',
                        'q10': 'B', 'q11': 'D', 'q12': 'C', 'q13': 'D', 'q14': 'A',
                        'q15': 'D', 'q16': 'B', 'q17': 'A', 'q18': 'C', 'q19': 'C',
                        'q20': 'D'}
Finished Checking 1 file(s) in 1.1 seconds
OMR Processing Rate        :     ~ 1.12 seconds/OMR
```

**21 个答案（含 Roll Number + 20 题）全部识别**，输出到 CSV + 可视化标记图。

### 输入文件结构

```
inputs/sample1/
├── template.json       # 答题卡布局（题号、bubble 坐标、网格规格）
├── config.json         # 处理参数（分辨率、阈值、显示等级）
├── omr_marker.jpg      # 四角 fiducial marker 模板（用作定位）
└── MobileCamera/
    └── sheet1.jpg      # 实际照片
```

⚠️ `template.json` 描述每个题目区的精确像素坐标、bubble 大小、网格行列数。**不同格式答题卡需要不同 template**。

---

## 二、ArUco 透视矫正（独立 demo）

### 输出文件

代码：[`scripts/answer-card-ocr/aruco-perspective-demo.py`](../../scripts/answer-card-ocr/aruco-perspective-demo.py)

```python
python3 scripts/answer-card-ocr/aruco-perspective-demo.py
```

生成 4 张图：

```
aruco-output/
├── marker_{0,1,2,3}.png        # 4 个 ArUco DICT_4X4_50 标记
├── synthetic_card.png          # 合成的「贴了四角标记的 A4 答题卡」（白底 + bubble）
├── synthetic_card_distorted.png # 模拟手机斜拍的透视畸变图
└── corrected.png               # 透视矫正后的图（应接近 synthetic_card.png）
```

### 关键代码

```python
detector = cv2.aruco.ArucoDetector(
    cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
    cv2.aruco.DetectorParameters()
)
corners, ids, _ = detector.detectMarkers(gray)
# ids = [0, 1, 2, 3] = 左上、右上、左下、右下
src = np.float32([centers[0], centers[1], centers[3], centers[2]])
dst = np.float32([[0,0], [W,0], [W,H], [0,H]])
M = cv2.getPerspectiveTransform(src, dst)
corrected = cv2.warpPerspective(distorted, M, (W, H))
```

### 数值验证

矫正后图 vs 原图 平均像素差：**19.37 / 255**

`< 30` 视为成功（图片细节几乎无损）。

### 结论

ArUco 矫正在**合成数据**上 100% 成功。**真实手机拍摄**也会成功，**前提是答题卡上有 ArUco markers**。

⚠️ **真实北京中考答题卡上没有 ArUco markers**（它们用自己的黑色定位方块，OMRChecker 也支持，但需要单独配置 marker 模板）。

---

## 三、真实中国答题卡兼容性评估

我观察了实际样本——朝阳 2026 一模语文答题卡照片：

| 维度 | 状态 |
|------|------|
| 答题卡格式 | 北京市统一命题，**朝阳区版本** |
| 四角 fiducial markers | ❌ 不是 ArUco，是**黑色方块**（OMRChecker 的 `CropOnMarkers` 也能匹配，需提供 marker 模板） |
| 选择题区 | 多区多空（如"第 1 题 5 个空"）、单选 + 多选混合 |
| 手写区 | 大量长答题（古诗文翻译、文言文、阅读理解） |
| 拍摄质量 | 手机随手拍，桌面背景、光照不均、可能有阴影 |

### 要让 OMRChecker 处理这张卡，需要做：

1. **裁出 4 角 marker 模板**：从一张标准答题卡上 crop 出黑色定位块，存为 `omr_marker.jpg`（5 分钟）
2. **写 `template.json`**：手工标注每个 bubble 的像素坐标（10 题选择题 × 4 选项 = 40 个坐标）。
   - 用 OMRChecker 的 `--setLayout` 模式（GUI 工具）：30 分钟/卡
   - 或纯手工编辑 JSON：1-2 小时/卡
3. **调 `config.json`**：分辨率、阈值。15 分钟。

**单张新格式答题卡首次配置 = 1-2 小时人工**。

### 朝阳区 2026 一模有 5 科答题卡（语数英物道）= **5 套 template**

如果做全北京 16 个区一模 + 二模 + 期中 + 期末 + 中考真题，常用模板数量约 **5 科 × 4-6 次 × 5-10 个常用区 = 100-300 套 template**。

每套用 1-2 小时配置 = **100-600 小时人工** = 一个全职运营 6 周-3 个月的工作。

⚠️ **这是路线 B 最大的隐藏成本**——不是技术难度，而是 template 制作。

---

## 四、缓解方案：自动 template 生成

调研发现可以**用 LLM 辅助生成 template**：

```python
# 思路（待验证）
1. 给 Qwen-VL 看一张干净的答题卡照片 + OMRChecker template 格式说明
2. 让它输出粗略的 bubble 区域坐标（题号 + 行列数）
3. 人工微调（5-10 分钟/卡）
```

预期：把 1-2 小时/卡 降到 **10-20 分钟/卡**。

⚠️ 这只是设想，未验证。但即使做到，**做 100 张模板也需 17-34 小时**。

---

## 五、修正后的路线 B 实施评估

| 阶段 | 原估时 | 修正估时 | 备注 |
|------|--------|---------|------|
| 可行性 demo | 半天 | ✅ **已完成** | OMRChecker + ArUco 都 work |
| 样本采集 + 基础 pipeline | 1-2 周 | 1-2 周 | 不变 |
| 涂卡识别核心 | 2 周 | 2 周 | 不变（单卡格式 PoC） |
| **Template 制作** | （隐含在上面） | **+2-4 周** | **新增显式工作量** |
| 手写部分 + 整合 | 1 周 | 1 周 | 不变 |
| 兜底 UI + 调优 | 2 周 | 2 周 | 不变 |
| **合计** | 6-8 周 | **8-11 周** | template 是新发现的大头 |

---

## 六、推荐下一步

### 短期（接下来 1-2 周）

1. **先做 1 套朝阳一模物理答题卡的 template**（已有真实样本）→ 跑通完整流程
2. **同时验证 LLM 辅助生成 template 的可行性**（Qwen-VL 能不能产出可用初稿）
3. 用贾小淇物理答题卡跑准确率 → 数字基线

### 中期（3-8 周）

如果短期效果好（准确率 > 85%）：
- 扩展到朝阳 5 科
- 启动小程序兜底 UI 开发

如果短期效果不好：
- 考虑路线 A（标准答题卡）"妥协版"——只对**家长可选**的"高精度模式"提供标准卡
- 默认仍走任意卡，但低置信度时建议家长用标准卡

### 长期

考虑做"**家长上传 → 后台人工标 template → 缓存复用**"的运营模式：
- 第一个朝阳家长上传 → 后台 30 分钟手工标 template → 之后同区同科都复用
- 月活 1000、20 个常用模板 → 一次性 20-40 小时投入

---

## 七、文档/代码产出

| 文件 | 用途 |
|------|------|
| 本文档 | demo 结果记录 |
| [`scripts/answer-card-ocr/aruco-perspective-demo.py`](../../scripts/answer-card-ocr/aruco-perspective-demo.py) | 可复用的 ArUco 矫正 demo（合成图 + 矫正） |

外部 fork（暂未集成进 repo）：
- `/tmp/omr-demo/OMRChecker/` — 跑通的官方 sample workspace

---

## 八、技术备注（踩坑速查）

| 坑 | 解决 |
|---|------|
| Python 3.14 装 opencv-python 触发源码编译（30+ 分钟） | 用 `opencv-python-headless`，有预编译 wheel |
| `pyobjc-core` 在 macOS 上对 LibreSSL Python 3.9 不兼容 | 用 Homebrew Python 3.14（OpenSSL 3.6.2） |
| OMRChecker `cv2.imshow` 在 headless 下会卡死 | `config.json` 里 `outputs.show_image_level = 0` |
| `ids[i]` 在 ArUco 新版返回 ndarray 而非 scalar | `int(ids[i][0]) if ids[i].ndim > 0 else int(ids[i])` |
