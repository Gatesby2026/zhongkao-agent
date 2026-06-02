#!/usr/bin/env python3
"""试卷结构化数据 → knowledge-base YAML（含 LLM 知识点标注）

支持两种输入格式：
  新格式（推荐）：--input knowledge-base/exams/_staging/<subject>/<slug>/structured-cloud/final.json
  旧格式（兼容）：--paper paper.json --answer-key answer-key.json [--exam-meta exam-meta.json]

输出：knowledge-base/exams/mock/<subject>/beijing/<slug>.yaml（figures 复制到 <slug>/figures/ 旁）

YAML schema（每题）：
  id, type, score, stem, options, has_image_options,
  answer, solution, knowledge_points, module, difficulty,
  recommended_for, qc_status, qc_note

qc_status 说明：
  draft        — 机器生成，无已知结构问题，待人工抽查
  needs_review — 机器生成，有已知问题（图片选项/答案缺失/solution缺失）
  verified     — 人工确认无误（由 tools/exam-review/ 写入）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import openai
    import yaml
except ImportError:
    print("pip install openai pyyaml", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[2]

# ─── 类型映射 ─────────────────────────────────────────────────────────────────

TYPE_MAP = {
    "choice":       "单选",
    "multi_choice": "多选",
    "fill_blank":   "填空",
    "calculation":  "计算",
    "experiment":   "实验探究",
    "essay":        "作文",          # 语文 essay 作文（之前误标"解答"）
    "problem_solving": "解答",       # 数学 docx 路线用此 type
    # 语文专用 type（chinese_docx_paper.py 产出）
    "handwriting":           "书写",
    "subjective_blank":      "主观填空",
    "dictation":             "默写",
    "appreciation":          "古诗赏析",
    "comprehension":         "现代文阅读",     # 现代文 section 专用
    "poem_comprehension":    "古诗内容理解",    # 古诗 section 内容理解（区分现代文）
    "classical_comprehension": "文言文综合理解",  # 文言文 section（区分现代文）
    "book_review":           "名著阅读",
    # 物理专用 type（physics_docx_paper.py 产出）
    "multi_choice":          "多选",
    "experiment":            "实验探究",
    "comprehensive":         "科普阅读",
    "calculation":           "计算题",
    # 道法专用 type（politics_docx_paper.py 产出）
    "judge":     "判断",
    "material":  "材料分析",
    # essay 已存在（语文作文复用）; 道法的 essay 是写作题，sub-type 由 stem 区分
    # 兼容旧格式中文 key
    "单选": "单选", "多选": "多选", "填空": "填空",
    "计算": "计算", "实验探究": "实验探究", "解答": "解答",
    "作文": "作文", "书写": "书写", "默写": "默写",
    "古诗赏析": "古诗赏析", "现代文阅读": "现代文阅读", "名著阅读": "名著阅读",
}

EXAM_TYPE_MAP = {
    "yimo": "一模", "一模": "一模",
    "ermo": "二模", "二模": "二模",
    "zhongkao": "真题", "中考": "真题",
    "qizhong": "期中", "qimo": "期末",
}

SOLUTION_REQUIRED = {"计算", "解答", "实验探究"}

# ─── 学科 modules ─────────────────────────────────────────────────────────────

SUBJECT_MODULES: dict[str, list[str]] = {
    "physics": ["soundLightHeat", "mechanics", "electricity", "experiments"],
    "math": [
        "numbersAndExpressions", "equationsAndInequalities", "functions",
        "triangles", "quadrilaterals", "circles", "geometryComprehensive",
        "statisticsAndProbability",
        # **R5.2**：北京中考 Q28 压轴必为「新定义」题（创新概念 + 抽象推理），
        # 之前 module list 缺 → Q28 落到 geometryComprehensive 错档。
        "newDefinition",
    ],
    "chinese":  ["reading", "writing", "classical", "chinese"],
    "english":  ["vocabulary", "grammar", "reading", "listening", "writing"],
    # **R5.5**：道法 8 模块（按教材划分），替换之前的单 "politics" 占位。
    # 之前所有题落"道法综合"，模块级聚合无信息量。
    "politics": [
        "ideology",            # 思想理论（中国梦/中国特色社会主义/强国建设）
        "ruleOfLaw",           # 法治教育（宪法/法治/公民权利义务/法律作用）
        "morality",            # 道德教育（诚信/友善/责任/爱国/集体/家庭美德）
        "mentalHealth",        # 心理健康（自我认识/情绪/抗挫/批判性思维）
        "nationSociety",       # 国家与社会（民族团结/国家安全/生态文明）
        "civicParticipation",  # 公民参与（民主/人大/基层自治/政治参与）
        "economy",             # 经济发展（创新/对外开放/共同富裕/乡村振兴）
        "chineseCulture",      # 中华文化（传承/文化自信/民族精神）
    ],
    "history":  ["history"],
    "geography": ["geography"],
    "biology":  ["biology"],
    "chemistry": ["chemistry"],
}
# 中文学科名 alias
_SUBJECT_ALIAS = {
    "物理": "physics", "数学": "math", "语文": "chinese",
    "英语": "english", "道法": "politics", "道德与法治": "politics",
    "历史": "history", "地理": "geography", "生物": "biology", "化学": "chemistry",
}


def _subject_en(subject: str) -> str:
    return _SUBJECT_ALIAS.get(subject, subject)


def _modules(subject: str) -> list[str]:
    return SUBJECT_MODULES.get(_subject_en(subject), [])


# ─── 输入格式归一化 ───────────────────────────────────────────────────────────

class NormalizedPaper:
    """将新旧两种输入格式统一为内部结构，供 enrich 使用。"""

    def __init__(self):
        self.exam_name: str = ""
        self.year: int | None = None
        self.district: str = ""
        self.exam_type: str = "真题"
        self.subject: str = ""
        self.full_score: int | None = None
        self.duration: int | None = None
        self.paper_dir: Path | None = None   # 原始试卷目录（用于定位 figures/）
        # [{id, number, type_en, score, stem, options, has_image_options, figure_path}]
        self.questions: list[dict] = []
        # {number: {correct, solution}}
        self.answers: dict[int, dict] = {}
        # 阅读理解/古诗文/资料类共享文章。元素 schema：
        #   {id, type, name?, q_range:[lo,hi], body, figure?, image_options?}
        # 题级通过 question.passage_id 关联（按 q_range 自动推断或显式指定）。
        # 语文/英语含 passage 二级模型；数学/物理通常为空 []
        self.passages: list[dict] = []

    # ── 新格式：final.json ──

    @classmethod
    def from_final(cls, data: dict, subject_hint: str = "",
                   paper_dir: Path | None = None) -> "NormalizedPaper":
        p = cls()
        p.exam_name = data.get("exam", "")
        p.subject = data.get("subject", subject_hint)
        p.paper_dir = paper_dir
        # 卷面元数据（v2 流水线从 OCR 头部抽取写入 final.json）
        p.full_score = data.get("full_score")
        p.duration = data.get("duration_minutes")
        # 优先用 final.json 已显式注入的 year/district/exam_type（chinese_docx_paper.py 已写）
        if data.get("year") is not None:    p.year = data["year"]
        if data.get("district"):            p.district = data["district"]
        if data.get("exam_type"):           p.exam_type = data["exam_type"]

        # 兜底：从 exam 名称解析元数据
        if not p.year or not p.district:
            _parse_exam_name(p)

        for q in data.get("questions", []):
            num = q.get("number", 0)
            opts = q.get("options")
            # options 若是旧式 list，转成 dict
            if isinstance(opts, list):
                opts = {o["label"]: o.get("text", "") for o in opts if "label" in o}
            p.questions.append({
                "id":               q.get("id", f"Q{num}"),
                "number":           num,
                "type_en":          q.get("type", "essay"),
                "score":            q.get("score", 2),
                "stem":             q.get("stem", ""),
                "options":          opts,
                "has_image_options": q.get("has_image_options", False),
                "figure_path":      q.get("figure_path"),   # e.g. "figures/q06.png"
                "figures_all":      q.get("figures_all") or [],  # 多图保留（数学图选项 A-D / 题目内嵌多图）
                "source_pages":     [f"page-{q['source_page']:02d}"]
                                    if q.get("source_page") else [],
                "section":          q.get("section", ""),
                "solution":         q.get("solution", ""),
            })

        for a in data.get("answers", []):
            num = a.get("number", 0)
            p.answers[num] = {
                "correct":  str(a.get("correct", "")),
                "solution": str(a.get("solution", "")),
            }

        # passages（语文/英语 二级模型；数学/物理通常无）
        for ps in data.get("passages", []) or []:
            p.passages.append(dict(ps))

        return p

    # ── 旧格式：paper.json + answer-key.json ──

    @classmethod
    def from_legacy(cls,
                    paper: dict,
                    answer_key: dict,
                    exam_meta: dict | None = None) -> "NormalizedPaper":
        p = cls()
        meta = paper.get("meta", {})
        exam = meta.get("exam", {})
        em = exam_meta or {}

        p.year = em.get("year") or exam.get("year")
        raw_district = em.get("district") or exam.get("district", "")
        p.district = raw_district + ("区" if raw_district and not raw_district.endswith("区") else "")
        p.exam_type = EXAM_TYPE_MAP.get(
            em.get("examType") or exam.get("examType", ""), "真题"
        )
        p.subject = em.get("subject") or exam.get("subject", "")
        p.full_score = meta.get("totalScore")
        p.duration = meta.get("duration")

        # 旧 answer-key：以 id 为 key
        ak_by_id = {
            a["id"]: a
            for a in answer_key.get("answers", [])
            if isinstance(a, dict) and "id" in a
        }

        for q in paper.get("questions", []):
            qid = q.get("id", "")
            num = _parse_qnum(qid)
            ak = ak_by_id.get(qid, {})
            score = q.get("score") or ak.get("score") or 2

            # 旧 stem 可能含选项行，尝试拆分
            stem_raw = q.get("stem", "")
            opts_list = q.get("options")  # 旧格式为 list[{label, text}]
            opts_dict: dict | None = None
            has_img = False

            if isinstance(opts_list, list) and opts_list:
                opts_dict = {o["label"]: o.get("text", "") for o in opts_list if "label" in o}
                has_img = all(v == "" or v == "[图]" for v in opts_dict.values())
            elif isinstance(opts_list, dict):
                opts_dict = opts_list
                has_img = all(v == "[图]" for v in opts_dict.values()) if opts_dict else False

            # 从 stem 中去除已嵌入的选项行（旧格式的遗留问题）
            stem = _strip_options_from_stem(stem_raw) if opts_dict else stem_raw

            # 旧 answer-key
            correct = ak.get("correct", "")
            if isinstance(correct, list):
                correct = "".join(correct) if all(len(c) == 1 for c in correct) else "；".join(str(c) for c in correct)
            else:
                correct = str(correct) if correct else ""

            p.answers[num] = {
                "correct":  correct,
                "solution": ak.get("correctSolution", ""),
            }
            p.questions.append({
                "id":               qid,
                "number":           num,
                "type_en":          q.get("type", "essay"),
                "score":            score,
                "stem":             stem,
                "options":          opts_dict,
                "has_image_options": has_img,
                "source_pages":     q.get("sourcePages", []),
            })

        return p


def _parse_qnum(qid: str) -> int:
    """'Q12' → 12, 'physics-q03' → 3, '5' → 5"""
    m = re.search(r"(\d+)", qid)
    return int(m.group(1)) if m else 0


def _parse_exam_name(p: "NormalizedPaper") -> None:
    """从 exam_name 字符串里解析 year / district / exam_type。"""
    name = p.exam_name
    m = re.search(r"(\d{4})", name)
    if m:
        p.year = int(m.group(1))
    # 只取 "XX区" 区名本体。北京 13 区名都是 2-3 中文字（朝阳/海淀/西城/
    # 东城/丰台/石景山/房山/通州/顺义/大兴/昌平/平谷/燕山/门头沟/怀柔/密云/延庆）。
    # 用锚定的 "北京市?" 前缀剥掉年份/省市前缀，否则
    # "2026年北京市朝阳区中考..." 会被贪婪 [^\s]+区 捕成 "2026年北京市朝阳区"
    m = re.search(r"北京市?([一-龥]{2,3}区)", name)
    if not m:
        m = re.search(r"([一-龥]{2,3}区)", name)
    if m:
        p.district = m.group(1)
    for k, v in EXAM_TYPE_MAP.items():
        if k in name:
            p.exam_type = v
            break


def _strip_options_from_stem(stem: str) -> str:
    """从旧格式的 stem 字符串末尾去掉已嵌入的 A/B/C/D 选项行。"""
    return re.sub(r"\n+[A-D][\.、．]\s*.*$", "", stem, flags=re.DOTALL).strip()


# ─── enrich prompt ───────────────────────────────────────────────────────────

ENRICH_SYSTEM = (
    "你是中考命题专家。任务：给定一道题及其标准答案，标注其在课标知识点体系中的位置 + 难度。\n"
    "风格：精确、对照课标用词、避免重复造词。中文输出。"
)

ENRICH_USER_TEMPLATE = """\
请为下面这道题标注知识库元数据：

# 学科
{subject}

# 题号 / 题型 / 满分
{qid}（{qtype}，{score} 分）

# 大题归属（**重要**，知识点必须对应该 section 内容）
{section_hint}

# 题干
{stem}

# 选项（如有）
{options_text}

# 标准答案
{answer}

# 该学科可选 module（只能从这里选 1 个）
{modules_str}

# 课标知识点参考（节选）
{curriculum_excerpt}

输出 JSON（直接输出，不要 markdown 包裹）：
{{
  "knowledge_points": ["1-3个，命名对齐课标"],
  "module": "必须从给定列表选1个",
  "difficulty": "基础|中等|能力",
  "recommended_for": ["L0","L1","L2","L3"]
}}

规则：
- **knowledge_points 必须对应「大题归属」**：
  - section=base（基础·运用）→ 字音/字形/成语运用/病句/词语运用/连贯/书写
  - section=classical（古诗文阅读）→ 默写/古诗赏析/古诗内容理解/文言文实词/文言文翻译/文言文理解
  - section=book_review（名著阅读）→ 名著情节/人物形象/主题理解
  - section=modern（现代文阅读）→ 综合题型对应 KP：
      * 选择"不符合文意"/判断 → 信息筛选
      * 概括内容/梳理思路 → 信息提取/段落梳理
      * 词语含义解释（解释某词在某段含义）→ 词语含义
      * 句式赏析/修辞/表达效果 → 句式赏析/修辞手法/表达效果
      * 段落作用/开头作用/结尾作用 → 段落作用
      * 论证过程/论证方法 → 论证分析
      * 写出启示/谈感悟 → 启示感悟
      * 记叙文文体 → 记叙文阅读；议论文 → 议论文阅读；说明文 → 说明文阅读
  - section=essay（作文）→ 命题作文/材料作文/半命题作文
  - **物理 section 专用 KP 范围**：
    - section=choice / multi_choice（单/多选）→ 按物理具体考点：
      * 力学：力的概念/二力平衡/牛顿定律/压强/浮力/简单机械
      * 电学：电流/电压/电阻/欧姆定律/电功电功率/电与磁
      * 光学：光的反射/折射/平面镜成像/凸透镜成像
      * 热学：温度/比热容/热量计算/物态变化
      * 能源：能量转化/能源类型/可再生
      * 声学：声音的产生与传播/响度音调音色
      * 物质：导体绝缘体/质量密度/分子热运动
    - section=experiment（实验探究）→ 实验方法/数据处理 + 具体实验
      （测密度/测电阻/欧姆定律/平面镜成像/熔化/凸透镜）
    - section=comprehensive（科普阅读）→ 综合应用 + 材料涉及考点
    - section=calculation（计算题）→ 公式综合应用（如 电功率+欧姆定律 / 压强+浮力）
  - **道法 section 专用 KP 范围 + module 映射**（按教材 8 模块，KP 决定 module）：
    - 思想理论 (module=ideology)：中国梦/中国特色社会主义新时代/强国建设/十四五十五五/全面建成小康社会
    - 法治教育 (module=ruleOfLaw)：宪法地位/依法治国/公民基本权利/公民基本义务/法律的作用/法治社会
    - 道德教育 (module=morality)：诚信/友善/责任意识/爱国主义/集体主义/社会公德/家庭美德
    - 心理健康 (module=mentalHealth)：自我认识/情绪调节/抗挫折/独立思考/批判性思维/人际交往
    - 国家与社会 (module=nationSociety)：民族团结/国家安全/生态文明/总体国家安全观/人类命运共同体
    - 公民参与 (module=civicParticipation)：民主形式/基层群众自治/人民代表大会制度/政治参与
    - 经济发展 (module=economy)：创新驱动/对外开放/共同富裕/乡村振兴/科技强国
    - 中华文化 (module=chineseCulture)：传承创新/文化自信/中华优秀传统文化/民族精神
    - **R5.5**：道法每题 module 必须从 8 个里选 1 个（与该题主要 KP 对应），
      严禁退化为旧的单一 "politics" — 否则模块级聚合失去信息量。
  - **数学 module 题号约定**（北京中考二模卷固定结构）：
    - Q1-Q16 按内容选 module（数与式/方程不等式/函数/三角形/四边形/圆/统计与概率）
    - Q17-Q25 中档解答，按主考点选 module
    - **Q26 二次函数综合** → module = functions（"二次函数综合"/"函数与几何结合" 类 KP）
    - **Q27 几何综合** → module = geometryComprehensive（"旋转"/"图形变换"/"几何证明" 类 KP）
    - **Q28 新定义题** → module = newDefinition（题干会给出新概念定义如"含角点"/"关联图形"/"m-区域点"等，必须选此 module；KP 用"新定义"+涉及的具体考点）
- **严禁将现代文题标注成"文言文"知识点，反之亦然**
- **严禁滥用"信息筛选"标签**：只用于"判断说法是否符合文意"类选择题；
  词语含义/句式赏析/段落作用/启示题 不要标"信息筛选"
- **物理 KP 必须是物理考点，不能写"信息筛选"等语文 KP**
- **道法 KP 必须是道法考点（如"宪法地位"/"中国梦"），不要标"段落作用"等语文 KP**
- difficulty：基础=直接考概念/简单计算；中等=多步推理/公式应用；能力=综合/压轴
- recommended_for：基础→[L0-L3]；中等→[L1-L3]；能力→[L2-L3]；压轴→[L3]
"""


def _client():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY 环境变量")
    return openai.OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def _load_curriculum(subject: str) -> str:
    subj_en = _subject_en(subject)
    candidates = [
        ROOT / "knowledge-base" / "subjects" / subj_en / "curriculum.yaml",
        ROOT / "knowledge-base" / "subjects" / subj_en / f"{subj_en}-curriculum.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8")[:3500]
    return "（未找到 curriculum.yaml）"


def _options_text(opts: dict | None, has_image: bool) -> str:
    if not opts:
        return "（无选项）"
    if has_image:
        return "（选项为图片，内容待补全）"
    return "\n".join(f"{k}. {v}" for k, v in opts.items())


def _answer_with_context(correct: str, opts: dict | None, has_image: bool) -> str:
    """给 LLM 看的答案字符串，选择题附上选项文本帮助推断知识点。"""
    if not correct:
        return "（未知）"
    if not opts or has_image:
        return correct
    # 单选
    if len(correct) == 1 and correct in opts:
        return f"{correct}（{opts[correct]}）"
    # 多选
    if all(c in opts for c in correct):
        return "；".join(f"{c}（{opts[c]}）" for c in correct)
    return correct


_SECTION_HINT_CN = {
    # 语文
    "base":        "一、基础·运用（字音/字形/成语/病句/词语连贯/书写）",
    "classical":   "二、古诗文阅读（默写/古诗赏析/文言文实词/文言文翻译/语句理解）",
    "book_review": "三、名著阅读（情节/人物形象/主题理解）",
    "modern":      "四、现代文阅读（信息筛选/记叙文/议论文/说明文/散文）",
    "essay":       "五、作文（命题作文/材料作文/半命题作文）",
    # 物理
    "choice":         "一、单项选择题（基础概念/简单判断）",
    "multi_choice":   "二、多项选择题（综合分析/多因素判断）",
    "experiment":     "三、实验探究题（实验方法/数据处理/装置原理）",
    "comprehensive":  "四、科普阅读题（综合应用/材料理解）",
    "calculation":    "五、计算题（公式应用/数据计算/受力分析）",
    # 道法（注意 choice 在物理被占用了，但 politics 用 type 是 "choice"/"judge"/"material"，
    # section 也用同名，所以这里加 politics 专属 section_hint 不太可能区分 —
    # 用题面 + subject 在 prompt 自然区分。下面 judge/material 道法专用）
    "judge":     "一、判断题（教材基本观点是否正确）",
    "material":  "二/三、材料分析题（时政材料 + 教材观点综合运用）",
}


def enrich_question(
    *,
    subject: str,
    qid: str,
    qtype: str,
    score: int,
    stem: str,
    opts: dict | None,
    has_image: bool,
    answer: str,
    modules: list[str],
    curriculum: str,
    cache_key: str | None,
    section: str = "",
) -> dict:
    cache_dir = ROOT / "scripts" / "knowledge-base" / ".cache"
    cache_dir.mkdir(exist_ok=True)
    if cache_key:
        f = cache_dir / f"{cache_key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))

    section_hint = _SECTION_HINT_CN.get(section, "（未标注，请根据题干自行判断）")

    user = ENRICH_USER_TEMPLATE.format(
        subject=subject,
        qid=qid,
        qtype=qtype,
        score=score,
        stem=stem[:800],
        options_text=_options_text(opts, has_image),
        answer=_answer_with_context(answer, opts, has_image)[:400],
        modules_str=", ".join(modules),
        curriculum_excerpt=curriculum,
        section_hint=section_hint,
    )
    client = _client()
    resp = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": ENRICH_SYSTEM},
            {"role": "user",   "content": user},
        ],
        temperature=0.2,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    result = json.loads(resp.choices[0].message.content)
    if modules and result.get("module") not in modules:
        result["module"] = modules[0]

    # **R5.2** 数学 Q28 硬规则：北京中考 Q28 必为新定义题（"称…为…"/"定义…为…"
    # 结构）。LLM 偶尔被「关联点 / ⊙O」字眼带偏到 circles/geometryComprehensive，
    # 用 stem 关键词检测兜底强制改回 newDefinition。
    if _subject_en(subject) == "math":
        try:
            qnum = int(re.sub(r"\D", "", qid))
        except (ValueError, TypeError):
            qnum = 0
        if qnum == 28:
            # 含 "称…为…/叫做…/定义…为…/我们规定…/记作…" 等新定义 marker
            if re.search(r"称[^。]{0,40}[为是]|叫\s*做|定义[^。]{0,30}为|"
                         r"我们规定|记作|记为|"
                         r"则称[^。]{0,40}点", stem):
                if "newDefinition" in modules:
                    result["module"] = "newDefinition"
                    # KP 补 "新定义" 标签（保留 LLM 已选的具体知识点）
                    kps = result.get("knowledge_points") or []
                    if "新定义" not in kps:
                        result["knowledge_points"] = ["新定义"] + kps[:2]

    if cache_key:
        (cache_dir / f"{cache_key}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


# ─── QC 状态推断 ──────────────────────────────────────────────────────────────

def _qc_status(q: dict, answer: str, solution: str, qtype: str) -> tuple[str, str]:
    """返回 (qc_status, qc_note)。

    判定原则（与「腾讯切题流水线」对齐）：
      - 选择题（单/多选）：要求 options（文本 OR 图片）+ answer 都齐；
        has_image_options=True 本身不是问题（若文本选项也齐就是图配文，更不是问题）。
      - 主观题（含 SOLUTION_REQUIRED 与其他）：不要求 answer，只看 solution。
    """
    issues = []
    is_choice = qtype in {"单选", "多选"}
    opts = q.get("options") or {}
    if is_choice:
        if not opts and not q.get("has_image_options"):
            issues.append("选择题缺少 options（既无文本也无图片选项）")
        if not answer:
            issues.append("选择题 answer 为空")
    else:
        # 主观题：只要求 solution
        if qtype in SOLUTION_REQUIRED and (solution == "__MISSING__" or not solution):
            issues.append("解题步骤未提取，需补全 solution")
    if issues:
        return "needs_review", "；".join(issues)
    return "draft", ""


# ─── 结构描述 ─────────────────────────────────────────────────────────────────

def _derive_structure(questions: list[dict]) -> str:
    counts: dict[str, dict] = OrderedDict()
    for q in questions:
        t = q["type"]
        if t not in counts:
            counts[t] = {"count": 0, "score": 0}
        counts[t]["count"] += 1
        counts[t]["score"] += q["score"]
    return " + ".join(f"{v['count']}{k}({v['score']}分)" for k, v in counts.items())


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def enrich_paper(paper: NormalizedPaper, cache_prefix: str) -> dict:
    subject = paper.subject
    modules = _modules(subject)
    curriculum = _load_curriculum(subject)

    # 准备任务列表
    tasks = []
    for q in paper.questions:
        num = q["number"]
        ak = paper.answers.get(num, {"correct": "", "solution": ""})
        tasks.append((q, ak))

    # 并发 LLM 标注
    enriched: dict[int, dict] = {}

    def _do(item):
        q, ak = item
        num = q["number"]
        qtype = TYPE_MAP.get(q["type_en"], q["type_en"])
        print(f"  [Q{num}] 标注中 ...", file=sys.stderr, flush=True)
        r = enrich_question(
            subject=subject,
            qid=f"Q{num}",
            qtype=qtype,
            score=q["score"],
            stem=q["stem"],
            opts=q["options"],
            has_image=q["has_image_options"],
            answer=ak["correct"],
            modules=modules,
            curriculum=curriculum,
            cache_key=f"{cache_prefix}-Q{num}-v3",   # v3: KP 细化 + 防信息筛选滥用
            section=q.get("section",""),
        )
        return num, r

    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(_do, t) for t in tasks]):
            num, r = fut.result()
            enriched[num] = r

    # 按题号排序组装
    questions_out = []
    for q, ak in tasks:
        num = q["number"]
        qtype = TYPE_MAP.get(q["type_en"], q["type_en"])
        r = enriched[num]

        answer  = ak["correct"]
        solution = ak["solution"] if ak["solution"] else (
            "__MISSING__" if qtype in SOLUTION_REQUIRED else ""
        )

        qc_status, qc_note = _qc_status(q, answer, solution, qtype)

        item: dict = {
            "id":               num,
            "type":             qtype,
            "score":            q["score"],
            "stem":             q["stem"],
        }
        # options 仅选择题写；无选项题省略该字段
        if q["options"] is not None:
            item["options"] = q["options"]
        # has_image_options 独立写入（纯图选项题 options=None 但仍需此标记，
        # 否则 yaml 里 has_image_options 永远是 None → 下游 exam-review 误判
        # 「选择题缺少 options 字段」）
        if q.get("has_image_options"):
            item["has_image_options"] = True
            # 数学图选项题（Q1 类）：把 figures_all 4 张图按 A/B/C/D 顺序映射
            # 替换 options 的 "[图]" 字面占位，让 yaml 自承载完整图引用
            figs = q.get("figures_all") or []
            if figs and len(figs) >= 4 and item.get("options"):
                letters = ["A", "B", "C", "D"]
                for idx, letter in enumerate(letters):
                    if idx < len(figs) and item["options"].get(letter) == "[图]":
                        item["options"][letter] = f"![](figures/{figs[idx]})"

        # figure：含图题目写入相对路径（相对于输出 YAML 所在目录）
        if q.get("figure_path"):
            item["figure"] = q["figure_path"]   # 由 _write_yaml 阶段实际复制
        # 多图（如解答题 sol 内嵌补图）也要纳入 yaml 复制清单
        if q.get("figures_all"):
            item.setdefault("_figures_extra", q["figures_all"])

        item.update({
            "answer":           answer,
            "solution":         solution,
            "knowledge_points": r.get("knowledge_points", []),
            "module":           r.get("module", modules[0] if modules else ""),
            "difficulty":       r.get("difficulty", "中等"),
            "recommended_for":  r.get("recommended_for", ["L1", "L2", "L3"]),
            "qc_status":        qc_status,
            "qc_note":          qc_note,
        })
        questions_out.append(item)

    # 题级 passage_id：按 q_range 自动推断（若 final.json 未显式带）
    # 语文/英语 二级模型：reading/cloze/资料 篇 + 题级 passage_id 关联
    for q_item in questions_out:
        for ps in paper.passages:
            rng = ps.get("q_range")
            if rng and rng[0] <= q_item["id"] <= rng[1]:
                q_item.setdefault("passage_id", ps["id"])
                break

    # 顶层
    header = {
        "year":             paper.year,
        "district":         paper.district,
        "exam_type":        paper.exam_type,
        "subject":          paper.subject,
        "full_score":       paper.full_score,
        "duration_minutes": paper.duration,
        "total_questions":  len(questions_out),
        "structure":        _derive_structure(questions_out),
        "passages":         paper.passages,
        "questions":        questions_out,
    }
    return header


# ─── YAML 写出 ────────────────────────────────────────────────────────────────

def _write_yaml(result: dict, out_path: Path,
                paper_dir: Path | None = None) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 复制 figure 文件到 YAML 旁边的同名子目录
    # YAML: knowledge-base/exams/mock/physics/beijing/2026-chaoyang-yi.yaml
    # 图片: knowledge-base/exams/mock/physics/beijing/2026-chaoyang-yi/figures/q06.png
    exam_slug = out_path.stem   # e.g. "2026-chaoyang-yi"
    fig_dest_base = out_path.parent / exam_slug  # YAML旁的同名目录

    if paper_dir:
        copied = 0
        # 收集所有图引用：q.figure + stem/solution/options 中的 ![](figures/...)
        all_rel: set[str] = set()
        for q in result["questions"]:
            fig_rel = q.get("figure")   # e.g. "figures/q06.png"
            if fig_rel:
                all_rel.add(fig_rel)
            # 数学解答步骤含示意图：扫 stem/solution/options 内嵌 ![](figures/...)
            for fld in ("stem", "solution"):
                txt = q.get(fld) or ""
                for m in re.finditer(r"!\[\]\(figures/([^)]+)\)", str(txt)):
                    all_rel.add(f"figures/{m.group(1)}")
            opts = q.get("options")
            if isinstance(opts, dict):
                for v in opts.values():
                    for m in re.finditer(r"!\[\]\(figures/([^)]+)\)", str(v)):
                        all_rel.add(f"figures/{m.group(1)}")
        # passage figure / image_options（语文非连续文本 / 英语 A 篇 image-match）
        # chinese_image_paper.py 写入时已含 slug 前缀（"2026-xxx-yi/figures/yyy.png"），
        # 其他来源可能只有 "figures/yyy.png"。规范化为相对 paper_dir 的 figures/yyy.png
        def _norm_figure_rel(fig_str: str) -> str:
            if fig_str.startswith(f"{exam_slug}/figures/"):
                return fig_str[len(exam_slug)+1:]   # 剥 slug 前缀
            if fig_str.startswith("figures/"):
                return fig_str
            return f"figures/{fig_str}"
        for ps in result.get("passages") or []:
            fig = ps.get("figure")
            if fig:
                all_rel.add(_norm_figure_rel(fig))
            img_opts = ps.get("image_options") or {}
            for v in img_opts.values():
                if isinstance(v, str):
                    all_rel.add(_norm_figure_rel(v))

        for fig_rel in sorted(all_rel):
            src = paper_dir / fig_rel
            dst = fig_dest_base / fig_rel
            # 若 dst 已存在（chinese_image_paper.py 直接写 mock 路径，paper_dir 不必有 src）→ skip
            if dst.exists() and not src.exists():
                continue
            if not src.exists():
                print(f"  ⚠️ 图片源文件不存在，跳过: {src}", file=sys.stderr)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        # 更新 figure 字段为相对 YAML 目录路径（含 slug 前缀）
        for q in result["questions"]:
            fig_rel = q.get("figure")
            if fig_rel and not fig_rel.startswith(exam_slug):
                q["figure"] = f"{exam_slug}/{fig_rel}"
        for ps in result.get("passages") or []:
            fig = ps.get("figure")
            if fig and not fig.startswith(exam_slug):
                ps["figure"] = f"{exam_slug}/" + (fig if fig.startswith("figures/") else f"figures/{fig}")
            img_opts = ps.get("image_options")
            if isinstance(img_opts, dict):
                for k, v in list(img_opts.items()):
                    if isinstance(v, str) and not v.startswith(exam_slug):
                        img_opts[k] = f"{exam_slug}/" + (v if v.startswith("figures/") else f"figures/{v}")
        if copied:
            print(f"  📷 复制 {copied} 张图片 → {fig_dest_base}/figures/", file=sys.stderr)

    # **合并旧 yaml 的 qc_***（保护人工审核结果不被自动重算清掉）
    # 历史教训：enrich/parser 都默认写 qc_status='draft', qc_note=''，会覆盖
    # 用户在 exam-review 工具里手工写的备注。
    # 规则：
    #   - old qc_status != 'draft' → 保留旧（用户标的 done/none/needs_review 不动）
    #   - old qc_note 非空 → 保留旧（用户的备注永远优先于自动生成的）
    if out_path.exists():
        try:
            existing_qc: dict = {}
            old_doc = yaml.safe_load(out_path.read_text(encoding="utf-8")) or {}
            # **过期 qc_note 过滤**：image OCR 时代标注的 patch-related qc 在 docx 路线下
            # 都是误导，识别后丢弃（"OCR" / "多了：A.xx" / "OCR没识别" / "原划线句" 等）
            STALE_PATTERNS = [
                "OCR", "ocr", "多了：", "里多了", "没有识别",
                "划线", "划线句", "划线的", "加点", "加点字",
                "图没识别", "图没有", "答案错位", "答案页错位",
                "patch", "兜底", "占位", "请对照", "请参照", "请补",
                # enrich 自动生成的 needs_review note（每次重 enrich 应基于新数据
                # 重新判定，不能保留旧的；否则旧 image 路线把全部题标 needs_review
                # 会一直传递下去）
                "answer 为空", "缺少 options", "需补全 solution",
                "解题步骤未提取", "选择题",
            ]
            for oq in (old_doc.get("questions") or []):
                qid = oq.get("id")
                if qid is None: continue
                note = (oq.get("qc_note") or "").strip()
                old_status = oq.get("qc_status", "draft") or "draft"
                # 如果旧 note 是过期的，note 和 status 一起清（自动判定的 NR）
                if note and any(p in note for p in STALE_PATTERNS):
                    note = ""
                    if old_status in ("needs_review", "flag"):
                        old_status = "draft"
                existing_qc[qid] = {"qc_status": old_status, "qc_note": note}
            for q in result["questions"]:
                old = existing_qc.get(q["id"], {})
                # qc_status: 仅当不是 'draft' / 'flag' / 'none'（自动写或重置的）才保留
                # done / needs_review（人工真正标的）才覆盖新值
                if old.get("qc_status", "draft") not in ("draft", "flag", "none"):
                    q["qc_status"] = old["qc_status"]
                if old.get("qc_note", ""):
                    q["qc_note"] = old["qc_note"]
        except Exception as e:
            print(f"  ⚠ 读旧 yaml 合并 qc_* 失败（沿用新值）: {e}", file=sys.stderr)

    # 统计 qc 摘要
    total = len(result["questions"])
    needs_review = sum(1 for q in result["questions"] if q["qc_status"] == "needs_review")
    draft = total - needs_review

    with out_path.open("w", encoding="utf-8") as f:
        f.write("# ============================================================\n")
        f.write(f"# {result['year']}年北京{result['district']}{result['exam_type']}"
                f"{result['subject']} — 自动生成\n")
        f.write("# ============================================================\n")
        f.write(f"# OCR: Qwen-VL-OCR  Enrich: qwen-max\n")
        f.write(f"# QC: draft={draft}  needs_review={needs_review}\n\n")
        yaml.safe_dump(result, f, allow_unicode=True, sort_keys=False, width=120)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="试卷结构化数据 → knowledge-base YAML"
    )
    # 新格式输入
    parser.add_argument("--input", "-i", type=Path,
                        help="新格式：<exam-dir>/structured-cloud/final.json")
    # 旧格式输入（兼容）
    parser.add_argument("--paper",      type=Path, help="旧格式：paper.json")
    parser.add_argument("--answer-key", type=Path, help="旧格式：answer-key.json")
    parser.add_argument("--exam-meta",  type=Path, help="旧格式：exam-meta.json（可选）")
    # 通用
    parser.add_argument("--subject", "-s",
                        help="学科（新格式时可省略，从 final.json 读取）")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="输出 YAML 路径")
    parser.add_argument("--cache-prefix", default=None,
                        help="LLM cache key 前缀（默认取输出文件名）")
    args = parser.parse_args()

    # ── 加载输入 ──
    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        # paper_dir = final.json 的上上级（即 <exam-dir>/），用于定位 figures/
        paper_dir = args.input.resolve().parent.parent
        paper = NormalizedPaper.from_final(data, subject_hint=args.subject or "",
                                           paper_dir=paper_dir)
        print(f"📄 final.json: {len(paper.questions)} 题", file=sys.stderr)
    elif args.paper and args.answer_key:
        paper_data = json.loads(args.paper.read_text(encoding="utf-8"))
        ak_data    = json.loads(args.answer_key.read_text(encoding="utf-8"))
        em_data    = json.loads(args.exam_meta.read_text(encoding="utf-8")) \
                     if args.exam_meta else None
        paper = NormalizedPaper.from_legacy(paper_data, ak_data, em_data)
        if args.subject:
            paper.subject = args.subject
        print(f"📄 paper.json: {len(paper.questions)} 题  "
              f"answer-key: {len(paper.answers)} 条", file=sys.stderr)
    else:
        parser.error("需要 --input 或 (--paper + --answer-key)")

    if not paper.subject:
        parser.error("无法推断学科，请指定 --subject")

    # **关键**：cache_prefix 必须带 subject 前缀，否则 chinese/physics/math 同名 yaml
    # （如 2026-chaoyang-yi）会共享 cache 导致 KP 错配。
    cache_prefix = args.cache_prefix or f"{paper.subject}-{args.output.stem}"
    result = enrich_paper(paper, cache_prefix)
    _write_yaml(result, args.output, paper_dir=paper.paper_dir)

    total = result["total_questions"]
    nr = sum(1 for q in result["questions"] if q["qc_status"] == "needs_review")
    print(f"\n✅ {args.output}", file=sys.stderr)
    print(f"   {total} 题  needs_review={nr}  structure: {result['structure']}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
