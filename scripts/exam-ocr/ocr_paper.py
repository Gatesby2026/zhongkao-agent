#!/usr/bin/env python3
"""单卷 OCR：images/*.png → structured-cloud/final.json

两步走（替代 ECS 上的 3 引擎融合流水线）：
  1. 逐页 Qwen-VL-OCR：试卷扫描页 → 原始 OCR 文本（保留题号 + 选项 + 答案页）
  2. 整卷 qwen-max：所有页文本 → 结构化 questions[] + answer_pages[]

输出 schema 跟 Codex `structured-cloud/final.json` 兼容：

    {
      "subject": "physics", "exam": "<exam name>",
      "page_count": 10,
      "questions": [
        {"id": "physics-q01", "number": 1, "type": "choice",
         "text": "1. ...", "options": [...], "source_page": 1},
        ...
      ],
      "answer_pages": [9, 10]
    }

CLI:
    python3 ocr_paper.py <paper-dir> --subject physics

    Reads:  <paper-dir>/images/page-*.png
    Writes: <paper-dir>/pages/page-NN.ocr.txt        (逐页 OCR 缓存)
            <paper-dir>/structured-cloud/final.json  (主成品)
            <paper-dir>/structured-cloud/final.md    (人看版)

需 DASHSCOPE_API_KEY。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import openai
except ImportError:
    print("pip install openai", file=sys.stderr); sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import derive_out_dir  # noqa: E402


SUBJECT_LABEL_CN = {
    "physics": "物理", "math": "数学", "chinese": "语文",
    "english": "英语", "politics": "道德与法治",
    "chemistry": "化学", "history": "历史", "biology": "生物", "geography": "地理",
}


# ============== client ==============

def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY 环境变量")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def _img_to_data_url(p: Path) -> str:
    b = base64.b64encode(p.read_bytes()).decode("ascii")
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b}"


# ============== step 1: per-page Qwen-VL-OCR ==============

OCR_SYS_PROMPT = (
    "你是 OCR 引擎，不是排版器。严格按图片所见逐字识别这页试卷。要求：\n"
    "\n"
    "【题号与结构】\n"
    "1. 必须以原始阿拉伯数字保留题号（如 16. 17. 18. 19. 20. ...），逐题独占一行。\n"
    "2. 严禁把题目转成 LaTeX \\begin{enumerate} / \\item 这种环境，必须保留视觉编号。\n"
    "\n"
    "【选项】\n"
    "3. 选项标签（A. B. C. D.）每个独占一行。\n"
    "4. 如果某个选项的内容是图片而非文字，写成「A. [图]」，不要只写字母 A。\n"
    "   判断依据：字母后面跟着的是图形/实物图/情景图，而不是可读文字。\n"
    "\n"
    "【图与图注】\n"
    "5. 题目中嵌入的图形（电路图、光路图、几何图、实物图等）用 [图] 单独占一行，不描述图形内容。\n"
    "6. 图中的标注文字（箭头所指的零件名、物理量符号、图例标签等）是图的组成部分，"
    "   不要把它们单独转录到题目正文或选项文字中。\n"
    "   例：图中有「紫外线→」「透镜组」「硅片」等标注，这些属于 [图]，不要出现在题目文字里。\n"
    "\n"
    "【公式与格式】\n"
    "7. 数学公式用行内 LaTeX（如 $x^2$、$F=ma$）；独立公式用 $$...$$；表格用 Markdown 表格。\n"
    "8. 不要改写题面、不要补答案、不要重新编号。\n"
    "\n"
    "【答案页】\n"
    "9. 「答案及评分参考」/「参考答案」页：照样逐题如实转录，保留题号、答案、解析步骤。\n"
    "\n"
    "【输出格式】\n"
    "10. 直接输出纯文本，不要 ```latex / ```markdown / ```json 代码围栏。"
)


def _is_garbage_ocr(text: str) -> bool:
    """检测 Qwen-VL-OCR 失败模式：
    1) 退化为目标检测（吐 pos_list / rotate_rect JSON）
    2) 把题号转换成 LaTeX enumerate 环境（吃掉视觉编号）
    """
    if not text or len(text.strip()) < 30:
        return True
    sample = text[:500]
    bad_markers = ("pos_list", "rotate_rect", '"polygons"', '"detection_result"',
                   r"\begin{enumerate}", r"\begin{itemize}")
    return any(m in sample for m in bad_markers)


def ocr_page(client, image_path: Path, retries: int = 3) -> str:
    """单页 OCR；若 qwen-vl-ocr-latest 退化（吐坐标 JSON），fallback 到 qwen-vl-max。"""
    data_url = _img_to_data_url(image_path)
    last_err = None
    # 先用 qwen-vl-ocr-latest（专 OCR 模型，质量高但偶尔退化）
    for i in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-vl-ocr-latest",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": OCR_SYS_PROMPT},
                    ],
                }],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            if not _is_garbage_ocr(text):
                return text
            print(f"    ⚠️ qwen-vl-ocr 退化（坐标 JSON），fallback qwen-vl-max", file=sys.stderr)
            break
        except Exception as e:
            last_err = e
            print(f"    ⚠️ retry {i+1}/{retries}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))

    # fallback：qwen-vl-max（通用多模态，不会输出 detection 模式）
    for i in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-vl-max",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": OCR_SYS_PROMPT},
                    ],
                }],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            if not _is_garbage_ocr(text):
                return text
            print(f"    ⚠️ qwen-vl-max 也退化，{i+1}/{retries}", file=sys.stderr)
        except Exception as e:
            last_err = e
            print(f"    ⚠️ vl-max retry {i+1}/{retries}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))

    raise RuntimeError(f"OCR failed (both vl-ocr 和 vl-max 退化): {image_path}: {last_err}")


# ============== V2: 拆分职责的流水线 ==============
# 设计原则：能用程序做的绝不用 LLM；LLM 只做分类和单题清洗。
# Step A 题号切分（程序）→ Step B 题型分类（qwen-max 单题）→
# Step C 选项剥离（程序）→ Step E 答案对齐（qwen-max 单题）→
# Step F source_page（来自 Step A 锚点）

# 答案页"强证据"：标题级别的关键词。不含"答题卡"（在考生须知里也出现）。
STRONG_ANSWER_MARKERS_RE = re.compile(
    r"(答案及评分(参考|标准|说明)?|参考答案|参考解答|答案与解析|评分标准)"
)
# 题号锚点：行首 1-99 + . / 、/ ． + 后续非空白
NUM_ANCHOR_RE = re.compile(r"(?m)^\s*(\d{1,2})\s*[.、．]\s*(?=\S)")
# 大题标题（"一、单项选择题"/"二、多项选择题..."），用于跳过 page 1 考生须知
SECTION_HEAD_RE = re.compile(r"(?m)^\s*[一二三四五六七八九十]+\s*[、，][^\n]{0,40}题")


def _classify_pages(pages_text: list[str]) -> list[bool]:
    """两步判定每页是不是答案页：
    1. 含 STRONG_ANSWER_MARKERS_RE → 答案页
    2. 试卷的格式约定：答案在试卷尾部，不与题目交错 →
       从"第一个答案页"开始，往后全部归答案页
    """
    n = len(pages_text)
    is_ans = [False] * n
    for i, t in enumerate(pages_text):
        if STRONG_ANSWER_MARKERS_RE.search(t[:400]):
            is_ans[i] = True
    # 答案页延续
    first = next((i for i, x in enumerate(is_ans) if x), None)
    if first is not None:
        for i in range(first, n):
            is_ans[i] = True
    return is_ans


def _strip_preamble(text: str, on_first_page: bool) -> str:
    """page 1 头部的考生须知/封面信息会带 "1./2./3./4." 条目，
    误匹为题号。用大题标题（"一、单项选择题"）锚点裁掉它们。
    其余页直接返回原文。
    """
    if not on_first_page:
        return text
    m = SECTION_HEAD_RE.search(text)
    if m:
        return text[m.start():]
    return text


def _pick_question_chain(matches: list, expected: int) -> list[tuple]:
    """从一页的题号锚点里挑出真正的题目链（对 OCR 题号错乱鲁棒）。

    关键事实：试卷题号是**全局连续整数** 1,2,3,…N。OCR 会把单页题号整体
    重置（如大兴 page-03 多选题 OCR 成 "1./2./3." 实为 11/12/13）或夹入
    单点跳变（如 page-07 续作行误识成 "16."）。旧版用全局 `n == expected`
    严格过滤，一旦某页 OCR 题号不接上，整页被吞并且**雪崩**吞掉其后所有页。

    新策略：取该页锚点里「连续 +1 整数最长子序列」作为题目链，
    打分以链长为主；起点恰为 expected（正常顺延）或贴近 expected 时加权，
    使「正常顺延页」优先于「页内残留子项 1./2.」，同时整页重置（page-03
    那种 1/2/3）因自成最长连续链仍被完整保留。
    返回 [(match, ocr_num), ...]（文档顺序）；无则 []。
    """
    if not matches:
        return []
    nums = [int(m.group(1)) for m in matches]
    n = len(nums)
    dp = [1] * n          # 以 i 结尾的「连续+1」链长
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if nums[j] == nums[i] - 1 and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                prev[i] = j

    best: list[int] | None = None
    best_score = None
    for i in range(n):
        chain: list[int] = []
        k = i
        while k != -1:
            chain.append(k)
            k = prev[k]
        chain.reverse()
        start_num = nums[chain[0]]
        score = len(chain)
        if start_num == expected:        # 正常顺延，强加权
            score += 5
        elif abs(start_num - expected) <= 2:
            score += 2
        if (best_score is None or score > best_score
                or (score == best_score and chain[0] < best[0])):
            best_score = score
            best = chain
    return [(matches[k], nums[k]) for k in best]


def split_by_question_number(pages_text: list[str]) -> tuple[list[dict], list[int]]:
    """Step A：按题号锚点切段（纯程序，无 LLM）。

    返回:
        questions_raw: [{"number": N, "text": "...", "source_page": P,
                         "ocr_number": OCR 原始题号(诊断用)}]
        answer_pages: 答案页页码列表（1-based）

    切分规则：
    - 每页先剥掉头部（考生须知、答案页标题）
    - 在剩余文本里按 ^N.[\s] 锚点找候选位置
    - 用 `_pick_question_chain` 取「连续整数最长子序列」抗 OCR 题号错乱
    - 题号按**文档顺序顺延**重编（不信任 OCR 题号——它会整页重置/跳变），
      OCR 原始号留在 ocr_number 供 qc 诊断；断号/题数异常由 qc_report 兜底
    - 跨页处理：page-N+1 第一锚点前的内容并入 page-N 末题
    """
    is_ans = _classify_pages(pages_text)
    answer_pages = [i + 1 for i, x in enumerate(is_ans) if x]

    segments: list[dict] = []
    last_num = 0

    for page_idx, raw_text in enumerate(pages_text):
        if is_ans[page_idx]:
            continue
        page_num = page_idx + 1
        text = _strip_preamble(raw_text, on_first_page=(page_num == 1))

        matches = list(NUM_ANCHOR_RE.finditer(text))
        chain = _pick_question_chain(matches, last_num + 1)

        if not chain:
            # 整页都是上一题的延续（跨页）
            if segments and text.strip():
                segments[-1]["text"] += "\n" + text.strip()
            continue

        # 第一个锚点之前的内容并入上一题
        first_start = chain[0][0].start()
        if first_start > 0 and segments:
            tail = text[:first_start].strip()
            # 大题标题（如"四、科普阅读题(共4分)"）跳过，别并入上一题
            if tail and not SECTION_HEAD_RE.match(tail):
                segments[-1]["text"] += "\n" + tail

        for i, (m, ocr_n) in enumerate(chain):
            last_num += 1               # 文档顺序顺延重编
            start = m.start()
            end = chain[i + 1][0].start() if i + 1 < len(chain) else len(text)
            segments.append({
                "number": last_num,
                "text": text[start:end].strip(),
                "source_page": page_num,
                "ocr_number": ocr_n,
            })

    return segments, answer_pages


# Step C：程序剥离 stem 和 options
# 选项锚点：A/B/C/D + . / 、/ ．，前面不能紧邻字母（防误匹"NaCl"中间的字母）
OPT_ANCHOR_RE = re.compile(r"(?:(?<=^)|(?<=[\s。，；,;]))([A-D])\s*[.、．]\s*")
# 单行多选项格式（如 "A. 音调 B. 响度 C. 音色 D. 声速"）的整行检测
INLINE_4OPTS_RE = re.compile(
    r"A\s*[.、．][^A-D\n]{1,30}B\s*[.、．][^A-D\n]{1,30}C\s*[.、．][^A-D\n]{1,30}D\s*[.、．][^\n]{1,30}"
)
# 图片选项行：选项本身是 4 张图，OCR 只剩裸标签 "A B C D"（无 . 无内容），
# 或带空点/[图] 占位（"A.[图] B.[图] C.[图] D.[图]"）。整行只有这 4 个标签。
IMG_4OPTS_RE = re.compile(
    r"(?m)^\s*A\s*[.、．]?\s*(?:\[图\])?\s+"
    r"B\s*[.、．]?\s*(?:\[图\])?\s+"
    r"C\s*[.、．]?\s*(?:\[图\])?\s+"
    r"D\s*[.、．]?\s*(?:\[图\])?\s*$"
)


def split_stem_options(text: str) -> tuple[str, dict | None]:
    """Step C：把单题文本切成 stem + options（纯程序）。

    防误判：
    - OCR 偶尔把图象坐标轴/标题误识成 "A. B." 开头（如 Q16 温度-时间图）
    - 用"选项内容长度 < 120 且 ≤ 2 行换行"过滤
    - 至少识别出 3 个合法选项才认为是选择题
    图片选项兜底：选项是 4 张图时 OCR 仅留裸标签行 "A B C D"，按
    has_image_options 约定回填 {A:"[图]",...}（否则整道选择题 options 丢失）。
    """
    # 找第一个候选 A 锚点
    m = OPT_ANCHOR_RE.search(text)
    if m and m.group(1) == "A":
        stem = text[:m.start()].rstrip()
        opts_text = text[m.start():]

        # 用同一锚点切分
        parts = OPT_ANCHOR_RE.split(opts_text)
        raw_opts: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            label = parts[i].strip()
            content = parts[i + 1].strip()
            # 最后一个选项常会把后续无关内容（图标 "甲乙"、新大题标题、表格）吞进来。
            # 选项内部通常无空行，遇到第一个 \n\n 截断。
            content = re.split(r"\n\s*\n", content, maxsplit=1)[0].strip()
            if label in "ABCD" and content and label not in raw_opts:
                raw_opts[label] = content

        # OCR 噪声防护：内容 > 120 字符 → 多半是图象/表格内容被误识为选项
        clean_opts = {k: v for k, v in raw_opts.items() if len(v) <= 120}
        # 中考选择题约定 4 选项，必须 A/B/C/D 都有才认为是 choice
        # （防止 Q24 那种"子题内含 A/B/C 备选数值"被误识为选择题）
        if set(clean_opts.keys()) == {"A", "B", "C", "D"}:
            return stem, clean_opts

    # 图片选项兜底：整行只有 "A B C D"（选项是图，无文字内容）。
    # 仅当 stem 较短才认（图片选择题题干都短；防长实验题里的图注 "A B C D" 误判）
    im = IMG_4OPTS_RE.search(text)
    if im:
        stem = text[:im.start()].rstrip()
        if len(stem) <= 200:
            return stem, {k: "[图]" for k in "ABCD"}

    return text.strip(), None


# Step B：单题类型分类（qwen-max，输入小输出小）
CLASSIFY_TYPE_PROMPT = """判断这道{subject_cn}题的题型，输出 JSON：
{{"type": "..."}}

题型枚举（必须六选一）：
- choice         : 选择题（含 A/B/C/D 选项；单选或多选都用 choice）
- fill_blank     : 填空题（题干含若干"_"或下划线空白，填字/数字）
- calculation    : 计算题（要求写完整推导和计算过程）
- experiment     : 实验探究题（多分小问 (1)(2)(3)，描述实验装置/步骤/结论）
- essay          : 解答题（其他需写文字论述的）

判断顺序：
1. 含 A. B. C. D. 选项行 → choice
2. 题号开头含"计算"、"求"且要求过程 → calculation
3. 多个 (1)(2) 小问 + 实验/装置词汇 → experiment
4. 只有若干 "_" 空格 → fill_blank
5. 其他 → essay

只输出 JSON，不要解释。"""


def classify_question_type(client, text: str, subject_cn: str,
                            number: int, retries: int = 2) -> str:
    """Step B：单题题型分类。

    输入小、输出小，失败成本低，可批量并发。
    """
    # 程序优先：若 split_stem_options 切出完整 4 选项 → 一定是 choice
    # 复用 Step C 的过滤逻辑（长度/4 选项约束），避免 Q16/Q24 类误判
    _, opts_test = split_stem_options(text)
    if opts_test and set(opts_test.keys()) == {"A", "B", "C", "D"}:
        return "choice"

    last_err = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": CLASSIFY_TYPE_PROMPT.format(subject_cn=subject_cn)},
                    {"role": "user", "content": text[:1500]},  # 单题不会很长，1500 足够
                ],
                temperature=0.0,
                max_tokens=64,
                response_format={"type": "json_object"},
                timeout=60,
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            t = data.get("type", "").strip()
            if t in ("choice", "fill_blank", "calculation", "experiment", "essay"):
                return t
            print(f"    ⚠️ Q{number} type 非法值: {t!r}", file=sys.stderr)
        except Exception as e:
            last_err = e
            print(f"    ⚠️ Q{number} 分类 attempt {attempt+1}: {e}", file=sys.stderr)
            time.sleep(1)
    # 兜底
    print(f"    ⚠️ Q{number} 分类失败，默认 essay: {last_err}", file=sys.stderr)
    return "essay"


# Step E：答案对齐
EXTRACT_CORRECT_PROMPT = """以下是一份{subject_cn}试卷答案页的 OCR 文本。
提取每道题的 correct 答案（不含解析步骤），输出 JSON：

{{"answers": [
  {{"number": 1, "correct": "C"}},
  {{"number": 16, "correct": "不变；晶体；引力"}}
]}}

规则：
1. 覆盖题号 1 到 {max_num}，**不能漏题**。每个题号一条。
2. correct 内容：
   - 选择题：字母（"C" 或多选 "AD"）
   - 填空/实验：每空答案用「；」分隔
   - 计算/解答：只填最终结论数值（如 "21800Ω；1400W"），不写过程
3. 直接输出 JSON。"""


def extract_correct_answers(client, answer_text: str, subject_cn: str,
                              max_num: int, retries: int = 3) -> dict[int, str]:
    """Step E-1：从答案页提取 correct（单次调用，输出紧凑）。

    返回 {number: correct_str}
    """
    prompt = EXTRACT_CORRECT_PROMPT.format(subject_cn=subject_cn, max_num=max_num)
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": answer_text},
                ],
                temperature=0.0,
                max_tokens=4096,
                response_format={"type": "json_object"},
                timeout=120,
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            result = {}
            for a in data.get("answers", []):
                if isinstance(a, dict) and "number" in a:
                    result[int(a["number"])] = str(a.get("correct", "")).strip()
            if len(result) >= max_num * 0.6:  # 至少覆盖 60%
                return result
            print(f"    ⚠️ correct 只覆盖 {len(result)}/{max_num}，重试", file=sys.stderr)
        except Exception as e:
            print(f"    ⚠️ correct attempt {attempt+1}: {e}", file=sys.stderr)
        time.sleep(2 * (attempt + 1))
    return result if 'result' in dir() else {}


EXTRACT_SOLUTION_ONE_PROMPT = """以下是一份{subject_cn}试卷答案页的 OCR 文本。
提取**第 {number} 题**的完整解题步骤/评分要点，输出 JSON：

{{"solution": "..."}}

规则：
1. solution 尽量完整保留推导、公式、评分点，按小问 (1)(2)(3) 分段（用 \\n 换行）。
2. 只输出第 {number} 题的内容，不要提取其他题号。
3. 若答案页只有简短结论无步骤，solution 写该结论文字。
4. 直接输出 JSON。"""


def extract_solution_for(client, answer_text: str, subject_cn: str,
                           number: int, retries: int = 2) -> str:
    """Step E-2：单题 solution 提取（小输入小输出）。"""
    prompt = EXTRACT_SOLUTION_ONE_PROMPT.format(subject_cn=subject_cn, number=number)
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": answer_text},
                ],
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
                timeout=120,
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            return str(data.get("solution", "")).strip()
        except Exception as e:
            print(f"    ⚠️ Q{number} solution attempt {attempt+1}: {e}", file=sys.stderr)
            time.sleep(2)
    return ""


def structure_pages_v2(client, pages_text: list[str], subject_en: str) -> dict:
    """新流水线：拆分职责，单题调用，每个 qwen-max 任务责任窄、输入小。

    流程：
      A. split_by_question_number(pages_text)        — 程序，无 LLM
      B. classify_question_type(text)  并发           — qwen-max 单题
      C. split_stem_options(text)                    — 程序
      E1. extract_correct_answers(answer_text)       — qwen-max 一次（紧凑）
      E2. extract_solution_for(answer_text, num) 并发 — qwen-max 单题，非选择题
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    subject_cn = SUBJECT_LABEL_CN.get(subject_en, subject_en)

    # Step A: 题号切分（程序，0 LLM 调用）
    print(f"  🧱 [A] 题号切分（程序）...", file=sys.stderr)
    segments, answer_pages = split_by_question_number(pages_text)
    print(f"      → 切出 {len(segments)} 题，答案页 {answer_pages}", file=sys.stderr)

    # Step B: 题型分类（qwen-max 单题，并发）
    # 程序优先：含 A./B. 锚点的直接判 choice，省 LLM 调用
    print(f"  🧱 [B] 题型分类（qwen-max 并发）...", file=sys.stderr)
    types: dict[int, str] = {}

    def _classify(seg):
        t = classify_question_type(client, seg["text"], subject_cn, seg["number"])
        return seg["number"], t

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_classify, s) for s in segments]
        for fut in as_completed(futs):
            num, t = fut.result()
            types[num] = t

    # Step C: 程序剥离 stem 和 options
    print(f"  🧱 [C] 选项剥离（程序）...", file=sys.stderr)
    # 同步抽取每题分值（基于 OCR 文本里大题分值描述）
    q_numbers = [s["number"] for s in segments]
    score_map = _extract_question_scores(pages_text, q_numbers)
    print(f"      → 分值: {score_map}", file=sys.stderr)

    questions = []
    for seg in segments:
        num = seg["number"]
        q_type = types.get(num, "essay")
        stem_raw, opts = split_stem_options(seg["text"])
        stem = _clean_stem(stem_raw)
        if opts:
            opts = {k: _clean_option_value(v) for k, v in opts.items()}
        has_image_options = bool(opts and all(v == "[图]" for v in opts.values()))
        questions.append({
            "id": f"{subject_en}-q{num:02d}",
            "number": num,
            "type": q_type,
            "score": score_map.get(num, 2),
            "stem": stem,
            "options": opts,
            "has_image_options": has_image_options,
            "source_page": seg["source_page"],
        })

    # Step E-1: correct（单次 qwen-max，覆盖全部题号）
    print(f"  🧱 [E1] correct 答案提取（qwen-max）...", file=sys.stderr)
    if answer_pages:
        ans_texts = [pages_text[p - 1] for p in answer_pages if 1 <= p <= len(pages_text)]
    else:
        ans_texts = pages_text[-2:]
    ans_full = "\n\n".join(f"## page-{p:02d}\n{t}" for p, t in zip(answer_pages or [len(pages_text)-1, len(pages_text)], ans_texts))
    max_num = max((q["number"] for q in questions), default=30)
    correct_map = extract_correct_answers(client, ans_full, subject_cn, max_num)

    # 后处理：选择题 + correct 长度 > 1 → multi_choice
    for q in questions:
        if q["type"] == "choice":
            c = correct_map.get(q["number"], "")
            if len(c) > 1 and all(ch in "ABCD" for ch in c):
                q["type"] = "multi_choice"

    # Step E-2: solution（非选择题，单题并发）
    SOLUTION_TYPES = {"calculation", "experiment", "essay", "fill_blank"}
    sol_targets = [q["number"] for q in questions if q["type"] in SOLUTION_TYPES]
    print(f"  🧱 [E2] solution 提取（qwen-max 并发，{len(sol_targets)} 题）...", file=sys.stderr)
    solution_map: dict[int, str] = {}

    def _extract_sol(n):
        s = extract_solution_for(client, ans_full, subject_cn, n)
        return n, s

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(_extract_sol, n) for n in sol_targets]
        for fut in as_completed(futs):
            n, s = fut.result()
            solution_map[n] = s

    # 合并 answers；solution 也跑 _clean_stem 清掉 LaTeX \\ 等残留
    all_nums = sorted(set(correct_map) | set(solution_map))
    answers = [
        {
            "number": n,
            "correct": correct_map.get(n, ""),
            "solution": _clean_stem(solution_map.get(n, "")),
        }
        for n in all_nums
    ]

    # 从 page-01 头部提取卷面元数据（满分 / 考试时长）
    full_score, duration = _extract_paper_meta(pages_text[0] if pages_text else "")

    return {
        "subject": subject_en,
        "exam": "",  # v2 不再让 LLM 编 exam name；上层从目录推
        "page_count": len(pages_text),
        "full_score": full_score,        # 来自 OCR 头部"满分为 X 分"
        "duration_minutes": duration,    # 来自 OCR 头部"时间 Y 分钟"
        "questions": questions,
        "answers": answers,
        "answer_pages": answer_pages,
    }


# 卷面元数据提取（满分 / 时长）
META_FULL_SCORE_RE = re.compile(r"满分(?:为)?\s*(\d+)\s*分")
META_DURATION_RE = re.compile(r"(?:考试)?时间\s*(\d+)\s*分钟")
# "16、17、19、23 题各 3 分" / "25、26 题各 4 分"
SCORE_LIST_RE = re.compile(r"((?:\d+\s*[、，]\s*)*\d+)\s*题\s*各\s*(\d+)\s*分")
# "每小题 N 分" / "每题 N 分"
SCORE_EACH_RE = re.compile(r"每\s*小?\s*题\s*(\d+)\s*分")
# 大题标题：「X、xxx题(...共 N 分...)」
SCORE_SECTION_RE = re.compile(
    r"(?m)^\s*[一二三四五六七八九十]+\s*[、，][^\n]{0,40}题[^\n]*?共\s*(\d+)\s*分"
)


def _extract_paper_meta(page1_text: str) -> tuple[int | None, int | None]:
    """从 page-01 OCR 头部提取卷面元数据。

    典型行：「本试卷共8页，26道小题，满分为70分，闭卷考试，时间70分钟。」
    """
    head = page1_text[:600]
    fs_m = META_FULL_SCORE_RE.search(head)
    du_m = META_DURATION_RE.search(head)
    return (
        int(fs_m.group(1)) if fs_m else None,
        int(du_m.group(1)) if du_m else None,
    )


def _extract_question_scores(
    pages_text: list[str], question_numbers: list[int]
) -> dict[int, int]:
    """从 OCR 文本提取每题分值。

    优先级：
      1. "X、Y、Z 题各 N 分" 显式列表
      2. 按大题段"共 N 分"减去已分配 / 剩余题数 均分
      3. 兜底：2 分

    典型 OCR 描述：
      - "一、单项选择题(...共24分，每小题2分)"
      - "三、实验探究题(共28分,16、17、19、23题各3分,18、20、21、22题各4分)"
      - "四、科普阅读题(共4分)"  ← 单题大题，按 section 平均
      - "五、计算题（共8分，25、26题各4分）"
    """
    full = "\n".join(pages_text)
    scores: dict[int, int] = {}

    # 1. 显式列表
    for m in SCORE_LIST_RE.finditer(full):
        n_list = [int(x) for x in re.findall(r"\d+", m.group(1))]
        score = int(m.group(2))
        for n in n_list:
            scores[n] = score

    # 2. 按大题"共 N 分"兜底（处理 Q24 这种单题大题）
    sections = list(SCORE_SECTION_RE.finditer(full))
    for i, sec in enumerate(sections):
        section_total = int(sec.group(1))
        seg_start = sec.end()
        seg_end = sections[i + 1].start() if i + 1 < len(sections) else len(full)
        seg_text = full[seg_start:seg_end]
        nums_in_section = sorted({
            int(m.group(1)) for m in NUM_ANCHOR_RE.finditer(seg_text)
        })
        unscored = [n for n in nums_in_section if n not in scores]
        if not unscored:
            continue
        scored_total = sum(scores.get(n, 0) for n in nums_in_section if n in scores)
        remaining = section_total - scored_total
        if remaining <= 0:
            continue
        per = remaining // len(unscored)
        if per <= 0:
            continue
        for n in unscored:
            scores[n] = per

    # 3. 兜底：2 分
    for n in question_numbers:
        scores.setdefault(n, 2)
    return scores


# ============== step 2: structure via qwen-max ==============

STRUCT_QUESTIONS_PROMPT = """以下是一份{subject_cn}试卷的逐页 OCR 文本（每页用 ## page-NN 标头分隔）。
只提取题目列表，不提取答案。输出 JSON，schema：

{{
  "exam": "2026 北京朝阳区初三一模 物理",
  "answer_pages": [9, 10],
  "questions": [
    {{
      "number": 1,
      "type": "choice",
      "text": "1. 下列物品中，通常情况下属于固体的是\\nA. 陶瓷杯\\nB. 橡皮\\nC. 钢尺\\nD. 塑料水瓶",
      "source_page": 1
    }},
    {{
      "number": 3,
      "type": "choice",
      "text": "3. 如图所示的实例中，目的是为了增大摩擦的是\\n[图]\\nA. [图]\\nB. [图]\\nC. [图]\\nD. [图]",
      "source_page": 1
    }},
    {{
      "number": 16,
      "type": "experiment",
      "text": "16. (1) 在研究某种物质熔化前后温度变化特点的实验时...(2) ...",
      "source_page": 5
    }}
  ]
}}

规则：
1. 题号单调递增、不漏题、不把答案页内容混入 questions。
2. text：把该题的完整题面文字（题干 + 选项行，含题号前缀）照原样放入，多行之间用 \\n 分隔。
   选项行格式保持 "A. 文字" / "A. [图]"；题目中嵌入的图用 [图] 占位。
3. type 枚举：choice / multi_choice / fill_blank / essay / experiment / calculation。
4. answer_pages：答案页的页码列表。
5. source_page：该题题干主体出现在哪页（根据 ## page-NN 标头判断），填阿拉伯数字。
   - 必须填写，不允许为 null。
   - 若题目跨页（题干在 page-N，选项在 page-N+1），填题干所在页（page-N）。
   - 答案页不算题目页，不要把答案页页码写入 source_page。
6. 直接输出 JSON，不要加代码块或解释。"""

STRUCT_CORRECT_PROMPT = """以下是一份{subject_cn}试卷的答案页 OCR 文本。
只提取每道题的正确答案（不含解析步骤），输出 JSON，schema：

{{
  "answers": [
    {{"number": 1, "correct": "C"}},
    {{"number": 16, "correct": "不变；晶体；引力"}}
  ]
}}

规则：
1. 每题一条，number 为原始题号，覆盖全部题目，不能漏题。
2. correct：选择题填字母（如 "C"、"AD"），填空/实验题各空答案用「；」分隔，
   计算/解答题只填最终数值结论（如 "21800Ω；1400W"），不要写推导过程。
3. 不输出 solution 字段，保持 JSON 紧凑。
4. 直接输出 JSON，不要加代码块或解释。"""

STRUCT_SOLUTION_PROMPT = """以下是一份{subject_cn}试卷的答案页 OCR 文本。
需要提取解题步骤的题号为：{non_choice_nums}（即本卷全部非选择题）。

输出 JSON，schema：

{{
  "solutions": [
    {{"number": 16, "solution": "（1）由图像可知熔化过程中温度保持不变，属于晶体。（2）引力使分子间产生相互作用..."}},
    {{"number": 23, "solution": "根据杠杆平衡条件 F1*l1=F2*l2，因 l1、l2 不变而 G 增大，所以 G0 增大..."}},
    {{"number": 25, "solution": "（1）U上=220-2=218V，R上=218/0.01=21800Ω。（2）P=UI=220×10=2200W"}}
  ]
}}

规则：
1. 对上述每个题号都输出一条，即使答案页只有简短说明也要输出（solution 写实际内容）。
2. solution 尽量完整保留推导过程、公式推导、评分要点，按小问 (1)(2)(3) 分段。
3. 若答案页某题只有最终结论无步骤，也要输出该题，solution 写该结论文字。
4. 直接输出 JSON，不要加代码块或解释。"""


def _call_qwen_max(client, system_prompt: str, user_content: str,
                    label: str, retries: int = 3,
                    min_list_key: str | None = None, min_count: int = 5) -> dict:
    """通用 qwen-max JSON 调用，带重试、finish_reason 检测、最小条目检测。"""
    last_err = None
    last_result = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_tokens=8192,
                response_format={"type": "json_object"},
                timeout=180,
            )
            choice = resp.choices[0]
            finish_reason = choice.finish_reason
            raw = choice.message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
            result = json.loads(raw)
            if finish_reason == "length":
                n = len(result.get(min_list_key, [])) if min_list_key else "?"
                print(f"    ⚠️ {label} attempt {attempt+1}: finish_reason=length（截断，{n} 条），重试",
                      file=sys.stderr)
                last_result = result
                time.sleep(3 * (attempt + 1))
                continue
            if min_list_key and len(result.get(min_list_key, [])) < min_count:
                n = len(result.get(min_list_key, []))
                print(f"    ⚠️ {label} attempt {attempt+1}: 只 {n} 条，可能截断，重试", file=sys.stderr)
                last_result = result
                time.sleep(3 * (attempt + 1))
                continue
            return result
        except Exception as e:
            last_err = e
            print(f"    ⚠️ {label} attempt {attempt+1}/{retries}: {type(e).__name__}: {str(e)[:120]}",
                  file=sys.stderr)
            time.sleep(5 * (attempt + 1))

    if last_result is not None:
        n = len(last_result.get(min_list_key, [])) if min_list_key else "?"
        print(f"    ⚠️ {label} 用最后一次结果（{n} 条）", file=sys.stderr)
        return last_result
    raise RuntimeError(f"{label} failed after {retries} tries: {last_err}")


def structure_pages(client, pages_text: list[str], subject_en: str,
                     retries: int = 3) -> dict:
    """整卷文本 → 结构化 JSON。三步：题目 + correct 答案 + solution 解析。

    分开调用以规避 8192 token 上限：
      Step A: 题目列表（stem + options，全页输入）
      Step B: correct 答案（仅答案页，无步骤，紧凑）
      Step C: solution 解析（仅答案页，仅非选择题）
    """
    subject_cn = SUBJECT_LABEL_CN.get(subject_en, subject_en)
    full_text = "\n\n".join(f"## page-{i+1:02d}\n{t}" for i, t in enumerate(pages_text))

    # Step A: 提取题目
    print(f"  🧱 [1/3] 提取题目 (qwen-max) ...", file=sys.stderr)
    q_prompt = STRUCT_QUESTIONS_PROMPT.format(subject_cn=subject_cn, subject_en=subject_en)
    q_result = _call_qwen_max(client, q_prompt, full_text,
                               label="questions", retries=retries,
                               min_list_key="questions", min_count=10)
    questions = q_result.get("questions", [])
    answer_pages = q_result.get("answer_pages", [])
    exam_name = q_result.get("exam", "")

    # 答案页文本（只发答案页，节省 tokens）
    if answer_pages:
        ans_texts = [pages_text[p - 1] for p in answer_pages if 1 <= p <= len(pages_text)]
    else:
        ans_texts = pages_text[-2:]
    ans_full = "\n\n".join(f"## page-{i+1:02d}\n{t}" for i, t in enumerate(ans_texts))

    # Step B: 提取 correct（紧凑，覆盖全部题目）
    print(f"  🧱 [2/3] 提取答案 correct (qwen-max, {len(ans_texts)} 页) ...", file=sys.stderr)
    b_prompt = STRUCT_CORRECT_PROMPT.format(subject_cn=subject_cn)
    b_result = _call_qwen_max(client, b_prompt, ans_full,
                               label="correct", retries=retries,
                               min_list_key="answers", min_count=5)
    answers_correct = {a["number"]: a["correct"]
                       for a in b_result.get("answers", [])
                       if isinstance(a, dict) and "number" in a}

    # Step C: 提取 solution（非选择题解析步骤，全答案页输入）
    # 告知模型哪些题号需要 solution，避免选择题干扰
    non_choice_nums = sorted({
        q["number"] for q in questions
        if q.get("type") not in ("choice", "multi_choice")
    })
    nums_hint = "、".join(str(n) for n in non_choice_nums) if non_choice_nums else "（无）"
    print(f"  🧱 [3/3] 提取解析 solution (qwen-max, 非选择题: {nums_hint}) ...", file=sys.stderr)
    c_prompt = STRUCT_SOLUTION_PROMPT.format(subject_cn=subject_cn, non_choice_nums=nums_hint)
    c_result = _call_qwen_max(client, c_prompt, ans_full,
                               label="solution", retries=retries,
                               min_list_key="solutions", min_count=1)
    answers_solution = {s["number"]: s["solution"]
                        for s in c_result.get("solutions", [])
                        if isinstance(s, dict) and "number" in s}

    # 合并 correct + solution
    all_numbers = sorted(set(answers_correct) | set(answers_solution))
    answers = [
        {
            "number": n,
            "correct": answers_correct.get(n, ""),
            "solution": answers_solution.get(n, ""),
        }
        for n in all_numbers
    ]

    return {
        "subject": subject_en,
        "exam": exam_name,
        "page_count": len(pages_text),
        "questions": questions,
        "answers": answers,
        "answer_pages": answer_pages,
    }


# ============== 题面文本归一化 ==============

def _clean_option_value(v: str) -> str:
    """清理选项文字：去掉 JSON/LaTeX 格式残留。"""
    v = v.strip()
    # LaTeX 行间距命令：\\[10pt] / \\[10pt / \[10pt] 等
    v = re.sub(r"\\+\[\d+pt\]?", "", v).strip()
    # 孤立的 \Npt] 或 \N] 残留
    v = re.sub(r"\\+\d+pt\]?$", "", v).strip()
    # 去尾部反斜杠
    v = re.sub(r"\\+$", "", v).strip()
    # 去尾部 ] 或 [ （JSON 数组括号残留）
    v = v.rstrip("]").rstrip("[").strip()
    # 去首尾引号
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1]
    return v


def _normalize_options(opts) -> dict | None:
    """把 qwen-max 可能返回的各种 options 格式统一为 {A: text, ...} dict，或 None。

    已观察到的异常格式：
      - str:  "A. 陶瓷杯\\nB. 橡皮\\nC. 钢尺\\nD. 塑料水瓶"
      - list of str: ["A. 陶瓷杯", "B. 橡皮", ...]
      - list of dict: [{"label": "A", "text": "陶瓷杯"}, ...]
      - dict (正确): {"A": "陶瓷杯", ...}
    """
    if opts is None:
        return None
    if isinstance(opts, dict):
        return opts  # 已是目标格式

    # list 格式
    if isinstance(opts, list):
        out = {}
        for item in opts:
            if isinstance(item, dict):
                # {"label": "A", "text": "..."} 或 {"A": "..."}
                label = item.get("label") or item.get("key")
                text = item.get("text") or item.get("value") or item.get("content", "")
                if not label and len(item) == 1:
                    label, text = next(iter(item.items()))
                if label and len(label) == 1 and label.isupper():
                    out[label] = str(text)
            elif isinstance(item, str):
                # "A. 陶瓷杯" 或 "A 陶瓷杯"
                m = re.match(r"^([A-E])[.、．\s]\s*(.*)", item.strip())
                if m:
                    out[m.group(1)] = _clean_option_value(m.group(2))
        return out if out else None

    # str 格式：逐行解析
    if isinstance(opts, str):
        out = {}
        for line in opts.splitlines():
            line = line.strip()
            m = re.match(r"^([A-E])[.、．\s]\s*(.*)", line)
            if m:
                out[m.group(1)] = _clean_option_value(m.group(2))
        return out if out else None

    return None


def _split_text_to_stem_options(text: str) -> tuple[str, dict | None]:
    """从 text 字段（题干 + 选项行混合）中拆出 stem 和 options dict。

    处理两种格式：
      1. 多行：选项每个占独立一行，以 "A." / "B." 等开头
      2. 单行内联：全部在一行，如 "题干 A. 选项A B. 选项B C. 选项C D. 选项D"
    返回 (stem_str, options_dict_or_None)。
    """
    OPTION_PAT = re.compile(r"(?<!\w)([A-E])[.、．]\s*")

    # 先尝试多行格式
    lines = text.splitlines()
    stem_lines = []
    opt_lines = []
    in_opts = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^[A-E][.、．]\s*", stripped):
            in_opts = True
            opt_lines.append(stripped)
        elif in_opts:
            if opt_lines:
                opt_lines[-1] += " " + stripped
        else:
            stem_lines.append(stripped)

    if opt_lines:
        stem = "\n".join(l for l in stem_lines if l)
        return stem, _normalize_options(opt_lines)

    # 单行内联格式：用 "A. " / "B. " 切分
    # 找第一个选项出现的位置，之前是 stem
    m = OPTION_PAT.search(text)
    if m and m.group(1) == "A":
        # 确保至少有两个选项才算内联格式
        parts = OPTION_PAT.split(text[m.start():])
        # split 产出: ['', 'A', 'text_A', 'B', 'text_B', ...]
        # 即 [prefix, label, content, label, content, ...]
        opts = {}
        i = 1
        while i + 1 < len(parts):
            label = parts[i].strip()
            content = parts[i + 1].strip()
            if label and label.isupper() and len(label) == 1:
                opts[label] = content
            i += 2
        if len(opts) >= 2:
            stem = re.sub(r"\\+$", "", text[:m.start()].strip()).strip()
            # clean values
            opts = {k: _clean_option_value(v) for k, v in opts.items()}
            return stem, opts

    # 无选项，全部是 stem
    return text.strip(), None


def _clean_stem(text: str) -> str:
    """清理 stem 字段：去 LaTeX 包裹/行间距残留、合并多余空白。"""
    t = text or ""
    # LaTeX 行间距命令：\\[10pt] 等（qwen-max 生成格式残留）
    t = re.sub(r"\\+\[\d+pt\]?", "", t)
    # 孤立的 \Npt] 残留
    t = re.sub(r"\\+\d+pt\]?", "", t)
    # LaTeX 换行符 \\ → 真实换行
    # 规则：连续两个反斜杠，**且不是真 LaTeX 命令前缀**才转换行
    # 真 LaTeX 命令名特征：≥ 2 个连续小写字母（mathrm/frac/widehat/text...）
    # 单字母（\\F \\G）或非字母（\\(2) \\| \\①）一律是 LLM 用作换行的 \\
    # e.g.  "性。\\(2) 若取" → "性。\n(2) 若取"
    #       "\\F_{浮} = ..."  → "\nF_{浮} = ..."
    #       "\\mathrm{kg}"   → 保留（真 LaTeX 命令）
    t = re.sub(r"\\\\(?![a-z]{2,})", "\n", t)
    # 去 LaTeX \[ \] 包裹（display math 遗留）
    t = re.sub(r"\\\[|\\\]", "", t)
    # 去多余反斜杠（\\A → A）
    t = re.sub(r"\\+([A-E]\.)", r"\1", t)
    # 若 stem 末尾误混入了选项行（A. xxx），截断到选项前
    t = re.sub(r"\n+[A-E][\.、．]\s*.*$", "", t, flags=re.DOTALL)
    # 去尾部孤立反斜杠
    t = re.sub(r"\\+\s*$", "", t, flags=re.MULTILINE).strip()
    # 合并多余空白
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    # Markdown 表格行之间不允许空行（LaTeX \\\\| 经 \\→\n 转换会产生 \n\n|）
    # 反复应用直到稳定：把连续 |...|\n\n|...| 收为 |...|\n|...|
    while True:
        new = re.sub(r'(\|[^\n]*\|)\s*\n\s*\n+(?=\s*\|)', r'\1\n', t)
        if new == t:
            break
        t = new
    return t.strip()


# ============== 主入口 ==============

def ocr_one_paper(src_dir: Path, out_dir: Path, subject_en: str,
                   force: bool = False, pipeline: str = "v2") -> Path:
    """src_dir: 原始卷目录（knowledge-original，只读 images/）。
    out_dir : 派生 staging 目录（knowledge-base），落 pages/structured-cloud。
    """
    images_dir = src_dir / "images"
    pages_cache = out_dir / "pages"
    struct_dir = out_dir / "structured-cloud"
    out_json = struct_dir / "final.json"

    if out_json.exists() and not force:
        print(f"  ⏭  缓存命中：{out_json}")
        return out_json

    images = sorted(images_dir.glob("page-*.png"))
    if not images:
        raise FileNotFoundError(f"无 page-*.png：{images_dir}")
    print(f"  📷 {len(images)} 张页面")

    client = _client()

    # Step 1: per-page OCR (cached by file)，并发 10 worker
    pages_cache.mkdir(parents=True, exist_ok=True)
    pages_text = [None] * len(images)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _ocr_one(args):
        i, img = args
        cache = pages_cache / f"page-{i:02d}.ocr.txt"
        if cache.exists() and not force:
            print(f"  ⏭  page-{i:02d} 缓存命中", flush=True)
            return i, cache.read_text(encoding="utf-8")
        print(f"  🔍 page-{i:02d} OCR ...", flush=True)
        text = ocr_page(client, img)
        cache.write_text(text, encoding="utf-8")
        return i, text

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_ocr_one, (i, img)) for i, img in enumerate(images, 1)]
        for fut in as_completed(futs):
            i, text = fut.result()
            pages_text[i - 1] = text

    # Step 2: structure
    if pipeline == "v2":
        print(f"  🧱 整卷结构化（v2：拆职责）...")
        result = structure_pages_v2(client, pages_text, subject_en)
    else:
        print(f"  🧱 整卷结构化（v1：legacy 单 LLM 调用）...")
        result = structure_pages(client, pages_text, subject_en)

    # ensure required fields + scrub malformed entries
    result.setdefault("subject", subject_en)
    result.setdefault("page_count", len(images))
    result.setdefault("answer_pages", [])
    qs_in = result.get("questions", [])
    qs = []
    for q in qs_in:
        if not isinstance(q, dict):
            print(f"  ⚠️ skip non-dict question: {repr(q)[:80]}", file=sys.stderr)
            continue
        if "number" not in q:
            print(f"  ⚠️ skip question missing number: {list(q.keys())}", file=sys.stderr)
            continue

        num = q["number"]
        q_type = q.get("type", "choice")
        source_page = q.get("source_page", None)

        # --- v2 直接给 stem+options dict，跳过解析；v1 给 text 字段，需拆 ---
        raw_text = q.get("text") or ""
        stem_raw = q.get("stem") or ""
        opts_raw = q.get("options")

        if raw_text and not stem_raw:
            # v1：text 字段含题干 + 选项行，逐行拆分
            stem, opts_raw = _split_text_to_stem_options(raw_text)
        else:
            stem = stem_raw

        # v2 已经在 structure_pages_v2 里跑过 _clean_stem，这里再跑等价于幂等
        stem = _clean_stem(stem)

        # 归一化 options → {A: text, ...} dict 或 None
        opts: dict | None = None
        if opts_raw is not None:
            if isinstance(opts_raw, dict):
                opts = opts_raw
            else:
                opts = _normalize_options(opts_raw)
                if opts:
                    print(f"  🔧 Q{num} options 格式修正 {type(opts_raw).__name__} → dict({list(opts.keys())})", file=sys.stderr)
                else:
                    print(f"  ⚠️ Q{num} options 无法解析: {repr(opts_raw)[:60]}", file=sys.stderr)

        # 图片选项一致性
        has_image_options = bool(opts and all(v == "[图]" for v in opts.values()))

        qs.append({
            "id": f"{subject_en}-q{num:02d}",
            "number": num,
            "type": q_type,
            "score": q.get("score", 2),  # 来自 v2 流水线的 _extract_question_scores
            "stem": stem,
            "options": opts,
            "has_image_options": has_image_options,
            "source_page": source_page,
        })
    result["questions"] = qs

    # answers 数组标准化
    answers_in = result.get("answers", [])
    answers = []
    for a in answers_in:
        if not isinstance(a, dict) or "number" not in a:
            continue
        answers.append({
            "number": a["number"],
            "correct": str(a.get("correct", "")),
            "solution": str(a.get("solution", "")),
        })
    result["answers"] = answers

    struct_dir.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # human-readable
    md_lines = [f"# {result.get('exam', '')}", "", f"科目: {subject_en} · {len(qs)} 题", ""]
    for q in qs:
        md_lines.append(f"## Q{q.get('number')} ({q.get('type','?')}) · page-{q.get('source_page','?')}")
        md_lines.append(q.get("text", ""))
        md_lines.append("")
    (struct_dir / "final.md").write_text("\n".join(md_lines), encoding="utf-8")

    print(f"  ✅ {out_json}")
    print(f"     {len(qs)} 题, answer_pages={result.get('answer_pages')}")
    return out_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("src_dir", type=Path,
                   help="原始卷目录（knowledge-original/...），含 images/page-*.png")
    p.add_argument("--out-dir", type=Path, default=None,
                   help="派生 staging 目录；缺省按 paths.derive_out_dir 映射到 "
                        "knowledge-base/exams/_staging/<subject>/<slug>/")
    p.add_argument("--subject", required=True,
                   choices=list(SUBJECT_LABEL_CN.keys()))
    p.add_argument("--force", action="store_true",
                   help="强制重 OCR（跳过缓存）")
    p.add_argument("--pipeline", choices=["v1", "v2"], default="v2",
                   help="结构化流水线：v2（默认，拆职责）/ v1（legacy 单调用）")
    args = p.parse_args()
    out_dir = args.out_dir or derive_out_dir(args.src_dir)
    ocr_one_paper(args.src_dir, out_dir, args.subject, force=args.force,
                  pipeline=args.pipeline)


if __name__ == "__main__":
    main()
