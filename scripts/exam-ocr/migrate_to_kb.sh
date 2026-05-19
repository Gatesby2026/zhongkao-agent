#!/usr/bin/env bash
# [已完成·勿再运行] 历史一次性脚本，路径基于旧 mock-exams 布局，已被
# migrate_exams_layout.sh + KB-LAYOUT 阶段1 取代。仅留作历史参考。
# 一次性迁移：把已生成的派生件从 knowledge-original 移到 knowledge-base staging，
# 并删除 knowledge-original 下的旧派生件（images/ 等原始件原地保留）。
# 幂等：可重复跑；目标已存在则 rsync 合并后删源。
set -u
ROOT=/Users/jiakui/projects/zhongkao-agent
cd "$ROOT"
SRC_BASE=knowledge-original/beijing-mock-2026/yimo
KB_BASE=knowledge-base/mock-exams/physics/beijing
DERIVED="pages layout-cache structured-cloud figures"
REGIONS="chaoyang daxing dongcheng fangshan fengtai haidian xicheng changping mentougou pinggu shijingshan shunyi tongzhou yanqing"

for r in $REGIONS; do
  src="$SRC_BASE/$r/physics"
  out="$KB_BASE/2026-$r-yi"
  [ -d "$src" ] || { echo "skip $r：无 $src"; continue; }
  mkdir -p "$out"
  for sub in $DERIVED; do
    s="$src/$sub"
    d="$out/$sub"
    [ -e "$s" ] || continue
    if [ ! -e "$d" ]; then
      mv "$s" "$d"
      echo "  mv  $r/$sub → $out/"
    else
      rsync -a "$s/" "$d/" && rm -rf "$s"
      echo "  merge+rm  $r/$sub → $out/"
    fi
  done
done

# 旧聚合报告迁移
for old in "$SRC_BASE/QC_SUMMARY_physics.md" \
           "knowledge-original/beijing-mock-2026/QC_SUMMARY_physics.md"; do
  [ -f "$old" ] && mv "$old" "$KB_BASE/QC_SUMMARY_physics.md" \
    && echo "  mv  $old → $KB_BASE/"
done

echo "迁移完成。原始件保留："
ls "$SRC_BASE"/daxing/physics 2>/dev/null
echo "派生件现位于：$KB_BASE/2026-<区>-yi/"
