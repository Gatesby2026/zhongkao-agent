# 选择题涂卡识别方法论 — 专题方案

> **版本**：v1.0（2026-05-31）
> **状态**：🔄 持续迭代（基线已稳定，细节持续改进）
> **关联**：[`STUDENT-REPORT-FEATURE-SPEC.md`](STUDENT-REPORT-FEATURE-SPEC.md) §3.1 ·
>   [`test-data/_choice-bench/`](../../test-data/_choice-bench/)（benchmark + ground-truth）
> **变更基础**：本文档锁定**当前最优方法 = Path B (零 API) + Path C (腾讯 OCR) 二段式**，
>   后续在此框架基础上逐步改进，**不再做架构横跳**。

---

## 0. 问题陈述

**输入**：学生答题卡照片（4-8 张 jpg / heic）

**输出**：每道选择题的填涂作答字典：
```python
{
  qid_int: {
    "filled": "B" | "AC" | "",   # 涂的字母（单选 1 个，多选 2-4 个）
    "confidence": 0.0-1.0,
    "source": "blob" | "tencent" | "缺字母" | "vl-max" | "no_answer",
  }
}
```

**核心难点**（4 个）：
1. **手机拍摄方向不固定**：EXIF 信息常缺失，照片可能旋转 0/90/180/270 度
2. **跨学科 layout 不同**：物理 5×3、数学 4×2 / 2×4 / 1×8、英语 12 选择 不同布局
3. **涂卡密度变化**：marker 笔 vs 圆珠笔 vs 铅笔，物理 vs 数学纸张不同
4. **印刷格式差异**：朝阳裸字母 `1. A B C D` vs 海淀方括号 `1.[A][B][C][D]`

---

## 1. 当前方案（v1.0）— 二段式 🔒

### 1.1 Path B：纯像素 blob 检测（零 API，物理首选）

**适用**：物理 5×3 layout（关丽涵海淀二模 15/15 ✓）

**算法**：
```
1. EXIF + 4 旋转 try（0/90/180/270）
2. y 直方图找涂卡 band：每行 100-800 黑像素 + 高度 ≥ 24 px
3. 行内 x 直方图找连续黑块（涂卡 blob）：宽 20-80 px
4. 多 layout 候选（physics-5x3 / math-4x2 / math-2x4 / math-1x8）
5. 反推 base_x → 每个 blob 中心 snap 到 (qid, letter) 网格
6. 挑 (rot, layout) 组合中 n_filled 最大者
```

**优势**：零 API 成本，毫秒级，物理卡 100% 命中

**局限**：
- 涂卡密度刚好 50% 时，threshold 卡边界 → 数学卡常失败
- 表头/分隔线落在 y 范围内被误识别为涂卡行
- layout 不在 4 个 hardcode 候选里就完全失败

**实现**：`scripts/answer-card-ocr/detect.py::detect_choices_by_blob`

### 1.2 Path C：腾讯 OCR + 缺字母法（数学/英语首选）

**适用**：Path B 命中 < 5 题时启用

**算法**：
```
1. 腾讯 GeneralAccurateOCR(image)
   ─ API 自动旋转 + 字符级精确 bbox
2. 找所有含 [A]/[B]/[C]/[D] 字符的 token
   ─ 处理合并 token：'1.[A][B]' / '[B][C][D]' / '8.[A][B][C]'
   ─ 按 token 文本中字符 index 按比例分 bbox
3. 按 y 聚类成行（y_tol = 25 px）
4. 过滤：每行至少 4 个 letter + distinct >= 2
5. 行内按 x 间距分组成 question（max_intra_q_gap = 200 px）
6. 缺字母法：每题 missing = {A,B,C,D} - OCR 看到 = 涂的字母
```

**优势**：
- ✅ 跨学科通用（A/B/C/D 字符 pattern 通用）
- ✅ 腾讯自动识别图片方向（彻底解决旋转问题）
- ✅ 无 layout 假设、无 y 范围 hardcode
- ✅ 实测沈跃然海淀数学 7/8 = 88%

**成本**：每张卡 +1 API 调用（~RMB 0.05）

**局限**：
- 单选题涂卡延伸到相邻字母 → 缺多字母 → 误判为多选（沈跃然 Q5 案例）
- 印刷 [X] 字符模糊时也会误识

**实现**：`scripts/answer-card-ocr/tencent_choice_grid.py` +
  `detect.py::detect_choices_by_tencent`

### 1.3 合并优先级 🔒

```python
# 在 detect_card 中（detect.py:866+）
if blob_choices[qid].filled and blob_conf >= 0.9:    # Path B 强信号
    use blob
elif tencent_choices[qid].filled and tencent_conf >= 0.85:  # Path C 强信号
    use tencent
elif qid in real_hits:                                 # 缺字母法 OCR 真识别
    use 缺字母
elif density_choices:                                  # Path A vl-max bbox
    use density
elif vlmax_choices:                                    # vl-max 直接判
    use vl-max
else:                                                  # no_answer
    fallback
```

### 1.4 触发策略

```python
# 流程：
Path B (零 API) →
    if n_filled >= 5: 直接出 ✓ 物理基线
    else: 触发 Path C
Path C (腾讯 API) →
    覆盖 Path B 漏掉的题
合并 → answer-card.json
```

**物理卡**：仅走 Path B（零 API，毫秒级）
**数学/英语卡**：Path B + Path C（~RMB 0.05/张）

---

## 2. 已否决方案 ❌

| 方案 | 否决原因 |
|------|----------|
| **qwen-vl-max 直接判涂卡** | 模型 prior 把涂黑当 token 噪声补全字母，海淀方括号格式 -15 分回归 |
| **OpenCV bubble detect 标准答题卡** | 需家长打印 PDF，用户摩擦太大 |
| **模板匹配** | 各区印版不同，模板维护成本高 |
| **腾讯 EduPaperOCR** | 为印刷试卷设计，把数学公式拆出来但不识别涂卡 |
| **腾讯 QuestionOCR** | 把整页切成 problem-solving regions，没有 multiple-choice 专项 |
| **腾讯 SubmitQuestionMarkAgentJob** | 需要 ReferenceAnswer 才能用，是判分 agent 不是涂卡识别 |

---

## 3. Benchmark testset 🔒

**位置**：`test-data/_choice-bench/`

**结构**：
```
_choice-bench/
├── README.md
├── bench_choice.py          # 跑全集 + 出命中率表
└── cases/
    └── <case>/
        ├── page-01.jpg (symlink)
        └── ground-truth.yaml  # 人工核实的填涂真值
```

**当前 cases**：

| Case | Layout | 真值来源 | 命中率 |
|------|--------|---------|--------|
| `guanlihan-haidian-er-physics` | physics-5x3 | user 确认 + Path B 双向 | **15/15 100%** |
| `shenyueran-haidian-er-math` | math-4x2 | user 直接告知 (CCBD CBAD) | **7/8 88%** |

**待补**（按优先级）：
1. `fangshiyao-xicheng-yi-math` — 西城数学（不同区 layout 验证）
2. `zhangyizhang-haidian-er-math` — 海淀数学（layout 跨学生稳定性）
3. `shixinran-xicheng-yi-math` — 西城数学
4. 朝阳数学卡（layout 不同？）
5. 英语 12 选择卡（cross-subject）
6. 道法 / 化学 / 历史 各 1-2 张

跑测：
```bash
TENCENT_OCR_SECRET_ID=... TENCENT_OCR_SECRET_KEY=... \
python3 test-data/_choice-bench/bench_choice.py [--verbose]
```

---

## 4. 已识别的改进方向 🔄

按 ROI 排序：

### P0 — 影响线上多数 case

| 方向 | 描述 |
|------|------|
| **单选涂卡覆盖相邻字母**（Q5 案例） | 缺字母法推 2-3 个字母 missing 时，启发式判断单选 vs 多选 |
| **涂卡淡时 OCR 误读字母** | 腾讯 OCR 把淡涂的字母也认出来 → 缺字母法漏判 |

### P1 — 跨学科 / layout 扩展

| 方向 | 描述 |
|------|------|
| **英语 12 选择 layout 实测** | layout 可能是 3 行 × 4 题 或 4 行 × 3 题 |
| **道法 选择 + 判断混合** | 判断题不是 A/B/C/D 形式 |
| **作答区裁切 + Path A 像素密度兜底** | Path C 失败时再 fallback 像素验证 |

### P2 — 性能 / 成本优化

| 方向 | 描述 |
|------|------|
| **物理卡也走腾讯** | 准确率可能更高，但每卡多 RMB 0.05 |
| **预先 EXIF 自动旋转** | 减少 4 次旋转尝试 |
| **结果 cache** | 同张照片不重复调腾讯 |

---

## 5. 实施约束 🔒

任何对 Path B / Path C 的修改 **必须**：

1. **跑通现有 bench**：`bench_choice.py` 必须保持/提升命中率
2. **回归测试集**（`test-data/_choice-bench/cases/`）每 case 不退化
3. **修改时按本文档"已否决方案"清单核对**，不重复走弯路
4. **新 layout / 新 API**：先加 benchmark case + ground-truth，再改 detect 逻辑

---

## 6. 历史轨迹（教训）

| 阶段 | 方法 | 命中率 | 教训 |
|------|------|--------|------|
| Phase 1 (5月初) | qwen-vl-max 直接判 | 30-40% | 模型 prior 干扰 token 补全 |
| Phase 2 | 缺字母法 (qwen-vl-ocr) | 60-65% | 朝阳裸字母稳，海淀方括号 0% |
| Phase 3 (5/29) | Path A: vl-max bbox + 像素密度 | 部分 | bbox 不稳，校准困难 |
| Phase 4 (5/30) | **Path B: 纯像素 blob** | 物理 100% | 物理基线锁定，跨学科失败 |
| Phase 5 (5/31) | **Path C: 腾讯 OCR + 缺字母法** | **95.7%** | layout 自适应 + 旋转自动解决 |

**关键 insight**：
- 涂卡识别**不是单一算法能解决**，需要多引擎按场景分工
- **专用 API（如 EduPaperOCR）≠ 适配涂卡识别**：通用 API（GeneralAccurateOCR）反而更准
- 缺字母法本质是"OCR 读不到 = 被涂"，**跨格式都适用**
- 像素扫法对物理标准卡极快极稳，但 layout 不通用

---

## 7. 术语对照

| 术语 | 含义 |
|------|------|
| **涂卡** | 学生在答题卡填涂题选项的黑色实心标记 |
| **填涂区 / 选择题区** | 答题卡上 `[A][B][C][D]` 排列的网格区域 |
| **blob** | 连续黑像素块（涂卡的 50×30 px 矩形） |
| **base_x** | 第一题 [A] 字母的 x 坐标，反推用 |
| **缺字母法** | "OCR 读不到的字母 = 被涂了" 的推断方法 |
| **letter_step** | 同题内相邻字母 cx 间距（~70 px 物理 / ~47 px 数学） |
| **col_step** | 同行内相邻题 cx 间距（~345 px 物理 / ~355 px 数学） |
