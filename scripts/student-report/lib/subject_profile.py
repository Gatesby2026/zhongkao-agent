"""5 科差异集中配置：模块映射 + 作文题判定。

把"科目专属"从代码各处收敛到一份配置——其他模块保持科目无关，仅靠
此处映射做适配。新增科目/模块时只动这里。
"""
from __future__ import annotations

# KB yaml 里 `module` 字段一律英文键 → 中文展示名
MODULE_CN_BY_SUBJECT: dict[str, dict[str, str]] = {
    "physics": {
        "electricity": "电学",
        "soundLightHeat": "声光热",
        "mechanics": "力学",
        "experiments": "实验探究",
    },
    "math": {
        "numbersAndExpressions": "数与式",
        "equationsAndInequalities": "方程与不等式",
        "functions": "函数",
        "triangles": "三角形",
        "quadrilaterals": "四边形",
        "circles": "圆",
        "geometryComprehensive": "几何综合",
        "statisticsAndProbability": "统计与概率",
    },
    "chinese": {
        "base": "基础运用",
        "writing": "作文",
        "reading": "现代文/名著阅读",
        "classical": "古诗文",
    },
    "english": {
        "grammar": "语法",
        "vocabulary": "词汇",
        "reading": "阅读",
        "writing": "写作",
    },
    "politics": {
        # **R5.5 (2026-06-01)**：KB 已细化为 8 模块
        "ideology":           "思想理论",
        "ruleOfLaw":          "法治教育",
        "morality":           "道德教育",
        "mentalHealth":       "心理健康",
        "nationSociety":      "国家与社会",
        "civicParticipation": "公民参与",
        "economy":            "经济发展",
        "chineseCulture":     "中华文化",
        # 旧"politics"占位兼容（已 enrich 全部细化后可删）
        "politics":           "道法综合",
    },
}

# 视为作文/写作类的题型关键词（命中即"AI 评分不可靠，能评则评，
# 评不出按满分占位"——参见 subjective_grade / auto_grade 兜底）
ESSAY_TYPE_KEYWORDS = ("作文", "essay", "composition", "写作")


def module_cn(subject: str, key: str) -> str:
    """KB 模块键 → 中文展示名。

    未知键原样返回（兼容 KB 已直接用中文键的情况），空键 → "其它"。
    """
    if not key:
        return "其它"
    m = MODULE_CN_BY_SUBJECT.get(subject or "", {})
    return m.get(key, key)


# 题型英文键 → 中文大题展示名（各科通用兜底；英语大题分法见 section_name）
_TYPE_CN = {
    "cloze": "完形填空", "完形": "完形填空",
    "reading": "阅读理解", "reading_express": "阅读表达",
    "单选": "单项选择", "多选": "多项选择", "判断": "判断题",
    "材料分析": "材料分析", "作文": "书面表达", "填空": "填空题",
    "解答": "解答题",
}


def section_name(subject: str, q) -> str:
    """一道题归到哪个「大题」（中文展示名）。subject 专属分法收敛在此。

    英语：单项选择 / 完形填空 / 阅读理解(A/B篇) / 阅读理解(C/D篇) / 阅读表达 / 书面表达。
    其它科：按题型中文名兜底（_TYPE_CN）。
    """
    t = (getattr(q, "type_cn", "") or "").strip()
    mod = (getattr(q, "module", "") or "").strip()
    pid = (getattr(q, "passage_id", "") or "").strip().lower()
    if subject == "english":
        if t == "cloze" or mod == "vocabulary":
            return "完形填空"
        if mod == "grammar":
            return "单项选择"
        if mod == "reading" and t in ("单选", "reading", "多选"):
            return "阅读理解（A/B篇）" if pid in ("reading_a", "reading_b") \
                else "阅读理解（C/D篇）"
        if t == "reading_express":
            return "阅读表达"
        if "作文" in t or is_essay(t):
            return "书面表达"
    return _TYPE_CN.get(t, t or "未分类")


def is_essay(qtype: str) -> bool:
    """题型是否为作文/写作类（决定是否走 AI 评分 + 满分兜底）。"""
    if not qtype:
        return False
    low = qtype.lower()
    return any(k in low or k in qtype for k in ESSAY_TYPE_KEYWORDS)
