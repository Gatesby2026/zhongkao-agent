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

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "test-data"
RUN_ROOT = TEST_ROOT / "_runs"
API = os.environ.get("API_BASE", "https://zhongkao.gatesby.xyz").rstrip("/")
STUDENT_NAME = os.environ.get("STUDENT_NAME", "贾小淇")
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
        if photos:
            cases.append({"name": d.name, "photos": photos, "xlsx": xlsx})
    return cases


# ─── 端到端流水线驱动 ─────────────────────────────────────────────────────
def run_pipeline(case: dict, out_dir: Path, *,
                 use_xlsx: bool) -> tuple[str | None, dict | None, str]:
    tag = f"{case['name']}/{'teacher' if use_xlsx else 'auto'}"

    def log(msg: str):
        print(f"  [{tag}] {msg}", flush=True)

    # 1. 上传照片
    files = [("files", (p.name, p.open("rb"), "application/octet-stream"))
             for p in case["photos"]]
    try:
        log(f"上传 {len(files)} 张照片 …")
        r = requests.post(f"{API}/api/analyses", files=files, timeout=180).json()
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
        d = requests.get(f"{API}/api/analyses/{aid}/detect", timeout=30).json()
        if d.get("status") in ("ready_confirm", "failed"):
            break
        time.sleep(3)
    log(f"detect → {d.get('status')}")
    (out_dir / "detect.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if d.get("status") != "ready_confirm":
        return aid, None, f"detect_failed: {d.get('error', '')[:200]}"

    # 3. 上传小分（仅 teacher 场景且 xlsx 可用）
    if use_xlsx and case["xlsx"]:
        log(f"上传小分表 {case['xlsx'].name}")
        with case["xlsx"].open("rb") as f:
            sr = requests.post(
                f"{API}/api/analyses/{aid}/scores",
                files={"file": (case["xlsx"].name, f,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=60).json()
        log(f"  小分: {sr.get('exam_total')}  {sr.get('n_questions')}题")

    # 4. /start
    requests.post(f"{API}/api/analyses/{aid}/start",
                  params={"student_name": STUDENT_NAME}, timeout=30)

    # 5. 轮询完成（Phase B/C + analyze + PDF）
    s = {}
    last_stage = None
    for _ in range(150):  # ~15min 上限
        s = requests.get(f"{API}/api/analyses/{aid}/status", timeout=30).json()
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
    rj = requests.get(f"{API}/api/analyses/{aid}/report", timeout=60).json()
    (out_dir / "report.json").write_text(
        json.dumps(rj, ensure_ascii=False, indent=2), encoding="utf-8")
    pdf = requests.get(f"{API}/api/analyses/{aid}/report.pdf", timeout=60)
    if pdf.status_code == 200:
        (out_dir / "report.pdf").write_bytes(pdf.content)
        log(f"PDF {len(pdf.content)//1024} KB")
    return aid, rj, "done"


# ─── 报告质量审核（qwen-max-latest）──────────────────────────────────────
AUDIT_PROMPT = """你是一位资深中学教师 + 产品质量评审员，正在审核一份学生学情分析报告 JSON。
逐项检查"明显问题"，按 P0/P1/P2 分级输出（P0=严重，数据自相矛盾/乱码/字段缺失 ；
P1=质量差但可读，如空话/排序错/英文键泄露 ； P2=改进建议）。

# 检查清单
1. **数据自洽**：
   - total_scored 是否 ≈ sum(wrong_questions[i].score - wrong_questions[i].lost) + 满分题的 score
   - lost_total 是否 ≈ sum(wrong_questions[i].lost)
   - n_lost 是否等于 len(wrong_questions)
   - rate ≈ total_scored / full_score
2. **模块映射**：modules[].name 必须**中文**——出现 "mechanics"/"writing"/"reading" 等
   英文键 = P0；非"其它"模块应覆盖该卷绝大多数题
3. **失分题列表**：wrong_questions 必须按 qid 升序（Q\\d+ 抽数字）；
   每条 type_cn/module_cn 非空；why_wrong/fix 不应是"仔细审题/注意单位"这种通用空话
4. **科目特异**：subject==chinese/english 且题型含"作文"应有合理处理
   （AI 估分或满分占位 + 待教师复核标记，不应估出明显离谱的分）
5. **乱码**：任何字段含 ☒/□/方框/连续 \\\\ 等 = P0
6. **总览数字范围**：rate 应在 0-1，得分率 = 百分比；total_scored ≤ full_score

# 输出格式（严格 JSON，无 markdown 围栏）
{
  "overall_grade": "A=可发给用户 / B=有瑕疵但可读 / C=多处问题需修 / D=不可用",
  "issues": [
    {"severity": "P0|P1|P2", "area": "数据自洽/模块/失分题/科目特异/乱码/总览",
     "detail": "问题描述", "evidence": "字段名或数值"}
  ],
  "summary": "一句话总评"
}

# 报告 JSON
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
    payload = AUDIT_PROMPT + json.dumps(report, ensure_ascii=False, indent=2)[:30000]
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

    # 每份数据跑两场景：teacher（带小分表）+ auto（无小分→系统自动判分）
    # 若 case 无 xlsx，跳过 teacher 场景
    summary = []
    for c in cases:
        scenarios = []
        if c["xlsx"]:
            scenarios.append("teacher")
        scenarios.append("auto")
        for sc in scenarios:
            print(f"\n=== ▶ {c['name']} / {sc} ===")
            d = run_dir / c["name"] / sc
            d.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            aid, report, status = run_pipeline(
                c, d, use_xlsx=(sc == "teacher"))
            elapsed = int(time.time() - t0)
            print(f"  耗时 {elapsed}s")
            au = audit_report(report) if status == "done" else {
                "overall_grade": "D",
                "issues": [{"severity": "P0", "area": "流水线",
                            "detail": status, "evidence": ""}],
                "summary": status,
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
    print(f"{'case':<22}{'场景':<8}{'状态':<8}{'耗时':<7}{'分级':<5}{'P0':<3}{'P1':<3}{'P2':<3}  评")
    for s in summary:
        print(f"{s['case']:<22}{s['scenario']:<8}{s['status']:<8}"
              f"{s['elapsed_s']:>4}s   {s['grade']:<5}"
              f"{s['P0']:<3}{s['P1']:<3}{s['P2']:<3}  {s['summary'][:54]}")
    (run_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详情见 {run_dir}/<case>/<scenario>/audit.json")


if __name__ == "__main__":
    main()
