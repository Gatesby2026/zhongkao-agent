<script setup lang="ts">
// 非朝阳区:校库浏览。学校+专业(班)+位置,**暂无录取线→无法冲稳保**。
// 数据 /api/zhiyuan/district/{py}(派生自 bjeea 官方统招计划 OCR + 高德 GCJ-02 坐标)。
import { ref, computed, watch, onMounted, nextTick } from 'vue'
declare const L: any
const props = defineProps<{ py: string; cn: string }>()
const schools = ref<any[]>([])
const loading = ref(false)
const err = ref('')
const q = ref('')
let map: any = null, layer: any = null

function schoolNotes(s: any): string[] {
  const seen = new Set<string>()
  for (const m of (s.majors || [])) {
    const n = (m.note || "").trim()
    if (n) seen.add(n)
  }
  return [...seen]
}

const filtered = computed(() => {
  const s = q.value.trim()
  if (!s) return schools.value
  return schools.value.filter(x => x.name.includes(s)
    || (x.majors || []).some((m: any) => (m.major_name || '').includes(s))
    || String(x.school_code).includes(s))
})

async function load() {
  loading.value = true; err.value = ''; schools.value = []
  try {
    const r = await fetch(`/api/zhiyuan/district/${props.py}`)
    const d = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)
    schools.value = d.schools || []
    await nextTick(); renderMap()
  } catch (e: any) {
    err.value = '加载失败：' + (e.message || e)
  } finally {
    loading.value = false
  }
}

function renderMap() {
  const pts = schools.value.filter(s => s.lat && s.lon)
  if (typeof L === 'undefined' || !document.getElementById('db-map')) return
  if (!map) {
    map = L.map('db-map', { zoomControl: true, scrollWheelZoom: false })
      .setView(pts.length ? [pts[0].lat, pts[0].lon] : [39.9, 116.4], 11)
    L.tileLayer('https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}',
      { subdomains: ['1', '2', '3', '4'], tileSize: 128, zoomOffset: 1, maxZoom: 18, attribution: '高德地图' }).addTo(map)
  }
  if (layer) layer.remove()
  layer = L.layerGroup().addTo(map)
  const bb: any[] = []
  for (const s of pts) {
    const mk = L.circleMarker([s.lat, s.lon], { radius: 6, color: '#fff', weight: 2, fillColor: '#2563eb', fillOpacity: .85 }).addTo(layer)
    mk.bindPopup(`<b>${s.name}</b><br><span style="color:#888">码 ${s.school_code}</span><br>${(s.majors || []).map((m: any) => m.major_code + ' ' + m.major_name).join('<br>') || '专业以官方网报为准'}`)
    bb.push([s.lat, s.lon])
  }
  if (bb.length) { try { map.fitBounds(bb, { padding: [30, 30] }) } catch { /* */ } setTimeout(() => map.invalidateSize(), 60) }
}

watch(() => props.py, load)
onMounted(load)
</script>

<template>
  <div class="db">
    <div class="db-banner">
      📚 <b>{{ cn }}区 · 校库</b>（共 {{ schools.length }} 所）：可<b>查校 / 看专业(班) / 看位置</b>。
      <b class="db-warn">⚠️ 该区暂无录取线/位次，无法做冲稳保推荐</b>——录取线需各区一分一段，待出分后补。
      想要冲稳保，请切回<b>朝阳</b>。
    </div>
    <input v-model="q" class="db-search" placeholder="搜学校名 / 专业 / 代码…" />
    <p v-if="loading" class="db-tip">加载中…</p>
    <p v-if="err" class="db-tip err">{{ err }}</p>

    <div id="db-map" class="db-map"></div>

    <div class="db-list">
      <div v-for="s in filtered" :key="s.school_code" class="db-row">
        <div class="db-r1">
          <span class="db-name">{{ s.name }}</span>
          <span class="db-code">{{ s.school_code }}</span>
          <span v-if="!s.lat" class="db-nocoord">无坐标</span>
        </div>
        <div class="db-majors">
          <span v-for="m in s.majors" :key="m.major_code" class="db-mchip"><b>{{ m.major_code }}</b> {{ m.major_name }}<small v-if="m.plan_total"> ·{{ m.plan_total }}人</small></span>
          <span v-if="!(s.majors && s.majors.length)" class="db-nomaj">专业(班)以官方网报为准</span>
        </div>
        <div v-for="(n, i) in schoolNotes(s)" :key="i" class="db-note">📋 {{ n }}</div>
      </div>
      <p v-if="!loading && !filtered.length" class="db-tip">无匹配学校。</p>
    </div>
    <p class="db-src">数据：计划数派生自《2026 北京中招大报纸》官方招生简章（学校代码/专业·T1）+ 高德坐标。一切以当年官方网报与简章为准。</p>
  </div>
</template>

<style scoped>
.db { padding: 4px 0 16px; }
.db-banner { background: var(--warning-bg); border: 1px solid var(--accent); border-radius: var(--radius-sm);
  font-size: 12.5px; line-height: 1.7; color: var(--gray-800); padding: 10px 12px; margin: 8px 0 12px; }
.db-warn { color: #b45309; }
.db-search { width: 100%; box-sizing: border-box; padding: 9px 12px; font-size: 14px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-sm); margin-bottom: 10px; }
.db-map { height: 300px; border-radius: var(--radius-sm); overflow: hidden; margin-bottom: 12px; border: 1px solid var(--gray-200); }
.db-list { display: flex; flex-direction: column; gap: 6px; }
.db-row { border: 1px solid var(--gray-100); border-radius: var(--radius-sm); background: var(--surface); padding: 8px 10px; }
.db-r1 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.db-name { font-size: 13.5px; font-weight: 600; color: var(--gray-800); }
.db-code { font-size: 11px; color: var(--gray-400); }
.db-nocoord { font-size: 10.5px; color: var(--gray-400); background: var(--gray-100); border-radius: var(--radius-xs); padding: 0 5px; }
.db-majors { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.db-mchip { font-size: 11.5px; padding: 2px 8px; border-radius: var(--radius-xs); background: var(--brand-50); color: var(--brand-dark); }
.db-mchip b { color: var(--brand-dark); }
.db-mchip small { color: var(--gray-500); }
.db-nomaj { font-size: 11.5px; color: var(--gray-400); }
.db-note { font-size: 11px; color: var(--gray-500); line-height: 1.55; margin-top: 5px;
  padding: 5px 8px; background: var(--gray-50); border-radius: var(--radius-xs); }
.db-tip { font-size: 12.5px; color: var(--gray-500); margin: 6px 0; }
.db-tip.err { color: var(--error); }
.db-src { font-size: 11px; color: var(--gray-400); margin-top: 12px; }
</style>
