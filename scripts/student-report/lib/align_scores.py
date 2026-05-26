"""xlsx 小分（班小二）题号 → yaml(KB) 题号 对齐。

班小二 xlsx 与 KB yaml 经常用**不同的题号体系**给同一份卷子：
  - 默写：yaml 合并成 1 题（Q8=4分），xlsx 拆 3 空（Q8/Q9/Q10 各 1+1+2 分）
  - 二选一作文：yaml 单 Q25=40分（外加 Q26 占位 0 分），xlsx 列两选项 Q27_1/Q27_2 各 40
  - 中段题号漂移：每题分值与切分两侧不一一对应，但**段落性"累加和"相等**

对策：按顺序双指针走 yaml 与 xlsx items，找累加满分相等的最小窗口
（"块"），块内按 yaml 各题的 full 占比把 xlsx 实得分按比例分摊；
每个 yaml 题挂上 subScores（原 xlsx 行明细），需要时可在报告里展开。

约束：xlsx examTotal、yaml total_full 一致是隐含前提；块对齐失败的位置
回退为 _alignmentMiss + 默认满分占位（与 schemas 缺失默认一致）。
"""
from __future__ import annotations

import re


def _qnum(qid) -> int:
    m = re.search(r"\d+", str(qid))
    return int(m.group(0)) if m else 0


def _norm_num(x) -> float:
    """xlsx scored 偶为 '-'（二选一未选），按 0 处理。"""
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def align(items: list[dict], yaml_qs: list[dict]) -> tuple[dict[int, dict], list[str]]:
    """累加块匹配。

    返回：
      aligned: {yaml_qnum: {scored, fullScore, subScores:[{xlsxQid,scored,fullScore,desc}],
                            _alignmentMiss?: bool}}
      warnings: 对齐警告字符串列表
    """
    # 跳过 yaml.full=0 的占位题（二选一备份），不消费 xlsx
    yaml_eff = [(q, _qnum(q.get("id")), float(q.get("score", 0) or 0))
                for q in yaml_qs]
    aligned: dict[int, dict] = {}
    warnings: list[str] = []
    i = j = 0  # i: yaml index, j: xlsx items index
    n_y, n_x = len(yaml_eff), len(items)

    while i < n_y:
        q, ynum, yfull = yaml_eff[i]
        # full=0 题：直接登记 0/0，不消费 xlsx
        if yfull <= 0:
            aligned[ynum] = {"scored": 0.0, "fullScore": 0.0,
                             "subScores": [], "_skipped": True}
            i += 1
            continue
        # 从当前 j 开始累加 xlsx，与 yaml 当前及后续累加比较
        ys = yfull
        yi = i + 1                          # yaml 累加到的下一个位置
        xs = 0.0
        xj = j
        # 优先尝试小窗口（仅吃 yaml 这一题）
        while xj < n_x and xs < ys - 1e-3:
            xs += float(items[xj]["fullScore"])
            xj += 1
        # 若 xlsx 累加 > yaml，继续吃后续 yaml 题直到两边相等
        while xs > ys + 1e-3 and yi < n_y:
            ys += yaml_eff[yi][2]
            yi += 1
            while xj < n_x and xs < ys - 1e-3:
                xs += float(items[xj]["fullScore"])
                xj += 1

        if abs(xs - ys) > 0.1:
            # 对齐失败：xlsx 走到尽头或永远凑不上 → 当前 yaml 题用满分占位
            warnings.append(
                f"Q{ynum} 起 yaml累加={ys} xlsx累加={xs} 无法对齐")
            aligned[ynum] = {"scored": yfull, "fullScore": yfull,
                             "subScores": [], "_alignmentMiss": True}
            i += 1
            continue

        block_yaml = yaml_eff[i:yi]                     # 这一块 yaml 题
        block_xlsx = items[j:xj]                        # 这一块 xlsx 行
        block_scored = sum(_norm_num(x.get("scored")) for x in block_xlsx)
        block_full = sum(yf for _, _, yf in block_yaml)

        if len(block_yaml) == 1:
            # 1:N（含 1:1）—— 整块算一题，subScores 全挂上
            scored = min(yfull, block_scored)
            aligned[ynum] = {
                "scored": round(scored, 2),
                "fullScore": yfull,
                "subScores": block_xlsx,
            }
        else:
            # M:N —— 按 yaml.full 占比把 block_scored 分摊；subScores 共享整块
            for q2, yn2, yf2 in block_yaml:
                share = block_scored * (yf2 / block_full) if block_full else 0
                aligned[yn2] = {
                    "scored": round(min(yf2, share), 2),
                    "fullScore": yf2,
                    "subScores": block_xlsx,        # 整块共享
                    "_blockShared": True,            # 标记此题与同块他题共享 subScores
                }
        i, j = yi, xj

    return aligned, warnings
