#!/usr/bin/env python3
"""腾讯"试题批改Agent"(SubmitQuestionMarkAgentJob) 适用性研究测试。

背景：腾讯下线数学试题识别3.0(EduPaperOCR,我们没用过)，推荐迁移到试题批改Agent。
研究问题：它对**我们的任务**有没有用？
  A. 涂卡选择题识别(线上主链路)——假设:不适用(为印刷题+手写作答设计)
  B. 主观题判分(我们的硬门槛:qwen读不动乱手写)——假设:可能有价值
用法：
  python3 qmark_agent_probe.py submit <image> [ref_answer_file]   # 提交单个任务
  python3 qmark_agent_probe.py query <job_id>                     # 查询结果
  python3 qmark_agent_probe.py run                                # 跑全部预设用例
环境：TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

from tencentcloud.common import credential
from tencentcloud.ocr.v20181119 import models, ocr_client

REGION = "ap-beijing"
OUT_DIR = Path(__file__).resolve().parents[2] / "_audits" / "qmark-agent"


def _client():
    cred = credential.Credential(
        os.environ["TENCENT_OCR_SECRET_ID"], os.environ["TENCENT_OCR_SECRET_KEY"])
    return ocr_client.OcrClient(cred, REGION)


def submit(image_path: str, ref_answer: str = "", step: bool = True) -> str:
    c = _client()
    req = models.SubmitQuestionMarkAgentJobRequest()
    req.ImageBase64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    cfg = {"KnowledgePoints": True, "TrueAnswer": True}
    if step:
        cfg["StepCorrection"] = True
    req.QuestionConfigMap = json.dumps(cfg)
    if ref_answer:
        req.ReferenceAnswer = ref_answer
    resp = c.SubmitQuestionMarkAgentJob(req)
    print(f"submitted {Path(image_path).name}: JobId={resp.JobId} "
          f"QuestionCount={getattr(resp, 'QuestionCount', '?')}")
    return resp.JobId


def query(job_id: str) -> dict:
    c = _client()
    req = models.DescribeQuestionMarkAgentJobRequest()
    req.JobId = job_id
    resp = c.DescribeQuestionMarkAgentJob(req)
    return json.loads(resp.to_json_string())


def poll(job_id: str, timeout: int = 300) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = query(job_id)
        st = d.get("Status") or d.get("JobStatus") or ""
        if str(st).lower() in ("success", "finished", "done", "3", "failed", "error"):
            return d
        time.sleep(8)
    return {"_timeout": True, "JobId": job_id}


CASES = [
    # (名字, 图, 参考答案来源qid或"", 真值说明)
    ("A_card_page1_choices", "students/jiaxiaoqi/2026-chaoyang-er-math/answer-card-photos/page-01.jpg",
     None, "涂卡Q1-8真值ACCBCABD+填空Q9-16全对——测它认不认涂卡"),
    ("B1_q21_partial", "students/jiaxiaoqi/2026-chaoyang-er-math/answer-card-photos/cropped/q21.png",
     21, "教师真值3/5(部分错)——测判分方向对不对"),
    ("B2_q28_zero", "students/jiaxiaoqi/2026-chaoyang-er-math/answer-card-photos/cropped/q28.png",
     28, "教师真值0/7(全错/未答)——测全错能不能判出来"),
    ("B3_q26_full", "students/jiaxiaoqi/2026-chaoyang-er-math/answer-card-photos/cropped/q26.png",
     26, "教师真值满分(对照组)——测对的会不会误杀"),
]


def _solutions() -> dict:
    import yaml
    root = Path(__file__).resolve().parents[2]
    d = yaml.safe_load(open(root / "knowledge-base/exams/mock/math/beijing/2026-chaoyang-er.yaml"))
    return {int(str(q["id"]).lstrip("Q")): (q.get("solution") or q.get("answer") or "")
            for q in d["questions"]}


def run_all():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sols = _solutions()
    root = Path(__file__).resolve().parents[2]
    jobs = []
    for name, img, ref_qid, truth in CASES:
        ref = sols.get(ref_qid, "")[:2000] if ref_qid else ""
        try:
            jid = submit(str(root / img), ref)
            jobs.append((name, jid, truth))
        except Exception as e:
            print(f"  ✗ {name} submit失败: {e}")
        time.sleep(7)   # 并发限10张/分钟
    print("\n--- polling ---")
    for name, jid, truth in jobs:
        d = poll(jid)
        out = OUT_DIR / f"{name}.json"
        out.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name}: -> {out}  (truth: {truth})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "submit":
        ref = Path(sys.argv[3]).read_text() if len(sys.argv) > 3 else ""
        submit(sys.argv[2], ref)
    elif cmd == "query":
        print(json.dumps(query(sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        run_all()
