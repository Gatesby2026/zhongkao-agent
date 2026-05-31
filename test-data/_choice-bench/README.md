# 选择题涂卡识别专题测试集

固化"答题卡选择题填涂识别"的回归 + 研究 benchmark。
跟通用 `test-data/<case>/` 区别：这里只关心**选择题部分**，每个 case 配
**人工核实的填涂真值**（ground-truth），用于度量识别命中率。

---

## 目录结构

```
_choice-bench/
├── README.md              # 本文档：测试集说明 + 研究备忘
├── bench_choice.py        # benchmark 脚本（跑所有 case + 出命中率表）
└── cases/
    ├── <case-1>/
    │   ├── page-01.jpg    # 答题卡照片（imgnorm 处理后）
    │   ├── ...
    │   └── ground-truth.yaml  # 人工核实的填涂真值
    └── <case-2>/
        └── ...
```

`ground-truth.yaml` schema：

```yaml
slug: 2026-haidian-er-physics      # 试卷 exam_slug
student: 关丽涵                     # 学生名
source: prod-aid-9cf5379f8880      # 卡来源
layout: physics-5x3                # 布局类型（见下表）
orientation: portrait              # 照片方向：portrait/landscape-left/landscape-right/upside-down
n_questions: 15                    # 选择题总数
answers:                           # 真实填涂（人工肉眼核实）
  Q1: A
  Q2: B
  ...
  Q13: BD       # 多选题
  Q14: ACD
  Q15: AB
verified_by: jiakui                # 谁核实的
verified_at: 2026-05-31
```

---

## 已知 layout 类型

| 布局 ID | 适用 | 行 × 题/行 | 总题数 | 备注 |
|---------|------|-----------|--------|------|
| `physics-5x3` | 海淀/朝阳 物理 | 3 单选行 + 1 多选行 | 15（12 单 + 3 多） | 关丽涵基线 |
| `math-4x2` | 海淀 数学 | 2 × 4 | 8 单选 | 沈跃然 |
| `math-2x4` | 朝阳 数学? | 4 × 2 | 8 单选 | 待验 |
| `math-1x8` | 西城 数学? | 8 × 1 | 8 单选 | 待验 |
| `english-?` | 英语 | 待研究 | 12 单选 | 待验 |
| `chinese-?` | 语文 | 待研究 | 1-3 单选 | 数量少 |
| `politics-?` | 道法 | 待研究 | 10-15 单选 + 判断 | 待验 |

每加一个新 layout 在 `detect.py` 的 `_LAYOUTS_TO_TRY` 加一项 + 在这表登记。

---

## 跑测

```bash
# 单 case
python3 test-data/_choice-bench/bench_choice.py guanlihan-haidian-er-physics

# 全部
python3 test-data/_choice-bench/bench_choice.py

# 详细模式（打印每题对比）
python3 test-data/_choice-bench/bench_choice.py --verbose
```

输出表格：每 case 命中率 / per-layout 命中率 / 全局命中率。

---

## 研究方向（待做）

`Path B` 当前在物理 15/15 命中，数学卡 1/8 — 因为：

1. **照片方向自适应**：部分手机 EXIF 缺失，需要软件自动识别正确方向
   - 候选：4 旋转 try（当前）/ 文本方向 OCR / Hough 线检测
2. **涂卡密度阈值**：物理涂卡 ~60-70% 密度，数学 ~50%
   - 候选：自适应 smoothing 窗口 / 区分印刷 `[X]` 与学生涂黑块的宽度
3. **Layout 自动发现**：不依赖 hardcode，从 blob 分布反推
   - 候选：blob 间距聚类 / 模板匹配 / 一次性 vl-max 接地
4. **多选题识别**：物理基线已 ✓，其他学科待测

研究流程：
1. 加新 case 到 `cases/`，标真值
2. 跑 `bench_choice.py` 看新 case 是否过
3. 不过则 debug `detect.py` 的具体 layout / 旋转 / 阈值
4. 改完跑全集回归，不退化才合并

---

## 数据隐私

- 学生照片包含可识别信息（姓名/准考证号），仅本机用，不外传
- `.gitignore` 已排除 `_choice-bench/` 不进公共仓库（如需要）
