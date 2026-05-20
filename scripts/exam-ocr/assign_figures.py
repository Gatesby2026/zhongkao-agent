"""把 paddle 检测的 image bbox 分配给试卷题号。

核心算法：
  1. 题号 y 区间：用 OCR 文本里题号锚点的字符位置 → 该题在页面的 y 百分比区间
  2. 含图证据：每题题干含 `[图]` / `如图` 的次数 = 该题的图 demand
  3. 全局匹配：贪心分配（按 y-IoU 排序），每题 supply 数 ≤ 该题 demand

完全基于程序规则，无 LLM 依赖。
"""
from __future__ import annotations

import re
from typing import Iterable


SECTION_HEAD_RE = re.compile(
    r"(?m)^\s*[一二三四五六七八九十]+\s*[、，][^\n]{0,40}(?:题|分\s*[)）])")
STRONG_ANSWER_MARKERS_RE = re.compile(
    r"(答案及评分(参考|标准|说明)?|参考答案|参考解答|答案与解析|评分标准)"
)
NUM_ANCHOR_RE = re.compile(r"(?m)^\s*(\d{1,2})\s*[.、．]\s*(?=\S)")
HAS_FIG_RE = re.compile(r"(如图|\[图\])")
# 题干里"如图N/图N所示"引用 → 该题需要的图号集合（语义硬键）
STEM_FIG_REF_RE = re.compile(r"如图\s*(\d+)|图\s*(\d+)\s*所示")
# 页内"图N[甲乙丙丁戊]"caption（图旁/图下标注，按 OCR 文档顺序≈视觉顺序）
PAGE_FIG_CAP_RE = re.compile(r"图\s*(\d+)\s*([甲乙丙丁戊])?")


def is_answer_page(text: str) -> bool:
    """前 400 字符含答案页强 marker → True。"""
    return bool(STRONG_ANSWER_MARKERS_RE.search(text[:400]))


def _strip_preamble(text: str, is_first_page: bool) -> tuple[str, int]:
    """page 1 头部的考生须知/封面信息会带 1./2./3. 条目，误匹为题号锚点。
    用大题标题（"一、单项选择题"）锚点剥掉。

    返回 (stripped_text, offset_chars)。
    """
    if not is_first_page:
        return text, 0
    m = SECTION_HEAD_RE.search(text)
    if m:
        return text[m.start():], m.start()
    return text, 0


def question_y_intervals(ocr_text: str, is_first_page: bool = False) -> dict[int, tuple[float, float]]:
    """从单页 OCR 文本算出每题在该页的 y 百分比区间。

    返回 {q_num: (y_pct_start, y_pct_end)}；y_pct 范围 0-100。

    原理：题号锚点 `^N.` 在文本中的字符位置 ≈ 该题在页面上的 y 起始位置。
    """
    total_full = len(ocr_text) or 1
    stripped, offset = _strip_preamble(ocr_text, is_first_page)
    y_off_pct = offset / total_full * 100
    stripped_total = len(stripped) or 1

    anchors: list[tuple[int, float]] = []
    for m in NUM_ANCHOR_RE.finditer(stripped):
        rel_pct = m.start() / stripped_total * 100
        abs_pct = y_off_pct + rel_pct * (1 - y_off_pct / 100)
        anchors.append((int(m.group(1)), abs_pct))

    intervals: dict[int, tuple[float, float]] = {}
    for i, (n, y) in enumerate(anchors):
        y_end = anchors[i + 1][1] if i + 1 < len(anchors) else 100.0
        intervals[n] = (y, y_end)
    return intervals


def question_figure_demand(ocr_text: str, is_first_page: bool = False) -> dict[int, int]:
    """每题题干含图的次数。作为图形 bbox 的 demand。

    返回 {q_num: count}；count = 0 表示该题不含图。
    覆盖 "如图N"/"[图]"/"图N所示" 三类（旧版只看前两类——"图N所示" 一律算 0
    导致整页被 extract_figures 跳过、paddle 不跑、q17/q18 等永远缺失）。
    """
    stripped, _ = _strip_preamble(ocr_text, is_first_page)
    anchors = [(int(m.group(1)), m.start()) for m in NUM_ANCHOR_RE.finditer(stripped)]

    demand: dict[int, int] = {}
    for i, (n, pos) in enumerate(anchors):
        end = anchors[i + 1][1] if i + 1 < len(anchors) else len(stripped)
        seg = stripped[pos:end]
        narrow = len(HAS_FIG_RE.findall(seg))
        refs = {(m.group(1) or m.group(2)) for m in STEM_FIG_REF_RE.finditer(seg)}
        demand[n] = max(narrow, len(refs))
    return demand


def question_fig_refs(ocr_text: str, is_first_page: bool = False) -> dict[int, set[str]]:
    """每题题干引用的"图号"集合（来自 `如图N` / `图N所示`）。

    返回 {q_num: {"1","8甲",...}}。空集表示该题不引用具名图。
    这是配题的**语义硬键**：题干"如图8"必须配到 caption "图8"的图，
    不受 paddle 合并/y 区间精度任何影响。
    """
    stripped, _ = _strip_preamble(ocr_text, is_first_page)
    anchors = [(int(m.group(1)), m.start()) for m in NUM_ANCHOR_RE.finditer(stripped)]
    out: dict[int, set[str]] = {}
    for i, (n, pos) in enumerate(anchors):
        end = anchors[i + 1][1] if i + 1 < len(anchors) else len(stripped)
        seg = stripped[pos:end]
        refs: set[str] = set()
        for m in STEM_FIG_REF_RE.finditer(seg):
            num = m.group(1) or m.group(2)
            if num:
                refs.add(num)
        out[n] = refs
    return out


def page_caption_seq(page_text: str, base_only: bool = False) -> list[str]:
    """页内"图N[甲乙]"caption 按 OCR 出现顺序（≈视觉 top→bottom）去重列表。
    返回 ["1","2","8甲","8乙",...]；同一图被多次引用只保首次。
    base_only=True 时按基础图号去重（"8甲"/"8乙" 合并为 "8"）——用于
    单题多子图（甲乙丙）场景，避免子图 caption 把序列吹大致配对失败。
    """
    seen: set[str] = set(); seq: list[str] = []
    for m in PAGE_FIG_CAP_RE.finditer(page_text):
        key = m.group(1) if base_only else m.group(1) + (m.group(2) or "")
        if key not in seen:
            seen.add(key); seq.append(key)
    return seq


def pair_units_to_fig_nums(
    page_text: str, image_boxes: list[dict], units: list[list[int]],
) -> dict[int, str]:
    """**按 unit（cluster 后的图组/单图）**与 OCR caption 序列配对。

    关键：图片选项题（"如图N所示"+ABCD 4 张选项图）下，paddle 给 N 张 image
    bbox，OCR 只给 1 个 "图N" caption——unit 数 = 1 = caption 数。**必须先
    cluster 再配对**，否则 count 永远对不齐导致整页放弃图号主键。

    units 是 [[image_idx,...], ...]，已按 y_top 排序。返回 {unit_idx: "N"}。
    """
    cap_seq = page_caption_seq(page_text)
    if not cap_seq or not units:
        return {}
    # 多子图页（如 Q17 含 14甲/14乙/14丙 + Q20 含 18 + Q21 含 19）会把 cap 序列
    # 吹大到 units 的 2 倍以上。这种页用「基础图号去重」再试，子图归同一题。
    if abs(len(cap_seq) - len(units)) > 1:
        cap_seq = page_caption_seq(page_text, base_only=True)
        if abs(len(cap_seq) - len(units)) > 1:
            return {}
    pairs: dict[int, str] = {}
    for ui in range(min(len(cap_seq), len(units))):
        pairs[ui] = cap_seq[ui]
    return pairs


def y_iou(box_y: tuple[float, float], iv: tuple[float, float]) -> float:
    """两段 y 区间的 IoU（轴向重叠 / 联合长度）。所有值是 y 百分比 0-100。"""
    inter = max(0.0, min(box_y[1], iv[1]) - max(box_y[0], iv[0]))
    union = max(box_y[1], iv[1]) - min(box_y[0], iv[0])
    return inter / union if union > 0 else 0.0


def cluster_inline_image_group(
    image_boxes: list[dict], *,
    y_center_tol_px: int = 25,
    size_ratio_tol: float = 0.3,
    min_group_size: int = 3,
) -> list[list[int]]:
    """识别"4 选项图"模式：y 中心相近、尺寸相近、横向排列的 image bbox 聚为一组。

    选择题的 ABCD 选项图典型格式：4 张同行同尺寸小图（OCR 偶尔漏标 `[图]`，
    导致 demand 算少；用空间聚类绕过 OCR 不完备）。

    返回 [[idx,...], ...] 每组是 image_boxes 的下标列表。单图（无同伴）不入组。
    """
    groups: list[list[int]] = []
    used: set[int] = set()
    for i, b in enumerate(image_boxes):
        if i in used:
            continue
        x1, y1, x2, y2 = b["bbox"]
        yc = (y1 + y2) / 2
        bw, bh = x2 - x1, y2 - y1
        cluster = [i]
        for j in range(i + 1, len(image_boxes)):
            if j in used:
                continue
            bj = image_boxes[j]
            x1j, y1j, x2j, y2j = bj["bbox"]
            ycj = (y1j + y2j) / 2
            bwj, bhj = x2j - x1j, y2j - y1j
            if abs(yc - ycj) > y_center_tol_px:
                continue
            # 尺寸相近
            if bw <= 0 or bh <= 0 or bwj <= 0 or bhj <= 0:
                continue
            if abs(bw - bwj) / max(bw, bwj) > size_ratio_tol:
                continue
            if abs(bh - bhj) / max(bh, bhj) > size_ratio_tol:
                continue
            cluster.append(j)
        if len(cluster) >= min_group_size:
            for k in cluster:
                used.add(k)
            groups.append(cluster)
    return groups


def assign_images_to_questions(
    image_boxes: list[dict],
    intervals: dict[int, tuple[float, float]],
    demands: dict[int, int],
    page_height: int,
    *,
    choice_qs: set[int] | None = None,
    min_iou: float = 0.05,
    page_text: str = "",
    is_first_page: bool = False,
) -> dict[int, list[dict]]:
    """全局匹配 image bbox 到题号。

    Args:
        image_boxes: paddle 输出的 image 类 bbox 列表
        intervals: {q_num: (y_pct_start, y_pct_end)}
        demands: {q_num: 题干含图数量} —— 作为 demand 上限
        page_height: 页面像素高度
        choice_qs: 选择题题号集合。用于优先把"4 选项图组"分给选择题（如 Q3
                   ABCD 各一张图，OCR 常漏标 `[图]` 致 demand 偏低）
        min_iou: y-IoU 低于此阈值的非组匹配丢弃

    策略：
      1. **空间聚类**把"同行同尺寸 ≥3 张图"聚成 unit，避免 OCR 漏标导致拆分
      2. **聚类组优先归选择题**：组内 y 中心找最近的 choice 题号（绕开 IoU 微差
         导致归错相邻题）
      3. 单图按 y-IoU 贪心分配，受 demand 上限约束
      4. 输出仍是每张 image 独立 bbox（同组归同题，上游裁切时合并外接矩形）

    返回 {q_num: [image_box, ...]}
    """
    if choice_qs is None:
        choice_qs = set()

    assigned: dict[int, list[dict]] = {}
    remaining = dict(demands)

    # 先把 raw image 聚成「unit」（group=4 图选项簇 OR 单图）。这是 R1 的关键
    # 修正：图选题下 N 张选项图 vs 1 个"图N"caption——必须 unit 级配对，否则
    # count 永远对不齐 → 图号主键根本不会触发（之前 14/15 的假信心来源）。
    groups_rel = cluster_inline_image_group(image_boxes)
    grouped_idx = {i for g in groups_rel for i in g}
    units: list[list[int]] = list(groups_rel) + [
        [i] for i in range(len(image_boxes)) if i not in grouped_idx]
    # unit 按 y_top 排序（≈视觉 top→bottom，与 OCR caption 文档顺序对齐）
    units.sort(key=lambda u: min(image_boxes[i]["bbox"][1] for i in u))
    used_units: set[int] = set()

    # 0. **图号硬匹配（主键）**：unit 序列 ↔ caption 序列（同 y/文档顺序）
    # 关键：用 stem_refs 作为权威 demand 上限（覆盖 HAS_FIG_RE 窄正则的漏判——
    # "图N所示" 不带 "如" 会让 demand=0，但 stem_refs 仍能识别）。
    if page_text and units:
        stem_refs = question_fig_refs(page_text, is_first_page=is_first_page)
        for q, refs in stem_refs.items():
            if refs:
                remaining[q] = max(remaining.get(q, 0), len(refs))
        unit_fig = pair_units_to_fig_nums(page_text, image_boxes, units)
        for u_idx, fig_key in unit_fig.items():
            fig_num_only = re.match(r"\d+", fig_key).group(0)
            owner = None
            for q, refs in stem_refs.items():
                if remaining.get(q, 0) <= 0:
                    continue
                if fig_key in refs or fig_num_only in refs:
                    owner = q; break
            if owner is None:
                continue
            for i in units[u_idx]:
                b = dict(image_boxes[i])
                b["_assign_reason"] = f"fig_num={fig_key}"
                assigned.setdefault(owner, []).append(b)
            remaining[owner] -= 1
            used_units.add(u_idx)

    # 2. 选择题 4 图组：剩余 cluster group unit（len≥3）归 y 最近 choice 题
    eligible_choice = [q for q in choice_qs if intervals.get(q) and demands.get(q, 0) > 0]
    for u_idx, unit in enumerate(units):
        if u_idx in used_units or len(unit) < 3:
            continue
        y1 = min(image_boxes[i]["bbox"][1] for i in unit)
        y2 = max(image_boxes[i]["bbox"][3] for i in unit)
        unit_yc = (y1 + y2) / 2 / page_height * 100
        if not eligible_choice:
            continue
        def _dist(q, yc=unit_yc):
            s, _ = intervals[q]
            return abs(s - yc)
        best_q = min(eligible_choice, key=_dist)
        if remaining.get(best_q, 0) <= 0:
            continue
        for i in unit:
            b = dict(image_boxes[i])
            b["_assign_reason"] = "choice_group"
            assigned.setdefault(best_q, []).append(b)
        remaining[best_q] -= 1
        used_units.add(u_idx)

    # 3. 单图（剩余 unit 中 len==1）按 y-IoU 贪心
    singles = [(u_idx, units[u_idx][0]) for u_idx, u in enumerate(units)
               if u_idx not in used_units and len(u) == 1]
    candidates: list[tuple[int, int, float]] = []  # (img_idx, q, iou)
    for _u_idx, i in singles:
        x1, y1, x2, y2 = image_boxes[i]["bbox"]
        box_y_pct = (y1 / page_height * 100, y2 / page_height * 100)
        for q, iv in intervals.items():
            if demands.get(q, 0) <= 0:
                continue
            iou = y_iou(box_y_pct, iv)
            if iou >= min_iou:
                candidates.append((i, q, iou))
    candidates.sort(key=lambda x: -x[2])

    used = set()
    for i, q, iou in candidates:
        if i in used:
            continue
        if remaining.get(q, 0) <= 0:
            continue
        b = dict(image_boxes[i])
        b["_y_iou"] = round(iou, 3)
        assigned.setdefault(q, []).append(b)
        used.add(i)
        remaining[q] -= 1

    return assigned


def classify_pages(
    pages_text: list[str], strong_marker_continues: bool = True
) -> list[bool]:
    """每页是否答案页。
    answer page detection: 含 strong marker 的页 + 之后所有页都算答案页（试卷格式约定）。
    """
    n = len(pages_text)
    out = [False] * n
    for i, t in enumerate(pages_text):
        if is_answer_page(t):
            out[i] = True
    if strong_marker_continues:
        first = next((i for i, x in enumerate(out) if x), None)
        if first is not None:
            for i in range(first, n):
                out[i] = True
    return out
