<script setup lang="ts">
import { ref, reactive, computed, nextTick, watch } from 'vue'

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
const ZHIYUAN_SLOTS = 12   // 统一招生志愿数（每志愿 2 专业）

interface Major {
  major_code: string; major_name: string; xuezhi: string; jiashi: string
  plan_total: string | number; plan_chaoyang: string; note: string
}
interface Card {
  name: string; level: string; note: string; ref_rank: number | string
  margin: number; margin_pct: string; volatility: number
  history: [number, number][]
  nearest: { campus: string; km: number; mins: number; over_max: boolean } | null
  style: string; tags: string[]; gaokao: string; matched: string[]
  school_code?: string; majors?: Major[]; campus_major?: string
  boarding?: boolean; coop?: boolean
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
  max_km: number | null; boarding: boolean; interests: string[] | null
  admission_source: string | null
  bands: Record<string, Card[]>; points: Point[]; private: Point[]
}

const form = reactive({
  rank: 5000,
  home: '',
  mode: 'driving',
  max_km: '' as number | string,
  boarding: false,
  interests: [] as string[],
})
// 学校类型图层开关（地图上显示哪些点）
const layers = reactive({ gongban: true, coop: true, minban: false })
const showMore = ref(false)
const loading = ref(false)
const errMsg = ref('')
const result = ref<Result | null>(null)
let mapInst: any = null
let publicLayer: any = null
let privateLayer: any = null

function toggleInterest(t: string) {
  const i = form.interests.indexOf(t)
  if (i >= 0) form.interests.splice(i, 1)
  else form.interests.push(t)
}
function cleanName(s: string): string { return (s || '').replace(/\s+/g, '') }
// 地图标签只取学校主名（空格 / 中点 / 括号前截断），避免把校区+计划说明全挤一起
function shortName(s: string): string {
  const n = (s || '').trim()
  return n.split(/[\s（(·]/)[0] || n
}

async function submit() {
  errMsg.value = ''
  if (!form.rank || form.rank < 1) { errMsg.value = '请填写有效的区排名'; return }
  loading.value = true
  try {
    const body: any = {
      rank: Number(form.rank),
      mode: form.mode,
      boarding: form.boarding,
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
    resetDraft()
    await nextTick()
    renderMap()
  } catch (e: any) {
    errMsg.value = '推荐失败：' + e.message
  } finally {
    loading.value = false
  }
}

/* ---------------- 地图 ---------------- */
function popupHtml(p: Point): string {
  let h = `<div class="pop"><b>${cleanName(p.name)}</b> <span style="color:${p.color}">[${p.band}]</span>`
  if (p.matched && p.matched.length) h += ` <span style="color:#16a085">🎯${p.matched.join('·')}</span>`
  let m = `<div class="meta">${p.level}`
  if (p.rank !== '—') m += ` ｜ 录取位次≈${p.rank}名 (margin ${p.margin})`
  if (p.dist && p.dist !== '距离未知') m += `<br>通勤 ${p.dist}`
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
    className: '', iconSize: [24, 24], iconAnchor: [12, 24],
    html: `<div style="background:${color};width:24px;height:24px;border-radius:50% 50% 50% 0;`
      + `transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);`
      + `display:flex;align-items:center;justify-content:center;">`
      + `<span class="lbl" style="transform:rotate(45deg);font-size:11px">${txt}</span></div>`,
  })
}
function smallIcon(color: string) {
  return L.divIcon({
    className: '', iconSize: [16, 16], iconAnchor: [8, 8],
    html: `<div style="background:${color};width:16px;height:16px;border-radius:50%;`
      + `border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45)"></div>`,
  })
}
// 该点是不是中外合作/国际班学校（用于 coop 图层过滤）
function isCoopPoint(p: Point): boolean {
  const c = findCard(p.name)
  return !!(c && c.coop)
}
function renderMarkers() {
  const res = result.value
  if (!res || !mapInst) return
  if (publicLayer) { mapInst.removeLayer(publicLayer); publicLayer = null }
  if (privateLayer) { mapInst.removeLayer(privateLayer); privateLayer = null }
  const bounds: any[] = []
  if (res.home_coord) bounds.push(res.home_coord)

  publicLayer = L.layerGroup()
  res.points.forEach((p) => {
    const coop = isCoopPoint(p)
    // 图层过滤：gongban 控普通公办点，coop 控中外合作校
    if (!layers.gongban && !(coop && layers.coop)) return
    if (coop && !layers.coop && !layers.gongban) return
    bounds.push([p.lat, p.lon])
    const icon = p.kind === 'full' ? pin(p.color, p.band) : smallIcon(p.color)
    const mk = L.marker([p.lat, p.lon], { icon }).addTo(publicLayer).bindPopup(popupHtml(p))
    // 缺省常驻显示学校名：重点推荐校(冲/稳/保)常驻，其余小点悬停显示，避免拥挤
    if (p.kind === 'full') {
      mk.bindTooltip(shortName(p.name), { permanent: true, direction: 'bottom', offset: [0, 2], className: 'map-lbl' })
    } else {
      mk.bindTooltip(shortName(p.name), { direction: 'top', offset: [0, -6], className: 'map-lbl' })
    }
  })
  if (layers.gongban || layers.coop) publicLayer.addTo(mapInst)

  privateLayer = L.layerGroup()
  res.private.forEach((p) => {
    bounds.push([p.lat, p.lon])
    L.marker([p.lat, p.lon], { icon: smallIcon(p.color) }).addTo(privateLayer)
      .bindPopup(popupHtml(p))
      .bindTooltip(shortName(p.name), { direction: 'top', offset: [0, -6], className: 'map-lbl' })
  })
  if (layers.minban) privateLayer.addTo(mapInst)

  if (bounds.length) mapInst.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
}
function renderMap() {
  const res = result.value
  if (!res) return
  if (mapInst) { mapInst.remove(); mapInst = null; publicLayer = null; privateLayer = null }
  // 默认中心：有住址用住址，否则用全部点位中心（朝阳）
  let center: [number, number] = res.home_coord || [39.95, 116.47]
  if (!res.home_coord && res.points.length) {
    const la = res.points.reduce((s, p) => s + p.lat, 0) / res.points.length
    const lo = res.points.reduce((s, p) => s + p.lon, 0) / res.points.length
    center = [la, lo]
  }
  const map = L.map('zmap', { zoomControl: false, scrollWheelZoom: false }).setView(center, 11)
  mapInst = map
  L.control.zoom({ position: 'topright' }).addTo(map)
  // tileSize:128 让 Leaflet 取深一级 zoom 的瓦片再缩到 128px 格子显示，
  // 高德街道注记随之整体缩小变细（注记是烤进瓦片像素的，只能用此法变小）
  L.tileLayer('https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}',
    { subdomains: ['1', '2', '3', '4'], tileSize: 128, zoomOffset: 1, maxZoom: 18, attribution: '高德地图' }).addTo(map)
  if (res.home_coord) {
    L.marker(res.home_coord, { icon: pin('#2c3e50', '家'), zIndexOffset: 1000 }).addTo(map)
      .bindPopup(`<div class="pop"><b>家</b><br>${res.home || ''}</div>`)
  }
  renderMarkers()
}
watch(layers, () => { if (mapInst) renderMarkers() }, { deep: true })

/* ---------------- 列表辅助 ---------------- */
function distTxt(c: Card): string {
  if (!c.nearest) return ''
  const n = c.nearest
  const campus = n.campus ? `${n.campus} ` : ''
  const over = n.over_max ? ' ⚠️超通勤上限' : ''
  return `📍${campus}${result.value?.mode_label || ''}${n.km}km/${n.mins}分钟${over}`
}
function findCard(name: string): Card | null {
  const res = result.value
  if (!res) return null
  for (const band of ['冲', '稳', '保', '够不上']) {
    const hit = (res.bands[band] || []).find(c => c.name === name)
    if (hit) return hit
  }
  return null
}

/* ---------------- 志愿草表（统招 12×2）---------------- */
interface Slot { name: string | null; picks: string[] }
const draft = ref<Slot[]>([])

// 可填报学校：冲→稳→保 顺序，须有官方学校代码；寄宿模式下不排距离
const reportable = computed<Card[]>(() => {
  const res = result.value
  if (!res) return []
  const out: Card[] = []
  for (const band of ['冲', '稳', '保']) {
    for (const c of (res.bands[band] || [])) {
      if (!c.school_code) continue
      // 非寄宿且明确超通勤上限的，排在草表末尾不预填（仍可手动选）
      out.push(c)
    }
  }
  return out
})
function bandOf(name: string | null): string {
  const res = result.value
  if (!res || !name) return ''
  for (const band of ['冲', '稳', '保', '够不上']) {
    if ((res.bands[band] || []).some(c => c.name === name)) return band
  }
  return ''
}
function majorsOf(name: string | null): Major[] {
  if (!name) return []
  return findCard(name)?.majors || []
}
function resetDraft() {
  const rep = reportable.value
  const slots: Slot[] = []
  for (let i = 0; i < ZHIYUAN_SLOTS; i++) {
    const c = rep[i]
    if (c) {
      const codes = (c.majors || []).slice(0, 2).map(m => m.major_code)
      slots.push({ name: c.name, picks: codes })
    } else {
      slots.push({ name: null, picks: [] })
    }
  }
  draft.value = slots
}
function onSlotSchool(i: number) {
  // 切换学校后，默认勾选前 2 个专业
  const s = draft.value[i]
  s.picks = majorsOf(s.name).slice(0, 2).map(m => m.major_code)
}
function togglePick(i: number, code: string) {
  const s = draft.value[i]
  const idx = s.picks.indexOf(code)
  if (idx >= 0) s.picks.splice(idx, 1)
  else if (s.picks.length < 2) s.picks.push(code)
}
function clearSlot(i: number) { draft.value[i] = { name: null, picks: [] } }
const filledSlots = computed(() => draft.value.filter(s => s.name).length)

function copyDraft() {
  const res = result.value
  if (!res) return
  const lines = [`统一招生 志愿草表（${res.district} · ${ZHIYUAN_SLOTS}志愿×2专业）`]
  draft.value.forEach((s, i) => {
    if (!s.name) { lines.push(`志愿${i + 1}　（空）`); return }
    const c = findCard(s.name)
    const ms = majorsOf(s.name).filter(m => s.picks.includes(m.major_code))
    const mtxt = ms.map(m => `${m.major_code} ${cleanName(m.major_name)}`).join('　')
    lines.push(`志愿${i + 1}　${cleanName(s.name)}(${c?.school_code || ''})　${mtxt}`)
  })
  const txt = lines.join('\n')
  navigator.clipboard?.writeText(txt).then(
    () => { copyHint.value = '已复制到剪贴板'; setTimeout(() => copyHint.value = '', 2000) },
    () => { copyHint.value = '复制失败，请手动选择' },
  )
}
const copyHint = ref('')
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>北京中考志愿参考 · 朝阳</h1>
      <p class="sub">按区排名做冲稳保匹配，叠加通勤路网距离与学校特色，并镜像官方填报格式生成统招志愿草表。仅辅助参考，最终以官方招生简章与老师建议为准。</p>
    </header>

    <div class="disclaimer">
      ⚠️ 学校代码 / 专业(班)代码派生自 <b>bjeea 2025 官方招生计划册</b>（人工核对映射），<b>2026 计划 7 月初发布后须刷新</b>；高考成绩为<b>民间·非官方</b>数据，仅作补充参考，请勿据此直接决策。
    </div>

    <!-- 输入区：排名必填，其余收进“更多条件” -->
    <section class="card form">
      <div class="primary">
        <label class="big">孩子区排名（一模/二模）
          <input type="number" v-model.number="form.rank" min="1" placeholder="如 5000" />
        </label>
        <button class="go" :disabled="loading" @click="submit">
          {{ loading ? '匹配中…' : '生成志愿建议' }}
        </button>
      </div>
      <button class="more-toggle" type="button" @click="showMore = !showMore">
        {{ showMore ? '▲ 收起更多条件' : '▼ 更多条件（住址 / 寄宿 / 通勤 / 兴趣）' }}
      </button>
      <div v-show="showMore" class="more">
        <div class="row">
          <label class="grow">家庭住址（填了才算通勤距离；不填也能看全区分布）
            <input type="text" v-model="form.home" placeholder="如 朝阳区大屯金泉家园" />
          </label>
          <label>通勤方式
            <select v-model="form.mode">
              <option v-for="m in MODES" :key="m.v" :value="m.v">{{ m.label }}</option>
            </select>
          </label>
          <label>通勤上限(km)
            <input type="number" v-model="form.max_km" min="1" placeholder="如 8" :disabled="form.boarding" />
          </label>
        </div>
        <label class="switch">
          <input type="checkbox" v-model="form.boarding" />
          <span>孩子接受<b>住宿</b>（开启后距离不再参与筛选，范围放开到全朝阳；距离仍展示作参考）</span>
        </label>
        <div class="interests">
          <span class="il">兴趣偏好（软匹配，命中置顶不硬筛）：</span>
          <button v-for="t in INTEREST_TAGS" :key="t" type="button"
            class="chip" :class="{ on: form.interests.includes(t) }" @click="toggleInterest(t)">{{ t }}</button>
        </div>
      </div>
      <p v-if="errMsg" class="err">{{ errMsg }}</p>
    </section>

    <section v-if="result" class="results">
      <!-- 1) 地图优先：先看全局 -->
      <div class="mapwrap">
        <div class="map-head">
          <h2>📍 志愿地图 · 全{{ result.district }}学校分布</h2>
          <div class="layer-chips">
            <button class="lchip" :class="{ on: layers.gongban }" @click="layers.gongban = !layers.gongban">公办普高</button>
            <button class="lchip" :class="{ on: layers.coop }" @click="layers.coop = !layers.coop">中外合作/国际班</button>
            <button class="lchip" :class="{ on: layers.minban }" @click="layers.minban = !layers.minban">民办·国际校</button>
          </div>
        </div>
        <div id="zmap"></div>
        <div class="legend">
          <span><i class="d" style="background:#e74c3c"></i>冲</span>
          <span><i class="d" style="background:#f1c40f"></i>稳</span>
          <span><i class="d" style="background:#2ecc71"></i>保</span>
          <span><i class="s" style="background:#9aa0a6"></i>位次够不上</span>
          <span><i class="s" style="background:#e67e22"></i>超通勤</span>
          <span><i class="s" style="background:#3498db"></i>民办/国际</span>
          <span v-if="result.home_coord"><i class="d" style="background:#2c3e50"></i>家</span>
        </div>
      </div>

      <!-- 2) 冲稳保列表 -->
      <div class="bands">
        <div v-for="band in ['冲', '稳', '保']" :key="band" class="band">
          <h2 :style="{ color: BAND_COLOR[band] }">
            <span class="dot" :style="{ background: BAND_COLOR[band] }"></span>
            {{ band }} <small>{{ BAND_DESC[band] }}</small>
            <span class="cnt">{{ (result.bands[band] || []).length }} 所</span>
          </h2>
          <p v-if="!(result.bands[band] || []).length" class="empty">该档暂无匹配学校</p>
          <div class="school-grid">
            <div v-for="c in result.bands[band]" :key="c.name" class="school">
              <div class="sname">
                {{ cleanName(c.name) }}
                <span class="lvl">{{ c.level }}</span>
                <span v-if="c.school_code" class="code">码{{ c.school_code }}</span>
              </div>
              <div class="badges">
                <span v-if="c.boarding" class="bdg b-board">🛏 有住宿</span>
                <span v-if="c.coop" class="bdg b-coop">🌐 中外合作班</span>
                <span v-if="c.matched && c.matched.length" class="bdg b-match">🎯{{ c.matched.join('·') }}</span>
              </div>
              <div class="meta">
                录取位次≈<b>{{ c.ref_rank }}</b>名 · margin {{ c.margin_pct }}
                <span v-if="c.volatility >= 0.4" class="vol">⚠️波动大</span>
              </div>
              <div v-if="distTxt(c)" class="meta">{{ distTxt(c) }}</div>
              <div v-if="c.majors && c.majors.length" class="majors">
                <span v-for="m in c.majors" :key="m.major_code" class="mj">
                  <b>{{ m.major_code }}</b> {{ cleanName(m.major_name) }}
                  <em v-if="m.plan_chaoyang">· 朝阳{{ m.plan_chaoyang }}</em>
                </span>
              </div>
              <div v-if="c.style" class="meta sub2">🏫 {{ c.style }}</div>
              <div v-if="c.gaokao" class="meta gk">🎓 高考(民间·非官方)：{{ c.gaokao }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 3) 志愿草表（统招 12×2）：最后输出，镜像官方填报 -->
      <div class="draftwrap">
        <h2>📝 统一招生 · 志愿草表（{{ ZHIYUAN_SLOTS }}志愿 × 每志愿2专业）</h2>
        <p class="draft-note">
          已按 <b>冲→稳→保</b> 顺序自动预填 {{ filledSlots }}/{{ ZHIYUAN_SLOTS }} 个志愿；可改学校、改专业(班，每志愿最多 2 个)。
          这就是中考网报系统里统招批次的样子（学校代码 + 专业代码）。
          <br>提示：<b>提前招生</b>（特长/特色等）与<b>校额到校/指标分配</b>是单独批次、单独填报，本表只覆盖<b>统一招生</b>；贯通培养 2026 起并入统招批次。
        </p>
        <div class="draft-actions">
          <button class="ghost" @click="resetDraft">重置为推荐顺序</button>
          <button class="ghost" @click="copyDraft">复制草表文本</button>
          <span v-if="copyHint" class="copyhint">{{ copyHint }}</span>
        </div>
        <div class="slots">
          <div v-for="(s, i) in draft" :key="i" class="slot" :class="{ empty: !s.name }">
            <div class="slot-no">志愿{{ i + 1 }}</div>
            <div class="slot-body">
              <div class="slot-row1">
                <select v-model="s.name" @change="onSlotSchool(i)" class="school-sel">
                  <option :value="null">（空 / 选择学校）</option>
                  <option v-for="c in reportable" :key="c.name" :value="c.name">
                    {{ cleanName(c.name) }}（{{ c.school_code }}）· {{ bandOf(c.name) }}
                  </option>
                </select>
                <button v-if="s.name" class="x" @click="clearSlot(i)">清空</button>
              </div>
              <div v-if="s.name" class="slot-majors">
                <button v-for="m in majorsOf(s.name)" :key="m.major_code" type="button"
                  class="mchip" :class="{ on: s.picks.includes(m.major_code) }"
                  @click="togglePick(i, m.major_code)">
                  <b>{{ m.major_code }}</b> {{ cleanName(m.major_name) }}
                </button>
                <span v-if="!majorsOf(s.name).length" class="nomajor">该校暂无官方专业代码数据</span>
              </div>
            </div>
          </div>
        </div>
        <p v-if="result.admission_source" class="src">数据来源：{{ result.admission_source }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { max-width: 1080px; margin: 0 auto; padding: 16px; background: var(--bg); min-height: 100%; }
.hero h1 { font-size: 20px; color: var(--brand-deeper); }
.hero .sub { color: var(--gray-600); font-size: 13px; margin-top: 4px; }
.disclaimer { background: var(--warning-bg); border: 1px solid var(--accent);
  color: var(--gray-800); font-size: 12.5px; padding: 10px 12px;
  border-radius: var(--radius-sm); margin: 12px 0; }
.card { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 16px; }

/* 输入区 */
.form .primary { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
.form label { display: flex; flex-direction: column; font-size: 12px; color: var(--gray-600); gap: 4px; }
.form label.big { flex: 1; min-width: 180px; font-size: 13px; font-weight: 600; color: var(--gray-800); }
.form input, .form select { padding: 9px 10px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); font-size: 14px; background: #fff; }
.form input:disabled { background: var(--gray-100); color: var(--gray-400); }
.go { padding: 11px 22px; background: var(--brand); color: #fff; border: none;
  border-radius: var(--radius-sm); font-size: 15px; font-weight: 600; white-space: nowrap; }
.go:disabled { opacity: .6; }
.more-toggle { margin-top: 12px; background: none; border: none; color: var(--brand);
  font-size: 13px; padding: 0; }
.more { margin-top: 12px; border-top: 1px dashed var(--gray-200); padding-top: 12px; }
.more .row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.more label { flex: 1; min-width: 130px; }
.more label.grow { flex: 2; min-width: 220px; }
.switch { flex-direction: row !important; align-items: center; gap: 8px !important;
  font-size: 13px !important; color: var(--gray-700) !important; margin-bottom: 12px; cursor: pointer; }
.switch input { width: 16px; height: 16px; }
.interests .il { font-size: 12px; color: var(--gray-600); display: block; margin-bottom: 6px; }
.chip { font-size: 12px; padding: 5px 10px; border: 1px solid var(--gray-300);
  background: #fff; border-radius: var(--radius-full); margin: 0 6px 6px 0; color: var(--gray-700); }
.chip.on { background: var(--brand); color: #fff; border-color: var(--brand); }
.err { color: var(--error); font-size: 13px; margin-top: 8px; }

.results { margin-top: 16px; }

/* 地图 */
.mapwrap { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm);
  padding: 14px; margin-bottom: 18px; }
.map-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.map-head h2 { font-size: 16px; }
.layer-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.lchip { font-size: 12px; padding: 4px 10px; border: 1px solid var(--gray-300); background: #fff;
  border-radius: var(--radius-full); color: var(--gray-500); }
.lchip.on { background: var(--brand-50); color: var(--brand-dark); border-color: var(--brand); }
/* 底色用页面同色：瓦片降透明度后由它透上来，实现"洗白"而不碰标记 */
#zmap { height: 460px; border-radius: var(--radius-sm); overflow: hidden;
  box-shadow: var(--shadow-sm); background: var(--bg); }
/* 柔和底图：去饱和 + 提亮 + 降对比把高德又黑又粗的注记压成浅灰细字；
   再降透明度让页面底色透上来，街道注记后退、彩色学校标记凸显，色调与界面统一。
   filter/opacity 只作用于瓦片层，markerPane 不受影响，标记仍清晰。 */
#zmap :deep(.leaflet-tile-pane) {
  filter: grayscale(0.85) brightness(1.34) contrast(0.88) saturate(0.64);
  opacity: 0.97;
}
/* 学校名常驻标签：紧凑、用界面字体，半透明白底，无箭头 */
#zmap :deep(.map-lbl) {
  background: rgba(255, 255, 255, 0.86); color: var(--gray-700);
  border: none; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  font-size: 11px; line-height: 1.2; font-weight: 600;
  padding: 1px 5px; border-radius: 4px; white-space: nowrap;
}
#zmap :deep(.map-lbl::before) { display: none; } /* 去掉小三角箭头 */
.legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--gray-600); margin-top: 8px; }
.legend i { display: inline-block; vertical-align: middle; margin-right: 4px; }
.legend i.d { width: 11px; height: 11px; border-radius: 50%; }
.legend i.s { width: 8px; height: 8px; border-radius: 50%; }

/* 冲稳保 */
.bands { margin-bottom: 18px; }
.band { margin-bottom: 18px; }
.band h2 { font-size: 16px; display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.band h2 small { color: var(--gray-500); font-weight: 400; font-size: 12px; }
.band h2 .cnt { margin-left: auto; font-size: 12px; color: var(--gray-500); font-weight: 400; }
.dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.empty { color: var(--gray-400); font-size: 13px; }
.school-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 10px; }
.school { background: var(--surface); border: 1px solid var(--gray-100); border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm); padding: 12px 14px; }
.sname { font-size: 15px; font-weight: 600; color: var(--gray-900); }
.sname .lvl { font-size: 11px; font-weight: 400; color: var(--brand); background: var(--brand-50);
  padding: 1px 6px; border-radius: var(--radius-xs); margin-left: 6px; }
.sname .code { font-size: 11px; font-weight: 400; color: var(--gray-500); background: var(--gray-100);
  padding: 1px 6px; border-radius: var(--radius-xs); margin-left: 4px; }
.badges { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 5px; }
.bdg { font-size: 11px; padding: 1px 7px; border-radius: var(--radius-full); }
.b-board { background: #ede9fe; color: #6d28d9; }
.b-coop { background: #e0f2fe; color: #0369a1; }
.b-match { background: #d1fae5; color: #047857; }
.meta { font-size: 12.5px; color: var(--gray-600); margin-top: 5px; }
.meta .vol { color: var(--accent); margin-left: 6px; }
.meta.gk { color: var(--gray-500); }
.meta.sub2 { color: var(--gray-500); }
.majors { margin-top: 6px; display: flex; flex-direction: column; gap: 2px; }
.mj { font-size: 12px; color: var(--gray-700); }
.mj b { color: var(--brand-dark); }
.mj em { color: var(--gray-400); font-style: normal; font-size: 11px; }

/* 志愿草表 */
.draftwrap { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 16px; }
.draftwrap h2 { font-size: 16px; margin-bottom: 8px; }
.draft-note { font-size: 12.5px; color: var(--gray-600); margin-bottom: 10px; line-height: 1.6; }
.draft-actions { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.ghost { font-size: 12.5px; padding: 6px 12px; border: 1px solid var(--gray-300); background: #fff;
  border-radius: var(--radius-xs); color: var(--gray-700); }
.copyhint { font-size: 12px; color: var(--success); }
.slots { display: flex; flex-direction: column; gap: 8px; }
.slot { display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px;
  border: 1px solid var(--gray-100); border-radius: var(--radius-sm); background: var(--gray-50); }
.slot.empty { opacity: .7; }
.slot-no { font-size: 12px; font-weight: 600; color: var(--brand-dark); min-width: 44px; padding-top: 8px; }
.slot-body { flex: 1; min-width: 0; }
.slot-row1 { display: flex; gap: 8px; align-items: center; min-width: 0; }
.school-sel { flex: 1; min-width: 0; padding: 7px 9px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); font-size: 13px; background: #fff; }
.x { font-size: 12px; padding: 6px 10px; border: 1px solid var(--gray-200); background: #fff;
  border-radius: var(--radius-xs); color: var(--gray-500); }
.slot-majors { margin-top: 7px; display: flex; flex-wrap: wrap; gap: 6px; }
.mchip { font-size: 12px; padding: 4px 9px; border: 1px solid var(--gray-300); background: #fff;
  border-radius: var(--radius-full); color: var(--gray-600); }
.mchip.on { background: var(--brand); color: #fff; border-color: var(--brand); }
.mchip.on b { color: #fff; }
.mchip b { color: var(--brand-dark); }
.nomajor { font-size: 12px; color: var(--gray-400); }
.src { font-size: 11px; color: var(--gray-400); margin-top: 12px; }

/* 移动端 */
@media (max-width: 640px) {
  .page { padding: 12px; }
  #zmap { height: 340px; }
  .school-grid { grid-template-columns: 1fr; }
  .form .primary { flex-direction: column; align-items: stretch; }
  .go { width: 100%; }
  .slot-no { min-width: 38px; }
}
</style>
