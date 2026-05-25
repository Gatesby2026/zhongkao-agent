"""班小二「学生成绩单」xlsx → scores.json（build_report 用）。

样本结构（sheet 名「学生成绩单」）：
  r1: "贾小淇"的考试成绩单            ← 学生名（弯引号包裹）
  r2: 学科 | 成绩                      ← 表头
  r3: 总分(70_0) | 60                  ← 总分；(70_0)=满分 70.0
  r4: 1(2_0) | 2                       ← 第1题；(2_0)=满分 2.0，得分 2
  ...                                  ← n(full_dec) | scored

输出 scores.json：
  {"examTotal":{"scored","fullScore"},
   "questions":[{"qId":"Q1","scored","fullScore"}...],
   "sections":[]}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl

# 学科列样式：  总分(70_0)  /  12(2_0)  /  20(4_0)；
# 班小二附加情况：
#   - 括号后追加知识点描述："2(2_0)能理解并合理使用成语"
#   - 主观题拆子小问："20_1(3_0)"、"23_1_1(2_0)"、作文"27_1(40_0)"
# 第 1 组只捕"主题号"，子号(_\d+)* 吞掉；末尾允许描述（去 $）
_PAREN = re.compile(r"^\s*(总分|\d+)(?:_\d+)*\s*[\(（]\s*(\d+)_(\d+)\s*[\)）]")


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).strip())
    except ValueError:
        return 0.0


def _full(intpart: str, dec: str) -> float:
    """(70_0)→70.0  (2_5)→2.5"""
    return float(f"{intpart}.{dec}")


def parse_scores_xlsx(xlsx_path: Path) -> dict:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    # 取第一个含「成绩单」的 sheet，否则首个
    sn = next((s for s in wb.sheetnames if "成绩" in s), wb.sheetnames[0])
    ws = wb[sn]

    rows = [[("" if c is None else c) for c in r]
            for r in ws.iter_rows(values_only=True)]
    if not rows:
        raise ValueError("空表")

    # 学生名：r1 形如 “贾小淇”的考试成绩单
    name = ""
    m = re.search(r"[“\"']?\s*([一-龥·]{2,6})\s*[”\"']?\s*的.*成绩单",
                  str(rows[0][0]))
    if m:
        name = m.group(1)

    exam_total = {"scored": 0.0, "fullScore": 0.0}
    # 主题号 → 累加 scored/fullScore；用 dict 合并子小问（20_1/20_2 → Q20）
    agg: dict[int, dict] = {}
    for r in rows:
        label = str(r[0]).strip()
        scored = _num(r[1]) if len(r) > 1 else 0.0
        pm = _PAREN.match(label)
        if not pm:
            continue
        key, ip, dp = pm.group(1), pm.group(2), pm.group(3)
        full = _full(ip, dp)
        if key == "总分":
            exam_total = {"scored": _i(scored), "fullScore": _i(full)}
            continue
        qid = int(key)
        cur = agg.setdefault(qid, {"scored": 0.0, "fullScore": 0.0})
        cur["scored"] += scored
        cur["fullScore"] += full
    questions = [
        {"qId": f"Q{n}",
         "scored": _i(agg[n]["scored"]),
         "fullScore": _i(agg[n]["fullScore"])}
        for n in sorted(agg)
    ]

    if not questions:
        raise ValueError("未解析到任何小题分（格式不符？）")

    # examTotal 兜底：缺总分则按小题求和
    if exam_total["fullScore"] == 0:
        exam_total = {
            "scored": _i(sum(q["scored"] for q in questions)),
            "fullScore": _i(sum(q["fullScore"] for q in questions)),
        }

    return {
        "examTotal": exam_total,
        "questions": questions,
        "sections": [],          # 班小二无分段信息；build_report 容忍空
        "_student_name": name,   # 供调用方校验/回填（非 build_report 字段）
    }


def _i(x: float):
    """整数则去 .0"""
    return int(x) if float(x).is_integer() else round(float(x), 2)


def write_scores_json(xlsx_path: Path, out_path: Path) -> dict:
    data = parse_scores_xlsx(xlsx_path)
    out = {k: v for k, v in data.items() if not k.startswith("_")}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return data


if __name__ == "__main__":
    import sys
    d = parse_scores_xlsx(Path(sys.argv[1]))
    print(json.dumps(d, ensure_ascii=False, indent=2))
