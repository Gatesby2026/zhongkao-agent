"""答题卡上传预检（detect 阶段，全流水线之前快失败）。

分层：
  L1 本地图像质量门（纯 PIL，毫秒级）：分辨率/清晰度/亮度/可解码
  L2 结构化完整性（card_meta 的 LLM 结构化输出，本模块只做判定）
  L3 KB 交叉核对（应有选择题数/主观题数 vs 识别到的）

产出统一 precheck dict：
  {block: bool, hard: [...], warn: [...], expected:{}, seen:{}, pages:[...]}
block=True → tasks 直接 mark_failed（带逐页可执行指引），不跑重流水线。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

# 阈值（保守：宁可放过边缘也别误挡好卡；硬挡只在明显不可用时触发）
MIN_LONG_EDGE = 1400          # 长边像素下限（imgnorm 正立化后通常 ≥2250）
HARD_LONG_EDGE = 760          # 低于此基本不可用 → 硬挡
BLUR_WARN = 70                # 边缘方差 < 此 → 偏糊（软警示）
BLUR_HARD = 22                # 边缘方差 < 此 → 基本糊到不可用
DARK_WARN = 55                # 平均灰度 < 此 → 偏暗
BRIGHT_WARN = 232             # 平均灰度 > 此 → 过曝/反光


def _page_metrics(p: Path) -> dict:
    """单张：长边、清晰度（拉普拉斯近似：FIND_EDGES 后方差）、平均亮度。"""
    m: dict = {"name": p.name, "ok": True, "issues": []}
    try:
        im = Image.open(p)
        im.load()
    except Exception as e:
        return {"name": p.name, "ok": False, "fatal": True,
                "issues": [f"无法解码（{e.__class__.__name__}）"]}
    w, h = im.size
    m["px"] = f"{w}x{h}"
    long_edge = max(w, h)

    g = im.convert("L")
    # 统一缩到长边 ~1024 再测，阈值才稳定可比
    if max(g.size) > 1024:
        s = 1024.0 / max(g.size)
        g = g.resize((max(1, round(g.size[0] * s)),
                      max(1, round(g.size[1] * s))))
    bright = ImageStat.Stat(g).mean[0]
    blur = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
    m["blur"] = round(blur, 1)
    m["bright"] = round(bright, 1)

    if long_edge < HARD_LONG_EDGE:
        m["ok"] = False
        m["fatal"] = True
        m["issues"].append(f"分辨率过低（{w}x{h}）")
    elif long_edge < MIN_LONG_EDGE:
        m["issues"].append(f"分辨率偏低（{w}x{h}），建议更清晰重拍")

    if blur < BLUR_HARD:
        m["ok"] = False
        m["fatal"] = True
        m["issues"].append("画面严重模糊/失焦")
    elif blur < BLUR_WARN:
        m["issues"].append("画面偏模糊")

    if bright < DARK_WARN:
        m["issues"].append("画面偏暗")
    elif bright > BRIGHT_WARN:
        m["issues"].append("过曝/反光")
    return m


def image_quality(paths: list[Path]) -> list[dict]:
    return [_page_metrics(p) for p in paths]


def evaluate(meta: dict, pages: list[dict],
             expected: dict | None = None,
             exam_subject: str = "") -> dict:
    """汇总 L1(pages) + L2(meta) + L3(expected) → 统一 precheck。"""
    hard: list[str] = []
    warn: list[str] = []
    expected = expected or {}

    # ---- L1：逐页质量 ----
    fatal_pages = [p for p in pages if p.get("fatal")]
    soft_pages = [p for p in pages
                  if not p.get("fatal") and p.get("issues")]
    for p in pages:
        idx = pages.index(p) + 1
        if p.get("fatal"):
            hard.append(f"第{idx}页：{'；'.join(p['issues'])}")
        elif p.get("issues"):
            warn.append(f"第{idx}页：{'；'.join(p['issues'])}")
    # 全部页都不可用 → 必硬挡
    if pages and len(fatal_pages) == len(pages):
        hard.append("所有照片均无法用于识别，请在光线均匀处重新清晰拍摄")

    # ---- L2：结构化完整性 ----
    if meta.get("is_answer_card") is False:
        hard.append("上传的不像学生答题卡（可能误传了试卷/答案/课本/空白纸）")
    if meta.get("has_header") is False:
        hard.append("缺「考生须知页」表头（印有考试名称的那页），请补拍该页")
    if meta.get("has_choice_grid") is False:
        hard.append("未找到选择题填涂区，请补拍含选择题涂卡的那页")
    for ms in (meta.get("missing") or []):
        msg = f"疑似缺失：{ms}"
        (hard if "页" in str(ms) else warn).append(msg)

    # ---- L3：与 KB 交叉核对 ----
    exp_sub = int(expected.get("subjective") or 0)
    seen_sub = int(meta.get("subjective_regions") or 0)
    if exp_sub and seen_sub == 0:
        hard.append(f"未检测到任何主观题作答区（本卷应有 {exp_sub} 道），"
                    "请补拍主观题作答页")
    elif exp_sub and 0 < seen_sub < exp_sub:
        warn.append(f"主观题作答区识别到 {seen_sub}/{exp_sub}，"
                    "可能有页未拍全，请核对")

    det_sub = (meta.get("subject") or "").strip()
    if exam_subject and det_sub and det_sub != exam_subject:
        hard.append(f"答题卡科目（{det_sub}）与识别考试（{exam_subject}）不一致，"
                    "可能传错科目")

    # 完整性布尔兜底（LLM 粗判）
    if meta.get("pages_complete") is False and not hard:
        warn.append(meta.get("completeness_note")
                    or "系统判断卷面可能不完整，请核对各页是否拍全")

    return {
        "block": bool(hard),
        "hard": hard,
        "warn": warn,
        "expected": expected,
        "seen": {"subjective_regions": seen_sub,
                 "has_header": meta.get("has_header"),
                 "has_choice_grid": meta.get("has_choice_grid")},
        "pages": [{"i": i + 1, "px": p.get("px", ""),
                   "blur": p.get("blur"), "bright": p.get("bright"),
                   "issues": p.get("issues", [])}
                  for i, p in enumerate(pages)],
    }


def block_message(pc: dict) -> str:
    """硬失败时给用户的可执行指引文本。"""
    lines = ["上传的答题卡未通过预检，请按以下提示重拍后重新上传："]
    for h in pc.get("hard", []):
        lines.append(f"• {h}")
    lines.append("提示：光线均匀、四角入框、字迹清晰，务必含「考生须知页」"
                 "顶部标题行与全部作答页。")
    return "\n".join(lines)
