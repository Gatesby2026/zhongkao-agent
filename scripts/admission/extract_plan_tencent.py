#!/usr/bin/env python3
"""
招生计划册（bjeea 图片版）→ 结构化 JSON  ·  腾讯云表格 OCR 路线
==============================================================
bjeea《普通高中学校统一招生计划》等以**整页表格 JPG** 发布（文本不可直接抽取）。
腾讯云 RecognizeTableAccurateOCR 把每页还原成带 行/列 索引的单元格，
据此重建每个「学校×专业」行：学校代码 / 校名 / 专业代码 / 专业名称 / 学制 / 加试
/ 计划合计 / 分区招生人数 / 特殊学生 / 特殊说明。

**列定位用「表头位置」而非 OCR 出的区代码数字**——实测腾讯把"朝阳03"误读成"朝阳05"，
但列的物理位置是稳定的；脚本扫表头行，按区名文字把每一列映射到字段，自动适配错位/多列。

**铁律（涉及孩子升学）**：代码/人数只能来自官方计划册，OCR 结果须人工核对方可进系统。
本脚本只把图片转成可核对的结构化文本，并对「学校代码缺失/列对不齐」打 flag。

用法：
  TENCENT_OCR_SECRET_ID=.. TENCENT_OCR_SECRET_KEY=.. \
  python scripts/admission/extract_plan_tencent.py \
      --images /tmp/bjeea_2025_tongzhao/p*.jpg \
      --out knowledge-base/admission/beijing/2025_tongzhao_plan.json \
      --year 2025 --plan tongzhao
每页原始单元格落 .cache/plan_tencent_cache.json，可断点续跑。
"""
import argparse
import base64
import io
import json
import os
import re
import sys
from pathlib import Path

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import ocr_client, models
from PIL import Image

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE = CACHE_DIR / "plan_tencent_cache.json"

# 表头位置 → 字段。区名用于在表头行里定位列；顺序仅作 fallback。
# 北京统招计划分区列（2025 实测含「燕山」单列）：
DISTRICT_COLS = ["东城", "西城", "朝阳", "丰台", "石景山", "海淀", "门头沟",
                 "燕山", "房山", "通州", "顺义", "昌平", "大兴", "怀柔",
                 "平谷", "密云", "延庆", "经开"]
HEADER_KEYS = {  # 表头关键字 → 内部字段名
    "学校代码": "school_code", "学校名称": "school_name",
    "专业代码": "major_code", "专业名称": "major_name",
    "学制": "xuezhi", "是否加试": "jiashi", "加试": "jiashi",
    "合计": "total", "特殊学生": "special_student", "特殊说明": "special_note",
}
SCHOOL_CODE_RE = re.compile(r"^\d{6}$")
MAJOR_CODE_RE = re.compile(r"^0?\d{1,2}$")


_DIST_TOKEN = re.compile(
    r"(东城区|西城区|朝阳区|丰台区|石景山区|海淀区|门头沟区|房山区|通州区|顺义区|"
    r"昌平区|大兴区|怀柔区|平谷区|密云区|延庆区|燕山地区|燕山|北京经济技术开发区)")
# 校名结尾的「校型后缀」——地址段紧跟在这些后缀之后出现
_NAME_SUFFIX = ("实验学校", "外国语学校", "国际学校", "职业学校", "职业高中", "高级中学",
                "附属中学", "实验中学", "学校", "中学", "学院", "附中", "分校", "校区",
                "中心", "高中", "职高", "一中", "二中", "三中", "四中", "五中", "六中",
                "七中", "八中", "九中", "十中", "中")


def clean_school_name(raw: str) -> str:
    """校名单元格常把「校名+地址电话」合并。策略：
    1) 去 OCR 内部空格；先用 电话/邮编/url/括号 做粗截。
    2) 地址段总是紧跟在「完整校名（以校型后缀结尾）」之后，且以「<区>区」开头；
       而校名内嵌的区名（如 北京市*朝阳区*人朝分实验学校）前面不是校型后缀。
       → 找第一个「前文以校型后缀结尾」的 <区>区 token，从那里截断。
    这样 和平街第一中学 / 睿德分校 / 大兴区第一中学 等都完整保留，只去掉真正的地址。"""
    if not raw:
        return raw
    s = re.sub(r"\s+", "", raw.strip())
    m = re.search(r"电话|邮编|https?|www\.|[（(]|\d", s)
    if m:
        s = s[:m.start()]
    for mm in _DIST_TOKEN.finditer(s):
        head = s[:mm.start()]
        if head and any(head.endswith(suf) for suf in _NAME_SUFFIX):
            s = head
            break
    return s.strip("，,、 ")


def _client():
    sid = os.environ.get("TENCENT_OCR_SECRET_ID")
    skey = os.environ.get("TENCENT_OCR_SECRET_KEY")
    if not sid or not skey:
        sys.exit("缺 TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY")
    cred = credential.Credential(sid, skey)
    hp = HttpProfile(); hp.endpoint = "ocr.tencentcloudapi.com"
    return ocr_client.OcrClient(cred, "ap-guangzhou", ClientProfile(httpProfile=hp))


def _b64(path: Path) -> str:
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def ocr_cells(cli, path: Path):
    """返回最大表的 cells: [{RowTl,RowBr,ColTl,ColBr,Text}]。"""
    req = models.RecognizeTableAccurateOCRRequest()
    req.ImageBase64 = _b64(path)
    resp = cli.RecognizeTableAccurateOCR(req)
    d = json.loads(resp.to_json_string())
    tabs = d.get("TableDetections", [])
    if not tabs:
        return []
    big = max(tabs, key=lambda t: len(t.get("Cells", [])))
    return [{"r": c.get("RowTl"), "c": c.get("ColTl"),
             "rb": c.get("RowBr"), "cb": c.get("ColBr"),
             "t": (c.get("Text") or "").strip()} for c in big.get("Cells", [])]


def build_grid(cells):
    grid = {}
    for c in cells:
        if c["r"] is None or c["c"] is None or c["r"] < 0:
            continue
        grid[(c["r"], c["c"])] = c["t"].replace("\n", " ").strip()
    return grid


def map_columns(grid):
    """扫前 3 行表头，把列号映射到字段名。返回 {字段: 列号} + {列号: 区名}。"""
    maxr = max((r for r, _ in grid), default=0)
    maxc = max((c for _, c in grid), default=0)
    header_text = {}  # col -> 合并的表头文字
    for r in range(min(3, maxr + 1)):
        for cc in range(maxc + 1):
            t = grid.get((r, cc), "")
            if t:
                header_text[cc] = (header_text.get(cc, "") + t)
    field_col, dist_col = {}, {}
    for cc, txt in header_text.items():
        t = re.sub(r"\s|\(.*?\)|（.*?）|\d", "", txt)
        for d in DISTRICT_COLS:
            if d in t:
                dist_col[cc] = d
        for k, f in HEADER_KEYS.items():
            if k in txt and f not in field_col:
                field_col[f] = cc
    return field_col, dist_col, maxr, maxc


def data_start_row(grid, maxr):
    """第一行出现 6 位学校代码的行号。"""
    for r in range(maxr + 1):
        for cc in range(3):
            if SCHOOL_CODE_RE.match(grid.get((r, cc), "")):
                return r
    return 2


def parse_page(grid, fill):
    field_col, dist_col, maxr, maxc = map_columns(grid)
    sc_col = field_col.get("school_code", 0)
    name_col = field_col.get("school_name", 1)
    mc_col = field_col.get("major_code", 2)
    mn_col = field_col.get("major_name", 3)
    xz_col = field_col.get("xuezhi")
    js_col = field_col.get("jiashi")
    total_col = field_col.get("total")
    note_col = field_col.get("special_note", maxc)
    spec_col = field_col.get("special_student")
    start = data_start_row(grid, maxr)

    rows = []
    for r in range(start, maxr + 1):
        sc = grid.get((r, sc_col), "")
        nm = grid.get((r, name_col), "")
        mc = grid.get((r, mc_col), "")
        mn = grid.get((r, mn_col), "")
        # 区级标题行（如"东城区"独占一行）跳过
        rowtext = "".join(grid.get((r, cc), "") for cc in range(maxc + 1))
        if not rowtext.strip():
            continue
        if SCHOOL_CODE_RE.match(sc):
            fill["code"] = sc
            fill["name"] = clean_school_name(nm) or fill.get("name")
            fill["name_raw"] = re.sub(r"\s+", " ", nm).strip() or fill.get("name_raw")
        elif re.match(r"^.{0,4}区$", rowtext.strip()):
            continue  # 区标题行
        # 没有专业代码也没有代码/校名的行：可能是上一专业的续行，跳过
        if not (MAJOR_CODE_RE.match(mc) or sc or mn):
            continue
        dist = {}
        for cc, dname in dist_col.items():
            v = grid.get((r, cc), "")
            if v:
                dist[dname] = v
        rec = {
            "school_code": fill.get("code"),
            "school_name": (clean_school_name(nm) if SCHOOL_CODE_RE.match(sc) else None) or fill.get("name"),
            "name_raw": (re.sub(r"\s+", " ", nm).strip() if SCHOOL_CODE_RE.match(sc) else None) or fill.get("name_raw"),
            "major_code": mc if MAJOR_CODE_RE.match(mc) else None,
            "major_name": mn or None,
            "xuezhi": grid.get((r, xz_col), "") if xz_col else "",
            "jiashi": grid.get((r, js_col), "") if js_col else "",
            "total": grid.get((r, total_col), "") if total_col else "",
            "districts": dist,
            "special_student": grid.get((r, spec_col), "") if spec_col else "",
            "special_note": grid.get((r, note_col), "") if note_col else "",
            "flags": [],
        }
        if not rec["school_code"]:
            rec["flags"].append("no_school_code")
        if rec["major_code"] is None and rec["major_name"] is None and not dist:
            continue  # 纯噪声行
        rows.append(rec)
    return rows


def load_cache():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def save_cache(c):
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--year", default="2025")
    ap.add_argument("--plan", default="tongzhao")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cli = _client()
    cache = load_cache()
    imgs = sorted(Path(p) for p in args.images)
    all_rows = []
    fill = {}
    for i, p in enumerate(imgs, 1):
        key = f"{args.plan}|{p.name}|{int(p.stat().st_mtime)}"
        if args.force or key not in cache:
            print(f"[{i}/{len(imgs)}] OCR {p.name} ...", flush=True)
            cache[key] = ocr_cells(cli, p)
            save_cache(cache)
        else:
            print(f"[{i}/{len(imgs)}] cached {p.name}", flush=True)
        grid = build_grid(cache[key])
        rows = parse_page(grid, fill)
        for r in rows:
            r["_page"] = p.name
        all_rows.extend(rows)

    out = {
        "year": args.year, "plan": args.plan,
        "source": "bjeea.cn 招生计划册 图片版 → 腾讯云 RecognizeTableAccurateOCR",
        "warning": "OCR 自动抽取，未逐行人工核对；代码/人数以官方计划册为准。"
                   f"{args.year} 数据，2026 计划发布后须刷新。",
        "district_cols": DISTRICT_COLS,
        "n_rows": len(all_rows),
        "rows": all_rows,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    nschool = len({r["school_code"] for r in all_rows if r["school_code"]})
    print(f"\n写入 {args.out}：{len(all_rows)} 专业行 / {nschool} 校 / {len(imgs)} 页")


if __name__ == "__main__":
    main()
