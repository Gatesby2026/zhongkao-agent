# scripts/ — 流水线脚本

跟 Web 端 (`admin/`)、小程序 (`miniprogram/`)、后端 (`backend/`) 平行的"无服务"脚本集合，按职责分四类。

| 子目录 | 职责 | 关键产物 |
|--------|------|---------|
| [`knowledge-base/`](./knowledge-base/) | 教辅 docx/PDF → 题库 YAML + 质量检查 | `knowledge-base/question-banks/<科目>/...` |
| [`exam-ocr/`](./exam-ocr/) | 中考试卷扫描页 → 结构化题库（Qwen + Aliyun 多引擎融合） | `admin/data/<集合>/processed/<科目>/structured-cloud/final.{md,json}` |
| [`answer-card-ocr/`](./answer-card-ocr/) | 学生答题卡（手写）OCR | `knowledge-original/<集合>/answer-card-ocr/IMG_*.md` |
| [`student-report/`](./student-report/) | 综合题库 + 答题卡 + 小分 → 学情分析 PDF | `learning situation/<学生>_<集合>_<科目>.pdf` |

## 上下游关系

```
[docx / PDF 教辅] ──→ knowledge-base/  ──→  knowledge-base/question-banks/

[试卷扫描页]      ──→ exam-ocr/        ──→  admin/data/processed/<科目>/structured-cloud/
                          ↓
                  RECIPE-beijing-exam-fetch.md
                  （北京中考一/二模检索方法）

[学生答题卡照片] ──→ answer-card-ocr/ ──→  answer-card-ocr/IMG_*.md
                          ↓
              [小分 xlsx] +
                          ↓
                     student-report/     ──→  learning situation/*.pdf
```

## 不在这里的脚本

- `admin/scripts/paper-scout.js` — Node 端、`admin/package.json` 的 `npm run scrape:papers` 入口，跟 Next.js 项目绑定，留在 `admin/scripts/`
