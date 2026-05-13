"""4 个标准 JSON 输入的 TypedDict（运行时校验最低必填字段）。

详细 schema 见 docs/product/STUDENT-REPORT-FEATURE-SPEC.md §三
"""
from __future__ import annotations
from typing import TypedDict, Literal, Optional


# ============ paper.json - 试卷结构化 ============

QuestionType = Literal[
    "choice",                # 单项选择
    "multi_choice",          # 多项选择
    "fill_blank",            # 填空
    "calculation",           # 计算题
    "experiment",            # 实验探究
    "essay",                 # 大题/科普/简答
]


class Option(TypedDict):
    label: str               # "A" / "B" / ...
    text: str


class Question(TypedDict, total=False):
    id: str                  # "Q12"
    type: QuestionType
    section: str             # "一、单项选择题"
    score: int               # 满分
    stem: str                # 题干（含格式如 LaTeX）
    options: list[Option]    # 选择题才有
    figures: list[str]       # 配图占位符
    sourcePages: list[str]   # 来源页码


class PaperMeta(TypedDict, total=False):
    exam: dict               # {city, district, grade, examType, year, subject}
    totalScore: int
    duration: int            # 分钟
    questionCount: int


class Paper(TypedDict):
    meta: PaperMeta
    questions: list[Question]


# ============ answer-key.json - 标准答案 ============

class AnswerKeyItem(TypedDict, total=False):
    id: str                  # "Q12"
    correct: str | list[str] # "C" 或 ["A","B","D"] 或 ["不变","晶体","引力"]
    correctSolution: str     # 大题：完整解答过程
    keySteps: list[str]      # 大题：给分要点
    score: int
    partialCreditRule: str   # 多选题计分规则


class AnswerKey(TypedDict):
    answers: list[AnswerKeyItem]


# ============ answer-card.json - 学生答题 ============

class StudentAnswer(TypedDict, total=False):
    qId: str
    type: QuestionType
    filled: str | list[str]  # 选择题：学生涂的字母
    rawText: str             # 填空/计算/实验题：学生写的内容
    confidence: float


class AnswerCard(TypedDict):
    student: dict            # {name, examId}
    answers: list[StudentAnswer]


# ============ scores.json - 小分 ============

class QuestionScore(TypedDict, total=False):
    qId: str
    scored: float            # 得分
    fullScore: float         # 满分
    isWrong: bool            # 完全错
    isPartial: bool          # 部分对


class Scores(TypedDict):
    examTotal: dict          # {scored, fullScore}
    questions: list[QuestionScore]
