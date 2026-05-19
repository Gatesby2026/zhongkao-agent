# answer-card-review

学生答题卡审核工具。加载 `students/<name>/<exam>/answer-card.json`（由 `scripts/answer-card-ocr/detect.py` 生成），自动与试卷标准答案对照，生成自包含 HTML 显示作答 / 对错 / 置信度 / 原图，便于教师/家长核对 OCR 识别结果。

## 用法

```bash
# 单学生单考试（自动找 photos + 推断标准答案）
./tools/answer-card-review/answer-card-review \
  students/jiaxiaoqi/2026-chaoyang-yi-physics

# 直接传 answer-card.json
./tools/answer-card-review/answer-card-review \
  students/jiaxiaoqi/2026-chaoyang-yi-physics/answer-card.json

# 显式指定标准答案 yaml（不自动推断）
./tools/answer-card-review/answer-card-review <dir> \
  --standard knowledge-base/mock-exams/physics/beijing/2026-chaoyang-yi.yaml

# 批量：某学生所有考试
./tools/answer-card-review/answer-card-review --student-all students/jiaxiaoqi
```

## 检测项

**题目级**
- `no_answer` — 未识别到作答（可能涂得太浅）warn
- `ocr_fail` — OCR 异常（conf ≤ 0.3，整段失败）error
- `low_conf` — 低置信度（conf ≤ 0.5）warn
- `multi_all` — 多选题选了全部 4 个 warn
- `multi_single` — 多选题只选 1 个，可能漏选 warn
- `partial_correct` — 漏选（学生选 ⊂ 标准）warn
- `extra_select` — 多选（学生选 ⊃ 标准）error
- `wrong` — 答错（学生 ≠ 标准）error

**卡级**
- `no_name` — 学生姓名为空
- `no_exam_id` — 考号为空
- `no_answers` — 未识别到任何答案
- `missing_qs` — 标准答案有但学生作答缺的题号列表

## 标准答案自动推断

工具从学生考试目录名 `<exam-slug>-<subject>` 自动推断标准答案 yaml：

```
students/jiaxiaoqi/2026-chaoyang-yi-physics/
   ↓ slug 拆分：base=2026-chaoyang-yi, subject=physics
   ↓ rglob 找
knowledge-base/mock-exams/physics/<region>/2026-chaoyang-yi.yaml
```

如果失败（或想用其他源），用 `--standard <yaml-path>` 显式指定。

## 页面操作

- **筛选**：全部 / 答错 / 有警告 / 未作答
- **📷 查看原图**：弹窗显示 `answer-card-photos/` 全部原始照片（base64 内嵌，自包含）
- **侧栏**：批量加载时切换不同学生的卡

## 文件结构

```
tools/answer-card-review/
├── README.md
├── answer-card-review              # bash launcher
├── answer_card_review.py           # Python 主程序
└── templates/
    └── index.html                  # HTML/CSS/JS 模板
```

## 依赖

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- 浏览器

无后端，HTML 自包含（原图以 base64 内嵌）。
