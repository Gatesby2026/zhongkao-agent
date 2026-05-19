#!/usr/bin/env bash
# 一次性：knowledge-base/mock-exams + exam-analysis
#   → knowledge-base/exams/{zhenti,mock,_staging,analysis}
# 原则：保持 figure 相对路径不变（figure_abs 相对 yaml 父目录解析），
#       零 yaml 数据改动；纯重定位。幂等、可 git 还原。
# 用法： bash migrate_exams_layout.sh [--dry]
set -u
DRY="${1:-}"
cd /Users/jiakui/projects/zhongkao-agent/knowledge-base
ME=mock-exams
mv_(){ # src dst
  [ -e "$1" ] || return 0
  if [ "$DRY" = "--dry" ]; then echo "  mv $1 → $2"; return 0; fi
  mkdir -p "$(dirname "$2")"; mv "$1" "$2"
}
is_zhenti(){ case "$1" in *-zhenti.yaml) return 0;; *) return 1;; esac; }

for s in chinese english math physics politics; do
  [ -d "$ME/$s/beijing" ] || continue
  # 1) yaml：按 zhenti/mock 拆
  for y in "$ME/$s/beijing"/*.yaml; do
    [ -e "$y" ] || continue
    f=$(basename "$y")
    if is_zhenti "$f"; then mv_ "$y" "exams/zhenti/$s/beijing/$f"
    else                    mv_ "$y" "exams/mock/$s/beijing/$f"; fi
  done
done

# 2) math 共享 figures：按文件名 slug 前缀拆 zhenti/mock
if [ -d "$ME/math/beijing/figures" ]; then
  for img in "$ME/math/beijing/figures"/*; do
    [ -e "$img" ] || continue
    b=$(basename "$img")
    case "$b" in
      *-zhenti-*|*-zhenti.*) mv_ "$img" "exams/zhenti/math/beijing/figures/$b" ;;
      *) mv_ "$img" "exams/mock/math/beijing/figures/$b" ;;
    esac
  done
  rmdir "$ME/math/beijing/figures" 2>/dev/null || true
fi

# 3) physics staging 目录：figures→final 旁，pages/layout-cache/structured-cloud→_staging
if [ -d "$ME/physics/beijing" ]; then
  for d in "$ME/physics/beijing"/*-yi; do
    [ -d "$d" ] || continue
    slug=$(basename "$d")
    [ -d "$d/figures" ] && mv_ "$d/figures" "exams/mock/physics/beijing/$slug/figures"
    for sub in pages layout-cache structured-cloud; do
      [ -e "$d/$sub" ] && mv_ "$d/$sub" "exams/_staging/physics/$slug/$sub"
    done
    rmdir "$d" 2>/dev/null || true
  done
fi

# 4) exam-analysis → exams/analysis
if [ -d exam-analysis ]; then
  for s in chinese english math physics politics; do
    [ -d "exam-analysis/$s" ] || continue
    mv_ "exam-analysis/$s" "exams/analysis/$s"
  done
  rmdir exam-analysis 2>/dev/null || true
fi

# 收尾：清空残骨架
[ "$DRY" = "--dry" ] || find "$ME" -type d -empty -delete 2>/dev/null
[ "$DRY" = "--dry" ] || rmdir "$ME" 2>/dev/null || true
echo "done${DRY:+ (dry-run)}"
