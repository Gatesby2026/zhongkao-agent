# Skill: 试卷图片 → YAML 知识库流水线操作手册

> 这是给 Claude 自己看的执行手册。当需要处理试卷 OCR、enrich 或 YAML 审核任务时，直接查此文件。

---

## 一、流水线全貌

```
试卷图片(PNG)
  ├─ [阶段 1] OCR → paper.json + answer-key.json
  ├─ [阶段 2] Enrich → YAML 草稿
  └─ [阶段 3] QC + 修订 → 最终 YAML 入库
```

### 阶段 1：OCR（ocr_paper.py）

| 项目 | 说明 |
|------|------|
| **输入** | `data/exams/<exam>/images/` 下的 PNG 图片（按页命名：page-01.png…） |
| **输出** | `data/exams/<exam>/paper.json`（题目结构）、`answer-key.json`（答案） |
| **工具** | `ocr_paper.py`，调用 Qwen-VL-OCR（阿里云百炼） |
| **质量要求** | 每题必须有 `id`、`type`、`score`、`stem`；选择题应有 `options`（无法获取图片选项时标记 `has_image_options: true`）；`answer-key.json` 解析题应包含 `correctSolution` |

**阶段 1 质量门控（进入阶段 2 的前提）：**
- `questions` 数组非空
- 每题 `id` 唯一
- 选择题：`options` 字段存在 **或** `has_image_options: true` 已标记
- 答案页：每题 `correct` 字段存在；实验/计算题 `correctSolution` 不为空字符串

---

### 阶段 2：Enrich（enrich_to_mock_exam.py）

| 项目 | 说明 |
|------|------|
| **输入** | `paper.json` + `answer-key.json` |
| **输出** | `knowledge-base/mock-exams/<subject>/beijing/<year>-<district>-<type>.yaml` |
| **工具** | `enrich_to_mock_exam.py`，调用 qwen-max |
| **质量要求** | YAML 每条记录的 `stem` 和 `options` 分离存储；`qc_status` 字段写入；`has_image_options` 正确传递；`solution` 非空（如来源为空则填 `__MISSING__` 而非空字符串） |

**阶段 2 质量门控（进入阶段 3 的前提）：**
- YAML 文件可被 `python -c "import yaml; yaml.safe_load(open('xxx.yaml'))"` 无异常解析
- 无 `solution: ''`（必须写 `__MISSING__` 或真实内容）
- `qc_status` 字段存在于每条记录

---

### 阶段 3：QC + 手工/自动修订（入库）

| 项目 | 说明 |
|------|------|
| **输入** | 阶段 2 输出的 YAML 草稿 |
| **输出** | 经过验收的最终 YAML，git commit 入 knowledge-base |
| **工具** | Claude 人工审核 + 必要时重跑单题 OCR / 手工补全 |
| **质量要求** | `qc_status: verified` 或 `qc_status: needs_review`（后者附 `qc_note` 说明原因）；选项混入问题已修正；solution 完整 |

---

## 二、新的 YAML Schema 设计（目标态）

```yaml
- id: 1
  type: 单选                    # 单选 / 填空 / 简答 / 计算 / 实验
  score: 2
  stem: '下列物品中，通常情况下属于导体的是'   # 纯题干，不含选项
  options:                       # 选择题专用；非选择题省略此字段
    A: 陶瓷杯
    B: 橡皮
    C: 钢尺
    D: 塑料水瓶
  has_image_options: false        # true = 选项是图片，options 字段不可信
  answer: C
  solution: '钢尺是金属材质，金属是导体...'   # 解题步骤；缺失时写 __MISSING__
  knowledge_points:
    - 导体与绝缘体
  module: electricity
  difficulty: 基础
  recommended_for: [L0, L1, L2, L3]
  source_pages: [page-01]        # 来源页
  qc_status: verified            # verified / needs_review / ocr_failed
  qc_note: ''                    # qc_status=needs_review 时写明原因
```

**关键字段规则：**

| 字段 | 规则 |
|------|------|
| `stem` | 只含题干文字，不含 A/B/C/D 选项行 |
| `options` | 仅选择题写；key 为大写字母，value 为文字内容 |
| `has_image_options` | OCR 无法提取选项时置 `true`，`options` 同时写 `{}` 或省略 |
| `solution` | 从 answer-key 解析页提取；无法获取写 `__MISSING__` |
| `qc_status` | 三态：`verified` / `needs_review` / `ocr_failed` |
| `qc_note` | 状态不是 verified 时必填，说明具体问题 |

---

## 三、各阶段 Validate 规则

### 阶段 1 验证（paper.json）

```bash
# 快速检查 paper.json 完整性
python3 - <<'EOF'
import json, sys

with open("data/exams/<exam>/paper.json") as f:
    data = json.load(f)

errors = []
ids = set()
for q in data.get("questions", []):
    qid = q.get("id", "?")
    if qid in ids:
        errors.append(f"重复 id: {qid}")
    ids.add(qid)
    if not q.get("stem"):
        errors.append(f"{qid}: stem 为空")
    if q.get("type") == "choice":
        if not q.get("options") and not q.get("has_image_options"):
            errors.append(f"{qid}: 选择题缺少 options 且未标记 has_image_options")

with open("data/exams/<exam>/answer-key.json") as f:
    ak = json.load(f)

for a in ak.get("answers", []):
    if not a.get("correct"):
        errors.append(f"answer-key {a.get('id')}: correct 为空")

if errors:
    print("FAIL:")
    for e in errors: print(" -", e)
    sys.exit(1)
else:
    print("OK")
EOF
```

### 阶段 2 验证（YAML）

```bash
# 验证 YAML 可解析 + 关键字段
python3 - <<'EOF'
import yaml, sys

with open("knowledge-base/mock-exams/<subject>/beijing/<file>.yaml") as f:
    records = yaml.safe_load(f)

errors = []
for r in records:
    rid = r.get("id", "?")
    if r.get("solution") == "":
        errors.append(f"id={rid}: solution 为空字符串，应写 __MISSING__")
    if "qc_status" not in r:
        errors.append(f"id={rid}: 缺少 qc_status 字段")
    if r.get("type") == "单选" and "stem" not in r:
        errors.append(f"id={rid}: 单选题缺少 stem 字段")

if errors:
    print("FAIL:")
    for e in errors: print(" -", e)
    sys.exit(1)
else:
    print(f"OK: {len(records)} 条记录通过验证")
EOF
```

---

## 四、常见失败模式及处理方式

### 4.1 图片选项题（has_image_options）

**症状：** 选项内容是实物图/情景图，OCR 原来只输出裸字母 `A\n\nB\n\nC\n\nD`。

**OCR prompt 已加规则（scripts/exam-ocr/ocr_paper.py）：**
> 如果某个选项的内容是图片而非文字，写成「A. [图]」，不要只写字母 A。

**结构化 prompt 已加规则：**
> options 全为 "[图]" 时，has_image_options 置 true。

**期望输出：**
```json
{
  "stem": "3. 如图所示的实例中，目的是为了增大摩擦的是",
  "options": {"A": "[图]", "B": "[图]", "C": "[图]", "D": "[图]"},
  "has_image_options": true
}
```

**后续处理：** enrich 阶段写 `qc_status: needs_review`，`qc_note: '选项为图片，需人工补全'`。不要猜选项内容，宁缺毋错。

---

### 4.2 图注混入选项文本

**症状：** 选项文字中夹杂图注（如 `"A. 紫外线 透镜组 光刺胶"`），选项之间无换行。

**根本原因：** OCR prompt 未明确区分"题目正文"和"图中标注文字"，模型把图注当正文转录。

**OCR prompt 已加规则（scripts/exam-ocr/ocr_paper.py）：**
> 图中的标注文字（箭头所指的零件名、物理量符号、图例标签等）属于 [图] 的一部分，不要把它们单独转录到题目正文或选项文字中。

**若仍出现（prompt 未生效）：**
1. 标记 `qc_status: needs_review`，`qc_note: '图注混入选项，需人工拆分'`。
2. 人工审核时，对照原图逐项修正 options 字段。
3. 不要用启发式正则猜分割点，容易把正确选项拆错。

---

### 4.3 OCR 乱码（LaTeX/数学公式混入）

**症状：** stem 或 options 中出现 `{ R _ { 0 }`、`s \widehat`、`\begin{enumerate}` 等 LaTeX 片段。

**识别方法：**
```python
import re
GARBAGE_PATTERN = re.compile(r'\\[a-zA-Z]+|_\s*\{|\^\s*\{|\{[^}]{0,10}\}')
if GARBAGE_PATTERN.search(text):
    # 疑似乱码
```

**处理方式：**
1. 触发重跑：对该题所在页单独调用 vl-max（更强模型）重跑 OCR。
2. 重跑仍失败：`qc_status: ocr_failed`，`qc_note: '数学公式/图形题，OCR 无法识别'`。
3. 该题暂不入库，记录到待人工处理列表。

---

### 4.4 实验/计算题 solution 缺失

**症状：** answer-key.json 中只有 `correct: "不变, 晶体, 引力"`，无 `correctSolution` 字段。

**根本原因：** 答案页的解题步骤没有被 OCR 提取（当前流水线只提取答案字母，不提取解析文字）。

**处理方式（短期）：**
- enrich 脚本检测到 `correctSolution` 缺失时，写 `solution: __MISSING__`，`qc_status: needs_review`，`qc_note: '解题步骤未从答案页提取'`。

**处理方式（中期）：**
- ocr_paper.py 增加"答案解析页"专项 prompt，单独提取解析文字，存入 `answer-key.json` 的 `correctSolution` 字段。
- prompt 要点：让模型区分"答案"（简短）和"解析/解题过程"（详细步骤），分别输出。

---

### 4.5 stem 和 options 混在一个大字符串中（现有 YAML 的历史问题）

**症状：** YAML `question` 字段是 `stem + \n + A. xxx\nB. xxx...` 的大字符串 blob。

**识别方法：** 字段名是 `question` 而非 `stem`；或 `stem` 字段包含 `\nA.` 模式。

**处理方式（批量修复历史 YAML）：**
```python
import re, yaml

def split_stem_options(text):
    """从大字符串里拆出 stem 和 options dict"""
    pattern = re.compile(r'\n([A-D])[\.、．]\s*(.+?)(?=\n[A-D][\.、．]|\Z)', re.DOTALL)
    options = {}
    for m in pattern.finditer(text):
        options[m.group(1)] = m.group(2).strip()
    stem = pattern.split(text)[0].strip()
    return stem, options
```

注意：这个函数对图注混入场景不可靠，修复后仍需人工抽查。

---

## 五、Claude 操作此流水线的标准命令

### 5.1 对单卷跑完整流水线

```bash
cd /Users/jiakui/projects/zhongkao-agent

# 阶段 1：OCR（输入目录含 page-*.png）
python3 scripts/exam-ocr/ocr_paper.py \
  data/exams/2026-haidian-yi-physics \
  --subject physics
# 输出：data/exams/2026-haidian-yi-physics/structured-cloud/final.json（需转换为 paper.json 格式）

# 阶段 2：Enrich
python3 scripts/knowledge-base/enrich_to_mock_exam.py \
  --paper data/exams/2026-haidian-yi-physics/paper.json \
  --answer-key data/exams/2026-haidian-yi-physics/answer-key.json \
  --subject 物理 \
  --cache-prefix 2026-haidian-yi-physics \
  --output knowledge-base/mock-exams/physics/beijing/2026-haidian-yi.yaml

# 阶段 3：审核后入库
git add knowledge-base/mock-exams/physics/beijing/2026-haidian-yi.yaml
git commit -m "feat(kb): 2026 海淀一模物理入库"
git push
```

### 5.2 批量跑多卷（parallel）

```bash
# 用 GNU parallel 并发跑 OCR，控制并发数避免 API 限流
ls data/exams/ | parallel -j 3 \
  python3 scripts/exam-ocr/ocr_paper.py data/exams/{} --subject physics
```

### 5.3 查看哪些卷 solution 缺失

```bash
python3 - <<'EOF'
import yaml, glob, os

missing = []
for f in glob.glob("knowledge-base/mock-exams/**/*.yaml", recursive=True):
    with open(f) as fp:
        records = yaml.safe_load(fp) or []
    for r in records:
        if r.get("solution") in ("", "__MISSING__", None):
            missing.append(f"{os.path.basename(f)} id={r.get('id')} type={r.get('type')}")

print(f"共 {len(missing)} 条 solution 缺失:")
for m in missing[:30]: print(" -", m)
EOF
```

### 5.4 查看 needs_review / ocr_failed 题目

```bash
python3 - <<'EOF'
import yaml, glob

for f in glob.glob("knowledge-base/mock-exams/**/*.yaml", recursive=True):
    with open(f) as fp:
        records = yaml.safe_load(fp) or []
    for r in records:
        if r.get("qc_status") in ("needs_review", "ocr_failed"):
            print(f"{f}  id={r.get('id')}  [{r.get('qc_status')}]  {r.get('qc_note','')}")
EOF
```

### 5.5 对单题重跑 OCR（vl-max 强模型）

```bash
# 指定页面重跑，输出合并回 paper.json
python3 scripts/ocr_paper.py \
  --exam 2026-chaoyang-yi-math \
  --pages page-03 page-04 \
  --model qwen-vl-max \
  --merge-into data/exams/2026-chaoyang-yi-math/paper.json
```

---

## 六、大规模运行时的注意事项

### API 限流

- 百炼 Qwen-VL-OCR：默认 QPS 较低，并发建议 ≤ 3，批次间加 sleep(1)。
- qwen-max（enrich）：token 消耗大，并发建议 ≤ 2。
- 出现 429 时，exponential backoff，最长等待 60 秒，超过 3 次失败记录到 `failed_exams.txt` 跳过，不要死循环重试。

### 进度记录

- 每跑完一卷立即写入 `data/pipeline_progress.jsonl`，格式：`{"exam": "...", "stage": 1, "status": "ok", "ts": "..."}`。
- 重跑前先读进度文件，跳过已完成的卷。

### 费用控制

- 每页 OCR 约 0.01-0.03 元，100 页 = 约 3 元。
- 每题 enrich 约 0.005 元，一卷 26 题 = 约 0.13 元。
- 批量跑前估算总费用：`总页数 × 0.02 + 总题数 × 0.005`。

### 错误分类

| 错误类型 | 处理方式 |
|----------|----------|
| API 超时 / 网络错误 | 重试 3 次后跳过，记录 failed |
| OCR 输出为空 | 检查图片是否损坏，标记 `ocr_failed` |
| JSON parse 失败 | 尝试 struct retry（用结构化 output prompt 重跑） |
| YAML 写出后 parse 报错 | 检查 solution 里的特殊字符，用 yaml.dump 而非手拼字符串 |

### Git 提交节奏

- 每区每科一次 commit，不要一次提交几十个文件。
- commit message 格式：`feat(kb): 2026 <区> 一模 <科目> 入库（<N> 题）`
- 入库前必须跑阶段 2 验证脚本，不允许带 `qc_status: ocr_failed` 的记录入库。

### 本地路径约定

```
/Users/jiakui/projects/zhongkao-agent/
├── data/
│   ├── exams/<exam>/
│   │   ├── images/          # 原始 PNG
│   │   ├── paper.json       # 阶段 1 输出
│   │   └── answer-key.json  # 阶段 1 输出
│   └── pipeline_progress.jsonl
├── scripts/
│   ├── ocr_paper.py
│   └── enrich_to_mock_exam.py
└── knowledge-base/
    └── mock-exams/
        └── <subject>/beijing/<year>-<district>-<type>.yaml
```

---

## 七、历史遗留 YAML 修复优先级

按以下顺序处理存量问题：

1. **`qc_status` 字段缺失** → 批量加字段脚本，根据 `solution` 是否为空、`has_image_options` 推断初始状态。
2. **`solution: ''`** → 批量替换为 `__MISSING__`，同时设 `qc_status: needs_review`。
3. **`question` 大字符串 blob** → 用 `split_stem_options()` 函数拆分，人工抽查 10% 结果。
4. **图片选项题** → 标记 `has_image_options: true`，需对照原卷补全选项。

当前已知待修复卷（来自 git status 删除记录）：changping / fangshan / mentougou / pinggu / shunyi / yanqing 等区的部分科目已被删除，说明质量不达标，需重跑 OCR 后重新入库。
