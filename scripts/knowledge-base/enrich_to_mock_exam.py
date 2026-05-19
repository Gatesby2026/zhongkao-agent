#!/usr/bin/env python3
"""试卷结构化数据 → knowledge-base YAML（含 LLM 知识点标注）

支持两种输入格式：
  新格式（推荐）：--input knowledge-base/exams/_staging/<subject>/<slug>/structured-cloud/final.json
  旧格式（兼容）：--paper paper.json --answer-key answer-key.json [--exam-meta exam-meta.json]

输出：knowledge-base/exams/mock/<subject>/beijing/<slug>.yaml（figures 复制到 <slug>/figures/ 旁）

YAML schema（每题）：
  id, type, score, stem, options, has_image_options,
  answer, solution, knowledge_points, module, difficulty,
  recommended_for, qc_status, qc_note

qc_status 说明：
  draft        — 机器生成，无已知结构问题，待人工抽查
  needs_review — 机器生成，有已知问题（图片选项/答案缺失/solution缺失）
  verified     — 人工确认无误（由 tools/exam-review/ 写入）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import openai
    import yaml
except ImportError:
    print("pip install openai pyyaml", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[2]

# ─── 类型映射 ─────────────────────────────────────────────────────────────────

TYPE_MAP = {
    "choice":       "单选",
    "multi_choice": "多选",
    "fill_blank":   "填空",
    "calculation":  "计算",
    "experiment":   "实验探究",
    "essay":        "解答",
    # 兼容旧格式中文 key
    "单选": "单选", "多选": "多选", "填空": "填空",
    "计算": "计算", "实验探究": "实验探究", "解答": "解答",
}

EXAM_TYPE_MAP = {
    "yimo": "一模", "一模": "一模",
    "ermo": "二模", "二模": "二模",
    "zhongkao": "真题", "中考": "真题",
    "qizhong": "期中", "qimo": "期末",
}

SOLUTION_REQUIRED = {"计算", "解答", "实验探究"}

# ─── 学科 modules ─────────────────────────────────────────────────────────────

SUBJECT_MODULES: dict[str, list[str]] = {
    "physics": ["soundLightHeat", "mechanics", "electricity", "experiments"],
    "math": [
        "numbersAndExpressions", "equationsAndInequalities", "functions",
        "triangles", "quadrilaterals", "circles", "geometryComprehensive",
        "statisticsAndProbability",
    ],
    "chinese":  ["reading", "writing", "classical", "chinese"],
    "english":  ["vocabulary", "grammar", "reading", "listening", "writing"],
    "politics": ["politics"],
    "history":  ["history"],
    "geography": ["geography"],
    "biology":  ["biology"],
    "chemistry": ["chemistry"],
}
# 中文学科名 alias
_SUBJECT_ALIAS = {
    "物理": "physics", "数学": "math", "语文": "chinese",
    "英语": "english", "道法": "politics", "道德与法治": "politics",
    "历史": "history", "地理": "geography", "生物": "biology", "化学": "chemistry",
}


def _subject_en(subject: str) -> str:
    return _SUBJECT_ALIAS.get(subject, subject)


def _modules(subject: str) -> list[str]:
    return SUBJECT_MODULES.get(_subject_en(subject), [])


# ─── 输入格式归一化 ───────────────────────────────────────────────────────────

class NormalizedPaper:
    """将新旧两种输入格式统一为内部结构，供 enrich 使用。"""

    def __init__(self):
        self.exam_name: str = ""
        self.year: int | None = None
        self.district: str = ""
        self.exam_type: str = "真题"
        self.subject: str = ""
        self.full_score: int | None = None
        self.duration: int | None = None
        self.paper_dir: Path | None = None   # 原始试卷目录（用于定位 figures/）
        # [{id, number, type_en, score, stem, options, has_image_options, figure_path}]
        self.questions: list[dict] = []
        # {number: {correct, solution}}
        self.answers: dict[int, dict] = {}

    # ── 新格式：final.json ──

    @classmethod
    def from_final(cls, data: dict, subject_hint: str = "",
                   paper_dir: Path | None = None) -> "NormalizedPaper":
        p = cls()
        p.exam_name = data.get("exam", "")
        p.subject = data.get("subject", subject_hint)
        p.paper_dir = paper_dir
        # 卷面元数据（v2 流水线从 OCR 头部抽取写入 final.json）
        p.full_score = data.get("full_score")
        p.duration = data.get("duration_minutes")

        # 从 exam 名称解析元数据（如"2026 北京朝阳区初三一模 物理"）
        _parse_exam_name(p)

        for q in data.get("questions", []):
            num = q.get("number", 0)
            opts = q.get("options")
            # options 若是旧式 list，转成 dict
            if isinstance(opts, list):
                opts = {o["label"]: o.get("text", "") for o in opts if "label" in o}
            p.questions.append({
                "id":               q.get("id", f"Q{num}"),
                "number":           num,
                "type_en":          q.get("type", "essay"),
                "score":            q.get("score", 2),
                "stem":             q.get("stem", ""),
                "options":          opts,
                "has_image_options": q.get("has_image_options", False),
                "figure_path":      q.get("figure_path"),   # e.g. "figures/q06.png"
                "source_pages":     [f"page-{q['source_page']:02d}"]
                                    if q.get("source_page") else [],
            })

        for a in data.get("answers", []):
            num = a.get("number", 0)
            p.answers[num] = {
                "correct":  str(a.get("correct", "")),
                "solution": str(a.get("solution", "")),
            }

        return p

    # ── 旧格式：paper.json + answer-key.json ──

    @classmethod
    def from_legacy(cls,
                    paper: dict,
                    answer_key: dict,
                    exam_meta: dict | None = None) -> "NormalizedPaper":
        p = cls()
        meta = paper.get("meta", {})
        exam = meta.get("exam", {})
        em = exam_meta or {}

        p.year = em.get("year") or exam.get("year")
        raw_district = em.get("district") or exam.get("district", "")
        p.district = raw_district + ("区" if raw_district and not raw_district.endswith("区") else "")
        p.exam_type = EXAM_TYPE_MAP.get(
            em.get("examType") or exam.get("examType", ""), "真题"
        )
        p.subject = em.get("subject") or exam.get("subject", "")
        p.full_score = meta.get("totalScore")
        p.duration = meta.get("duration")

        # 旧 answer-key：以 id 为 key
        ak_by_id = {
            a["id"]: a
            for a in answer_key.get("answers", [])
            if isinstance(a, dict) and "id" in a
        }

        for q in paper.get("questions", []):
            qid = q.get("id", "")
            num = _parse_qnum(qid)
            ak = ak_by_id.get(qid, {})
            score = q.get("score") or ak.get("score") or 2

            # 旧 stem 可能含选项行，尝试拆分
            stem_raw = q.get("stem", "")
            opts_list = q.get("options")  # 旧格式为 list[{label, text}]
            opts_dict: dict | None = None
            has_img = False

            if isinstance(opts_list, list) and opts_list:
                opts_dict = {o["label"]: o.get("text", "") for o in opts_list if "label" in o}
                has_img = all(v == "" or v == "[图]" for v in opts_dict.values())
            elif isinstance(opts_list, dict):
                opts_dict = opts_list
                has_img = all(v == "[图]" for v in opts_dict.values()) if opts_dict else False

            # 从 stem 中去除已嵌入的选项行（旧格式的遗留问题）
            stem = _strip_options_from_stem(stem_raw) if opts_dict else stem_raw

            # 旧 answer-key
            correct = ak.get("correct", "")
            if isinstance(correct, list):
                correct = "".join(correct) if all(len(c) == 1 for c in correct) else "；".join(str(c) for c in correct)
            else:
                correct = str(correct) if correct else ""

            p.answers[num] = {
                "correct":  correct,
                "solution": ak.get("correctSolution", ""),
            }
            p.questions.append({
                "id":               qid,
                "number":           num,
                "type_en":          q.get("type", "essay"),
                "score":            score,
                "stem":             stem,
                "options":          opts_dict,
                "has_image_options": has_img,
                "source_pages":     q.get("sourcePages", []),
            })

        return p


def _parse_qnum(qid: str) -> int:
    """'Q12' → 12, 'physics-q03' → 3, '5' → 5"""
    m = re.search(r"(\d+)", qid)
    return int(m.group(1)) if m else 0


def _parse_exam_name(p: "NormalizedPaper") -> None:
    """从 exam_name 字符串里解析 year / district / exam_type。"""
    name = p.exam_name
    m = re.search(r"(\d{4})", name)
    if m:
        p.year = int(m.group(1))
    m = re.search(r"([^\s]+区)", name)
    if m:
        p.district = m.group(1)
    for k, v in EXAM_TYPE_MAP.items():
        if k in name:
            p.exam_type = v
            break


def _strip_options_from_stem(stem: str) -> str:
    """从旧格式的 stem 字符串末尾去掉已嵌入的 A/B/C/D 选项行。"""
    return re.sub(r"\n+[A-D][\.、．]\s*.*$", "", stem, flags=re.DOTALL).strip()


# ─── enrich prompt ───────────────────────────────────────────────────────────

ENRICH_SYSTEM = (
    "你是中考命题专家。任务：给定一道题及其标准答案，标注其在课标知识点体系中的位置 + 难度。\n"
    "风格：精确、对照课标用词、避免重复造词。中文输出。"
)

ENRICH_USER_TEMPLATE = """\
请为下面这道题标注知识库元数据：

# 学科
{subject}

# 题号 / 题型 / 满分
{qid}（{qtype}，{score} 分）

# 题干
{stem}

# 选项（如有）
{options_text}

# 标准答案
{answer}

# 该学科可选 module（只能从这里选 1 个）
{modules_str}

# 课标知识点参考（节选）
{curriculum_excerpt}

输出 JSON（直接输出，不要 markdown 包裹）：
{{
  "knowledge_points": ["1-3个，命名对齐课标"],
  "module": "必须从给定列表选1个",
  "difficulty": "基础|中等|能力",
  "recommended_for": ["L0","L1","L2","L3"]
}}

规则：
- difficulty：基础=直接考概念/简单计算；中等=多步推理/公式应用；能力=综合/压轴
- recommended_for：基础→[L0-L3]；中等→[L1-L3]；能力→[L2-L3]；压轴→[L3]
"""


def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY 环境变量")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def _load_curriculum(subject: str) -> str:
    subj_en = _subject_en(subject)
    candidates = [
        ROOT / "knowledge-base" / "subjects" / subj_en / "curriculum.yaml",
        ROOT / "knowledge-base" / "subjects" / subj_en / f"{subj_en}-curriculum.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8")[:3500]
    return "（未找到 curriculum.yaml）"


def _options_text(opts: dict | None, has_image: bool) -> str:
    if not opts:
        return "（无选项）"
    if has_image:
        return "（选项为图片，内容待补全）"
    return "\n".join(f"{k}. {v}" for k, v in opts.items())


def _answer_with_context(correct: str, opts: dict | None, has_image: bool) -> str:
    """给 LLM 看的答案字符串，选择题附上选项文本帮助推断知识点。"""
    if not correct:
        return "（未知）"
    if not opts or has_image:
        return correct
    # 单选
    if len(correct) == 1 and correct in opts:
        return f"{correct}（{opts[correct]}）"
    # 多选
    if all(c in opts for c in correct):
        return "；".join(f"{c}（{opts[c]}）" for c in correct)
    return correct


def enrich_question(
    *,
    subject: str,
    qid: str,
    qtype: str,
    score: int,
    stem: str,
    opts: dict | None,
    has_image: bool,
    answer: str,
    modules: list[str],
    curriculum: str,
    cache_key: str | None,
) -> dict:
    cache_dir = ROOT / "scripts" / "knowledge-base" / ".cache"
    cache_dir.mkdir(exist_ok=True)
    if cache_key:
        f = cache_dir / f"{cache_key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))

    user = ENRICH_USER_TEMPLATE.format(
        subject=subject,
        qid=qid,
        qtype=qtype,
        score=score,
        stem=stem[:800],
        options_text=_options_text(opts, has_image),
        answer=_answer_with_context(answer, opts, has_image)[:400],
        modules_str=", ".join(modules),
        curriculum_excerpt=curriculum,
    )
    client = _client()
    resp = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": ENRICH_SYSTEM},
            {"role": "user",   "content": user},
        ],
        temperature=0.2,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    result = json.loads(resp.choices[0].message.content)
    if modules and result.get("module") not in modules:
        result["module"] = modules[0]
    if cache_key:
        (cache_dir / f"{cache_key}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


# ─── QC 状态推断 ──────────────────────────────────────────────────────────────

def _qc_status(q: dict, answer: str, solution: str, qtype: str) -> tuple[str, str]:
    """返回 (qc_status, qc_note)。"""
    issues = []
    if q.get("has_image_options"):
        issues.append("选项为图片，需人工补全选项内容")
    # 选择题但 options 为空（既非图片选项也没有文字）
    if qtype in {"单选", "多选"} and not q.get("options") and not q.get("has_image_options"):
        issues.append("选择题缺少 options 字段，可能是图片选项未标记或 OCR 遗漏")
    if not answer:
        issues.append("answer 为空")
    if qtype in SOLUTION_REQUIRED and solution == "__MISSING__":
        issues.append("解题步骤未提取，需补全 solution")
    if issues:
        return "needs_review", "；".join(issues)
    return "draft", ""


# ─── 结构描述 ─────────────────────────────────────────────────────────────────

def _derive_structure(questions: list[dict]) -> str:
    counts: dict[str, dict] = OrderedDict()
    for q in questions:
        t = q["type"]
        if t not in counts:
            counts[t] = {"count": 0, "score": 0}
        counts[t]["count"] += 1
        counts[t]["score"] += q["score"]
    return " + ".join(f"{v['count']}{k}({v['score']}分)" for k, v in counts.items())


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def enrich_paper(paper: NormalizedPaper, cache_prefix: str) -> dict:
    subject = paper.subject
    modules = _modules(subject)
    curriculum = _load_curriculum(subject)

    # 准备任务列表
    tasks = []
    for q in paper.questions:
        num = q["number"]
        ak = paper.answers.get(num, {"correct": "", "solution": ""})
        tasks.append((q, ak))

    # 并发 LLM 标注
    enriched: dict[int, dict] = {}

    def _do(item):
        q, ak = item
        num = q["number"]
        qtype = TYPE_MAP.get(q["type_en"], q["type_en"])
        print(f"  [Q{num}] 标注中 ...", file=sys.stderr, flush=True)
        r = enrich_question(
            subject=subject,
            qid=f"Q{num}",
            qtype=qtype,
            score=q["score"],
            stem=q["stem"],
            opts=q["options"],
            has_image=q["has_image_options"],
            answer=ak["correct"],
            modules=modules,
            curriculum=curriculum,
            cache_key=f"{cache_prefix}-Q{num}",
        )
        return num, r

    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(_do, t) for t in tasks]):
            num, r = fut.result()
            enriched[num] = r

    # 按题号排序组装
    questions_out = []
    for q, ak in tasks:
        num = q["number"]
        qtype = TYPE_MAP.get(q["type_en"], q["type_en"])
        r = enriched[num]

        answer  = ak["correct"]
        solution = ak["solution"] if ak["solution"] else (
            "__MISSING__" if qtype in SOLUTION_REQUIRED else ""
        )

        qc_status, qc_note = _qc_status(q, answer, solution, qtype)

        item: dict = {
            "id":               num,
            "type":             qtype,
            "score":            q["score"],
            "stem":             q["stem"],
        }
        # options 仅选择题写；无选项题省略该字段
        if q["options"] is not None:
            item["options"] = q["options"]
            item["has_image_options"] = q["has_image_options"]

        # figure：含图题目写入相对路径（相对于输出 YAML 所在目录）
        if q.get("figure_path"):
            item["figure"] = q["figure_path"]   # 由 _write_yaml 阶段实际复制

        item.update({
            "answer":           answer,
            "solution":         solution,
            "knowledge_points": r.get("knowledge_points", []),
            "module":           r.get("module", modules[0] if modules else ""),
            "difficulty":       r.get("difficulty", "中等"),
            "recommended_for":  r.get("recommended_for", ["L1", "L2", "L3"]),
            "qc_status":        qc_status,
            "qc_note":          qc_note,
        })
        questions_out.append(item)

    # 顶层
    header = {
        "year":             paper.year,
        "district":         paper.district,
        "exam_type":        paper.exam_type,
        "subject":          paper.subject,
        "full_score":       paper.full_score,
        "duration_minutes": paper.duration,
        "total_questions":  len(questions_out),
        "structure":        _derive_structure(questions_out),
        "questions":        questions_out,
    }
    return header


# ─── YAML 写出 ────────────────────────────────────────────────────────────────

def _write_yaml(result: dict, out_path: Path,
                paper_dir: Path | None = None) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 复制 figure 文件到 YAML 旁边的同名子目录
    # YAML: knowledge-base/exams/mock/physics/beijing/2026-chaoyang-yi.yaml
    # 图片: knowledge-base/exams/mock/physics/beijing/2026-chaoyang-yi/figures/q06.png
    exam_slug = out_path.stem   # e.g. "2026-chaoyang-yi"
    fig_dest_base = out_path.parent / exam_slug  # YAML旁的同名目录

    if paper_dir:
        copied = 0
        for q in result["questions"]:
            fig_rel = q.get("figure")   # e.g. "figures/q06.png"
            if not fig_rel:
                continue
            src = paper_dir / fig_rel
            if not src.exists():
                print(f"  ⚠️ 图片源文件不存在，跳过: {src}", file=sys.stderr)
                continue
            dst = fig_dest_base / fig_rel   # e.g. .../2026-chaoyang-yi/figures/q06.png
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            # 更新 YAML 中的 figure 路径为相对于 YAML 目录的路径
            q["figure"] = f"{exam_slug}/{fig_rel}"
            copied += 1
        if copied:
            print(f"  📷 复制 {copied} 张图片 → {fig_dest_base}/figures/", file=sys.stderr)

    # 统计 qc 摘要
    total = len(result["questions"])
    needs_review = sum(1 for q in result["questions"] if q["qc_status"] == "needs_review")
    draft = total - needs_review

    with out_path.open("w", encoding="utf-8") as f:
        f.write("# ============================================================\n")
        f.write(f"# {result['year']}年北京{result['district']}{result['exam_type']}"
                f"{result['subject']} — 自动生成\n")
        f.write("# ============================================================\n")
        f.write(f"# OCR: Qwen-VL-OCR  Enrich: qwen-max\n")
        f.write(f"# QC: draft={draft}  needs_review={needs_review}\n\n")
        yaml.safe_dump(result, f, allow_unicode=True, sort_keys=False, width=120)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="试卷结构化数据 → knowledge-base YAML"
    )
    # 新格式输入
    parser.add_argument("--input", "-i", type=Path,
                        help="新格式：<exam-dir>/structured-cloud/final.json")
    # 旧格式输入（兼容）
    parser.add_argument("--paper",      type=Path, help="旧格式：paper.json")
    parser.add_argument("--answer-key", type=Path, help="旧格式：answer-key.json")
    parser.add_argument("--exam-meta",  type=Path, help="旧格式：exam-meta.json（可选）")
    # 通用
    parser.add_argument("--subject", "-s",
                        help="学科（新格式时可省略，从 final.json 读取）")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="输出 YAML 路径")
    parser.add_argument("--cache-prefix", default=None,
                        help="LLM cache key 前缀（默认取输出文件名）")
    args = parser.parse_args()

    # ── 加载输入 ──
    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        # paper_dir = final.json 的上上级（即 <exam-dir>/），用于定位 figures/
        paper_dir = args.input.resolve().parent.parent
        paper = NormalizedPaper.from_final(data, subject_hint=args.subject or "",
                                           paper_dir=paper_dir)
        print(f"📄 final.json: {len(paper.questions)} 题", file=sys.stderr)
    elif args.paper and args.answer_key:
        paper_data = json.loads(args.paper.read_text(encoding="utf-8"))
        ak_data    = json.loads(args.answer_key.read_text(encoding="utf-8"))
        em_data    = json.loads(args.exam_meta.read_text(encoding="utf-8")) \
                     if args.exam_meta else None
        paper = NormalizedPaper.from_legacy(paper_data, ak_data, em_data)
        if args.subject:
            paper.subject = args.subject
        print(f"📄 paper.json: {len(paper.questions)} 题  "
              f"answer-key: {len(paper.answers)} 条", file=sys.stderr)
    else:
        parser.error("需要 --input 或 (--paper + --answer-key)")

    if not paper.subject:
        parser.error("无法推断学科，请指定 --subject")

    cache_prefix = args.cache_prefix or args.output.stem
    result = enrich_paper(paper, cache_prefix)
    _write_yaml(result, args.output, paper_dir=paper.paper_dir)

    total = result["total_questions"]
    nr = sum(1 for q in result["questions"] if q["qc_status"] == "needs_review")
    print(f"\n✅ {args.output}", file=sys.stderr)
    print(f"   {total} 题  needs_review={nr}  structure: {result['structure']}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
