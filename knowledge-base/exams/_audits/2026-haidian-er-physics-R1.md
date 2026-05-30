# 2026 北京海淀区 物理二模 R1（docx 路线复审）

**yaml**: `knowledge-base/exams/mock/physics/beijing/2026-haidian-er.yaml`
**源 docx**: `knowledge-base/exams/_staging/physics/2026-haidian-er/src-unzip/精品解析：2026年北京市海淀区中考二模考试物理（解析版）.docx`
**已知**: 25 题 / 65 分 → 应 26 题 / 70 分（差 1 题 / 5 分）

## OVERALL: NEEDS_FIX（缺 Q17 / 5 分）

---

## 1. 缺哪题？

**Q17（实验探究，5 分，沸腾 + 二氧化氮扩散）**

源 docx 段落实测（解析版 document.xml）：
- 段 235 三、实验探究题（共28分，**16题4分，17、22题各5分**，18题2分，19、20、21、23题各3分）
- 段 236 `16. `（题头单独一段，body 在 237/239）
- 段 247 `17. `（题头单独一段，body 在 248/250）
- 段 261 `18. 小明利用如图所示的装置...`
- …
- 段 434 `26. ...`

源 docx 共 **26 题（1-26）**，yaml ids 1..16, 18..26 = **25 题，缺 Q17**。

Q17 题面（确认存在）：
- (1) 沸腾前后温度随吸热变化（图甲/乙/丙）
- (2) 二氧化氮扩散实验（图丁）
- 答案 (1) 乙 / 加热时间 / 温度不变；(2) 铅柱拉不开 / 分子间引力

## 2. parser 哪里漏识别

定位：`scripts/exam-docx/physics_docx_paper.py` 主状态机 **354-369 行**。

**根因**：Q16 题面后紧接 `【答案】… 【16题详解】… 【17题详解】…`，parser 进入 `mode=answer`。然后遇到 `17. `（独立一行、题头空、body 在后续段），落入 "answer→question 切换"：

```python
# L357-369
if (mode == "answer" and q_m and "【" not in ln):
    n = int(q_m.group(1))
    if n > last_q_seen and n <= 30:
        min_len = 6 if cur_typ == "essay" else 15
        if len(ln.strip()) >= min_len:   # ← `17. ` len=3 → 失败
            mode = "question"; ...
```

`17. ` 整行长度 3 < 15 → 不切回 question → Q17 头与 (1)(2) body 全留 a_lines，不进 sections，`_parse_section` 自然不生成 Q17 question。

对比 Q16 没事：Q16 之前由 section header "三、实验探究题..." 在 332 行触发 `mode=question`，所以空头 `16. ` 在 question 模式下作为普通题号锚（`_parse_section` 不检查 rest 长度，head+body 跨段 OK）。

物理实验题"题头-body 跨段"极常见（Q16/17/18），但只有 Q17 命中"夹在前一题 answer 块之后"这一组合而触发该 bug。本地 import parser 运行验证：`nums=[1..16, 18..26]`，缺 17 复现。

## 3. 精确 fix 路径

**File**: `scripts/exam-docx/physics_docx_paper.py`
**Line**: 354-369

### 方案 A（推荐 / 物理特异，跨区长期）
在 min_len 检查处加例外：若题号锚行后 ≤5 行内出现 `（1）` 等中文括号子问号，认定 "实验题头-体跨段"，直接切回 question，不卡 min_len。

```python
# 外层循环改 enumerate(lines)
SUBQ_FOLLOW_RE = re.compile(r"^\s*[（(][1-9一二三四五][)）]")
...
if (mode == "answer" and q_m and "【" not in ln):
    n = int(q_m.group(1))
    if n > last_q_seen and n <= 30:
        has_subq = any(
            SUBQ_FOLLOW_RE.match(lines[j])
            for j in range(i+1, min(len(lines), i+6))
        )
        min_len = 6 if cur_typ == "essay" else 15
        if has_subq or len(ln.strip()) >= min_len:
            mode = "question"
            if cur_typ: sections[cur_typ].append(ln)
            last_q_seen = n
            continue
```

### 方案 B（通用 / 备选）
为实验/探究类 section 单独设 `min_len=3`（与 essay 区别开），需新增 typ 白名单。

### 方案 C（patch 救火 / 不修底层）
`_patches/physics/2026-haidian-er.yaml` 强插 Q17 完整 create。一次性救火；A/B 才是长期方案。

## 4. 修后一致性

- `total_questions: 25 → 26`
- `full_score: 65 → 70`
- `structure` "7实验探究(23分)" → "8实验探究(28分)"

`_parse_per_question_scores` 已能识别 "16题4分，17、22题各5分..."，Q17 一旦被识别即自动分 5 分。

## 5. 其他抽查（无 P0）

- Q26 yaml 在，结构正常。
- LaTeX 1901 公式块未逐一抽查（任务限缺题诊断，跳过）。
- 答案归属：Q17 丢失期间 `【17题详解】` 可能被错附邻题；修后 `__Q_CTX__:17` 自动归位，需 spot-check Q16/Q18 solution 末尾是否净化。

**优先级**：方案 A → 重跑 → diff 出 Q17 → spot-check Q16/Q18 solution。
