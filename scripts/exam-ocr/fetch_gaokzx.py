#!/usr/bin/env python3
"""从 gaokzx.com 批量抓取北京中考一模/二模试卷图片。

用法：
    # 1. 先解析汇总页（手工保存的 summary.html）→ 详情页索引
    python3 fetch_gaokzx.py parse-summary \
        --summary-html knowledge-original/beijing-mock-2026/yimo/_raw-fetch/summary.html \
        --output knowledge-original/beijing-mock-2026/yimo/_raw-fetch/entries.json

    # 2. 抓取详情页 + 下载图片
    python3 fetch_gaokzx.py fetch \
        --entries knowledge-original/beijing-mock-2026/yimo/_raw-fetch/entries.json \
        --out-root knowledge-original/beijing-mock-2026/yimo \
        --only-subjects 物理 数学 语文 英语 道法           # 可选过滤
        # --only-districts 朝阳 海淀                         # 可选过滤

    # 3. 生成 bulk_pipeline manifest
    python3 fetch_gaokzx.py manifest \
        --entries knowledge-original/beijing-mock-2026/yimo/_raw-fetch/entries.json \
        --out scripts/exam-ocr/manifest-2026-yimo.json

每步幂等：已存在的页面/图片不重抓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

SUBJ_EN = {
    "语文": "chinese", "数学": "math", "英语": "english",
    "物理": "physics", "道法": "politics", "化学": "chemistry", "历史": "history",
}
DISTRICT_EN = {
    "海淀": "haidian", "西城": "xicheng", "东城": "dongcheng", "朝阳": "chaoyang",
    "丰台": "fengtai", "石景山": "shijingshan", "顺义": "shunyi", "门头沟": "mentougou",
    "平谷": "pinggu", "怀柔": "huairou", "密云": "miyun", "延庆": "yanqing",
    "通州": "tongzhou", "大兴": "daxing", "房山": "fangshan", "昌平": "changping",
    "燕山": "yanshan",
    "北师大实验中学": "bsdsy", "二中": "erzhong", "四中": "sizhong",
    "人大附中": "rdfz", "汇文": "huiwen", "东直门": "dongzhimen",
    "三十五中": "sanshiwu", "陈经纶": "chenjinglun", "人朝分校": "rcfx",
    "北师大附中": "bsdfz",
}
EXAM_TYPE_EN = {"一模": "yi", "二模": "er", "三模": "san"}


def http_get(url: str, retries: int = 3, sleep: float = 1.5) -> bytes:
    """GET with UA + retry。自动 quote 路径里的空格等非法字符。"""
    # 修补未编码空格/中文（urllib 会拒绝带控制字符的 URL）
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "/" in rest:
            host, path = rest.split("/", 1)
            path = urllib.parse.quote(path, safe="/?&=%")
            url = f"{scheme}://{host}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            print(f"  ⚠️  retry {i+1}/{retries}: {e}", file=sys.stderr)
            time.sleep(sleep * (i + 1))
    raise RuntimeError(f"failed after {retries} tries: {url}: {last_err}")


# ====================== parse-summary ======================

def parse_summary(summary_html: Path, year: int = 2026, exam_type: str = "一模") -> list[dict]:
    """汇总页 HTML → 详情页 entries 列表。"""
    soup = BeautifulSoup(summary_html.read_text(encoding="utf-8"), "html.parser")
    rows = soup.find("table").find_all("tr")

    entries = []
    current_district = None
    for r in rows[1:]:
        cells = r.find_all("td")
        if len(cells) == 5:
            current_district = cells[0].get_text(strip=True)
            subj = cells[1].get_text(strip=True)
            link_cells = cells[2:5]
        elif len(cells) == 4:
            subj = cells[0].get_text(strip=True)
            link_cells = cells[1:4]
        else:
            continue
        for year_label, cell in zip(["2026", "2025", "2024"], link_cells):
            if int(year_label) != year:
                continue
            a = cell.find("a")
            if not a:
                continue
            href = a.get("href", "")
            m = re.search(r"/(\d+)\.html", href)
            if not m:
                continue
            entries.append({
                "year": year,
                "exam_type": exam_type,
                "district": current_district,
                "district_en": DISTRICT_EN.get(current_district, current_district),
                "subject": subj,
                "subject_en": SUBJ_EN.get(subj, subj),
                "detail_url": href,
                "detail_id": m.group(1),
                "exam_slug": f"{year}-{DISTRICT_EN.get(current_district, current_district)}-{EXAM_TYPE_EN[exam_type]}-{SUBJ_EN.get(subj, subj)}",
            })
    return entries


# ====================== fetch ======================

PAPER_IMG_RE = re.compile(
    # gaokzx 部分 URL 含未编码空格（如"数学   有答案"），所以允许 \t 但不允许换行/引号
    r'cdn\.gaokzx\.com/zixunzhan/[^"<>\n\\]+\.(?:png|jpg|jpeg)',
    re.IGNORECASE,
)


def extract_paper_image_urls(detail_html: str, year: int, exam_type: str) -> list[str]:
    """从详情页 HTML 抽试卷图片 URL。

    试卷图命名混乱（gaokzx 编辑随手起名）：
      - 规范型：`..._2026北京XX初三一模物理_<datetime>_<NN><ts>.png`
      - 缺字头：`..._026北京朝阳初三一模物理_..._<NN><ts>.png`
      - 通用型：`..._<ts1>_1_页面_<NN><ts2>.jpg`（无任何科目关键字）
      - 短编号：`..._<ts1>_<N><ts2>.jpg`（单位数页码，无关键字）

    策略：抽出所有形如 `_<ts1>_<...>_<NN><ts2>.<ext>` 的候选，按 ts1 分组，
    保留页数 ≥3 的最大组（一份试卷必然连续上传多页）。
    """
    candidates = set(PAPER_IMG_RE.findall(detail_html))

    # 匹配：开头 _<14-13位时间戳>_，结尾 _<1-2位页码><10+位时间戳>.<ext>
    # 容许中间任意内容
    # ts2 严格 13 位（gaokzx 毫秒戳）；这样 (\d{1,2}) 在 `_11778054791545.jpg` 等单位数页号会
    # 通过回溯正确取到 page=1 而不是 page=11。
    sig_re = re.compile(
        r"^cdn\.gaokzx\.com/zixunzhan/_?(\d{13})_.*?(?<![\d])(\d{1,2})(\d{13})\.(?:png|jpg|jpeg)$",
        re.IGNORECASE,
    )

    # 收集 (ts1, page_num, url)
    rows = []
    for u in candidates:
        decoded = urllib.parse.unquote(u)
        m = sig_re.match(decoded)
        if not m:
            continue
        ts1, page_num_str, _ts2 = m.groups()
        page = int(page_num_str)
        if not (1 <= page <= 30):  # 试卷一般 6-20 页，再宽点
            continue
        rows.append((ts1, page, u))

    if not rows:
        return []

    # 按 ts1 前 10 位（秒级，同一上传 batch）分组
    from collections import defaultdict
    groups = defaultdict(list)
    for ts1, page, u in rows:
        groups[ts1[:10]].append((page, u))

    # 合并所有"够大"的组（≥3 页），覆盖东城数学这种一卷分多次上传的场景。
    # 装饰图（单图组）天然被过滤。
    paper_groups = [g for g in groups.values() if len(g) >= 3]
    if not paper_groups:
        return []
    merged = []
    for g in paper_groups:
        merged.extend(g)
    merged.sort(key=lambda x: x[0])

    seen_pages = set()
    out = []
    for page, u in merged:
        if page in seen_pages:
            continue
        seen_pages.add(page)
        out.append("https://" + u)
    return out


def fetch_entry(entry: dict, out_root: Path, force: bool = False) -> dict:
    """抓一个 (区, 科) 的详情页 + 全部 page-*.png。"""
    district_en = entry["district_en"]
    subject_en = entry["subject_en"]
    dst_dir = out_root / district_en / subject_en
    images_dir = dst_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # 详情页 HTML
    html_path = dst_dir / "source.html"
    if force or not html_path.exists():
        print(f"  📥 fetch detail {entry['detail_url']}")
        html_path.write_bytes(http_get(entry["detail_url"]))
    detail_html = html_path.read_text(encoding="utf-8", errors="ignore")

    # 抽图片 URL
    img_urls = extract_paper_image_urls(detail_html, entry["year"], entry["exam_type"])
    if not img_urls:
        print(f"  ⚠️  {entry['district']}{entry['subject']}: 没找到试卷图")
        return {**entry, "page_count": 0, "images": []}

    (dst_dir / "urls.txt").write_text("\n".join(img_urls), encoding="utf-8")

    # 下载
    downloaded = []
    for i, url in enumerate(img_urls, 1):
        out = images_dir / f"page-{i:02d}.png"
        if not force and out.exists() and out.stat().st_size > 1024:
            downloaded.append(out.name)
            continue
        print(f"  📥 page {i:02d}: {urllib.parse.unquote(url)[-60:]}")
        out.write_bytes(http_get(url))
        downloaded.append(out.name)
        time.sleep(0.4)

    return {**entry, "page_count": len(downloaded), "images": downloaded}


# ====================== manifest ======================

def build_manifest(entries: list[dict], out_root: Path) -> list[dict]:
    """生成 bulk_pipeline.py 用的 manifest（只列已抓到图的）。"""
    jobs = []
    out_root_abs = out_root.resolve()
    for e in entries:
        images_dir = out_root_abs / e["district_en"] / e["subject_en"] / "images"
        final_json = out_root_abs / e["district_en"] / e["subject_en"] / "structured-cloud" / "final.json"
        pages = sorted(images_dir.glob("page-*.png"))
        if not pages:
            continue
        try:
            pd = str(images_dir.relative_to(ROOT))
            fj = str(final_json.relative_to(ROOT))
        except ValueError:
            pd, fj = str(images_dir), str(final_json)
        jobs.append({
            "exam_slug": e["exam_slug"],
            "subject": e["subject"],
            "subject_en": e["subject_en"],
            "exam_meta": {
                "city": "北京", "district": e["district"], "grade": "初三",
                "examType": e["exam_type"], "year": e["year"], "subject": e["subject"],
            },
            "paper_pages_dir": pd,
            "paper_final_json": fj,
        })
    return jobs


# ====================== CLI ======================

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("parse-summary")
    sp.add_argument("--summary-html", type=Path, required=True)
    sp.add_argument("--output", type=Path, required=True)
    sp.add_argument("--year", type=int, default=2026)
    sp.add_argument("--exam-type", default="一模")

    fp = sub.add_parser("fetch")
    fp.add_argument("--entries", type=Path, required=True)
    fp.add_argument("--out-root", type=Path, required=True)
    fp.add_argument("--only-subjects", nargs="*", default=None)
    fp.add_argument("--only-districts", nargs="*", default=None)
    fp.add_argument("--force", action="store_true")

    mp = sub.add_parser("manifest")
    mp.add_argument("--entries", type=Path, required=True)
    mp.add_argument("--out-root", type=Path, required=True)
    mp.add_argument("--out", type=Path, required=True)

    args = p.parse_args()

    if args.cmd == "parse-summary":
        entries = parse_summary(args.summary_html, args.year, args.exam_type)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        by_d = defaultdict(list)
        for e in entries:
            by_d[e["district"]].append(e["subject"])
        print(f"✅ {len(entries)} entries → {args.output}")
        for d, subs in by_d.items():
            print(f"  {d:>10s} ({len(subs)}科): {' '.join(subs)}")

    elif args.cmd == "fetch":
        entries = json.loads(args.entries.read_text(encoding="utf-8"))
        if args.only_subjects:
            entries = [e for e in entries if e["subject"] in args.only_subjects]
        if args.only_districts:
            entries = [e for e in entries if e["district"] in args.only_districts]
        print(f"📦 will fetch {len(entries)} entries")
        results = []
        for i, e in enumerate(entries, 1):
            print(f"\n[{i}/{len(entries)}] {e['district']}-{e['subject']} ({e['exam_slug']})")
            try:
                r = fetch_entry(e, args.out_root, force=args.force)
                results.append(r)
            except Exception as ex:
                print(f"  ❌ {ex}", file=sys.stderr)
                results.append({**e, "error": str(ex)})
        print(f"\n📊 done: {sum(1 for r in results if r.get('page_count'))} ok / {len(results)} total")

    elif args.cmd == "manifest":
        entries = json.loads(args.entries.read_text(encoding="utf-8"))
        jobs = build_manifest(entries, args.out_root)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ {len(jobs)} jobs → {args.out}")


if __name__ == "__main__":
    main()
