#!/usr/bin/env python3
"""
将 knowledge-original 中的 docx 模考试卷转换为 knowledge-base YAML 格式。
用法: python3 scripts/docx-to-yaml.py
"""

import os
import re
import sys
import docx
import yaml

# ============================================================
# 配置
# ============================================================

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "knowledge-original", "北京中考数学模拟卷")
DST_DIR = os.path.join(ROOT, "knowledge-base", "mock-exams", "math", "beijing")

# 区名 → 英文 key
DISTRICT_MAP = {
    "海淀": "haidian",
    "西城": "xicheng",
    "东城": "dongcheng",
    "朝阳": "chaoyang",
    "丰台": "fengtai",
    "石景山": "shijingshan",
    "通州": "tongzhou",
    "大兴": "daxing",
    "房山": "fangshan",
    "顺义": "shunyi",
    "门头沟": "mentougou",
    "密云": "miyun",
    "平谷": "pinggu",
    "燕山": "yanshan",
    "延庆": "yanqing",
}

# 考试类型映射
EXAM_TYPE_MAP = {
    "一模": "yi",
    "二模": "er",
    "三模": "san",
}

# 模块关键词 → moduleId
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
        "坐标系", "动点", "最值", "存在性",
        "几何综合", "新定义",
    ],
}

# 难度判定规则（按题号）
def get_difficulty(qid, q_type):
    """根据题号和题型判断难度"""
    if q_type == "选择":
        if qid <= 5:
            return "基础"
        elif qid <= 7:
            return "中档"
        else:
            return "较难"
    elif q_type == "填空":
        real_id = qid - 8  # 填空题从9开始
        if real_id <= 4:
            return "基础"
        elif real_id <= 7:
            return "中档"
        else:
            return "较难"
    else:  # 解答题
        if qid <= 19:
            return "基础"
        elif qid <= 22:
            return "中档"
        elif qid <= 25:
            return "较难"
        else:
            return "压轴"

# recommended_for 判定
def get_recommended_for(difficulty):
    mapping = {
        "基础": ["L0", "L1", "L2", "L3"],
        "中档": ["L1", "L2", "L3"],
        "较难": ["L2", "L3"],
        "压轴": ["L3"],
    }
    return mapping.get(difficulty, ["L1", "L2", "L3"])

# 分值判定
def get_score(qid, q_type):
    if q_type in ("选择", "填空"):
        return 2
    # 解答题分值（北京中考标准）
    score_map = {
        17: 5, 18: 5, 19: 5, 20: 5,
        21: 5, 22: 5, 23: 6, 24: 6,
        25: 6, 26: 6, 27: 7, 28: 7,
    }
    return score_map.get(qid, 5)


# ============================================================
# 解析 docx
# ============================================================

def extract_paragraphs(docx_path):
    """提取 docx 的所有段落文本"""
    doc = docx.Document(docx_path)
    return [p.text.strip() for p in doc.paragraphs]


def detect_module(analysis_text, question_text):
    """根据【分析】和题目文本推断模块"""
    combined = analysis_text + " " + question_text
    scores = {}
    for module, keywords in MODULE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[module] = score
    if not scores:
        return "geometryComprehensive"  # 默认
    return max(scores, key=scores.get)


def parse_exam(paragraphs):
    """解析试卷段落，提取题目列表"""
    questions = []
    current_q = None
    current_section = None  # "question" | "answer" | "analysis" | "detail"
    current_type = None     # "选择" | "填空" | "解答"

    # 正则匹配题号
    q_pattern = re.compile(r'^(\d+)[.．、]\s*(.*)')
    answer_pattern = re.compile(r'【答案】(.*)')
    analysis_marker = re.compile(r'【(分析|解析)】(.*)')
    detail_marker = re.compile(r'【详解】(.*)')
    subq_marker = re.compile(r'【?小问\d+详解】?(.*)')

    for line in paragraphs:
        if not line:
            continue

        # 检测题型切换
        if "选择题" in line and ("一、" in line or "第一部分" in line):
            current_type = "选择"
            continue
        if "填空题" in line and ("二、" in line or "第二部分" in line):
            current_type = "填空"
            continue
        if "解答题" in line and ("三、" in line):
            current_type = "解答"
            continue
        # 有些卷子没有明确的"三、解答题"标记，通过题号判断
        if line.startswith("第二部分") and "非选择题" in line:
            continue

        # 匹配新题目
        m = q_pattern.match(line)
        if m:
            qid = int(m.group(1))
            qtext = m.group(2)

            # 自动判断题型
            if current_type is None:
                if qid <= 8:
                    current_type = "选择"
                elif qid <= 16:
                    current_type = "填空"
                else:
                    current_type = "解答"
            elif qid == 9:
                current_type = "填空"
            elif qid == 17:
                current_type = "解答"

            # 保存上一题
            if current_q:
                questions.append(current_q)

            current_q = {
                "id": qid,
                "type": current_type or "解答",
                "question": qtext,
                "answer": "",
                "analysis": "",
                "detail": "",
            }
            current_section = "question"
            continue

        if current_q is None:
            continue

        # 匹配答案
        m = answer_pattern.match(line)
        if m:
            current_q["answer"] = m.group(1).strip()
            current_section = "answer"
            continue

        # 匹配分析
        m = analysis_marker.match(line)
        if m:
            current_q["analysis"] = m.group(2).strip()
            current_section = "analysis"
            continue

        # 匹配详解
        m = detail_marker.match(line)
        if m:
            current_q["detail"] = m.group(1).strip()
            current_section = "detail"
            continue

        # 匹配小问详解
        m = subq_marker.match(line)
        if m:
            current_q["detail"] += "\n" + line
            current_section = "detail"
            continue

        # 点睛 — 属于分析
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

    # 保存最后一题
    if current_q:
        questions.append(current_q)

    return questions


def build_yaml_data(questions, year, district_cn, exam_type_cn):
    """将解析后的题目列表构建为 YAML 数据结构"""
    yaml_questions = []
    for q in questions:
        qid = q["id"]
        qtype = q["type"]
        difficulty = get_difficulty(qid, qtype)

        # 清理文本
        question_text = q["question"].strip()
        answer_text = q["answer"].strip()
        analysis_text = q["analysis"].strip()
        detail_text = q["detail"].strip()

        # 推断模块
        module = detect_module(analysis_text, question_text)

        # 提取知识点（从分析文本中提取关键词）
        kps = extract_knowledge_points(analysis_text, question_text)

        yaml_q = {
            "id": qid,
            "type": qtype,
            "score": get_score(qid, qtype),
            "question": question_text if len(question_text) > 5 else f"（第{qid}题，详见原卷）",
            "answer": answer_text,
            "solution": detail_text[:500] if detail_text else "",  # 限制长度
            "knowledge_points": kps,
            "module": module,
            "difficulty": difficulty,
            "recommended_for": get_recommended_for(difficulty),
        }
        yaml_questions.append(yaml_q)

    data = {
        "year": int(year),
        "district": f"{district_cn}区" if not district_cn.endswith("区") else district_cn,
        "exam_type": exam_type_cn,
        "subject": "数学",
        "full_score": 100,
        "duration_minutes": 120,
        "total_questions": len(yaml_questions),
        "structure": "8选择(16分) + 8填空(16分) + 12解答(68分)",
        "questions": yaml_questions,
    }
    return data


def extract_knowledge_points(analysis, question):
    """从分析文本中提取知识点关键词"""
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
        "扇形统计图", "条形统计图",
        "尺规作图",
    ]
    found = [kp for kp in kp_candidates if kp in combined]
    return found if found else ["综合"]


# ============================================================
# 文件发现与匹配
# ============================================================

def find_district_exams(src_dir):
    """扫描 src_dir 下所有目录，找到区级统考的解析版 docx"""
    results = []

    for batch_dir in sorted(os.listdir(src_dir)):
        batch_path = os.path.join(src_dir, batch_dir)
        if not os.path.isdir(batch_path) or batch_dir.startswith("."):
            continue

        # 解析年份和考试类型
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

        # 遍历该批次下的试卷目录
        for exam_dir in sorted(os.listdir(batch_path)):
            exam_path = os.path.join(batch_path, exam_dir)
            if not os.path.isdir(exam_path) or exam_dir.startswith("."):
                continue

            # 检测区名
            district_cn = None
            for d in DISTRICT_MAP:
                if d in exam_dir:
                    district_cn = d
                    break

            # 跳过校级考试（如果没匹配到区，说明是学校级别的）
            if not district_cn:
                # 检查是否是知名学校的考试（也值得收录）
                continue

            # 找解析版 docx
            for f in os.listdir(exam_path):
                if f.endswith(".docx") and "解析" in f:
                    results.append({
                        "year": year,
                        "district_cn": district_cn,
                        "district_en": DISTRICT_MAP[district_cn],
                        "exam_type_cn": exam_type_cn,
                        "exam_type_en": EXAM_TYPE_MAP[exam_type_cn],
                        "docx_path": os.path.join(exam_path, f),
                        "filename": f,
                    })
                    break  # 一个目录只取一个解析版

    return results


# ============================================================
# 主流程
# ============================================================

def main():
    # 优先级：四大区 > 其他区
    priority_districts = {"海淀", "西城", "东城", "朝阳"}

    print("=" * 60)
    print("扫描 knowledge-original 中的数学模拟卷...")
    print("=" * 60)

    all_exams = find_district_exams(SRC_DIR)

    # 按优先级排序：四大区在前，然后按年份倒序
    def sort_key(e):
        priority = 0 if e["district_cn"] in priority_districts else 1
        return (priority, -int(e["year"]), e["exam_type_en"], e["district_cn"])

    all_exams.sort(key=sort_key)

    print(f"\n找到 {len(all_exams)} 套区级统考卷：")
    for e in all_exams:
        print(f"  {e['year']} {e['district_cn']} {e['exam_type_cn']}")

    # 检查已存在的 YAML
    existing = set()
    if os.path.exists(DST_DIR):
        for f in os.listdir(DST_DIR):
            if f.endswith(".yaml"):
                existing.add(f)

    print(f"\n已存在 {len(existing)} 个 YAML 文件: {existing}")
    print()

    # 逐个转换
    success = 0
    failed = 0
    skipped = 0

    for exam in all_exams:
        yaml_filename = f"{exam['year']}-{exam['district_en']}-{exam['exam_type_en']}.yaml"
        yaml_path = os.path.join(DST_DIR, yaml_filename)

        if yaml_filename in existing:
            print(f"[跳过] {yaml_filename} 已存在")
            skipped += 1
            continue

        print(f"[转换] {exam['year']} {exam['district_cn']} {exam['exam_type_cn']} → {yaml_filename}")

        try:
            paragraphs = extract_paragraphs(exam["docx_path"])
            questions = parse_exam(paragraphs)

            if len(questions) < 10:
                print(f"  ⚠️ 只解析到 {len(questions)} 题，可能有问题，仍然保存")

            data = build_yaml_data(questions, exam["year"], exam["district_cn"], exam["exam_type_cn"])

            # 生成 YAML header
            header = f"""# ============================================================
# {exam['year']}年北京{exam['district_cn']}区中考数学{exam['exam_type_cn']}试卷 — 逐题分析
# ============================================================
# 数据来源：knowledge-original/{exam['filename']}
# 自动生成，部分数学公式可能显示不全（docx公式对象无法完整提取）
# 满分：100分  时长：120分钟

"""
            # 自定义 YAML 输出
            yaml_content = yaml.dump(data, allow_unicode=True, default_flow_style=False,
                                     width=200, sort_keys=False)

            os.makedirs(DST_DIR, exist_ok=True)
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(header + yaml_content)

            print(f"  ✅ 成功：{len(questions)} 题")
            success += 1

        except Exception as ex:
            print(f"  ❌ 失败：{ex}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"转换完成：成功 {success}，失败 {failed}，跳过 {skipped}")
    print(f"输出目录：{DST_DIR}")


if __name__ == "__main__":
    main()
