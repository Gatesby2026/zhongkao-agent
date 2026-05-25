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
        # 当前 KB 全部题目标"politics"单模块；待 KB 细化为
        # 心理/道德/法治/国情等 8 模块时此表对应扩
        "politics": "道法综合",
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


def is_essay(qtype: str) -> bool:
    """题型是否为作文/写作类（决定是否走 AI 评分 + 满分兜底）。"""
    if not qtype:
        return False
    low = qtype.lower()
    return any(k in low or k in qtype for k in ESSAY_TYPE_KEYWORDS)
