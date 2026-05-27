#!/usr/bin/env python3
"""physics_image_paper — 用腾讯云 QuestionSplitOCR 单 API 替换整套 OCR+layout+图分配。

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
    python3 scripts/exam-ocr/physics_image_paper.py \\
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
import subprocess
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
# 注：曾试过 "题号+(N分)" 模式判定答案 chunk，但题目 stem 也常有 (2分) 标分值
# （如 shijingshan Q16: "16.(1)如图甲...(2分)"），会误判整页为答案页。
# 改靠 (1) 标准 marker + (2) 题号倒退（_assemble 中 min(nums) < max_seen - 3）。
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


# 北京物理一模分值默认表（兜底；后续从答案页"题各N分" hint 动态覆盖）
def _default_score(num: int) -> int:
    if 1 <= num <= 12:  return 2
    if 13 <= num <= 15: return 2
    if num in (16, 18, 22, 23): return 3
    if num in (17, 19, 20, 21): return 4
    if num == 24:       return 4
    if num in (25, 26): return 4
    return 2


def _parse_score_rules_from_text(text: str) -> dict[int, int]:
    """从答案页文本里解析「16、18、22、23题各3分」式样的分值规则。
    返回 {题号: 分值}。
    """
    rules: dict[int, int] = {}
    # 模式 1：(共N分，A、B、C题各X分，D、E题各Y分)
    for m in re.finditer(r"([0-9、，,\s]+)题各\s*(\d+)\s*分", text):
        nums_str = m.group(1).replace(",", "、").replace("，", "、")
        for n_str in re.findall(r"\d+", nums_str):
            try:
                rules[int(n_str)] = int(m.group(2))
            except ValueError:
                pass
    # 模式 2：「16.(1)..." 单题分值合计——逐题 "(N分)" 求和
    # 暂不实现（模式 1 已覆盖大多北京物理卷）
    return rules


def _parse_full_score_from_text(text: str) -> int | None:
    """从卷首文本里解析「满分N分」字样。"""
    m = re.search(r"满分\s*[为是]?\s*(\d+)\s*分", text)
    return int(m.group(1)) if m else None


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


def _crop_to_b64(img_path: Path, bbox: tuple) -> str:
    """裁切 bbox 区域 → JPEG → base64（用于按区域调 OCR）。"""
    pad = 8
    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    x1 = max(0, bbox[0] - pad); y1 = max(0, bbox[1] - pad)
    x2 = min(W, bbox[2] + pad); y2 = min(H, bbox[3] + pad)
    crop = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO(); crop.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _table_cells_to_markdown(cells: list[dict]) -> str:
    """把腾讯 RecognizeTableAccurateOCR 的 Cells[] 转成 markdown 表格。
    Cells 每项有 RowTl/RowBr/ColTl/ColBr/Text；按行 col 排列成二维矩阵。
    """
    if not cells:
        return ""
    n_rows = max(c.get("RowBr", c.get("RowTl", 0)) for c in cells) + 1
    n_cols = max(c.get("ColBr", c.get("ColTl", 0)) for c in cells) + 1
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for c in cells:
        rt = c.get("RowTl", 0); ct = c.get("ColTl", 0)
        t = (c.get("Text") or "").strip().replace("|", "丨").replace("\n", " ")
        if 0 <= rt < n_rows and 0 <= ct < n_cols:
            grid[rt][ct] = t
    md = []
    md.append("| " + " | ".join(grid[0]) + " |")
    md.append("|" + "|".join(["---"] * n_cols) + "|")
    for row in grid[1:]:
        md.append("| " + " | ".join(row) + " |")
    return "\n".join(md)


def _call_table_ocr(img_path: Path, bbox: tuple) -> str:
    """对原页 bbox 区域调 RecognizeTableAccurateOCR → 返回 markdown 表格字符串。
    失败返回空字符串。
    """
    try:
        b64 = _crop_to_b64(img_path, bbox)
        req = models.RecognizeTableAccurateOCRRequest()
        req.ImageBase64 = b64
        resp = _get_client().RecognizeTableAccurateOCR(req)
        d = json.loads(resp.to_json_string())
        out = []
        for tb in d.get("TableDetections", []):
            cells = tb.get("Cells", [])
            md = _table_cells_to_markdown(cells)
            if md:
                out.append(md)
        return "\n\n".join(out)
    except Exception as e:
        print(f"[table-ocr] {img_path.name} bbox={bbox} 失败: {e}", flush=True)
        return ""


def _refill_table_data(questions: list[dict], cache_dir: Path,
                        images_dir: Path, force: bool = False) -> int:
    """对含 table 的题，把表格内容 OCR 成 markdown 追加到 stem 末尾。
    带缓存：tencent-cache/tables/q<NN>_<idx>.md。
    """
    table_cache = cache_dir / "tables"
    table_cache.mkdir(parents=True, exist_ok=True)
    fixed = 0
    for q in questions:
        tables = [f for f in (q.get("_figs") or []) if f.get("kind") == "table"]
        if not tables:
            continue
        # 已经含表数据的不重复（stem 末尾已有 markdown 表头识别）
        if re.search(r"\|\s*-+\s*\|", q.get("stem", "") or ""):
            continue
        mds = []
        for i, t in enumerate(tables):
            pg = t["page"]
            cf = table_cache / f"q{q['number']:02d}_{i}.md"
            if cf.exists() and not force:
                md = cf.read_text(encoding="utf-8")
            else:
                md = _call_table_ocr(images_dir / f"page-{pg:02d}.png", t["bbox"])
                cf.write_text(md, encoding="utf-8")
            if md:
                mds.append(md)
        if mds:
            q["stem"] = (q.get("stem", "") or "").rstrip() + "\n\n" + "\n\n".join(mds)
            fixed += 1
            print(f"  [refill-table] Q{q['number']}: 追加 {len(mds)} 个表格",
                  flush=True)
    return fixed


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
    """仅按显式标题标识；题号倒退判定在 _assemble 里独立处理。"""
    if not text:
        return False
    return any(m in text for m in ANSWER_PAGE_MARKERS)


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


def _iou(a: tuple, b: tuple) -> float:
    """两个 (x1,y1,x2,y2) bbox 的 IoU。"""
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    ua = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / ua if ua > 0 else 0.0


def _paddle_python(src: Path) -> Path | None:
    """从 src（原始卷目录）向上找 .venv-paddle/bin/python3。"""
    cur = src.resolve()
    while cur.parent != cur:
        cand = cur / ".venv-paddle" / "bin" / "python3"
        if cand.exists():
            return cand
        cur = cur.parent
    return None


def _paddle_layout(img_path: Path, cache_dir: Path, src: Path,
                    force: bool = False) -> list[dict]:
    """对一张页面取 paddle layout 检测结果（带 layout-cache 缓存 + .venv-paddle 子进程）。

    返回 [{label, bbox: [x1,y1,x2,y2], score}, ...]；paddle 不可用或失败时返 []。
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{img_path.stem}.layout.json"
    if cf.exists() and not force:
        return json.loads(cf.read_text(encoding="utf-8"))
    py = _paddle_python(src)
    if not py:
        return []
    script = Path(__file__).resolve().parent / "paddle_layout.py"
    try:
        r = subprocess.run([str(py), str(script), str(img_path)],
                          capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"[paddle] {img_path.name} 失败: {r.stderr.strip()[-200:]}",
                  flush=True)
            return []
        boxes = json.loads(r.stdout.strip().splitlines()[-1])
        cf.write_text(json.dumps(boxes, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        return boxes
    except Exception as e:
        print(f"[paddle] {img_path.name} 异常: {e}", flush=True)
        return []


def _fallback_missing_figures(questions: list[dict], images_dir: Path,
                               layout_cache_dir: Path, src: Path) -> int:
    """对 stem 引用「图N/图N甲」但 _figs 为空的题，从 paddle 检测的
    image/table/chart bbox 里补图。补的 fig 带 page 标记。
    """
    if not _paddle_python(src):
        print("[fallback-fig] 无 .venv-paddle，跳过", flush=True)
        return 0
    fixed = 0
    # 每页已占用 bbox（含腾讯检测 + 之前 fallback 已补的）
    occupied: dict[int, list[tuple]] = {}
    for q in questions:
        for fig in q.get("_figs") or []:
            occupied.setdefault(fig["page"], []).append(fig["bbox"])

    fig_ref_re = re.compile(r"(?:如图|图)\s*(\d+)\s*([甲乙丙丁戊])?")
    for q in questions:
        stem = q.get("stem") or ""
        if not fig_ref_re.search(stem):
            continue
        # 按"引图数 vs 实有 image 数"判定（table 单独不算"图"，避免 Q14 这种
        # 有表无图却跳过 fallback 的情况）
        refs = {(m.group(1) + (m.group(2) or ""))
                for m in fig_ref_re.finditer(stem)}
        img_have = sum(1 for f in q.get("_figs") or [] if f.get("kind") == "image")
        if img_have >= len(refs):
            continue
        pg = q.get("source_page")
        if not pg: continue
        boxes = _paddle_layout(images_dir / f"page-{pg:02d}.png",
                                layout_cache_dir, src)
        if not boxes:
            continue
        # 触发条件是缺 image（不缺 table），所以候选只取 image/chart（不补 table）
        cands = [tuple(int(x) for x in b["bbox"]) for b in boxes
                 if b["label"] in ("image", "chart")]
        cands = [c for c in cands
                 if not any(_iou(c, o) > 0.3 for o in occupied.get(pg, []))]
        if not cands:
            continue
        outer = q.get("_outer_coord")
        if outer:
            ox1, oy1, ox2, oy2 = outer
            in_q = [c for c in cands if oy1 <= (c[1]+c[3])/2 <= oy2]
            if in_q:
                cands = in_q
        for c in cands:
            q.setdefault("_figs", []).append(
                {"page": pg, "bbox": c, "kind": "image"})
            occupied.setdefault(pg, []).append(c)
        fixed += 1
        print(f"  [fallback-fig] Q{q['number']}: p{pg:02d} 补 {len(cands)} 张",
              flush=True)
    return fixed


def _redistribute_figures_by_stem_refs(questions: list[dict]) -> int:
    """根据 stem 引用"图N/图N甲"的数量 vs 实际 figs 数，做全局图重分配。

    核心场景：Q4 跨页（stem 在 p1 底，图被腾讯归到 p2 顶部的 Q5）→
    Q5 figs 过量、Q4 figs 不足 → 把 Q5 的"y 最靠上的"那张转给 Q4。

    算法：
      1. 计算每题 need = len(stem refs 集合), have = len(figs)
      2. 找 over (have > need) 与 under (have < need) 的题
      3. 相邻题（题号 ±1）配对：
         - prev under + curr over → curr 的 y 最靠上 fig 转 prev（跨页倒灌）
         - curr over + next under → curr 的 y 最靠下 fig 转 next（同页溢出）
      4. 多轮迭代直到无可转移
    """
    STEM_REF = re.compile(r"(?:如图|图)\s*(\d+)\s*([甲乙丙丁戊])?")

    def _info(q):
        refs = {(m.group(1) + (m.group(2) or ""))
                for m in STEM_REF.finditer(q.get("stem") or "")}
        figs = q.get("_figs") or []
        # 图选项题（如 Q1/Q2/Q3 图选项 4 张）需求 = 选项数（即图本身就是选项）；
        # 否则需求 = stem 引用图号数。若两者皆有取 max。
        need = len(refs)
        if q.get("has_image_options"):
            n_opts = len(q.get("options") or {}) or 4
            need = max(need, n_opts)
        return need, len(figs)

    total_moved = 0
    for _ in range(5):  # 最多 5 轮（防意外循环）
        moved_this_round = 0
        for i, q in enumerate(questions):
            need, have = _info(q)
            if have <= need:
                continue
            # 优先尝试转给前一题（跨页倒灌：Q5 figs[0] 实际是 Q4 的）
            for j in (i - 1, i + 1):
                if not (0 <= j < len(questions)):
                    continue
                n_need, n_have = _info(questions[j])
                if n_have >= n_need:
                    continue
                k = min(have - need, n_need - n_have)
                if k <= 0:
                    continue
                figs = q["_figs"]
                figs.sort(key=lambda f: f["bbox"][1])
                if j == i - 1:
                    moved = figs[:k]; q["_figs"] = figs[k:]
                else:
                    moved = figs[-k:]; q["_figs"] = figs[:-k]
                questions[j].setdefault("_figs", []).extend(moved)
                moved_this_round += k
                total_moved += k
                pages_from = sorted({f["page"] for f in moved})
                print(f"  [redistribute] Q{questions[i]['number']} → "
                      f"Q{questions[j]['number']}: {k} 张 "
                      f"(from p{pages_from})", flush=True)
                have -= k
                if have <= need: break
        if moved_this_round == 0:
            break
    return total_moved


_SUBQ_RE = re.compile(r"\(\s*[1-9]\s*\)")
_PAGE_FOOTER_NOISE = re.compile(
    r"(?m)^\s*(?:"
    r"[一二三四五六七八九十]+\s*[、，][^\n]{0,40}"     # 大题标题"三、实验探究题..."
    r"|[^\n]{0,30}第\s*\d+\s*页[^\n]*"                # 各种 "...第N页..." 行
    r"|第\s*\d+\s*页\s*/?\s*共?\s*\d*\s*页?"
    r"|九年级[^\n]*"                                  # 九年级开头的版心信息
    r")\s*$\n?"
)


_PUNCT_END = set("。，；：！？.,;:!?)）")


# 下一行起始可能是填空续行的特征：单位（g/kg/cm/N/Pa/W/V/A...）、纯数字、
# 字母变量、英文括号注释（选填"左"或"右"）等——**不是中文字开头**
_FILL_NEXT_HEAD_RE = re.compile(
    r"^\s*(?:[(（][^\n]{0,30}[)）]"      # (选填"左"或"右")
    r"|[a-zA-Z0-9]"                       # g; cm 0.5 P=
    r"|kg|cm|mm|m/s|N\b|Pa|J\b|°[CF])"  # 常见单位
)


def _join_oversplit_lines(text: str) -> str:
    """合并 OCR 把"行内填空空白"误切成换行的情况。

    场景：试卷里"...苹果的质量是 _____ g;" 一行，OCR 因填空空白把
    "g;" 切到了下一行。视觉两行但语义同行。

    判定（同时满足）：
      - 上行末尾非中文标点结尾
      - 下行非子小题/选项开头、长度 < 40
      - 下行起始为单位/数字/字母/(选填...)——**非中文字开头**
        （避免"轻\n压"这种纯中文换行被误合）
    """
    out = []
    for ln in text.split("\n"):
        s = ln.rstrip()
        if not s:
            out.append(ln); continue
        prev_tail = out[-1].rstrip() if out else ""
        # 上行结尾是"图"/"如图" 时下行通常是图编号（图17乙），不应误合
        is_fig_ref_split = bool(re.search(r"(?:如?图)\s*$", prev_tail))
        if (out and prev_tail
                and prev_tail[-1] not in _PUNCT_END
                and not is_fig_ref_split
                and not re.match(r"^\s*\(\s*[1-9]\s*\)", s)
                and not re.match(r"^\s*[A-D]\s*[.、．]", s)
                and not _SUBQ_RE.match(s)
                and _FILL_NEXT_HEAD_RE.match(s)
                and len(s) < 40):
            out[-1] = out[-1].rstrip() + "____" + s.lstrip()
        else:
            out.append(ln)
    return "\n".join(out)


def _slice_general_text(full_text: str, num: int, next_num: int,
                          nxt_heads: list[str] | None = None) -> str:
    """通用 OCR 文本按 `^N.` 锚点切出第 num 题段（直到 `^next_num.` 或文末）。

    流程（顺序敏感）：
      1. 清页脚噪声
      2. 按 num/next_num 切 chunk
      3. **next.stem 头部截断**：在原始 chunk 上找 next 题任意行（含短标题），
         截断到最早出现位置——必须在孤立短行清理之前，否则"多旋翼无人机" 这种
         6 字标题被噪声清理误丢，导致截断点找不到。
      4. 清孤立短行（图中标签等）
      5. 行内填空空白合并
    """
    clean = _PAGE_FOOTER_NOISE.sub("\n", full_text)
    start_re = re.compile(rf"(?m)^\s*{num}\s*[.、．]")
    end_re = re.compile(rf"(?m)^\s*{next_num}\s*[.、．]")
    sm = start_re.search(clean)
    if not sm: return ""
    em = end_re.search(clean, sm.end())
    chunk = clean[sm.end():em.start() if em else len(clean)]
    chunk = re.split(r"(?m)^\s*(?:参考答案|答案及评分)", chunk, maxsplit=1)[0]

    # next.stem 头部截断（在清孤立行之前）
    if nxt_heads:
        positions = []
        for h in nxt_heads:
            if h and len(h) >= 4 and h in chunk:
                positions.append(chunk.find(h))
        if positions:
            chunk = chunk[:min(positions)].rstrip()

    # 清孤立的图标签噪声：单行 ≤ 8 字、不含中文标点/子小题/选项 marker
    out_lines = []
    for ln in chunk.split("\n"):
        s = ln.strip()
        if not s:
            out_lines.append(""); continue
        if (re.search(r"[，。；：？！,;:?!]", s)
                or _SUBQ_RE.search(s)
                or re.match(r"^[A-D]\s*[.、．]", s)
                or len(s) > 8):
            out_lines.append(ln)
    chunk = "\n".join(out_lines).strip()
    return _join_oversplit_lines(chunk)


def _expected_subq_count(stem: str) -> int | None:
    """根据 stem 启动语推 (1)(2)(3) 应有几个。无明显启动语则 None。"""
    # 试卷常见启动语 + 数字提示，但腾讯返回信息不足时简单计数现有 (N)
    matches = sorted({int(m.group(1)) for m in re.finditer(r"\((\d)\)", stem)})
    return max(matches) if matches else None


def _refill_subquestions(questions: list[dict], cache_dir: Path,
                          images_dir: Path, n_pages: int,
                          answer_pages: set[str] | None = None,
                          force: bool = False) -> int:
    """主观题（实验/计算/解答/填空）若 stem 缺 (1)(2)(3) 子小题
    （腾讯 Question.ResultList 给空或残缺）→ 用 GeneralAccurateOCR 跨页补抽。

    策略：对每个 type 为非选择题的题，若 stem 不含 "(N)" 模式：
      1. OCR source_page 起到下一题号出现为止的所有页
      2. 切出 `^num.` 到 `^next_num.` 之间的整段
      3. 若比腾讯返回的 stem 长，则替换
    """
    general_cache = cache_dir / "general"
    general_cache.mkdir(parents=True, exist_ok=True)

    nums_sorted = sorted({q["number"] for q in questions if q.get("number", 0) > 0})
    next_num: dict[int, int] = {n: nums_sorted[i+1] if i+1 < len(nums_sorted)
                                else 999 for i, n in enumerate(nums_sorted)}
    by_num: dict[int, dict] = {q["number"]: q for q in questions
                                if q.get("number")}
    # 答案页起始页号——refill 不能越过这一页，否则会把答案页解答内容拉进 stem
    first_answer_page = n_pages + 1
    for ap in (answer_pages or set()):
        m = re.search(r"page-(\d+)", ap)
        if m:
            first_answer_page = min(first_answer_page, int(m.group(1)))
    fixed = 0
    for q in questions:
        if q["type"] in ("choice", "multi_choice"):
            continue
        stem = q.get("stem") or ""
        page = q.get("source_page")
        if not page: continue
        num = q["number"]; nxt = next_num.get(num, 999)
        nxt_q = by_num.get(nxt)
        nxt_page = (nxt_q.get("source_page") if nxt_q else None) or n_pages
        # 扫到 next 题源页（含）——子小题可能延续到 next 源页前几行；
        # 再用 next.stem 头部截断防误吃 next 的前导材料
        end_page = max(page, nxt_page)
        # 不能越过答案页起始（防 Q26 这种最后题把答案页解答拉进 stem）
        end_page = min(end_page, first_answer_page - 1)

        parts: list[str] = []
        for pg in range(page, min(end_page + 1, n_pages + 1)):
            gf = general_cache / f"page-{pg:02d}.txt"
            if gf.exists() and not force:
                txt = gf.read_text(encoding="utf-8")
            else:
                txt = _call_general_ocr(images_dir / f"page-{pg:02d}.png")
                gf.write_text(txt, encoding="utf-8")
            parts.append(txt)
            if re.search(rf"(?m)^\s*{nxt}\s*[.、．]", txt):
                break
        full = "\n".join(parts)
        # 从 next 题 stem 抽多候选 head（含短标题），传给 _slice 内部按最早匹配截断
        nxt_heads: list[str] = []
        if nxt_q and nxt_q.get("stem"):
            for ln in nxt_q["stem"].split("\n"):
                s = ln.strip()
                if len(s) >= 4:
                    nxt_heads.append(s[:30])
                    if len(nxt_heads) >= 5:
                        break
        chunk = _slice_general_text(full, num, nxt, nxt_heads=nxt_heads)

        if chunk and len(chunk) > len(stem):
            q["stem"] = chunk
            fixed += 1
            print(f"  [refill-subq] Q{num} stem: {len(stem)} → {len(chunk)} 字",
                  flush=True)
    return fixed


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
    print(f"[physics_image_paper] 题号缺口 {missing}，用通用 OCR 补抽", flush=True)

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
    """把腾讯 ResultList[i] 一项构造为内部题字典。

    **关键嵌套结构**：腾讯实验探究/解答题的 (1)(2)(3) 子小题放在
    item.Question[0].ResultList[] 里（每子小题又有 Question/Option/Figure/
    Table/Coord 全套字段）。本函数把所有子小题的 Text 追加到 stem，把它们的
    Figure/Option/Table 合并到主题——否则 Q17 等只剩"如图14甲..."一行 stem。
    """
    sx, sy = scale
    q_arr = item.get("Question") or []
    stem_text = q_arr[0].get("Text", "") if q_arr else ""
    num = _peek_number(item) or 0
    group_type = q_arr[0].get("GroupType", "") if q_arr else ""

    # 收集 main item + 所有子小题（Question[0].ResultList）的 Option/Figure/Table
    def _collect_subs(item_or_sub: dict, sub_arr: list[dict]):
        for opt in item_or_sub.get("Option") or []:
            sub_arr.append(("option", opt))
        for fig in item_or_sub.get("Figure") or []:
            sub_arr.append(("figure", fig))
        for tbl in item_or_sub.get("Table") or []:
            sub_arr.append(("table", tbl))

    collected: list[tuple[str, dict]] = []
    _collect_subs(item, collected)

    # 子小题（嵌套 Question[0].ResultList）
    sub_texts: list[str] = []
    if q_arr and q_arr[0].get("ResultList"):
        for sub in q_arr[0]["ResultList"]:
            sq = sub.get("Question") or []
            if sq:
                t = sq[0].get("Text", "").strip()
                if t:
                    sub_texts.append(t)
            _collect_subs(sub, collected)

    # 完整 stem = 主 stem + 所有子小题 Text
    full_stem = stem_text
    for st in sub_texts:
        if st:
            full_stem += "\n" + st

    # 选项
    options: dict[str, str] = {}
    for kind, obj in collected:
        if kind != "option": continue
        label, text = _parse_option_text(obj.get("Text", ""))
        if label:
            options[label] = text

    # Figures / Tables bbox（统一存进 _figs，带 page 标记）
    # kind 标准化：image / table（"figure" 来源标签统一为 "image"，方便下游 fallback
    # 按 "image 数 vs stem refs 数" 判定缺图）
    fig_count = 0; tbl_count = 0
    figs: list[dict] = []
    for kind, obj in collected:
        if kind not in ("figure", "table"): continue
        if not obj.get("Coord"): continue
        bbox = _bbox_xyxy(obj["Coord"], sx, sy)
        out_kind = "image" if kind == "figure" else "table"
        figs.append({"page": source_page, "bbox": bbox, "kind": out_kind})
        if kind == "figure": fig_count += 1
        else: tbl_count += 1

    type_en = _infer_type_en(num, options, group_type)
    has_img_opts = (
        type_en in ("choice", "multi_choice")
        and fig_count >= 3
        and (not options or len(options) == fig_count)
    )

    return {
        "number": num,
        "type": type_en,
        "score": _default_score(num),
        "stem": _normalize_stem(full_stem),
        "_stem_raw": stem_text,
        "options": options if options else None,
        "has_image_options": has_img_opts,
        "source_page": source_page,
        "_group_type": group_type,
        "_figs": figs,
        "_outer_coord": _bbox_xyxy(item.get("Coord", {}), sx, sy)
                        if item.get("Coord") else None,
    }


def _merge_into(prev: dict, cur: dict) -> None:
    """把无题号续块合并到上一有号块（stem 接在 prev 后面）。"""
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
    prev.setdefault("_figs", []).extend(cur.get("_figs") or [])


def _merge_forward(target: dict, lead: dict) -> None:
    """把前导块（阅读材料）合并到后续有题号块（stem 接在 target 前面）。"""
    if lead.get("stem"):
        if target["stem"]:
            target["stem"] = lead["stem"] + "\n" + target["stem"]
        else:
            target["stem"] = lead["stem"]
    target.setdefault("_figs", [])
    target["_figs"] = (lead.get("_figs") or []) + target["_figs"]


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


def _compact_solution(text: str) -> str:
    """合并 solution 中散开的短行（数学公式被 OCR 按视觉行切碎的情况）。

    规则：只用「解:」/ 「(N)」 作段落分隔，其余行合并到当前段落（用空格）。
    Q25 这种"G\\n2N\\nm球\\n2N..." 公式碎片会聚成 1 段，避免视觉上一长串散行。
    """
    paragraphs: list[str] = []
    cur: list[str] = []

    def _flush():
        if cur:
            paragraphs.append(" ".join(cur))

    for ln in text.split("\n"):
        s = ln.strip()
        if not s: continue
        # 段落起始：(N) 子小题 或 "解:" 标头；(N分) 不算（分值标注是行尾内联）
        if re.match(r"^\s*\([1-9]\)(?![分])", s) or re.match(r"^\s*解\s*[:：]", s):
            _flush(); cur = [s]
        else:
            cur.append(s)
    _flush()
    return "\n".join(paragraphs)


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
            # 公式碎行紧凑：按 (N)/解: 分段，其余短行合并到段落
            out[cur_num] = _compact_solution("\n".join(buf)).strip()

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


_READ_PASSAGE_REF_RE = re.compile(r"(根据文章|根据材料|阅读|根据上文|根据上述材料)")


def _assemble(api_per_page: dict[str, dict],
              answer_pages_text: dict[str, str] | None = None
              ) -> tuple[list[dict], list[dict], int, set[str]]:
    """聚合多页 API 结果 → (questions, answers, num_pages, answer_pages_set)。

    跨题归属规则（针对无题号块）：
      - 默认归前一有题号块（续题/选项行/续描述）
      - 但若下一块也是有题号块、且其 stem 含「根据文章/根据材料/阅读」等
        引用前文的标记 → 该块是"前导阅读材料"，归后一块（如 Q24 科普阅读）
    """
    questions: list[dict] = []
    answer_items: list[dict] = []
    answer_pages: set[str] = set()

    # 第一遍：page-level 答案页判定。两种触发：
    #   (a) 某 item.Question.Text 含"参考答案/(N分)" 等 marker
    #   (b) 某页"最小题号"< 之前页"历史最大题号"- 3（题号显著倒退；
    #       适配 changping/dongcheng/pinggu 这种无"参考答案"标题的答案页）
    # 一旦命中，该页及后续所有页都算答案页。
    sorted_pages = sorted(api_per_page)
    first_answer_idx = len(sorted_pages)

    # 收集每页题号
    page_nums: dict[str, list[int]] = {}
    for page_name in sorted_pages:
        rl = (api_per_page[page_name].get("QuestionInfo") or [{}])[0]\
                .get("ResultList", [])
        nums = []
        for item in rl:
            n = _peek_number(item)
            if n: nums.append(n)
        page_nums[page_name] = nums

    max_seen = 0
    for i, page_name in enumerate(sorted_pages):
        rl = (api_per_page[page_name].get("QuestionInfo") or [{}])[0]\
                .get("ResultList", [])
        # (a) 标准 marker
        for item in rl:
            q_text = ((item.get("Question") or [{}])[0]).get("Text", "")
            if _is_answer_marker(q_text):
                first_answer_idx = i; break
        if first_answer_idx < len(sorted_pages):
            break
        # (b) 题号倒退
        nums = page_nums[page_name]
        if nums and max_seen and min(nums) < max_seen - 3:
            first_answer_idx = i; break
        if nums:
            max_seen = max(max_seen, max(nums))

    for page_name in sorted_pages[first_answer_idx:]:
        answer_pages.add(page_name)

    # 第二遍：把非答案页的 items 收集成线性序列，方便用 next 上下文决策
    flat_items: list[tuple[int, dict, tuple[float, float]]] = []
    for page_name in sorted_pages:
        d = api_per_page[page_name]
        page_num = int(re.search(r"page-(\d+)", page_name).group(1))
        scale = tuple(d.get("_scale", [1.0, 1.0]))
        rl = (d.get("QuestionInfo") or [{}])[0].get("ResultList", [])
        if page_name in answer_pages:
            for item in rl:
                answer_items.append(item)
        else:
            for item in rl:
                flat_items.append((page_num, item, scale))

    # 线性扫描，决策每个 item 归前 vs 归后
    pending_forward: dict | None = None  # 等待归到下一个有题号块的"前导块"
    for i, (page_num, item, scale) in enumerate(flat_items):
        qd = _build_question(item, scale, page_num)
        if qd["number"] > 0:
            # 若有前导块在等，先合并进当前题
            if pending_forward:
                _merge_forward(qd, pending_forward)
                pending_forward = None
            questions.append(qd)
        else:
            # 无题号块 → 决定归前还是归后
            goes_forward = False
            for j in range(i + 1, len(flat_items)):
                nxt_qd = _build_question(flat_items[j][1], flat_items[j][2],
                                          flat_items[j][0])
                if nxt_qd["number"] > 0:
                    if _READ_PASSAGE_REF_RE.search(nxt_qd.get("stem") or ""):
                        goes_forward = True
                    break
            if goes_forward:
                # 暂存，等下一个有题号块来吸收（合并 stem/figs/options）
                if pending_forward is None:
                    pending_forward = qd
                else:
                    _merge_into(pending_forward, qd)
            elif questions:
                _merge_into(questions[-1], qd)
            # else 丢弃（页头）

    # 答案页通用 OCR 文本（外部传入，包含整页选择题表格）
    general_text = "\n".join((answer_pages_text or {}).get(p, "")
                              for p in sorted(answer_pages))
    answers = _parse_answer_page(answer_items, general_text) if answer_items else []
    return questions, answers, len(api_per_page), answer_pages


# ─── 裁图 ────────────────────────────────────────────────────────────────────

PADDING_PX = 10  # 外扩留白

def _group_same_row(bboxes: list[tuple]) -> list[list[tuple]]:
    """按 y 重叠分组：同一行（y_IoU > 0.3）的 bbox 合并为一组；不同行独立。
    返回 [[bbox,...], ...]，每组内的 bbox 是同行（视觉上横排），不同组独立裁切。
    """
    groups: list[list[tuple]] = []
    used = set()
    for i, a in enumerate(bboxes):
        if i in used: continue
        ay1, ay2 = a[1], a[3]
        g = [a]; used.add(i)
        for j in range(i + 1, len(bboxes)):
            if j in used: continue
            b = bboxes[j]
            by1, by2 = b[1], b[3]
            inter = max(0, min(ay2, by2) - max(ay1, by1))
            union = max(ay2, by2) - min(ay1, by1)
            iou_y = inter / union if union > 0 else 0
            if iou_y > 0.3:
                g.append(b); used.add(j)
        groups.append(g)
    return groups


def _vstack_pil(sub_imgs: list, gap: int = 10):
    """多张 PIL 图垂直拼接（等比缩放窄的到最大宽）。"""
    if len(sub_imgs) == 1:
        return sub_imgs[0]
    max_w = max(s.size[0] for s in sub_imgs)
    resized = []
    for s in sub_imgs:
        sw, sh = s.size
        if sw < max_w:
            resized.append(s.resize((max_w, int(sh * max_w / sw)), Image.LANCZOS))
        else:
            resized.append(s)
    total_h = sum(s.size[1] for s in resized) + gap * (len(resized) - 1)
    out = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y = 0
    for s in resized:
        out.paste(s, (0, y))
        y += s.size[1] + gap
    return out


def _crop_figures(src_images_dir: Path, questions: list[dict],
                  out_figures: Path) -> dict[int, str]:
    """按 q['_figs'] 每张图的 page 字段从对应原页裁切。

    关键：**只对"同行"图合并外接矩形**（如 Q1 的 4 张图选项横排，视觉成一张）。
    "不同行"图分别裁后 vstack（如 Q14 右上 image11 + 左下 data table，
    两者位置不重叠，合并外接会吞中间题干文字）。
    """
    out_figures.mkdir(parents=True, exist_ok=True)
    page_imgs: dict[int, Path] = {}
    for p in src_images_dir.glob("page-*.png"):
        m = re.search(r"page-(\d+)", p.name)
        if m:
            page_imgs[int(m.group(1))] = p

    figure_paths: dict[int, str] = {}
    for q in questions:
        # 只裁 image kind；table（数据表）属于 stem 内容范畴，应进 stem 文本，
        # 不应裁成 figure 与示意图拼在一起（Q14 表 1 数据若进图，视觉上奇怪）
        figs = [f for f in (q.get("_figs") or []) if f.get("kind") == "image"]
        if not figs:
            continue
        # 先按 page 分组，每页内再按"同行"细分
        by_page: dict[int, list[tuple]] = {}
        for f in figs:
            by_page.setdefault(f["page"], []).append(f["bbox"])

        sub_imgs = []
        for pg in sorted(by_page):
            img_path = page_imgs.get(pg)
            if not img_path: continue
            img = Image.open(img_path); W, H = img.size
            # 同页内按"y 重叠"分组，每组一张外接矩形 crop
            row_groups = _group_same_row(by_page[pg])
            row_groups.sort(key=lambda g: min(b[1] for b in g))
            for group in row_groups:
                x1, y1, x2, y2 = _outer_rect(group)
                x1 = max(0, x1 - PADDING_PX); y1 = max(0, y1 - PADDING_PX)
                x2 = min(W, x2 + PADDING_PX); y2 = min(H, y2 + PADDING_PX)
                if x2 > x1 and y2 > y1:
                    sub_imgs.append(img.crop((x1, y1, x2, y2)))

        if not sub_imgs:
            continue
        final = _vstack_pil(sub_imgs)
        out = out_figures / f"q{q['number']:02d}.png"
        final.save(out)
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
    print(f"[physics_image_paper] {len(pages)} 页 → {out_dir}", flush=True)

    # 1) 每页调 API（带缓存）
    api_results: dict[str, dict] = {}
    t0 = time.time()
    for p in pages:
        api_results[p.name] = _api_cached(p, cache_dir, force=a.force)
        rl_n = len((api_results[p.name].get("QuestionInfo") or [{}])[0]
                   .get("ResultList", []))
        print(f"  {p.name}: {rl_n} 块", flush=True)
    print(f"[physics_image_paper] API 总耗时 {time.time()-t0:.1f}s", flush=True)

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
        print(f"[physics_image_paper] qwen-vl 兜底补 {len(qd)} 个选择题答案，"
              f"correct 总数 {sum(1 for a in answers if a['correct'])}",
              flush=True)

    # 4a-2) 主观题子小题补全：腾讯 Question.ResultList 给空时用通用 OCR 跨页补
    rf = _refill_subquestions(questions, cache_dir, images_dir,
                                n_pages=len(pages),
                                answer_pages=answer_pages, force=a.force)
    if rf:
        print(f"[physics_image_paper] 通用 OCR 补 {rf} 题 stem/子小题", flush=True)

    # 4b) 题号缺口 fallback：通用 OCR 补抽（如 chaoyang page-01 漏切）
    got = [q["number"] for q in questions if q.get("number", 0) > 0]
    fb = _fill_gaps_via_general_ocr(api_results, cache_dir, images_dir,
                                     got, force=a.force)
    if fb:
        existing = {q["number"] for q in questions}
        for q in fb:
            if q["number"] not in existing:
                # 兼容内部字段（裁图需要这些 _ 字段）
                q.setdefault("_figs", [])
                q.setdefault("_outer_coord", None)
                q.setdefault("_group_type", "")
                q.setdefault("_stem_raw", q["stem"])
                questions.append(q)
        questions.sort(key=lambda x: x["number"])
        print(f"[physics_image_paper] fallback 补抽 {len(fb)} 题 → 总 {len(questions)} 题",
              flush=True)
    print(f"[physics_image_paper] 解析出 {len(questions)} 题 / {len(answers)} 答案 "
          f"(其中 correct 非空 {sum(1 for a in answers if a['correct'])})",
          flush=True)

    # 4b-2) 含表题：表格 OCR 成 markdown 追加到 stem 末尾（与图剥离）
    rt = _refill_table_data(questions, cache_dir, images_dir, force=a.force)
    if rt:
        print(f"[physics_image_paper] OCR 表格补 {rt} 题 stem", flush=True)

    # 4c-1) 图归属重分配：跨页/相邻题 figs 按 stem refs 数全局再分配
    #     场景：Q4 stem 在 p1 底，图被腾讯归到 p2 顶部的 Q5 → 把 Q5 多余的图转给 Q4
    nmoved = _redistribute_figures_by_stem_refs(questions)
    if nmoved:
        print(f"[physics_image_paper] 全局重分配转移 {nmoved} 张图", flush=True)

    # 4c-2) 缺图兜底：经过重分配仍 stem 引"图N"但 figs=0 → paddle 补
    layout_cache_dir = out_dir / "layout-cache"
    nfix = _fallback_missing_figures(questions, images_dir, layout_cache_dir, src)
    if nfix:
        print(f"[physics_image_paper] paddle 兜底 {nfix} 题 figures", flush=True)

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
        print(f"[physics_image_paper] 裁切 {len(figure_paths)} 张 figures", flush=True)

    # 5b) 从答案页文本 + 卷首文本动态校正分值（覆盖 _default_score 兜底）
    full_answer_text = "\n".join(answer_text.values())
    score_rules = _parse_score_rules_from_text(full_answer_text)
    if score_rules:
        for q in questions:
            if q["number"] in score_rules:
                q["score"] = score_rules[q["number"]]
        print(f"[physics_image_paper] 答案页解析分值规则覆盖 {len(score_rules)} 题",
              flush=True)
    # full_score：先尝试 page-01 卷首文本"满分N分"，否则用各题分值求和
    full_score = None
    p01 = images_dir / "page-01.png"
    if p01.exists():
        gf01 = cache_dir / "general" / "page-01.txt"
        gf01.parent.mkdir(parents=True, exist_ok=True)
        if not gf01.exists() or a.force:
            txt01 = _call_general_ocr(p01)
            gf01.write_text(txt01, encoding="utf-8")
        full_score = _parse_full_score_from_text(gf01.read_text(encoding="utf-8"))
    if full_score is None:
        full_score = sum(q.get("score", 0) for q in questions) or None

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
        "full_score": full_score,
        "questions": out_questions,
        "answers": answers,
    }
    out_struct = out_dir / "structured-cloud"
    out_struct.mkdir(parents=True, exist_ok=True)
    fj = out_struct / "final.json"
    fj.write_text(json.dumps(final, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    print(f"[physics_image_paper] ✅ {fj}", flush=True)
    print(f"   题号={[q['number'] for q in out_questions]}", flush=True)


if __name__ == "__main__":
    main()
