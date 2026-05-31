#!/usr/bin/env python3
"""比较 B (qwen-vl-max) 与 C (Tencent OCR + 缺字母法) 在 cropped 涂卡区上的命中率。

流程：
  1. choice_region_locate 找出涂卡区 + 旋正 + 裁切
  2. cropped 图分别送给 vl-max 和 Tencent OCR 提取作答
  3. 跟 ground-truth 比对，出命中率表

用法：
  TENCENT_OCR_SECRET_ID=... TENCENT_OCR_SECRET_KEY=... \\
  DASHSCOPE_API_KEY=... \\
  python3 test-data/_choice-bench/bench_methods.py [--method B|C|all]
"""
import argparse
import base64
import io
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "answer-card-ocr"))
from choice_region_locate import crop_choice_region

CASES_ROOT = Path(__file__).resolve().parent / "cases"


# ============== Method B: qwen-vl-max 看 cropped 图 ==============

_VLM_PROMPT = """这是一张答题卡的选择题填涂区裁切图，共 {n_q} 道题。

任务：逐题看学生用黑色涂了哪个字母（A/B/C/D）。
- 涂黑/涂满的方框就是学生作答
- 多选题可能涂多个字母（例如 BD / ACD）
- 没有涂的题用空字符串

严格输出 JSON（不要 markdown 围栏，不要解释）：
{{"answers": {{"Q1": "B", "Q2": "AD", ...}}}}"""


def detect_vlmax(cropped_image, n_questions: int) -> dict[int, str]:
    import openai
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺 DASHSCOPE_API_KEY")
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    buf = io.BytesIO()
    cropped_image.save(buf, "JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()

    resp = client.chat.completions.create(
        model="qwen-vl-max",
        messages=[{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text",
             "text": _VLM_PROMPT.format(n_q=n_questions)},
        ]}],
        temperature=0.0, max_tokens=1024,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    data = json.loads(raw)
    ans = data.get("answers") or {}
    out: dict[int, str] = {}
    for k, v in ans.items():
        qid = int(str(k).strip().upper().lstrip("Q"))
        out[qid] = str(v).strip().upper()
    return out


# ============== Method C: Tencent OCR 缺字母法 on cropped ==============

def detect_tencent_on_crop(cropped_image, n_questions: int,
                            original_path: Path = None) -> dict[int, str]:
    """C method: 腾讯 OCR + 缺字母法。

    实测 cropped 图 OCR 信号反而变差（图变小，对比度变化）→ 直接在
    原图上跑 Tencent OCR，cropped 只用作可视化验证。
    """
    sys.path.insert(0, str(ROOT / "scripts" / "answer-card-ocr"))
    from tencent_choice_grid import locate_choice_grid

    if original_path is None:
        # fallback: 把 cropped 存临时文件
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        cropped_image.save(tmp, "JPEG", quality=90)
        original_path = Path(tmp)

    info = locate_choice_grid(original_path)
    filled = info.get("filled") or {}
    return {qid: f for qid, f in filled.items() if qid <= n_questions}


# ============== Method A: Path B 像素扫（原图） ==============

def detect_pixel_blob(original_path: Path, n_questions: int) -> dict[int, str]:
    """A method: 原图 Path B 像素 blob 扫描。物理 5x3 layout 强。"""
    from detect import detect_choices_by_blob
    r = detect_choices_by_blob([original_path])
    out = {}
    for q, v in r.items():
        if q > n_questions: continue
        f = v.get("filled") or ""
        if isinstance(f, list):
            f = "".join(f)
        out[q] = str(f).strip().upper()
    return out


# ============== Bench 主流程 ==============

def _qid_int(q):
    s = str(q).strip().upper().lstrip("Q")
    return int(s) if s.isdigit() else 0


def bench_case(case_dir: Path, methods: list[str]) -> dict:
    """跑单 case 所有 methods，返回 {method: (hits, total, misses)}。"""
    gt_path = case_dir / "ground-truth.yaml"
    if not gt_path.exists():
        return {"error": "no ground-truth.yaml"}
    gt = yaml.safe_load(gt_path.read_text(encoding="utf-8")) or {}
    truth = {_qid_int(q): str(v).strip().upper()
             for q, v in (gt.get("answers") or {}).items()}
    if not truth:
        return {"error": "empty answers"}

    photos = sorted(p for p in case_dir.iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png")
                    and p.name.startswith("page-"))
    if not photos:
        return {"error": "no photos"}

    # Step 1: 裁切
    try:
        cropped, info = crop_choice_region(photos[0])
        if not info.get("found"):
            return {"error": f"crop failed: {info.get('reason')}"}
    except Exception as e:
        return {"error": f"crop exception: {e}"}

    results = {"cropped": cropped, "info": info, "truth": truth, "methods": {}}
    n_q = gt.get("n_questions", len(truth))

    for m in methods:
        try:
            if m == "A":
                pred = detect_pixel_blob(photos[0], n_q)
            elif m == "B":
                pred = detect_vlmax(cropped, n_q)
            elif m == "C":
                pred = detect_tencent_on_crop(cropped, n_q, original_path=photos[0])
            else:
                continue
            hits = 0
            misses = []
            for qid, t in sorted(truth.items()):
                p = pred.get(qid, "")
                if p == t:
                    hits += 1
                else:
                    misses.append((qid, t, p))
            results["methods"][m] = (hits, len(truth), misses)
        except Exception as e:
            results["methods"][m] = (0, len(truth), [("err", str(e)[:80], "")])
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["A", "B", "C", "all"], default="all")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--case", help="只跑指定 case")
    args = ap.parse_args()

    methods = ["A", "B", "C"] if args.method == "all" else [args.method]

    targets = sorted(d for d in CASES_ROOT.iterdir() if d.is_dir())
    if args.case:
        targets = [d for d in targets if d.name == args.case]

    print(f"{'case':<40s}  {'A(像素)':>11s}  {'B(vlmax)':>11s}  {'C(tencent)':>11s}")
    print("-" * 80)
    tot_a = tot_b = tot_c = tot_n = 0
    misses = {"A": {}, "B": {}, "C": {}}
    for d in targets:
        r = bench_case(d, methods)
        if "error" in r:
            print(f"{d.name:<40s}  ERROR: {r['error']}")
            continue
        n = len(r["truth"])
        tot_n += n
        results_str = []
        for m, tot_var in [("A", "a"), ("B", "b"), ("C", "c")]:
            res = r["methods"].get(m)
            if res:
                s = f"{res[0]}/{res[1]} ({100*res[0]/res[1]:.0f}%)"
                results_str.append(s)
                misses[m][d.name] = res[2]
                if m == "A": tot_a += res[0]
                elif m == "B": tot_b += res[0]
                else: tot_c += res[0]
            else:
                results_str.append("-")
        print(f"{d.name:<40s}  {results_str[0]:>11s}  {results_str[1]:>11s}  {results_str[2]:>11s}")

    print("-" * 80)
    rates = [f"{t}/{tot_n} ({100*t/tot_n:.1f}%)" if tot_n else "-"
             for t in (tot_a, tot_b, tot_c)]
    print(f"{'合计':<40s}  {rates[0]:>11s}  {rates[1]:>11s}  {rates[2]:>11s}")

    if args.verbose:
        for m_label, m_data in [("A (像素 blob)", misses["A"]),
                                  ("B (vl-max)", misses["B"]),
                                  ("C (tencent 缺字母)", misses["C"])]:
            print(f"\n=== {m_label} 失误详情 ===")
            for case, ms in m_data.items():
                if ms:
                    print(f"\n[{case}]")
                    for qid, t, p in ms:
                        print(f"  Q{qid}: 真={t!r}  识={p!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
