"""从答题卡 OCR 文本识别考试身份（区/科目/年份/模别）+ 学生信息。

北京模拟卷答题卡表头典型：
  北京市朝阳区九年级综合练习（一）   ← 区 + 模别（一）=一模 （二）=二模
  物理答题卡                          ← 科目
  2026.4                              ← 年份
  学校：北京市朝阳外国语学校
  姓名：贾小淇
  准考证号：17020950

输出 exam_slug = <year>-<district_en>-<examtype_en>-<subject_en>，
并校验 knowledge-base 是否有对应 yaml。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = ROOT / "knowledge-base" / "mock-exams"

DISTRICT_EN = {
    "海淀": "haidian", "西城": "xicheng", "东城": "dongcheng", "朝阳": "chaoyang",
    "丰台": "fengtai", "石景山": "shijingshan", "顺义": "shunyi", "门头沟": "mentougou",
    "昌平": "changping", "房山": "fangshan", "通州": "tongzhou", "大兴": "daxing",
    "延庆": "yanqing", "平谷": "pinggu", "怀柔": "huairou", "密云": "miyun",
    "燕山": "yanshan",
}
SUBJECT_EN = {
    "语文": "chinese", "数学": "math", "英语": "english",
    "物理": "physics", "道德与法治": "politics", "道法": "politics",
    "化学": "chemistry", "历史": "history",
}
SUBJECT_DIR = {"chinese": "chinese", "math": "math", "english": "english",
               "physics": "physics", "politics": "politics",
               "chemistry": "chemistry", "history": "history"}


def _exam_type(text: str) -> tuple[str, str]:
    """返回 (中文, en)。模拟卷术语：综合练习（一）/一模 → yi。"""
    if "综合练习（一）" in text or "综合练习(一)" in text or "一模" in text \
       or "第一次模拟" in text:
        return "一模", "yi"
    if "综合练习（二）" in text or "综合练习(二)" in text or "二模" in text \
       or "第二次模拟" in text:
        return "二模", "er"
    if "综合练习（三）" in text or "三模" in text:
        return "三模", "san"
    if "学业水平" in text or "中考" in text:
        return "中考真题", "zhenti"
    return "", ""


def extract_identity(lines: list[str]) -> dict:
    """从 OCR 行抽考试身份 + 学生信息。字段缺失则为空串。"""
    head = "\n".join(lines[:15])  # 表头集中在前若干行

    # 年份
    ym = re.search(r"(20\d{2})\s*[.\-年]", head) or re.search(r"(20\d{2})", head)
    year = ym.group(1) if ym else ""

    # 区
    district = district_en = ""
    for cn, en in DISTRICT_EN.items():
        if f"{cn}区" in head or f"北京市{cn}" in head or f"{cn}县" in head:
            district, district_en = cn, en
            break

    # 科目（"物理答题卡" / "数学 答题卡"）
    subject = subject_en = ""
    sm = re.search(r"(语文|数学|英语|物理|道德与法治|道法|化学|历史)\s*答题卡", head)
    if not sm:
        sm = re.search(r"(语文|数学|英语|物理|道德与法治|道法|化学|历史)", head)
    if sm:
        subject = sm.group(1)
        subject_en = SUBJECT_EN.get(subject, "")

    exam_cn, exam_en = _exam_type(head)

    # 学生
    name = ""
    nm = re.search(r"姓\s*名[：:\s]*([一-龥·]{2,6})", head)
    if nm:
        name = nm.group(1)
    sid = ""
    im = re.search(r"准考证号[：:\s]*([0-9A-Za-z]{4,20})", head)
    if im:
        sid = im.group(1)

    slug = ""
    if year and district_en and exam_en and subject_en:
        slug = f"{year}-{district_en}-{exam_en}-{subject_en}"

    return {
        "year": year, "district": district, "district_en": district_en,
        "subject": subject, "subject_en": subject_en,
        "exam_type": exam_cn, "exam_type_en": exam_en,
        "exam_slug": slug, "student_name": name, "student_id": sid,
    }


def kb_yaml_for_slug(slug: str) -> Path | None:
    """exam_slug → mock-exams yaml（兼容 2026-chaoyang-yi[-physics].yaml 两式）。"""
    parts = slug.split("-")
    if len(parts) < 4:
        return None
    subj = parts[-1]
    base = KB_ROOT / SUBJECT_DIR.get(subj, subj) / "beijing"
    if not base.exists():
        return None
    no_subj = "-".join(parts[:-1])
    for cand in (base / f"{no_subj}.yaml", base / f"{slug}.yaml"):
        if cand.exists():
            return cand
    return None


EXAMTYPE_EN = {"一模": "yi", "二模": "er", "三模": "san",
               "中考": "zhenti", "中考真题": "zhenti"}


def slug_from_meta(meta: dict) -> dict:
    """card_meta（qwen-vl-max 中文字段）→ exam_slug + KB 校验。"""
    district = (meta.get("district") or "").strip().replace("区", "")
    subject_cn = (meta.get("subject") or "").strip()
    year = re.sub(r"\D", "", str(meta.get("year") or ""))[:4]
    et_cn = (meta.get("exam_type") or "").strip()

    district_en = DISTRICT_EN.get(district, "")
    subject_en = SUBJECT_EN.get(subject_cn, "")
    et_en = EXAMTYPE_EN.get(et_cn, "")

    slug = ""
    if year and district_en and et_en and subject_en:
        slug = f"{year}-{district_en}-{et_en}-{subject_en}"
    y = kb_yaml_for_slug(slug) if slug else None
    return {
        "exam_slug": slug, "matched": bool(y), "yaml": str(y) if y else "",
        "district": district, "district_en": district_en,
        "subject": subject_cn, "subject_en": subject_en,
        "year": year, "exam_type": et_cn, "exam_type_en": et_en,
        "student_name": (meta.get("student_name") or "").strip(),
        "student_id": (meta.get("student_id") or "").strip(),
    }


def detect_exam(lines: list[str]) -> dict:
    """主入口：识别 + 校验知识库。返回 identity，额外含 matched(bool) + yaml。"""
    idy = extract_identity(lines)
    y = kb_yaml_for_slug(idy["exam_slug"]) if idy["exam_slug"] else None
    idy["matched"] = bool(y)
    idy["yaml"] = str(y) if y else ""
    return idy


if __name__ == "__main__":
    import sys, json
    txt = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read()
    print(json.dumps(detect_exam(txt.splitlines()), ensure_ascii=False, indent=2))
