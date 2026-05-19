# 答题卡（手机拍照）识别技术方案调研

> 调研日期：2026-05-14
> 决策：**B 路线 — 兼容任意答题卡**（牺牲准确率换零摩擦）
> 关联文档：[`../specs/STUDENT-REPORT-FEATURE-SPEC.md`](../specs/STUDENT-REPORT-FEATURE-SPEC.md) §三 步骤 3
> （注：本文为 2026-05-14 归档调研流水账，已被落地流水线取代）

---

## 一、核心结论

| 结论 | 内容 |
|---|---|
| 1 | **国内三大云（阿里/百度/腾讯）的"教育 OCR"全是切印刷试卷，没有任何商业 OMR API 卖给开发者** |
| 2 | **LLM 视觉模型（Qwen-VL / GPT-4o / Claude）对涂卡 fill ratio 判断天生不擅长**，换模型解决不了 |
| 3 | **专业 OMR 系统（南昊/阅卷王/讯飞智学）都是 B 端学校采购**，不卖 API + 必须用他们印的卡 + 必须扫描仪 |
| 4 | **整个 C 端市场没有"手机拍 + 任意答题卡 + 自动批改"先例**——学而思/作业帮/猿辅导都不做这个 |
| 5 | **唯一可行路径**：OpenCV 自建 CV 流水线（基于开源 [OMRChecker](https://github.com/Udayraj123/OMRChecker)）+ Qwen-VL 处理手写 + 人工兜底 UI |

## 二、为什么这看似"成熟技术"在这里成了痛点

OMR（涂卡识别）是 70 年代成熟技术，**但只在"扫描仪 + 标准卡"场景成熟**：

| 场景 | 难度 |
|------|------|
| 扫描仪 + 标准答题卡（高考阅卷） | 简单，30 年前就 99%+ |
| **手机拍 + 任意答题卡（我们的场景）** | 难，没有现成方案 |

差异点：手机拍照引入透视畸变 + 光照不均 + 模糊 + 任意旋转 + 任意背景，必须重新做 CV 流水线。

## 三、A/B 路线对比与决策

| 维度 | A. 标准答题卡 | **B. 任意答题卡** ✅ |
|------|-------------|------------------|
| 涂卡识别准确率 | 98%+ | ~90% |
| 用户体验 | 家长需打印我们设计的 PDF | **零摩擦，直接拍** |
| 实施周期 | 3-4 周 | 6-8 周 |
| 人工兜底比例 | < 2% | ~10% |
| 调参/样本采集投入 | 小 | **大**（需采集 50-100 张真实样本） |

**决策（2026-05-14）：选 B**。理由：

- 家长用户体验**零摩擦**是 C 端产品最关键的留存因素
- 10% 兜底通过"小程序里点击确认"实现，1 秒可完成
- 多花的 2-4 周开发是值得的投入

## 四、推荐架构

```
家长拍照（手机）
    ↓
[前端] 模糊度/亮度检测 + 引导框 UI
       → 不合格立即让用户重拍（避免事后失败）
    ↓
[后端] 答题卡边界检测 + 透视矫正
       - 优先 ArUco 四角（如果卡上有定位点）
       - 兜底 findContours 最大四边形
    ↓
┌──────────────────────┬───────────────────────┐
│  选择题区 OMR        │   手写答案区 OCR        │
│  (OpenCV 自建)        │   (Qwen-VL-Max，保留)  │
│  - 自适应二值化       │                       │
│  - 题号/格子定位      │                       │
│  - 填涂比例计算       │                       │
│  - 置信度评分         │                       │
└──────────────────────┴───────────────────────┘
    ↓                          ↓
[置信度策略]
  - 涂卡 fill_ratio > 0.5 & 第二高 < 0.3：高置信
  - 否则：低置信，进人工确认 UI
    ↓
最终 answer-card.json + 兜底标记
    ↓
进 pipeline.py 后续流程
```

## 五、技术选型与依据

| 模块 | 选型 | 链接 / 备注 |
|------|------|------------|
| 图像预处理 | OpenCV (Python) | 成熟、免费 |
| 答题卡定位 | ArUco markers（优先）+ findContours（兜底） | [OpenCV ArUco](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html) |
| 涂卡 OMR | fork [OMRChecker](https://github.com/Udayraj123/OMRChecker) 改造 | MIT 协议，工业级 |
| 手写答案 | 保留 Qwen-VL-Max | 已验证 80%+ |
| 兜底 UI | 小程序对话流内嵌"核对涂卡"步骤 | 1 秒/题 |

## 六、关键技术参考

- [PyImageSearch Bubble Sheet OMR 教程](https://pyimagesearch.com/2016/10/03/bubble-sheet-multiple-choice-scanner-and-test-grader-using-omr-python-and-opencv/) — 工业界 OMR 入门标准
- [Adaptive Threshold 实战](https://docs.opencv.org/4.x/d7/d4d/tutorial_py_thresholding.html) — 解决光照不均
- [ArUco marker 在线生成](https://chev.me/arucogen/) — 半天验 perspective correction

## 七、商业 OCR 厂商现状（调研明细）

| 厂商 | 产品 | 是否真做涂卡 OMR | 备注 |
|------|------|-----------------|------|
| 阿里云 | `RecognizeEduPaperCut/OCR/Structed` | ❌ 切印刷题 | 0.01-0.03 元/次 |
| 百度智能云 | "试卷切题识别" | ❌ 切印刷题 | 0.06 元/次 |
| 腾讯云 | "试题识别" | ❌ 切印刷题 | ~0.01 元/次 |
| 科大讯飞 | "智学网" | ✅（B 端） | 不卖 API |
| 有道/商汤/汉王 | 通用 OCR | ❌ | 无 OMR 产品 |
| 南昊/正迅/蓝鸽/阅卷王 | 网上阅卷整套 | ✅（B 端） | 不卖 API + 必须标准卡 + 必须扫描仪 |

## 八、实施路线图（B 路线，6-8 周）

### 第 0 周 — 可行性 demo（半天，必做）

不论后续如何走，先验证基础设施：

1. `git clone https://github.com/Udayraj123/OMRChecker` → 跑官方 demo（30 分钟）
2. 配最简模板（10 道单选）+ 手机拍 5 张样本 → 出准确率基线（2 小时）
3. ArUco 四角 + OpenCV `warpPerspective` 跑通透视矫正 demo（半天）

**通过则继续；不通过则重新评估架构**。

### 第 1-2 周 — 样本采集 + 基础 pipeline

- 采集真实样本：10 张贾小淇的答题卡（已有）+ 找朋友家长收 30-50 张其他卡
- 基础 OpenCV pipeline：模糊检测 → 边界检测 → 透视矫正
- 输出 `answer-card-raw-detection.json`（区域定位结果）

### 第 3-4 周 — 涂卡识别核心

- fork OMRChecker，适配中国答题卡格式（A/B/C/D 单选、ABCD 多选）
- 实现：题号 OCR（用 Qwen-VL 找题号位置）+ 格子定位 + 填涂比例计算
- 置信度评分系统
- 跑回归测试集 → 调阈值

### 第 5-6 周 — 兜底 UI + 整合

- 小程序内"核对涂卡"页面：显示原图区域 + AI 猜测 + ABCD 按钮
- 整合进 pipeline.py：替换现有 qwen-answer-card-ocr.py
- 端到端回归

### 第 7-8 周 — 调优 + 上线准备

- 100 张真实样本调参
- 边缘 case 兜底（卷子折角、用蓝笔涂、橡皮擦印记等）
- 上线小程序内测

## 九、当前 W1 已交付，W2 待启动

| 阶段 | 状态 |
|------|------|
| W1 — pipeline.py MVP（4 JSON → MD + PDF） | ✅ 已交付（commit c9bd49a） |
| W2 — 答题卡 CV pipeline（本调研对应） | ⏳ 待启动 |
| W3 — 答案页自动结构化 | ⏳ |
| W4 — gaokzx 试卷抓取 | ⏳ |
| W5-6 — 后端 API + 小程序集成 | ⏳ |

## 十、可执行的第一步

```bash
# 半天验证可行性，零成本
git clone https://github.com/Udayraj123/OMRChecker
cd OMRChecker
pip install -r requirements.txt
python3 main.py --inputDir samples/sample1
```

跑通后用手机拍 5 张贾小淇物理答题卡（已有的）跑一遍，看准确率基线。

不通过则马上停下重新讨论；通过则按 6-8 周路线图推进。
