<script setup lang="ts">
// 统一研判口径图例(位次口径·公办统招 / 市级统筹同一套档)。compact=只显示色块行。
defineProps<{ rank?: number | string | null; compact?: boolean }>()
</script>

<template>
  <p class="jl" :class="{ compact }">
    <template v-if="!compact"><b>研判口径(位次)</b>：你区排 <b>{{ rank }}</b> 名 与各校 <b>2026 预估录取位次</b>比，领先门槛越多越稳。</template>
    <span class="tj tj-wen">保</span>领先门槛≥15%
    <span class="tj tj-wen">稳</span>领先0–15%
    <span class="tj tj-chong">冲</span>落后≤25%
    <span class="tj tj-no">够不上</span>落后&gt;25%
    <span class="tj tj-unk">待核</span>无线
    <template v-if="!compact"><br><b>公办统招 / 市级统筹同一套档</b>（同一相对位置=同一档，不再有"搏"）。统筹另注：<b>录取即锁定</b>、只填"够一够的 upgrade"；<b>校额到校</b>是另一维度（看校内排名、判"值不值得用"，不在此位次档）。</template>
  </p>
</template>

<style scoped>
.jl { font-size: 11.5px; line-height: 1.8; color: #4b5563; background: #f3f4f6; border-radius: 6px; padding: 8px 10px; margin: 8px 0 0; }
.jl.compact { background: none; padding: 0; margin: 0; line-height: 1.6; }
.tj { display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 999px; white-space: nowrap; margin: 0 1px; }
.tj-wen { background: #eafaf1; color: #1e8449; }
.tj-chong { background: #fdecea; color: #c0392b; }
.tj-no { background: #eceef1; color: #6b7280; }
.tj-unk { background: #eaf2f8; color: #2471a3; }
</style>
