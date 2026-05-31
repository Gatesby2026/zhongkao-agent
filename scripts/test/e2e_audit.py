#!/usr/bin/env python3
"""端到端自动化测试 + LLM 报告质量审核。

对 test-data/<case>/ 每份测试数据:
  1. 上传照片到生产 API (https://zhongkao.gatesby.xyz)
  2. 轮询 detect → 上传小分 xlsx → /start → 轮询完成
  3. 拉报告 JSON + PDF
  4. 调 qwen-max-latest 审核报告，按 P0/P1/P2 输出问题清单
  5. 汇总打印 + 写 _runs/<ts>/_summary.json

用法:
  DASHSCOPE_API_KEY=sk-... python3 scripts/test/e2e_audit.py
  # 可选：API_BASE=http://localhost:8200 跑本地后端
  # 可选：CASES=jiaxiaoqi-physics,jiaxiaoqi-math 只跑指定 case
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from requests.exceptions import RequestException


def _req(method: str, url: str, *, expect_json: bool = False, **kw):
    """HTTP 调用 + 简单重试。

    expect_json=True：同步检查响应能 json.loads；失败也算瞬时错走重试
                     （Aliyun nginx 偶发 502/空 body，json() 否则会炸）。
    """
    last = None
    for i in range(5):
        try:
            r = requests.request(method, url, **kw)
            if expect_json:
                _ = r.json()                 # 触发 JSONDecodeError 入重试
            return r
        except (RequestException, json.JSONDecodeError) as e:
            last = e
            time.sleep(1 + i * 2)
    raise last


def _get(url, **kw): return _req("GET", url, **kw)
def _post(url, **kw): return _req("POST", url, **kw)

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "test-data"
RUN_ROOT = TEST_ROOT / "_runs"
API = os.environ.get("API_BASE", "https://zhongkao.gatesby.xyz").rstrip("/")
# 每 case 真实学生名（用于 e2e 测试覆盖），缺省=不覆盖，让 card_meta OCR
# 结果保留。早期默认 "贾小淇" 把所有 case 都强改成贾小淇名，污染报告抬头。
PER_CASE_NAME = {
    # 命名规范：<pinyin>-<district>-<examtype>-<subject>
    #   district = haidian / chaoyang / xicheng / shijingshan / ...
    #   examtype = yi（一模） / er（二模） / zhenti（中考真题）
    #   subject  = math / physics / chinese / english / politics / chemistry / history
    # 开发基线（贾小淇 朝阳一模/二模 全 5 科）
    "jiaxiaoqi-chaoyang-yi-physics": "贾小淇",
    "jiaxiaoqi-chaoyang-yi-math": "贾小淇",
    "jiaxiaoqi-chaoyang-yi-chinese": "贾小淇",
    "jiaxiaoqi-chaoyang-er-physics": "贾小淇",
    "jiaxiaoqi-chaoyang-er-math": "贾小淇",
    "jiaxiaoqi-chaoyang-er-chinese": "贾小淇",
    "jiaxiaoqi-chaoyang-er-english": "贾小淇",
    "jiaxiaoqi-chaoyang-er-politics": "贾小淇",
    # 生产真实 case
    "guanlihan-haidian-er-physics": "关丽涵",
    "zhangjingqi-haidian-er-physics": "张靖奇",
    "zhangyiran-shijingshan-yi-chinese": "张伊冉",
    "tuominde-chaoyang-yi-physics": "脱敏的",
    # 2026-05-31 当日新增
    "shixinran-xicheng-yi-math": "史欣然",
    "zhangyizhang-haidian-er-math": "张益彰",
    "fangshiyao-xicheng-yi-math": "房诗尧",
    "shenyueran-haidian-er-math": "沈跃然",
}
STUDENT_NAME_GLOBAL = os.environ.get("STUDENT_NAME", "")  # 不再硬编码默认
IMG_EXTS = {".jpg", ".jpeg", ".png", ".heic"}


# ─── 测试数据扫描 ──────────────────────────────────────────────────────────
def find_cases() -> list[dict]:
    only = set(s.strip() for s in os.environ.get("CASES", "").split(",") if s.strip())
    cases = []
    for d in sorted(TEST_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        if only and d.name not in only:
            continue
        photos = sorted(
            p for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in IMG_EXTS
            and not p.name.startswith(".") and p.stat().st_size > 1024
        )
        xlsx = next((p for p in d.iterdir()
                     if p.suffix.lower() in (".xlsx", ".xls")
                     and not p.name.startswith(".")), None)
        # 可选：image-scores/ 子目录里第一张图作为"图片小分"场景输入
        img_dir = d / "image-scores"
        score_image = None
        if img_dir.is_dir():
            score_image = next(
                (p for p in img_dir.iterdir()
                 if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic")
                 and not p.name.startswith(".")), None)
        if photos:
            cases.append({"name": d.name, "photos": photos,
                          "xlsx": xlsx, "score_image": score_image})
    return cases


# ─── 端到端流水线驱动 ─────────────────────────────────────────────────────
def run_pipeline(case: dict, out_dir: Path, *,
                 score_file: Path | None,
                 scenario: str) -> tuple[str | None, dict | None, str]:
    """跑一次完整流水线。score_file=None → auto 模式（不上传小分）。"""
    tag = f"{case['name']}/{scenario}"

    def log(msg: str):
        print(f"  [{tag}] {msg}", flush=True)

    # 1. 上传照片
    files = [("files", (p.name, p.open("rb"), "application/octet-stream"))
             for p in case["photos"]]
    try:
        log(f"上传 {len(files)} 张照片 …")
        r = _post(f"{API}/api/analyses", files=files, timeout=180, expect_json=True).json()
    finally:
        for _, (_, fh, _) in files:
            try: fh.close()
            except Exception: pass
    aid = r.get("id")
    log(f"aid={aid} status={r.get('status')}")
    if not aid:
        return None, None, f"upload_failed: {r}"

    # 2. 轮询 detect
    d = {}
    for _ in range(60):
        d = _get(f"{API}/api/analyses/{aid}/detect", timeout=30, expect_json=True).json()
        if d.get("status") in ("ready_confirm", "failed"):
            break
        time.sleep(3)
    log(f"detect → {d.get('status')}")
    (out_dir / "detect.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if d.get("status") != "ready_confirm":
        return aid, None, f"detect_failed: {d.get('error', '')[:200]}"

    # 3. 上传小分（teacher 系列场景；图片/xlsx 都走同 /scores 入口）
    if score_file:
        log(f"上传小分 {score_file.name}")
        with score_file.open("rb") as f:
            sr = _post(
                f"{API}/api/analyses/{aid}/scores",
                files={"file": (score_file.name, f, "application/octet-stream")},
                timeout=180, expect_json=True).json()
        log(f"  小分 src={sr.get('source')}  {sr.get('exam_total')}  "
            f"{sr.get('n_questions')}题  warnings={len(sr.get('warnings') or [])}")

    # 4. /start
    # 学生名优先级：环境变量 > 每 case 映射 > 不覆盖（card_meta OCR 结果保留）
    name_override = (STUDENT_NAME_GLOBAL
                      or PER_CASE_NAME.get(case["name"], ""))
    params = {"student_name": name_override} if name_override else {}
    _post(f"{API}/api/analyses/{aid}/start", params=params, timeout=30)

    # 5. 轮询完成（Phase B/C + analyze + PDF）
    s = {}
    last_stage = None
    for _ in range(150):  # ~15min 上限
        s = _get(f"{API}/api/analyses/{aid}/status", timeout=30, expect_json=True).json()
        if (s.get("stage"), s.get("stage_name")) != last_stage:
            last_stage = (s.get("stage"), s.get("stage_name"))
            log(f"  stage {s.get('stage')} {s.get('stage_name', '')}")
        if s.get("status") in ("done", "failed"):
            break
        time.sleep(6)
    log(f"pipeline → {s.get('status')}")
    (out_dir / "status.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    if s.get("status") != "done":
        return aid, None, f"pipeline_failed: {s.get('error', '')[:200]}"

    # 6. 拉报告
    rj = _get(f"{API}/api/analyses/{aid}/report", timeout=60, expect_json=True).json()
    (out_dir / "report.json").write_text(
        json.dumps(rj, ensure_ascii=False, indent=2), encoding="utf-8")
    pdf = _get(f"{API}/api/analyses/{aid}/report.pdf", timeout=60)
    if pdf.status_code == 200:
        (out_dir / "report.pdf").write_bytes(pdf.content)
        log(f"PDF {len(pdf.content)//1024} KB")
    return aid, rj, "done"


# ─── 机械事实预校验（Python 准确算好，省得审核员 LLM 出错）─────────────
def mechanical_facts(report: dict) -> dict:
    """先把"会算的事"用 Python 算准——审核员只看结论，不再自己验算。
    上一轮跑发现 qwen-max-latest 在 排序/求和/计数 上反复误判。"""
    wq = report.get("wrong_questions", []) or []
    n_lost = report.get("n_lost", 0)
    lost_total = float(report.get("lost_total", 0) or 0)
    sum_lost = round(sum(float(w.get("lost") or 0) for w in wq), 2)
    qids = []
    for w in wq:
        m = re.search(r"\d+", w.get("qid", "") or "")
        if m: qids.append(int(m.group(0)))
    modules = report.get("modules", []) or []
    mod_names = [m.get("name", "") for m in modules]
    mod_has_english = any(re.search(r"[A-Za-z]", n or "") for n in mod_names)
    mod_lost_qs_sum = sum(len(m.get("lost_qs") or []) for m in modules)
    full_score = float(report.get("full_score", 0) or 0)
    total_scored = float(report.get("total_scored", 0) or 0)
    rate = float(report.get("rate", 0) or 0)
    rate_ok = (abs(rate * full_score - total_scored) < 0.5) if full_score else False
    # 乱码/异常字符扫描
    full_text = json.dumps(report, ensure_ascii=False)
    bad_chars = []
    for ch in ("☒", "□", "▢"):
        if ch in full_text: bad_chars.append(ch)
    return {
        "n_lost_matches_len_wq": n_lost == len(wq),
        "n_lost": n_lost, "len_wq": len(wq),
        "lost_total_matches_sum_wq_lost": abs(lost_total - sum_lost) < 0.05,
        "lost_total": lost_total, "sum_wq_lost": sum_lost,
        "qids_ascending": qids == sorted(qids),
        "qid_sequence": qids,
        "module_names": mod_names,
        "modules_all_chinese": not mod_has_english,
        "modules_cover_n_lost": mod_lost_qs_sum == n_lost,
        "modules_lost_qs_total": mod_lost_qs_sum,
        "rate_consistent": rate_ok,
        "rate": rate, "total_scored": total_scored, "full_score": full_score,
        "tofu_chars_found": bad_chars,
        "score_source": report.get("score_source"),
        "subject": report.get("subject"),
        "essay_questions": [w["qid"] for w in wq
                            if "作文" in (w.get("type_cn") or "")],
    }


# ─── 报告质量审核（qwen-max-latest）──────────────────────────────────────
AUDIT_PROMPT = """你是中学教学产品的内容质量评审员。下面给你一份学生学情分析报告 JSON，
**机械算术 / 排序 / 字段计数 已由 Python 预先校验通过**（见 mechanical_facts 块），
**不要再质疑或重复校验这些**——你的工作是判**内容质量**。

按 P0/P1/P2 输出问题：
  P0 = 真实错误：乱码（tofu_chars_found 非空才报）、明显事实错（如分数 >100 / 模块名是英文 / 作文 AI 估 80%+ 满分却没标待复核）
  P1 = 内容质量：why_wrong / fix 空话（"仔细审题"、"注意单位"、"审题漏条件"）；
       LaTeX 公式不完整或定界符错；表述冗长偏题；作文兜底逻辑可疑
  P2 = 改进建议：表述可更精准 / 排版可更易读 等

# **不要再报的（已 Python 验过；如 mechanical_facts 显示 False 才可报）**
- "wrong_questions 未升序"——qids_ascending=True 就不要报
- "n_lost 与 len(wq) 不一致"——n_lost_matches_len_wq=True 就不要报
- "lost_total ≠ sum"——lost_total_matches_sum_wq_lost=True 就不要报
- "total_scored 与公式不符"——你看不到满分题，别推断；rate_consistent 已校验
- "模块英文键"——modules_all_chinese=True 就不要报

输出严格 JSON：
{
  "overall_grade": "A 可发给用户 / B 有内容瑕疵 / C 多处问题需修 / D 不可用",
  "issues": [
    {"severity": "P0|P1|P2", "area": "内容/作文/LaTeX/乱码/其它",
     "detail": "问题描述", "evidence": "具体字段或值"}
  ],
  "summary": "一句话总评"
}
"""


def audit_report(report: dict | None) -> dict:
    if not report:
        return {"overall_grade": "D",
                "issues": [{"severity": "P0", "area": "流水线",
                            "detail": "未产出报告", "evidence": ""}],
                "summary": "流水线失败"}
    try:
        import openai
    except ImportError:
        return {"overall_grade": "?",
                "issues": [{"severity": "P0", "area": "审核工具",
                            "detail": "缺 openai 包", "evidence": ""}],
                "summary": "pip install openai"}
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        return {"overall_grade": "?",
                "issues": [{"severity": "P0", "area": "审核工具",
                            "detail": "缺 DASHSCOPE_API_KEY", "evidence": ""}],
                "summary": "环境变量缺失"}
    client = openai.OpenAI(api_key=key,
                           base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    facts = mechanical_facts(report)
    payload = (AUDIT_PROMPT
               + "\n# mechanical_facts（Python 预校验，结论可信）\n"
               + json.dumps(facts, ensure_ascii=False, indent=2)
               + "\n\n# 报告 JSON\n"
               + json.dumps(report, ensure_ascii=False, indent=2)[:28000])
    resp = client.chat.completions.create(
        model="qwen-max-latest",
        messages=[{"role": "user", "content": payload}],
        temperature=0.0, max_tokens=2500,
        response_format={"type": "json_object"}, timeout=180,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"overall_grade": "?",
                "issues": [{"severity": "P0", "area": "审核解析",
                            "detail": f"返回非 JSON: {raw[:300]}",
                            "evidence": ""}],
                "summary": "审核 LLM 输出无法解析"}


# ─── 主流程 ─────────────────────────────────────────────────────────────
def main():
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    run_dir = RUN_ROOT / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== API: {API}   输出: {run_dir} ===")
    cases = find_cases()
    if not cases:
        print("无测试数据")
        sys.exit(1)
    print(f"=== {len(cases)} 份测试数据 ===")
    for c in cases:
        print(f" - {c['name']}: {len(c['photos'])} 张照片 + "
              f"{'小分' if c['xlsx'] else '无小分'}")

    # 每份数据按可用资源生成场景：
    #   teacher_xlsx  → 带 xlsx 小分表
    #   teacher_image → 带图片小分（image-scores/ 目录里第一张图）
    #   auto          → 不带小分（系统自动判分）
    summary = []
    for c in cases:
        scenarios: list[tuple[str, Path | None]] = []
        if c["xlsx"]:
            scenarios.append(("teacher_xlsx", c["xlsx"]))
        if c["score_image"]:
            scenarios.append(("teacher_image", c["score_image"]))
        scenarios.append(("auto", None))
        for sc, sf in scenarios:
            print(f"\n=== ▶ {c['name']} / {sc} ===")
            d = run_dir / c["name"] / sc
            d.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            aid, report, status = None, None, "?"
            try:
                aid, report, status = run_pipeline(
                    c, d, score_file=sf, scenario=sc)
            except Exception as e:
                import traceback
                status = f"exception: {type(e).__name__}: {e}"
                print(f"  [{c['name']}/{sc}] !! {status}")
                traceback.print_exc()
            elapsed = int(time.time() - t0)
            print(f"  耗时 {elapsed}s")
            au = audit_report(report) if status == "done" else {
                "overall_grade": "D",
                "issues": [{"severity": "P0", "area": "流水线",
                            "detail": status, "evidence": ""}],
                "summary": status[:200],
            }
            (d / "audit.json").write_text(
                json.dumps(au, ensure_ascii=False, indent=2), encoding="utf-8")
            summary.append({
                "case": c["name"], "scenario": sc, "aid": aid,
                "status": status, "elapsed_s": elapsed,
                "grade": au.get("overall_grade"),
                "P0": sum(1 for i in au.get("issues", []) if i.get("severity") == "P0"),
                "P1": sum(1 for i in au.get("issues", []) if i.get("severity") == "P1"),
                "P2": sum(1 for i in au.get("issues", []) if i.get("severity") == "P2"),
                "summary": au.get("summary", ""),
            })

    print("\n" + "=" * 78 + "\n汇总")
    print(f"{'case':<22}{'场景':<15}{'状态':<8}{'耗时':<7}{'分级':<5}{'P0':<3}{'P1':<3}{'P2':<3}  评")
    for s in summary:
        print(f"{s['case']:<22}{s['scenario']:<15}{s['status']:<8}"
              f"{s['elapsed_s']:>4}s   {s['grade']:<5}"
              f"{s['P0']:<3}{s['P1']:<3}{s['P2']:<3}  {s['summary'][:50]}")
    (run_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详情见 {run_dir}/<case>/<scenario>/audit.json")


if __name__ == "__main__":
    main()
