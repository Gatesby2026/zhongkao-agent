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
5. 直接输出 JSON，不要加代码块或解释。"""

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
    # 去 LaTeX \[ \] 包裹
    t = t.replace("\\[", "").replace("\\]", "")
    # 去多余反斜杠（\\A → A）
    t = re.sub(r"\\+([A-E]\.)", r"\1", t)
    # 若 stem 末尾误混入了选项行（A. xxx），截断到选项前
    t = re.sub(r"\n+[A-E][\.、．]\s*.*$", "", t, flags=re.DOTALL)
    # 合并多余空白
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ============== 主入口 ==============

def ocr_one_paper(paper_dir: Path, subject_en: str, force: bool = False) -> Path:
    images_dir = paper_dir / "images"
    pages_cache = paper_dir / "pages"
    out_dir = paper_dir / "structured-cloud"
    out_json = out_dir / "final.json"

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
    print(f"  🧱 整卷结构化 (qwen-max) ...")
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

        # --- 从 text 字段（新格式）或 stem+options（旧格式）提取题干和选项 ---
        raw_text = q.get("text") or ""
        stem_raw = q.get("stem") or ""
        opts_raw = q.get("options")

        if raw_text and not stem_raw:
            # 新格式：text 字段包含题干 + 选项行，逐行拆分
            stem, opts_raw = _split_text_to_stem_options(raw_text)
        else:
            stem = stem_raw

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

    out_dir.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # human-readable
    md_lines = [f"# {result.get('exam', '')}", "", f"科目: {subject_en} · {len(qs)} 题", ""]
    for q in qs:
        md_lines.append(f"## Q{q.get('number')} ({q.get('type','?')}) · page-{q.get('source_page','?')}")
        md_lines.append(q.get("text", ""))
        md_lines.append("")
    (out_dir / "final.md").write_text("\n".join(md_lines), encoding="utf-8")

    print(f"  ✅ {out_json.relative_to(paper_dir.parent.parent) if paper_dir.parent.parent in out_json.parents else out_json}")
    print(f"     {len(qs)} 题, answer_pages={result.get('answer_pages')}")
    return out_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("paper_dir", type=Path,
                   help="单卷目录，包含 images/page-*.png")
    p.add_argument("--subject", required=True,
                   choices=list(SUBJECT_LABEL_CN.keys()))
    p.add_argument("--force", action="store_true",
                   help="强制重 OCR（跳过缓存）")
    args = p.parse_args()
    ocr_one_paper(args.paper_dir, args.subject, force=args.force)


if __name__ == "__main__":
    main()
