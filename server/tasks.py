"""后台任务：两段式。

A. 检测（detect_only，上传后立即跑，~10s）：
   card_meta(qwen-vl-max) 读表头 → 考试身份 + 学生 + 卷面完整性
   → 按 slug 重命名学生目录 + 写 student.json → status='ready_confirm'
   家长在「答题卡页」看到识别结果 + 可下载试卷原卷确认。

B. 流水线（run_pipeline，家长确认 + 传小分后由 /start 触发）：
   detect.detect_card 真实涂卡 → answer-card.json
   → 等上传小分 → build_report → done

阶段（status/stage_name）：
  detecting → ready_confirm →(/start)→ running(识别作答/对照标答/AI分析/提分建议) → done|failed
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path

import db
import pipeline_adapter as pa
import exam_match
import precheck

ROOT = Path(__file__).resolve().parents[1]
SR_DIR = ROOT / "scripts" / "answer-card-ocr"
UPLOAD_ROOT = ROOT / "server" / "uploads"

_lock = threading.Lock()


_CHOICE_TYPES = {"单选", "多选", "choice", "multi_choice"}


def _subjective_qnums(yaml_path: Path) -> list[int]:
    """从 KB 试卷 yaml 推导主观题题号（非选择题型）。

    驱动 detect_card 的 Phase B（裁切+手写OCR）/ Phase C（看图评分）。
    """
    import re
    import yaml as _yaml
    d = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    out: list[int] = []
    for q in d.get("questions", []):
        if q.get("type") in _CHOICE_TYPES:
            continue
        m = re.search(r"\d+", str(q.get("id", "")))
        if m:
            out.append(int(m.group()))
    return sorted(set(out))


def _kb_expected(yaml_path: Path) -> dict:
    """该卷应有的选择题/主观题数（L3 交叉核对用）。"""
    import yaml as _yaml
    d = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    qs = d.get("questions", [])
    choice = sum(1 for q in qs if q.get("type") in _CHOICE_TYPES)
    return {"choice": choice, "subjective": len(qs) - choice}


def _kb_choice_qnums(yaml_path: Path) -> list[int]:
    """KB 试卷中选择题的题号（用于 Phase A 漏识别交叉核对）。"""
    import re as _re
    import yaml as _yaml
    d = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    out: list[int] = []
    for q in d.get("questions", []):
        if q.get("type") not in _CHOICE_TYPES:
            continue
        m = _re.search(r"\d+", str(q.get("id", "")))
        if m:
            out.append(int(m.group()))
    return sorted(set(out))


def _filter_answer_card_pages(imgs: list[Path], per_page: list[dict]) -> tuple[list[Path], list[int]]:
    """按 card_meta.per_page 剔除 is_answer_card=False 的页（P1.1 / B-选 1）。

    返回：(剔除后的图片列表, 被忽略的页 i 列表)
    """
    if not per_page:
        return imgs, []
    skip_idx = {p["i"] for p in per_page
                if isinstance(p, dict) and p.get("is_answer_card") is False}
    if not skip_idx:
        return imgs, []
    kept = [img for i, img in enumerate(imgs, 1) if i not in skip_idx]
    return kept, sorted(skip_idx)


def _imgs(photos_dir: Path) -> list[Path]:
    return sorted(
        p for p in photos_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic")
        and p.stat().st_size > 1024
    )


# ============== A. 检测 ==============

def submit_detect(aid: str, student_dir: Path):
    threading.Thread(target=_detect, args=(aid, student_dir),
                     daemon=True).start()


def _detect(aid: str, student_dir: Path):
    try:
        db.set_detected(aid, "", "detecting", "识别考试信息")
        photos_dir = student_dir / "answer-card-photos"
        imgs = _imgs(photos_dir)
        if not imgs:
            raise RuntimeError("无有效答题卡图片")

        sys.path.insert(0, str(SR_DIR))
        import card_meta  # noqa

        meta = card_meta.extract_card_meta(imgs)
        idy = exam_match.slug_from_meta(meta)
        idy["exam_title"] = meta.get("exam_title", "")
        idy["completeness_note"] = meta.get("completeness_note", "")
        idy["pages_complete"] = bool(meta.get("pages_complete", False))

        if not idy["matched"]:
            # 识别不到考试 → 失败（让用户重拍含顶部标题行的照片重传）
            db.mark_failed(
                aid,
                "没能从答题卡识别出考试信息。请重新拍照上传——"
                "务必拍清「考生须知页」最顶部的标题行"
                "（如「北京市朝阳区九年级综合练习（一）物理答题卡」）。")
            return

        # ---- 预检 L1+L2+L3：全流水线之前快失败，给逐页可执行指引 ----
        slug = idy["exam_slug"]
        try:
            yaml_path = exam_match.kb_yaml_for_slug(slug)
            expected = _kb_expected(Path(yaml_path)) if yaml_path else {}
        except Exception:
            expected = {}
        quality = precheck.image_quality(imgs)            # L1 本地质量门
        pc = precheck.evaluate(meta, quality, expected)   # +L2 结构化 +L3 KB
        idy["precheck"] = pc
        if pc["block"]:
            db.set_detected(aid, json.dumps(idy, ensure_ascii=False),
                            "detecting", "预检未通过")
            db.mark_failed(aid, precheck.block_message(pc))
            return

        name = idy.get("student_name") or "考生"

        # 按 slug 重命名目录（infer_standard 靠 dir 名找 yaml）
        if slug and student_dir.name != slug:
            new_dir = student_dir.parent / slug
            if new_dir.exists():
                import shutil
                shutil.rmtree(new_dir)
            student_dir.rename(new_dir)
            student_dir = new_dir
        (student_dir / "student.json").write_text(
            json.dumps({"name": name,
                        "examId": idy.get("student_id", "")},
                       ensure_ascii=False), encoding="utf-8")
        db.set_exam_info(aid, name, slug, str(student_dir))

        idy["student_dir"] = str(student_dir)
        db.set_detected(aid, json.dumps(idy, ensure_ascii=False),
                        "ready_confirm", "待确认")
    except Exception as e:
        traceback.print_exc()
        db.mark_failed(aid, f"{type(e).__name__}: {e}")


# ============== B. 流水线 ==============

def submit_pipeline(aid: str, student_dir: Path):
    threading.Thread(target=_pipeline, args=(aid, student_dir),
                     daemon=True).start()


def _ensure_scores(aid: str, student_dir: Path, wait_s: int = 25):
    """小分可选：
    - 家长上传了班小二小分 → 用它（老师阅卷分，权威）
    - 没上传 → 系统自动判分（选择题确定性 + 主观题 qwen-vl-max 看图估分）
    短暂等待上传到位（家长可能正传）；超时则自动判分，不再失败。
    """
    target = student_dir / "scores.json"
    src_marker = student_dir / ".score_source"
    uploaded = UPLOAD_ROOT / aid / "scores.json"
    waited = 0
    while waited < wait_s:
        if uploaded.exists():
            target.write_bytes(uploaded.read_bytes())
            src_marker.write_text("teacher", encoding="utf-8")
            return
        time.sleep(3)
        waited += 3

    # 无小分 → 自动判分
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    import auto_grade, exam_match  # noqa
    yaml_path = exam_match.kb_yaml_for_slug(student_dir.name)
    if not yaml_path:
        raise RuntimeError(f"找不到试卷标准答案：{student_dir.name}")
    db.update_stage(aid, 3, "无小分，系统自动判分中")
    auto_grade.write_auto_scores(student_dir, Path(yaml_path))
    src_marker.write_text("auto", encoding="utf-8")


def _pipeline(aid: str, student_dir: Path):
    with _lock:
        try:
            db.update_stage(aid, 2, "识别答题卡作答")
            sys.path.insert(0, str(SR_DIR))
            import detect  # noqa

            photos_dir = student_dir / "answer-card-photos"
            imgs = _imgs(photos_dir)

            # 接入完整技能流水线：Phase A 选择题缺字母法 +
            # Phase B 主观题腾讯云方框+讯飞手写裁切 +
            # Phase C qwen-vl-max 看图阅卷（产 grade.missedPoints 供报告错因）
            yaml_path = exam_match.kb_yaml_for_slug(student_dir.name)
            if not yaml_path:
                raise RuntimeError(f"找不到试卷标准答案：{student_dir.name}")
            subj_qnums = _subjective_qnums(Path(yaml_path))
            choice_qnums = _kb_choice_qnums(Path(yaml_path))

            # P1.1：按 card_meta.per_page 剔除"非答题卡页"（混拍场景）
            detected_raw = db.get_analysis(aid).get("detected") or "{}"
            try:
                _det = json.loads(detected_raw)
            except json.JSONDecodeError:
                _det = {}
            per_page = (_det.get("per_page") if isinstance(_det, dict) else None) or []
            imgs_filtered, skipped_pages = _filter_answer_card_pages(imgs, per_page)
            if not imgs_filtered:
                raise RuntimeError("剔除非答题卡页后无有效图片，请重新上传")
            if skipped_pages:
                print(f"[_pipeline {aid}] 剔除非答题卡页：{skipped_pages}",
                      flush=True)

            db.update_stage(aid, 2, "识别答题卡作答（选择题+主观题裁切）")
            res = detect.detect_card(
                imgs_filtered, photos_dir=photos_dir,
                subjective_qnums=subj_qnums,
                standard_yaml=Path(yaml_path))

            # 学生名以 student.json 为准（card_meta 表头识别 / 家长确认页纠正，
            # 均比答题卡涂卡区 OCR 可靠），始终覆盖 detect 结果
            sj = student_dir / "student.json"
            known = json.loads(sj.read_text()) if sj.exists() else {}
            stu = dict(getattr(res, "student", {}) or {})
            if known.get("name"):
                stu["name"] = known["name"]
            if known.get("examId") and not stu.get("examId"):
                stu["examId"] = known["examId"]
            # 计算答题卡识别覆盖（P0.1 + P0.2 缺失追踪）
            choice_parsed = set(getattr(res, "choice_qids_parsed", []) or [])
            subj_cropped = set(getattr(res, "subjective_qids_cropped", []) or [])
            missing_choice = sorted(set(choice_qnums) - choice_parsed)
            missing_subj = sorted(set(subj_qnums) - subj_cropped)
            (student_dir / "answer-card.json").write_text(
                json.dumps({
                    "student": stu or known,
                    "answers": getattr(res, "answers", []),
                    "_data_quality": {
                        "missing_choice_qids": [f"Q{n}" for n in missing_choice],
                        "missing_subjective_qids": [f"Q{n}" for n in missing_subj],
                        "skipped_non_card_pages": skipped_pages,
                    },
                }, ensure_ascii=False, indent=2), encoding="utf-8")

            db.update_stage(aid, 3, "对照标准答案")
            _ensure_scores(aid, student_dir)

            def on_stage(idx, n):
                db.update_stage(aid, idx, n)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")


# ---- Phase 1 纯 reference 演示（无上传）----

def submit_reference(aid: str, student_dir: Path):
    threading.Thread(target=_reference, args=(aid, student_dir),
                     daemon=True).start()


def _reference(aid: str, student_dir: Path):
    with _lock:
        try:
            for i, n in [(1, "识别考试信息"), (2, "识别答题卡作答")]:
                db.update_stage(aid, i, n)

            def on_stage(idx, nm):
                db.update_stage(aid, idx, nm)

            pdf = pa.run_report(student_dir, on_stage=on_stage)
            db.mark_done(aid, str(pdf))
        except Exception as e:
            traceback.print_exc()
            db.mark_failed(aid, f"{type(e).__name__}: {e}")
