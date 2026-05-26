#!/usr/bin/env python3
"""学情分析报告生成（学生向）。

输入（新数据约定）：
  knowledge-base/exams/{mock,zhenti}/<subj>/beijing/<slug>.yaml   # 试卷结构化
  students/<name>/<exam-slug>/answer-card.json           # 学生作答（含主观题看图评分）
  students/<name>/<exam-slug>/scores.json                # 最终得分
  students/<name>/<exam-slug>/student.json               # 学生信息（可选）

流程：
  1. join 三方 → ExamView（lib/schemas）
  2. 程序聚合：模块/难度/知识点/大题（lib/aggregate，无 LLM）
  3. LLM：逐失分题归因 + 整卷综合（lib/analyze，qwen-max + .cache）
  4. 生成 Markdown（失分题内嵌答题卡裁切原图，file:// 绝对路径）
  5. 调 md-to-pdf skill convert.sh → PDF

用法：
  DASHSCOPE_API_KEY=$KEY python3 scripts/student-report/build_report.py \
    --student-dir students/jiaxiaoqi/2026-chaoyang-yi-physics \
    [--standard <yaml>]   # 不传则自动推断
    [--skip-pdf]

预留：跨考试趋势——schemas/aggregate 已按单场设计，多场对比时在总览加趋势小节。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import aggregate as agg          # noqa: E402
from lib import analyze                    # noqa: E402
from lib.schemas import load_exam_view, ExamView, QView  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KB_ROOT = ROOT / "knowledge-base" / "exams"   # 下含 mock/ zhenti/
MD2PDF = Path.home() / ".claude" / "skills" / "md-to-pdf" / "convert.sh"
SUBJ_RE = re.compile(
    r"-(physics|chinese|math|english|politics|history|chemistry|biology|geography)$")


def infer_standard(student_dir: Path) -> Path | None:
    """students/<name>/2026-chaoyang-yi-physics → kb/.../physics/.../2026-chaoyang-yi.yaml"""
    slug = student_dir.name
    m = SUBJ_RE.search(slug)
    if not m:
        return None
    subj, base = m.group(1), slug[:m.start()]
    for kind in ("mock", "zhenti"):       # 模拟优先，再真题
        d = KB_ROOT / kind / subj / "beijing"
        hits = sorted(d.glob(f"{base}.yaml")) if d.exists() else []
        if hits:
            return hits[0]
    return None


# ─── Markdown 渲染 ───────────────────────────────────────────────────────────

def _bar(rate: float, width: int = 20) -> str:
    n = round(rate * width)
    return "█" * n + "░" * (width - n)


from lib.textfmt import fix_latex_escape as _fix_tex  # noqa: E402


def _hl(s: str) -> str:
    """关键内容染红（md-to-pdf python-markdown 透传 raw HTML）。对标旧标杆红色重点。"""
    return f'<span style="color:#c0392b;font-weight:600">{s}</span>'


def _fig_abs(exam: ExamView, q: QView) -> str | None:
    """答题卡裁切原图绝对路径（file:// 供 Chrome headless 内嵌）。"""
    if not q.region_image:
        return None
    p = (exam.student_dir / "answer-card-photos" / q.region_image)
    return f"file://{p.resolve()}" if p.exists() else None


def render_markdown(exam: ExamView, per_q: dict[int, dict],
                    overall: dict) -> str:
    st = agg.overall_stats(exam)
    mods = agg.module_mastery(exam)
    diffs = agg.difficulty_breakdown(exam)
    secs = agg.section_breakdown(exam)
    kps = agg.lost_knowledge_points(exam)
    lost = agg.lost_questions(exam)

    L: list[str] = []
    w = L.append

    # 标题
    w(f"# {exam.student_name} · {exam.exam_title} · 学情报告\n")
    w(f"> 考号 {exam.student_id}　|　总分 **{st['total_scored']} / "
      f"{st['full_score']}**（得分率 {st['rate']*100:.0f}%）"
      f"　|　失分 {st['lost_total']} 分，{st['n_lost']} 题\n")

    # 数据质量提示条（小分表 + 答题卡识别缺失 → 报告顶部告知）
    dq = getattr(exam, "data_quality", {}) or {}
    notices = []
    # ── 答题卡侧（P0.4）──
    miss_choice = dq.get("card_missing_choice_qids") or []
    miss_subj = dq.get("card_missing_subjective_qids") or []
    skipped_pages = dq.get("card_skipped_non_card_pages") or []
    if miss_choice:
        qs = "、".join(miss_choice[:6])
        more = " 等" if len(miss_choice) > 6 else ""
        notices.append(
            f"答题卡未识别到 {len(miss_choice)} 道选择题涂卡（{qs}{more}），"
            "按未作答记 0 分；若实际有作答，请重传更清晰照片")
    if miss_subj:
        qs = "、".join(miss_subj[:4])
        more = " 等" if len(miss_subj) > 4 else ""
        notices.append(
            f"答题卡未识别到 {len(miss_subj)} 道主观题作答区（{qs}{more}），"
            "可能该页缺拍或字迹太糊")
    if skipped_pages:
        notices.append(
            f"上传的 {len(skipped_pages)} 张图被判为非答题卡内容已忽略"
            f"（第 {'、'.join(str(i) for i in skipped_pages)} 张）")
    # ── 小分表侧 ──
    n_assumed = len(dq.get("assumed_full_qids") or [])
    n_block = len(dq.get("align_block_shared_qids") or [])
    n_miss = len(dq.get("align_miss_qids") or [])
    if n_assumed:
        qs = "、".join((dq.get("assumed_full_qids") or [])[:6])
        more = " 等" if n_assumed > 6 else ""
        notices.append(f"小分表未列出 {n_assumed} 道（{qs}{more}），按满分占位")
    if n_block:
        notices.append(f"小分表与试卷题号划分不同，{n_block} 道题按比例分摊")
    if n_miss:
        qs = "、".join((dq.get("align_miss_qids") or [])[:4])
        notices.append(f"{n_miss} 道题对齐失败按满分占位（{qs}…）")
    for w_ in (dq.get("parse_warnings") or [])[:2]:
        notices.append(w_)
    if notices:
        w("\n> ⚠ **数据质量提示**\n>\n")
        for nt in notices:
            w(f"> - {nt}\n")
        w("\n")

    # 逐题得分速览（开篇，一眼定位丢分题）
    w("\n## 逐题得分速览\n")
    w("> 🟢 满分　🟡 部分扣分　🔴 全失\n")
    w("\n| 题 | 得分 | 题 | 得分 | 题 | 得分 | 题 | 得分 | 题 | 得分 |")
    w("|--|--|--|--|--|--|--|--|--|--|")
    qs_sorted = sorted(exam.questions, key=lambda x: x.num)
    cells = []
    for q in qs_sorted:
        mark = "🟢" if q.lost <= 0 else ("🔴" if q.scored <= 0 else "🟡")
        cells.append(f"{q.qid} | {mark}{q.scored:g}/{q.score}")
    for i in range(0, len(cells), 5):
        row = cells[i:i + 5]
        while len(row) < 5:
            row.append(" | ")
        w("| " + " | ".join(row) + " |")

    # 一、总览
    w("\n## 一、这次考得怎么样\n")
    w(f"- **{overall.get('verdict','')}**\n")
    w("\n**各大题得分率**\n")
    w("\n| 大题 | 得分 | 满分 | 得分率 |")
    w("|---|---|---|---|")
    for s in secs:
        w(f"| {s['type_cn']} | {s['scored']} | {s['full']} | "
          f"`{_bar(s['rate'],12)}` {s['rate']*100:.0f}% |")
    w("\n**模块掌握度**（弱→强）\n")
    w("\n| 模块 | 得分 | 满分 | 掌握度 |")
    w("|---|---|---|---|")
    for m in mods:
        w(f"| {m['module_cn']} | {m['scored']} | {m['full']} | "
          f"`{_bar(m['rate'],12)}` {m['rate']*100:.0f}% |")
    w("\n**难度维度**\n")
    w("\n| 难度 | 题数 | 得分率 | 失分题 |")
    w("|---|---|---|---|")
    for d in diffs:
        w(f"| {d['difficulty']} | {d['n']} | {d['rate']*100:.0f}% | "
          f"{'、'.join(d['lost_qs']) or '—'} |")

    # 二、薄弱诊断
    w("\n## 二、哪些还没掌握\n")
    for ws in overall.get("weakSpots", []):
        qs = "、".join(ws.get("qs", []))
        w(f"- **{ws.get('area','')}**（失 {ws.get('lostPoints','?')} 分"
          f"{f'：{qs}' if qs else ''}）— {ws.get('evidence','')}")

    # 三、逐题精析（按题号升序，便于对照试卷）
    w("\n## 三、每道失分题，到底错在哪\n")
    for q in sorted(lost, key=lambda x: x.num):
        a = per_q.get(q.num, {})
        kp = a.get("knowledgePoint") or q.module_cn
        # 标题对齐旧版标杆：第 N 题（题型 · 精确知识点 · 失 N 分）
        w(f"\n### 第 {q.num} 题（{q.type_cn} · {kp} · 失 {q.lost} 分）\n")

        # —— 原题：题干+配图+选项全在【一个连续 blockquote】里 ——
        # 关键：所有行加 > 前缀，段间空行也用 ">"（裸空行会终止 blockquote）
        w("#### 原题\n")
        # 清 OCR 残留的 markdown 代码围栏（```text / ```）——在 blockquote 内会破坏渲染
        stem = re.sub(r"^\s*```[a-zA-Z]*\s*$", "", q.stem,
                      flags=re.MULTILINE).strip()
        if len(stem) > 460:
            stem = stem[:460] + " ……"
        paper_fig = exam.figure_abs(q)
        qlines: list[str] = []
        if paper_fig and "[图]" in stem:
            head, _, tail = stem.partition("[图]")
            tail = tail.replace("[图]", "").strip()
            if head.strip():
                qlines += head.strip().split("\n")
            qlines += ["", f"![{q.qid}题目配图]({paper_fig})", ""]
            if tail:
                qlines += tail.split("\n")
        else:
            qlines += stem.replace("[图]", "").split("\n")
            if paper_fig:
                qlines += ["", f"![{q.qid}题目配图]({paper_fig})"]
        if q.options:
            qlines.append("")
            qlines += [f"- {k}. {v}" for k, v in q.options.items()]
        w("\n".join(("> " + ln) if ln.strip() else ">" for ln in qlines))
        w("")

        # —— 标准答案 / 你的答案 ——
        if q.is_choice:
            w("#### 标准答案\n")
            w(f"{_hl(q.std_answer)} ✅\n")
            w("#### 你的答案\n")
            sf = q.student_filled or "（未作答）"
            w(f"**{sf}** ❌\n")
        else:
            w("#### 标准答案\n")
            w("> " + _hl(_fix_tex(q.std_answer.strip())).replace("\n", "\n> ")
              + "\n")
            w("#### 你的答案\n")
            ans_fig = _fig_abs(exam, q)         # 答题卡裁切原图
            if ans_fig:
                w(f"![{q.qid}答题卡作答原图]({ans_fig})\n")
            else:
                w("> （未识别到答题卡作答区，建议人工核对原卷）\n")

        # —— 阅卷详情（主观题）：以【老师实际批改分】为准，删除 AI 估分口径 ——
        # P0：grade.suggestedScore（AI 看图建议分）与 scores.json（老师实际分）
        # 系统性不一致；scoreReason 含 AI 估分会与实际分自相矛盾。故：
        #   只展示 老师实际分 + matchedPoints(✓) + missedPoints(✗ 看图事实，无估分)
        #   missedPoints 空但实际失分 → 诚实标注，不臆造
        g = q.grade if not q.is_choice else None
        if not q.is_choice:
            w("#### 阅卷详情\n")
            w(f"**本题得分：{q.scored:g} / {q.score}**（老师批改为准）\n")
            mp = (g or {}).get("matchedPoints") or []
            msd = (g or {}).get("missedPoints") or []
            if mp:
                w("**✓ 你答对的：**\n")
                for x in mp:
                    w(f"- {_fix_tex(x)}")
                w("")
            if msd:
                w("**✗ 你失分的：**\n")
                for x in msd:
                    w(f"- {_hl(_fix_tex(x))}")   # 看图失分事实（含「应为X你算成Y」对比）
                w("")
            elif q.lost > 0:
                w(_hl(f"⚠️ 本题失 {q.lost:g} 分，但 AI 看图未能定位具体失分点——"
                      f"请对照老师在原卷上的批注核对。") + "\n")

        # —— 选项对比表（选择题）——
        ct = a.get("comparisonTable") or []
        if q.is_choice and ct:
            w("#### 选项逐项对比\n")
            w("| 选项 | 你的判断 | 正解 | 说明 |")
            w("|---|---|---|---|")
            for row in ct:
                opt = row.get("option", "")
                mark = " ✅" if row.get("correct") == "对" else ""
                w(f"| {opt}{mark} | {row.get('student','')} | "
                  f"{row.get('correct','')} | {row.get('reason','')} |")
            w("")

        # —— 错因分析（揭示思维误区，不复述答案）——
        ww = a.get("whyWrong") or []
        if isinstance(ww, list) and ww:
            w("#### 你为什么会错\n")
            for i, pt in enumerate(ww, 1):
                pt = _fix_tex(pt)
                w(f"{i}. {_hl(pt) if i == 1 else pt}")
            w("")

        # —— ✅ 正确该怎么做（核心：让学生看完能独立做对）——
        sc = a.get("solveCorrectly") or []
        if isinstance(sc, list) and sc:
            w("#### ✅ 正确该怎么做\n")
            for i, pt in enumerate(sc, 1):
                w(f"{i}. {_fix_tex(pt)}")
            w("")

        # —— 这道题的避坑点（本题特有，非通用废话）——
        ki = a.get("keyInsight") or []
        if isinstance(ki, list) and ki:
            w("#### 这道题的避坑点\n")
            for pt in ki:
                w(f"- {_hl(_fix_tex(pt))}")
            w("")

        w("---")

    # 四、答题习惯
    habits = overall.get("habits") or _extract_habits(per_q, exam)
    if habits:
        w("\n## 四、你的答题习惯\n")
        for h in habits:
            w(f"- {h}")

    # 五、行动计划
    w("\n## 五、下一步怎么提分\n")
    for p in overall.get("actionPlan", []):
        w(f"\n### 优先级 {p.get('priority','?')}：{p.get('topic','')}"
          f"（预期 +{p.get('expectedGain','?')}）\n")
        w(f"{p.get('why','')}\n")
        for d in p.get("drills", []):
            w(f"- {d}")
    wp = overall.get("weekPlan", [])
    if wp:
        w("\n**备战周计划**\n")
        w("\n| 周 | 重点 | 量化目标 |")
        w("|---|---|---|")
        for x in wp:
            w(f"| 第{x.get('week','?')}周 | {x.get('focus','')} | {x.get('target','')} |")
    w(f"\n**下次目标**：{overall.get('nextTarget','')}\n")

    # 肯定面（放最后，正向收尾）
    pos = overall.get("positives", [])
    if pos:
        w("\n## 六、你做得好的地方\n")
        for p in pos:
            w(f"- {p}")

    w("\n---\n> 本报告由 AI 辅助生成，失分事实基于答题卡识别 + 看图阅卷；"
      "训练建议供参考，具体以老师指导为准。\n")
    return "\n".join(L)


def _extract_habits(per_q: dict, exam: ExamView) -> list[str]:
    """从全卷失分模式提炼**可改的具体行为**（程序，不依赖 LLM）。

    不止 errorType 计数，结合题型/连环错/多选漏选等模式。
    """
    from collections import Counter
    lost = [q for q in exam.questions if q.is_lost]
    et_q: dict[str, list[str]] = {}
    for q in lost:
        et = (per_q.get(q.num) or {}).get("errorType", "")
        if et:
            et_q.setdefault(et, []).append(q.qid)

    out = []
    # 1. 计算失误连环：多道计算/解答题因计算错失分
    calc_lost = [q.qid for q in lost
                 if q.type_cn in ("计算", "解答")
                 and "计算" in (per_q.get(q.num) or {}).get("errorType", "")]
    if len(calc_lost) >= 2:
        out.append(f"**计算链条脆弱**：{('、'.join(calc_lost))} 都因一个数据/单位错"
                   f"带崩整题——养成「每步代入后回看一眼、最终结果代回验证」的习惯")
    # 2. 多选求稳漏选
    multi_lost = [q.qid for q in lost if q.type_cn == "多选"]
    if multi_lost:
        out.append(f"**多选偏保守**：{('、'.join(multi_lost))} 漏选丢分——多选题"
                   f"对每个选项独立判断到底，别因「拿不准就不选」漏掉对的")
    # 3. 表述不规范（主观题高频）
    expr = et_q.get("表述不规范", [])
    if len(expr) >= 2:
        out.append(f"**结论不写到「点」上**：{('、'.join(expr))} 都因表述差关键词"
                   f"丢分——背standard结论模板，答主观题对照采分点逐条写")
    # 4. 兜底：errorType 高频
    if not out:
        for et, n in Counter(
                (per_q.get(q.num) or {}).get("errorType", "")
                for q in lost).most_common():
            if et and n >= 2:
                out.append(f"「{et}」出现 {n} 次，是本次最该改的习惯")
    return out


# ─── 主流程 ──────────────────────────────────────────────────────────────────

def build(student_dir: Path, standard: Path | None, skip_pdf: bool) -> Path:
    standard = standard or infer_standard(student_dir)
    if not standard or not standard.exists():
        print(f"❌ 找不到标准答案 yaml（试 --standard 指定）", file=sys.stderr)
        sys.exit(1)
    print(f"📄 试卷: {standard}")
    print(f"👤 学生目录: {student_dir}")

    exam = load_exam_view(standard, student_dir)
    lost = agg.lost_questions(exam)
    print(f"   {exam.student_name} {exam.exam_title}: "
          f"{exam.total_scored}/{exam.full_score}，失分题 {len(lost)} 道")

    slug = student_dir.name
    cache_prefix = f"report-v4-{exam.student_name}-{slug}"  # v4 同步 pipeline_adapter

    # 逐题归因（并发 + .cache）
    print(f"\n🧠 逐失分题归因（{len(lost)} 题，并发）...")
    per_q: dict[int, dict] = {}

    def _one(q: QView):
        return q.num, analyze.analyze_question(
            q, cache_key=f"{cache_prefix}-{q.qid}")

    with ThreadPoolExecutor(max_workers=6) as ex:
        for fut in as_completed([ex.submit(_one, q) for q in lost]):
            num, r = fut.result()
            per_q[num] = r
            print(f"   Q{num}: {r.get('errorType','?')}")

    # 整卷综合
    print(f"\n🧠 整卷综合诊断 ...")
    mods = agg.module_mastery(exam)
    rois = agg.module_roi(exam)
    diffs = agg.difficulty_breakdown(exam)
    kps = agg.lost_knowledge_points(exam)
    st = agg.overall_stats(exam)

    stats_block = (f"总分 {st['total_scored']}/{st['full_score']}"
                   f"（{st['rate']*100:.0f}%）；选择题 {st['choice_scored']}/"
                   f"{st['choice_full']}；非选择 {st['subj_scored']}/{st['subj_full']}；"
                   f"共失 {st['lost_total']} 分 {st['n_lost']} 题")
    module_block = "\n".join(
        f"- {m['module_cn']}：{m['scored']}/{m['full']}"
        f"（{m['rate']*100:.0f}%）失分题 {'、'.join(m['lost_qs']) or '无'}"
        for m in mods)
    # 提分 ROI 排序（按失分降序）—— 给 actionPlan 量化"补哪个模块挽回多少分"
    roi_block = "\n".join(
        f"- {r['module_cn']}：失 {r['lost']} 分（满分 {r['full']}，{r['n_questions']} 题，"
        f"得分率 {r['rate']*100:.0f}%）—— 补此模块预估可挽回最多 {r['lost']} 分"
        for r in rois if r['lost'] > 0) or "（无可挽回失分）"
    difficulty_block = "\n".join(
        f"- {d['difficulty']}：{d['n']} 题，得分率 {d['rate']*100:.0f}%，"
        f"失分 {'、'.join(d['lost_qs']) or '无'}" for d in diffs)
    kp_block = "\n".join(
        f"- {k['kp']}：失 {k['lost_total']} 分（{'、'.join(k['qs'])}）"
        for k in kps[:12]) or "（无失分知识点）"
    per_q_block = "\n".join(
        f"- {q.qid}（{q.type_cn} 失{q.lost}）："
        f"{per_q.get(q.num,{}).get('errorType','?')} / "
        f"{per_q.get(q.num,{}).get('whyWrong','')[:60]}"
        for q in lost)

    overall = analyze.analyze_overall(
        stats_block=stats_block, module_block=module_block,
        difficulty_block=difficulty_block, kp_block=kp_block,
        per_q_block=per_q_block, roi_block=roi_block,
        cache_key=f"{cache_prefix}-overall")

    # 渲染 + 输出
    md = render_markdown(exam, per_q, overall)
    # 交付物统一收口到 out/（REPO-LAYOUT 三层铁律）。
    # 路径用学生目录名（拼音 id）+ slug，学生中文名只进报告正文不进路径。
    out_dir = ROOT / "out" / "student-reports" / student_dir.parent.name / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"\n📝 Markdown → {md_path}")

    if not skip_pdf:
        pdf_path = md_path.with_suffix(".pdf")
        print(f"📄 调 md-to-pdf skill 出 PDF ...")
        r = subprocess.run(["bash", str(MD2PDF), str(md_path), str(pdf_path)],
                            capture_output=True, text=True)
        if r.returncode == 0:
            print(f"✅ PDF → {pdf_path}")
            return pdf_path
        print(f"⚠️ PDF 生成失败：{r.stderr[:300]}", file=sys.stderr)
    return md_path


def main():
    p = argparse.ArgumentParser(description="学情分析报告生成（学生向）")
    p.add_argument("--student-dir", required=True, type=Path,
                   help="students/<name>/<exam-slug>/")
    p.add_argument("--standard", type=Path,
                   help="试卷标准答案 yaml（不传则自动推断）")
    p.add_argument("--skip-pdf", action="store_true", help="只出 Markdown")
    args = p.parse_args()
    sd = args.student_dir.resolve()
    if not sd.is_dir():
        print(f"❌ 目录不存在: {sd}", file=sys.stderr); sys.exit(1)
    out = build(sd, args.standard.resolve() if args.standard else None,
                args.skip_pdf)
    print(f"\n🎉 完成: {out}")


if __name__ == "__main__":
    main()
