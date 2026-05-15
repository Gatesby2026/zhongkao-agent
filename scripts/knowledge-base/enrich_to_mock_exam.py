#!/usr/bin/env python3
"""把学情报告流水线产物（paper.json + answer-key.json）转化为
knowledge-base/mock-exams/<科目>/beijing/<year>-<区>-<类型>.yaml 格式。

补充字段（LLM 推断）：
- knowledge_points: 涉及知识点（对照 curriculum.yaml）
- module: 模块标签（soundLightHeat / mechanics / ...）
- difficulty: 基础 / 中等 / 能力
- recommended_for: L0 / L1 / L2 / L3 推荐级别

CLI:
    python enrich_to_mock_exam.py \\
        --paper paper.json --answer-key answer-key.json \\
        --exam-meta exam-meta.json \\
        --output mock-exams/physics/beijing/2026-chaoyang-yi.yaml
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

try:
    import openai
    import yaml
except ImportError:
    print("pip install openai pyyaml", file=sys.stderr); sys.exit(1)


ROOT = Path(__file__).resolve().parents[2]


# ============== schema 映射 ==============

TYPE_MAP = {  # paper.json type → mock-exam YAML type
    "choice": "单选",
    "multi_choice": "多选",
    "fill_blank": "填空",
    "calculation": "计算",
    "experiment": "实验探究",
    "essay": "解答",
}

EXAM_TYPE_MAP = {
    "yimo": "一模", "一模": "一模",
    "ermo": "二模", "二模": "二模",
    "zhongkao": "真题", "中考": "真题",
    "qizhong": "期中", "qimo": "期末",
}


# 物理 modules 映射（基于现有 mock-exam YAML）
PHYSICS_MODULES = ["soundLightHeat", "mechanics", "electricity", "experiments", "calculation"]
MATH_MODULES = [
    "numbersAndExpressions", "equationsAndInequalities", "functions",
    "triangles", "quadrilaterals", "circles", "geometryComprehensive",
    "statisticsAndProbability",
]
SUBJECT_MODULES = {
    "物理": PHYSICS_MODULES, "physics": PHYSICS_MODULES,
    "数学": MATH_MODULES, "math": MATH_MODULES,
}


# ============== LLM enrich ==============

ENRICH_SYSTEM = """你是中考命题专家。任务：给定一道题及其标准答案，标注其在课标知识点体系中的位置 + 难度。
风格：精确、对照课标用词、避免重复造词。中文输出。"""


ENRICH_USER_TEMPLATE = """请为下面这道题标注知识库元数据：

# 学科
{subject}

# 题号 / 题型 / 满分
{qid}（{qtype}，{score} 分）

# 题干
{stem}

# 标准答案
{answer}

# 该学科可选 module（只能从这里选 1 个）
{modules_str}

# 课标知识点参考（节选）
{curriculum_excerpt}

# 输出 JSON

```json
{{
  "knowledge_points": ["..."],
  "module": "...",
  "difficulty": "基础|中等|能力",
  "recommended_for": ["L0","L1","L2","L3"]
}}
```

规则：
- `knowledge_points`：1-3 个，命名风格对齐课标（如"光的折射"、"串联电路分压"、"杠杆平衡条件"）
- `module`：必须从给定列表精确选 1 个
- `difficulty`：
  - 基础 = 直接考概念/简单计算
  - 中等 = 多步推理 / 公式应用
  - 能力 = 综合 / 压轴 / 多知识点交叉
- `recommended_for`：
  - 基础题 → [L0, L1, L2, L3]
  - 中等题 → [L1, L2, L3]
  - 能力题 → [L2, L3]
  - 压轴 → [L3]

不要 markdown 包裹，直接输出 JSON。"""


def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY 环境变量")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def load_curriculum(subject: str) -> str:
    """读 curriculum.yaml 节选给 LLM 当 prompt 上下文。"""
    candidates = [
        ROOT / "knowledge-base" / "subjects" / subject / "curriculum.yaml",
        ROOT / "knowledge-base" / "subjects" / subject / f"{subject}-curriculum.yaml",
    ]
    for p in candidates:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            # 节选：取前 3000 字符避免 prompt 太长
            return text[:3500]
    return "（未找到 curriculum.yaml）"


def enrich_question(
    *,
    subject: str,
    qid: str,
    qtype: str,
    score: int,
    stem: str,
    answer: str,
    modules: list[str],
    curriculum_excerpt: str,
    cache_key: str | None = None,
) -> dict:
    """LLM 给单题打标签。"""
    cache_dir = ROOT / "scripts" / "knowledge-base" / ".cache"
    cache_dir.mkdir(exist_ok=True)
    if cache_key:
        f = cache_dir / f"{cache_key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))

    user = ENRICH_USER_TEMPLATE.format(
        subject=subject, qid=qid, qtype=qtype, score=score,
        stem=stem[:800], answer=str(answer)[:600],
        modules_str=", ".join(modules),
        curriculum_excerpt=curriculum_excerpt,
    )
    client = _client()
    resp = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": ENRICH_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.2, max_tokens=512,
        response_format={"type": "json_object"},
    )
    result = json.loads(resp.choices[0].message.content)
    # 强制 module 在白名单中（subject 无白名单时不强制）
    if modules and result.get("module") not in modules:
        result["module"] = modules[0]  # fallback
    if cache_key:
        f.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


# ============== 主流程 ==============

def format_options(options, stem: str = "") -> str:
    """选项列表 → 文本（追加到 stem）。

    若 stem 里已经包含"A. xxx"形式的选项，跳过避免重复。
    """
    if not options:
        return ""
    # 简单启发：stem 末尾 200 字内已含 "A." 或 "A、" → 已有选项
    tail = stem[-300:]
    if any(f"{lab}." in tail or f"{lab}、" in tail for lab in ("A", "B", "C", "D")):
        return ""
    return "\n\n" + "\n".join(f"{o['label']}.{o['text']}" for o in options if o.get('label'))


def format_answer(ak_item: dict, qtype: str) -> str:
    """answer-key item → mock-exam 的 answer 字段。"""
    c = ak_item.get("correct")
    if c is not None:
        if isinstance(c, list):
            return "".join(c) if all(len(x) == 1 for x in c) else "; ".join(str(x) for x in c)
        return str(c)
    return ak_item.get("correctSolution", "")


def format_answer_with_options(ak_item: dict, options: list | None) -> str:
    """给 enrich LLM 的 answer 上下文：选择题答案 + 对应选项文本，帮助 LLM 推断知识点。

    例：answer='C', options=[{'A','陶瓷杯'},{'B','橡皮'},{'C','钢尺'},{'D','塑料水瓶'}]
        → 'C（钢尺）'
    """
    base = format_answer(ak_item, "")
    if not options or not base:
        return base
    # 单字母选择题
    if len(base) == 1 and base in "ABCDE":
        for o in options:
            if o.get("label") == base:
                return f"{base}（{o.get('text','')}）"
    # 多选
    if all(c in "ABCDE" for c in base) and len(base) > 1:
        parts = []
        for ch in base:
            for o in options:
                if o.get("label") == ch:
                    parts.append(f"{ch}（{o.get('text','')}）")
                    break
        return "; ".join(parts) if parts else base
    return base


def derive_structure(questions: list[dict]) -> str:
    """生成 'X选择(N分) + Y填空(M分) + ...' 结构描述。"""
    from collections import OrderedDict
    counts = OrderedDict()
    for q in questions:
        t = TYPE_MAP.get(q.get("type", ""), q.get("type", "?"))
        # 累计
        key = t
        if key not in counts:
            counts[key] = {"count": 0, "score": 0}
        counts[key]["count"] += 1
        counts[key]["score"] += q.get("score", 0)
    return " + ".join(
        f"{v['count']}{k}({v['score']}分)" for k, v in counts.items()
    )


def enrich_to_mock_exam(
    paper: dict,
    answer_key: dict,
    exam_meta: dict | None,
    subject: str,
    cache_prefix: str = "enrich",
) -> dict:
    """主转换：paper + answer-key → mock-exam dict。"""
    answers_by_id = {a["id"]: a for a in answer_key.get("answers", [])}
    modules = SUBJECT_MODULES.get(subject, [])
    curriculum = load_curriculum(subject if subject in ("math","chinese","english","physics","politics") else {"物理":"physics","数学":"math","语文":"chinese","英语":"english","道法":"politics"}.get(subject, subject))

    questions_out = []
    for q in paper.get("questions", []):
        qid = q.get("id", "")
        qtype_internal = q.get("type", "")
        qtype = TYPE_MAP.get(qtype_internal, qtype_internal)
        ak = answers_by_id.get(qid, {})
        score = q.get("score") or ak.get("score") or 2

        # 题干含选项（智能去重）
        stem_text = q.get("stem", "")
        full_question = stem_text + format_options(q.get("options"), stem=stem_text)

        # LLM enrich：答案附选项文本（帮 LLM 推断知识点）
        print(f"  [{qid}] 标注中 ...", file=sys.stderr, flush=True)
        enriched = enrich_question(
            subject=subject, qid=qid, qtype=qtype, score=score,
            stem=full_question,
            answer=format_answer_with_options(ak, q.get("options")),
            modules=modules, curriculum_excerpt=curriculum,
            cache_key=f"{cache_prefix}-{qid}",
        )

        item = {
            "id": int(qid.replace("Q", "")) if qid.startswith("Q") else qid,
            "type": qtype,
            "score": score,
            "question": full_question,
            "answer": format_answer(ak, qtype_internal),
            "solution": ak.get("correctSolution", ""),
            "knowledge_points": enriched.get("knowledge_points", []),
            "module": enriched.get("module", modules[0] if modules else ""),
            "difficulty": enriched.get("difficulty", "中等"),
            "recommended_for": enriched.get("recommended_for", ["L1","L2","L3"]),
        }
        questions_out.append(item)

    # 顶层元数据
    em = exam_meta or {}
    meta = paper.get("meta", {})
    exam = meta.get("exam", {})

    result = {
        "year": em.get("year") or exam.get("year"),
        "district": (em.get("district") or exam.get("district", "")) + ("区" if em.get("district") or exam.get("district") else ""),
        "exam_type": EXAM_TYPE_MAP.get(em.get("examType") or exam.get("examType",""), "真题"),
        "subject": em.get("subject") or exam.get("subject", subject),
        "full_score": meta.get("totalScore"),
        "duration_minutes": meta.get("duration"),
        "total_questions": len(questions_out),
        "structure": derive_structure(questions_out),
        "questions": questions_out,
    }
    return result


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--answer-key", type=Path, required=True)
    parser.add_argument("--exam-meta", type=Path)
    parser.add_argument("--subject", required=True,
                        help="学科：物理 / 数学 / 语文 / 英语 / 道法")
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--cache-prefix", default=None)
    args = parser.parse_args()

    paper = json.loads(args.paper.read_text(encoding="utf-8"))
    ak = json.loads(args.answer_key.read_text(encoding="utf-8"))
    em = json.loads(args.exam_meta.read_text(encoding="utf-8")) if args.exam_meta else None
    cache_prefix = args.cache_prefix or args.output.stem

    print(f"📄 paper: {len(paper.get('questions',[]))} 题, answer-key: {len(ak.get('answers',[]))} 题",
          file=sys.stderr)
    result = enrich_to_mock_exam(paper, ak, em, subject=args.subject, cache_prefix=cache_prefix)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # 写 YAML 加注释头
    with args.output.open("w", encoding="utf-8") as f:
        f.write(f"# ============================================================\n")
        f.write(f"# {result['year']}年北京{result['district']}{result['exam_type']}{result['subject']} — 自动生成\n")
        f.write(f"# ============================================================\n")
        f.write(f"# 数据来源: gaokzx.com OCR + Qwen-VL-OCR + qwen-max enrich\n")
        f.write(f"# 满分: {result['full_score']} 分 时长: {result['duration_minutes']} 分钟\n\n")
        yaml.safe_dump(result, f, allow_unicode=True, sort_keys=False, width=200)

    print(f"\n✅ {args.output}", file=sys.stderr)
    print(f"   {result['total_questions']} 题, 结构: {result['structure']}", file=sys.stderr)


if __name__ == "__main__":
    main()
