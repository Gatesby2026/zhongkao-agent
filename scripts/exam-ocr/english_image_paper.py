#!/usr/bin/env python3
"""english_image_paper — 北京中考英语试卷 PNG → final.json（v1 passage 二级模型）。

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
    python3 scripts/exam-ocr/english_image_paper.py \\
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
    # **范围按北京中考英语标准格式**（38 题、60 分）；若区试卷不同，下游
    # 用实际解析到的题号 + 答案 + section 自带分值动态修正，不会卡死在此处。
    # 序号分隔符兼容 `、` 中文顿号 / `.` 英文点（yanshan: "五.文段表达"）
    (re.compile(r"^\s*一[、.]\s*单项填空"),    range(1, 13),  "choice",          0.5),
    (re.compile(r"^\s*二[、.]\s*完形填空"),    range(13, 21), "cloze",           1),
    (re.compile(r"^\s*三[、.]\s*阅读理解"),    range(21, 34), "reading",         2),
    # 四、阅读表达 是 reading_express，区别于 五、文段表达 (essay/作文)
    # 措辞变体: "阅读表达"/"阅读与表达"/"阅读短文"（yanshan）
    (re.compile(r"^\s*四[、.]\s*阅读(?:与表达|表达|短文)"), range(34, 38), "reading_express", None),
    (re.compile(r"^\s*五[、.]\s*文段表达"),    range(38, 39), "essay",           10),
]
# 阅读理解 4 篇按试卷标号 A/B/C/D 命名（(一)=A image-match, (二)=B, (三)=C, (四)=D）
_READING_SUB_LETTERS = ["A", "B", "C", "D", "E", "F"]
# 答案页起始标记：跨区已收集到 10+ 变体，统一用 re alternation 兜底
# - 朝阳: "英语试卷答案及评分参考"
# - 海淀/丰台: "英语参考答案" / "九年级英语参考答案"
# - 平谷: "英语试卷答案"（无评分参考）
# - 西城: "英语答案及评分参考"
# - 通州: "参考答案" 单独行
# - 燕山: "英语试卷答案及评分参考"
# - 房山: "九年级英语参考答案"
# - 昌平: "英语试卷参考答案及评分标准"
# - 大兴: "初三英语期末练习参考答案"
# - 顺义: （格式 TBD）
# - 东城: "英语试卷参考答案及评分参考"
# - 石景山: "英语试卷答案及评分参考"
ANSWER_MARKER = re.compile(
    r"参考答案"
    r"|答案(?:及|与)\s*评分(?:\s*(?:参考|标准))?"
    r"|英语(?:试卷)?\s*答案"
    r"|英语\s*参考答案"
    r"|试卷\s*答案"
    # shunyi 紧凑答案页特征："单选:1-5..." / "完形:13-..."
    # 这些以 `:` 结尾的小节标签只出现在答案页，问题页都是 `(每题X分,共Y分)` 格式
    r"|^\s*(?:单选|完形|阅读理解|阅读表达|文段表达)\s*[:：]",
    re.MULTILINE
)

# 图片配对题（A 篇）识别 —— 多关键词集合，覆盖各区不同措辞：
# - chaoyang/dongcheng: "配最适合的图片"
# - haidian/xicheng: "选择最适宜（合）的图"
# - 通用模式: "图"+"匹配/对应/选择"
_IMG_MATCH_HINTS = [
    "配最适合的图片", "配最适合的图", "选择最适宜", "选择最合适",
    "选出最适合的图", "图片所对应", "饼状图", "柱状图", "条形图",
    "匹配最适合",  # xicheng "匹配最适合他们的课程"
    # 通用兜底：含 "图" + "匹配/对应" 由 _IMG_MATCH_RE 处理
]
# 通用 instruction 模式：
# (1) (A、B、C、D) 带括号字母列表 = 配对题标准措辞（chaoyang/xicheng/...）
# (2) "填在相应位置上" 是配对题独有短语（pinggu "A、B、C、D选项填在相应位置上"）
#    区别于正文 "A、B、C、D 四个选项中,选择最佳选项"
_IMG_MATCH_RE = re.compile(
    r"图[^\n]{0,20}(?:匹配|对应|相应位置)"
    r"|(?:匹配|对应)[^\n]{0,10}图"
    r"|[\(（]\s*A\s*[、，,]\s*B\s*[、，,]\s*C\s*[、，,]\s*D\s*[\)）]"
    r"|填在\s*相应\s*的?\s*位置"  # "相应位置上" / "相应的位置上" (pinggu)
)


def _is_image_match_section(text: str) -> bool:
    """是否为图片配对题（多证据法 - 各区措辞不同时仍能识别）。

    跨区已验证：
    - chaoyang: "配最适合的图片"
    - haidian: "饼状图...将该主题对应的选项(A、B、C、D)填在相应位置"
    """
    if any(h in text for h in _IMG_MATCH_HINTS):
        return True
    if _IMG_MATCH_RE.search(text):
        return True
    return False

# **阅读表达分值动态解析**：从 section 标题 "(第34-36题每题2分，第37题4分，共10分)"
# 抽出 per-question score。各区可能不同（chaoyang: 2/2/2/4，其他区可能 3/3/2/2 等）。
# pinggu: "34-36题每题2分,37题4分" (无 "第" 前缀)
# chaoyang/haidian: "第34-36题每题2分，第37题4分" (含 "第")
# 兼容两种写法
_EXPRESS_SCORE_RE = re.compile(
    r"(?:第)?(\d+)(?:[-–~](\d+))?题\s*(?:每题)?\s*(\d+(?:\.\d+)?)\s*分")


def _parse_express_scores(section_header_text: str) -> dict[int, float]:
    """从 '四、阅读表达(第34-36题每题2分，第37题4分)' 抽 {q_num: score}。
    解析失败返回空 dict（caller fallback 到默认 2 分）。
    """
    out: dict[int, float] = {}
    for m in _EXPRESS_SCORE_RE.finditer(section_header_text):
        n1 = int(m.group(1))
        n2 = int(m.group(2)) if m.group(2) else n1
        score = float(m.group(3))
        for q in range(n1, n2 + 1):
            out[q] = score
    return out

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


# ─── 图片选项裁剪（qwen-vl-max 定位 4 张图选项的 bbox + PIL 裁剪）────────

_CROP_PROMPT = """这是北京中考英语试卷「图片配对题」所在的整页。

页面上有 4 张图片选项，旁边各有字母标号 A、B、C、D。它们通常排成：
  - 2×2 网格（A B 在上一排，C D 在下一排），或
  - 1×4 横排，或
  - 4×1 竖排

请精确给出 **每张图本身（含图周围少量留白即可）** 的 bbox 百分比坐标。
**bbox 必须包含完整的图片内容**（不要只框一小部分）；可以带上字母标号一起框。
4 张图通常 **大小相近**（误差 < 30%）。

坐标说明：左上角为原点 (0,0)，整页右下角为 (100,100)。
x1<x2，y1<y2。每张图的 bbox 宽度通常 30–50%，高度通常 15–25%。

输出 JSON：
{"options": [
  {"label": "A", "x1": 5.0, "y1": 55.0, "x2": 50.0, "y2": 75.0},
  {"label": "B", "x1": 50.0, "y1": 55.0, "x2": 95.0, "y2": 75.0},
  {"label": "C", "x1": 5.0, "y1": 75.0, "x2": 50.0, "y2": 95.0},
  {"label": "D", "x1": 50.0, "y1": 75.0, "x2": 95.0, "y2": 95.0}
]}

要求：必须返回 ABCD 全部 4 张；坐标必须覆盖完整图片；只输出 JSON。"""


def _crop_image_options(page_img: Path, out_dir: Path, prefix: str) -> dict[str, str]:
    """qwen-vl-max 定位 4 张图选项 bbox → PIL 裁。返回 {A: rel_path, ...}。

    后处理校验：bbox 宽度过窄（<15% 页宽）或 4 图尺寸差异 >50% → 视为失败，
    打印告警让人工 review（避免之前 D 选项裁错的盲点）。
    """
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        print(f"[english_image_paper] ⚠ 无 DASHSCOPE_API_KEY 环境变量，跳过图选项裁剪 "
              f"（图配对题 Q 仍可正常输出，但 options 字段为空）", flush=True)
        return {}
    try:
        import openai
    except ImportError:
        print(f"[english_image_paper] ⚠ pip install openai 后才能裁图选项", flush=True)
        return {}

    client = openai.OpenAI(api_key=api_key,
                            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    b64 = base64.b64encode(page_img.read_bytes()).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    try:
        resp = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _CROP_PROMPT},
            ]}],
            temperature=0.0, max_tokens=512, timeout=120,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        data = json.loads(raw)
    except Exception as e:
        print(f"[english_image_paper] ⚠ qwen-vl 定位失败: {e}", flush=True)
        return {}

    img = Image.open(page_img)
    W, H = img.size
    out_dir.mkdir(parents=True, exist_ok=True)
    # 收 bbox（dict），先全部解析 + 验证，再决定是否裁
    parsed: dict[str, tuple[int,int,int,int]] = {}
    for opt in data.get("options", []):
        label = opt.get("label", "").strip().upper()
        if label not in {"A", "B", "C", "D"}: continue
        try:
            x1 = int(opt["x1"] * W / 100); y1 = int(opt["y1"] * H / 100)
            x2 = int(opt["x2"] * W / 100); y2 = int(opt["y2"] * H / 100)
        except Exception:
            continue
        # 限位：qwen 偶尔给越界坐标（如 1256 vs W=1117），clamp 而非 drop
        x1 = max(0, min(W, x1)); x2 = max(0, min(W, x2))
        y1 = max(0, min(H, y1)); y2 = max(0, min(H, y2))
        if x1 >= x2 or y1 >= y2 or (x2 - x1) < W * 0.05 or (y2 - y1) < H * 0.05:
            print(f"[english_image_paper] ⚠ {label} bbox 退化 ({x1},{y1},{x2},{y2})", flush=True)
            continue
        parsed[label] = (x1, y1, x2, y2)

    # —— 校验 + 自动修复 ——
    # 1. 宽 < 15% / 高 < 8% / 与同伴面积差 >3× 视为坏 bbox，剔除
    sizes = {l: (x2-x1)*(y2-y1) for l, (x1,y1,x2,y2) in parsed.items()}
    bad: set[str] = set()
    if len(sizes) >= 2:
        median_s = sorted(sizes.values())[len(sizes)//2]
        for l, s in sizes.items():
            if s < median_s / 3:
                bad.add(l)
    # 绝对阈值放宽到 8%（changping 等区图选项较窄）；
    # 中位数检查 (line above) 仍能剔出真的歪掉的 bbox
    for l, (x1,y1,x2,y2) in parsed.items():
        if (x2-x1) < W * 0.08 or (y2-y1) < H * 0.05:
            print(f"[english_image_paper] ⚠ 选项{l} bbox {x2-x1}x{y2-y1} 过小，剔除", flush=True)
            bad.add(l)
    for l in bad:
        parsed.pop(l, None)

    # 2. 缺失选项推断：剩 3 个 → 推断布局（2x2 / 1x4 / 4x1）补 4th
    missing = sorted({"A","B","C","D"} - set(parsed.keys()))
    if missing and len(parsed) == 3:
        for l, b in parsed.items():
            print(f"[english_image_paper]   已识别 {l}: x1={b[0]} y1={b[1]} x2={b[2]} y2={b[3]} "
                  f"({b[2]-b[0]}x{b[3]-b[1]})", flush=True)
        widths = [x2-x1 for x1,y1,x2,y2 in parsed.values()]
        heights = [y2-y1 for x1,y1,x2,y2 in parsed.values()]
        w_med = sorted(widths)[1]; h_med = sorted(heights)[1]
        # 收 row/col 用容差合并
        def _merge(vs, tol):
            out = []
            for v in sorted(set(vs)):
                if not out or v - out[-1] > tol: out.append(v)
            return out
        cols = _merge([x1 for x1,_,_,_ in parsed.values()], w_med * 0.4)
        rows = _merge([y1 for _,y1,_,_ in parsed.values()], h_med * 0.4)
        print(f"[english_image_paper]   布局推断: {len(cols)} 列 x {len(rows)} 行", flush=True)
        guess = None
        if len(cols) == 2 and len(rows) == 2:
            # 2x2 grid 缺哪个角
            occupied = set()
            for x1, y1, _, _ in parsed.values():
                ci = 0 if abs(x1-cols[0]) < abs(x1-cols[1]) else 1
                ri = 0 if abs(y1-rows[0]) < abs(y1-rows[1]) else 1
                occupied.add((ci, ri))
            for ci in (0,1):
                for ri in (0,1):
                    if (ci,ri) not in occupied:
                        guess = (cols[ci], rows[ri],
                                 min(W, cols[ci]+w_med), min(H, rows[ri]+h_med))
                        break
                if guess: break
        elif len(rows) == 1 and len(cols) == 3:
            # 1x4 横排
            sorted_bb = sorted(parsed.items(), key=lambda kv: kv[1][0])  # by x1
            x_left = sorted_bb[0][1][0]
            x_right = sorted_bb[-1][1][2]
            span = x_right - x_left
            # **关键诊断 v2**：若 3 bbox 跨度 > 80% 页宽，剩余空间装不下第 4 张 →
            # qwen 把 4 张图所在区域误识别为 3 张（接邻或近接邻），统一重分 4 等。
            # 兼容 qwen 偶尔给出 5-30px 小间隙的情况（早前 strict <10px 漏过这种）。
            gaps = [sorted_bb[i+1][1][0] - sorted_bb[i][1][2] for i in range(2)]
            mostly_contiguous = all(abs(g) < W * 0.05 for g in gaps)
            spans_full_width = span > W * 0.75 or x_right > W * 0.85
            if (mostly_contiguous or spans_full_width):
                print(f"[english_image_paper] 🔧 检测到 ABC 接邻、跨度 {span}px → "
                      f"判定为 1x4 误识别，重新四等分", flush=True)
                each_w = span // 4
                y1_top = sorted_bb[0][1][1]; y2_bot = sorted_bb[0][1][3]
                # **高度约束**：qwen 原 bbox 高度常含下方正文（user feedback：
                # "下边多了正文的内容"），强制高度 ≤ 宽度 × 1.1（近方形）。
                # 北京中考英语图选项通常是方形或略宽（4:3），不会比宽更高。
                max_h = int(each_w * 1.1)
                if (y2_bot - y1_top) > max_h:
                    y2_bot = y1_top + max_h
                    print(f"[english_image_paper]   高度裁短至 {max_h}px（防混入正文）",
                          flush=True)
                for i, label in enumerate("ABCD"):
                    nx1 = x_left + i * each_w
                    nx2 = x_left + (i+1) * each_w if i < 3 else x_right
                    parsed[label] = (nx1, y1_top, nx2, y2_bot)
                guess = None  # 已直接写入 parsed
            else:
                step = (max(cols) - min(cols)) // (len(cols) - 1)
                new_x1 = max(cols) + step
                new_x2 = min(W, new_x1 + w_med)
                if new_x1 < W - 20:
                    guess = (new_x1, rows[0], new_x2, min(H, rows[0]+h_med))
        elif len(cols) == 1 and len(rows) == 3:
            # 4x1 竖排：缺最下
            step = (max(rows) - min(rows)) // (len(rows) - 1)
            new_y1 = max(rows) + step
            new_y2 = min(H, new_y1 + h_med)
            if new_y1 < H - 20:
                guess = (cols[0], new_y1, min(W, cols[0]+w_med), new_y2)
        if guess:
            for m in missing:
                parsed[m] = guess
                print(f"[english_image_paper] 🔧 推断 {m}: {guess}", flush=True)
                break

    missing_after = sorted({"A","B","C","D"} - set(parsed.keys()))
    if missing_after:
        # 用 ⚠ 而非 ❌：缺图选项不阻断流水线（self-check 已豁免
        # has_image_options=True 题的 options 检查），只是裁图不完整
        print(f"[english_image_paper] ⚠ 推断后仍缺选项 {missing_after}", flush=True)

    # 落盘
    rel: dict[str, str] = {}
    for label, (x1, y1, x2, y2) in parsed.items():
        crop = img.crop((x1, y1, x2, y2))
        out_path = out_dir / f"{prefix}-opt-{label}.png"
        crop.save(out_path)
        rel[label] = f"{prefix}-opt-{label}.png"
    return rel


def _ocr_page_single(img: Path, cache: Path, engine: str, force=False) -> str:
    """单引擎 OCR + cache。engine ∈ {'GeneralAccurateOCR', 'GeneralBasicOCR'}。"""
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and not force:
        return cache.read_text(encoding="utf-8")
    req_cls = getattr(models, f"{engine}Request")
    req = req_cls()
    req.ImageBase64 = _img_to_b64(img)
    resp = getattr(_get_client(), engine)(req)
    d = json.loads(resp.to_json_string())
    txt = "\n".join(td.get("DetectedText","") for td in d.get("TextDetections", []))
    cache.write_text(txt, encoding="utf-8")
    return txt


def _ocr_page(img: Path, cache: Path, force=False) -> str:
    """OCR 单页 - 默认用 GeneralAccurate（layout-aware，长 passage 更好）。
    答案页的紧凑短行漏读由 _ocr_page_basic_supplement 在主流程补救。
    返回值已剥页脚（下游不必再 strip）。
    """
    txt = _ocr_page_single(img, cache, "GeneralAccurateOCR", force)
    return _strip_footers(txt)


def _ocr_page_basic_supplement(img: Path, cache_dir: Path, force=False) -> str:
    """GeneralBasic 补 OCR（专用于答案页紧凑短行救援）。
    历史教训：tongzhou Q19 "19.C" 单行被 Accurate 漏读，Basic 抓到；但 Basic
    对正文长行表现差。所以只在答案页补一次 Basic，merge 到 a_text 给
    _parse_answers 多一次机会捞 N.X 答案行。
    """
    cache = cache_dir / img.name.replace(".png", ".txt")
    try:
        txt = _ocr_page_single(img, cache, "GeneralBasicOCR", force)
        return _strip_footers(txt)
    except Exception as e:
        print(f"[english_image_paper] ⚠ Basic 补 OCR fail ({img.name}): {e}", flush=True)
        return ""


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


# ─── 共享 helpers（所有 section parser 必须复用，禁止再写新 regex）───────
# 历史教训：choice/cloze/reading 各写过一份独立的选项 regex，导致同类 bug
# （"Bored/Chang'e/Disappointed" 含 A-D 字母被吞）在 reading 修了 choice 没修。
# 新增 section parser 时，**必须**调用下面的 helper：
#   - 选项块解析 → _parse_options_block
#   - 单项填空 OCR 漏读空位补回 → _insert_blank_marks
#   - passage 段内 OCR 误换行合并 → _join_paragraph_lines
#   - 页脚清洗 → 已在 _ocr_page 出口统一调，下游不需要再调（但 idempotent，重复无副作用）
# 若有新边界情况现 helper 无法覆盖，**修 helper**，不要在 caller 里另写一套。

_NUM_HEAD_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.*)$", re.MULTILINE)
# 选项标记 anchor：(^行首 或 空白) + A-D + .|、|． — 严格要求 . 在字母后，
# 避免误命中单词中的 C/D（如 "Chang'e"、"Disappointed"）
_OPT_MARK_RE = re.compile(r"(?:^|\s)([A-D])\s*[.、．]\s*", re.MULTILINE)


def _normalize_options_block(block: str, inject_missing_A: bool = False) -> str:
    """OCR 紧凑/漏字变体的规范化（cloze + reading 都用）：
    (1) "N.A.value" → "N. A.value"（数字与字母间补空格）
    (2) "N. A value" → "N. A. value"（A 后补 . — shunyi cloze）
    (3) "D value" 行首字母后缺 . → "D. value"（shunyi reading Q26 D 选项）
    (4) **仅 cloze**：N. <非A-D字符> → N. A. <字符>（shunyi OCR 漏 A 字符）
       reading 题干常以题号+疑问句开头（"24. What..."），不能注入 A.
    """
    block = re.sub(r"(?m)^(\s*\d{1,2})\s*[.、．]\s*(?=[A-D])", r"\1. ", block)
    block = re.sub(r"(?m)^(\s*\d{1,2}\s*[.、．]\s*)A\s+(?=[a-zA-Z])", r"\1A. ", block)
    block = re.sub(r"(?m)^([A-D])\s+(?=[a-zA-Z])", r"\1. ", block)
    if inject_missing_A:
        block = re.sub(r"(?m)^(\s*\d{1,2}\s*[.、．]\s*)(?![A-D]\s*[.、．\s])(?=[a-zA-Z])",
                        r"\1A. ", block)
    return block


def _parse_options_block(block: str) -> dict[str, str]:
    """统一选项解析：规范化 → 剥页脚 → 按 anchor 切 → 按首现保留 ABCD 各一个。

    适用 单项填空 / 完形选项行 / 阅读理解。规避旧 `[^A-D\\n]` 陷阱
    （会因"Bored/Chang'e/Disappointed"含 A-D 字母吞掉选项）。
    """
    block = _normalize_options_block(block)
    block = _strip_footers(block)
    marks = list(_OPT_MARK_RE.finditer(block))
    seen: set[str] = set(); marks_uniq = []
    for m in marks:
        if m.group(1) not in seen:
            seen.add(m.group(1)); marks_uniq.append(m)
    opts: dict[str, str] = {}
    for i, m in enumerate(marks_uniq):
        end = marks_uniq[i+1].start() if i+1 < len(marks_uniq) else len(block)
        val = block[m.end():end].strip().rstrip(".").strip()
        opts[m.group(1)] = val
    return opts
# 句末标点：仅 . ! ? ; 。 ！ ？ ；（不含逗号——"Mom, [空位] I use" 中逗号
# 不算结句，下行可能是空位续行）
_SENT_END = re.compile(r"[.!?;。！？；]\s*$")


def _insert_blank_marks(stem: str) -> str:
    """OCR 漏读单项填空空位：行末无标点 + 下行接非选项/题号起始 → 中间插 `___`。

    英语单选 stem 通常含 1 个空位，OCR 把空白处吞了，留下"前段\\n后段"。
    把这种换行替换为 ` ___ ` 让空位显式。
    """
    lines = [ln.rstrip() for ln in stem.split("\n") if ln.strip()]
    if len(lines) <= 1: return stem
    out = [lines[0]]
    n_blanks = 0  # 单项填空一般 1 个空，避免插入多个
    for ln in lines[1:]:
        prev = out[-1]
        is_sent_end = bool(_SENT_END.search(prev))
        is_apos_end = bool(re.search(r"['’]s?\s*$|[”\"]\s*$", prev))  # Alice's / "word"
        is_dialog = bool(re.match(r"^\s*[-—]", ln))
        is_option = bool(re.match(r"^\s*[A-D]\s*[.、．]", ln))
        # 用 ___ 合：行末非句末/所有格 + 下行非对话/选项 + 还没插过空位
        if not is_sent_end and not is_apos_end and not is_dialog and not is_option and n_blanks < 1:
            out[-1] = prev + " ___ " + ln
            n_blanks += 1
        elif is_sent_end or is_dialog:
            out.append(ln)  # 真换段
        else:
            out[-1] = prev + " " + ln  # 普通续行：用空格连（避免显示多行）
    return "\n".join(out)


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
        # stem 去前导题号 + 合并跨行空位标记
        stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem_full).strip()
        stem = _insert_blank_marks(stem)
        # 抽选项（统一 helper：剥页脚 + 严格 anchor）
        opts = _parse_options_block(opts_part)
        out.append({"number": n, "stem": stem, "options": opts})
    return out


# ─── section 二：完形填空 ───────────────────────────────────────────────────

def _parse_cloze(text: str, num_range: range) -> tuple[dict, list[dict]]:
    """切完形填空：1 篇文章（含空位编号） + 8 题（每题 4 选项）。

    文章正文里数字 13/14/15/... 直接作为空位标记，转换为 `___N___` 显式标记。
    选项行：N. A. xx / B. xx / C. xx / D. xx
    """
    # 找第一个题号 ^N. 选项行（A. xxx）作为"选项段"起点
    # 放宽：A 后的 . 可选（shunyi OCR 偶有 "13. A believing" 无 .）
    lines = text.split("\n")
    opt_start = None
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*(\d{1,2})\s*[.、．]\s*A\s*[.、．\s]", ln)
        if m and int(m.group(1)) in num_range:
            opt_start = i; break
    if opt_start is None:
        return {"body": _strip_footers(text)}, []
    # 文章在 opt_start 之前（去除大题标题 + instruction + 页脚）
    body_lines = []
    for ln in lines[:opt_start]:
        s = ln.strip()
        if not s: continue
        if re.search(r"完形填空|选择最佳选项|阅读下面", s): continue
        body_lines.append(s)
    body = _strip_footers("\n".join(body_lines)).strip()
    body = _join_paragraph_lines(body)  # 合并段内 OCR 误换行
    # 转空位标记：13-20 这些数字（前后非数字/字母边界）→ ___N___
    for n in num_range:
        body = re.sub(rf"(?<![\d\w]){n}(?![\d\w])", f"___{n}___", body)
    # 选项部分：8 题 × 4 行
    opts_block = "\n".join(lines[opt_start:]).strip()
    # 规范化（cloze 段允许 inject_missing_A — "15. plans" → "15. A. plans"）
    opts_block = _normalize_options_block(opts_block, inject_missing_A=True)

    # 切题：以 "^N. A． " 起点
    q_starts = []
    for m in re.finditer(r"^\s*(\d{1,2})\s*[.、．]\s*A\s*[.、．\s]",
                          opts_block, re.MULTILINE):
        q_starts.append((int(m.group(1)), m.start()))
    questions = []
    for i, (n, pos) in enumerate(q_starts):
        end = q_starts[i+1][1] if i+1 < len(q_starts) else len(opts_block)
        chunk = opts_block[pos:end]
        # 抽 4 个选项（统一 helper：剥页脚 + anchor）
        opts = _parse_options_block(chunk)
        if len(opts) >= 4:
            questions.append({"number": n,
                              "blank_index": n - num_range.start + 1,
                              "options": opts, "stem": ""})
    q_nums = [q["number"] for q in questions]
    passage = {"body": body, "type": "cloze",
               "q_range": [min(q_nums), max(q_nums)] if q_nums else None}
    return passage, questions


# ─── section 三：阅读理解 ───────────────────────────────────────────────────

_SUB_RE = re.compile(r"^\s*[(（]([一二三四五六])[)）]")
_SINGLE_LETTER_RE = re.compile(r"^\s*([A-E])\s*$")  # 单字母行（篇章标识）

# 卷面噪声 patterns —— 在 _ocr_page 出口统一剥（cross-cutting concern）。
# 关键原则：每个 pattern 要把噪声 **连同其后缀整段** 匹配掉，否则 sub("")
# 留残骸会污染下游（曾因 "(共10页)" 残留进 Q5/Q13/Q30/Q37/Q38 题干）。
_NOISE_LINE_PATTERNS = [
    # ① 完整页脚 "九年级英语试卷第N页(共M页)" / "九年级(英语)第N页(共M页)" /
    #    "初三英语试卷第N页(共M页)" / "北京市西城区九年级统一测试试卷英语2026.4第N页"
    #    放宽到 30 chars 中间内容，覆盖含日期/区名等长 header
    re.compile(r"(?:初[一二三]|九年级|高[一二三])[^\n]{0,30}\s*第\s*\d+\s*页"
               r"(?:\s*[\(（]\s*共\s*\d+\s*页\s*[\)）])?"),
    # ①' 无年级前缀的简化页脚 "英语试卷第N页(共M页)" / "英语试卷参考答案第N页"
    # （dongcheng/fengtai 等区使用这种简写）
    re.compile(r"英语(?:试卷)?(?:参考答案)?\s*第\s*\d+\s*页"
               r"(?:\s*[\(（]\s*共\s*\d+\s*页\s*[\)）])?"),
    # ①'' "第N页/共M页" 斜杠分隔（tongzhou：tongzhou 多页用"第11页/共20页"）
    re.compile(r"第\s*\d+\s*页\s*/\s*共\s*\d+\s*页"),
    # ② 答案页脚 "英语试卷参考答案第N页(共M页)"
    re.compile(r"[一-龥]*试卷参考答案[^\n]{0,12}第\s*\d+\s*页"
               r"(?:\s*[\(（]\s*共\s*\d+\s*页\s*[\)）])?"),
    # ③ 单独 "(共N页)" 或 "第N页(共M页)" 一整行（兜底残块）
    re.compile(r"^\s*[\(（]?\s*第?\s*\d*\s*页?\s*[\)）]?\s*[\(（]?\s*共\s*\d+\s*页\s*[\)）]?\s*$"),
    # ④ 卷面 cover header：放宽匹配，覆盖各区/各年措辞变体：
    #   - "北京市朝阳区九年级综合练习(一)"
    #   - "北京市海淀区初三第一学期期末练习"
    #   - "西城区2026届九年级一模"
    #   - "门头沟区2025-2026学年九年级第一次模拟练习"
    #   - "朝阳区九年级综合练习" (无北京市前缀)
    re.compile(
        r"^\s*(?:北京市?\s*)?[一-龥]{1,8}区[一-龥0-9\s\-届第一二三四五六七八九十学年期模]{1,30}"
        r"(?:练习|考试|测试)"
        r"(?:\s*[\(（][一二三四五六\d]{1,3}[\)）])?\s*$"),
    # ⑤ 卷面 cover header："英语试卷"（精确，**不能加后缀**否则会吃掉
    #    "英语试卷答案及评分参考" 导致 ANSWER_MARKER 失效，所有答案变空）
    re.compile(r"^\s*英语试卷\s*$"),
    # ⑥ "2026.4" 之类纯日期行
    re.compile(r"^\s*20\d{2}[.\-/]\d{1,2}\s*$"),
]
# 兼容别处保留的引用（exam-review 检测和 reading sub-section 内部过滤）
_PAGE_FOOTER_RE = _NOISE_LINE_PATTERNS[0]


def _strip_footers(text: str) -> str:
    """剥所有卷面噪声（页脚 / cover header / 答案页脚 / 日期等）。

    用 sub("") 而非整行 drop —— 噪声可能 inline 在 OCR 行尾（比如某些扫描
    把 "...句子末尾。 九年级英语试卷第N页(共M页)" 合在一行）。sub 干净后
    若整行空则 drop。
    """
    out = []
    for ln in text.split("\n"):
        cleaned = ln
        for pat in _NOISE_LINE_PATTERNS:
            cleaned = pat.sub("", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            out.append(cleaned)
    return "\n".join(out)


def _join_paragraph_lines(text: str) -> str:
    """合并 OCR 段内换行：上行末非句末标点 → 与下行用空格连。
    段落起点（含 ___N___ 空位标记的行也算续接段）由 "上行 . ! ? ; " 结尾断开。
    """
    lines = [ln.rstrip() for ln in text.split("\n") if ln.strip()]
    if not lines: return text
    out = [lines[0]]
    for ln in lines[1:]:
        prev = out[-1]
        # 上一行末以句末标点结束 → 段落分隔；否则与下行连
        if re.search(r"[.!?;。！？；]\s*['’”\")]?\s*$", prev):
            out.append(ln)
        else:
            out[-1] = prev + " " + ln
    return "\n".join(out)


def _parse_reading(text: str, num_range: range) -> tuple[list[dict], list[dict]]:
    """切阅读理解。**两级边界设计**（跨区通用）：

    1. **主层（primary）边界**：(一) (二) 等 _SUB_RE 标记
    2. **每个 primary 内部**：
       - 若 image-match（A 篇）→ 单 passage，内部所有 A/B/C/D 单字母行
         都是图片标号，**不**做二次切分（修复 daxing 案例）
       - 若文本篇章 → 用 _SINGLE_LETTER_RE 切多篇（如 (二) 内的 B/C/D）

    跨区已验证：chaoyang ((一)(二))、haidian ((一)+letter A label, (二)+letters B C D)、
    daxing ((一)+5 letter labels, (二)+letters)
    """
    lines = text.split("\n")
    # Primary 边界 = _SUB_RE 主层标记
    primary_starts = [i for i, ln in enumerate(lines) if _SUB_RE.match(ln)]
    if not primary_starts:
        # 兜底：无 (一)(二) 标记时退化用 letter 切分
        primary_starts = [i for i, ln in enumerate(lines) if _SINGLE_LETTER_RE.match(ln)]

    passages: list[dict] = []
    questions: list[dict] = []
    sub_letter_idx = 0  # 全局 A/B/C/D 计数（跨 primary 累加）

    for k, p_start in enumerate(primary_starts):
        p_end = primary_starts[k+1] if k+1 < len(primary_starts) else len(lines)
        primary_lines = [ln for ln in lines[p_start:p_end]
                          if not _PAGE_FOOTER_RE.search(ln)]
        primary_text = "\n".join(primary_lines)

        # 是否 image-match：决定要不要在 primary 内部 letter-split
        is_image_match = _is_image_match_section(primary_text)
        if not is_image_match:
            # 文本篇章 primary：内部按 _SINGLE_LETTER_RE 切多篇
            inner_letter_positions = [
                li for li, ln in enumerate(primary_lines)
                if _SINGLE_LETTER_RE.match(ln)
            ]
            if inner_letter_positions:
                # 多篇：每个 letter 行起一个 article
                sub_segments = []
                for ai, li in enumerate(inner_letter_positions):
                    art_end = (inner_letter_positions[ai+1]
                               if ai+1 < len(inner_letter_positions) else len(primary_lines))
                    sub_segments.append(primary_lines[li:art_end])
            else:
                # 单篇：整个 primary 即一篇
                sub_segments = [primary_lines]
        else:
            # image-match：整个 primary 是单 passage（内部所有 letter 都是标号）
            sub_segments = [primary_lines]

        for sub_lines in sub_segments:
            sub_text = "\n".join(sub_lines)
            # image-match 的 anchor 可能不在行首（xicheng "Harry 21."）；
            # 用更宽容的多模式正则
            if is_image_match:
                # 行末或行内任意位置的 "N." 模式（image-match 学生标号位置不固定）
                anchor_pat = re.compile(r"(?:^|\s)(\d{1,2})\s*[.、．](?:\s|$)",
                                         re.MULTILINE)
            else:
                anchor_pat = _NUM_HEAD_RE
            q_anchors = [m for m in anchor_pat.finditer(sub_text)
                         if int(m.group(1)) in num_range]
            if not q_anchors:
                continue
            # image-match 内可能命中重复（同 N 出现多次），去重保第一个
            seen = set(); q_anchors_uniq = []
            for m in q_anchors:
                n = int(m.group(1))
                if n not in seen:
                    seen.add(n); q_anchors_uniq.append(m)
            q_anchors = q_anchors_uniq
            sub_letter = (_READING_SUB_LETTERS[sub_letter_idx]
                          if sub_letter_idx < len(_READING_SUB_LETTERS)
                          else str(sub_letter_idx))
            sub_letter_idx += 1
            _process_reading_sub(sub_lines, sub_text, q_anchors, sub_letter,
                                  is_image_match, num_range, passages, questions)
    return passages, questions


def _process_reading_sub(sub_lines, sub_text, q_anchors, sub_letter,
                          is_image_match, num_range, passages, questions):
    """处理单个 sub-section（一篇 passage + 其题目）。原 _parse_reading 后半段
    抽出来，便于两级边界 caller 调用。"""
    if is_image_match:
        # 锚点行检测：兼容两种 image-match OCR 版式
        # (a) chaoyang/daxing: 独立行 "21." 夹在描述段中
        # (b) xicheng: "Harry 21." 名字+空格+N. 在行末
        anchor_re_strict = re.compile(
            r"^(?:\s*|.*\s)(\d{1,2})\s*[.、．]\s*$")
        q_nums_sub = [int(a.group(1)) for a in q_anchors]
        # **缺锚兜底**：image-match 段固定 3 题(num_range[0]..[2])。如果 OCR
        # 漏读 anchor（tongzhou Q22 漏 "22."），按 num_range 补齐期望题号，
        # 后面 paragraph-to-question 映射时按段落序号 fallback。
        expected = list(num_range)[:3]
        if len(q_nums_sub) < 3 and len(expected) == 3:
            for n in expected:
                if n not in q_nums_sub:
                    q_nums_sub.append(n)
            q_nums_sub = sorted(q_nums_sub)
        pid = f"reading_{sub_letter}"

        # 清 header（sub 标题 / instruction），收集 body_lines
        body_lines: list[str] = []
        for ln in sub_lines:
            s = ln.strip()
            if not s: continue
            if re.match(r"^\s*[(（][一二三四五六][)）]", s): continue
            # 通用 instruction 关键词集合（覆盖各区措辞变体）
            if any(h in s for h in _IMG_MATCH_HINTS) \
                    or "其中一个选项" in s or "请根据" in s:
                continue
            # 续行 instruction（如 "...A、B、C、D"）
            if re.search(r"[、，,]\s*[A-D]\s*[、，,]\s*[A-D]", s):
                continue
            # 单字母行（image-match 内是图片标号，不算正文）
            if _SINGLE_LETTER_RE.match(ln):
                continue
            body_lines.append(s)

        # 把 body_lines 按"句末 . 行"切段；记录每段是否含锚点
        paragraphs: list[tuple[list[str], int | None]] = []
        cur: list[str] = []
        cur_anchor: int | None = None
        for ln in body_lines:
            am = anchor_re_strict.match(ln)
            if am and int(am.group(1)) in num_range:
                cur_anchor = int(am.group(1))
                continue  # 锚点行本身不入正文
            cur.append(ln)
            if ln.rstrip().endswith(".") or ln.rstrip().endswith("."):
                paragraphs.append((cur, cur_anchor))
                cur = []
                cur_anchor = None
        if cur:
            paragraphs.append((cur, cur_anchor))

        # 按题号归并段落。优先级：
        # 1) 段内含 anchor → 直接归该题
        # 2) **段落数 == 期望题数 == 3** → 按段落 index 映射（处理 OCR 漏锚）
        # 3) 否则继承 last_num
        stems_by_num: dict[int, list[str]] = {n: [] for n in q_nums_sub}
        # 仅当段落数恰好等于 q_nums_sub 大小，按 index 直接对应
        idx_map_ok = len(paragraphs) == len(q_nums_sub)
        last_num: int | None = None
        for p_idx, (plines, anchor) in enumerate(paragraphs):
            if anchor is not None:
                target = anchor
            elif idx_map_ok:
                target = q_nums_sub[p_idx]
            elif last_num is not None:
                target = last_num
            else:
                target = q_nums_sub[0]
            # 剥学生名行（独立姓名串）：兼容中/英名
            name_line: str | None = None
            kept: list[str] = []
            eng_name_re = re.compile(r"^[A-Z][a-z]+(?:[\s\-][A-Z][a-z']+){0,3}$")
            cn_name_re = re.compile(r"^[一-龥]{2,4}$")
            for l in plines:
                s = l.strip()
                if len(s) <= 20 and (eng_name_re.fullmatch(s) or cn_name_re.fullmatch(s)):
                    name_line = s
                else:
                    kept.append(s)
            seg = " ".join(kept).strip()
            if name_line:
                seg = (seg + f" ({name_line})").strip()
            if seg:
                stems_by_num[target].append(seg)
            last_num = target

        # passage body = 题型说明（短）
        instr_lines: list[str] = []
        for ln in sub_lines[:5]:
            s = ln.strip()
            if not s: continue
            if re.match(r"^\s*[(（][一二三四五六][)）]", s):
                s = re.sub(r"^\s*[(（][一二三四五六][)）]\s*", "", s)
            if any(h in s for h in _IMG_MATCH_HINTS) \
                    or "其中一个选项" in s or "请根据" in s:
                instr_lines.append(s)
        instr_body = _join_paragraph_lines("\n".join(instr_lines))
        passages.append({"id": pid, "type": "reading",
                          "body": instr_body,
                          "q_range": [min(q_nums_sub), max(q_nums_sub)],
                          "_needs_src_page_figure": True,
                          "_is_image_match": True})
        for n in q_nums_sub:
            stem = " ".join(stems_by_num.get(n, [])).strip()
            questions.append({"number": n, "stem": stem,
                               "options": None,
                               "passage_id": pid, "type": "choice",
                               "has_image_options": True})
        return

    # 文本篇章
    body = sub_text[:q_anchors[0].start()].strip()
    body = re.sub(r"^\s*[(（][一二三四五六][)）][^\n]*", "", body).strip()
    body = re.sub(r"^\s*[A-E]\s*$", "", body, flags=re.MULTILINE).strip()
    body = re.sub(r"^\s*阅读下[^\n]+", "", body, flags=re.MULTILINE).strip()
    body = re.sub(r"^\s*请阅读[^\n]+", "", body, flags=re.MULTILINE).strip()
    body = _join_paragraph_lines(_strip_footers(body))
    pid = f"reading_{sub_letter}"
    q_nums_sub = [int(a.group(1)) for a in q_anchors]
    passages.append({"id": pid, "type": "reading", "body": body,
                      "q_range": [min(q_nums_sub), max(q_nums_sub)]})
    for i, am in enumerate(q_anchors):
        n = int(am.group(1))
        end = q_anchors[i+1].start() if i+1 < len(q_anchors) else len(sub_text)
        chunk = sub_text[am.start():end]
        # 规范化（让 "A Offering" 无 . 也能被 a_pos 命中：shunyi Q27 case）
        chunk = _normalize_options_block(chunk)
        a_pos = re.search(r"\bA\s*[.、．]\s*", chunk)
        stem = chunk[:a_pos.start()] if a_pos else chunk
        stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem).strip()
        opts = _parse_options_block(chunk[a_pos.start():]) if a_pos else {}
        questions.append({
            "number": n, "stem": stem, "options": opts,
            "passage_id": pid, "type": "choice"
        })


# ─── section 四：阅读表达 ───────────────────────────────────────────────────

def _parse_express(text: str, num_range: range) -> tuple[dict, list[dict], dict[int, float]]:
    """阅读表达：1 篇文章 + 主观题（无选项）。

    返回 (passage, questions, scores_by_num)：
    scores_by_num 从 section 标题 "(第N-M题每题K分)" 动态解析；空 dict 表示
    解析失败，caller 应 fallback 到默认。
    """
    lines = text.split("\n")
    q_anchors = [m for m in _NUM_HEAD_RE.finditer(text)
                 if int(m.group(1)) in num_range]
    if not q_anchors:
        return {"body": text.strip()}, [], {}
    # 先解析 section 标题分值（在题号 anchor 之前的部分）
    header_text = text[:q_anchors[0].start()]
    scores_by_num = _parse_express_scores(header_text)
    body = header_text.strip()
    # 清大题标题
    body = re.sub(r"^\s*四、\s*阅读(?:与|表达)[^\n]*\n", "", body).strip()
    body = re.sub(r"^\s*阅读下面[^\n]+\n", "", body, flags=re.MULTILINE).strip()
    body = _join_paragraph_lines(_strip_footers(body))
    q_nums = [int(m.group(1)) for m in q_anchors]
    passage = {"id": "express", "type": "reading_express", "body": body,
               "q_range": [min(q_nums), max(q_nums)] if q_nums else None}
    questions = []
    for i, m in enumerate(q_anchors):
        n = int(m.group(1))
        end = q_anchors[i+1].start() if i+1 < len(q_anchors) else len(text)
        stem = text[m.start():end].strip()
        stem = re.sub(r"^\s*\d+\s*[.、．]\s*", "", stem).strip()
        questions.append({
            "number": n, "stem": stem, "options": None,
            "passage_id": "express", "type": "reading_express"
        })
    return passage, questions, scores_by_num


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

_MULTI_ANS_LINE_RE = re.compile(
    # 数字+分隔(可缺)+字母答案，分隔符： [.、．] 或单纯空格 或直接字母（"13D"）
    r"(\d{1,2})\s*[.、．]?\s*([A-D]+)(?=\s+\d{1,2}\s*[.、．]?\s*[A-D]|\s*$)")
# 范围答案模式 "1-5 BCDBB" / "1—5 BCDBB" / "6-10 ADCDC"
# pinggu 等区使用紧凑范围格式
# 范围答案模式 - 允许范围与字母无空格 (shunyi: "1-5BDABC"; pinggu: "1-5 BCDBB")
_RANGE_ANS_RE = re.compile(
    r"(\d{1,2})\s*[\-—~]\s*(\d{1,2})\s*([A-D]{2,12})")


# 篇章字母答案模式 "A---DBA" / "A---D B A" / "B--- A B C"
# shunyi/pinggu 用此紧凑格式标注阅读理解答案，按北京中考标配映射：
# A篇=Q21-23 (3), B篇=Q24-26 (3), C篇=Q27-29 (3), D篇=Q30-33 (4)
# 关键正则约束：
# - 段首允许 ^/\n/:/： (shunyi 把"阅读理解:A---DBA" 整段写一行，A 在 `:` 后)
# - 字母段只允许 [A-D] 和**普通空格**，不允许 \n (防止贪婪到下一行)
_SECTION_ANS_RE = re.compile(
    r"(?:^|\n|[:：])\s*([A-D])\s*[-—:：]{1,4}\s*([A-D ]{2,15})")
_SECTION_Q_START = {"A": 21, "B": 24, "C": 27, "D": 30}


def _expand_section_letters_ans(text: str) -> str:
    """展开 "A---DBA" 等篇章字母答案为 "21.D\\n22.B\\n23.A"。"""
    out_lines = []
    for ln in text.split("\n"):
        m = _SECTION_ANS_RE.search("\n" + ln)
        if m:
            section = m.group(1)
            letters = re.sub(r"\s+", "", m.group(2))
            if section in _SECTION_Q_START and 1 <= len(letters) <= 5 \
                    and all(c in "ABCD" for c in letters):
                start_q = _SECTION_Q_START[section]
                expanded = "\n".join(f"{start_q+i}.{letters[i]}"
                                      for i in range(len(letters)))
                out_lines.append(expanded)
                continue
        out_lines.append(ln)
    return "\n".join(out_lines)


def _expand_range_ans(text: str) -> str:
    """范围答案展开 "1-5 BCDBB" → "1.B\\n2.C\\n3.D\\n4.B\\n5.B"。
    （pinggu 用 "1-5 BCDBB 6-10 ADCDC" 紧凑表示 12 道单选答案）
    """
    out = []
    for ln in text.split("\n"):
        new_parts: list[str] = []
        cursor = 0
        any_replaced = False
        for m in _RANGE_ANS_RE.finditer(ln):
            n1, n2, letters = int(m.group(1)), int(m.group(2)), m.group(3)
            count = n2 - n1 + 1
            if len(letters) == count and 1 <= n1 <= 40:
                any_replaced = True
                # 关键：先 strip 前缀文本（去除空格连接前一段答案的尾巴）
                pre = ln[cursor:m.start()].strip()
                if pre:
                    new_parts.append(pre)
                new_parts.append("\n".join(f"{n1+i}.{letters[i]}"
                                            for i in range(count)))
                cursor = m.end()
        if any_replaced:
            tail = ln[cursor:].strip()
            if tail:
                new_parts.append(tail)
            # 用 \n 连接，确保每段在自己行（防止 "5.B 6.A" 合行）
            out.append("\n".join(p for p in new_parts if p))
        else:
            out.append(ln)
    return "\n".join(out)


def _expand_multi_ans(text: str) -> str:
    """把一行多答案 "1.C 2.D 3.A 4.B..." 展开为多行 "1.C\\n2.D\\n3.A...".
    （前缀如 "(A)" / "(B)" 在 _parse_answers 中独立处理）
    """
    out = []
    for ln in text.split("\n"):
        # 先剥前缀 "(A)" / "(B)" 之类的篇章标识
        prefix_m = re.match(r"^\s*[(（][A-D][)）]\s*", ln)
        prefix = prefix_m.group(0) if prefix_m else ""
        body = ln[len(prefix):] if prefix else ln
        ms = list(_MULTI_ANS_LINE_RE.finditer(body))
        # 若含 ≥ 2 个 "N.X" 模式且全是字母答案 → 拆分
        if len(ms) >= 2 and all(re.fullmatch(r"[A-D]+", m.group(2)) for m in ms):
            for m in ms:
                out.append(f"{m.group(1)}.{m.group(2)}")
        else:
            out.append(ln)
    return "\n".join(out)


def _parse_answers(answer_text: str) -> list[dict]:
    """从答案页文本解析每题答案。

    格式（北京中考英语典型）：
      "1.C 2.D 3.A 4.B ..."          单项填空一行 12 题
      "13.B 14.A 15.D ..."           完形一行 8 题
      "(A)21.A 22.C 23.B"            阅读 A 篇带篇章标识
      "(B) 24.C\\n25.D\\n26. A"       阅读 B 篇每题独立行
      "34. Small actions..."          阅读表达主观答案
    先预处理把一行多答案展开，再按 ^N. 切。
    """
    # 小写 a/b/c/d 答案标准化为大写（Basic OCR 偶把 "C" 读成 "c"）
    # 限定在"N.<小写>"模式中替换，避免影响正文里的小写字母
    answer_text = re.sub(r"(?m)(^\s*\d{1,2}\s*[.、．\s]+)([a-d])(\s|$)",
                          lambda m: m.group(1) + m.group(2).upper() + m.group(3),
                          answer_text)
    # 多级展开：
    # 1) "A---DBA" → 21.D 22.B 23.A 等篇章字母模式（shunyi/pinggu）
    # 2) "1-5 BCDBB" → 1.B 2.C 3.D ...（pinggu/shunyi）
    # 3) "1.A 2.B 3.C" 一行多答案（chaoyang/haidian）
    answer_text = _expand_section_letters_ans(answer_text)
    answer_text = _expand_range_ans(answer_text)
    answer_text = _expand_multi_ans(answer_text)
    out: list[dict] = []
    cur_num = None; cur_buf: list[str] = []

    def _flush():
        if cur_num is None: return
        sol = "\n".join(cur_buf).strip()
        # 选择题：sol 是单字母 A-D。三种情况：
        # 1) sol 纯 A-D（chaoyang/haidian 紧凑答案）
        # 2) sol 形如 "D\n[详解]..."（tongzhou/yanshan/pinggu 教辅评析体）
        # 3) sol 主观题文字（reading_express）
        if re.fullmatch(r"[A-D]+", sol):
            correct = sol
        else:
            # 取首行 A-D 字符作为答案
            m = re.match(r"^\s*([A-D]+)(?:\s*$|[^A-Da-z])", sol)
            correct = m.group(1) if m else ""
        out.append({"number": cur_num, "correct": correct, "solution": sol})

    for ln in answer_text.split("\n"):
        s = ln.strip()
        if not s: continue
        # 跳大题标题/页脚/篇章 letter 行（pinggu: "A" 单独一行作篇章标识）
        if re.match(r"^[一二三四五六]、|第[一二]部分|^\d{4}\.\d|参考答案"
                     r"|英语试卷参考答案|英语试卷答案|英语参考答案"
                     r"|九年级英语|九年级练习|英语答案"
                     r"|单选\s*[:：]|完形\s*[:：]|阅读理解\s*[:：]"
                     r"|阅读表达\s*[:：]|文段表达\s*[:：]"
                     r"|^[A-D]\s*$", s):  # 篇章 letter 单独一行
            continue
        # 剥前缀 "(A)" / "(B)" 等篇章标识 + shunyi "A---DBA" + pinggu "B 24 B"
        s = re.sub(r"^\s*[(（][A-D][)）]\s*", "", s)
        s = re.sub(r"^\s*[A-D]\s*[-—]{2,}\s*", "", s)  # shunyi "A---DBA"
        s = re.sub(r"^\s*[A-D]\s+(?=\d)", "", s)  # pinggu "B 24" → "24"
        # 剥 "[答案]" / "【答案】" 包装（tongzhou 两种位置）：
        # (a) "[答案]13.C" 前缀型 → "13.C"
        # (b) "13.[答案]C" 中缀型 → "13.C"
        s = re.sub(r"^\s*[\[【]\s*答案\s*[\]】]\s*", "", s)
        s = re.sub(r"^\s*(\d{1,2})\s*[.、．]?\s*[\[【]\s*答案\s*[\]】]\s*",
                    r"\1.", s)
        # 允许 "21 C"（空格分隔无 .）/ "13D"（紧接字母无任何分隔）
        m = re.match(r"^\s*(\d{1,2})(?:\s*[.、．\s]+|(?=[A-D]))(.*)$", s)
        if m and 1 <= int(m.group(1)) <= 40:
            _flush()
            cur_num = int(m.group(1))
            cur_buf = [m.group(2).strip()] if m.group(2).strip() else []
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

    # 1. OCR 全 12 页（主引擎：GeneralAccurate）
    full_text = ""
    page_texts = []  # 保存每页文本，便于精确定位"哪一页是答案页"
    for p in pages:
        t = _ocr_page(p, cache_dir / f"{p.stem}.txt", force)
        page_texts.append((p, t))
        full_text += "\n" + t

    # 1.5 答案页**dual-OCR 补**：找含 ANSWER_MARKER 的页 + 之后所有页，
    # 用 GeneralBasic 再 OCR 一次，merge 进 full_text。Basic 在紧凑短行
    # （"19.C" 单行）漏读率比 Accurate 低（tongzhou case），互补救援。
    basic_cache = out_dir / "tencent-cache" / "basic"
    am_probe = ANSWER_MARKER.search(full_text)
    if am_probe:
        # 找含 marker 的页 idx
        pos = 0
        ans_idx = None
        for i, (p, t) in enumerate(page_texts):
            pos_next = pos + len(t) + 1  # +1 for "\n" separator
            if pos <= am_probe.start() < pos_next:
                ans_idx = i; break
            pos = pos_next
        if ans_idx is not None:
            basic_supplement = []
            for p, _ in page_texts[ans_idx:]:
                bs = _ocr_page_basic_supplement(p, basic_cache, force)
                if bs:
                    basic_supplement.append(bs)
            if basic_supplement:
                full_text += "\n" + "\n".join(basic_supplement)

    # 2. 切题目页 vs 答案页。
    # **关键**：marker（"答案及评分"）所在的行通常是 "英语试卷答案及评分参考"，
    # 在它**之前**还有 1-2 行答案页 cover header（"北京市朝阳区..."、"英语试卷"、
    # "2026.4" 等）。如果直接 full_text[:am.start()] 切，cover header 会粘到
    # 最后一道题（Q38 文段表达）的 stem 末尾。所以要先 walk back 到 marker 行
    # 行首，再继续 walk back 跳过紧邻的 cover header 行。
    am = ANSWER_MARKER.search(full_text)
    if am:
        line_start = full_text.rfind("\n", 0, am.start()) + 1
        before = full_text[:line_start].rstrip("\n")
        before_lines = before.split("\n")
        _cover_re = re.compile(
            r"^\s*(?:(?:北京市?\s*)?[一-龥]{1,8}区[一-龥0-9\s\-]{0,30}"
            r"(?:练习|考试|测试)?|英语试卷|20\d{2}[.\-/]\d{1,2})\s*$")
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

    # **从 SECTIONS 驱动**：题号范围 / 默认分值 都查 SECTIONS，不在此硬编码。
    # 各区试卷如果题号边界稍有不同（如 cloze 9 题而非 8），改 SECTIONS 即可，
    # 不必动 parse 逻辑。
    sec_by_typ = {typ: (r, default_s) for _, r, typ, default_s in SECTIONS}

    if "choice" in sec:
        rng, ds = sec_by_typ["choice"]
        for q in _split_choice_questions(sec["choice"], rng):
            q["type"] = "choice"; q["score"] = ds
            questions.append(q)
    if "cloze" in sec:
        rng, ds = sec_by_typ["cloze"]
        cz_pass, cz_qs = _parse_cloze(sec["cloze"], rng)
        cz_pass["id"] = "cloze"
        passages.append(cz_pass)
        for q in cz_qs:
            q["passage_id"] = "cloze"; q["type"] = "cloze"; q["score"] = ds
            questions.append(q)
    if "reading" in sec:
        rng, ds = sec_by_typ["reading"]
        rd_pass, rd_qs = _parse_reading(sec["reading"], rng)
        passages.extend(rd_pass)
        for q in rd_qs:
            q["score"] = ds
            questions.append(q)
    if "reading_express" in sec:
        rng, ds = sec_by_typ["reading_express"]
        ex_pass, ex_qs, ex_scores = _parse_express(sec["reading_express"], rng)
        passages.append(ex_pass)
        for q in ex_qs:
            # ex_scores 来自 section 标题动态解析，无 fallback 用 ds 或 2
            q["score"] = ex_scores.get(q["number"], ds or 2)
            questions.append(q)
    if "essay" in sec:
        rng, ds = sec_by_typ["essay"]
        for q in _parse_essay(sec["essay"], rng):
            q["score"] = ds
            questions.append(q)

    # 4. 答案
    answers = _parse_answers(a_text)

    full_score = sum(q.get("score", 0) for q in questions) or None

    # 图片配对题 passage：把整页源图挂到 passage.figure（共享资源）
    for ps in passages:
        if ps.get("_needs_src_page_figure"):
            for p in pages:
                tp = cache_dir / f"{p.stem}.txt"
                if tp.exists() and _is_image_match_section(tp.read_text(encoding="utf-8")):
                    ps["_src_page_img"] = str(p)
                    break

    # **元数据 final.json 写 year/district/exam_type**（R1 通病: yaml meta 全空）
    slug = out_dir.name
    m_slug = re.match(r"(\d{4})-(.+?)-(\w+)", slug)
    year_val = int(m_slug.group(1)) if m_slug else None
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
        "subject": "english",
        "year": year_val,
        "district": (region_cn + "区") if region_cn else "",
        "exam_type": type_cn,
        "full_score": full_score,
        "duration_minutes": 90,  # 北京英语 90 分钟
        "passages": passages,
        "questions": questions,
        "answers": answers,
    }
    # 5. 自检：缺号/缺选项/缺答案。**不让 bug 流入 yaml 等人工审**。
    _self_check(result)
    return result


# 北京中考英语：题号 1-38 必须齐；分值合计应为 60
# 残留噪声通用检测（各区都适用，不绑死 chaoyang 的 "共10页"）：
# - "共\d+页" 含括号变体
# - "北京市XX区...练习"
# - "九年级英语试卷第N页"
_RESIDUAL_NOISE_RES = [
    re.compile(r"[\(（]\s*共\s*\d+\s*页\s*[\)）]"),
    re.compile(r"共\s*\d+\s*页"),
    re.compile(r"北京市[一-龥]{1,8}区[一-龥]{1,16}练习"),
    re.compile(r"(?:初[一二三]|九年级|高[一二三])[一-龥]{0,8}试卷?第\s*\d+\s*页"),
    re.compile(r"^\s*英语试卷\s*$", re.MULTILINE),
]


def _has_residual_noise(text: str) -> bool:
    return any(p.search(text) for p in _RESIDUAL_NOISE_RES)


# 从 SECTIONS 推导期望题号 + 期望总分，不硬编码 38/60。
# 各区试卷如果题数/分值标准不同，改 SECTIONS 即可，自检自动跟随。
def _expected_nums() -> set[int]:
    out: set[int] = set()
    for _, rng, _, _ in SECTIONS:
        out.update(rng)
    return out


def _expected_full_score() -> float:
    total = 0.0
    for _, rng, typ, default_s in SECTIONS:
        if default_s is None:
            # reading_express 段：默认按每题 2 分估算（含 1 道 4 分题，但精确值
            # 由 _parse_express 动态解析；此处仅给个体检参考下限）
            total += len(rng) * 2.5  # 4 题平均 2.5 分（2+2+2+4=10）
        else:
            total += len(rng) * default_s
    return total


def _self_check(result: dict) -> None:
    """parse_paper 收尾自检。任何一项 fail 都打 ⚠️ 到 stderr；
    若有 **严重缺失**（缺号 / 缺选项 / 单选缺答案 / passage 空），exit code 非 0。

    自检规则历史：每次人工 review 抖到的"我应该自己能发现"的 bug，要回填到
    这里成为永久规则，避免后续区试卷重复踩坑。
    """
    qs = result.get("questions", [])
    passages = result.get("passages", [])
    ans_by = {a["number"]: a for a in result.get("answers", [])}
    nums_have = {q["number"] for q in qs}

    fatal: list[str] = []
    warn: list[str] = []

    expected_nums = _expected_nums()
    expected_score = _expected_full_score()
    missing = sorted(expected_nums - nums_have)
    extra = sorted(nums_have - expected_nums)
    if missing:
        fatal.append(f"缺题号: {missing}")
    if extra:
        warn.append(f"多余题号（超出 SECTIONS 期望）: {extra}")
    actual_score = result.get("full_score") or 0
    # 允许 ±5% 浮动（reading_express 分值动态 + 各区差异）
    if abs(actual_score - expected_score) > expected_score * 0.05:
        warn.append(f"分值 {actual_score} ≠ 期望 ~{expected_score:g} (差异 >5%)")

    # —— passage 体检（用户多次抱怨 "passage 没内容"，回填规则） ——
    # 阅读型 passage 至少 100 字 body，否则审稿无法看到 shared article。
    # image-match 类型用 _needs_src_page_figure 标记豁免 figure-only 情况
    # （但我们仍要求 body 含 instruction + profile，>100 字）
    for p in passages:
        pid = p.get("id", "?")
        ptype = p.get("type", "")
        body = p.get("body", "") or ""
        # image-match passage 的"内容"是 4 张图（figure），body 只放 instruction
        # 是合理的——自检豁免（标记位 _is_image_match）
        is_img_match = p.get("_is_image_match") or p.get("_needs_src_page_figure")
        if ptype in ("reading", "reading_express") and len(body) < 100 and not is_img_match:
            fatal.append(f"passage[{pid}] type={ptype} body 仅 {len(body)} 字（应 ≥100）")
        if ptype == "cloze" and len(body) < 500:
            fatal.append(f"passage[{pid}] cloze body 仅 {len(body)} 字（应 ≥500）")
        # passage body 不应只是 section instruction 起手语（image-match 豁免）
        body_head = body.lstrip()[:30]
        if body_head and re.match(r"^(下列|请阅读|阅读下面?|根据短文|从下面)", body_head):
            if len(body) < 150 and not is_img_match:
                warn.append(f"passage[{pid}] body 像 instruction 而非文章: {body_head!r}")

    for q in qs:
        n = q["number"]; t = q.get("type", "")
        opts = q.get("options")
        if t in {"choice", "cloze"} and not q.get("has_image_options"):
            if not isinstance(opts, dict) or len(opts) < 4:
                fatal.append(f"Q{n}({t}) options 不足 4: {opts}")
            else:
                empty = [k for k, v in opts.items() if not str(v).strip()]
                if empty:
                    fatal.append(f"Q{n}({t}) 选项 {empty} 内容空")
        if t in {"choice", "cloze"}:
            a = ans_by.get(n, {})
            if not a.get("correct"):
                fatal.append(f"Q{n}({t}) 答案空")
        if t in {"choice", "cloze"} and not q.get("has_image_options"):
            # cloze stem 故意空（passage 承载），choice 必须非空
            if t == "choice" and not str(q.get("stem", "")).strip():
                fatal.append(f"Q{n}(choice) stem 空")
        # —— 题干 / passage body 不应含页面噪声残块 ——
        # 通用 noise 模式（不硬编码具体页数），各区都适用
        for fld in ("stem",):
            v = q.get(fld, "") or ""
            if _has_residual_noise(v):
                fatal.append(f"Q{n} {fld} 含页面噪声: {v[-60:]!r}")

    # passage body 也查噪声
    for p in passages:
        body = p.get("body", "") or ""
        if _has_residual_noise(body):
            fatal.append(f"passage[{p.get('id')}] body 含页面噪声")

    if fatal:
        print("\n❌ 自检失败：", file=sys.stderr)
        for f in fatal: print(f"   - {f}", file=sys.stderr)
    if warn:
        print("\n⚠️  自检告警：", file=sys.stderr)
        for w in warn: print(f"   - {w}", file=sys.stderr)
    if not fatal and not warn:
        print("✅ parse 自检全通过（题号齐 / 选项齐 / 答案齐 / 分值对 / "
              "passage body 齐 / 无页面噪声）", flush=True)


TYPE_EN2CN = {
    "choice": "单选", "cloze": "完形", "reading": "阅读",
    "reading_express": "阅读表达",  # 四、阅读表达（主观题，非作文）
    "essay": "写作",  # 五、文段表达（作文）
}


def _write_yaml(result: dict, src: Path, out_dir: Path) -> None:
    """final.json → yaml（schema 兼容 exam-review；含 passages 二级字段）。"""
    try:
        import yaml as Y
    except ImportError:
        print("(skip yaml: PyYAML 未装)"); return
    slug = out_dir.name  # 如 2026-changping-yi
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

    # 同一 N 多记录时，优先非空 correct（dual-OCR 会重复，且 essay 文本里
    # 数字误匹配会产生空 correct 噪声记录，如 fangshan "30 minutes" 误识为 Q30）
    answers_by_num: dict[int, dict] = {}
    for a in result["answers"]:
        n = a["number"]
        if n not in answers_by_num:
            answers_by_num[n] = a
        else:
            cur = answers_by_num[n]
            # 新记录有 correct 而旧的没有 → 替换
            if a.get("correct") and not cur.get("correct"):
                answers_by_num[n] = a
            # 新旧都有 correct → 保留更长 solution（带详解）
            elif a.get("correct") and len(a.get("solution","")) > len(cur.get("solution","")):
                answers_by_num[n] = a
    yaml_questions = []
    # 推 mock 目录（先算 yaml_path，便于读已有 qc_status/qc_note 做合并）
    repo_root_pre = out_dir
    while repo_root_pre.parent != repo_root_pre:
        if (repo_root_pre / "knowledge-base").is_dir(): break
        repo_root_pre = repo_root_pre.parent
    _yaml_path_pre = (repo_root_pre / "knowledge-base" / "exams" / "mock"
                       / "english" / "beijing" / f"{slug}.yaml")
    existing_qc: dict[int, dict] = {}
    if _yaml_path_pre.exists():
        try:
            old = Y.safe_load(_yaml_path_pre.read_text(encoding="utf-8")) or {}
            for q in (old.get("questions") or []):
                qid = q.get("id")
                if qid is None: continue
                existing_qc[qid] = {
                    "qc_status": q.get("qc_status", "draft"),
                    "qc_note":   q.get("qc_note", ""),
                }
        except Exception as e:
            print(f"[english_image_paper] ⚠ 读旧 yaml 合并 qc_* 失败: {e}", flush=True)
    for q in result["questions"]:
        n = q["number"]
        a = answers_by_num.get(n, {})
        qtype = TYPE_EN2CN.get(q.get("type"), "解答")
        item: dict = {
            "id": n, "type": qtype, "score": q.get("score", 0),
            "stem": q.get("stem", ""),
        }
        if q.get("options"):
            item["options"] = q["options"]
        if q.get("has_image_options"):
            item["has_image_options"] = True
        if q.get("passage_id"):
            item["passage_id"] = q["passage_id"]
        if q.get("blank_index"):
            item["blank_index"] = q["blank_index"]
        item["answer"] = a.get("correct", "")
        item["solution"] = a.get("solution", "")
        item["knowledge_points"] = []
        item["module"] = ""
        item["difficulty"] = ""
        prev = existing_qc.get(n, {})
        item["qc_status"] = prev.get("qc_status", "draft")
        item["qc_note"] = prev.get("qc_note", "")
        yaml_questions.append(item)

    # 推 mock 目录
    repo_root = out_dir
    while repo_root.parent != repo_root:
        if (repo_root / "knowledge-base").is_dir(): break
        repo_root = repo_root.parent
    mock_dir = repo_root / "knowledge-base" / "exams" / "mock" / "english" / "beijing"
    mock_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = mock_dir / f"{slug}.yaml"

    # passage 处理：image-match 类型 → 4 张 cropped 图作 **passage 共享资源**
    # （image_options 字段，A/B/C/D → 相对路径）。per-question 不再重复 options，
    # 审稿在 passage 卡看 4 张图、在 question 卡看 stem + answer letter。
    yaml_passages = []
    figs_dir = _yaml_path_pre.parent / slug / "figures"
    for ps in result.get("passages", []):
        item_p = {k: v for k, v in ps.items() if not k.startswith("_")}
        if ps.get("_src_page_img"):
            src_p = Path(ps["_src_page_img"])
            figs_dir.mkdir(parents=True, exist_ok=True)
            opt_rels = _crop_image_options(src_p, figs_dir,
                                            prefix=f"passage-{ps['id']}")
            if opt_rels:
                # 4 张图挂到 passage.image_options（共享，不写到 per-question）
                item_p["image_options"] = {
                    k: f"{slug}/figures/{v}" for k, v in opt_rels.items()
                }
        yaml_passages.append(item_p)

    data = {
        "year": year, "district": (region_cn + "区") if region_cn else "",
        "exam_type": type_cn, "subject": "english",
        "full_score": result.get("full_score"),
        "duration_minutes": 90,
        "total_questions": len(yaml_questions),
        "passages": yaml_passages,
        "questions": yaml_questions,
    }
    yaml_path.write_text(
        Y.safe_dump(data, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    print(f"[english_image_paper] ✅ yaml {yaml_path}", flush=True)


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
    # **patch 应用**（_patches/english/<slug>.yaml）
    slug = out_dir.name
    from _patches_applier import load_and_apply_patches
    repo_root = out_dir
    while repo_root.parent != repo_root:
        if (repo_root / "knowledge-base").is_dir(): break
        repo_root = repo_root.parent
    n_patch = load_and_apply_patches(slug, "english", result, repo_root)
    if n_patch:
        print(f"[english_image_paper] 🔧 应用 {n_patch} 处 patch", flush=True)

    fj = structured / "final.json"
    fj.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    qs = result["questions"]; ans = result["answers"]
    print(f"[english_image_paper] ✅ {fj}", flush=True)
    print(f"   题号: {sorted(set(q['number'] for q in qs))}", flush=True)
    print(f"   passages: {len(result['passages'])}  questions: {len(qs)}  "
          f"answers: {len(ans)}  full_score: {result['full_score']}", flush=True)
    _write_yaml(result, src, out_dir)


if __name__ == "__main__":
    main()
