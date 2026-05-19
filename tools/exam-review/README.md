# exam-review

Mock-exam YAML 手工审核工具。加载 `knowledge-base/mock-exams/` 下的试卷
YAML，自动检测常见质量问题（缺答案、option 不全、solution 为空、知识点
未标注等），生成自包含 HTML 可视化页面，支持键盘导航和手工标注。

## 用法

```bash
# 单文件
./tools/exam-review/exam-review knowledge-base/mock-exams/physics/beijing/2026-chaoyang-yi.yaml

# 某科目全部
./tools/exam-review/exam-review --subject physics

# 全部科目
./tools/exam-review/exam-review --all

# 只生成 HTML 不打开浏览器
./tools/exam-review/exam-review --subject physics --out /tmp/review.html --no-open
```

加到 PATH 后可直接 `exam-review ...`：

```bash
export PATH="$PATH:$HOME/projects/zhongkao-agent/tools/exam-review"
```

## 检测项

**题目级**
- `empty_stem`        — 题干为空（error）
- `zero_score`        — 分值为 0（error）
- `no_answer`         — 答案为空（error）
- `answer_format`     — 单/多选答案格式不符（warn）
- `options_missing`   — 选择题缺 options 字段（error）
- `options_incomplete`— 选择题缺某选项（error）
- `options_empty_content` — 选项内容为空或仅 [图]（error）
- `no_solution`       — 实验/计算/解答题 solution 未填（warn）
- `no_kp`             — knowledge_points 为空（warn）
- `bad_module`        — module 不在已知枚举（warn）
- `qc_flag`           — 生成阶段已标记 needs_review（warn）

**卷级**
- `score_mismatch` — 分值合计 ≠ full_score
- `count_mismatch` — 实际题数 ≠ total_questions
- `dup_id`         — 重复 id

## 页面操作

- **筛选**：全部 / 有问题 / 已确认 / 已标记 / 待处理
- **键盘**：`↑↓` / `j/k` 导航 · `空格` 确认 · `F` 标记 · `C` 折叠 · `[]` 切卷
- **标注**：每题可"✅确认 / 🚩标记 / 备注"，保存在浏览器 localStorage

## 文件结构

```
tools/exam-review/
├── README.md
├── exam-review          # bash launcher（PATH 入口）
├── exam_review.py       # Python 主程序
└── templates/
    └── index.html       # HTML/CSS/JS 模板（含 KaTeX、markdown 表格渲染）
```

## 依赖

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- 浏览器（KaTeX 通过 CDN 加载）

无后端，HTML 自包含（图片以 base64 内嵌）。
