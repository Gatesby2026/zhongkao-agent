# /convert-docx — 批量转换 docx 试卷为结构化 YAML

将 knowledge-original 目录下的 docx 模考试卷，通过以下 pipeline 转为 knowledge-base 中的 YAML：

```
docx → LibreOffice HTML → Qwen-VL OCR公式 → LaTeX文本 → 结构化YAML
```

## 使用方式

用户可能的指令：
- `/convert-docx` — 转换所有新增的 docx
- `/convert-docx 2025海淀一模` — 转换指定试卷
- `/convert-docx --force` — 强制重新转换所有
- `/convert-docx --dry-run` — 只预览不执行

## 执行步骤

### 1. 环境检查
运行以下检查，如有缺失则提示用户安装：
```bash
# LibreOffice
which soffice || ls /Applications/LibreOffice.app/Contents/MacOS/soffice

# Python 依赖
python3 -c "import yaml; import bs4" 2>/dev/null || pip3 install pyyaml beautifulsoup4
```

### 2. 执行转换
根据用户参数构造命令：

```bash
# 默认：转换所有新增（跳过已有）
cd /Users/jiakui/projects/zhongkao-agent && python3 scripts/docx-pipeline.py

# 指定单文件
python3 scripts/docx-pipeline.py --file "path/to/exam.docx" --year 2025 --district 海淀 --exam-type 一模

# 强制覆盖
python3 scripts/docx-pipeline.py --force

# 预览模式
python3 scripts/docx-pipeline.py --dry-run

# 限量测试
python3 scripts/docx-pipeline.py --limit 3
```

### 3. 质量检查
转换完成后，自动抽查：
- 读取 1-2 个新生成的 YAML 文件
- 检查题目数量是否 ≥ 25（北京中考通常 28 题）
- 检查 LaTeX 公式是否正确嵌入（搜索 `$` 符号）
- 检查选择题选项是否完整（不再是空白）
- 报告转换统计和质量评估

### 4. 更新知识库加载
如果有新的 YAML 文件生成，检查 `app/lib/knowledge-base.ts` 中的 `loadMockExams()` 函数是否能自动加载（该函数会扫描目录下所有 .yaml 文件，通常无需修改）。

## 注意事项
- OCR 缓存在 `scripts/.ocr-cache/ocr-results.json`，相同公式图片不会重复调用 API
- API Key 已内置在脚本中，也可通过环境变量 `DASHSCOPE_API_KEY` 覆盖
- 每个 docx 文件转换约需 30-60 秒（取决于公式数量和网络速度）
- 转换 HTML 临时文件存放在 `/tmp/docx-pipeline/`

## 输出格式
每个 YAML 文件结构：
```yaml
year: 2025
district: 海淀区
exam_type: 一模
questions:
  - id: 1
    type: 选择
    score: 2
    question: "下列图形中，是中心对称图形的是（）\nA. $...$  B. $...$"
    answer: "A"
    solution: "..."
    knowledge_points: [中心对称图形]
    module: geometryComprehensive
    difficulty: 基础
    recommended_for: [L0, L1, L2, L3]
```
