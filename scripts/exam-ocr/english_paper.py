#!/usr/bin/env python3
"""english_paper — 北京中考英语试卷 PNG → final.json（v1 passage 二级模型）。

与物理 v2 / 数学 v1 路线对偶；但因英语含「篇章共享题」（完形 1 篇 + 8 题、
阅读理解 4 篇 × 4-5 题、阅读表达 1 篇 + 4 题），引入 **passages** 二级数据
模型，每题用 `passage_id` 关联文章，避免每题重复存文章。

流水线：
  1. 调腾讯 GeneralAccurateOCR 全 12 页（带 cache）
  2. 拼成 full_text，按 "参考答案" marker 切题目页 vs 答案页
  3. 题目页按 5 大题（一/二/三/四/五）切 section
  4. section 内识别 passage + questions：
     - 一、单项填空：纯题（无 passage）
     - 二、完形填空：1 篇 passage（含数字空位标记）+ 8 题
     - 三、阅读理解：多 sub-section（一/二/三/四），每 sub 1 篇 + 多题
     - 四、阅读表达：1 篇 + 多题主观
     - 五、文段表达：纯 essay
  5. 答案页解析：每题"N.X" 格式抽 correct + 主观题取 sample answer
  6. 输出 final.json + 兼容 exam-review yaml schema（passages 字段新增）

用法:
  TENCENT_OCR_SECRET_ID=... TENCENT_OCR_SECRET_KEY=... \\
  DASHSCOPE_API_KEY=... \\
    python3 scripts/exam-ocr/english_paper.py \\
      knowledge-original/<series>/<round>/<region>/english --subject english
"""
from __future__ import annotations

import argparse, base64, io, json, os, re, sys, shutil
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("pip install pillow", file=sys.stderr); sys.exit(1)
try:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.ocr.v20181119 import ocr_client, models
except ImportError:
    print("pip install tencentcloud-sdk-python-ocr", file=sys.stderr); sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import derive_out_dir  # noqa: E402

# ─── 北京中考英语结构 ────────────────────────────────────────────────────────

SECTIONS = [
    # (大题标题正则, 题号范围, type, 默认分值[每题])
    (re.compile(r"^\s*一、\s*单项填空"),    range(1, 13),  "choice",          0.5),
    (re.compile(r"^\s*二、\s*完形填空"),    range(13, 21), "cloze",           1),
    (re.compile(r"^\s*三、\s*阅读理解"),    range(21, 34), "reading",         2),
    (re.compile(r"^\s*四、\s*阅读(?:与|表达)"), range(34, 38), "reading_express", None),
    (re.compile(r"^\s*五、\s*文段表达"),    range(38, 39), "essay",           10),
]
EXPRESS_SCORES = {34: 2, 35: 2, 36: 2, 37: 4}  # 阅读表达分值不均
ANSWER_MARKER = re.compile(r"参考答案|答案及评分")

# ─── API ─────────────────────────────────────────────────────────────────────

_client = None
def _get_client():
    global _client
    if _client: return _client
    sid = os.environ.get("TENCENT_OCR_SECRET_ID", "")
    skey = os.environ.get("TENCENT_OCR_SECRET_KEY", "")
    if not (sid and skey):
        sys.exit("缺 TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY")
    cred = credential.Credential(sid, skey)
    http = HttpProfile(); http.endpoint = "ocr.tencentcloudapi.com"
    _client = ocr_client.OcrClient(cred, "ap-guangzhou",
                                    ClientProfile(httpProfile=http))
    return _client


def _img_to_b64(p: Path, max_dim=3000):
    img = Image.open(p)
    w, h = img.size
    if max(w, h) > max_dim:
        r = max_dim / max(w, h)
        img = img.resize((int(w*r), int(h*r)), Image.LANCZOS)
    img = img.convert("RGB")
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def _ocr_page(img: Path, cache: Path, force=False) -> str:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and not force:
        return cache.read_text(encoding="utf-8")
    req = models.GeneralAccurateOCRRequest()
    req.ImageBase64 = _img_to_b64(img)
    resp = _get_client().GeneralAccurateOCR(req)
    d = json.loads(resp.to_json_string())
    txt = "\n".join(td.get("DetectedText","") for td in d.get("TextDetections", []))
    cache.write_text(txt, encoding="utf-8")
    return txt


# ─── 切大题 ──────────────────────────────────────────────────────────────────

def _split_sections(full: str) -> dict[str, str]:
    """按"一、/二、/三、/四、/五、" 标题切 5 段题目正文。

    返回 {"choice": "...", "cloze": "...", "reading": "...",
         "reading_express": "...", "essay": "..."}
    """
    lines = full.split("\n")
    section_starts: list[tuple[int, str]] = []  # (line_idx, type)
    for i, ln in enumerate(lines):
        for re_title, _, typ, _ in SECTIONS:
            if re_title.search(ln):
                section_starts.append((i, typ))
                break
    # 截到答案页前
    answer_idx = next((i for i, ln in enumerate(lines)
                       if ANSWER_MARKER.search(ln)), len(lines))
    out: dict[str, str] = {}
    for k, (start, typ) in enumerate(section_starts):
        end = section_starts[k+1][0] if k+1 < len(section_starts) else answer_idx
        if start >= answer_idx: break
        end = min(end, answer_idx)
        out.setdefault(typ, "\n".join(lines[start:end]).strip())
    return out


# ─── section 一：单项填空 ───────────────────────────────────────────────────

_OPT_INLINE_RE = re.compile(
    r"([A-D])\s*[.、．]\s*([^A-D\n]+?)(?=\s*[A-D]\s*[.、．]|$)", re.DOTALL)
_NUM_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.*)$", re.MULTILINE)


def _split_choice_questions(text: str, num_range: range) -> list[dict]:
    """按 ^N. 切单项填空题，每题抽 ABCD 选项。"""
    # 找所有题号位置
    matches = list(_NUM_HEAD_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        if n not in num_range: continue
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        chunk = text[m.start():end]
        # 切 stem 与选项：找第一个 "A． " 之前是 stem
        a_pos = re.search(r"\bA\s*[.、．]\s*", chunk)
        if a_pos:
            stem_full = chunk[:a_pos.start()]
            opts_part = chunk[a_pos.start():]
        else:
            stem_full = chunk; opts_part = ""
        # stem 去前导题号
        stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem_full).strip()
        # 抽选项
        opts: dict[str, str] = {}
        for om in _OPT_INLINE_RE.finditer(opts_part):
            opts[om.group(1)] = om.group(2).strip().rstrip(".")
        out.append({"number": n, "stem": stem, "options": opts})
    return out


# ─── section 二：完形填空 ───────────────────────────────────────────────────

def _parse_cloze(text: str, num_range: range) -> tuple[dict, list[dict]]:
    """切完形填空：1 篇文章（含空位编号） + 8 题（每题 4 选项）。

    文章正文里数字 13/14/15/... 直接作为空位标记。
    选项行：N. A. xx / B. xx / C. xx / D. xx
    """
    # 找第一个题号 ^N. 选项行（A. xxx）作为"选项段"起点
    lines = text.split("\n")
    opt_start = None
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*(\d{1,2})\s*[.、．]\s*A\s*[.、．]", ln)
        if m and int(m.group(1)) in num_range:
            opt_start = i; break
    if opt_start is None:
        return {"body": text.strip()}, []
    # 文章在 opt_start 之前（去除大题标题 + instruction 行）
    body_lines = []
    in_body = False
    for ln in lines[:opt_start]:
        s = ln.strip()
        if not s: continue
        if re.search(r"完形填空|选择最佳选项|阅读下面", s): continue
        in_body = True
        body_lines.append(s)
    body = "\n".join(body_lines).strip()
    # 选项部分：8 题 × 4 行
    opts_block = "\n".join(lines[opt_start:]).strip()
    # 切题：以 "^N. A． " 起点
    q_starts = []
    for m in re.finditer(r"^\s*(\d{1,2})\s*[.、．]\s*A\s*[.、．]",
                          opts_block, re.MULTILINE):
        q_starts.append((int(m.group(1)), m.start()))
    questions = []
    for i, (n, pos) in enumerate(q_starts):
        end = q_starts[i+1][1] if i+1 < len(q_starts) else len(opts_block)
        chunk = opts_block[pos:end]
        # 抽 4 个选项（每行一个或多行）
        opts = {}
        for om in re.finditer(r"\b([A-D])\s*[.、．]\s*([^\nA-D]+?)(?=\s*[A-D]\s*[.、．]|\s*$)",
                              chunk, re.DOTALL):
            opts[om.group(1)] = om.group(2).strip().rstrip(".")
        if len(opts) >= 4:
            questions.append({"number": n,
                              "blank_index": n - num_range.start + 1,
                              "options": opts, "stem": ""})
    passage = {"body": body, "type": "cloze"}
    return passage, questions


# ─── section 三：阅读理解 ───────────────────────────────────────────────────

_SUB_RE = re.compile(r"^\s*[(（]([一二三四五六])[)）]")


def _parse_reading(text: str, num_range: range) -> tuple[list[dict], list[dict]]:
    """切阅读理解：多 sub-section（一/二/三/四），每 sub 1 篇 + 多题。

    返回 (passages, questions)。
    """
    lines = text.split("\n")
    # 找 sub-section 起点（"(一)" "(二)" ...）
    sub_starts = []
    for i, ln in enumerate(lines):
        if _SUB_RE.match(ln):
            sub_starts.append(i)
    passages = []
    questions = []
    for k, si in enumerate(sub_starts):
        sub_end = sub_starts[k+1] if k+1 < len(sub_starts) else len(lines)
        sub_lines = lines[si:sub_end]
        # 该 sub 内：找题号锚点
        sub_text = "\n".join(sub_lines)
        q_anchors = list(_NUM_HEAD_RE.finditer(sub_text))
        q_anchors = [a for a in q_anchors if int(a.group(1)) in num_range]
        if not q_anchors:
            continue
        # 第一个题号之前 = passage body
        body = sub_text[:q_anchors[0].start()].strip()
        # 清理 sub-section 标题行（"(一) Amy..."）头部
        body = re.sub(r"^\s*[(（][一二三四五六][)）]", "", body).strip()
        pid = f"reading_{si}"
        passages.append({"id": pid, "type": "reading", "body": body})
        # 切题
        for i, am in enumerate(q_anchors):
            n = int(am.group(1))
            end = q_anchors[i+1].start() if i+1 < len(q_anchors) else len(sub_text)
            chunk = sub_text[am.start():end]
            # 切 stem / options
            a_pos = re.search(r"\bA\s*[.、．]\s*", chunk)
            stem = chunk[:a_pos.start()] if a_pos else chunk
            stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem).strip()
            opts = {}
            if a_pos:
                opt_block = chunk[a_pos.start():]
                for om in re.finditer(
                    r"\b([A-D])\s*[.、．]\s*([^\n]+?)(?=\n\s*[A-D]\s*[.、．]|\Z)",
                    opt_block, re.DOTALL):
                    opts[om.group(1)] = om.group(2).strip().rstrip(".")
            questions.append({
                "number": n, "stem": stem, "options": opts,
                "passage_id": pid, "type": "choice"
            })
    return passages, questions


# ─── section 四：阅读表达 ───────────────────────────────────────────────────

def _parse_express(text: str, num_range: range) -> tuple[dict, list[dict]]:
    """阅读表达：1 篇文章 + 主观题（无选项）"""
    lines = text.split("\n")
    q_anchors = [m for m in _NUM_HEAD_RE.finditer(text)
                 if int(m.group(1)) in num_range]
    if not q_anchors:
        return {"body": text.strip()}, []
    body = text[:q_anchors[0].start()].strip()
    # 清大题标题
    body = re.sub(r"^\s*四、\s*阅读(?:与|表达)[^\n]*\n", "", body).strip()
    body = re.sub(r"^\s*阅读下面[^\n]+\n", "", body, flags=re.MULTILINE).strip()
    passage = {"id": "express", "type": "reading_express", "body": body}
    questions = []
    for i, m in enumerate(q_anchors):
        n = int(m.group(1))
        end = q_anchors[i+1].start() if i+1 < len(q_anchors) else len(text)
        stem = text[m.start():end].strip()
        stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem).strip()
        questions.append({
            "number": n, "stem": stem, "options": None,
            "passage_id": "express", "type": "essay"
        })
    return passage, questions


# ─── section 五：文段表达 ───────────────────────────────────────────────────

def _parse_essay(text: str, num_range: range) -> list[dict]:
    """文段表达：1 个 essay 题。"""
    lines = text.strip().split("\n")
    # 跳过大题标题，剩下都是 stem
    body = []
    for ln in lines[1:]:
        s = ln.strip()
        if not s: continue
        body.append(s)
    stem = "\n".join(body).strip()
    return [{"number": num_range.start, "stem": stem, "options": None,
             "type": "essay"}]


# ─── 答案页解析 ─────────────────────────────────────────────────────────────

def _parse_answers(answer_text: str) -> list[dict]:
    """从答案页文本解析每题答案。

    格式：
      "1.D\n2.D\n..." 选择题字母
      "34.(The writer uses...)" 阅读表达主观题
      "37.写出居住地附近..." 写作评分标准
    """
    out: list[dict] = []
    cur_num = None; cur_buf: list[str] = []

    def _flush():
        if cur_num is None: return
        sol = "\n".join(cur_buf).strip()
        # 选择题：sol 是单字母 A-D
        correct = sol if re.fullmatch(r"[A-D]+", sol) else ""
        out.append({"number": cur_num, "correct": correct, "solution": sol})

    for ln in answer_text.split("\n"):
        s = ln.strip()
        if not s: continue
        # 跳大题标题
        if re.match(r"^[一二三四五六]、|第[一二]部分|^\d{4}\.\d|参考答案", s):
            continue
        m = re.match(r"^\s*(\d{1,2})\s*[.、．]\s*(.*)$", s)
        if m and 1 <= int(m.group(1)) <= 40:
            _flush()
            cur_num = int(m.group(1))
            cur_buf = [m.group(2).strip()]
        else:
            if cur_num is not None: cur_buf.append(s)
    _flush()
    return out


# ─── 主流程 ──────────────────────────────────────────────────────────────────

def parse_paper(src: Path, out_dir: Path, force=False) -> dict:
    images_dir = src / "images"
    pages = sorted(images_dir.glob("page-*.png"))
    if not pages:
        sys.exit(f"无 images: {images_dir}")
    cache_dir = out_dir / "tencent-cache" / "general"

    # 1. OCR 全 12 页
    full_text = ""
    for p in pages:
        full_text += "\n" + _ocr_page(p, cache_dir / f"{p.stem}.txt", force)
    # 2. 切题目页 vs 答案页
    am = ANSWER_MARKER.search(full_text)
    q_text = full_text[:am.start()] if am else full_text
    a_text = full_text[am.start():] if am else ""
    # 3. 切 5 大题
    sec = _split_sections(q_text)

    passages: list[dict] = []
    questions: list[dict] = []

    if "choice" in sec:
        for q in _split_choice_questions(sec["choice"], range(1, 13)):
            q["type"] = "choice"; q["score"] = 0.5
            questions.append(q)
    if "cloze" in sec:
        cz_pass, cz_qs = _parse_cloze(sec["cloze"], range(13, 21))
        cz_pass["id"] = "cloze"
        passages.append(cz_pass)
        for q in cz_qs:
            q["passage_id"] = "cloze"; q["type"] = "cloze"; q["score"] = 1
            questions.append(q)
    if "reading" in sec:
        rd_pass, rd_qs = _parse_reading(sec["reading"], range(21, 34))
        passages.extend(rd_pass)
        for q in rd_qs:
            q["score"] = 2
            questions.append(q)
    if "reading_express" in sec:
        ex_pass, ex_qs = _parse_express(sec["reading_express"], range(34, 38))
        passages.append(ex_pass)
        for q in ex_qs:
            q["score"] = EXPRESS_SCORES.get(q["number"], 2)
            questions.append(q)
    if "essay" in sec:
        for q in _parse_essay(sec["essay"], range(38, 39)):
            q["score"] = 10
            questions.append(q)

    # 4. 答案
    answers = _parse_answers(a_text)

    full_score = sum(q.get("score", 0) for q in questions) or None
    return {
        "subject": "english",
        "full_score": full_score,
        "passages": passages,
        "questions": questions,
        "answers": answers,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", type=Path)
    ap.add_argument("--subject", default="english")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    src = a.src_dir.resolve()
    if not (src / "images").is_dir():
        sys.exit(f"无 images/: {src}")
    out_dir = derive_out_dir(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    structured = out_dir / "structured-cloud"
    structured.mkdir(parents=True, exist_ok=True)

    result = parse_paper(src, out_dir, force=a.force)
    fj = structured / "final.json"
    fj.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    qs = result["questions"]; ans = result["answers"]
    print(f"[english_paper] ✅ {fj}", flush=True)
    print(f"   题号: {sorted(set(q['number'] for q in qs))}", flush=True)
    print(f"   passages: {len(result['passages'])}  questions: {len(qs)}  "
          f"answers: {len(ans)}  full_score: {result['full_score']}", flush=True)


if __name__ == "__main__":
    main()
