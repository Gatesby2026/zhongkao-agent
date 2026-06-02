"""数据加载 + 按题号 join。

输入三件套（新数据约定）：
  - 试卷结构化:  knowledge-base/exams/{mock,zhenti}/<subj>/beijing/<slug>.yaml
  - 学生作答:    students/<name>/<slug>/answer-card.json
  - 最终得分:    students/<name>/<slug>/scores.json
  - 学生信息:    students/<name>/<slug>/student.json（可选）

join 后每题一条 QView，喂给 aggregate / analyze。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import align_scores, subject_profile


# module 英文 → 中文（物理；其它学科按需扩展）
MODULE_CN = {
    "soundLightHeat": "声光热",
    "mechanics": "力学",
    "electricity": "电学",
    "experiments": "实验",
    "numbersAndExpressions": "数与式",
    "equationsAndInequalities": "方程与不等式",
    "functions": "函数",
    "triangles": "三角形",
    "quadrilaterals": "四边形",
    "circles": "圆",
    "geometryComprehensive": "几何综合",
    "statisticsAndProbability": "统计与概率",
}

CHOICE_TYPES = {"单选", "多选", "choice", "multi_choice", "cloze", "完形", "完形填空"}

SUBJECT_CN = {"physics": "物理", "chinese": "语文", "math": "数学",
              "english": "英语", "politics": "道法", "history": "历史",
              "chemistry": "化学", "biology": "生物", "geography": "地理"}
DISTRICT_CN = {"chaoyang": "朝阳", "dongcheng": "东城", "xicheng": "西城",
               "haidian": "海淀", "fengtai": "丰台", "fangshan": "房山",
               "daxing": "大兴", "shijingshan": "石景山", "tongzhou": "通州",
               "changping": "昌平", "beijing": "北京"}
ROUND_CN = {"yi": "一模", "er": "二模", "zhenti": "真题", "qimo": "期末",
            "qizhong": "期中"}


def _title_from_slug(slug: str, subject: str) -> str:
    """students 目录名 2026-chaoyang-yi-physics → '2026朝阳一模物理'。
    比 yaml 顶层可靠（上游 enrich 偶尔丢 year/district）。"""
    parts = slug.split("-")
    year = parts[0] if parts and parts[0].isdigit() else ""
    district = next((DISTRICT_CN.get(p, "") for p in parts if p in DISTRICT_CN), "")
    rnd = next((ROUND_CN.get(p, "") for p in parts if p in ROUND_CN), "")
    subj_cn = SUBJECT_CN.get(subject, subject)
    return f"{year}{district}{rnd}{subj_cn}".strip() or slug


@dataclass
class QView:
    """一道题的完整视图（试卷 + 作答 + 得分 三方 join）。"""
    num: int
    qid: str
    type_cn: str
    is_choice: bool
    score: int
    scored: float
    lost: float
    stem: str
    options: dict | None
    std_answer: str
    solution: str
    knowledge_points: list[str]
    module: str
    module_cn: str
    difficulty: str
    figure: str | None
    student_filled: str | None
    student_ocr_seen: str | None
    student_handwriting: str | None
    region_image: str | None
    page_image: str | None
    grade: dict | None
    passage_id: str = ""   # 英语阅读分篇用（reading_A/B/C/D 等）

    @property
    def is_lost(self) -> bool:
        return self.lost > 0


@dataclass
class ExamView:
    student_name: str
    student_id: str
    subject: str
    exam_slug: str
    exam_title: str
    full_score: int
    total_scored: float
    questions: list[QView] = field(default_factory=list)
    raw_sections: list[dict] = field(default_factory=list)  # scores.json 原始 sections（人工填，准确）
    kb_yaml_path: Path = None
    student_dir: Path = None
    # 数据质量（小分表解析+对齐+缺数据）汇总，给报告顶部提示用
    data_quality: dict = field(default_factory=dict)

    def figure_abs(self, q: "QView") -> str | None:
        """试卷配图绝对 file:// 路径（yaml.figure 相对 kb_yaml 目录）。"""
        if not q.figure or self.kb_yaml_path is None:
            return None
        p = (self.kb_yaml_path.parent / q.figure).resolve()
        return f"file://{p}" if p.exists() else None


def _qnum(qid) -> int:
    if isinstance(qid, int):
        return qid
    m = re.search(r"(\d+)", str(qid))
    return int(m.group(1)) if m else 0


def load_exam_view(kb_yaml: Path, student_dir: Path) -> ExamView:
    """加载并 join 三方数据。"""
    paper = yaml.safe_load(kb_yaml.read_text(encoding="utf-8"))
    ac = json.loads((student_dir / "answer-card.json").read_text(encoding="utf-8"))
    scores = json.loads((student_dir / "scores.json").read_text(encoding="utf-8"))

    student = dict(ac.get("student", {}))
    sj_path = student_dir / "student.json"
    if sj_path.exists():
        for k, v in json.loads(sj_path.read_text(encoding="utf-8")).items():
            student.setdefault(k, v)

    ac_by_num = {_qnum(a.get("qId")): a for a in ac.get("answers", [])}
    align_warn: list[str] = []
    align_miss_qids: list[str] = []
    align_block_qids: list[str] = []
    # 优先用 align：xlsx items + yaml.questions → yaml 题号索引的对齐结果
    # （处理：默写多空合并、二选一作文、中段题号漂移等 xlsx/yaml 体系差）
    if scores.get("items"):
        sc_by_num, align_warn = align_scores.align(
            scores["items"], paper.get("questions", []))
        align_miss_qids = [f"Q{n}" for n, v in sc_by_num.items()
                           if v.get("_alignmentMiss")]
        align_block_qids = [f"Q{n}" for n, v in sc_by_num.items()
                            if v.get("_blockShared")]
    else:
        # 兼容旧 scores.json（auto_grade 输出 / 不带 items 的历史数据）
        sc_by_num = {_qnum(s.get("qId")): s for s in scores.get("questions", [])}

    subject = paper.get("subject", "")
    exam_title = _title_from_slug(student_dir.name, subject)

    assumed_full_qids: list[str] = []
    qviews: list[QView] = []
    for q in paper.get("questions", []):
        num = _qnum(q.get("id"))
        sc = sc_by_num.get(num, {})
        a = ac_by_num.get(num, {})
        # full 以 yaml 为权威（二选一作文等场景，xlsx 子题求和会超 yaml 满分）
        full = float(q.get("score", 0) or 0)
        if "scored" in sc:
            scored = max(0.0, min(full, float(sc.get("scored", 0))))
        else:
            # 班小二惯例：未列出的题 = 学生满分（典型为选择题全对）
            scored = full
            if full > 0 and scores.get("items"):
                # 仅 items 模式（有 align）下记缺失；旧 questions 模式不记
                assumed_full_qids.append(f"Q{num}")
        type_cn = q.get("type", "")
        module = q.get("module", "")
        filled = a.get("filled")
        qviews.append(QView(
            num=num, qid=f"Q{num}", type_cn=type_cn,
            is_choice=type_cn in CHOICE_TYPES,
            score=full, scored=scored, lost=round(full - scored, 2),
            stem=q.get("stem", ""), options=q.get("options"),
            std_answer=str(q.get("answer", "")),
            solution=q.get("solution", "") or "",
            knowledge_points=q.get("knowledge_points") or [],
            module=module,
            module_cn=subject_profile.module_cn(subject, module),
            difficulty=q.get("difficulty", ""), figure=q.get("figure"),
            student_filled=("".join(filled) if isinstance(filled, list) else filled),
            student_ocr_seen=a.get("ocrSeen"),
            student_handwriting=a.get("handwritingText"),
            region_image=a.get("regionImage"),
            page_image=a.get("pageImage"),
            grade=a.get("grade"),
            passage_id=str(q.get("passage_id") or q.get("passage") or ""),
        ))

    qviews.sort(key=lambda v: v.num)
    return ExamView(
        student_name=student.get("name", ""),
        student_id=str(student.get("examId", "")),
        subject=subject,
        exam_slug=student_dir.name,
        exam_title=exam_title,
        full_score=scores.get("examTotal", {}).get(
            "fullScore", paper.get("full_score", 0)),
        total_scored=scores.get("examTotal", {}).get("scored", 0),
        questions=qviews,
        raw_sections=scores.get("sections", []),
        kb_yaml_path=kb_yaml,
        student_dir=student_dir,
        data_quality={
            "score_source_file": scores.get("_source", "unknown"),
            "parse_warnings": list(scores.get("_warnings") or []),
            "align_warnings": align_warn,
            "align_block_shared_qids": align_block_qids,    # 按比例分摊
            "align_miss_qids": align_miss_qids,             # 对齐失败按满分占位
            "assumed_full_qids": assumed_full_qids,         # xlsx 未列出按满分占位
            # 答题卡侧识别覆盖（P0.1+P0.2，来自 answer-card.json._data_quality）
            "card_missing_choice_qids":
                (ac.get("_data_quality") or {}).get("missing_choice_qids") or [],
            "card_missing_subjective_qids":
                (ac.get("_data_quality") or {}).get("missing_subjective_qids") or [],
            "card_skipped_non_card_pages":
                (ac.get("_data_quality") or {}).get("skipped_non_card_pages") or [],
        },
    )
