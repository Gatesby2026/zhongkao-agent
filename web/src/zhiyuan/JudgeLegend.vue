<script setup lang="ts">
// 统一研判口径图例（公办统招 / 市级统筹共用 Δ 口径）。compact=只显示色块行。
defineProps<{ rank?: number | string | null; est?: number | null; compact?: boolean }>()
</script>

<template>
  <p class="jl" :class="{ compact }">
    <template v-if="est != null && !compact"><b>研判口径</b>：你区排 <b>{{ rank }}</b> 名 → 一分一段估分 <b>≈{{ est }}</b>，与各校 <b>2025 统招线</b>比（Δ=估分−线）。</template>
    <span class="tj tj-wen">稳</span>Δ≥+10
    <span class="tj tj-chong">冲</span>−10~+10
    <span class="tj tj-bo">搏</span>−20~−10
    <span class="tj tj-no">够不上</span>Δ&lt;−20
    <span class="tj tj-unk">待核</span>无公开线
    <template v-if="!compact"><br><b>公办统招 / 市级统筹共用此口径</b>。统筹比的是各校<b>统招线</b>（统筹实际线官方不公开、通常更低，故偏保守——"够不上"才基本无望，"冲"档实际机会更大）。<b>历年线</b>=单源/历年参考；新校无历史则"待核"。</template>
  </p>
</template>

<style scoped>
.jl { font-size: 11.5px; line-height: 1.8; color: #4b5563; background: #f3f4f6; border-radius: 6px; padding: 8px 10px; margin: 8px 0 0; }
.jl.compact { background: none; padding: 0; margin: 0; line-height: 1.6; }
.tj { display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 999px; white-space: nowrap; margin: 0 1px; }
.tj-wen { background: #eafaf1; color: #1e8449; }
.tj-bo { background: #fef5e7; color: #b9770e; }
.tj-chong { background: #fdecea; color: #c0392b; }
.tj-no { background: #eceef1; color: #6b7280; }
.tj-unk { background: #eaf2f8; color: #2471a3; }
</style>
