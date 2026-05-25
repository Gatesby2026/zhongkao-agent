#!/usr/bin/env python3
"""politics-inspect — 道法 yaml 质量自动检查（对齐 chinese/physics inspect 风格）

检查项：
- 题数 25（容忍 22-28）
- 满分 70（容忍 60-100：部分区可能改革后含 80）
- 题型分布：judge ≥ 8 / choice ≥ 8 / material ≥ 3
- judge 答案 ∈ {正确, 错误, √, ×, 对, 错}
- choice 答案 ∈ {A,B,C,D} 单字母或多选
- 空 stem / 空答案 / 空 sol (按 type 容忍)
- 缺 KP
"""
import yaml, glob, sys, re
from pathlib import Path

JUDGE_OK = {"正确", "错误", "√", "×", "对", "错"}


def inspect_one(yaml_path: Path) -> dict:
    d = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    qs = d.get("questions", [])
    stats = {
        "n_q": len(qs),
        "sum_score": sum(q.get("score", 0) for q in qs),
        "full_score": d.get("full_score", 0),
        "n_judge": 0, "n_choice": 0, "n_material": 0, "n_essay": 0,
        "n_other_type": 0,
        "empty_stem": 0, "empty_ans": 0, "bad_judge_ans": 0,
        "bad_choice_ans": 0, "short_sol": 0, "no_kp": 0,
        "missing_ids": [],
    }
    ids = {q.get("id") for q in qs}
    stats["missing_ids"] = sorted(set(range(1, stats["n_q"]+1)) - ids)
    for q in qs:
        t = q.get("type", "")
        if t == "判断": stats["n_judge"] += 1
        elif t == "单选" or t == "choice": stats["n_choice"] += 1
        elif t == "材料分析": stats["n_material"] += 1
        elif t in ("写作", "作文"): stats["n_essay"] += 1
        else: stats["n_other_type"] += 1

        stem = (q.get("stem") or "").strip()
        ans = (q.get("answer") or "").strip()
        sol = (q.get("solution") or "").strip()
        kps = q.get("knowledge_points") or []

        if not stem: stats["empty_stem"] += 1
        if t == "判断":
            if ans not in JUDGE_OK: stats["bad_judge_ans"] += 1
        elif t in ("单选", "choice"):
            if not re.fullmatch(r"[A-D]{1,4}", ans): stats["bad_choice_ans"] += 1
        elif t in ("材料分析", "写作", "作文"):
            # 主观题：答案在 sol 里；若 sol 也短才报警
            if len(sol) < 30: stats["short_sol"] += 1
            if not ans and not sol: stats["empty_ans"] += 1
        if not kps: stats["no_kp"] += 1
    return stats


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else \
        "knowledge-base/exams/mock/politics/beijing/2026-*-yi.yaml"
    paths = sorted(Path(".").glob(pattern))
    if not paths:
        print(f"no match: {pattern}"); sys.exit(1)

    print(f'{"district":<14}{"Q#":>4}{"sum":>5}{"full":>5}'
          f'{"jdg":>5}{"chc":>5}{"mat":>5}{"esy":>5}'
          f'{"badJ":>6}{"badC":>6}{"shtS":>6}{"miss":>20}')
    print('-' * 110)
    totals = {"n_q":0, "sum_score":0, "n_judge":0, "n_choice":0,
              "n_material":0, "n_essay":0, "bad_judge_ans":0,
              "bad_choice_ans":0, "short_sol":0, "no_kp":0}
    warns = []
    for p in paths:
        s = inspect_one(p)
        region = p.stem.replace("2026-", "").replace("-yi", "")
        miss = ",".join(str(x) for x in s["missing_ids"][:6])
        print(f'{region:<14}{s["n_q"]:>4}{s["sum_score"]:>5}'
              f'{s["full_score"]:>5}{s["n_judge"]:>5}{s["n_choice"]:>5}'
              f'{s["n_material"]:>5}{s["n_essay"]:>5}'
              f'{s["bad_judge_ans"]:>6}{s["bad_choice_ans"]:>6}'
              f'{s["short_sol"]:>6}{miss:>20}')
        for k in totals: totals[k] += s.get(k, 0)
        # 警告：满分不是 70
        if s["full_score"] != 70: warns.append(f"  {region}: full_score={s['full_score']} ≠ 70")
        if s["n_q"] not in (24, 25, 26): warns.append(f"  {region}: n_q={s['n_q']} 不在 [24,26]")
        if s["bad_judge_ans"]: warns.append(f"  {region}: {s['bad_judge_ans']} 个 judge 答案不合规")
        if s["bad_choice_ans"]: warns.append(f"  {region}: {s['bad_choice_ans']} 个 choice 答案不合规")
    print()
    print(f'合计 {len(paths)} 区 {totals["n_q"]} 题')
    print(f'  judge={totals["n_judge"]} choice={totals["n_choice"]}'
          f' material={totals["n_material"]} essay={totals["n_essay"]}')
    print(f'  badJ={totals["bad_judge_ans"]} badC={totals["bad_choice_ans"]}'
          f' shtS={totals["short_sol"]} noKP={totals["no_kp"]}')
    if warns:
        print("\n⚠ 警告:")
        for w in warns: print(w)


if __name__ == "__main__":
    main()
