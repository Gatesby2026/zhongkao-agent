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


SECTION_HEAD_RE = re.compile(r"(?m)^\s*[一二三四五六七八九十]+\s*[、，][^\n]{0,40}题")
STRONG_ANSWER_MARKERS_RE = re.compile(
    r"(答案及评分(参考|标准|说明)?|参考答案|参考解答|答案与解析|评分标准)"
)
NUM_ANCHOR_RE = re.compile(r"(?m)^\s*(\d{1,2})\s*[.、．]\s*(?=\S)")
HAS_FIG_RE = re.compile(r"(如图|\[图\])")


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
    """每题题干含 `[图]` / `如图` 的次数。作为图形 bbox 的 demand。

    返回 {q_num: count}；count = 0 表示该题不含图。
    """
    stripped, _ = _strip_preamble(ocr_text, is_first_page)
    anchors = [(int(m.group(1)), m.start()) for m in NUM_ANCHOR_RE.finditer(stripped)]

    demand: dict[int, int] = {}
    for i, (n, pos) in enumerate(anchors):
        end = anchors[i + 1][1] if i + 1 < len(anchors) else len(stripped)
        seg = stripped[pos:end]
        demand[n] = len(HAS_FIG_RE.findall(seg))
    return demand


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

    # 1. 聚类
    groups = cluster_inline_image_group(image_boxes)
    grouped_idx = {i for g in groups for i in g}
    singles = [[i] for i in range(len(image_boxes)) if i not in grouped_idx]

    assigned: dict[int, list[dict]] = {}
    remaining = dict(demands)

    # 2. 聚类组：优先归到 y 中心最近的选择题（用区间中心距离，IoU 不参与）
    eligible_choice = [q for q in choice_qs if intervals.get(q) and demands.get(q, 0) > 0]
    for unit in groups:
        # unit 的 y 中心（外接矩形）
        y1 = min(image_boxes[i]["bbox"][1] for i in unit)
        y2 = max(image_boxes[i]["bbox"][3] for i in unit)
        unit_yc = (y1 + y2) / 2 / page_height * 100

        if not eligible_choice:
            continue
        # 4 选项图通常紧贴题号下方（题号 + ABCD 文字 + 4 张图同行）；
        # OCR 字符位置算法对"图密集区"y_start 略低估 1-2%。
        # 用"题号 y_start 距离" 作判据：unit_yc 最接近哪题的起点就归哪题。
        def _dist(q):
            s, _ = intervals[q]
            return abs(s - unit_yc)
        best_q = min(eligible_choice, key=_dist)
        # 把组内所有图都归 best_q（不消耗 demand 多次，组算 1 unit）
        if remaining.get(best_q, 0) <= 0:
            continue
        for i in unit:
            b = dict(image_boxes[i])
            b["_assign_reason"] = "choice_group"
            assigned.setdefault(best_q, []).append(b)
        remaining[best_q] -= 1

    # 3. 单图按 y-IoU 贪心，受 demand 上限
    candidates: list[tuple[int, int, float]] = []
    for s in singles:
        i = s[0]
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
