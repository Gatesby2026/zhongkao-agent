#!/usr/bin/env python3
"""
北京中考数学试卷 — 结构化数据质量验证脚本
Layer1: 覆盖检测（原卷 ↔ YAML 匹配）
Layer2: 结构检测（题数/分值/题型分布）
Layer3: 答案检测（逐题答案比对）

用法:
    python3 scripts/validate-exam-structure.py [--subject math] [--year 2023] [--layer 1] [--layer 2] [--layer 3]
    python3 scripts/validate-exam-structure.py --layer 1 2 3   # 跑所有层
"""

import os
import re
import sys
import yaml
import argparse
from pathlib import Path
from collections import defaultdict

# ============================================================
# 配置
# ============================================================

ROOT = Path(__file__).parent.parent
ORIG_DIR = ROOT / "knowledge-original"
KB_DIR = ROOT / "knowledge-base"

SUBJECTS = {
    "math":    ("北京中考数学模拟卷", "mock-exams/math/beijing"),
    "chinese": ("北京中考语文模拟卷", "mock-exams/chinese/beijing"),
    "english": ("北京中考英语模拟卷", "mock-exams/english/beijing"),
    "physics": ("北京中考物理模拟卷", "mock-exams/physics/beijing"),
    "politics":("北京中考道法模拟卷", "mock-exams/politics/beijing"),
}

# 区名 → 英文 key
DISTRICT_MAP = {
    "海淀": "haidian", "西城": "xicheng", "东城": "dongcheng",
    "朝阳": "chaoyang", "丰台": "fengtai", "石景山": "shijingshan",
    "通州": "tongzhou", "大兴": "daxing", "房山": "fangshan",
    "顺义": "shunyi", "门头沟": "mentougou", "密云": "miyun",
    "平谷": "pinggu", "燕山": "yanshan", "延庆": "yanqing",
}

EXAM_TYPE_MAP = {"一模": "yi", "二模": "er", "三模": "san"}

# 标准试卷结构（题号→题型）
# 北京中考数学: 1-8 选择, 9-16 填空, 17-28 解答
STANDARD_STRUCTURE = {
    "选择": (1, 8),
    "填空": (9, 16),
    "解答": (17, 28),
}

# 解答题标准分值（北京中考）
SOLUTION_SCORES = {
    17: 5, 18: 5, 19: 5, 20: 5,
    21: 5, 22: 5, 23: 6, 24: 6,
    25: 6, 26: 6, 27: 7, 28: 7,
}


# ============================================================
# Layer1: 覆盖检测
# ============================================================

def parse_original_dir(orig_path):
    """
    扫描原始试卷目录，返回文件列表。
    返回: dict[exam_key] -> {year, district, exam_type, juan_path, jiexi_path}
    """
    exams = {}
    orig_path = Path(orig_path)

    for top_folder in sorted(orig_path.iterdir()):
        if not top_folder.is_dir():
            continue
        year_match = re.match(r"(\d{4})年北京中考", top_folder.name)
        if not year_match:
            continue
        year = year_match.group(1)

        for sub_folder in sorted(top_folder.iterdir()):
            if not sub_folder.is_dir():
                continue
            # 解析子目录名得到区+类型
            # 格式如: "2023年北京中考数学二模15份"
            # 或: "精品解析：2023年北京市东城区中考二模数学试题"
            folder_name = sub_folder.name.replace("精品解析：", "")

            # 提取区和类型
            district_cn = None
            exam_type_cn = None
            for dt_cn, dt_key in EXAM_TYPE_MAP.items():
                if dt_cn in folder_name:
                    exam_type_cn = dt_cn
                    exam_type_key = dt_key
                    break
            if not exam_type_cn:
                continue

            # 提取区
            for dc, dk in DISTRICT_MAP.items():
                if dc in folder_name:
                    district_cn = dc
                    district_key = dk
                    break
            if not district_cn:
                continue

            key = f"{year}-{district_key}-{exam_type_key}"

            # 找docx文件
            juan_files = list(sub_folder.glob("*原卷版*.docx"))
            jiexi_files = list(sub_folder.glob("*解析版*.docx"))

            exams[key] = {
                "year": year,
                "district_cn": district_cn,
                "district_key": district_key,
                "exam_type_cn": exam_type_cn,
                "exam_type_key": exam_type_key,
                "folder": str(sub_folder),
                "juan_path": str(juan_files[0]) if juan_files else None,
                "jiexi_path": str(jiexi_files[0]) if jiexi_files else None,
            }

    return exams


def parse_yaml_dir(yaml_dir):
    """
    扫描YAML目录，返回文件元数据。
    返回: dict[exam_key] -> yaml_data
    注意：YAML中district是"朝阳区"（带区字），exam_type是"一模"（中文），
    需去掉"区"字后匹配 DISTRICT_MAP，转 exam_type 为英文 key。
    """
    # 中文考试类型 → 英文 key
    exam_type_cn_to_key = {v: k for k, v in EXAM_TYPE_MAP.items()}  # {"一模": "yi", ...}

    yamls = {}
    yaml_dir = Path(yaml_dir)

    for yf in sorted(yaml_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
            if not data or "year" not in data:
                continue

            # 转换 exam_type → 英文 key
            exam_type_cn = data.get("exam_type", "")
            exam_type_key = exam_type_cn_to_key.get(exam_type_cn, exam_type_cn)

            # 转换 district → 英文 key（YAML中是"朝阳区"，需去掉"区"字再匹配）
            district_cn = data.get("district", "")
            district_stripped = district_cn.replace("区", "").replace("县", "")
            district_key = DISTRICT_MAP.get(district_stripped, district_stripped)

            key = f"{data['year']}-{district_key}-{exam_type_key}"
            data["_key"] = key
            yamls[key] = data
        except Exception:
            pass

    return yamls


def layer1_coverage_check(subject):
    """Layer1: 检测原卷与YAML的覆盖差异"""
    orig_subfolder, yaml_subfolder = SUBJECTS[subject]
    orig_path = ORIG_DIR / orig_subfolder
    yaml_path = KB_DIR / yaml_subfolder

    if not yaml_path.exists():
        print(f"[Layer1] YAML目录不存在: {yaml_path}")
        return

    orig_exams = parse_original_dir(orig_path)
    yaml_exams = parse_yaml_dir(yaml_path)

    orig_keys = set(orig_exams.keys())
    yaml_keys = set(yaml_exams.keys())

    only_orig = orig_keys - yaml_keys
    only_yaml = yaml_keys - orig_keys

    print(f"\n{'='*60}")
    print(f"Layer1 覆盖检测 — {subject}")
    print(f"{'='*60}")
    print(f"  原卷数量: {len(orig_keys)}")
    print(f"  YAML数量: {len(yaml_keys)}")
    print(f"  匹配数量: {len(orig_keys & yaml_keys)}")

    if only_orig:
        print(f"\n  ⚠️ 原卷有但YAML缺失 ({len(only_orig)}份):")
        for k in sorted(only_orig):
            info = orig_exams[k]
            print(f"    - {info['year']}年 {info['district_cn']} {info['exam_type_cn']}  →  {k}")
            print(f"      路径: {info['folder']}")

    if only_yaml:
        print(f"\n  ⚠️ YAML有但原卷缺失 ({len(only_yaml)}份，可能是真题):")
        for k in sorted(only_yaml):
            d = yaml_exams[k]
            print(f"    - {d['year']}年 {d.get('district','?')} {d.get('exam_type','?')}  →  {k}")

    if not only_orig and not only_yaml:
        print(f"\n  ✅ 覆盖完整，原卷与YAML完全匹配")


# ============================================================
# Layer2: 结构检测
# ============================================================

def layer2_structure_check(subject):
    """Layer2: 题数/分值/题型分布与YAML结构字段比对"""
    _, yaml_subfolder = SUBJECTS[subject]
    yaml_path = KB_DIR / yaml_subfolder

    if not yaml_path.exists():
        print(f"[Layer2] YAML目录不存在: {yaml_path}")
        return

    yaml_exams = parse_yaml_dir(yaml_path)

    errors = []
    warnings = []

    for key, data in sorted(yaml_exams.items()):
        year = data.get("year", "?")
        district = data.get("district", "?")
        exam_type = data.get("exam_type", "?")
        label = f"{year}年 {district} {exam_type}"

        questions = data.get("questions", [])
        actual_count = len(questions)

        # 1. 检查题数
        declared_count = data.get("total_questions", 0)
        if actual_count != declared_count:
            errors.append(f"  ❌ 题数不符: 声明{declared_count}题, 实际{actual_count}题  [{label}]")

        # 2. 检查分值加总
        actual_score = sum(q.get("score", 0) for q in questions)
        declared_score = data.get("full_score", 0)
        if actual_score != declared_score:
            errors.append(f"  ❌ 分值不符: 声明{declared_score}分, 加总{actual_score}分  [{label}]")

        # 3. 检查题型分布
        structure = data.get("structure", "")
        # 格式如: "8选择(16分) + 8填空(16分) + 12解答(68分)"
        type_counts = {}
        for m in re.finditer(r"(\d+)(选择|填空|解答)\((\d+)分\)", structure):
            type_counts[m.group(2)] = (int(m.group(1)), int(m.group(3)))

        for qtype, (expected_n, expected_pts) in type_counts.items():
            actual_n = sum(1 for q in questions if q.get("type") == qtype)
            if actual_n != expected_n:
                errors.append(f"  ❌ {qtype}数量不符: 声明{expected_n}题, 实际{actual_n}题  [{label}]")
            actual_pts = sum(q.get("score", 0) for q in questions if q.get("type") == qtype)
            if actual_pts != expected_pts:
                errors.append(f"  ❌ {qtype}分值不符: 声明{expected_pts}分, 加总{actual_pts}分  [{label}]")

        # 4. 检查各题分值是否合理（解答题）
        for q in questions:
            if q.get("type") == "解答":
                qid = q.get("id", 0)
                score = q.get("score", 0)
                expected = SOLUTION_SCORES.get(qid, 5)
                if score != expected:
                    warnings.append(f"  ⚠️ 第{qid}题分值{score}分, 标准应为{expected}分  [{label}]")

    print(f"\n{'='*60}")
    print(f"Layer2 结构检测 — {subject} ({len(yaml_exams)}份试卷)")
    print(f"{'='*60}")

    if errors:
        print(f"\n  错误 ({len(errors)}项):")
        for e in errors[:30]:
            print(e)
        if len(errors) > 30:
            print(f"  ... 还有 {len(errors)-30} 项错误")
    else:
        print(f"\n  ✅ 无结构错误")

    if warnings:
        print(f"\n  警告 ({len(warnings)}项):")
        for w in warnings[:20]:
            print(w)
        if len(warnings) > 20:
            print(f"  ... 还有 {len(warnings)-20} 项警告")


# ============================================================
# Layer3: 答案检测
# ============================================================

def extract_answers_from_docx(docx_path):
    """
    从解析版docx提取答案。
    策略：扫描每个段落，找 "[答案]" 标记或选项模式。
    返回: dict[question_id] -> answer_letter
    """
    try:
        import docx
    except ImportError:
        return {}

    doc = docx.Document(docx_path)
    answers = {}
    current_q_id = None

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # 识别题号
        # 格式1: "1." "2." 在段首
        m = re.match(r"^(\d+)[．.、]", text)
        if m:
            current_q_id = int(m.group(1))

        # 格式2: "答案：X" "答案:X" 或 "【答案】X"
        ans_m = re.search(r"(?:答案|Answer)[:：]\s*([A-G]?)", text, re.IGNORECASE)
        if ans_m and current_q_id:
            ans = ans_m.group(1).upper()
            if ans in ("A", "B", "C", "D"):
                answers[current_q_id] = ans
            current_q_id = None
            continue

        # 格式3: 直接是选项 "C" 单独成行（常见于答案页）
        if re.match(r"^[A-D]$", text) and current_q_id:
            answers[current_q_id] = text
            current_q_id = None

        # 格式4: "故.*选[择BC]" 解答题的答案说明
        jieda_ans = re.search(r"(?:故|则|可得)[^。]*[选故选]([A-D])", text)
        if jieda_ans and current_q_id:
            answers[current_q_id] = jieda_ans.group(1)
            current_q_id = None

    return answers


def layer3_answer_check(subject):
    """Layer3: 提取解析版答案，与YAML逐题比对"""
    orig_subfolder, yaml_subfolder = SUBJECTS[subject]
    orig_path = ORIG_DIR / orig_subfolder
    yaml_path = KB_DIR / yaml_subfolder

    yaml_exams = parse_yaml_dir(yaml_path)
    orig_exams = parse_original_dir(orig_path)

    print(f"\n{'='*60}")
    print(f"Layer3 答案检测 — {subject}")
    print(f"{'='*60}")

    total_compared = 0
    total_wrong = 0
    no_jiexi = []

    for key, data in sorted(yaml_exams.items()):
        if key not in orig_exams:
            continue

        orig_info = orig_exams[key]
        jiexi_path = orig_info.get("jiexi_path")

        if not jiexi_path:
            no_jiexi.append(key)
            continue

        # 提取docx答案
        docx_answers = extract_answers_from_docx(jiexi_path)

        # 与YAML比对（只比对选择和填空）
        questions = data.get("questions", [])
        wrong = []
        for q in questions:
            if q.get("type") not in ("选择", "填空"):
                continue
            qid = q.get("id")
            yaml_ans = q.get("answer", "").strip().upper()
            docx_ans = docx_answers.get(qid, "").strip().upper()

            if not docx_ans:
                continue  # 提取不到则跳过

            total_compared += 1
            if yaml_ans != docx_ans:
                wrong.append((qid, yaml_ans, docx_ans))
                total_wrong += 1

        label = f"{data.get('year')}年 {data.get('district')} {data.get('exam_type')}"
        if wrong:
            print(f"\n  ❌ {label}  — 答案错误 ({len(wrong)}处):")
            for qid, yAns, dAns in wrong:
                print(f"     第{qid}题: YAML={yAns}, 原卷={dAns}")

    if no_jiexi:
        print(f"\n  ⚠️ 有YAML但无解析版原卷 ({len(no_jiexi)}份):")
        for k in no_jiexi[:10]:
            print(f"     {k}")

    if total_compared == 0:
        print(f"\n  ⚠️ 未提取到有效答案对比（可能是docx格式不标准，或无解析版）")
        print(f"     提示: Layer3需要解析版docx，原卷版不含答案")
    else:
        print(f"\n  📊 共比对 {total_compared} 道选择/填空题，错误 {total_wrong} 道")
        if total_wrong == 0:
            print(f"  ✅ 全部答案正确")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="北京中考试卷结构化数据验证")
    parser.add_argument("--subject", "-s", default="math",
                        choices=list(SUBJECTS.keys()), help="科目 (默认: math)")
    parser.add_argument("--year", "-y", type=int, help="只验证特定年份")
    parser.add_argument("--layers", "-l", nargs="+", type=int,
                        default=[1, 2, 3], choices=[1, 2, 3],
                        help="跑哪些层 (默认: 1 2 3)")
    args = parser.parse_args()

    print(f"\n{'#'*60}")
    print(f"#  北京中考试卷结构化数据质量验证")
    print(f"#  科目: {args.subject}   层: {args.layers}")
    print(f"{'#'*60}")

    for layer in args.layers:
        if layer == 1:
            layer1_coverage_check(args.subject)
        elif layer == 2:
            layer2_structure_check(args.subject)
        elif layer == 3:
            layer3_answer_check(args.subject)

    print(f"\n{'='*60}")
    print(f"验证完成")


if __name__ == "__main__":
    main()
