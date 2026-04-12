#!/usr/bin/env python3
"""
docx → HTML → Qwen-VL OCR → LaTeX → YAML 全自动转换 pipeline

用法:
  python3 scripts/docx-pipeline.py                           # 转换所有 docx
  python3 scripts/docx-pipeline.py --file "path/to/exam.docx"  # 转换单个文件
  python3 scripts/docx-pipeline.py --dry-run                  # 只预览，不实际转换
  python3 scripts/docx-pipeline.py --force                    # 强制覆盖已有 YAML

依赖:
  brew install --cask libreoffice
  pip3 install pyyaml beautifulsoup4

环境变量:
  DASHSCOPE_API_KEY  — 阿里云百炼 API Key（Qwen-VL 公式 OCR 用）
"""

import os
import re
import sys
import glob
import json
import time
import hashlib
import base64
import argparse
import subprocess
import urllib.request
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ 缺少 pyyaml: pip3 install pyyaml")
    sys.exit(1)

# ============================================================
# 配置
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "knowledge-original" / "北京中考数学模拟卷"
DST_DIR = ROOT / "knowledge-base" / "mock-exams" / "math" / "beijing"
CACHE_DIR = ROOT / "scripts" / ".ocr-cache"  # OCR 结果缓存

# Qwen-VL API
DASHSCOPE_API_KEY = os.environ.get(
    "DASHSCOPE_API_KEY", "sk-269db71be27b4dcfbedb0c21c382d288"
)
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen-vl-max"

# LibreOffice 路径
SOFFICE_PATHS = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
]

# 并发 OCR 数
OCR_CONCURRENCY = 5
# API 请求间隔（秒），避免限速
OCR_DELAY = 0.2

# 区名 → 英文 key
DISTRICT_MAP = {
    "海淀": "haidian", "西城": "xicheng", "东城": "dongcheng",
    "朝阳": "chaoyang", "丰台": "fengtai", "石景山": "shijingshan",
    "通州": "tongzhou", "大兴": "daxing", "房山": "fangshan",
    "顺义": "shunyi", "门头沟": "mentougou", "密云": "miyun",
    "平谷": "pinggu", "燕山": "yanshan", "延庆": "yanqing",
    "怀柔": "huairou", "昌平": "changping",
}

EXAM_TYPE_MAP = {"一模": "yi", "二模": "er", "三模": "san"}

# 模块关键词
MODULE_KEYWORDS = {
    "numbersAndExpressions": [
        "实数", "有理数", "无理数", "绝对值", "平方根", "立方根", "科学记数法",
        "因式分解", "整式", "分式", "幂", "根式", "多项式", "单项式",
        "数轴", "相反数", "倒数",
    ],
    "equationsAndInequalities": [
        "一元一次方程", "一元二次方程", "二元一次方程", "分式方程",
        "不等式", "不等式组", "方程组", "根的判别式", "韦达定理",
        "增长率", "利润", "行程", "工程问题",
    ],
    "functions": [
        "一次函数", "正比例函数", "反比例函数", "二次函数", "抛物线",
        "函数图象", "函数性质", "自变量", "顶点", "对称轴",
        "k的取值", "解析式", "函数表达式",
    ],
    "triangles": [
        "三角形", "全等", "相似", "勾股定理", "直角三角形",
        "等腰三角形", "等边三角形", "三角函数", "锐角三角函数",
        "中位线", "角平分线", "中线", "高线", "对顶角", "平行线",
        "外角", "内角和",
    ],
    "quadrilaterals": [
        "四边形", "平行四边形", "矩形", "菱形", "正方形", "梯形",
        "中点四边形",
    ],
    "circles": [
        "圆", "圆周角", "圆心角", "切线", "弦", "垂径定理",
        "扇形", "弧长", "圆锥", "内切圆", "外接圆",
    ],
    "statisticsAndProbability": [
        "概率", "统计", "频率", "平均数", "中位数", "众数", "方差",
        "标准差", "频率分布", "直方图", "条形统计图", "折线统计图",
        "扇形统计图", "树状图", "列表法", "随机事件", "样本",
    ],
    "geometryComprehensive": [
        "旋转", "平移", "对称", "轴对称", "中心对称",
        "坐标系", "动点", "最值", "存在性", "几何综合", "新定义",
    ],
}


# ============================================================
# Step 1: LibreOffice docx → HTML
# ============================================================

def find_soffice():
    for p in SOFFICE_PATHS:
        if os.path.isfile(p):
            return p
        # try which
        try:
            result = subprocess.run(["which", p], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
    return None


def docx_to_html(docx_path, output_dir):
    """用 LibreOffice 把 docx 转成 HTML，返回 HTML 文件路径"""
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError("找不到 LibreOffice，请安装: brew install --cask libreoffice")

    os.makedirs(output_dir, exist_ok=True)

    # 检查是否已有 HTML 缓存
    stem = Path(docx_path).stem
    existing_html = list(Path(output_dir).glob("*.html"))
    if existing_html:
        return str(existing_html[0])

    # 杀掉可能残留的 soffice 进程（LibreOffice 只允许单实例）
    subprocess.run(["pkill", "-f", "soffice"], capture_output=True)
    time.sleep(2)
    cmd = [soffice, "--headless", "--convert-to", "html", "--outdir", str(output_dir), str(docx_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice 转换失败: {result.stderr}")

    # 找生成的 HTML 文件
    html_files = list(Path(output_dir).glob("*.html"))
    if not html_files:
        raise RuntimeError(f"未找到生成的 HTML 文件")

    return str(html_files[0])


# ============================================================
# Step 2: HTML 解析 — 提取文本 + 公式图片位置
# ============================================================

class ExamHTMLParser(HTMLParser):
    """解析 LibreOffice 导出的 HTML，提取文本并标记公式图片位置"""

    def __init__(self, html_dir):
        super().__init__()
        self.html_dir = html_dir
        self.segments = []  # [(type, content)] → type: "text" | "formula_img" | "figure_img"
        self._in_body = False
        self._skip = False  # 跳过 style/script 标签

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "body":
            self._in_body = True
            return

        if tag in ("style", "script"):
            self._skip = True
            return

        if not self._in_body or self._skip:
            return

        if tag == "br":
            self.segments.append(("text", "\n"))

        if tag == "p":
            # 段落开始，加换行
            self.segments.append(("text", "\n"))

        if tag == "img":
            src = attrs_dict.get("src", "")
            name = attrs_dict.get("name", "")
            width = int(attrs_dict.get("width", 0) or 0)
            height = int(attrs_dict.get("height", 0) or 0)

            # 解码 URL 编码的文件名
            from urllib.parse import unquote
            src_decoded = unquote(src)
            img_path = os.path.join(self.html_dir, src_decoded)

            if src.endswith(".gif") or name.startswith("Object"):
                # 公式图片 → 需要 OCR
                self.segments.append(("formula_img", img_path))
            elif src.endswith(".png") or src.endswith(".jpg"):
                # 题图/几何图形
                if width > 30 and height > 30:
                    self.segments.append(("figure_img", img_path))
                else:
                    # 很小的图可能也是公式
                    self.segments.append(("formula_img", img_path))

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip = False

    def handle_data(self, data):
        if self._in_body and not self._skip:
            text = data.strip()
            if text:
                self.segments.append(("text", text))


def parse_html(html_path):
    """解析 HTML 文件，返回 segments 列表"""
    html_dir = os.path.dirname(html_path)
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        html_content = f.read()

    parser = ExamHTMLParser(html_dir)
    parser.feed(html_content)
    return parser.segments


# ============================================================
# Step 3: Qwen-VL 公式 OCR
# ============================================================

OCR_PROMPT = """请将图片中的数学公式转为LaTeX。规则：
1. 只输出LaTeX代码，不要任何解释、不要```包裹
2. 这是中国初中数学题，注意区分π(pi)和x
3. 常见符号：∠→\\angle, △→\\triangle, ∴→\\therefore, ∵→\\because, ≅→\\cong, ⊥→\\perp, ∥→\\parallel
4. 如果是纯文字或简单字母/数字，直接输出原文
5. 不要加$符号包裹"""


def get_image_hash(img_path):
    """计算图片文件 hash，用于缓存"""
    with open(img_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def load_ocr_cache():
    """加载 OCR 缓存"""
    cache_file = CACHE_DIR / "ocr-results.json"
    if cache_file.exists():
        with open(cache_file, "r") as f:
            return json.load(f)
    return {}


def save_ocr_cache(cache):
    """保存 OCR 缓存"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "ocr-results.json"
    with open(cache_file, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def ocr_single_image(img_path, cache):
    """OCR 单张公式图片，有缓存"""
    if not os.path.exists(img_path):
        return f"[图片缺失: {os.path.basename(img_path)}]"

    img_hash = get_image_hash(img_path)
    if img_hash in cache:
        return cache[img_hash]

    # 读取图片并 base64 编码
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    ext = img_path.rsplit(".", 1)[-1].lower()
    mime_map = {"gif": "image/gif", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
    mime = mime_map.get(ext, "image/png")

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
        "max_tokens": 300,
    }

    req = urllib.request.Request(
        DASHSCOPE_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            latex = result["choices"][0]["message"]["content"].strip()
            # 清理：去除可能的 $ 包裹和 ``` 包裹
            latex = re.sub(r'^```\w*\n?', '', latex)
            latex = re.sub(r'\n?```$', '', latex)
            latex = latex.strip("$ \n")
            cache[img_hash] = latex
            return latex
    except Exception as e:
        return f"[OCR失败: {e}]"


def batch_ocr(formula_images, cache):
    """批量 OCR 公式图片，带并发和缓存"""
    # 去重（同一图片可能出现多次）
    unique_paths = list(set(formula_images))

    # 统计缓存命中
    to_ocr = []
    for p in unique_paths:
        if os.path.exists(p):
            h = get_image_hash(p)
            if h not in cache:
                to_ocr.append(p)

    cached_count = len(unique_paths) - len(to_ocr)
    print(f"    公式图片: {len(unique_paths)} 张（缓存命中 {cached_count}，需 OCR {len(to_ocr)}）")

    if not to_ocr:
        return

    done = 0
    with ThreadPoolExecutor(max_workers=OCR_CONCURRENCY) as pool:
        futures = {}
        for p in to_ocr:
            time.sleep(OCR_DELAY)  # 简单限速
            f = pool.submit(ocr_single_image, p, cache)
            futures[f] = p

        for f in as_completed(futures):
            done += 1
            path = futures[f]
            try:
                result = f.result()
            except Exception as e:
                print(f"      ⚠️ OCR 异常: {os.path.basename(path)}: {e}")
            if done % 20 == 0:
                print(f"      OCR 进度: {done}/{len(to_ocr)}")
                save_ocr_cache(cache)  # 定期保存

    save_ocr_cache(cache)


# ============================================================
# Step 4: 组装纯文本（公式用 $LaTeX$ 替换）
# ============================================================

def assemble_text(segments, cache):
    """把 HTML segments 组装成带 LaTeX 的纯文本"""
    parts = []
    for seg_type, content in segments:
        if seg_type == "text":
            parts.append(content)
        elif seg_type == "formula_img":
            if os.path.exists(content):
                img_hash = get_image_hash(content)
                latex = cache.get(img_hash, "[公式]")
                # 如果 LaTeX 很短且是纯字母，不加 $ 包裹
                if re.match(r'^[A-Za-z]{1,3}$', latex):
                    parts.append(latex)
                else:
                    parts.append(f"${latex}$")
            else:
                parts.append("[公式]")
        elif seg_type == "figure_img":
            parts.append("[图]")

    text = "".join(parts)
    # 清理多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ============================================================
# Step 5: 解析题目结构
# ============================================================

def get_difficulty(qid, q_type):
    if q_type == "选择":
        if qid <= 5: return "基础"
        elif qid <= 7: return "中档"
        else: return "较难"
    elif q_type == "填空":
        real_id = qid - 8
        if real_id <= 4: return "基础"
        elif real_id <= 7: return "中档"
        else: return "较难"
    else:
        if qid <= 19: return "基础"
        elif qid <= 22: return "中档"
        elif qid <= 25: return "较难"
        else: return "压轴"


def get_recommended_for(difficulty):
    return {
        "基础": ["L0", "L1", "L2", "L3"],
        "中档": ["L1", "L2", "L3"],
        "较难": ["L2", "L3"],
        "压轴": ["L3"],
    }.get(difficulty, ["L1", "L2", "L3"])


def get_score(qid, q_type):
    if q_type in ("选择", "填空"):
        return 2
    return {17: 5, 18: 5, 19: 5, 20: 5, 21: 5, 22: 5,
            23: 6, 24: 6, 25: 6, 26: 6, 27: 7, 28: 7}.get(qid, 5)


def detect_module(analysis_text, question_text):
    combined = analysis_text + " " + question_text
    scores = {}
    for module, keywords in MODULE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[module] = score
    if not scores:
        return "geometryComprehensive"
    return max(scores, key=scores.get)


def extract_knowledge_points(analysis, question):
    combined = analysis + " " + question
    kp_candidates = [
        "中心对称图形", "轴对称图形", "对顶角", "邻补角", "平行线",
        "因式分解", "分式方程", "一元二次方程", "二元一次方程组",
        "一次函数", "反比例函数", "二次函数", "正比例函数",
        "概率", "树状图", "列表法", "频率", "统计",
        "平均数", "中位数", "众数", "方差",
        "圆周角", "垂径定理", "切线", "弦",
        "全等三角形", "相似三角形", "勾股定理",
        "平行四边形", "矩形", "菱形", "正方形",
        "旋转", "平移", "轴对称",
        "根的判别式", "韦达定理",
        "三角函数", "锐角三角函数",
        "科学记数法", "绝对值",
        "不等式", "不等式组",
        "坐标系", "动点", "最值",
        "扇形统计图", "条形统计图", "尺规作图",
    ]
    found = [kp for kp in kp_candidates if kp in combined]
    return found if found else ["综合"]


def parse_questions(text):
    """解析纯文本中的题目结构"""
    questions = []
    current_q = None
    current_section = None
    current_type = None

    q_pattern = re.compile(r'^(\d+)[.．、]\s*(.*)', re.DOTALL)
    answer_pattern = re.compile(r'【答案】(.*)')
    analysis_marker = re.compile(r'【(分析|解析)】(.*)')
    detail_marker = re.compile(r'【详解】(.*)')
    subq_marker = re.compile(r'【?小问\d+详解】?(.*)')

    # 跳过试卷头部（注意事项、考试说明等），直到遇到题型标记或第1题
    header_done = False
    HEADER_SKIP_KEYWORDS = [
        "本试卷", "注意事项", "答题卡", "草稿纸", "考试结束",
        "准确填写", "一律填涂", "2B铅笔", "黑色字迹", "签字笔",
        "考试时间", "满分", "共8页", "共三道", "九年级",
    ]

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 跳过试卷头部
        if not header_done:
            if any(kw in line for kw in HEADER_SKIP_KEYWORDS):
                continue
            # 遇到题型标记或题号，说明正文开始
            if re.match(r'^[一二三]、', line) or re.match(r'^第[一二三]部分', line) or q_pattern.match(line):
                header_done = True
            else:
                continue  # 其他头部内容也跳过

        # 检测题型切换
        if "选择题" in line and ("一、" in line or "第一部分" in line):
            current_type = "选择"
            continue
        if "填空题" in line and ("二、" in line or "第二部分" in line):
            current_type = "填空"
            continue
        if "解答题" in line and "三、" in line:
            current_type = "解答"
            continue
        if line.startswith("第二部分") and "非选择题" in line:
            continue

        # 匹配新题目
        m = q_pattern.match(line)
        if m:
            qid = int(m.group(1))
            qtext = m.group(2)

            # 过滤无效题号
            # 1) 范围检查：北京中考最多28题
            if qid < 1 or qid > 28:
                if current_q and current_section:
                    if current_section == "question":
                        current_q["question"] += "\n" + line
                    elif current_section == "detail":
                        current_q["detail"] += "\n" + line
                    elif current_section == "analysis":
                        current_q["analysis"] += "\n" + line
                continue

            # 2) 内容检查：题目文本太短的是表格数据，不是真题目
            #    真实题目至少有几个汉字或完整的数学表达式
            has_chinese = bool(re.search(r'[\u4e00-\u9fff]{2,}', qtext))
            has_math = '$' in qtext or '\\' in qtext
            has_option = bool(re.search(r'[A-D][.．、]', qtext))
            is_real_question = has_chinese or has_math or has_option or len(qtext) > 15
            if not is_real_question:
                # 这只是表格里的数字，不是新题目
                if current_q and current_section:
                    if current_section == "question":
                        current_q["question"] += "\n" + line
                    elif current_section == "detail":
                        current_q["detail"] += "\n" + line
                    elif current_section == "analysis":
                        current_q["analysis"] += "\n" + line
                continue

            # 3) ID 必须递增（允许等于，用于去重逻辑）
            if current_q and qid < current_q["id"] and qid != 1:
                # ID 回退，说明进入了重复区域（原卷+解析双份）
                # 后面的内容全部忽略
                if current_section and current_q:
                    if current_section == "question":
                        current_q["question"] += "\n" + line
                    elif current_section == "detail":
                        current_q["detail"] += "\n" + line
                continue

            if current_type is None:
                if qid <= 8: current_type = "选择"
                elif qid <= 16: current_type = "填空"
                else: current_type = "解答"
            elif qid == 9:
                current_type = "填空"
            elif qid == 17:
                current_type = "解答"

            if current_q:
                questions.append(current_q)

            current_q = {
                "id": qid, "type": current_type or "解答",
                "question": qtext, "answer": "", "analysis": "", "detail": "",
            }
            current_section = "question"
            continue

        if current_q is None:
            continue

        m = answer_pattern.match(line)
        if m:
            current_q["answer"] = m.group(1).strip()
            current_section = "answer"
            continue

        m = analysis_marker.match(line)
        if m:
            current_q["analysis"] = m.group(2).strip()
            current_section = "analysis"
            continue

        m = detail_marker.match(line)
        if m:
            current_q["detail"] = m.group(1).strip()
            current_section = "detail"
            continue

        m = subq_marker.match(line)
        if m:
            current_q["detail"] += "\n" + line
            current_section = "detail"
            continue

        if line.startswith("【点睛】"):
            current_q["analysis"] += "\n" + line.replace("【点睛】", "").strip()
            current_section = "analysis"
            continue

        # 累加到当前段落
        if current_section == "question":
            current_q["question"] += "\n" + line
        elif current_section == "answer":
            current_q["answer"] += " " + line
        elif current_section == "analysis":
            current_q["analysis"] += "\n" + line
        elif current_section == "detail":
            current_q["detail"] += "\n" + line

    if current_q:
        questions.append(current_q)

    # 去重：解析版文件可能包含"原卷+解析"两遍内容
    # 策略：只保留每个题号的第一次出现（通常带有答案的那个）
    seen_ids = set()
    deduped = []
    for q in questions:
        qid = q["id"]
        if qid in seen_ids:
            # 如果之前的版本没答案但这个有，替换
            for i, existing in enumerate(deduped):
                if existing["id"] == qid and not existing["answer"] and q["answer"]:
                    deduped[i] = q
                    break
            continue
        seen_ids.add(qid)
        deduped.append(q)

    return deduped


# ============================================================
# Step 6: 输出 YAML
# ============================================================

def build_yaml(questions, year, district_cn, exam_type_cn):
    yaml_questions = []
    for q in questions:
        qid = q["id"]
        qtype = q["type"]
        difficulty = get_difficulty(qid, qtype)
        question_text = q["question"].strip()
        answer_text = q["answer"].strip()
        analysis_text = q["analysis"].strip()
        detail_text = q["detail"].strip()
        module = detect_module(analysis_text, question_text)
        kps = extract_knowledge_points(analysis_text, question_text)

        yaml_q = {
            "id": qid,
            "type": qtype,
            "score": get_score(qid, qtype),
            "question": question_text if len(question_text) > 5 else f"（第{qid}题，详见原卷）",
            "answer": answer_text,
            "solution": detail_text[:800] if detail_text else "",
            "knowledge_points": kps,
            "module": module,
            "difficulty": difficulty,
            "recommended_for": get_recommended_for(difficulty),
        }
        yaml_questions.append(yaml_q)

    district_label = f"{district_cn}区" if not district_cn.endswith(("区", "山")) else district_cn
    return {
        "year": int(year),
        "district": district_label,
        "exam_type": exam_type_cn,
        "subject": "数学",
        "full_score": 100,
        "duration_minutes": 120,
        "total_questions": len(yaml_questions),
        "structure": "8选择(16分) + 8填空(16分) + 12解答(68分)",
        "questions": yaml_questions,
    }


# ============================================================
# 文件扫描
# ============================================================

def find_all_exams():
    """扫描所有 docx 文件"""
    results = []
    for batch_dir in sorted(os.listdir(SRC_DIR)):
        batch_path = SRC_DIR / batch_dir
        if not batch_path.is_dir() or batch_dir.startswith("."):
            continue

        year_match = re.search(r'(202\d)', batch_dir)
        if not year_match:
            continue
        year = year_match.group(1)

        exam_type_cn = None
        for et in ["一模", "二模", "三模"]:
            if et in batch_dir:
                exam_type_cn = et
                break
        if not exam_type_cn:
            continue

        for exam_dir in sorted(os.listdir(batch_path)):
            exam_path = batch_path / exam_dir
            if not exam_path.is_dir() or exam_dir.startswith("."):
                continue

            district_cn = None
            for d in DISTRICT_MAP:
                if d in exam_dir:
                    district_cn = d
                    break
            if not district_cn:
                continue

            # 优先选"解析版"，避免选到"原卷版"（两者都含"精品解析"前缀）
            docx_files = [f for f in os.listdir(exam_path) if f.endswith(".docx")]
            # 优先级：解析版 > 含"解析"的 > 任意docx
            chosen = None
            for f in docx_files:
                if "解析版" in f:
                    chosen = f
                    break
            if not chosen:
                for f in docx_files:
                    if "解析" in f and "原卷" not in f:
                        chosen = f
                        break
            if not chosen and docx_files:
                chosen = docx_files[0]

            if chosen:
                results.append({
                    "year": year,
                    "district_cn": district_cn,
                    "district_en": DISTRICT_MAP[district_cn],
                    "exam_type_cn": exam_type_cn,
                    "exam_type_en": EXAM_TYPE_MAP[exam_type_cn],
                    "docx_path": str(exam_path / chosen),
                })
    return results


# ============================================================
# 主流程
# ============================================================

def convert_single(docx_path, year, district_cn, district_en, exam_type_cn, exam_type_en,
                   cache, force=False, dry_run=False):
    """转换单个 docx 文件"""
    yaml_filename = f"{year}-{district_en}-{exam_type_en}.yaml"
    yaml_path = DST_DIR / yaml_filename

    if yaml_path.exists() and not force:
        print(f"  [跳过] {yaml_filename} 已存在")
        return "skipped"

    if dry_run:
        print(f"  [预览] {year} {district_cn} {exam_type_cn} → {yaml_filename}")
        return "dry_run"

    print(f"  [转换] {year} {district_cn} {exam_type_cn} → {yaml_filename}")

    try:
        # Step 1: docx → HTML
        tmp_dir = f"/tmp/docx-pipeline/{year}-{district_en}-{exam_type_en}"
        print(f"    Step 1: LibreOffice 转 HTML...")
        html_path = docx_to_html(docx_path, tmp_dir)

        # Step 2: 解析 HTML
        print(f"    Step 2: 解析 HTML...")
        segments = parse_html(html_path)

        # 收集所有公式图片
        formula_images = [s[1] for s in segments if s[0] == "formula_img"]

        # Step 3: 批量 OCR
        if formula_images:
            print(f"    Step 3: Qwen-VL 公式 OCR...")
            batch_ocr(formula_images, cache)

        # Step 4: 组装纯文本
        print(f"    Step 4: 组装 LaTeX 文本...")
        full_text = assemble_text(segments, cache)

        # Step 5: 解析题目
        print(f"    Step 5: 解析题目结构...")
        questions = parse_questions(full_text)
        print(f"    解析到 {len(questions)} 道题")

        if len(questions) < 10:
            print(f"    ⚠️ 题目数量偏少，可能存在解析问题")

        # Step 6: 生成 YAML
        data = build_yaml(questions, year, district_cn, exam_type_cn)

        header = f"""# ============================================================
# {year}年北京{district_cn}区中考数学{exam_type_cn}试卷 — 逐题分析
# ============================================================
# 数据来源: knowledge-original docx (LibreOffice HTML + Qwen-VL OCR)
# 公式格式: LaTeX（通过 Qwen-VL 视觉模型从 MathType 公式图片识别）
# 满分：100分  时长：120分钟

"""
        yaml_content = yaml.dump(data, allow_unicode=True, default_flow_style=False,
                                  width=200, sort_keys=False)

        DST_DIR.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(header + yaml_content)

        print(f"    ✅ 完成: {len(questions)} 题 → {yaml_filename}")
        return "success"

    except Exception as ex:
        print(f"    ❌ 失败: {ex}")
        import traceback
        traceback.print_exc()
        return "failed"


def main():
    parser = argparse.ArgumentParser(description="docx → LaTeX YAML 全自动转换")
    parser.add_argument("--file", help="转换单个 docx 文件")
    parser.add_argument("--year", help="指定年份（配合 --file 使用）")
    parser.add_argument("--district", help="指定区名中文（配合 --file 使用）")
    parser.add_argument("--exam-type", help="指定考试类型：一模/二模/三模（配合 --file 使用）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不实际转换")
    parser.add_argument("--force", action="store_true", help="强制覆盖已有 YAML")
    parser.add_argument("--limit", type=int, help="限制转换数量（调试用）")
    args = parser.parse_args()

    print("=" * 60)
    print("📄 docx → LaTeX YAML 全自动转换 Pipeline")
    print("=" * 60)

    # 加载 OCR 缓存
    cache = load_ocr_cache()
    print(f"OCR 缓存: {len(cache)} 条")

    if args.file:
        # 单文件模式
        if not os.path.exists(args.file):
            print(f"❌ 文件不存在: {args.file}")
            sys.exit(1)

        year = args.year or "2025"
        district_cn = args.district or "海淀"
        exam_type_cn = args.exam_type or "一模"
        district_en = DISTRICT_MAP.get(district_cn, "unknown")
        exam_type_en = EXAM_TYPE_MAP.get(exam_type_cn, "yi")

        convert_single(args.file, year, district_cn, district_en,
                       exam_type_cn, exam_type_en, cache,
                       force=args.force, dry_run=args.dry_run)
    else:
        # 批量模式
        exams = find_all_exams()
        priority = {"海淀", "西城", "东城", "朝阳"}
        exams.sort(key=lambda e: (0 if e["district_cn"] in priority else 1,
                                   -int(e["year"]), e["exam_type_en"]))

        print(f"\n找到 {len(exams)} 套区级统考卷")

        if args.limit:
            exams = exams[:args.limit]
            print(f"限制转换前 {args.limit} 套")

        stats = {"success": 0, "failed": 0, "skipped": 0}
        for i, exam in enumerate(exams, 1):
            print(f"\n[{i}/{len(exams)}]")
            result = convert_single(
                exam["docx_path"], exam["year"],
                exam["district_cn"], exam["district_en"],
                exam["exam_type_cn"], exam["exam_type_en"],
                cache, force=args.force, dry_run=args.dry_run,
            )
            stats[result] = stats.get(result, 0) + 1

            # 每转换5套保存一次缓存
            if i % 5 == 0:
                save_ocr_cache(cache)

        save_ocr_cache(cache)

        print(f"\n{'=' * 60}")
        print(f"转换完成: 成功 {stats['success']}，失败 {stats['failed']}，跳过 {stats['skipped']}")
        print(f"OCR 缓存: {len(cache)} 条")
        print(f"输出目录: {DST_DIR}")


if __name__ == "__main__":
    main()
