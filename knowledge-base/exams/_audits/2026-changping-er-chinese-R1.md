# 2026 北京昌平区 二模 chinese — R1 大模型审核报告

- yaml: `knowledge-base/exams/mock/chinese/beijing/2026-changping-er.yaml`
- 源 docx: `knowledge-original/zxxk-downloads/2026-ermu-chinese/changping_chinese.docx`
- final.json: `knowledge-base/exams/_staging/chinese/2026-changping-er/structured-cloud/final.json`
- parser: `scripts/exam-docx/chinese_docx_paper.py`

## OVERALL：FAIL（P0 parser bug，与 pinggu 同根）

yaml 52 题/139 分，期望 26 题/100 分。题号 1-26 出现两次（第一遍真试题，第二遍参考答案被误算成新题）。**与 pinggu 是完全同一类型 docx 结构 + 同一 parser bug**，pinggu 通过下游 _patches 强行删除幽灵题才落到 27 题，未触及 parser 根因。

---

## 1. docx 内部结构（解压实测）

`/tmp/changping_docx/word/document.xml` 文本流（去标签后）共 125 个非空行：

- 行 0-114：题面（封面 + 一/二/三大题 + 26 题题面 + 作文）
- 行 115：**唯一答案区切换 marker `参考答案`**（独占段）
- 行 116-124：**全部 26 题答案压在 9 个段落里**，形如：

```
116: 1.D2.C3.修改：...4.①东晋 ②杜甫5.A6.示例：...
117: 7.千树万树梨花开8.猿鸟乱鸣...9.示例：...
118: 10.①古人和来者②苍凉雄浑、孤寂悲凉11."悠悠"...
...
124: 26.略
```

**关键统计**：

| 标记 | 出现次数 |
| --- | --- |
| `【答案】` | **0** |
| `【N题详解】` | **0** |
| `【详解】` | **0** |
| `【解析】` / `【点睛】` | **0** |
| `参考答案` | 1 |
| `一、` / `二、` / `三、` | 各 1（仅出现在题面，答案区无重复大题头） |

## 2. 与 pinggu 对比

pinggu_chinese.docx 文本流 247 行，`参考答案` 在行 125，紧跟 `一、基础·运用（共14分）` + `1.C（共2分）` + `2.D（共2分）` …，同样 `【答案】=0 / 【详解】=0`。**两区 100% 同型**：

- 共同点：**单一 `参考答案` 锚 + 答案区无 `【...】` markers + 答案串行压段（pinggu 一题一段、changping 多题一段）**
- 差异：pinggu 在 `参考答案` 后**重复了一遍 `一、基础·运用`** 大题头，触发 parser SECTION_HEADERS 命中 → 又开了一组新 question；changping 答案区**无任何大题头**，全靠 `1.D2.C...` 这种 `NUM_HEAD_RE` 命中开新题。两者最终症状一致（题数翻倍），路径不同。

## 3. parser 失败点（chinese_docx_paper.py）

第 218 行 `NOISE_LINE_RE` 把 `参考答案` 当噪声直接 drop。第 259-268 行入 answer 模式**只认 `【答案】/【详解】/【解析】/【点睛】/【导语】/【N题详解】`**。changping 的 `参考答案` **既不是 noise 应丢弃，也无法触发 mode = "answer"**：

```
当前控制流：
  参考答案    → NOISE drop（mode 仍 question）
  1.D2.C3...  → NUM_HEAD_RE 命中 → 当成新题 Q1 stem 起头
  ...         → 一直 question 模式累计到 Q26 → ghost 26 题
```

## 4. 应该在哪个 marker 切 mode

**`参考答案`（独占段、行首、可带"及评分标准"后缀）必须是 mode = "answer" 切换信号**，且**之后整段 docx 不再开新题、不再切 section、不再触发 SUB_HEADER**。这是单 marker 一次性吸收。

## 5. Fix 建议（按优先级）

### P0 fix（parser，根治 pinggu + changping）

在 `chinese_docx_paper.py` 第 218 行**移除** `参考答案|答案及评分` 出 NOISE_LINE_RE；在 207 行附近**新增**：

```python
# 整卷尾部"参考答案"独占段：之后所有内容一次性归 answer 模式
GLOBAL_ANSWER_HEADER_RE = re.compile(
    r"^\s*(?:参考答案(?:[与及]评分(?:标准|参考|建议))?|答案及评分(?:标准|参考)?)\s*$"
)
```

在 249 行 `for ln in lines:` 主循环开头（早于 sec_m 判定）插：

```python
if GLOBAL_ANSWER_HEADER_RE.match(ln):
    if mode == "question":
        a_lines.append(f"__Q_CTX__:{last_q_seen}")
    mode = "answer_global"   # 新增吸收态：永不退出，忽略 SECTION/SUB/NUM_HEAD
    a_lines.append(ln)
    continue
if mode == "answer_global":
    a_lines.append(ln)
    continue
```

并在 `_parse_answers` 里识别 `1.D2.C3.X` 这类**单段多题串行答案**：用 `re.split(r"(?=(?<![0-9])\d{1,2}\s*[.、．])", line)` 拆段并按 `__Q_CTX__` 推进 q_num。

### P0 fix（changping yaml 立即清理）

在 `_patches/chinese/2026-changping-er.yaml` 删 Q27-Q52 全部 52 个幽灵节点（保留 Q1-Q26），把对应 26 题答案分发回 Q1-Q26 的 `answer` 字段。pinggu 同款 patch 模式可参考。

### P1（cross-check）

跑完 parser fix 后对 14 区 chinese docx 回归：扫 `【答案】` / `【详解】` 计数为 0 的所有区，确保都走新的 `answer_global` 路径。当前确认昌平/平谷 = 0 marker，其余 12 区应有 `【答案】`/`【详解】` 不走该分支。
