#!/usr/bin/env python3
"""下载 gaokzx.com 二模 PDF（有答案版本）。
用法：python3 scripts/download_ermu_pdfs.py
"""
import json, re, subprocess, sys, time, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_BASE = ROOT / "knowledge-original/gaokzx-downloads"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

# 待下载：(district_en, subject_en, subject_cn, page_id)
ENTRIES = [
    # 海淀
    ("haidian",    "politics", "道法",  "155730"),
    # 丰台
    ("fengtai",    "chinese",  "语文",  "155740"),
    ("fengtai",    "math",     "数学",  "155741"),
    ("fengtai",    "english",  "英语",  "155837"),
    ("fengtai",    "physics",  "物理",  "155836"),
    # 昌平
    ("changping",  "chinese",  "语文",  "155682"),
    ("changping",  "politics", "道法",  "155830"),
    ("changping",  "physics",  "物理",  "155706"),
    # 门头沟
    ("mentougou",  "math",     "数学",  "155838"),
    # 房山
    ("fangshan",   "math",     "数学",  "155707"),
    ("fangshan",   "english",  "英语",  "155737"),
    ("fangshan",   "physics",  "物理",  "155736"),
    # 大兴
    ("daxing",     "chinese",  "语文",  "155739"),
    ("daxing",     "english",  "英语",  "155834"),
    ("daxing",     "physics",  "物理",  "155833"),
    ("daxing",     "politics", "道法",  "155832"),
    # 石景山
    ("shijingshan","physics",  "物理",  "155840"),
    # 平谷
    ("pinggu",     "math",     "数学",  "155760"),
    ("pinggu",     "physics",  "物理",  "155759"),
]


def fetch_html(url: str) -> str:
    result = subprocess.run(
        ["curl", "-s", "-A", UA, url],
        capture_output=True, text=True
    )
    return result.stdout


def extract_pdfs(html: str) -> list[str]:
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    pdfs = []
    for s in scripts:
        if 'zixunzhan' not in s:
            continue
        try:
            data = json.loads(s)
        except Exception:
            continue
        def walk(obj, depth=0):
            if depth > 15:
                return
            if isinstance(obj, str) and '.pdf' in obj.lower() and 'cdn.gaokzx.com' in obj:
                pdfs.append(obj)
            elif isinstance(obj, list):
                [walk(x, depth + 1) for x in obj]
            elif isinstance(obj, dict):
                [walk(v, depth + 1) for v in obj.values()]
        walk(data)
    return list(dict.fromkeys(pdfs))


def pick_with_answer(pdfs):  # type: (list) -> str or None
    """优先选含"有答案"的 PDF；若无则选含"答案"的；若还无则返回 None。"""
    for p in pdfs:
        decoded = urllib.parse.unquote(p)
        if "有答案" in decoded:
            return p
    for p in pdfs:
        decoded = urllib.parse.unquote(p)
        if "答案" in decoded:
            return p
    return None


def download_pdf(url: str, out_path: Path) -> bool:
    encoded = urllib.parse.quote(url, safe=':/?=&#%')
    result = subprocess.run(
        ["curl", "-s", "-L", "--output", str(out_path), encoded],
        capture_output=True
    )
    if result.returncode != 0:
        return False
    size = out_path.stat().st_size if out_path.exists() else 0
    return size > 10_000  # at least 10KB


def main():
    ok = 0
    skip = 0
    fail = 0

    for district_en, subject_en, subject_cn, page_id in ENTRIES:
        out_dir = OUT_BASE / f"2026-ermu-{subject_en}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{district_en}_{subject_en}.pdf"

        if out_path.exists() and out_path.stat().st_size > 10_000:
            print(f"  ✅ skip  {district_en}_{subject_en} (already {out_path.stat().st_size//1024}KB)")
            skip += 1
            continue

        url = f"https://www.gaokzx.com/gk/zhongkao/{page_id}.html"
        print(f"  📥 {district_en} {subject_cn} (id={page_id}) ...")
        html = fetch_html(url)

        if len(html) < 500:
            print(f"     ❌ HTML too short ({len(html)} bytes) — bot block?")
            fail += 1
            continue

        pdfs = extract_pdfs(html)
        if not pdfs:
            print(f"     ❌ no PDFs found in page")
            fail += 1
            continue

        chosen = pick_with_answer(pdfs)
        if not chosen:
            print(f"     ⚠️  PDFs found but none with 答案: {[urllib.parse.unquote(p)[-40:] for p in pdfs]}")
            fail += 1
            continue

        decoded_name = urllib.parse.unquote(chosen)[-60:]
        print(f"     🔗 {decoded_name}")

        success = download_pdf(chosen, out_path)
        if success:
            size_kb = out_path.stat().st_size // 1024
            print(f"     ✅ saved {out_path.name} ({size_kb}KB)")
            ok += 1
        else:
            print(f"     ❌ download failed or file too small")
            fail += 1

        time.sleep(0.8)

    print(f"\n📊 done: {ok} downloaded, {skip} skipped, {fail} failed")


if __name__ == "__main__":
    main()
