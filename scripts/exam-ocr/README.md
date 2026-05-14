# scripts/exam-ocr/ — 试卷 OCR + 答案抽取

历史 OCR pipeline notes（早期 Codex 工作）+ 新增 `extract_answer_key.py`（2026-05-14）。

## 🎯 主入口：`extract_answer_key.py`

从试卷扫描页（含答案页）→ 标准 `answer-key.json`。

```bash
python3 extract_answer_key.py \
    --paper paper.json \
    --pages paper-images/page-*.png \
    --output answer-key.json
```

### 工作流（两阶段）

1. **答案页识别 + OCR**（`qwen-vl-ocr-latest`）
   - 对每页 OCR，找含"答案"/"评分标准"/"参考答案"关键字的页
   - 输出纯文本
2. **结构化对齐**（`qwen-max`）
   - 把答案页 OCR 文本对齐到 `paper.json` 里的每道题
   - 输出标准 `answer-key.json`：选择/多选/填空/大题各按 schema 类型

### 实测准确率（朝阳一模 物理）

| 题型 | 准确率 |
|------|--------|
| 单选（Q1-Q12） | **12/12** ✅ |
| 多选（Q13-Q15） | **3/3** ✅ |
| 填空（Q16-Q19） | **4/4** ✅ |
| 实验/计算（Q20-Q26） | **7/7 大体完整**（图描述/数学公式格式有损） |
| **总计** | **26/26** |

### 已知局限

- 电路图、几何示意图等**图形描述会丢失**（OCR 抓不到图）
- LaTeX 公式格式可能跟手工版略有差异（语义等价但风格不同）
- 答案页里"答案 + 评分要点"混在一起时，`keySteps` 可能不全

---

## 完整试卷 OCR pipeline（早期 Codex 工作）

This note records the OCR lessons from the 2026 Beijing Chaoyang Grade 9 first mock paper extraction work.

## Where To Keep This Knowledge

- Keep project-specific OCR pipeline decisions in this repository, not in memory.
- Use memory only for stable user preferences, account context, and operational shortcuts.
- Create a reusable Codex skill only after the workflow is stable across multiple projects.
- Never store API keys or server passwords in docs. Use environment variables or the existing secret manager.

## Tested Inputs

- Dataset: `data/chaoyang-2026-yimo`
- Main sample page: math page 2
- Known difficult cases:
  - Question 8: PaddleOCR missed the question header and formula line.
  - Question 11: PaddleOCR missed the main fractional equation.
  - Math formulas and tables need higher fidelity than plain OCR text.

## OCR Engines Tested

### PaddleOCR

Environment on ECS:

- `paddlepaddle==2.6.2`
- `paddleocr==2.7.3`
- `numpy==1.26.4`

Works well for bulk low-cost OCR and produces usable page text quickly.

Observed weakness:

- Can miss compact formula/question-header lines.
- On math page 2 it missed question 8's header/formula line and question 11's fractional equation.
- It is not reliable enough as the sole source for final math structure.

Use PaddleOCR as the first-pass local OCR and fallback text source.

### Alibaba Cloud OCR: Education Scenario

Product family: Alibaba Cloud OCR `ocr-api`, education scenario.

Useful APIs:

- `recognize-edu-paper-ocr`: full-page K12 OCR. Good formula text and line coordinates.
- `recognize-edu-paper-cut`: question segmentation. Returns `subject_list`, question ids, content boxes, and word-level OCR.
- `recognize-edu-paper-structed`: page layout, tables, text blocks, and figures.

Best observed behavior:

- `paper-cut` correctly segmented math page 2 into questions `7,8,9,10,11,12,13,14`.
- `paper-ocr` recognized key formulas:
  - Question 8: `y = \frac { 2 } { x }`
  - Question 11: `\frac { 2 } { x + 3 } = \frac { 1 } { x }`
- `paper-structed` is useful for preserving tables and figures, but is not the primary question boundary source.

Recommended use:

- Use `recognize-edu-paper-cut` as the structural backbone.
- Use `recognize-edu-paper-ocr` to supplement formula text.
- Use `recognize-edu-paper-structed` to preserve tables and figure coordinates.

### Alibaba Cloud Bailian / DashScope Qwen OCR

Model family: Qwen OCR through DashScope / Bailian.

Recommended model:

- `qwen-vl-ocr-latest`

Authentication:

- Use `DASHSCOPE_API_KEY`.
- Do not hard-code the key in new scripts or docs.

Observed behavior:

- With a generic prompt, Qwen OCR produces polished LaTeX but may rewrite layout into `enumerate`, losing original visible question numbering.
- With a strict prompt, it returned useful structured question blocks for math page 2 and preserved question numbers `7-14`.
- It handled formulas and tables better than PaddleOCR:
  - Question 8: `y = \frac{2}{x}(x > 0)`
  - Question 11: `\frac{2}{x+3} = \frac{1}{x}`
  - Question 13 table was converted into a clean Markdown table.

Risk:

- It can normalize punctuation, spacing, and phrasing.
- Treat it as an intelligent repair/refinement pass, not as a strict raw OCR source.

Recommended prompt style:

```text
You are an OCR engine, not a layout assistant.
Preserve visible question numbers.
Do not renumber questions.
Do not rewrite question text.
Use inline LaTeX for formulas.
Use [figure] placeholders for figures.
Use Markdown tables only when the source has a table.
Return structured JSON with question number, type, stem, options, figures, and uncertain_notes.
```

## Recommended Pipeline

### Cloud-First Production Baseline

For production batch extraction, use this as the default path:

1. Run Qwen OCR on every paper page with a strict OCR prompt.
2. Run Alibaba Cloud Education OCR on every paper page.
3. Run Alibaba Cloud Education Cut on every paper page.
4. Normalize model responses aggressively:
   - plain text JSON
   - Markdown fenced JSON
   - nested `text: { key_items: [...] }`
   - malformed JSON with an otherwise recoverable `text` field
   - empty top-level `text` where useful text appears in `key_items`
5. Fuse per question:
   - prefer Qwen text when it is complete and not hallucinated
   - use Education Cut for question boundaries and missed inline question markers
   - use Education OCR when Qwen misses a page, returns only a keyword, or hallucinates repeated content
6. Run deterministic validation:
   - expected question count per subject
   - missing and duplicate question numbers
   - subject-specific critical checks
   - answer page exclusion
7. Only use PaddleOCR as a low-cost local baseline or emergency fallback, not as the production primary source.

This is the current best practice from the Chaoyang 2026 first mock validation. The earlier “Paddle first, cloud enhance” flow is useful for exploration, but it should not be the default production architecture.

### Legacy/Exploratory Pipeline

1. Download paper images and keep source URL manifests.
2. Run PaddleOCR for cheap first-pass text and searchable raw OCR.
3. Run Alibaba `recognize-edu-paper-cut` to get question boundaries.
4. Run Alibaba `recognize-edu-paper-ocr` for formula-rich page text.
5. Run `recognize-edu-paper-structed` when a page has tables, diagrams, or layout-sensitive content.
6. Run `qwen-vl-ocr-latest` only on difficult pages or question crops to repair formulas, tables, and mixed layout.
7. Merge outputs by question id:
   - boundary from `paper-cut`
   - raw text from PaddleOCR
   - formulas from `paper-ocr`
   - tables/figures from `paper-structed`
   - final repair from Qwen OCR
8. Mark merged questions with provenance and `needs_review` when engines disagree.

## Practical Quality Rules

- Never trust one OCR engine for math.
- Always compare formula-bearing questions against at least one cloud OCR result.
- Preserve source image page and crop coordinates for audit.
- For Chinese/English reading passages, group passage text with following questions, but keep passage blocks separate from individual question blocks.
- For answers, detect answer pages/sections and store them separately from questions.
- Store OCR outputs under `processed/<subject>/` with per-engine subdirectories.

## Current Sample Outputs On ECS

Cloud-first structured outputs:

- `processed/<subject>/cloud-ocr/qwen/`
- `processed/<subject>/cloud-ocr/aliyun-ocr/`
- `processed/<subject>/cloud-ocr/aliyun-cut/`
- `processed/<subject>/structured-cloud/final.json`
- `processed/<subject>/structured-cloud/final.md`
- `processed/<subject>/structured-cloud/validation-report.json`
- `processed/structured-cloud-index.json`

Validated sample result:

- Chinese: 27/27, including `矗（zhù）` critical phonetic trap and question 3 options.
- Math: 28/28, including question 8 `y=ax+3` / `2/x` and question 11 `2/(x+3)=1/x`.
- Physics: 26/26.
- English: 38/38, including separate questions 21, 22, and 23.
- Morality and Law: 25/25.

Legacy math page 2 comparison outputs were saved under:

- `processed/math/aliyun-education-page-02/`
- `processed/math/dashscope-qwen-vl-ocr-page-02/`
- `processed/math/aliyun-page-02/`

The corrected math draft now includes:

- Question 8 function: `y=2/x`
- Question 11 equation: `2/(x+3)=1/x`
