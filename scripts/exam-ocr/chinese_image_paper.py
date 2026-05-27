#!/usr/bin/env python3
"""chinese_image_paper — 北京中考语文试卷 PNG → final.json（v1 路线）。

学英语路线（dual-OCR + 5 层防御）+ 语文特化：
  - 5 大题：基础运用 / 古诗文 / 名著 / 现代文 / 作文
  - 多 passage 二级模型（每大题都可能含共享文本段）
  - 主观题答案是大段中文（不是 A-D）
  - 拼音注音 `(zhù)` / 故意错字 **严禁自动纠正**
  - 题型 11 种：choice / dictation / appreciation / subjective_blank /
    comprehension / correction / argument_analysis / book_review / essay /
    handwriting / interpretation

流水线：
  1. Tencent GeneralAccurate OCR 全 N 页（cache）
  2. ANSWER_MARKER 切题目页 vs 答案页 → 答案页 GeneralBasic 补
  3. _split_sections 切 5 大题
  4. 各 section parsers
  5. _parse_answers 解析答案（选择题 N.答案:A / 主观题 N.答案示例:...）
  6. _self_check + 输出 yaml

用法:
  TENCENT_OCR_SECRET_ID=... TENCENT_OCR_SECRET_KEY=... \\
    python3 scripts/exam-ocr/chinese_image_paper.py \\
      knowledge-original/<series>/<round>/<region>/chinese --subject chinese
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

# ─── 北京中考语文结构（27 题 / 100 分 / 150 分钟）───────────────────────────

SECTIONS = [
    # 默认配置（朝阳标准布局），题号范围作为参考；实际按 OCR 标题出现顺序切。
    (re.compile(r"^\s*一[、.]\s*基础\s*[··]?\s*运用"), range(1, 8),   "base",       13),
    (re.compile(r"^\s*二[、.]\s*古诗文\s*阅读"),            range(8, 16),  "classical",  16),
    (re.compile(r"^\s*三[、.]\s*名著\s*阅读"),              range(16, 17), "book_review", 5),
    (re.compile(r"^\s*四[、.]\s*现代文\s*阅读"),            range(17, 27), "modern",     26),
    (re.compile(r"^\s*五[、.]\s*作文"),                     range(27, 28), "essay",      40),
]
# **跨区通用**：按内容关键词识别 section type（忽略大题编号位置）。
# 朝阳=三名著/四现代文；石景山=三现代文/四名著。两区 type 都能正确分。
SECTION_BY_CONTENT = [
    (re.compile(r"^\s*[一二三四五][、.]\s*基础\s*[··]?\s*运用"),       "base"),
    (re.compile(r"^\s*[一二三四五][、.]\s*(?:古诗文|诗文)\s*阅读"),     "classical"),
    (re.compile(r"^\s*[一二三四五][、.]\s*名著\s*阅读"),              "book_review"),
    (re.compile(r"^\s*[一二三四五][、.]\s*现代文\s*阅读"),            "modern"),
    (re.compile(r"^\s*[一二三四五][、.]\s*(?:作文|写作|文段表达)"),     "essay"),
]
# 答案页 marker（参考英语 ANSWER_MARKER 多变体；跨区已覆盖："参考答案"、
# "X模答案"（顺义）、"X次练习答案"、"语文答案"、"语文试卷答案"、"答案及评分"）
ANSWER_MARKER = re.compile(
    r"参考答案|答案及评分|语文(?:试卷)?\s*答案|试卷答案"
    r"|[一二三四五]模答案|[一二三四五]次练习答案"
    r"|初[一二三]\s*语文\s*答案"
    r"|^\s*(?:基础\s*[··]?\s*运用|古诗文|名著|现代文|作文)\s*[:：]",
    re.MULTILINE
)

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


# ─── 图表自动裁剪（qwen-vl-max bbox + PIL crop）─────────────────────────────

_FIGURE_REF_KEYWORDS = [
    "图1", "图2", "图3", "图4", "图5",
    "如图", "下图", "上图", "图表", "见图", "见下图", "见上图",
    "饼状图", "饼图", "柱状图", "条形图", "折线图", "示意图",
]


def _has_figure_reference(text: str) -> bool:
    """passage body / question stem 是否引用了图（含 "图1" / "如图" 等关键词）。"""
    return any(kw in text for kw in _FIGURE_REF_KEYWORDS)


_FIGURE_CROP_PROMPT = """这是中考语文试卷的一页。请定位页中**最显著的图表/图形/示意图**（如柱状图、饼图、折线图、流程图、表格图示等）的 bbox 百分比坐标。

{hint}

规则：
1. 坐标百分比（0-100），左上角为原点，x 向右 y 向下
2. bbox 应包含完整图（含图标题、坐标轴、数据标签）
3. 若页面无图表（纯文字），返回 {{"bbox": null}}
4. 多个图时返回最显著的一个

输出 JSON：
{{"bbox": {{"x1": 5.0, "y1": 60.0, "x2": 95.0, "y2": 92.0}}}}

只输出 JSON。"""


def _detect_figure_bbox_on_page(page_img: Path, hint: str = "") -> tuple[float,float,float,float] | None:
    """qwen-vl-max 定位页上的图表 bbox 百分比。返回 (x1,y1,x2,y2) 或 None。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        print(f"[chinese_image_paper] ⚠ 无 DASHSCOPE_API_KEY，跳过自动图裁剪", flush=True)
        return None
    try:
        import openai
    except ImportError:
        return None
    client = openai.OpenAI(api_key=api_key,
                            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    b64 = base64.b64encode(page_img.read_bytes()).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    hint_str = f"提示：图标题或附近文字含: {hint}" if hint else ""
    prompt = _FIGURE_CROP_PROMPT.format(hint=hint_str)
    try:
        resp = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ]}],
            temperature=0.0, max_tokens=256, timeout=90,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        d = json.loads(raw)
        bbox = d.get("bbox")
        if not bbox: return None
        return (float(bbox["x1"]), float(bbox["y1"]),
                float(bbox["x2"]), float(bbox["y2"]))
    except Exception as e:
        print(f"[chinese_image_paper] ⚠ qwen-vl 定位图失败 ({page_img.name}): {e}", flush=True)
        return None


def _normalize_bbox_to_fraction(bbox: tuple) -> tuple:
    """qwen-vl 返回的 bbox 单位常混乱（percent 0-100 / per-mil 0-1000 / 像素），
    归一化到 0-1 fraction。某些情况下 x 和 y 不同单位（如 x 百分比，y 千分比）也兼容。
    """
    def _norm(v):
        v = float(v)
        if v <= 1.0: return max(0, v)
        if v <= 100: return v / 100
        if v <= 1000: return v / 1000
        # 像素级（>1000）：caller 处理（这里返回 1，触发 clamp）
        return 1.0
    return tuple(_norm(v) for v in bbox)


def _crop_figure_to_file(page_img: Path, bbox_pct: tuple, out_path: Path) -> bool:
    """PIL 按归一化 bbox 裁切图。返回成功与否。bbox_pct 单位自动识别。"""
    try:
        img = Image.open(page_img)
        W, H = img.size
        x1, y1, x2, y2 = _normalize_bbox_to_fraction(bbox_pct)
        ix1 = max(0, int(x1 * W))
        iy1 = max(0, int(y1 * H))
        ix2 = min(W, int(x2 * W))
        iy2 = min(H, int(y2 * H))
        if ix2 - ix1 < 50 or iy2 - iy1 < 50:
            print(f"[chinese_image_paper]     bbox 退化: ({ix1},{iy1},{ix2},{iy2}) "
                  f"orig={bbox_pct} W={W} H={H}", flush=True)
            return False
        crop = img.crop((ix1, iy1, ix2, iy2))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_path)
        return True
    except Exception as e:
        print(f"[chinese_image_paper] ⚠ 裁图失败: {e}", flush=True)
        return False


def _find_page_for_passage(passage_body: str, page_texts: list) -> Path | None:
    """根据 passage body 定位它所在的页（取头 60 字 在 OCR text 里找包含）。"""
    head = re.sub(r"[\s\n\[\]]", "", passage_body[:120])[:60]
    if not head: return None
    for p, t in page_texts:
        t_clean = re.sub(r"[\s\n]", "", t)
        if head[:30] in t_clean:
            return p
    return None


def _auto_crop_figures_for_passages(passages: list, page_texts: list,
                                      out_dir: Path, slug: str) -> int:
    """对所有疑似含图的 passage 自动检测 + 裁图 + 写 figure 字段。
    返回成功裁图数。
    """
    # 找 repo_root（与 _write_yaml 同款做法）
    repo_root = out_dir
    while repo_root.parent != repo_root:
        if (repo_root / "knowledge-base").is_dir(): break
        repo_root = repo_root.parent
    figs_dir = (repo_root / "knowledge-base" / "exams" / "mock"
                 / "chinese" / "beijing" / slug / "figures")
    n = 0
    for ps in passages:
        pid = ps.get("id","?"); ptype = ps.get("type","?")
        # 跳过已有 figure 的（手工 patch 已配置）
        if ps.get("figure"):
            print(f"[chinese_image_paper]   passage[{pid}] 已有 figure，跳过", flush=True)
            continue
        body = ps.get("body","") or ""
        # 触发条件：body 含"图1/2/.." 或 passage type 是 non_continuous
        if not (_has_figure_reference(body) or ptype == "non_continuous"):
            print(f"[chinese_image_paper]   passage[{pid}] type={ptype} 无图引用 → skip", flush=True)
            continue
        print(f"[chinese_image_paper]   passage[{pid}] type={ptype} 触发裁图...", flush=True)
        try:
            # 定位含此 passage 的页
            page = _find_page_for_passage(body, page_texts)
            if not page:
                print(f"[chinese_image_paper]   passage[{pid}] 未找到对应页", flush=True)
                continue
            print(f"[chinese_image_paper]     找到页: {page.name}", flush=True)
            m = re.search(r"(图[1-5][^\n。]{0,30})", body)
            hint = m.group(1) if m else ""
            print(f"[chinese_image_paper]     hint: {hint!r}, 调 qwen-vl...", flush=True)
            bbox = _detect_figure_bbox_on_page(page, hint)
            if not bbox:
                print(f"[chinese_image_paper]   passage[{pid}] qwen 未返回有效 bbox",
                      flush=True)
                continue
            print(f"[chinese_image_paper]     qwen bbox: {bbox}", flush=True)
            out_path = figs_dir / f"passage-{pid}-figure.png"
            if _crop_figure_to_file(page, bbox, out_path):
                ps["figure"] = f"{slug}/figures/passage-{pid}-figure.png"
                n += 1
                print(f"[chinese_image_paper]   🔧 自动裁图 passage[{pid}] from "
                      f"{page.name}, bbox={bbox}", flush=True)
            else:
                print(f"[chinese_image_paper]   passage[{pid}] PIL 裁图失败", flush=True)
        except Exception as e:
            import traceback
            print(f"[chinese_image_paper]   passage[{pid}] 异常: {e}", flush=True)
            traceback.print_exc()
    return n


def _ocr_page_single(img: Path, cache: Path, engine: str, force=False) -> str:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and not force:
        return cache.read_text(encoding="utf-8")
    req_cls = getattr(models, f"{engine}Request")
    req = req_cls(); req.ImageBase64 = _img_to_b64(img)
    resp = getattr(_get_client(), engine)(req)
    d = json.loads(resp.to_json_string())
    txt = "\n".join(td.get("DetectedText","") for td in d.get("TextDetections", []))
    cache.write_text(txt, encoding="utf-8")
    return txt


def _ocr_page(img: Path, cache: Path, force=False) -> str:
    txt = _ocr_page_single(img, cache, "GeneralAccurateOCR", force)
    return _strip_footers(txt)


def _ocr_page_basic_supplement(img: Path, cache_dir: Path, force=False) -> str:
    cache = cache_dir / img.name.replace(".png", ".txt")
    try:
        txt = _ocr_page_single(img, cache, "GeneralBasicOCR", force)
        return _strip_footers(txt)
    except Exception as e:
        print(f"[chinese_image_paper] ⚠ Basic 补 OCR fail ({img.name}): {e}", flush=True)
        return ""


# ─── 噪声（学英语，但语文特化保留拼音）────────────────────────────────────

# 卷面噪声 patterns —— 出口统一剥
_NOISE_LINE_PATTERNS = [
    # 页脚 "九年级语文试卷第N页(共M页)" / "语文试卷参考答案第N页"
    re.compile(r"(?:初[一二三]|九年级|高[一二三])[一-龥]{0,12}"
               r"(?:试卷|[\(（][^\)）]{1,8}[\)）])?\s*第\s*\d+\s*页"
               r"(?:\s*[\(（]\s*共\s*\d+\s*页\s*[\)）])?"),
    re.compile(r"语文(?:试卷)?(?:参考答案)?\s*第\s*\d+\s*页"
               r"(?:\s*[\(（]\s*共\s*\d+\s*页\s*[\)）])?"),
    re.compile(r"第\s*\d+\s*页\s*/\s*共\s*\d+\s*页"),
    # 单纯 "共N页" 无括号（yanqing 等 OCR 偶把 "(2分)(共10页)" 误识为 "(2分)共10页"）
    re.compile(r"共\s*\d+\s*页"),
    # 卷面 cover header
    re.compile(r"^\s*(?:北京市?\s*)?[一-龥]{1,8}区[一-龥0-9\s\-]{0,30}"
               r"(?:练习|考试|测试)\s*[\(（]?[一二三四五六\d]{0,3}[\)）]?\s*$"),
    re.compile(r"^\s*语文试卷\s*$"),
    re.compile(r"^\s*20\d{2}[.\-/]\d{1,2}\s*$"),
    # ZXXK / 北京高考在线 / 京考一点通 等水印（二模 xicheng/chaoyang R1
    # 12+ 题 stem/options/passage 都中招；行内任意位置出现都剥掉）
    re.compile(r"www\.gaokzx\.com|gaokzx\.com|bjgkzx"),
    re.compile(r"学科网\s*\(\s*www[^\)）]*\s*\)?|学科网"),
    re.compile(r"菁优网"),
    re.compile(r"北京高考(?:在线)?(?:\s*官方微信)?"),
    re.compile(r"京考一点通(?:[\(（][^\)）]*[\)）])?"),
    # OCR 把 "京考一点通" 误识成 "京者一点通"（chaoyang R1 narrative passage）
    re.compile(r"京者一点通[^\n]{0,30}"),
    re.compile(r"考在线(?:com)?"),  # OCR 噪 chaoyang Q15 "考在线com"
    re.compile(r"获取更多试题资料及排名分析信息。?"),
    re.compile(r"关注[一-龥]+(?:官方)?微信[^\n]*"),
    # **chaoyang R1 报告挖出的 14 处水印残字碎片**：OCR 把网址/小程序号切碎，
    # 残字粘 stem/options/sol 末尾。这些是 ZXXK / gaokzx / 高考在线 / 微信
    # 号品牌的细碎残片，无业务语义
    re.compile(r"(?:www\.|aokz|okzx|okz|k2x|m\.co|mwww|mx\.co|gao)"
               r"(?:\.com|x\.com|x|\.co|com)?"),
    re.compile(r"^\s*高考(?:在)?线?\s*$"),  # 整行 "高考线" / "高考在" 残字
    re.compile(r"^\s*关注\s*[:：]?\s*[，,]?\s*$"),  # 整行 "关注:，"
    re.compile(r"^\s*(?:高|线|com)\s*$"),  # 单字残片
    re.compile(r"微信号?\s*[:：]\s*\w*"),
]


def _strip_footers(text: str) -> str:
    out = []
    for ln in text.split("\n"):
        cleaned = ln
        for pat in _NOISE_LINE_PATTERNS:
            cleaned = pat.sub("", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            out.append(cleaned)
    return "\n".join(out)


# ─── 共享 helpers ───────────────────────────────────────────────────────────

# 题号行：行首 N. / N、 / N． （N 1-30）
# 题号锚：行首"N." / "N、" / "N．" / **"N，"**（xicheng OCR 把句号识为逗号）
# 兼容半/全角逗号。原 (?=\D) 会漏掉 yanqing 的 "14.7:列对..." 这种 OCR 串字
# （下→7），改为不限制下一字符，靠 1<=N<=28 范围筛除误识别。
_NUM_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．,，]\s*(.*)$", re.MULTILINE)
# 选项标记 anchor（严格：必须 . 后跟字母，避免单字"A"误命中）
# 选项标记：A./B./C./D. 标准分隔符 + 兜底 3 类 OCR 缺陷
#   - 半/全角逗号当分隔（shunyi "D，朝阳区"）
#   - 直接接中文（shunyi "D桃花源..."）
#   - 小写 b（shunyi "b.北京市..."）
# 注：仅认行首（^|\n 紧贴）以避免 passage 正文 "A 段中..." 等误命中。
_OPT_MARK_RE = re.compile(
    r"(?:^|\n)\s*([A-Da-d])\s*(?:[.、．,，]\s*|(?=[一-鿿]))",
    re.MULTILINE)


def _parse_options_block(block: str) -> dict[str, str]:
    """统一选项解析（学英语：anchor + 首现去重 + 页脚保护）。
    支持 4 种 OCR 缺陷：标准 "A."、半/全角逗号 "A，"、紧贴中文 "A中"、小写 "a."。
    """
    block = _strip_footers(block)
    marks = list(_OPT_MARK_RE.finditer(block))
    seen: set[str] = set(); marks_uniq = []
    for m in marks:
        key = m.group(1).upper()    # 小写 b/c/d 归一化为 B/C/D
        if key not in seen:
            seen.add(key); marks_uniq.append((m, key))
    opts: dict[str, str] = {}
    for i, (m, key) in enumerate(marks_uniq):
        end = marks_uniq[i+1][0].start() if i+1 < len(marks_uniq) else len(block)
        val = block[m.end():end].strip().rstrip(".").strip()
        # **option 长度上限兜底**：中文单选 option 一般 ≤ 80 字，超 100 字几乎
        # 一定吞了下段 passage 文字（chaoyang R1 Q1.D/Q3.D/Q14.D，约 200 字）
        # 截到首个换行或全角句号（必须 D 选项本体已有内容才截）
        if len(val) > 100:
            m_break = re.search(r"[\n。！？]", val)
            if m_break and m_break.start() > 0:
                truncated = val[:m_break.start()].strip()
                if truncated:
                    val = truncated
        opts[key] = val
    return opts


# 段落合并（passage body 用，禁止 strip 拼音注音）
def _join_paragraph_lines(text: str) -> str:
    lines = [ln.rstrip() for ln in text.split("\n") if ln.strip()]
    if not lines: return text
    out = [lines[0]]
    for ln in lines[1:]:
        prev = out[-1]
        # 中文句末标点（含中文标点）→ 段落分隔；否则连
        if re.search(r"[。！？；…\?\!\.]\s*['’”\")]?\s*$", prev):
            out.append(ln)
        else:
            out[-1] = prev + ln  # 中文不加空格连接
    return "\n".join(out)


# ─── section 切分 ─────────────────────────────────────────────────────────────

def _split_sections(full: str) -> dict[str, str]:
    """按 5 大题标题切（按**内容关键词**识别 section type，不依赖大题编号位置）。
    返回 {"base":..., "classical":..., "book_review":..., "modern":..., "essay":...}
    """
    lines = full.split("\n")
    section_starts: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        for re_title, typ in SECTION_BY_CONTENT:
            if re_title.search(ln):
                section_starts.append((i, typ))
                break
    # 答案页 marker 之前
    am_match = ANSWER_MARKER.search(full)
    if am_match:
        # 找 marker 所在行 idx
        pos = 0; am_idx = len(lines)
        for i, ln in enumerate(lines):
            line_end = pos + len(ln) + 1
            if pos <= am_match.start() < line_end:
                am_idx = i; break
            pos = line_end
    else:
        am_idx = len(lines)
    out: dict[str, str] = {}
    for k, (start, typ) in enumerate(section_starts):
        end = section_starts[k+1][0] if k+1 < len(section_starts) else am_idx
        if start >= am_idx: break
        end = min(end, am_idx)
        out.setdefault(typ, "\n".join(lines[start:end]).strip())
    # **跨区兜底**：若未检测到 essay section 但 q_text 含 Q27/Q28 anchor，自动归 essay。
    # pinggu 区试卷直接 "27.从下面两个题目..." 无 "五、作文" 头；昌平 Q28 是作文。
    if "essay" not in out:
        for q_essay in (27, 28):
            ln_re = re.compile(rf"^\s*{q_essay}\s*[.、．,，]")
            for i, ln in enumerate(lines[:am_idx]):
                if ln_re.match(ln):
                    for typ in list(out):
                        body = out[typ]
                        bm = ln_re.search(body)
                        if bm: out[typ] = body[:bm.start()].rstrip()
                    out["essay"] = "\n".join(lines[i:am_idx]).strip()
                    break
            if "essay" in out: break
    return out


# ─── 题型推断 + 默认分值 ────────────────────────────────────────────────────

# 朝阳 2026 一模标配（用作 fallback；下游用答案页分值标注覆盖）
DEFAULT_QSCORE = {
    1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2,            # 基础（13）
    8: 1, 9: 1, 10: 2, 11: 2, 12: 3, 13: 2, 14: 2, 15: 3,  # 古诗文（16）
    16: 5,                                                  # 名著（5）
    17: 2, 18: 2, 19: 3, 20: 2, 21: 3, 22: 3, 23: 4, 24: 2, 25: 2, 26: 3,  # 现代文（26）
    27: 40,                                                 # 作文（40）
}

# 类型映射（基于答案性质 + section type）
def _infer_qtype(n: int, section: str, ans_correct: str, ans_solution: str,
                  options: dict | None) -> str:
    """语文题型推断。注：朝阳一模题号→题型大致稳定；用 (n, section, 答案形态) 综合判断。"""
    # 选择题：答案 ans_correct 是单字母 A-D
    if ans_correct and re.fullmatch(r"[A-D]", ans_correct):
        return "choice"
    # 作文
    if section == "essay":
        return "essay"
    # 名著
    if section == "book_review":
        return "book_review"
    # 基础特殊题
    if section == "base":
        if n == 1: return "handwriting"  # 写字题
        if "答案示例" in ans_solution or "改为" in ans_solution: return "subjective_blank"
        return "subjective_blank"
    # 古诗文 —— 不依赖固定题号：根据答案形态判断
    # （朝阳 8-10 默写 / 11 古诗填空 / 12 赏析 / 13-14 文言选择 / 15 链接材料
    #   昌平 9-11 默写 / 12 赏析 / 13 赏析 / 14 文言选择 / 15 文言简答 / 16 链接材料
    #   各区差异较大，按答案样式判断更稳定。）
    if section == "classical":
        # 答案是 ① ② ③ 编号 + 短文 → 默写
        if re.search(r"[①②③④⑤]", ans_solution) and len(ans_solution) < 80:
            return "dictation"
        # 答案是单一短句 (<30字)、无"答案示例" → 默写
        if ans_solution and len(ans_solution) < 30 and "示例" not in ans_solution:
            return "dictation"
        # 有"赏析""比较""手法""意境""情感"等关键词 → 赏析
        if any(k in ans_solution for k in ["手法", "意境", "情景交融", "渲染", "烘托"]):
            return "appreciation"
        return "subjective_blank"
    # 现代文
    if section == "modern":
        return "comprehension"
    return "subjective_blank"


CN_TYPE_LABEL = {
    "choice": "单选",
    "dictation": "默写",
    "appreciation": "赏析",
    "subjective_blank": "主观填空",
    "comprehension": "简答",
    "correction": "修改病句",
    "argument_analysis": "论证分析",
    "book_review": "名著阅读",
    "essay": "作文",
    "handwriting": "写字",
    "interpretation": "理解",
}


# ─── 答案页解析 ─────────────────────────────────────────────────────────────

# "N.答案:A" / "N.答案示例:..." / "N.答案；略"
# OCR 偶把 `:` 识别为 `;` / `；` / `。`，统一兼容
_ANSWER_HEAD_RE = re.compile(
    r"^\s*(\d{1,2})\s*[.、．。]\s*答案(?:示例|要点)?\s*[:：;；]\s*(.*)$",
    re.MULTILINE)
# **fallback**: 紧凑格式 "N.X"（无 "答案:" 字样，如 fangshan "13.D" / "14.C"）
# 仅当 X 是单字母 A-D 或短主观文字才视为答案
_ANSWER_COMPACT_RE = re.compile(
    r"^\s*(\d{1,2})\s*[.、．。]\s*([A-D](?:\s*\(\s*\d+\s*分\s*\))?)\s*$",
    re.MULTILINE)
# **fengtai/部分区格式**: "N.(N分)X" 形式（无 "答案:" 关键字，分值在前）
_ANSWER_SCORED_RE = re.compile(
    r"^\s*(\d{1,2})\s*[.、．。]\s*[\(（]\s*(?:共\s*)?\d+(?:\.\d+)?\s*分[\)）]\s*(.*)$",
    re.MULTILINE)
# **海淀/古诗文默写格式**: "N.<plain text>"（无 "答案:" 无分值括号）
# 仅在 a_text（答案页）内启用以避免与 stem 混淆
_ANSWER_PLAIN_RE = re.compile(
    r"^\s*(\d{1,2})\s*[.、．。]\s*([^\s\(（].+)$",
    re.MULTILINE)
# 大题标题 — 用作 answer body 切割边界（防答案 bleed 到下一大题）
_BIG_SECTION_RE = re.compile(r"^\s*[一二三四五]\s*[、.]\s*", re.MULTILINE)
# 子部分标题（(一)/(二)/(三)）— 答案页里出现的子段总分行
# 例 "(三)阅读《桃花源记》，完成13-15题。(共7分)" — Q12 的 body 不能含它（否则 score=7）
_SUB_SECTION_RE = re.compile(
    r"^\s*[\(（][一二三四五][\)）]\s*(?:[\(（]?\s*共?\s*\d+\s*分|阅读|默写|名著)",
    re.MULTILINE)
# 卷首页噪声 — answer body 越过末尾后会捞到 basic OCR 的卷首页内容（"学校 班级 姓名"）
# 在这里截断
_COVER_BOUNDARY_RE = re.compile(
    r"^\s*(?:北京市|考生须知|学校\s+班级|本试卷共|九年级综合练习)",
    re.MULTILINE)
# 评分括号 "(2分)" / "(共3分。每空1分)" — 单独一行或紧跟答案末尾
_SCORE_RE = re.compile(r"[\(（]\s*(?:共\s*)?(\d+(?:\.\d+)?)\s*分(?:[。\.，,；;][^)）]*)?\s*[\)）]")


# 表格答案 — OCR 把 "题号 1 2 3 答案 B A C" 这种横向表格按列读成纵向
# 形如:
#   题号
#   2
#   3
#   答案
#   B
#   A
# → {2:B, 3:A}（dongcheng 区）
def _parse_answer_table(answer_text: str) -> dict[int, str]:
    """OCR 把表格按列读成纵向时的兜底解析。返回 {n: letter}。"""
    out: dict[int, str] = {}
    lines = [l.rstrip() for l in answer_text.split("\n")]
    i = 0
    while i < len(lines):
        if lines[i].strip() == "题号":
            j = i + 1
            nums: list[int] = []
            while j < len(lines) and lines[j].strip().isdigit():
                nums.append(int(lines[j].strip())); j += 1
            if j < len(lines) and lines[j].strip() in ("答案", "答案:"):
                k = j + 1
                ans: list[str] = []
                while k < len(lines) and re.fullmatch(r"\s*[A-D]\s*", lines[k]):
                    ans.append(lines[k].strip()); k += 1
                if nums and len(nums) == len(ans):
                    for n, a in zip(nums, ans):
                        if 1 <= n <= 28: out[n] = a
            i = j
        i += 1
    return out


def _parse_answers(answer_text: str) -> list[dict]:
    """解析答案页：N.答案:[内容] + (N分) 评分行。

    选择题 sol = "A"，主观题 sol = 大段文字。
    correct 字段仅当 sol 是 A-D 时填，其余为空（主观题无 correct）。
    """
    # 0. 表格选择题答案（dongcheng）
    table_choices = _parse_answer_table(answer_text)
    # 找所有 N.答案 头位置 + 多种 fallback
    heads_main = list(_ANSWER_HEAD_RE.finditer(answer_text))
    heads_compact = list(_ANSWER_COMPACT_RE.finditer(answer_text))
    heads_scored = list(_ANSWER_SCORED_RE.finditer(answer_text))
    heads_plain = list(_ANSWER_PLAIN_RE.finditer(answer_text))
    # 合并：去重，按位置排序。优先级 main > scored > compact > plain
    seen_qids: set[int] = set()
    heads: list[re.Match] = []
    for hlist in (heads_main, heads_scored, heads_compact, heads_plain):
        for h in hlist:
            qid = int(h.group(1))
            if qid in seen_qids: continue
            if not (1 <= qid <= 28): continue
            heads.append(h); seen_qids.add(qid)
    heads.sort(key=lambda h: h.start())
    # **boundary anchor**：含所有 RE 的 head（不去重），用于切 tail
    # 解决 dual-OCR Q8 head 来自 basic 末尾，body 吞所有后续题答案的 bug
    # (chaoyang R2 Q8 sol 焊 Q9/Q10 答案剧透 P0 根因)
    all_boundary = sorted(
        set(h.start() for hlist in (heads_main, heads_scored, heads_compact, heads_plain)
            for h in hlist if 1 <= int(h.group(1)) <= 28),
    )
    out: list[dict] = []
    for i, m in enumerate(heads):
        n = int(m.group(1))
        # body = 首行剩余内容(group 2) + 后续行直到任何题号 anchor OR 下一大题
        first_line_rest = (m.group(2) or "").strip()
        # 下一个 boundary：任何引擎抓到的题号位置（不含本 head 自己）
        next_boundary = next((b for b in all_boundary if b > m.end()), len(answer_text))
        next_start = min(next_boundary,
                          heads[i+1].start() if i+1 < len(heads) else len(answer_text))
        tail = answer_text[m.end():next_start]
        # **关键**：tail 含下一大题标题（"二、古诗文"）时截断，避免 bleed
        sec_m = _BIG_SECTION_RE.search(tail)
        if sec_m:
            tail = tail[:sec_m.start()]
        # 子段标题（(一)/(二)/(三)）— 含 "(共N分)" 的子段总分，会被误识别为本题分值
        sub_m = _SUB_SECTION_RE.search(tail)
        if sub_m:
            tail = tail[:sub_m.start()]
        # 卷首页噪声截断（dual-OCR 把 cover page 内容附加到末尾）
        cov_m = _COVER_BOUNDARY_RE.search(tail)
        if cov_m:
            tail = tail[:cov_m.start()]
        # 拼起来；首行内容 + \n + tail
        body = (first_line_rest + "\n" + tail).strip()
        # 抽分值：取**第一个** (N分) 或 (共N分)（总分）—— 避免取到子项的细分（"2分;1分"）
        # 优先匹配 (共N分) 形式
        m_gross = re.search(r"[\(（]\s*共\s*(\d+(?:\.\d+)?)\s*分", body)
        if m_gross:
            score = float(m_gross.group(1))
        else:
            m_first = _SCORE_RE.search(body)
            score = float(m_first.group(1)) if m_first else None
        # 移除所有评分括号，剩 solution 文字
        sol = _SCORE_RE.sub("", body).strip()
        # correct（仅 A-D）
        first_line = sol.split("\n")[0].strip()
        correct = first_line if re.fullmatch(r"[A-D]", first_line) else ""
        out.append({"number": n, "correct": correct, "solution": sol,
                     "score": score})
    # 合并表格选择题答案（dongcheng）：若 out 没有该题号或 correct 为空 → 用表格答案
    existing = {a["number"]: a for a in out}
    for n, letter in table_choices.items():
        if n in existing:
            if not existing[n].get("correct"):
                existing[n]["correct"] = letter
                if not existing[n].get("solution"): existing[n]["solution"] = letter
        else:
            out.append({"number": n, "correct": letter, "solution": letter,
                         "score": None})
    out.sort(key=lambda a: a["number"])
    return out


# ─── section parsers ────────────────────────────────────────────────────────

# 工具：找"N." 题号锚
def _find_q_anchors(text: str, num_range: range) -> list[re.Match]:
    """跨区通用：忽略静态 num_range，接受 1-27 内所有题号。
    各 section text 已由 _split_sections 预切，section 边界自然把题号分到对应 section。
    朝阳 base=Q1-7 / 昌平 base=Q1-8 / 海淀 classical=Q7-15 / 西城 classical=Q7-15 等差异
    通过 section 文本切片解决，不依赖固定题号区间。"""
    return [m for m in _NUM_HEAD_RE.finditer(text)
            if 1 <= int(m.group(1)) <= 28]


def _insert_blank_marker(stem: str) -> str:
    """语文默写/填空 stem 中 OCR 把横线吞了，按上下文插 ___ 标记。
    模式：
      "落红不是无情物，\n_。" → "落红不是无情物，___。"
      "9.\n，不知口体之奉不若人也" → "___，不知口体之奉不若人也"
      "①.②." → "①___，②___"（编号点占位）
      "(此处)_" 单字符下划线 → "___"
    """
    s = stem
    # 1) 句末标点前的空缺：， 前接 。/！/？/； 之间只有空白/换行 → 插 ___
    s = re.sub(r"([，,])\s*[\n\s_]{0,4}([。！？；])", r"\1___\2", s)
    # 2) 行首孤立的"，"前面缺内容 → "___，"
    s = re.sub(r"(?m)^\s*([，,])", r"___\1", s)
    # 3) 编号"①./②./③..." 转 "①___/②___/③___"
    s = re.sub(r"([①②③④⑤⑥⑦⑧⑨⑩])\s*[.、．]", r"\1___", s)
    # 4) 单字符 "_" 当横线占位（OCR 偶把横线识为单 _）→ ___
    s = re.sub(r"(?<![_a-zA-Z0-9])_(?![_a-zA-Z0-9])", "___", s)
    # 5) 已有"___" 多次连接 → 归一化为单个 ___
    s = re.sub(r"_{3,}", "___", s)
    return s


# **passage q_range anchor 提取**：从 "(一)阅读...完成 N-M 题" 等明示题号
# 范围的子段标题抽真实 q_range，替代靠 sub_text 内题号 min/max（OCR 切分错
# 会把多个 sub 题号挤一起，致 q_range 跨度过大 → passage_id 全表错配）。
# chaoyang R1 报告 P0：non_continuous q_range=[2,25] 错（应 [17,19]）的根因。
_QRANGE_ANCHOR_RE = re.compile(
    r"[\(（][一二三四五][\)）]?\s*(?:[^\n]{0,30})?完成\s*(\d{1,2})\s*[-－]\s*(\d{1,2})\s*题")


def _extract_qrange_anchor(text: str) -> tuple[int, int] | None:
    """从 text 头部抽 '完成 N-M 题' anchor，返回 (N, M)；找不到 None。"""
    m = _QRANGE_ANCHOR_RE.search(text[:500])
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


# 子部分标题（资料一/资料二/.../后记/(一)/(二)等）— stem / option 切到这里就截断
# 二模新增：行程式 sub-header "第一站航天科技体验中心" / "结语致未来探索者"
# 整行作为 sub-section 标题（xicheng-er Q2/Q3/Q4 P0 跨题 bug 根因）。
_SUB_HEADER_BOUNDARY_RE = re.compile(
    r"(?m)^\s*(?:"
    r"资料[一二三四五]"
    r"|后记|卷首语|卷尾语|前言|序言"
    r"|[\(（][一二三四五][\)）]"
    r"|材料[一二三四五]"
    r"|第[一二三四五六七八九十]\s*(?:站|章|部分|节|篇|关|幕)[一-龥A-Za-z0-9（）\(\)]{0,30}"
    r"|(?:结语|导语)[一-龥A-Za-z0-9（）\(\)]{0,30}"
    r"|[甲乙丙丁]\s*[、.]"
    r")\s*$")


def _trim_at_sub_boundary(text: str) -> str:
    """如果 text 中含子部分标题（资料二/材料一/(二)/后记 等），在那截断。
    用于防止 stem 或 option value 越界到下一段 passage。
    """
    m = _SUB_HEADER_BOUNDARY_RE.search(text)
    if m:
        return text[:m.start()].rstrip()
    return text


def _parse_section_generic(text: str, num_range: range, default_type: str,
                            passages: list[dict], questions: list[dict],
                            section_label: str):
    """通用 section parser：按题号切 chunk，抽 stem + options（若有选项）。
    passage 抽取由 caller 单独处理（语文 passage 太多样）。
    """
    anchors = _find_q_anchors(text, num_range)
    if not anchors: return
    for i, m in enumerate(anchors):
        n = int(m.group(1))
        end = anchors[i+1].start() if i+1 < len(anchors) else len(text)
        chunk = text[m.start():end]
        # **关键修复**：chunk 内若含 sub-header（资料二/后记等），在此截断
        # 防止 stem/options bleed 到下一段 passage 内容
        chunk = _trim_at_sub_boundary(chunk)
        # 切 stem / options：找第一个 A 选项之前是 stem（支持 A. / A， / A 紧贴中文 / 小写 a.）
        a_pos = re.search(
            r"(?:^|\n)\s*[Aa]\s*(?:[.、．,，]\s*|(?=[一-鿿]))",
            chunk, re.MULTILINE)
        if a_pos:
            stem_part = chunk[:a_pos.start()]
            opts_part = chunk[a_pos.start():]
            # option block 也要在 sub-header 处截断
            opts_part = _trim_at_sub_boundary(opts_part)
            opts = _parse_options_block(opts_part)
        else:
            stem_part, opts = chunk, {}
        stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem_part).strip()
        stem = _strip_footers(stem)
        # 中文 stem 多行合并（解决 Q5/Q6 多余换行问题）
        stem = _join_paragraph_lines(stem)
        # 默写/古诗文 section 特殊：插横线占位
        if section_label == "classical":
            stem = _insert_blank_marker(stem)
        questions.append({
            "number": n, "stem": stem, "options": opts if opts else None,
            "type_hint": default_type, "section": section_label,
        })


# 选项行检测（通用）：行首是 A.X 或 A.X B.X 紧凑格式 / 4 选项 A.X..D.X 单行
# Basic OCR 常输出 "A.琳琅满目B.惟妙惟肖C.别具匠心D.源远流长" 这种紧凑格式
_OPTION_LINE_RES = [
    re.compile(r"^\s*[A-D]\s*[.、．]"),       # 行首 A./B./C./D.（紧凑或带空格都覆盖）
    re.compile(r"^\s*[A-D]\s*[.、．].*[A-D]\s*[.、．]"),  # 同行含 2+ 选项标号（明显是 4 选项紧凑）
]


def _is_option_line(ln: str) -> bool:
    """判断一行是否是选项行（题目选项 A./B./C./D.，不应进入 passage body）。"""
    s = ln.strip()
    if not s: return False
    return any(p.search(s) for p in _OPTION_LINE_RES)


def _parse_base_section(text: str, num_range: range,
                         passages: list[dict], questions: list[dict]):
    """一、基础·运用：按"资料一/资料二/资料三/后记"切多个 sub-passage，
    题目根据位置归到所在的 sub-passage（每个题与最近的前一个资料关联）。
    """
    lines = text.split("\n")
    # 标记资料/后记起始行
    # _SUB_HEADER_RE 匹配 "资料一/二/三/四" / "后记" / "卷首语" 等子部分标题
    sub_header_re = re.compile(r"^\s*(资料[一二三四五]|后记|卷首语|卷尾语|前言|序言)\s*$")
    sub_starts: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = sub_header_re.match(ln)
        if m:
            sub_starts.append((i, m.group(1)))

    anchors = _find_q_anchors(text, num_range)
    anchor_lines = {}  # {line_idx: question_num}
    for a in anchors:
        # 找 anchor 在 lines 中的行号
        pos = a.start()
        cur = 0
        for li, ln in enumerate(lines):
            nxt = cur + len(ln) + 1
            if cur <= pos < nxt:
                anchor_lines[li] = int(a.group(1)); break
            cur = nxt

    if sub_starts:
        # 按子部分切 passages
        for k, (si, name) in enumerate(sub_starts):
            end_i = sub_starts[k+1][0] if k+1 < len(sub_starts) else len(lines)
            # passage body：si 之后到 end_i 之间，跳题号行 + 选项行 + 大题标题
            body_lines = []
            for li in range(si + 1, end_i):
                ln_s = lines[li].strip()
                if not ln_s: continue
                m = _NUM_HEAD_RE.match(lines[li])
                if m and int(m.group(1)) in num_range: continue
                # **通用 fix**：跳过所有选项行（含 Basic OCR 紧凑格式 "A.XB.YC.ZD.W"）
                if _is_option_line(ln_s): continue
                body_lines.append(ln_s)
            body = _join_paragraph_lines("\n".join(body_lines)).strip()
            if not body: continue
            # 此 sub 关联的题号：si..end_i 之间的 anchor
            sub_qs = sorted(qn for li, qn in anchor_lines.items()
                             if si < li < end_i)
            if not sub_qs:
                # 如果题在下一段开始前，把后段第一题也归过来（题穿插模式）
                next_qs = sorted(qn for li, qn in anchor_lines.items() if li >= end_i)
                if next_qs:
                    sub_qs = [next_qs[0]]
            pid = f"base_{name}"
            passages.append({
                "id": pid, "type": "base",
                "name": name,  # 中文名 "资料一" / "后记"
                "q_range": [min(sub_qs), max(sub_qs)] if sub_qs else None,
                "body": body[:3000],
            })
    else:
        # fallback: 单一 passage
        body_lines = []
        for ln in lines:
            ln_s = ln.strip()
            if not ln_s: continue
            m = _NUM_HEAD_RE.match(ln)
            if m and int(m.group(1)) in num_range: continue
            if _is_option_line(ln_s): continue
            if re.match(r"^\s*一、", ln_s): continue
            body_lines.append(ln_s)
        body = _join_paragraph_lines("\n".join(body_lines)).strip()
        if body:
            q_nums = [int(a.group(1)) for a in anchors]
            passages.append({
                "id": "base_intro", "type": "base",
                "q_range": [min(q_nums), max(q_nums)],
                "body": body[:3000],
            })
    _parse_section_generic(text, num_range, "subjective_blank",
                            passages, questions, "base")


def _parse_classical_section(text: str, num_range: range,
                              passages: list[dict], questions: list[dict]):
    """二、古诗文：3 子部分。**默写无 passage，古诗/文言文有 passage**。"""
    # 子部分按 "(一)" "(二)" "(三)" 切
    lines = text.split("\n")
    sub_starts = []
    for i, ln in enumerate(lines):
        if re.match(r"^\s*[\(（][一二三四五][\)）]", ln):
            sub_starts.append(i)
    if not sub_starts:
        # fallback：全 section 作 1 个 passage
        _parse_section_generic(text, num_range, "subjective_blank",
                                passages, questions, "classical")
        return
    for k, si in enumerate(sub_starts):
        end_i = sub_starts[k+1] if k+1 < len(sub_starts) else len(lines)
        sub_text = "\n".join(lines[si:end_i])
        sub_anchors = _find_q_anchors(sub_text, num_range)
        if not sub_anchors: continue
        # passage body = sub_text 中题号 anchor 之前的部分（含子部分标题外）
        body = sub_text[:sub_anchors[0].start()]
        # 清子部分标题
        body = re.sub(r"^\s*[\(（][一二三四五][\)）][^\n]*", "", body).strip()
        body = _join_paragraph_lines(_strip_footers(body))
        if body and len(body) > 10:
            q_nums = [int(a.group(1)) for a in sub_anchors]
            # **优先用 "完成 N-M 题" anchor**（更稳；防 OCR 切错 sub 致跨度大）
            anchor_range = _extract_qrange_anchor(sub_text)
            qr = list(anchor_range) if anchor_range else [min(q_nums), max(q_nums)]
            pid = f"classical_{k+1}"
            passages.append({
                "id": pid, "type": "classical",
                "q_range": qr,
                "body": body[:2000],
            })
        _parse_section_generic(sub_text, num_range, "subjective_blank",
                                passages, questions, "classical")


def _parse_book_review_section(text: str, num_range: range,
                                passages: list[dict], questions: list[dict]):
    """三、名著阅读：1 题（可能含表格）。无独立 passage（stem 自含）。"""
    _parse_section_generic(text, num_range, "book_review",
                            passages, questions, "book_review")


def _parse_modern_section(text: str, num_range: range,
                           passages: list[dict], questions: list[dict]):
    """四、现代文：3 篇（非连/记叙/议论）。每篇 1 passage。"""
    lines = text.split("\n")
    sub_starts = []
    for i, ln in enumerate(lines):
        if re.match(r"^\s*[\(（][一二三四五][\)）]", ln):
            sub_starts.append(i)
    if not sub_starts:
        _parse_section_generic(text, num_range, "comprehension",
                                passages, questions, "modern")
        return
    for k, si in enumerate(sub_starts):
        end_i = sub_starts[k+1] if k+1 < len(sub_starts) else len(lines)
        sub_text = "\n".join(lines[si:end_i])
        sub_anchors = _find_q_anchors(sub_text, num_range)
        if not sub_anchors: continue
        body = sub_text[:sub_anchors[0].start()]
        body = re.sub(r"^\s*[\(（][一二三四五][\)）][^\n]*", "", body).strip()
        body = _join_paragraph_lines(_strip_footers(body))
        if body:
            q_nums = [int(a.group(1)) for a in sub_anchors]
            pid_type = ["non_continuous", "narrative", "argument"][k] if k < 3 else f"modern_{k+1}"
            # **优先用 "完成 N-M 题" anchor**（防 OCR 切错 sub 致跨度大；
            # chaoyang R1 P0：non_continuous q_range=[2,25] 应 [17,19]）
            anchor_range = _extract_qrange_anchor(sub_text)
            qr = list(anchor_range) if anchor_range else [min(q_nums), max(q_nums)]
            passages.append({
                "id": pid_type, "type": pid_type,
                "q_range": qr,
                "body": body[:5000],
            })
        _parse_section_generic(sub_text, num_range, "comprehension",
                                passages, questions, "modern")


def _parse_essay_section(text: str, num_range: range, questions: list[dict]):
    """五、作文：1 题（27），2 选 1。stem 较长，需合并 OCR 跨行换行。"""
    anchors = _find_q_anchors(text, num_range)
    if anchors:
        m = anchors[0]
        stem = text[m.start():].strip()
        stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem)
        stem = _strip_footers(stem)
        # 合并 OCR 跨行换行（段落以"(1)"/"(2)"/"要求"开头处保留分段）
        stem = _join_paragraph_lines(stem)
        questions.append({
            "number": int(m.group(1)), "stem": stem, "options": None,
            "type_hint": "essay", "section": "essay",
        })


# ─── 主流程 ──────────────────────────────────────────────────────────────────

def parse_paper(src: Path, out_dir: Path, force=False) -> dict:
    images_dir = src / "images"
    pages = sorted(images_dir.glob("page-*.png"))
    if not pages:
        sys.exit(f"无 images: {images_dir}")
    cache_dir = out_dir / "tencent-cache" / "general"
    basic_cache = out_dir / "tencent-cache" / "basic"

    # 1. OCR 全页
    full_text = ""
    page_texts = []
    for p in pages:
        t = _ocr_page(p, cache_dir / f"{p.stem}.txt", force)
        page_texts.append((p, t))
        full_text += "\n" + t

    # 1.5 **题目页和答案页都 dual-OCR with Basic**
    # 语文与英语不同：题目页也常有 OCR 短行漏读（默写题、横线占位行等）
    # 下游 dedupe by num 取 stem 更长的，避免重复
    sup_all = []
    for p, _ in page_texts:
        bs = _ocr_page_basic_supplement(p, basic_cache, force)
        if bs: sup_all.append(bs)
    if sup_all:
        full_text += "\n" + "\n".join(sup_all)

    # 2. 切题目页 vs 答案页
    # **跨区通用**：优先用 ANSWER_MARKER；若不命中（如大兴答案页只有 "三、名著阅读"
    # 而无 "参考答案" 头），fallback 到答案密集区检测 —— 找 _ANSWER_HEAD_RE 头出现
    # >= 3 次后的最早一处作为 a_text 起点。
    am = ANSWER_MARKER.search(full_text)
    answer_start = am.start() if am else None
    if answer_start is None:
        ans_heads = list(_ANSWER_HEAD_RE.finditer(full_text))
        if len(ans_heads) >= 3:
            answer_start = ans_heads[0].start()
            print(f"[chinese_image_paper] ⚠ ANSWER_MARKER 未命中，"
                  f"fallback 用首个 N.答案 位置作为答案起点（共 {len(ans_heads)} 处）")
    if answer_start is not None:
        line_start = full_text.rfind("\n", 0, answer_start) + 1
        before = full_text[:line_start].rstrip("\n")
        before_lines = before.split("\n")
        _cover_re = re.compile(
            r"^\s*(?:(?:北京市?\s*)?[一-龥]{1,8}区[一-龥0-9\s\-]{0,30}"
            r"(?:练习|考试|测试)?|语文试卷|20\d{2}[.\-/]\d{1,2})\s*$")
        while before_lines and (
            not before_lines[-1].strip() or _cover_re.match(before_lines[-1])
        ):
            before_lines.pop()
        q_text = "\n".join(before_lines)
        a_text = full_text[line_start:]
    else:
        q_text = full_text
        a_text = ""

    # 3. 切 5 大题
    sec = _split_sections(q_text)
    passages: list[dict] = []
    questions: list[dict] = []
    sec_by_typ = {typ: (r, ts) for _, r, typ, ts in SECTIONS}

    if "base" in sec:
        rng, _ = sec_by_typ["base"]
        _parse_base_section(sec["base"], rng, passages, questions)
    if "classical" in sec:
        rng, _ = sec_by_typ["classical"]
        _parse_classical_section(sec["classical"], rng, passages, questions)
    if "book_review" in sec:
        rng, _ = sec_by_typ["book_review"]
        _parse_book_review_section(sec["book_review"], rng, passages, questions)
    if "modern" in sec:
        rng, _ = sec_by_typ["modern"]
        _parse_modern_section(sec["modern"], rng, passages, questions)
    if "essay" in sec:
        rng, _ = sec_by_typ["essay"]
        _parse_essay_section(sec["essay"], rng, questions)

    # 3.5 **dedupe questions by num**（dual-OCR 可能创建多份同号题，取 stem 更长的）
    questions_by_num: dict[int, dict] = {}
    for q in questions:
        n = q["number"]
        if n not in questions_by_num:
            questions_by_num[n] = q
        else:
            cur = questions_by_num[n]
            # stem 更长（含信息多）的胜出；options 非空更优先
            score_new = len(q.get("stem","") or "") + (100 if q.get("options") else 0)
            score_cur = len(cur.get("stem","") or "") + (100 if cur.get("options") else 0)
            if score_new > score_cur:
                questions_by_num[n] = q
    questions = sorted(questions_by_num.values(), key=lambda q: q["number"])

    # 4. 答案 + 分值合并到题
    answers = _parse_answers(a_text)
    ans_by_num: dict[int, dict] = {}
    for a in answers:
        n = a["number"]
        if n not in ans_by_num or (a.get("correct") and not ans_by_num[n].get("correct")):
            ans_by_num[n] = a
    for q in questions:
        n = q["number"]
        a = ans_by_num.get(n, {})
        q["answer"] = a.get("correct", "")
        q["solution"] = a.get("solution", "")
        # 分值：答案页带的优先；否则用 DEFAULT_QSCORE
        # 推断 type 先做，以便 score sanity check 用得上
        q["type"] = _infer_qtype(n, q.get("section",""),
                                   q["answer"], q["solution"],
                                   q.get("options"))
        parsed_score = a.get("score")
        default_score = DEFAULT_QSCORE.get(n, 0)
        # **作文 Q27 永远 40 分**（北京 13 区都一致）—— 避免 OCR 把
        # "27.评分标准 (36分) ... 4分 ..." 误识别为 36/13/4
        if q["type"] == "essay":
            q["score"] = 40
        # **选择题最多 3 分**（北京中考语文标准每题 1-2 分；超过明显是误识别）
        elif q["type"] == "choice" and parsed_score and parsed_score > 3:
            q["score"] = default_score or 2
        # **非作文最多 5 分**（北京中考语文单题最大 5 分，超过通常是 section 总分误识别）
        elif parsed_score and parsed_score > 8 and q["type"] != "essay":
            q["score"] = default_score or parsed_score
        else:
            q["score"] = parsed_score or default_score
        # 修改病句类题（如 Q4），stem 末尾加注：答案是修改后的句子，原画线句需对照原图
        stem_str = q.get("stem","") or ""
        if "画线句" in stem_str and "修改" in stem_str and q["solution"]:
            q["stem"] = stem_str + "\n\n[画线句修改后参考: " + q["solution"][:80] + "]"

    full_score = sum(q.get("score", 0) for q in questions) or None

    # 5. **自动图表裁剪**（对 non_continuous / 含"图N"的 passage）
    slug = out_dir.name
    print(f"[chinese_image_paper] 🔍 auto_crop scan: {len(passages)} passages", flush=True)
    n_cropped = _auto_crop_figures_for_passages(passages, page_texts, out_dir, slug)
    if n_cropped:
        print(f"[chinese_image_paper] ✅ 自动裁出 {n_cropped} 张 passage 图表", flush=True)
    else:
        print(f"[chinese_image_paper]   （未触发自动裁图）", flush=True)

    # **元数据从 slug 反推 + 封面 OCR 校验**（chaoyang R1 P1：
    # final.json 没 year/district/exam_type → enrich 写 yaml 是 null/''/真题）
    slug = out_dir.name
    m_slug = re.match(r"(\d{4})-(.+?)-(\w+)", slug)
    year = int(m_slug.group(1)) if m_slug else None
    region_slug = m_slug.group(2) if m_slug else ""
    typ_slug = m_slug.group(3) if m_slug else ""
    region_cn = {"chaoyang":"朝阳","haidian":"海淀","mentougou":"门头沟",
                  "fengtai":"丰台","xicheng":"西城","dongcheng":"东城",
                  "shijingshan":"石景山","tongzhou":"通州","shunyi":"顺义",
                  "changping":"昌平","daxing":"大兴","fangshan":"房山",
                  "pinggu":"平谷","huairou":"怀柔","miyun":"密云",
                  "yanqing":"延庆","yanshan":"燕山"}.get(region_slug, region_slug)
    type_cn = {"yi":"一模","er":"二模","san":"三模","zhen":"真题"}.get(typ_slug, "一模")

    result = {
        "subject": "chinese",
        "year": year,
        "district": (region_cn + "区") if region_cn else "",
        "exam_type": type_cn,
        "full_score": full_score,
        "duration_minutes": 150,  # 北京中考语文标准时长（下游 enrich 透传到 yaml）
        "passages": passages,
        "questions": questions,
        "answers": answers,
    }
    _self_check(result)
    return result


# ─── 自检 ────────────────────────────────────────────────────────────────────

_EXPECTED_FULL_SCORE = 100


def _self_check(result: dict) -> None:
    qs = result.get("questions", [])
    passages = result.get("passages", [])
    nums_have = sorted(q["number"] for q in qs)
    fatal: list[str] = []
    warn: list[str] = []

    # 题数应 ≥ 22（北京中考语文 23-27 之间；东城 23 / 海淀 26 / 其他多为 27）
    if len(qs) < 22:
        fatal.append(f"题数 {len(qs)} < 22（最少 22 题）")
    elif len(qs) < 25:
        warn.append(f"题数 {len(qs)} 偏少（北京标准 25-27 题，部分区如东城 23）")
    # 题号连续性
    if nums_have:
        gaps = [n for n in range(nums_have[0], nums_have[-1]+1) if n not in nums_have]
        if gaps:
            warn.append(f"题号不连续，缺 {gaps}")
    # 分值
    actual = result.get("full_score") or 0
    if abs(actual - _EXPECTED_FULL_SCORE) > 5:
        warn.append(f"分值 {actual} ≠ 期望 ~100（差 >5）")
    # 选择题答案空
    for q in qs:
        t = q.get("type", "")
        if t == "choice" and not q.get("answer"):
            fatal.append(f"Q{q['number']}(choice) 答案空")
    # 残留页面噪声
    for q in qs:
        s = q.get("stem","") or ""
        if "共10页" in s or "共11页" in s or re.search(r"北京市[一-龥]+区[一-龥]+练习", s):
            fatal.append(f"Q{q['number']} stem 含页面噪声: {s[-60:]!r}")

    if fatal:
        print("\n❌ 自检失败：", file=sys.stderr)
        for f in fatal: print(f"   - {f}", file=sys.stderr)
    if warn:
        print("\n⚠️  自检告警：", file=sys.stderr)
        for w in warn: print(f"   - {w}", file=sys.stderr)
    if not fatal and not warn:
        print(f"✅ parse 自检全通过（{len(qs)} 题 / {actual} 分）", flush=True)


# ─── yaml writer ────────────────────────────────────────────────────────────

def _apply_patches_to_result(patches: dict, result: dict) -> int:
    """对 result（final.json 结构，questions 用 `number` 字段）应用 patches。
    这保证 patches 也进 final.json，下游 enrich 能看到（包括 create 的新题）。
    返回应用的 patch 数。
    """
    n_applied = 0
    # passages（**bug 修**：支持 explicit body 覆盖 + q_range 修正）
    ps_patches = patches.get("passages") or {}
    for pid, patch in ps_patches.items():
        # **create**: passage 不存在则新建（chaoyang R2 缺整篇 argument passage）
        if patch.get("create"):
            existing = next((ps for ps in result.get("passages", []) if ps["id"] == pid), None)
            if existing is None:
                result.setdefault("passages", []).append({
                    "id": pid,
                    "type": patch.get("type", pid),
                    "q_range": patch.get("q_range") or [1, 1],
                    "body": patch.get("body", ""),
                    "figure": patch.get("figure"),
                })
                n_applied += 1
                continue
        for ps in result.get("passages", []):
            if ps["id"] != pid: continue
            for rep in patch.get("body_replace") or []:
                if rep.get("from") and rep["from"] in ps.get("body",""):
                    ps["body"] = ps["body"].replace(rep["from"], rep.get("to",""))
                    n_applied += 1
            if patch.get("body_append"):
                ps["body"] = (ps.get("body","") + patch["body_append"]); n_applied += 1
            if "figure" in patch:
                ps["figure"] = patch["figure"]; n_applied += 1
            if "body" in patch:  # explicit body 覆盖（含空串清空）
                ps["body"] = patch["body"]; n_applied += 1
            if "q_range" in patch:  # 修正错的 q_range
                ps["q_range"] = patch["q_range"]; n_applied += 1
            if "type" in patch:
                ps["type"] = patch["type"]; n_applied += 1
            break
    # questions（按 number 字段在 result["questions"] 找）
    q_patches = patches.get("questions") or {}
    for qid_raw, patch in q_patches.items():
        qid = int(qid_raw)
        target = next((q for q in result["questions"] if q["number"] == qid), None)
        if target is None and patch.get("create"):
            new_q = {
                "number": qid,
                "type": patch.get("type", "subjective_blank"),
                "stem": patch.get("stem", ""),
                "options": patch.get("options"),
                "answer": patch.get("answer", ""),
                "solution": patch.get("solution", ""),
                "score": patch.get("score", 0),
                "section": patch.get("section", ""),
            }
            insert_at = next((i for i, q in enumerate(result["questions"])
                              if q["number"] > qid), len(result["questions"]))
            result["questions"].insert(insert_at, new_q)
            n_applied += 1
            continue
        if target is None: continue
        q = target
        # **bug 修**：用 'in patch' 区分 missing vs explicit null/空串，
        # 否则 'options: null' / 'solution: ""' 这种清空 patch 失效
        if "stem" in patch:
            q["stem"] = patch["stem"]; n_applied += 1
        if patch.get("stem_append"):
            q["stem"] = q.get("stem","") + patch["stem_append"]; n_applied += 1
        if "options" in patch:
            q["options"] = patch["options"]; n_applied += 1
        if "solution" in patch:
            q["solution"] = patch["solution"]; n_applied += 1
            # **bug 修**：同步改 answers[].solution（enrich 真正读这里）
            ans = next((a for a in result.get("answers", []) if a.get("number") == qid), None)
            if ans is not None:
                ans["solution"] = patch["solution"]
        if "answer" in patch:
            q["answer"] = patch["answer"]; n_applied += 1
            ans = next((a for a in result.get("answers", []) if a.get("number") == qid), None)
            if ans is not None:
                ans["correct"] = patch["answer"]
        if patch.get("type"):
            q["type"] = patch["type"]; n_applied += 1
        if "score" in patch:
            q["score"] = patch["score"]; n_applied += 1
    # 重算 full_score
    if n_applied:
        result["full_score"] = sum(q.get("score", 0) or 0 for q in result["questions"])
    return n_applied


def _apply_patches(patches: dict, result: dict, yaml_questions: list[dict]) -> int:
    """通用 patches 应用器（yaml 层）。schema 见 _patches/chinese/*.yaml 注释。
    返回应用的 patch 数。
    """
    n = 0
    # passage patches（**bug 修**：支持 create + q_range + explicit body 覆盖）
    ps_patches = patches.get("passages") or {}
    for pid, patch in ps_patches.items():
        if patch.get("create"):
            existing = next((ps for ps in result.get("passages", []) if ps["id"] == pid), None)
            if existing is None:
                result.setdefault("passages", []).append({
                    "id": pid,
                    "type": patch.get("type", pid),
                    "q_range": patch.get("q_range") or [1, 1],
                    "body": patch.get("body", ""),
                    "figure": patch.get("figure"),
                })
                n += 1
                continue
        for ps in result.get("passages", []):
            if ps["id"] != pid: continue
            for rep in patch.get("body_replace") or []:
                if rep.get("from") and rep["from"] in ps.get("body",""):
                    ps["body"] = ps["body"].replace(rep["from"], rep.get("to",""))
                    n += 1
            if patch.get("body_append"):
                ps["body"] = (ps.get("body","") + patch["body_append"]); n += 1
            if "figure" in patch:
                ps["figure"] = patch["figure"]; n += 1
            if "body" in patch:  # explicit body 覆盖（含空串清空）
                ps["body"] = patch["body"]; n += 1
            if "q_range" in patch:
                ps["q_range"] = patch["q_range"]; n += 1
            if "type" in patch:
                ps["type"] = patch["type"]; n += 1
            break
    # question patches（按 id 在 yaml_questions 中找）
    q_patches = patches.get("questions") or {}
    for qid_raw, patch in q_patches.items():
        qid = int(qid_raw)
        target = next((q for q in yaml_questions if q["id"] == qid), None)
        # **create**: 题号缺失（如 yanqing Q21 OCR 错乱漏题）→ 新建一题插入
        if target is None and patch.get("create"):
            new_q = {
                "id": qid,
                "type": patch.get("type", "subjective_blank"),
                "stem": patch.get("stem", ""),
                "options": patch.get("options"),
                "answer": patch.get("answer", ""),
                "solution": patch.get("solution", ""),
                "score": patch.get("score", 0),
                "section": patch.get("section", ""),
                "qc_status": "needs_review",
                "qc_note": "patch-created（OCR 漏题，手动补入）",
            }
            insert_at = next((i for i, q in enumerate(yaml_questions)
                              if q["id"] > qid), len(yaml_questions))
            yaml_questions.insert(insert_at, new_q)
            n += 1
            continue
        if target is None: continue
        q = target
        # **bug 修**：用 'in patch' 区分 missing vs explicit null/空串
        if "stem" in patch:
            q["stem"] = patch["stem"]; n += 1
        if patch.get("stem_append"):
            q["stem"] = q.get("stem","") + patch["stem_append"]; n += 1
        if "options" in patch:
            q["options"] = patch["options"]; n += 1
        if "solution" in patch:
            q["solution"] = patch["solution"]; n += 1
        if "answer" in patch:
            q["answer"] = patch["answer"]; n += 1
        if patch.get("type"):
            q["type"] = patch["type"]; n += 1
        if "score" in patch:
            q["score"] = patch["score"]; n += 1
        # **bug 修**：passage_id 也要支持 patch
        if "passage_id" in patch:
            q["passage_id"] = patch["passage_id"]; n += 1
    return n


def _write_yaml(result: dict, src: Path, out_dir: Path) -> None:
    try:
        import yaml as Y
    except ImportError:
        print("(skip yaml: PyYAML 未装)"); return
    slug = out_dir.name
    m = re.match(r"(\d{4})-(.+?)-(\w+)", slug)
    year = int(m.group(1)) if m else None
    region_slug = m.group(2) if m else ""
    typ_slug = m.group(3) if m else ""
    region_cn = {"chaoyang":"朝阳","haidian":"海淀","mentougou":"门头沟",
                 "fengtai":"丰台","xicheng":"西城","dongcheng":"东城",
                 "shijingshan":"石景山","tongzhou":"通州","shunyi":"顺义",
                 "changping":"昌平","daxing":"大兴","fangshan":"房山",
                 "pinggu":"平谷","huairou":"怀柔","miyun":"密云",
                 "yanqing":"延庆","yanshan":"燕山"}.get(region_slug, region_slug)
    type_cn = {"yi":"一模","er":"二模","san":"三模","zhen":"真题"}.get(typ_slug,"一模")

    repo_root = out_dir
    while repo_root.parent != repo_root:
        if (repo_root / "knowledge-base").is_dir(): break
        repo_root = repo_root.parent
    yaml_path = (repo_root / "knowledge-base" / "exams" / "mock"
                  / "chinese" / "beijing" / f"{slug}.yaml")
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    # 合并旧 qc_*（沿用英语 / 数学 / enrich 同款规则）
    existing_qc: dict[int, dict] = {}
    if yaml_path.exists():
        try:
            old = Y.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            for q in (old.get("questions") or []):
                qid = q.get("id")
                if qid is None: continue
                existing_qc[qid] = {
                    "qc_status": q.get("qc_status", "draft"),
                    "qc_note":   q.get("qc_note", ""),
                }
        except Exception as e:
            print(f"[chinese_image_paper] ⚠ 读旧 yaml 合并 qc_* 失败: {e}", flush=True)

    yaml_questions = []
    for q in result["questions"]:
        n = q["number"]
        item: dict = {
            "id": n,
            "type": CN_TYPE_LABEL.get(q["type"], q["type"]),
            "score": q.get("score", 0),
            "stem": q.get("stem",""),
        }
        if q.get("options"):
            item["options"] = q["options"]
        if q.get("passage_id"):
            item["passage_id"] = q["passage_id"]
        item["answer"] = q.get("answer","")
        item["solution"] = q.get("solution","")
        item["knowledge_points"] = []
        item["module"] = ""
        item["difficulty"] = ""
        prev = existing_qc.get(n, {})
        item["qc_status"] = prev.get("qc_status","draft")
        item["qc_note"] = prev.get("qc_note","")
        yaml_questions.append(item)

    # passage → 关联 question
    for ps in result.get("passages", []):
        rng = ps.get("q_range")
        if rng:
            for q in yaml_questions:
                if rng[0] <= q["id"] <= rng[1]:
                    q.setdefault("passage_id", ps["id"])

    # **通用 patches 机制**：加载 knowledge-base/exams/_patches/chinese/<slug>.yaml
    # 应用人工修过的 stem / options / solution / passage body 等
    # 每区一份 patch 文件，跨区不影响；重跑 OCR 不丢手修
    patch_path = repo_root / "knowledge-base" / "exams" / "_patches" / "chinese" / f"{slug}.yaml"
    if patch_path.exists():
        try:
            patches = Y.safe_load(patch_path.read_text(encoding="utf-8")) or {}
            applied = _apply_patches(patches, result, yaml_questions)
            if applied:
                print(f"[chinese_image_paper] 🔧 应用 {applied} 处人工 patch（{patch_path.name}）",
                      flush=True)
        except Exception as e:
            print(f"[chinese_image_paper] ⚠ 加载 patch 失败: {e}", flush=True)

    data = {
        "year": year,
        "district": (region_cn + "区") if region_cn else "",
        "exam_type": type_cn, "subject": "chinese",
        "full_score": result.get("full_score"),
        "duration_minutes": 150,
        "total_questions": len(yaml_questions),
        "passages": result.get("passages", []),
        "questions": yaml_questions,
    }
    yaml_path.write_text(
        Y.safe_dump(data, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    print(f"[chinese_image_paper] ✅ yaml {yaml_path}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", type=Path)
    ap.add_argument("--subject", default="chinese")
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
    # **patches 进 final.json**（这样 enrich 也能看到补的题/分数/stem，不会覆盖手修）
    try:
        import yaml as Y
        slug_for_patch = out_dir.name
        patch_path = (Path(__file__).resolve().parent.parent.parent
                      / "knowledge-base" / "exams" / "_patches" / "chinese"
                      / f"{slug_for_patch}.yaml")
        if patch_path.exists():
            patches = Y.safe_load(patch_path.read_text(encoding="utf-8")) or {}
            applied = _apply_patches_to_result(patches, result)
            if applied:
                print(f"[chinese_image_paper] 🔧 final.json 应用 {applied} 处 patch", flush=True)
    except Exception as e:
        print(f"[chinese_image_paper] ⚠ patch 进 final.json 失败: {e}", flush=True)
    fj = structured / "final.json"
    fj.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    qs = result["questions"]
    print(f"[chinese_image_paper] ✅ {fj}", flush=True)
    print(f"   题号: {sorted(q['number'] for q in qs)}", flush=True)
    print(f"   passages: {len(result['passages'])}  questions: {len(qs)}  "
          f"answers: {len(result['answers'])}  full_score: {result['full_score']}",
          flush=True)
    _write_yaml(result, src, out_dir)


if __name__ == "__main__":
    main()
