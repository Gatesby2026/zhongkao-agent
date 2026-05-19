#!/usr/bin/env python3
"""学生答题卡审核工具 — answer-card.json 内容检查 + 与标准答案对照 + 原图查看

加载 detect.py 生成的 answer-card.json，做质量检查（识别率、置信度、未作答等），
可选与试卷 YAML 标准答案对照判对错，生成自包含 HTML（内嵌原始照片）在浏览器中
打开。

用法：
    # 单学生（自动找 photos + standard）
    answer-card-review students/jiaxiaoqi/2026-chaoyang-yi-physics

    # 直接传 answer-card.json
    answer-card-review students/jiaxiaoqi/2026-chaoyang-yi-physics/answer-card.json

    # 显式指定标准答案 yaml
    answer-card-review <dir> --standard knowledge-base/exams/mock/physics/beijing/2026-chaoyang-yi.yaml

    # 批量：某学生所有考试
    answer-card-review --student-all students/jiaxiaoqi
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import webbrowser
from pathlib import Path

import yaml

TOOL_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = TOOL_DIR / "templates" / "index.html"
REPO_ROOT = TOOL_DIR.parent.parent
DEFAULT_KB_ROOT = REPO_ROOT / "knowledge-base" / "exams" / "mock"


# ─── 标准答案定位 ────────────────────────────────────────────────────────────

SLUG_SUBJECT_RE = re.compile(r"-(physics|chinese|math|english|politics|history|chemistry|biology|geography)$")


def infer_standard_path(exam_dir: Path) -> Path | None:
    """从学生考试目录名推断标准答案 yaml 路径。

    students/<name>/<exam-slug>/  例：2026-chaoyang-yi-physics
    → knowledge-base/exams/mock/physics/<region>/2026-chaoyang-yi.yaml
    """
    slug = exam_dir.name
    m = SLUG_SUBJECT_RE.search(slug)
    if not m:
        return None
    subject = m.group(1)
    base_slug = slug[:m.start()]
    subj_dir = DEFAULT_KB_ROOT / subject
    if not subj_dir.exists():
        return None
    # rglob 找 <base_slug>.yaml（任意区域子目录）
    hits = list(subj_dir.rglob(f"{base_slug}.yaml"))
    return hits[0] if hits else None


def load_standard_choice_answers(yaml_path: Path) -> dict[str, str]:
    """从试卷 yaml 提取选择题标准答案。返回 {qId: answer_str}"""
    if not yaml_path or not yaml_path.exists():
        return {}
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    answers = {}
    for q in data.get("questions", []):
        qtype = q.get("type", "")
        # 兼容中英文 type
        if qtype in ("choice", "multi_choice", "单选", "多选"):
            qid = q.get("id")
            if isinstance(qid, int):
                qid = f"Q{qid}"
            elif isinstance(qid, str) and not qid.startswith("Q"):
                qid = f"Q{qid}"
            ans = str(q.get("answer", "")).strip()
            if qid and ans:
                answers[qid] = ans
    return answers


# ─── 检测规则 ────────────────────────────────────────────────────────────────

def detect_issues(answer: dict, std_answer: str | None = None) -> list[dict]:
    """逐题检测。返回 [{code, level, msg}]。"""
    issues = []
    qid = answer.get("qId", "")
    qtype = answer.get("type", "")
    filled = answer.get("filled")
    conf = float(answer.get("confidence", 0))
    ocr_seen = answer.get("ocrSeen", "")

    # 1. 未作答
    if not filled or (isinstance(filled, list) and not filled):
        issues.append({"code": "no_answer", "level": "warn",
                       "msg": "未识别到作答（可能涂得太浅）"})

    # 2. OCR 异常（conf 0.3 = 4 个字母都缺）
    if conf <= 0.3:
        issues.append({"code": "ocr_fail", "level": "error",
                       "msg": f"OCR 异常（conf={conf}，可能整段失败）"})
    elif conf <= 0.5:
        issues.append({"code": "low_conf", "level": "warn",
                       "msg": f"低置信度（conf={conf}），建议核对原图"})

    # 3. 多选异常
    if qtype == "multi_choice":
        n = len(filled) if isinstance(filled, list) else 0
        if n == 4:
            issues.append({"code": "multi_all", "level": "warn",
                           "msg": "多选题选了全部 4 个，可能 OCR 异常"})
        elif n == 1:
            issues.append({"code": "multi_single", "level": "warn",
                           "msg": "多选题只选了 1 个，可能漏选"})

    # 4. 与标准答案比对
    if std_answer:
        student_str = "".join(filled) if isinstance(filled, list) else str(filled)
        student_set = set(student_str)
        std_set = set(std_answer)
        if student_set == std_set:
            pass  # 正确
        elif student_set < std_set:
            missing = sorted(std_set - student_set)
            issues.append({"code": "partial_correct", "level": "warn",
                           "msg": f"漏选 {'/'.join(missing)}（学生选 {student_str}，标准 {std_answer}）"})
        elif student_set > std_set:
            extra = sorted(student_set - std_set)
            issues.append({"code": "extra_select", "level": "error",
                           "msg": f"多选 {'/'.join(extra)}（学生选 {student_str}，标准 {std_answer}）"})
        else:
            issues.append({"code": "wrong", "level": "error",
                           "msg": f"答错（学生选 {student_str}，标准 {std_answer}）"})

    return issues


def check_card(data: dict, std_answers: dict) -> list[dict]:
    """卷级检查。"""
    issues = []
    student = data.get("student", {})
    if not student.get("name"):
        issues.append({"code": "no_name", "msg": "学生姓名为空"})
    if not student.get("examId"):
        issues.append({"code": "no_exam_id", "msg": "考号为空"})

    answers = data.get("answers", [])
    if not answers:
        issues.append({"code": "no_answers", "msg": "未识别到任何答案，OCR 完全失败"})

    if std_answers:
        std_qids = set(std_answers)
        student_qids = set(a.get("qId") for a in answers)
        missing = sorted(std_qids - student_qids, key=lambda q: int(q[1:]) if q[1:].isdigit() else 0)
        if missing:
            issues.append({"code": "missing_qs",
                           "msg": f"标准答案有 {len(std_qids)} 选择题但学生作答只识别到 {len(student_qids)}，缺：{', '.join(missing)}"})

    return issues


# ─── 加载学生数据 ────────────────────────────────────────────────────────────

def _photo_to_b64(path: Path, max_kb: int = 800) -> str | None:
    """读图转 base64 data URL。"""
    if not path.exists():
        return None
    try:
        b = path.read_bytes()
        # 简单尺寸保护：超过 800KB 也放进去（HEIC 已转 JPG，一般够小）
        ext = path.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "heic": "image/heic"}.get(ext, "image/jpeg")
        return f"data:{mime};base64,{base64.b64encode(b).decode('ascii')}"
    except Exception:
        return None


def load_exam_card(exam_dir: Path, standard_path: Path | None = None) -> dict:
    """加载一个学生 + 一份考试的所有数据，附加检测结果。

    exam_dir: students/<name>/<exam-slug>/
    """
    card_path = exam_dir / "answer-card.json"
    if not card_path.exists():
        raise FileNotFoundError(f"找不到 answer-card.json: {card_path}")
    data = json.loads(card_path.read_text(encoding="utf-8"))

    # 标准答案
    if standard_path is None:
        standard_path = infer_standard_path(exam_dir)
    std_answers = load_standard_choice_answers(standard_path) if standard_path else {}

    # 学生 metadata（合并 student.json，如有）
    student_json = exam_dir / "student.json"
    if student_json.exists():
        sj = json.loads(student_json.read_text(encoding="utf-8"))
        data.setdefault("student", {})
        for k, v in sj.items():
            data["student"].setdefault(k, v)

    # 标记每题检测 + 对错
    for a in data.get("answers", []):
        std = std_answers.get(a.get("qId"))
        a["_std_answer"] = std
        # 主观题：不做选择题检测，不算对错
        if a.get("type") == "subjective":
            a["_issues"] = []
            a["_correct"] = None
        else:
            a["_issues"] = detect_issues(a, std)
            if std and a.get("filled"):
                student_str = "".join(a["filled"]) if isinstance(a["filled"], list) else str(a["filled"])
                a["_correct"] = set(student_str) == set(std)
            else:
                a["_correct"] = None

        # 主观题：加载裁切的原图 base64
        if a.get("regionImage"):
            region_path = exam_dir / "answer-card-photos" / a["regionImage"]
            a["_region_b64"] = _photo_to_b64(region_path)
        else:
            a["_region_b64"] = None

    data["_card_issues"] = check_card(data, std_answers)
    data["_standard_path"] = str(standard_path) if standard_path else None
    data["_standard_count"] = len(std_answers)
    data["_exam_dir"] = str(exam_dir)
    data["_exam_slug"] = exam_dir.name

    # 原图（base64 内嵌）
    photos_dir = exam_dir / "answer-card-photos"
    photos = []
    if photos_dir.exists():
        for p in sorted(photos_dir.iterdir()):
            if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".heic"):
                continue
            b64 = _photo_to_b64(p)
            if b64:
                photos.append({"name": p.name, "data": b64})
    data["_photos"] = photos

    return data


def collect_cards(arg_path: str | None, student_dir: str | None,
                  student_all: str | None) -> list[Path]:
    """根据 CLI 参数收集要审核的学生考试目录列表。"""
    if arg_path:
        p = Path(arg_path)
        if p.is_file() and p.name == "answer-card.json":
            return [p.parent]
        if p.is_dir() and (p / "answer-card.json").exists():
            return [p]
        # 也许是相对路径
        return [p]
    if student_dir:
        return [Path(student_dir)]
    if student_all:
        base = Path(student_all)
        return sorted(d for d in base.iterdir()
                      if d.is_dir() and (d / "answer-card.json").exists())
    return []


# ─── HTML 拼装 ───────────────────────────────────────────────────────────────

def build_html(cards: list[dict]) -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"找不到模板：{TEMPLATE_PATH}")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    def clean(c):
        out = {}
        out["student"] = c.get("student", {})
        out["answers"] = c.get("answers", [])
        out["_card_issues"] = c.get("_card_issues", [])
        out["_standard_path"] = c.get("_standard_path")
        out["_standard_count"] = c.get("_standard_count", 0)
        out["_exam_dir"] = c.get("_exam_dir", "")
        out["_exam_slug"] = c.get("_exam_slug", "")
        out["_photos"] = c.get("_photos", [])
        return out

    cleaned = [clean(c) for c in cards]
    cards_json = json.dumps(cleaned, ensure_ascii=False, default=str)
    return template.replace("__CARDS_JSON__", cards_json)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="answer-card-review",
        description="学生答题卡审核工具（answer-card.json 可视化 + 对错判定）",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("path", nargs="?",
                       help="单学生考试目录（含 answer-card.json）或 .json 文件")
    group.add_argument("--student-dir", help="同 path（兼容旧式）")
    group.add_argument("--student-all", help="某学生全部考试（students/<name>/）")
    parser.add_argument("--standard", help="标准答案 yaml 路径（不传则自动从 exam-slug 推断）")
    parser.add_argument("--out", help="输出 HTML 路径（默认临时文件，自动打开浏览器）")
    parser.add_argument("--no-open", action="store_true", help="只生成不打开浏览器")
    args = parser.parse_args()

    exam_dirs = collect_cards(args.path, args.student_dir, args.student_all)
    if not exam_dirs:
        print("❌ 未找到学生考试目录或 answer-card.json", file=sys.stderr); sys.exit(1)

    standard_path = Path(args.standard).resolve() if args.standard else None

    print(f"📂 加载 {len(exam_dirs)} 份答题卡…")
    cards = []
    for d in exam_dirs:
        try:
            c = load_exam_card(d, standard_path)
            cards.append(c)
            n_ans = len(c.get("answers", []))
            n_std = c.get("_standard_count", 0)
            correct = sum(1 for a in c["answers"] if a.get("_correct") is True)
            print(f"  ✓ {d.name}: {n_ans} 题识别 / 标准 {n_std} 题 / 正确 {correct}")
        except Exception as e:
            print(f"  ✗ {d}: {e}", file=sys.stderr)

    if not cards:
        print("❌ 没有成功加载任何卡", file=sys.stderr); sys.exit(1)

    html = build_html(cards)

    if args.out:
        out_path = args.out
        Path(out_path).write_text(html, encoding="utf-8")
    else:
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8",
            prefix="answer-card-review-",
        )
        tf.write(html)
        tf.flush()
        out_path = tf.name

    print(f"🌐 生成: {out_path}")
    if not args.no_open:
        webbrowser.open(f"file://{os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
