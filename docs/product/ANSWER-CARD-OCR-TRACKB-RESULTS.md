# 答题卡 OCR — Track A+B 并行 demo 结果

> 日期：2026-05-14
> 关联：[ANSWER-CARD-OCR-RESEARCH.md](./ANSWER-CARD-OCR-RESEARCH.md) · [ANSWER-CARD-OCR-DEMO-RESULTS.md](./ANSWER-CARD-OCR-DEMO-RESULTS.md)
> 目的：在真实中国答题卡上验证 4 种方法的可行性

---

## TL;DR

| 实验 | 结果 |
|---|---|
| 1. OMRChecker 官方 sample | ✅ 1.1 秒/张、21 题识别全对（已验过） |
| 2. ArUco 透视矫正 | ✅ 像素差 19.37/255（已验过） |
| **3. LLM 辅助生成 template** | ❌ **失败**：Qwen-VL 标的 bubble 位置严重偏离实际涂卡区 |
| **4. 真实中国答题卡上手工 + OpenCV** | ⚠️ **部分成功**：能找到涂卡 bubble，但需要 template 约束区域 |

**关键结论**：路线 B（兼容任意答题卡）**技术上可行但成本不可低估**——**LLM 不能减少 template 工程量**。Per-card-format template 必须人工或半人工标定。

---

## 实验 3：LLM 辅助 template 生成（Track B）

### 假设

如果 Qwen-VL-Max 能识别答题卡照片上 bubble 的精确像素坐标，每张新格式的 template 配置时间可以从 1-2 小时 ↓ 到 10-20 分钟。

### 方法

- 给 Qwen-VL-Max 看 1280×1707 的真实朝阳一模语文答题卡
- 用严格 JSON 模式要求输出每个涂卡题的 4 个 bubble 像素坐标 `{cx, cy, r}`
- 把 LLM 输出的圆圈画在原图上验证

代码：[`scripts/answer-card-ocr/llm-template-gen-poc.py`](../../scripts/answer-card-ocr/llm-template-gen-poc.py)

### 结果

LLM 输出 6 道题、24 个 bubble 坐标，但**几乎所有都聚集在图片顶部 1/3 区域**——实际涂卡区是在图片中段。

```
LLM 给的 Q2 bubble 坐标: y=410, x=290–380
真实 Q2 在原图: y ≈ 630, x ≈ 130–270
```

x 偏差 ~200 像素，y 偏差 ~220 像素。在 1280×1707 的图上这是**几乎完全错位**。

### 为什么失败

跟之前已验证的事实一致：**LLM 视觉模型不擅长精确像素坐标**。
- 它能"识别那里有 ABCD 涂卡"（定性正确）
- 但说不准"在第几行第几列"（量化错误）

这同样适用于 GPT-4o、Claude vision、Gemini vision。**不是 prompt 调优能修复的。**

### 启示

**LLM 在 template 制作中能做的：**
- ✅ 识别"这张卡上有多少道涂卡题"
- ✅ 识别"题号是什么、有 ABCD 几个选项"
- ❌ 给不出精确像素坐标

**人机分工的可行方案**（未验证但合理）：
- LLM 给"粗略 region"（"涂卡区大概在图片 30%-70% 高度处"）
- CV 在那个 region 内用 contour detection 找精确 bubble
- 人工最后微调 + 标定题号映射

---

## 实验 4：真实中国答题卡 + OpenCV 自动 bubble 检测

### 方法

跳过 OMRChecker（template 太复杂），直接用 OpenCV `adaptiveThreshold` + `findContours` 自动找图中所有"被涂黑的小方块"。

代码：[`scripts/answer-card-ocr/bubble-find-auto-poc.py`](../../scripts/answer-card-ocr/bubble-find-auto-poc.py)

### 结果

```
图: 1280×1707
总轮廓数: 2386
涂卡 bubble 候选: 123 个
```

可视化（[auto-detected.png](../../scripts/answer-card-ocr/aruco-perspective-demo.py)）显示找到了所有真正涂卡的 bubble ✅，**但也包括 100+ 假阳性**：
- 表头里的小方块（"缺考标记"附近）
- 手写笔迹的偶然连通域
- QR 码
- 二维码定位标
- 涂卡选项编号（"A B C D" 字母本身被识别成方块）

### 启示

**纯 CV 找 bubble 在干净 sample 上能 work，在真实拍照的中国答题卡上需要 region 约束**。

约束的方式：
1. **Template.json**（OMRChecker 路线）— 显式给"涂卡区在 (x,y,w,h)"
2. **训练小模型**（YOLO） — 让模型学"哪些是涂卡 bubble"
3. **混合**：LLM 给粗略 region → CV 在 region 内找精确 bubble

---

## 修正后的路线 B 实施路线

```
┌─────────────────────────────────────────────┐
│ 用户拍照（任意答题卡）                          │
└─────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────┐
│ 第 1 道闸：图片预检                            │
│  - 模糊度检测                                  │
│  - 分辨率检测                                  │
│  - 答题卡识别（QR / 表头 OCR 判断哪份卡）       │
└─────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────┐
│ 第 2 道闸：找已知 template                      │
│  - 是否已有这种卡的 template？                   │
│  - 有 → 跳到识别；无 → 进 template 制作流程       │
└─────────────────────────────────────────────┘
                  ↓ 已知 template
┌─────────────────────────────────────────────┐
│ 第 3 步：透视矫正 + bubble fill 计算            │
│  - OMRChecker 或自建 CV pipeline               │
└─────────────────────────────────────────────┘
                  ↓
                结果

如果 template 缺失：

┌─────────────────────────────────────────────┐
│ Template 制作流程（运营 / 半自动）              │
│  - 显示原图给运营人员                           │
│  - 提供"点击 bubble 中心"工具（GUI）           │
│  - LLM 辅助识别题号文字                         │
│  - 运营人员审核 + 保存                          │
│  - 单卡耗时：5-15 分钟（含 LLM 辅助）           │
└─────────────────────────────────────────────┘
```

### 关键决策点

| 决策 | 影响 |
|---|---|
| 是否做 template 制作工具？ | 减少运营成本 5x，开发 1 周 |
| 是否标准化"高频"卡（朝阳/海淀一模二模）？ | 80% 用户复用 20 套 template，运营成本可控 |
| 是否限制支持的考试范围？ | 缩小到"北京一模二模 5 科" → 大约 80 套 template 覆盖大部分需求 |

---

## 修正后的路线 A vs B 重新对比

调研已验证两条路都"可行"，但成本结构变了：

| 维度 | A 标准卡（自有 fiducial） | B 任意卡 |
|---|---|---|
| 用户体验 | 需打印 PDF | 拍即可 |
| 单卡识别准确率 | 98%+ | ~90%（有 template 时） |
| **支持范围** | 我们设计的卡 = 100% | 北京高频 ~80 套卡（覆盖 80% 需求） |
| Template 工程量 | 1 套 | **80+ 套**（每张 5-15 分钟，需 7-20 小时） |
| 运营持续投入 | 一次性 | 每出新版考试都要补 template |
| 兜底人工率 | < 2% | 10%+（识别失败 + 不支持的卡格式） |

**意外发现**：路线 B 不是"省 1 次 PDF 打印 vs 多 N 倍工作量"——
- A 的工程量集中在**前期设计 1 套标准卡**（1 周）
- B 的工程量分散到**持续制作 80+ 套 template**（每周 1-2 套，长期投入）

---

## 给产品决策的建议

调研做完，**建议重新评估 A vs B**：

### 选项 1（保守，推荐 MVP）：A 路线 + 强体验补偿

- 设计一份带 ArUco 标记的标准答题卡 PDF
- 微信小程序里"3 秒打印教程"+ 自动适配 A4 打印
- 学生在我们的卡上做模考 / 重做错题 → 拍照
- 识别准确率 98%+，几乎不需要兜底 UI
- **MVP 4 周可上线**

### 选项 2（雄心，但成本高）：B 路线 + template 工厂

- 启动"template 工厂"项目：投入 1 人月做 50 套高频卡 template
- 用户体验零摩擦
- 但识别准确率 ~90%，需要兜底 UI
- **MVP 8-12 周**

### 选项 3（混合，平衡）：A 默认 + B 兜底

- 默认走 A 路线（我们设计的卡，准确率 98%）
- 用户也可以"凑合"拍学校发的卡 → 走 B 路线（准确率 ~90%，兜底 UI 多）
- 渐进式扩 B 路线 template 库
- **MVP 5-6 周（先 A，B 后做）**

---

## 实验产出（已 commit 进 repo）

| 文件 | 内容 |
|---|---|
| `scripts/answer-card-ocr/aruco-perspective-demo.py` | ArUco 透视矫正 demo |
| `scripts/answer-card-ocr/llm-template-gen-poc.py` | LLM 辅助生成 template（**失败案例**保留） |
| `scripts/answer-card-ocr/bubble-detect-manual-poc.py` | 手工坐标 + 灰度阈值检测 |
| `scripts/answer-card-ocr/bubble-find-auto-poc.py` | 完全自动 contour 检测（找到+假阳性） |
| `docs/product/ANSWER-CARD-OCR-DEMO-RESULTS.md` | 半天 demo 结果（实验 1+2） |
| 本文 | Track A+B 并行结果 |

---

## 下一步

**等产品决策**（A / B / 混合）后启动具体开发。每条路线时间和工程量已量化。
