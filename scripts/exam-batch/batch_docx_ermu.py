#!/usr/bin/env python3
"""5 学科二模 docx → final.json → enrich → mock yaml 批量 runner."""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path("/Users/jiakui/projects/zhongkao-agent")
SRC = ROOT / "knowledge-original/zxxk-downloads"
STAGING = ROOT / "knowledge-base/exams/_staging"
MOCK = ROOT / "knowledge-base/exams/mock"

DASHSCOPE_KEY = "sk-269db71be27b4dcfbedb0c21c382d288"
ENV = dict(os.environ)
ENV["DASHSCOPE_API_KEY"] = DASHSCOPE_KEY

# 已知 zip 内只含 PDF（非 docx 源）→ 跳过 docx 路线
PDF_ONLY_ZIPS = {
    ("physics", "xicheng"),
    ("politics", "fengtai"),
    ("politics", "yanshan"),
    ("politics", "shijingshan"),  # 也是 pdf only per first batch run
}

REGIONS = {
    "chinese":  ["changping","chaoyang","daxing","fangshan","fengtai","haidian","pinggu","shunyi","xicheng"],
    "english":  ["changping","chaoyang","daxing","fangshan","fengtai","mentougou","pinggu","shijingshan","shunyi","xicheng"],
    "math":     ["changping","chaoyang","daxing","fangshan","fengtai","haidian","mentougou","pinggu","shijingshan","shunyi","xicheng","yanshan"],
    "physics":  ["changping","chaoyang","daxing","fangshan","haidian","pinggu","shijingshan","shunyi","xicheng"],
    "politics": ["changping","chaoyang","daxing","fengtai","haidian","shijingshan","shunyi","xicheng","yanshan"],
}

def find_src(subject: str, region: str) -> Optional[Path]:
    for ext in ("zip", "docx"):
        c = SRC / f"2026-ermu-{subject}" / f"{region}_{subject}.{ext}"
        if c.exists():
            return c
    return None

def run_one(subject: str, region: str) -> Tuple[str, str, str]:
    slug = f"2026-{region}-er"
    if (subject, region) in PDF_ONLY_ZIPS:
        return (subject, region, "SKIP pdf-only zip")
    src = find_src(subject, region)
    if not src:
        return (subject, region, "SKIP no src")

    # Step 1: docx_paper → final.json (math 用 --out-dir，其余 --slug)
    if subject == "math":
        # math 现支持 zip 输入（自带 _pick_jiexi_docx + 双 docx merge），
        # 直接传 zip 触发 merge fix（chaoyang/pinggu Q17-28 sol 填）
        out_dir = STAGING / "math" / slug
        cmd1 = ["python3", str(ROOT / "scripts/exam-docx/math_docx_paper.py"),
                str(src), "--out-dir", str(out_dir)]
    else:
        cmd1 = ["python3", str(ROOT / f"scripts/exam-docx/{subject}_docx_paper.py"),
                str(src), "--slug", slug]
    p1 = subprocess.run(cmd1, capture_output=True, text=True, cwd=str(ROOT), env=ENV)
    if p1.returncode != 0:
        return (subject, region, f"FAIL docx_paper: {p1.stderr.strip()[-200:]}")

    # math 自己写 mock yaml，无需 enrich
    if subject == "math":
        return (subject, region, "OK math direct")

    # Step 2: enrich → mock yaml
    fj = STAGING / subject / slug / "structured-cloud" / "final.json"
    if not fj.exists():
        return (subject, region, f"FAIL no final.json @ {fj}")
    out = MOCK / subject / "beijing" / f"{slug}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd2 = ["python3", str(ROOT / "scripts/knowledge-base/enrich_to_mock_exam.py"),
            "-i", str(fj), "-s", subject, "-o", str(out)]
    p2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=str(ROOT), env=ENV)
    if p2.returncode != 0:
        return (subject, region, f"FAIL enrich: {p2.stderr.strip()[-200:]}")

    score_line = next((ln for ln in p2.stdout.splitlines() if "题" in ln and "分" in ln), "")
    return (subject, region, f"OK {score_line.strip()}")

def main():
    import sys as _sys
    only = _sys.argv[1] if len(_sys.argv) > 1 else None
    jobs = [(s, r) for s, rs in REGIONS.items() for r in rs if (only is None or s == only)]
    print(f"# {len(jobs)} 卷批跑（并发 6）", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(run_one, s, r): (s, r) for s, r in jobs}
        for fut in as_completed(futs):
            s, r = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = (s, r, f"EXC {e}")
            results.append(res)
            tag = f"{res[0]}/{res[1]}"
            print(f"  [{tag:30s}] {res[2]}", flush=True)

    print("\n=== SUMMARY ===")
    ok = sum(1 for _, _, st in results if st.startswith("OK"))
    fail = sum(1 for _, _, st in results if st.startswith("FAIL"))
    skip = sum(1 for _, _, st in results if st.startswith("SKIP"))
    print(f"OK={ok}  FAIL={fail}  SKIP={skip}  TOTAL={len(results)}")
    if fail:
        print("\nFAILURES:")
        for s, r, st in results:
            if st.startswith("FAIL"):
                print(f"  {s}/{r}: {st}")

if __name__ == "__main__":
    main()
