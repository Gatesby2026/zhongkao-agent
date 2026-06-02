<script setup lang="ts">
import { ref, reactive, nextTick } from 'vue'

declare const L: any

const INTEREST_TAGS = [
  '理科见长', '科技创新', '外语特色', '文科人文', '艺术特长',
  '体育特长', '国际方向', '课程改革', '学科竞赛', '综合均衡', '寄宿制',
]
const MODES = [
  { v: 'driving', label: '驾车' },
  { v: 'transit', label: '公交' },
  { v: 'bicycling', label: '骑行' },
  { v: 'walking', label: '步行' },
]
const BAND_COLOR: Record<string, string> = { 冲: '#e74c3c', 稳: '#f1c40f', 保: '#2ecc71' }
const BAND_DESC: Record<string, string> = {
  冲: '略低于录取线，冲一冲',
  稳: '略高于录取线，比较稳',
  保: '明显高于录取线，保底',
}

interface Card {
  name: string; level: string; note: string; ref_rank: number | string
  margin: number; margin_pct: string; volatility: number
  history: [number, number][]
  nearest: { campus: string; km: number; mins: number; over_max: boolean } | null
  style: string; tags: string[]; gaokao: string; matched: string[]
}
interface Point {
  name: string; lat: number; lon: number; kind: string; color: string
  band: string; level: string; rank: string; margin: string; dist: string
  hist: string; note: string; reason: string; style: string
  tags: string[]; gaokao: string; matched: string[]
}
interface Result {
  district: string; rank: number; home: string | null
  home_coord: [number, number] | null; mode: string; mode_label: string
  max_km: number | null; interests: string[] | null
  bands: Record<string, Card[]>; points: Point[]; private: Point[]
}

const form = reactive({
  rank: 5000,
  home: '',
  mode: 'driving',
  max_km: '' as number | string,
  interests: [] as string[],
})
const loading = ref(false)
const errMsg = ref('')
const result = ref<Result | null>(null)
let mapInst: any = null

function toggleInterest(t: string) {
  const i = form.interests.indexOf(t)
  if (i >= 0) form.interests.splice(i, 1)
  else form.interests.push(t)
}

async function submit() {
  errMsg.value = ''
  if (!form.rank || form.rank < 1) { errMsg.value = '请填写有效的区排名'; return }
  loading.value = true
  try {
    const body: any = {
      rank: Number(form.rank),
      mode: form.mode,
      interests: form.interests.length ? form.interests : null,
    }
    if (form.home.trim()) body.home = form.home.trim()
    if (form.max_km !== '' && Number(form.max_km) > 0) body.max_km = Number(form.max_km)
    const r = await fetch('/api/zhiyuan/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    result.value = await r.json()
    await nextTick()
    renderMap()
  } catch (e: any) {
    errMsg.value = '推荐失败：' + e.message
  } finally {
    loading.value = false
  }
}

function popupHtml(p: Point): string {
  let h = `<div class="pop"><b>${p.name}</b> <span style="color:${p.color}">[${p.band}]</span>`
  if (p.matched && p.matched.length) h += ` <span style="color:#16a085">🎯${p.matched.join('·')}</span>`
  let m = `<div class="meta">${p.level}`
  if (p.rank !== '—') m += ` ｜ 录取位次≈${p.rank}名 (margin ${p.margin})`
  m += `<br>通勤 ${p.dist}`
  if (p.style) m += `<br>🏫 ${p.style}`
  if (p.tags && p.tags.length) m += '<br>' + p.tags.map(t => '#' + t).join(' ')
  if (p.gaokao) m += `<br>🎓 高考(民间·非官方)：${p.gaokao}`
  if (p.hist) m += `<br>${p.hist}`
  if (p.note) m += `<br>${p.note}`
  if (p.reason) m += `<br>🚫 <b style="color:#c0392b">不在报名范围：</b>${p.reason}`
  return h + m + '</div></div>'
}

function pin(color: string, txt: string) {
  return L.divIcon({
    className: '', iconSize: [34, 34], iconAnchor: [17, 34],
    html: `<div style="background:${color};width:34px;height:34px;border-radius:50% 50% 50% 0;`
      + `transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);`
      + `display:flex;align-items:center;justify-content:center;">`
      + `<span class="lbl" style="transform:rotate(45deg)">${txt}</span></div>`,
  })
}
function smallIcon(color: string) {
  return L.divIcon({
    className: '', iconSize: [14, 14], iconAnchor: [7, 7],
    html: `<div style="background:${color};width:14px;height:14px;border-radius:50%;`
      + `border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4);opacity:.9"></div>`,
  })
}

function renderMap() {
  const res = result.value
  if (!res || !res.home_coord) return
  if (mapInst) { mapInst.remove(); mapInst = null }
  const HOME = res.home_coord
  const map = L.map('zmap', { zoomControl: false }).setView(HOME, 12)
  mapInst = map
  L.control.zoom({ position: 'topright' }).addTo(map)
  L.tileLayer('https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}',
    { subdomains: ['1', '2', '3', '4'], maxZoom: 18, attribution: '高德地图' }).addTo(map)

  L.marker(HOME, { icon: pin('#2c3e50', '家'), zIndexOffset: 1000 }).addTo(map)
    .bindPopup(`<div class="pop"><b>家</b><br>${res.home || ''}</div>`)

  const bounds: any[] = [HOME]
  const publicLayer = L.layerGroup().addTo(map)
  res.points.forEach((p) => {
    bounds.push([p.lat, p.lon])
    const icon = p.kind === 'full' ? pin(p.color, p.band) : smallIcon(p.color)
    L.marker([p.lat, p.lon], { icon }).addTo(publicLayer).bindPopup(popupHtml(p))
  })
  const privateLayer = L.layerGroup()
  res.private.forEach((p) => {
    L.marker([p.lat, p.lon], { icon: smallIcon(p.color) }).addTo(privateLayer).bindPopup(popupHtml(p))
  })
  L.control.layers(null, {
    '统招公办（含够不上/超通勤）': publicLayer,
    '民办/国际校': privateLayer,
  }, { position: 'topright', collapsed: false }).addTo(map)
  map.fitBounds(bounds, { padding: [50, 50] })
}

function distTxt(c: Card): string {
  if (!c.nearest) return ''
  const n = c.nearest
  const campus = n.campus ? `${n.campus} ` : ''
  const over = n.over_max ? ' ⚠️超通勤上限' : ''
  return `📍${campus}${result.value?.mode_label || ''}${n.km}km/${n.mins}分钟${over}`
}
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>北京中考志愿参考 · 朝阳</h1>
      <p class="sub">按区排名做冲稳保匹配，叠加通勤路网距离与学校特色。仅辅助参考，最终以官方招生简章与老师建议为准。</p>
    </header>

    <div class="disclaimer">
      ⚠️ 高考成绩为<b>民间·非官方</b>数据（网传喜报等），仅作录取位次的补充参考，<b>不作为独立维度</b>，请勿据此直接决策。
    </div>

    <section class="card form">
      <div class="row">
        <label>孩子区排名
          <input type="number" v-model.number="form.rank" min="1" placeholder="如 5000" />
        </label>
        <label>通勤方式
          <select v-model="form.mode">
            <option v-for="m in MODES" :key="m.v" :value="m.v">{{ m.label }}</option>
          </select>
        </label>
      </div>
      <div class="row">
        <label class="grow">家庭住址（可选，填了才算通勤距离）
          <input type="text" v-model="form.home" placeholder="如 朝阳区大屯金泉家园" />
        </label>
        <label>通勤上限(km，可选)
          <input type="number" v-model="form.max_km" min="1" placeholder="如 8" />
        </label>
      </div>
      <div class="interests">
        <span class="il">兴趣偏好（软匹配，命中置顶不硬筛）：</span>
        <button v-for="t in INTEREST_TAGS" :key="t" type="button"
          class="chip" :class="{ on: form.interests.includes(t) }" @click="toggleInterest(t)">{{ t }}</button>
      </div>
      <button class="go" :disabled="loading" @click="submit">
        {{ loading ? '匹配中…' : '生成志愿建议' }}
      </button>
      <p v-if="errMsg" class="err">{{ errMsg }}</p>
    </section>

    <section v-if="result" class="results">
      <div v-for="band in ['冲', '稳', '保']" :key="band" class="band">
        <h2 :style="{ color: BAND_COLOR[band] }">
          <span class="dot" :style="{ background: BAND_COLOR[band] }"></span>
          {{ band }} <small>{{ BAND_DESC[band] }}</small>
          <span class="cnt">{{ (result.bands[band] || []).length }} 所</span>
        </h2>
        <p v-if="!(result.bands[band] || []).length" class="empty">该档暂无匹配学校</p>
        <div v-for="c in result.bands[band]" :key="c.name" class="school">
          <div class="sname">
            {{ c.name }}
            <span class="lvl">{{ c.level }}</span>
            <span v-if="c.matched && c.matched.length" class="match">🎯{{ c.matched.join('·') }}</span>
          </div>
          <div class="meta">
            录取位次≈<b>{{ c.ref_rank }}</b>名 · margin {{ c.margin_pct }}
            <span v-if="c.volatility >= 0.4" class="vol">⚠️位次年际波动大</span>
          </div>
          <div v-if="distTxt(c)" class="meta">{{ distTxt(c) }}</div>
          <div v-if="c.style" class="meta">🏫 {{ c.style }}</div>
          <div v-if="c.tags && c.tags.length" class="tags">
            <span v-for="t in c.tags" :key="t" class="tag">#{{ t }}</span>
          </div>
          <div v-if="c.gaokao" class="meta gk">🎓 高考(民间·非官方仅参考)：{{ c.gaokao }}</div>
          <div v-if="c.history && c.history.length" class="meta hist">
            历年位次：<span v-for="h in c.history" :key="h[0]">{{ h[0] }}年≈{{ h[1] }}名 </span>
          </div>
          <div v-if="c.note" class="meta note">{{ c.note }}</div>
        </div>
      </div>

      <div class="mapwrap">
        <h2>志愿地图</h2>
        <p v-if="!result.home_coord" class="empty">填写家庭住址后可显示通勤地图。</p>
        <div v-show="result.home_coord" id="zmap"></div>
        <div v-if="result.home_coord" class="legend">
          <span><i class="d" style="background:#e74c3c"></i>冲</span>
          <span><i class="d" style="background:#f1c40f"></i>稳</span>
          <span><i class="d" style="background:#2ecc71"></i>保</span>
          <span><i class="s" style="background:#9aa0a6"></i>位次够不上</span>
          <span><i class="s" style="background:#e67e22"></i>超通勤</span>
          <span><i class="s" style="background:#3498db"></i>民办/国际(右上角切换)</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { max-width: 760px; margin: 0 auto; padding: 16px; background: var(--bg); min-height: 100%; }
.hero h1 { font-size: 20px; color: var(--brand-deeper); }
.hero .sub { color: var(--gray-600); font-size: 13px; margin-top: 4px; }
.disclaimer { background: var(--warning-bg); border: 1px solid var(--accent);
  color: var(--gray-800); font-size: 12.5px; padding: 10px 12px;
  border-radius: var(--radius-sm); margin: 12px 0; }
.card { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 16px; }
.form .row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.form label { display: flex; flex-direction: column; font-size: 12px; color: var(--gray-600); flex: 1; gap: 4px; }
.form label.grow { flex: 2; }
.form input, .form select { padding: 9px 10px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); font-size: 14px; background: #fff; }
.interests { margin-bottom: 12px; }
.interests .il { font-size: 12px; color: var(--gray-600); display: block; margin-bottom: 6px; }
.chip { font-size: 12px; padding: 5px 10px; border: 1px solid var(--gray-300);
  background: #fff; border-radius: var(--radius-full); margin: 0 6px 6px 0; color: var(--gray-700); }
.chip.on { background: var(--brand); color: #fff; border-color: var(--brand); }
.go { width: 100%; padding: 12px; background: var(--brand); color: #fff; border: none;
  border-radius: var(--radius-sm); font-size: 15px; font-weight: 600; }
.go:disabled { opacity: .6; }
.err { color: var(--error); font-size: 13px; margin-top: 8px; }
.results { margin-top: 16px; }
.band { margin-bottom: 20px; }
.band h2 { font-size: 16px; display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.band h2 small { color: var(--gray-500); font-weight: 400; font-size: 12px; }
.band h2 .cnt { margin-left: auto; font-size: 12px; color: var(--gray-500); font-weight: 400; }
.dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.empty { color: var(--gray-400); font-size: 13px; }
.school { background: var(--surface); border-radius: var(--radius-sm); box-shadow: var(--shadow-sm);
  padding: 12px 14px; margin-bottom: 10px; }
.sname { font-size: 15px; font-weight: 600; color: var(--gray-900); }
.sname .lvl { font-size: 11px; font-weight: 400; color: var(--brand); background: var(--brand-50);
  padding: 1px 6px; border-radius: var(--radius-xs); margin-left: 6px; }
.sname .match { font-size: 12px; color: #16a085; margin-left: 6px; }
.meta { font-size: 12.5px; color: var(--gray-600); margin-top: 5px; }
.meta .vol { color: var(--accent); margin-left: 6px; }
.meta.gk { color: var(--gray-500); }
.meta.note { color: var(--gray-500); font-style: italic; }
.tags { margin-top: 5px; }
.tag { font-size: 11px; color: var(--brand-dark); background: var(--brand-50);
  padding: 1px 7px; border-radius: var(--radius-full); margin-right: 5px; }
.mapwrap h2 { font-size: 16px; margin-bottom: 8px; }
#zmap { height: 420px; border-radius: var(--radius-sm); overflow: hidden; box-shadow: var(--shadow-sm); }
.legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--gray-600); margin-top: 8px; }
.legend i { display: inline-block; vertical-align: middle; margin-right: 4px; }
.legend i.d { width: 11px; height: 11px; border-radius: 50%; }
.legend i.s { width: 8px; height: 8px; border-radius: 50%; }
</style>
