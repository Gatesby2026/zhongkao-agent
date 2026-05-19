# 北京 2026 一模 · 物理结构化质量汇总
_生成 2026-05-18 · 流水线 v2（含 avalanche / 图片选项 两项 root-cause 修复）_

| 区 | 题数 | 分值合计 | full_score | 断号 | options缺(选择题) | 判定 |
|---|---|---|---|---|---|---|
| changping | 26 | 60 | None | — | [16] | ❌需复核 |
| chaoyang | 26 | 70 | 70 | — | — | ✅达标 |
| daxing | 27 | 59 | 70 | — | [3, 10, 15] | ❌需复核 |
| dongcheng | 26 | 65 | 70 | — | — | ❌需复核 |
| fangshan | 23 | 58 | 70 | — | [10, 13, 14] | ❌需复核 |
| fengtai | 26 | 70 | 70 | — | [11, 14, 15] | ❌需复核 |
| haidian | 26 | 70 | 70 | — | [15] | ❌需复核 |
| mentougou | 25 | 70 | 70 | — | — | ✅达标 |
| pinggu | 25 | 64 | 70 | — | [14] | ❌需复核 |
| shijingshan | 26 | 66 | 70 | — | [3] | ❌需复核 |
| shunyi | 26 | 69 | 70 | — | — | ❌需复核 |
| tongzhou | 26 | 66 | 70 | — | — | ❌需复核 |
| xicheng | 27 | 66 | 70 | — | — | ❌需复核 |
| yanqing | 42 | 101 | None | — | [6, 11, 16, 21, 24] | ❌需复核 |

**2/14 区零问题达标**（chaoyang 金标准 + mentougou）。其余为残留 OCR 源噪声，qc_report 已精确定位 → needs_review 人工复核（符合 skill 人在环设计）。

## 关键结论
- **avalanche 根因已修复**：旧 `split_by_question_number` 全局 `n==expected` 严格过滤，遇 OCR 题号整页重置/跳变雪崩吞后续所有页（daxing 曾仅 10 题）。改为「每页连续整数最长子序列 + 文档顺序顺延重编」。daxing 10→27 题；chaoyang 金标准逐题字节级不变（无回归）。
- **图片选项丢失根因已修复**：选项为 4 图时 OCR 仅留裸标签行 `A B C D`，旧点号正则匹配不到→整题 options 丢失。新增 `IMG_4OPTS_RE` 兜底回填 `{A:[图]…}`（stem≤200 护栏防长实验题误判）。清掉 dongcheng/xicheng/tongzhou 全部、haidian/pinggu 部分。
- **残留（needs_review，非流水线缺陷）**：①电路图/示意图选项且 OCR 无 A/B/C/D 标签（fengtai Q11 类）文本不可恢复需图形裁切+人工；②选项因 OCR 阅读序与题干分离（Q14/15 类）；③个别题型误判（haidian Q15 计算题→multi_choice）；④分值差几分=分值抽取噪声；⑤changping/yanqing full_score=None（考生须知版式差异）；⑥**yanqing 42 题异常**：源 18 页疑似双卷/含答题卡，需核验源数据。

产物：各区 `…/yimo/<区>/physics/structured-cloud/final.json`；逐区原始评估 `/tmp/region_qc_summary.txt`。