#!/usr/bin/env python3
"""tencent_paper — 用腾讯云 QuestionSplitOCR 单 API 替换整套 OCR+layout+图分配。

设计与决策依据见 docs/architecture/KB-LAYOUT 与 SKILL 「已决结论」。

替代关系：
  旧（已弃）：ocr_paper(qwen-vl) → paddle layout → assign_figures
  新（本脚本）：QuestionSplitOCR / 单次/页 → 结构化 question+figure+option

API 返回的每题对象自带：
  Question.Text + Coord         — 题干文本 + 4 点 bbox
  Option[].Text + Coord         — 选项文本 + bbox
  Figure[].Coord                — 题图 bbox（图选项题给 4 个）
  Table[].Coord                 — 表格 bbox
  GroupType                     — multiple-choice / fill-in-the-blank /
                                  problem-solving / arithmetic
  Coord                         — 整题外接矩形

后处理职责：
  1. 跨页续题合并（题号锚点 ^\\d+\\.；无号块归到上一有号块）
  2. 答案页剥离（"参考答案" 关键字 → 该页起切答案解析模式）
  3. 题型推断（北京物理特征：Q1-12 单选 / Q13-15 多选 / 其余按 GroupType + 关键字）
  4. 裁切 figures（每题 Figure[] 外接矩形 → figures/qNN.png）
  5. 输出与 enrich_to_mock_exam 兼容的 final.json

用法：
  TENCENT_OCR_SECRET_ID=... TENCENT_OCR_SECRET_KEY=... \\
    python3 scripts/exam-ocr/tencent_paper.py \\
      knowledge-original/<series>/<round>/<region>/<subject> --subject physics
  [--force]   清 API 缓存重跑
  [--no-crop] 跳过裁图（只产 final.json，调试用）
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

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
from paths import derive_out_dir, repo_root  # noqa: E402


# ─── 常量 ────────────────────────────────────────────────────────────────────

NUM_PREFIX_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]")
ANSWER_PAGE_MARKERS = ("参考答案", "答案及评分", "评分标准", "答案与解析")
# 答案 chunk 的强特征：题号开头 + 含 "(N 分)"——题目 stem 几乎不会有此模式。
# 用于无 "参考答案" 标题页的卷子（如 chaoyang，直接以 "16.(1)... (3分)" 开篇）。
ANSWER_CHUNK_RE = re.compile(r"^\s*\d{1,2}\s*[.、．].*\(\s*\d+\s*分\s*\)", re.DOTALL)
MAX_DIM = 3000              # API 入参图片最长边
MAX_BYTES = 9_000_000       # API 入参 < 10MB

# 北京物理一模题型固定结构：Q1-12 单选, Q13-15 多选, Q16-21 实验探究,
# Q22-23 实验探究 (含表), Q24 解答(科普阅读), Q25-26 计算
def _infer_type_en(num: int, options: list, group_type: str) -> str:
    if num <= 0:
        return "essay"
    if 1 <= num <= 12:
        return "choice"
    if 13 <= num <= 15:
        return "multi_choice"
    if num in (24,):
        return "essay"
    if num in (25, 26) or group_type == "arithmetic":
        return "calculation"
    # 16-23：实验探究（含填空、含表、含图）
    return "experiment"


# 北京物理一模题型分值默认表（与 ocr_paper 沿用一致；enrich 可被卷面满分覆盖）
def _default_score(num: int) -> int:
    if 1 <= num <= 12:  return 2
    if 13 <= num <= 15: return 2
    if num == 16:       return 3
    if 17 <= num <= 18: return 3
    if 19 <= num <= 21: return 4
    if num in (22, 23): return 4
    if num == 24:       return 4
    if num in (25, 26): return 4
    return 2


# ─── 腾讯云 API ─────────────────────────────────────────────────────────────

_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    sid = os.environ.get("TENCENT_OCR_SECRET_ID", "")
    skey = os.environ.get("TENCENT_OCR_SECRET_KEY", "")
    if not (sid and skey):
        sys.exit("缺 TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY")
    cred = credential.Credential(sid, skey)
    http_p = HttpProfile(); http_p.endpoint = "ocr.tencentcloudapi.com"
    _client = ocr_client.OcrClient(cred, "ap-guangzhou",
                                   ClientProfile(httpProfile=http_p))
    return _client


def _img_to_b64(path: Path) -> tuple[str, tuple[int, int], tuple[int, int]]:
    """返回 (b64, (orig_w, orig_h), (sent_w, sent_h))。"""
    img = Image.open(path); orig_w, orig_h = img.size
    if max(orig_w, orig_h) > MAX_DIM:
        r = MAX_DIM / max(orig_w, orig_h)
        img = img.resize((int(orig_w * r), int(orig_h * r)), Image.LANCZOS)
    img = img.convert("RGB")
    for q in (88, 75, 60):
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=q)
        if len(buf.getvalue()) <= MAX_BYTES:
            break
    return (base64.b64encode(buf.getvalue()).decode(),
            (orig_w, orig_h), img.size)


def _call_split(img_path: Path) -> dict:
    """调用 QuestionSplitOCR，返回 dict（含 _scale_x/y 用于坐标回原）。"""
    b64, (ow, oh), (sw, sh) = _img_to_b64(img_path)
    req = models.QuestionSplitOCRRequest(); req.ImageBase64 = b64
    resp = _get_client().QuestionSplitOCR(req)
    d = json.loads(resp.to_json_string())
    d["_orig_size"] = [ow, oh]
    d["_sent_size"] = [sw, sh]
    d["_scale"] = [ow / sw, oh / sh]
    return d


def _qwen_extract_choice_answers(img_path: Path) -> dict[int, str]:
    """用 qwen-vl-max 看图重读选择题答案表（兜底腾讯 OCR 列错位）。
    返回 {题号: 答案} 如 {1:"B", 13:"AC"}。
    """
    try:
        import openai
    except ImportError:
        return {}
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        return {}
    client = openai.OpenAI(api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    b = base64.b64encode(img_path.read_bytes()).decode("ascii")
    data_url = f"data:image/png;base64,{b}"
    prompt = ("看这页物理试卷答案页里的「选择题答案表」（题号-答案对应行）。\n"
              "只输出 JSON 对象 {\"题号\": \"答案\"}：\n"
              "- 单选题答案是单字母 A/B/C/D\n"
              "- 多选题答案是多字母组合 如 AC / BD / ABC\n"
              "- 题号是阿拉伯数字\n"
              "- 只要确定的、表格里清晰可见的题号-答案对，遇模糊宁可漏不要猜\n"
              "示例输出：{\"1\":\"B\",\"2\":\"C\",\"13\":\"AC\"}\n"
              "**只输出 JSON，无其他文字、无围栏。**")
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model="qwen-vl-max",
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt}]}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
            d = json.loads(raw)
            return {int(k): str(v).strip().upper() for k, v in d.items()
                    if str(k).isdigit() and v}
        except Exception as e:
            print(f"[qwen-vl] 兜底失败: {e}", flush=True)
    return {}


def _call_general_ocr(img_path: Path) -> str:
    """通用文字识别——用于答案页表格（QuestionSplitOCR 把表格 Text 留空）。"""
    b64, _, _ = _img_to_b64(img_path)
    req = models.GeneralAccurateOCRRequest(); req.ImageBase64 = b64
    resp = _get_client().GeneralAccurateOCR(req)
    d = json.loads(resp.to_json_string())
    return "\n".join(td.get("DetectedText", "")
                     for td in d.get("TextDetections", []))


def _api_cached(img_path: Path, cache_dir: Path, force: bool = False) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{img_path.stem}.json"
    if cf.exists() and not force:
        return json.loads(cf.read_text(encoding="utf-8"))
    d = _call_split(img_path)
    cf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


# ─── 几何 ────────────────────────────────────────────────────────────────────

def _bbox_xyxy(coord: dict, sx: float, sy: float) -> tuple[int, int, int, int]:
    """腾讯 4 点 Coord → (x1,y1,x2,y2)，应用缩放回原图。"""
    if isinstance(coord, list):
        coord = coord[0] if coord else {}
    xs = [coord[k]["X"] for k in ("LeftTop", "RightTop", "RightBottom", "LeftBottom")]
    ys = [coord[k]["Y"] for k in ("LeftTop", "RightTop", "RightBottom", "LeftBottom")]
    return (int(min(xs) * sx), int(min(ys) * sy),
            int(max(xs) * sx), int(max(ys) * sy))


def _outer_rect(bboxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    return (min(b[0] for b in bboxes), min(b[1] for b in bboxes),
            max(b[2] for b in bboxes), max(b[3] for b in bboxes))


# ─── 题号 / 答案页判断 ──────────────────────────────────────────────────────

def _peek_number(item: dict) -> int | None:
    """从 ResultList item 的 Question[0].Text 抽题号；无则 None。"""
    q = item.get("Question") or []
    if not q:
        return None
    m = NUM_PREFIX_RE.match(q[0].get("Text", ""))
    return int(m.group(1)) if m else None


def _is_answer_marker(text: str) -> bool:
    if not text:
        return False
    if any(m in text for m in ANSWER_PAGE_MARKERS):
        return True
    # 答案 chunk 模式（chaoyang 这类无 "参考答案" 标题页的卷子）
    return bool(ANSWER_CHUNK_RE.match(text))


# ─── 题号缺口 fallback：通用 OCR + 题号切分 ─────────────────────────────────

def _split_by_qnum(text: str) -> list[dict]:
    """从纯文本里按 ^N. 锚点切题块，返回 [{number, stem, options}]。

    用于 QuestionSplitOCR 在某些页面（如带"考生须知"的首页）漏切的兜底：
    GeneralAccurateOCR 的逐行文本里题号清晰可寻，但无 bbox 信息——
    所以这条路径只用于纯文本题（含图选项的题需要别的兜底）。
    """
    questions: list[dict] = []
    cur: dict | None = None
    SECTION_RE = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、，]")
    OPT_RE = re.compile(r"^\s*([A-D])\s*[.、．]\s*(.*)$")
    NOTICE_RE = re.compile(r"^[1-9]\.(本试卷|在试卷|试题答案|在答题|考试结束)")

    def _flush():
        if cur and cur.get("number", 0) > 0:
            cur["stem"] = cur["stem"].strip()
            questions.append({k: v for k, v in cur.items()})

    for ln in text.splitlines():
        ln = ln.rstrip()
        if not ln: continue
        if SECTION_RE.match(ln): continue
        if NOTICE_RE.match(ln): continue        # 跳过 "1.本试卷..." 须知
        m = NUM_PREFIX_RE.match(ln)
        # 题号锚点：行首 N. 且不是须知/选项续行
        if m and 1 <= int(m.group(1)) <= 30 and not OPT_RE.match(ln):
            _flush()
            cur = {"number": int(m.group(1)),
                   "stem": NUM_PREFIX_RE.sub("", ln, count=1).strip(),
                   "options": {}}
            continue
        if cur is None: continue
        om = OPT_RE.match(ln)
        if om:
            cur["options"][om.group(1)] = om.group(2).strip()
        else:
            cur["stem"] += "\n" + ln
    _flush()
    return questions


def _fill_gaps_via_general_ocr(api_results: dict[str, dict],
                                cache_dir: Path,
                                images_dir: Path,
                                got_numbers: list[int],
                                force: bool = False) -> list[dict]:
    """检测题号缺口；用 GeneralAccurateOCR 对应页补抽。

    返回补齐的 question dict 列表（无 bbox，type_en 用默认推断；figures 留空）。
    适配 chaoyang 这类"页 1 被考生须知干扰致 QuestionSplitOCR 只切出 1 块"的卷。
    """
    if not got_numbers:
        return []
    expected = set(range(1, max(got_numbers) + 1))
    missing = sorted(expected - set(got_numbers))
    if not missing:
        return []
    print(f"[tencent_paper] 题号缺口 {missing}，用通用 OCR 补抽", flush=True)

    # 猜哪页含 missing：腾讯每页第一个有题号的块的 page 是已知 anchor
    # missing 比"页 P 的最小题号"小 → 应在 page < P 的某页
    page_first_num: dict[int, int] = {}
    for page_name in sorted(api_results):
        page_num = int(re.search(r"page-(\d+)", page_name).group(1))
        for item in (api_results[page_name].get("QuestionInfo") or [{}])[0]\
                       .get("ResultList", []):
            n = _peek_number(item)
            if n:
                page_first_num.setdefault(page_num, n)
                break

    # 缺失页 = 第一个 page_first_num > min(missing) 的 page 的前一页（或 page-01）
    suspect_pages: set[int] = set()
    for mn in missing:
        candidate = 1
        for pg in sorted(page_first_num):
            if page_first_num[pg] > mn:
                candidate = pg - 1 if pg > 1 else 1
                break
            candidate = pg
        suspect_pages.add(candidate)

    general_cache = cache_dir / "general"
    general_cache.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for pg in sorted(suspect_pages):
        page_name = f"page-{pg:02d}.png"
        gf = general_cache / f"page-{pg:02d}.txt"
        if gf.exists() and not force:
            txt = gf.read_text(encoding="utf-8")
        else:
            txt = _call_general_ocr(images_dir / page_name)
            gf.write_text(txt, encoding="utf-8")
        for q in _split_by_qnum(txt):
            n = q["number"]
            if n in missing:
                type_en = _infer_type_en(n, q.get("options"), "")
                opts = q["options"] or {}
                # 选择题无文本选项 → 必为图选项（A./B./C./D. 文本本来就在图里）
                has_img_opts = (type_en in ("choice", "multi_choice")
                                 and not opts)
                out.append({
                    "number": n,
                    "type": type_en,
                    "score": _default_score(n),
                    "stem": q["stem"],
                    "options": opts or None,
                    "has_image_options": has_img_opts,
                    "source_page": pg,
                    "figure_path": None,
                })
    return out


# ─── 主流程：组装 questions ─────────────────────────────────────────────────

def _normalize_stem(text: str) -> str:
    """去前导题号 + trim。"""
    return NUM_PREFIX_RE.sub("", text or "", count=1).strip()


def _parse_option_text(text: str) -> tuple[str, str]:
    """'A.木制小碗' → ('A', '木制小碗')；无效则 ('', text)。"""
    m = re.match(r"^\s*([A-D])\s*[.、．]\s*(.*)$", text or "")
    if m:
        return m.group(1), m.group(2).strip()
    return "", (text or "").strip()


def _build_question(item: dict, scale: tuple[float, float],
                    source_page: int) -> dict:
    sx, sy = scale
    q_arr = item.get("Question") or []
    stem_text = q_arr[0].get("Text", "") if q_arr else ""
    num = _peek_number(item) or 0
    group_type = q_arr[0].get("GroupType", "") if q_arr else ""

    # 选项
    options: dict[str, str] = {}
    for opt in item.get("Option") or []:
        label, text = _parse_option_text(opt.get("Text", ""))
        if label:
            options[label] = text

    # Figures: 每个图的 bbox（保留原始坐标，裁切时再合并）
    fig_bboxes = [_bbox_xyxy(f.get("Coord", {}), sx, sy)
                  for f in (item.get("Figure") or [])
                  if f.get("Coord")]
    table_bboxes = [_bbox_xyxy(t.get("Coord", {}), sx, sy)
                    for t in (item.get("Table") or [])
                    if t.get("Coord")]

    type_en = _infer_type_en(num, options, group_type)
    # 图选项题判定：选择题 + ≥3 图 + (options 空 OR options 数==figs 数)
    # 空 options（如 Q8 纯图选项）和等数（如 Q1 图+文字标签）都算
    has_img_opts = (
        type_en in ("choice", "multi_choice")
        and len(fig_bboxes) >= 3
        and (not options or len(options) == len(fig_bboxes))
    )

    return {
        "number": num,
        "type": type_en,
        "score": _default_score(num),
        "stem": _normalize_stem(stem_text),
        "_stem_raw": stem_text,                       # 用于跨页合并日志
        "options": options if options else None,
        "has_image_options": has_img_opts,
        "source_page": source_page,
        "_group_type": group_type,
        "_fig_bboxes": fig_bboxes,                    # 暂存，裁图阶段消费
        "_table_bboxes": table_bboxes,
        "_outer_coord": _bbox_xyxy(item.get("Coord", {}), sx, sy)
                        if item.get("Coord") else None,
    }


def _merge_into(prev: dict, cur: dict) -> None:
    """把无题号续块合并到上一有号块。"""
    if cur.get("stem"):
        if prev["stem"]:
            prev["stem"] += "\n" + cur["stem"]
        else:
            prev["stem"] = cur["stem"]
    if cur.get("options"):
        if not prev.get("options"):
            prev["options"] = {}
        for k, v in cur["options"].items():
            prev["options"].setdefault(k, v)
        if not prev.get("has_image_options") and cur.get("has_image_options"):
            prev["has_image_options"] = True
    prev["_fig_bboxes"].extend(cur.get("_fig_bboxes") or [])
    prev["_table_bboxes"].extend(cur.get("_table_bboxes") or [])


def _parse_choice_answers_from_text(text: str) -> dict[int, str]:
    """从 GeneralAccurateOCR 的纯文本里提取选择题答案。

    答案页典型版式（每行一项，腾讯逐行输出）：
      题号 \n 1 \n 2 \n ... \n 12 \n 答案 \n B \n C \n D \n ...
    用「'题号' 段→数字列表」对齐「'答案' 段→字母列表」。
    支持多组（单选/多选两块表格）。
    """
    out: dict[int, str] = {}
    lines = [ln.strip() for ln in text.splitlines()]
    i = 0
    while i < len(lines):
        if lines[i] == "题号":
            nums: list[int] = []
            j = i + 1
            while j < len(lines) and re.fullmatch(r"\d{1,2}", lines[j]):
                nums.append(int(lines[j])); j += 1
            if j < len(lines) and lines[j] == "答案":
                k = j + 1
                ans: list[str] = []
                while k < len(lines) and re.fullmatch(r"[A-D]+", lines[k]):
                    ans.append(lines[k]); k += 1
                # 长度不齐时一律放弃（错位风险高于"漏一个"风险）；
                # 由上层走 Qwen-VL 兜底再读一次答案表
                if len(nums) == len(ans) and nums == sorted(set(nums)):
                    for n, a in zip(nums, ans):
                        out[n] = a
                else:
                    print(f"[answer-table] 题号/答案列长度不齐 "
                          f"nums={nums} ans={ans} → 放弃，由上层兜底", flush=True)
                i = k; continue
        i += 1
    return out


def _parse_solutions_from_text(text: str) -> dict[int, str]:
    """从答案页纯文本里按题号 ^N. 锚点切块，返回 {N: solution}。

    答案页布局（GeneralAccurateOCR 输出）：
      "...\n三、实验探究题\n16.(1)右(1分)\n(2)162(1分)\n...\n17.(2)同一平面内...\n..."
    用「题号锚点 ^N.」切分；段落标题（"三、实验探究题"等）当噪声丢弃。
    """
    SECTION_RE = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、，].*")
    PAGE_FOOTER_RE = re.compile(r"第\s*\d+\s*页/共")
    out: dict[int, str] = {}
    cur_num: int | None = None
    buf: list[str] = []

    def _flush():
        if cur_num is not None and buf:
            out[cur_num] = "\n".join(buf).strip()

    for ln in text.splitlines():
        ln = ln.rstrip()
        if not ln: continue
        if SECTION_RE.match(ln) or PAGE_FOOTER_RE.search(ln): continue
        m = re.match(r"^\s*(\d{1,2})\s*[.、．]\s*(.*)$", ln)
        if m and 1 <= int(m.group(1)) <= 30:
            _flush()
            cur_num = int(m.group(1))
            buf = [m.group(2).rstrip()] if m.group(2).strip() else []
        else:
            if cur_num is not None:
                buf.append(ln)
    _flush()
    return out


def _parse_answer_page(items: list[dict], general_text: str = "") -> list[dict]:
    """答案页 → answers[{number, correct, solution}]。

    主源是 GeneralAccurateOCR 的整页文本（含选择题表格 + 主观题解答）；
    QuestionSplitOCR 的 ResultList 仅作 fallback（已被验证不如通用 OCR 完整）。
    """
    answers_by_num: dict[int, dict] = {}

    # 选择题答案表格
    if general_text:
        for n, a in _parse_choice_answers_from_text(general_text).items():
            answers_by_num.setdefault(n, {"number": n, "correct": "",
                                          "solution": ""})["correct"] = a
        # 主观题 solution（同一份文本切块）
        for n, s in _parse_solutions_from_text(general_text).items():
            entry = answers_by_num.setdefault(n, {"number": n, "correct": "",
                                                  "solution": ""})
            # 若选择题 correct 已有，保留；solution 取通用 OCR 切块
            if not entry["solution"]:
                entry["solution"] = s

    # Fallback：QuestionSplitOCR 的主观题块（覆盖更广的边角 case）
    full_text = "\n".join((it.get("Question") or [{}])[0].get("Text", "")
                          for it in items)
    for n, s in _parse_solutions_from_text(full_text).items():
        entry = answers_by_num.setdefault(n, {"number": n, "correct": "",
                                              "solution": ""})
        if not entry["solution"]:
            entry["solution"] = s

    return [answers_by_num[n] for n in sorted(answers_by_num)]


def _assemble(api_per_page: dict[str, dict],
              answer_pages_text: dict[str, str] | None = None
              ) -> tuple[list[dict], list[dict], int, set[str]]:
    """聚合多页 API 结果 → (questions, answers, num_pages, answer_pages_set)。"""
    questions: list[dict] = []
    answer_items: list[dict] = []
    in_answer = False
    answer_pages: set[str] = set()

    for page_name in sorted(api_per_page):
        d = api_per_page[page_name]
        page_num = int(re.search(r"page-(\d+)", page_name).group(1))
        scale = tuple(d.get("_scale", [1.0, 1.0]))
        rl = (d.get("QuestionInfo") or [{}])[0].get("ResultList", [])

        page_is_answer = in_answer
        for item in rl:
            q_text = ((item.get("Question") or [{}])[0]).get("Text", "")
            if not in_answer and _is_answer_marker(q_text):
                in_answer = True
                page_is_answer = True
            if in_answer:
                answer_items.append(item)
                continue
            qd = _build_question(item, scale, page_num)
            if qd["number"] > 0:
                questions.append(qd)
            elif questions:
                _merge_into(questions[-1], qd)
        if page_is_answer:
            answer_pages.add(page_name)

    # 答案页通用 OCR 文本（外部传入，包含整页选择题表格）
    general_text = "\n".join((answer_pages_text or {}).get(p, "")
                              for p in sorted(answer_pages))
    answers = _parse_answer_page(answer_items, general_text) if answer_items else []
    return questions, answers, len(api_per_page), answer_pages


# ─── 裁图 ────────────────────────────────────────────────────────────────────

PADDING_PX = 10  # 外扩留白

def _crop_figures(src_images_dir: Path, questions: list[dict],
                  out_figures: Path) -> dict[int, str]:
    """每题 Figure+Table bbox 外接矩形 → figures/qNN.png；
    多页 figures 合并到首页那张（按面积比简单选）。
    返回 {number: 'figures/qNN.png'}。
    """
    out_figures.mkdir(parents=True, exist_ok=True)
    page_imgs: dict[int, Path] = {}
    for p in src_images_dir.glob("page-*.png"):
        m = re.search(r"page-(\d+)", p.name)
        if m:
            page_imgs[int(m.group(1))] = p
    figure_paths: dict[int, str] = {}
    for q in questions:
        bboxes = (q.get("_fig_bboxes") or []) + (q.get("_table_bboxes") or [])
        if not bboxes:
            continue
        page = q.get("source_page")
        img_path = page_imgs.get(page)
        if not img_path:
            continue
        x1, y1, x2, y2 = _outer_rect(bboxes)
        img = Image.open(img_path); W, H = img.size
        x1 = max(0, x1 - PADDING_PX); y1 = max(0, y1 - PADDING_PX)
        x2 = min(W, x2 + PADDING_PX); y2 = min(H, y2 + PADDING_PX)
        if x2 <= x1 or y2 <= y1:
            continue
        out = out_figures / f"q{q['number']:02d}.png"
        img.crop((x1, y1, x2, y2)).save(out)
        figure_paths[q["number"]] = f"figures/q{q['number']:02d}.png"
    return figure_paths


# ─── 元数据 ─────────────────────────────────────────────────────────────────

_TYPE_CN = {"yimo": "一模", "ermo": "二模", "sanmo": "三模", "zhenti": "真题"}

def _parse_exam_meta(src: Path) -> dict:
    """从源路径推 exam 名称（与 enrich_to_mock_exam 的 _parse_exam_name 匹配）。

    src = .../knowledge-original/beijing-mock-2026/yimo/mentougou/physics
    → exam = "2026 北京门头沟区初三一模 物理"
    """
    subject_en = src.name
    region = src.parent.name
    type_dir = src.parent.parent.name
    set_dir = src.parent.parent.parent.name
    m = re.search(r"(\d{4})", set_dir)
    year = m.group(1) if m else ""
    type_cn = _TYPE_CN.get(type_dir, type_dir)
    region_cn = region  # enrich 会加"区"后缀
    subj_cn = {"physics": "物理", "chemistry": "化学", "math": "数学",
               "biology": "生物", "english": "英语", "chinese": "语文",
               "history": "历史", "politics": "道法", "geography": "地理"}.get(
                   subject_en, subject_en)
    return {
        "subject": subject_en,
        "exam": f"{year} 北京{region_cn}区初三{type_cn} {subj_cn}",
    }


# ─── 入口 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", type=Path)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--force", action="store_true", help="清 API 缓存重跑")
    ap.add_argument("--no-crop", action="store_true")
    a = ap.parse_args()

    src = a.src_dir.resolve()
    images_dir = src / "images"
    if not images_dir.is_dir():
        sys.exit(f"无 images/：{src}")
    out_dir = derive_out_dir(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "tencent-cache"
    figures_dir = out_dir / "figures"

    pages = sorted(images_dir.glob("page-*.png"))
    if not pages:
        sys.exit(f"无 page-*.png：{images_dir}")
    print(f"[tencent_paper] {len(pages)} 页 → {out_dir}", flush=True)

    # 1) 每页调 API（带缓存）
    api_results: dict[str, dict] = {}
    t0 = time.time()
    for p in pages:
        api_results[p.name] = _api_cached(p, cache_dir, force=a.force)
        rl_n = len((api_results[p.name].get("QuestionInfo") or [{}])[0]
                   .get("ResultList", []))
        print(f"  {p.name}: {rl_n} 块", flush=True)
    print(f"[tencent_paper] API 总耗时 {time.time()-t0:.1f}s", flush=True)

    # 2) 第一遍组装识别答案页
    _, _, _, answer_pages = _assemble(api_results)

    # 3) 对答案页用 GeneralAccurateOCR 拿表格文本（带缓存）
    general_cache = cache_dir / "general"
    general_cache.mkdir(parents=True, exist_ok=True)
    answer_text: dict[str, str] = {}
    for ap in sorted(answer_pages):
        gf = general_cache / f"{ap.replace('.png','')}.txt"
        if gf.exists() and not a.force:
            answer_text[ap] = gf.read_text(encoding="utf-8")
        else:
            txt = _call_general_ocr(images_dir / ap)
            gf.write_text(txt, encoding="utf-8")
            answer_text[ap] = txt
        print(f"  [answer] {ap}: GeneralOCR {len(answer_text[ap])} chars", flush=True)

    # 4) 第二遍：用答案页文本提取选择题答案
    questions, answers, n_pages, _ = _assemble(api_results, answer_text)

    # 4a-1) 选择题答案缺口 → qwen-vl-max 兜底读答案表（带缓存）
    expected_choice_nums = set(range(1, 16))  # 北京物理 Q1-15 是选择题
    answers_by_num = {a["number"]: a for a in answers}
    got_correct = {n for n, a in answers_by_num.items() if a["correct"]}
    missing_correct = sorted(expected_choice_nums - got_correct)
    if missing_correct and answer_pages:
        qcache = cache_dir / "qwen-vl-answers.json"
        if qcache.exists() and not a.force:
            qd = json.loads(qcache.read_text(encoding="utf-8"))
        else:
            qd = {}
            for ap in sorted(answer_pages):
                got = _qwen_extract_choice_answers(images_dir / ap)
                if got:
                    qd.update({str(k): v for k, v in got.items()})
                    break  # 通常答案表都在第一答案页
            qcache.write_text(json.dumps(qd, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        for k, v in qd.items():
            n = int(k)
            entry = answers_by_num.setdefault(n, {"number": n, "correct": "",
                                                   "solution": ""})
            if not entry["correct"]:
                entry["correct"] = v
        answers = sorted(answers_by_num.values(), key=lambda x: x["number"])
        print(f"[tencent_paper] qwen-vl 兜底补 {len(qd)} 个选择题答案，"
              f"correct 总数 {sum(1 for a in answers if a['correct'])}",
              flush=True)

    # 4b) 题号缺口 fallback：通用 OCR 补抽（如 chaoyang page-01 漏切）
    got = [q["number"] for q in questions if q.get("number", 0) > 0]
    fb = _fill_gaps_via_general_ocr(api_results, cache_dir, images_dir,
                                     got, force=a.force)
    if fb:
        existing = {q["number"] for q in questions}
        for q in fb:
            if q["number"] not in existing:
                # 兼容内部字段（裁图需要这些 _ 字段）
                q.setdefault("_fig_bboxes", [])
                q.setdefault("_table_bboxes", [])
                q.setdefault("_outer_coord", None)
                q.setdefault("_group_type", "")
                q.setdefault("_stem_raw", q["stem"])
                questions.append(q)
        questions.sort(key=lambda x: x["number"])
        print(f"[tencent_paper] fallback 补抽 {len(fb)} 题 → 总 {len(questions)} 题",
              flush=True)
    print(f"[tencent_paper] 解析出 {len(questions)} 题 / {len(answers)} 答案 "
          f"(其中 correct 非空 {sum(1 for a in answers if a['correct'])})",
          flush=True)

    # 5) 裁图
    if not a.no_crop:
        # 清旧
        if figures_dir.is_dir():
            for f in figures_dir.glob("q*.png"):
                f.unlink()
        figure_paths = _crop_figures(images_dir, questions, figures_dir)
        for q in questions:
            fp = figure_paths.get(q["number"])
            if fp:
                q["figure_path"] = fp
        print(f"[tencent_paper] 裁切 {len(figure_paths)} 张 figures", flush=True)

    # 6) 输出 final.json（剥离内部 _ 字段）
    meta = _parse_exam_meta(src)
    out_questions = []
    for q in questions:
        item = {k: v for k, v in q.items() if not k.startswith("_")}
        item["id"] = f"{a.subject}-q{q['number']:02d}"
        out_questions.append(item)

    final = {
        "subject": meta["subject"],
        "exam": meta["exam"],
        "page_count": n_pages,
        "questions": out_questions,
        "answers": answers,
    }
    out_struct = out_dir / "structured-cloud"
    out_struct.mkdir(parents=True, exist_ok=True)
    fj = out_struct / "final.json"
    fj.write_text(json.dumps(final, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    print(f"[tencent_paper] ✅ {fj}", flush=True)
    print(f"   题号={[q['number'] for q in out_questions]}", flush=True)


if __name__ == "__main__":
    main()
