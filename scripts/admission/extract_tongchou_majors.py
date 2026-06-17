#!/usr/bin/env python3
"""
市级统筹招生计划（带专业代码）→ 抽取学校代码 / 专业代码 / 各区名额
================================================================
bjeea《市级优质高中教育资源统筹一/二招生计划》以整页表格 JPG 发布，
表头：学校代码 | 学校名称(地址电话) | 专业代码 | 专业名称 | 合计 | 东城01 西城02 朝阳05 …
关键结论（2025 实测）：
  - 统筹一 专业代码 全表统一 = 20（普通班）
  - 统筹二 专业代码 全表统一 = 30（普通班）
  - 网报 = 学校代码(6位) + 专业代码(2位)，如 五中统筹一 = 101002 + 20

用法（图片来自 bjeea 87197 统筹一 / 87196 统筹二，每页一张 JPG）：
  TENCENT_OCR_SECRET_ID=... TENCENT_OCR_SECRET_KEY=... \
  python3 extract_tongchou_majors.py \
     --yi 统筹一p1.jpg 统筹一p2.jpg --er 统筹二p1.jpg 统筹二p2.jpg \
     --out /tmp/tongchou_majors_2025.json

朝阳名额取「合计后的第 3 个招生地区列」（东城01 西城02 朝阳05）。
2026 计划 7 月初发布后专业码全部作废重编，须用新图重跑本脚本。
"""
import argparse, base64, json, os, re, sys, warnings
warnings.filterwarnings("ignore")
from tencentcloud.common import credential
from tencentcloud.ocr.v20181119 import ocr_client, models

# 招生地区列顺序（合计之后），朝阳是第 3 个
DISTRICT_ORDER = ["东城", "西城", "朝阳", "丰台", "石景山", "海淀", "门头沟", "房山",
                  "通州", "顺义", "昌平", "大兴", "怀柔", "平谷", "密云", "延庆", "经开"]


def ocr_rows(cli, path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    req = models.RecognizeTableAccurateOCRRequest()
    req.from_json_string(json.dumps({"ImageBase64": b64}))
    r = json.loads(cli.RecognizeTableAccurateOCR(req).to_json_string())
    by = {}
    for tb in r.get("TableDetections", []):
        for c in tb.get("Cells", []):
            by.setdefault(c.get("RowTl"), []).append((c.get("ColTl"), (c.get("Text") or "").strip()))
    out = []
    for rtl in sorted(by):
        out.append([t for _, t in sorted(by[rtl])])
    return out


def parse(rows, tier, major_code):
    res = []
    for row in rows:
        line = " | ".join(row)
        m = re.search(r"\b([12]\d{5})\b", line)
        if not m:
            continue
        code = m.group(1)
        # 名称 = 含代码的单元格里换行后的第一段中文
        name_cell = next((c for c in row if code in c), "")
        name = re.sub(r"^[12]\d{5}\s*", "", name_cell.split("\n")[0]).strip()
        # 数字序列：合计 + 各区。取“合计”之后第 3 个=朝阳
        nums = [c for c in row if re.fullmatch(r"\d+", c)]
        chaoyang = None
        if len(nums) >= 4:  # 合计,东城,西城,朝阳,...
            chaoyang = int(nums[3])
        res.append({"school_code": code, "name": name, "tier": tier,
                    "major_code": major_code, "major_name": "普通班",
                    "full": code + major_code, "chaoyang_raw_guess": chaoyang})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yi", nargs="+", required=True, help="统筹一 JPG（专业码 20）")
    ap.add_argument("--er", nargs="+", required=True, help="统筹二 JPG（专业码 30）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sid = os.environ.get("TENCENT_OCR_SECRET_ID")
    skey = os.environ.get("TENCENT_OCR_SECRET_KEY")
    if not (sid and skey):
        sys.exit("需 TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY 环境变量")
    cli = ocr_client.OcrClient(credential.Credential(sid, skey), "ap-beijing")
    out = []
    for fp in a.yi:
        out += parse(ocr_rows(cli, fp), "统筹一", "20")
    for fp in a.er:
        out += parse(ocr_rows(cli, fp), "统筹二", "30")
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=2)
    print(f"抽出 {len(out)} 行 → {a.out}")
    print("⚠️ chaoyang_raw_guess 为列位推断，须与官方图/名额表人工核对后再用。")


if __name__ == "__main__":
    main()
