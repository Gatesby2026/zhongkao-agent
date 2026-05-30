#!/usr/bin/env python3
"""主观题辅助批改 — 两种方案对照。

方案 A: 用题目上下文做 OCR 后修正（qwen-max 纯文本）
    输入：讯飞 OCR 草稿 + 题干 + 标准答案 + 评分要点
    输出：修正后的学生作答 + 与标准答案要点对照 + 建议得分

方案 B: 大模型直接看图阅卷（qwen-vl-max）
    输入：学生手写裁切原图 + 题干 + 标准答案 + 评分要点
    输出：模型读到的学生作答 + 与标准答案要点对照 + 建议得分

两条独立路径，方便对照真实效果决定最终方案。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

try:
    import openai
except ImportError:
    print("pip install openai", file=sys.stderr); sys.exit(1)

try:
    import yaml
except ImportError:
    print("pip install pyyaml", file=sys.stderr); sys.exit(1)


def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


# ─── 通用 prompt 框架 ────────────────────────────────────────────────────────

GRADE_SCHEMA = """输出 JSON（直接给，不要 markdown 围栏）：
{{
  "correctedText": "学生最可能写的真实内容（修正 OCR 错字 / 看清手写）",
  "matchedPoints": ["命中的标准答案要点列表"],
  "missedPoints": ["未答出的要点"],
  "suggestedScore": <0-{full_score} 整数或半分>,
  "scoreReason": "评分理由（哪些点得分、哪些扣分、扣多少）",
  "needsTeacherReview": <true/false 模型自己评估是否需要老师复核>
}}"""


# ─── 方案 A: OCR 后处理（纯文本，qwen-max）────────────────────────────────

PROMPT_A = """你是中考物理阅卷助手。请基于学生答案 OCR 草稿 + 题目上下文，
做两件事：
1. **修正 OCR 错字** — 学生书写潦草时讯飞 OCR 会读错（如"分配"→"匀速"、
   "白张林衣"→"长木板"）。根据物理常识和上下文判断学生真正写的内容。
2. **对照标准答案评分** — 逐要点对照，给出建议得分和理由。

⚠️ 关键约束：
- **忠实于学生原文**：只修明显 OCR 错误（语义/物理常识不通），不要补全学生
  没写的内容
- **不要把错答美化成对答**：如果学生真的答错了，OCR 修正后仍然是错的
- 评分建议**仅供老师参考**，不要默认采纳

# 题目（{qtype}，{full_score} 分）
{stem}

# 标准答案
{answer}

# 评分要点 / 完整解析
{solution}

# 学生答案 OCR 草稿（讯飞手写识别）
{ocr_text}

""" + GRADE_SCHEMA


def correct_with_context(stem: str, std_answer: str, solution: str,
                          full_score: int, qtype: str,
                          ocr_text: str, *,
                          client=None, model: str = "qwen-max") -> dict:
    """方案 A：OCR 后处理。"""
    client = client or _client()
    prompt = PROMPT_A.format(
        qtype=qtype, full_score=full_score, stem=stem[:600],
        answer=std_answer[:600], solution=(solution or "—")[:800],
        ocr_text=(ocr_text or "（OCR 无输出）")[:600],
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是严谨的中考物理阅卷助手。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=1024,
        response_format={"type": "json_object"},
        timeout=120,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    return json.loads(raw)


# ─── 方案 B: 大模型直接看图（qwen-vl-max）─────────────────────────────────

PROMPT_B = """你是中考物理阅卷助手。请直接看学生手写答题区图片，结合题目上下文：
1. **读出学生的实际作答内容** — 物理潦草手写常见错读，注意结合上下文判断
2. **对照标准答案评分** — 逐要点对照，给出建议得分和理由

⚠️ 关键约束：
- 忠实于图片所见，不要"美化"学生答案
- 评分建议**仅供老师参考**

# 题目（{qtype}，{full_score} 分）
{stem}

# 标准答案
{answer}

# 评分要点 / 完整解析
{solution}

""" + GRADE_SCHEMA


def _img_b64(path: Path, max_dim: int = 2000) -> str:
    from PIL import Image
    import io
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


_ESSAY_TYPE_KEYWORDS = ("作文", "essay", "composition", "写作")


def _is_essay(qtype: str) -> bool:
    if not qtype:
        return False
    low = qtype.lower()
    return any(k in low or k in qtype for k in _ESSAY_TYPE_KEYWORDS)


def _full_score_fallback(full_score: int, why: str) -> dict:
    """作文/写作类 AI 评分失败 → 按满分占位，标待老师小分校准。
    （口径：能评则评，不能评按满分计——不蒙数也不让总分被作文压低）"""
    return {
        "correctedText": "",
        "matchedPoints": [],
        "missedPoints": [],
        "suggestedScore": full_score,
        "scoreReason": f"作文 AI 暂未稳定评分（{why}），按满分占位等老师小分校准",
        "needsTeacherReview": True,
        "_essayFullFallback": True,
    }


def _call_grade_b(stem, std_answer, solution, full_score, qtype,
                  image_path, client, model) -> dict:
    prompt = PROMPT_B.format(
        qtype=qtype, full_score=full_score, stem=stem[:600],
        answer=std_answer[:600], solution=(solution or "—")[:800],
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _img_b64(image_path)}},
            {"type": "text", "text": prompt},
        ]}],
        temperature=0.0,
        max_tokens=1024,
        response_format={"type": "json_object"},
        timeout=120,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    return json.loads(raw)


def read_and_grade(stem: str, std_answer: str, solution: str,
                    full_score: int, qtype: str,
                    image_path: Path, *,
                    client=None, model: str = "qwen-vl-max") -> dict:
    """方案 B：大模型直接看图。

    作文/写作类（is_essay）走"能评则评，不能评按满分计"兜底：
      - 模型抛错 / 返回不可解析 / suggestedScore 缺失或越界 → 满分占位 +
        needsTeacherReview=True（口径见 _full_score_fallback）
    非作文：按原行为（异常向上抛，由调用方处理）。
    """
    client = client or _client()
    essay = _is_essay(qtype)
    try:
        r = _call_grade_b(stem, std_answer, solution, full_score, qtype,
                          image_path, client, model)
    except Exception as e:
        if essay:
            return _full_score_fallback(full_score, f"{type(e).__name__}")
        raise

    if essay:
        sc = r.get("suggestedScore") if isinstance(r, dict) else None
        try:
            sc_f = float(sc)
        except (TypeError, ValueError):
            return _full_score_fallback(full_score, "返回无 suggestedScore")
        if not (0 <= sc_f <= float(full_score)):
            return _full_score_fallback(full_score, "返回分数越界")
        # 作文 AI 能给出有效分 → 采用，但仍标 needsTeacherReview=True
        r["needsTeacherReview"] = True
    return r


# ─── 加载试卷 yaml ───────────────────────────────────────────────────────────

# ─── 兜底：整页 vl-max 看图给一组主观题评分 ─────────────────────────────
# 用途：Phase B 腾讯云方框 + 严格 fallback 命中率 < 50% 时触发
# 不依赖框检测/讯飞印刷题号 OCR，跨区稳定

_BATCH_PROMPT = """这是一名学生中考答题卡的多张照片。请逐题在图中**找到该题
的学生作答**（按题号定位，作答区通常是黑色方框包围的区域），结合标准答案评分。

**忠实学生原作**：没写就 0 分、写错不美化；评分仅供老师参考；
**只输出本任务给的题号**，不要输出其它题。

# 需评分的主观题
{qlist}

严格输出 JSON（不要 markdown 围栏）：
{{
  "grades": [
    {{"qnum": 16, "studentAnswer": "学生作答原文（抄读，潦草也尽量原样）",
      "matchedPoints": ["对的要点1","对的要点2"],
      "missedPoints":  ["没答出的要点1"],
      "suggestedScore": 2, "scoreReason": "得分依据 30-80 字",
      "needsTeacherReview": false}},
    ...
  ]
}}

每题都要给。完全没找到学生作答 → suggestedScore=0、needsTeacherReview=true、
studentAnswer="（系统未找到该题作答区）"。"""


def batch_grade_full_pages(image_paths: list[Path],
                            subj_qs: list[dict],
                            *, model: str = "qwen-vl-max",
                            max_imgs: int = 6) -> dict[int, dict]:
    """整页看 N 张照片，给 subj_qs 列表里每题一份 grade。

    Args:
        subj_qs: [{id, type, stem, answer, solution, score}, ...]
                 (来自 load_paper_questions 的 dict.values() 子集)
    Returns: {qid_int: grade_dict}  与 read_and_grade 同 schema
    """
    client = _client()
    qlist_lines = []
    for q in subj_qs:
        qid = q.get("id")
        if isinstance(qid, str):
            m = re.match(r"Q?(\d+)", qid)
            if m: qid = int(m.group(1))
        if not isinstance(qid, int): continue
        qlist_lines.append(
            f"- 题号{qid}（{q.get('type','')}，{q.get('score',0)} 分）\n"
            f"  题干：{str(q.get('stem',''))[:300]}\n"
            f"  标答：{str(q.get('answer',''))[:300]}\n"
            f"  解析：{str(q.get('solution',''))[:200]}\n"
        )
    qlist_txt = "\n".join(qlist_lines)
    content = []
    for p in image_paths[:max_imgs]:
        content.append({
            "type": "image_url",
            "image_url": {"url": _img_b64(p)},
        })
    content.append({
        "type": "text",
        "text": _BATCH_PROMPT.format(qlist=qlist_txt),
    })
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=0.0, max_tokens=6144,
        response_format={"type": "json_object"}, timeout=240,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    out: dict[int, dict] = {}
    for g in (data.get("grades") or []):
        if not isinstance(g, dict): continue
        try:
            qn = int(g.get("qnum") or g.get("qid") or 0)
        except (TypeError, ValueError):
            continue
        # 与 read_and_grade 一致的 schema
        out[qn] = {
            "correctedText": str(g.get("studentAnswer") or ""),
            "matchedPoints": list(g.get("matchedPoints") or []),
            "missedPoints":  list(g.get("missedPoints") or []),
            "suggestedScore": g.get("suggestedScore"),
            "scoreReason":   str(g.get("scoreReason") or ""),
            "needsTeacherReview": bool(g.get("needsTeacherReview", True)),
            "_source": "vlmax_full_page_fallback",
        }
    return out


def load_paper_questions(yaml_path: Path) -> dict[int, dict]:
    """从知识库 yaml 加载题目信息。返回 {qid_int: question_dict}"""
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    out = {}
    for q in data.get("questions", []):
        qid = q.get("id")
        if isinstance(qid, int):
            out[qid] = q
        elif isinstance(qid, str):
            m = re.match(r"Q?(\d+)", qid)
            if m:
                out[int(m.group(1))] = q
    return out


# ─── CLI 测试 ────────────────────────────────────────────────────────────────

def _main():
    ap = argparse.ArgumentParser(
        description="主观题辅助批改 — 方案 A/B 对照"
    )
    ap.add_argument("--standard", required=True, type=Path,
                    help="试卷 yaml（含 stem/answer/solution/score）")
    ap.add_argument("--qid", required=True, type=int, help="题号")
    ap.add_argument("--ocr-text", help="（方案 A）讯飞 OCR 文本")
    ap.add_argument("--image", type=Path, help="（方案 B）学生作答原图")
    ap.add_argument("--method", choices=["A", "B", "both"], default="both")
    args = ap.parse_args()

    paper = load_paper_questions(args.standard)
    q = paper.get(args.qid)
    if not q:
        print(f"❌ 试卷 yaml 里找不到 Q{args.qid}", file=sys.stderr); sys.exit(1)

    print(f"\n=== Q{args.qid} ({q['type']}, {q['score']} 分) ===")
    print(f"标准答案: {q.get('answer','')}")
    print()

    client = _client()
    args_common = dict(
        stem=q.get("stem", ""),
        std_answer=str(q.get("answer", "")),
        solution=q.get("solution", ""),
        full_score=q.get("score", 4),
        qtype=q.get("type", "解答"),
        client=client,
    )

    if args.method in ("A", "both"):
        if not args.ocr_text:
            print("⚠️ 方案 A 需要 --ocr-text"); sys.exit(1)
        print("=== 方案 A：OCR 后处理（qwen-max）===")
        r = correct_with_context(ocr_text=args.ocr_text, **args_common)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print()

    if args.method in ("B", "both"):
        if not args.image:
            print("⚠️ 方案 B 需要 --image"); sys.exit(1)
        print("=== 方案 B：大模型看图（qwen-vl-max）===")
        r = read_and_grade(image_path=args.image, **args_common)
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
