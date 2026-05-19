#!/usr/bin/env bash
# 批量结构化北京一模物理卷 + 每份质量评估。
# 路径分离（见 docs/specs/KB-LAYOUT.md）：
#   原始件   knowledge-original/beijing-mock-2026/yimo/<区>/physics/images/
#   派生中间 knowledge-base/exams/_staging/physics/2026-<区>-yi/
#            （pages / layout-cache / structured-cloud；figures 由 enrich 复制到最终件旁）
#   最终件   knowledge-base/exams/mock/physics/beijing/2026-<区>-yi.yaml
# out-dir 由 ocr_paper / qc_report 经 paths.derive_out_dir 自动映射，
# 本脚本仅复算 slug 用于清缓存 + 定位 qc 目标。
set -u
export DASHSCOPE_API_KEY=sk-269db71be27b4dcfbedb0c21c382d288
ROOT=/Users/jiakui/projects/zhongkao-agent
cd "$ROOT"
SRC_BASE=knowledge-original/beijing-mock-2026/yimo
STAGING_BASE=knowledge-base/exams/_staging/physics
SUMMARY="knowledge-base/exams/mock/physics/beijing/region_qc_summary.txt"
mkdir -p "$STAGING_BASE" "$(dirname "$SUMMARY")"
: > "$SUMMARY"

REGIONS="chaoyang daxing dongcheng fangshan fengtai haidian xicheng changping mentougou pinggu shijingshan shunyi tongzhou yanqing"

for r in $REGIONS; do
  src="$SRC_BASE/$r/physics"
  out="$STAGING_BASE/2026-$r-yi"
  echo "######## $r ########"
  rm -f "$out/structured-cloud/final.json" "$out/structured-cloud/final.md"
  python3 scripts/exam-ocr/ocr_paper.py "$src" --subject physics \
    --pipeline v2 2>&1 | tail -3
  echo "---- qc $r ----"
  python3 scripts/exam-ocr/qc_report.py "$out" 2>&1 | tee -a "$SUMMARY"
  echo "" >> "$SUMMARY"
done

echo "ALL DONE → $SUMMARY"
