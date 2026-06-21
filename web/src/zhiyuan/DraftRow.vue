<script setup lang="ts">
// 只读志愿行：②校额 / ②统筹 / ③统招 共用。由各自 adapter 归一成同一 view-model 后渲染。
// 行1=序号+校名+meta(代码/统筹几/新校预测)+档位徽标；行2=专业(班)；行3=理由(headline+因子+⚠️风险)
interface MajorVM { code: string; name?: string }
defineProps<{
  seq: number
  name: string
  meta?: string
  band?: { label: string; cls: string }
  majors?: MajorVM[]
  majorsNote?: string
  headline?: string
  factors?: string[]
  risk?: string
}>()
</script>

<template>
  <div class="uslot ro">
    <div class="ro-row1">
      <span class="slot-no on">{{ seq }}</span>
      <span class="ro-name">{{ name }}</span>
      <span v-if="meta" class="ro-meta">{{ meta }}</span>
      <span v-if="band" class="ro-band" :class="band.cls">{{ band.label }}</span>
    </div>
    <div class="ro-major-line">
      <span class="lbl">专业(班)</span>
      <span v-for="m in (majors || [])" :key="m.code" class="ro-mchip"><b>{{ m.code }}</b> {{ m.name }}</span>
      <span v-if="!(majors && majors.length)" class="nomajor">{{ majorsNote || '以官方网报为准' }}</span>
    </div>
    <div v-if="headline" class="ro-rsn">
      <span class="ur-head">{{ headline }}</span>
      <span v-for="(f, i) in (factors || [])" :key="i" class="ur-f">{{ f }}</span>
      <span v-if="risk" class="ur-risk">⚠️ {{ risk }}</span>
    </div>
  </div>
</template>

<style scoped>
.uslot.ro { background: var(--surface); border: 1px solid var(--gray-100); border-radius: var(--radius-sm); padding: 8px 10px; }
.ro-row1 { display: flex; align-items: center; gap: 8px; min-width: 0; }
.slot-no { flex: 0 0 auto; width: 22px; height: 22px; border-radius: 50%; font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; background: var(--gray-200); color: var(--gray-500); }
.slot-no.on { background: var(--brand); color: #fff; }
.ro-name { font-size: 13.5px; font-weight: 600; color: var(--gray-800); min-width: 0; }
.ro-meta { font-size: 11px; color: var(--gray-400); flex: 0 0 auto; }
.ro-band { margin-left: auto; flex: 0 0 auto; font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: var(--radius-full); }
.ro-major-line { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding-left: 30px; margin-top: 6px; }
.ro-major-line .lbl { font-size: 11px; color: var(--gray-400); }
.ro-rsn { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding-left: 30px; margin-top: 5px;
  font-size: 12px; color: var(--gray-600); line-height: 1.55; }
.ro-mchip { font-size: 11.5px; padding: 2px 8px; border-radius: var(--radius-xs); background: var(--brand-50); color: var(--brand-dark); }
.ro-mchip b { color: var(--brand-dark); }
.nomajor { font-size: 11.5px; color: var(--gray-400); }
.ur-head { color: var(--gray-700); }
.ur-f { font-size: 11px; color: var(--gray-600); background: var(--gray-100); border-radius: var(--radius-xs); padding: 1px 6px; }
.ur-risk { font-size: 11px; color: #b45309; background: var(--warning-bg); border-radius: var(--radius-xs); padding: 1px 6px; }
/* 档位徽标配色（与父级 us-b 摘要一致）*/
.band-冲 { background: #fde8e6; color: #c0392b; }
.band-稳 { background: #fdf3d4; color: #9a7d0a; }
.band-保 { background: #d8f5e3; color: #1e8e4e; }
.band-刺 { background: #ede7f6; color: #6a1b9a; }
.band-够不上 { background: var(--gray-100); color: var(--gray-400); }
</style>
