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
const ZHIYUAN_SLOTS = 12   // 统一招生志愿数（每志愿 2 专业）

interface Major {
  major_code: string; major_name: string; xuezhi: string; jiashi: string
  plan_total: string | number; plan_chaoyang: string; note: string
}
interface Card {
  name: string; level: string; note: string; ref_rank: number | string
  margin: number; margin_pct: string; volatility: number
  history: [number, number][]
  score_lines?: { year: number; score: number | null; rank: number | null }[]
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
  rank: 4500,
  home: '朝阳区大屯路金泉花园小区',
  mode: 'bicycling',
  max_km: 8 as number | string,
  boarding: false,
  interests: [] as string[],
})
// 学校类型图层开关（地图上显示哪些点）
const layers = reactive({ gongban: true, coop: true, minban: false })
const tab = ref<'map' | 'draft'>('map')   // 地图 / 志愿草表 两个并列页
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
    tab.value = 'map'        // 生成后回到地图页，保证地图在可见状态下初始化
    await nextTick()
    renderMap()
  } catch (e: any) {
    errMsg.value = '推荐失败：' + e.message
  } finally {
    loading.value = false
  }
}

/* ---------------- 地图 ---------------- */
// 选中学校 → 右侧详情面板（替代地图气泡）
const selectedPoint = ref<Point | null>(null)
function selectPoint(p: Point) { selectedPoint.value = p }
// 由点位反查冲稳保卡片：多校区点名形如 "和平街一中·和平街校区(...)"，取 · 前主名匹配
function cardOfPoint(p: Point | null): Card | null {
  if (!p) return null
  const base = p.name.split('·')[0]
  return findCard(base) || findCard(p.name)
}
const selCard = computed<Card | null>(() => cardOfPoint(selectedPoint.value))
const boardBadge = '<span class="bd-badge" title="可寄宿/有住宿">宿</span>'
function pin(color: string, txt: string, boarding = false) {
  return L.divIcon({
    className: '', iconSize: [24, 24], iconAnchor: [12, 24],
    html: `<div style="position:relative;width:24px;height:24px">`
      + `<div style="background:${color};width:24px;height:24px;border-radius:50% 50% 50% 0;`
      + `transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);`
      + `display:flex;align-items:center;justify-content:center;">`
      + `<span class="lbl" style="transform:rotate(45deg);font-size:11px">${txt}</span></div>`
      + (boarding ? boardBadge : '') + `</div>`,
  })
}
function smallIcon(color: string, boarding = false) {
  return L.divIcon({
    className: '', iconSize: [16, 16], iconAnchor: [8, 8],
    html: `<div style="position:relative;width:16px;height:16px">`
      + `<div style="background:${color};width:16px;height:16px;border-radius:50%;`
      + `border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45)"></div>`
      + (boarding ? boardBadge : '') + `</div>`,
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
    const boarding = !!cardOfPoint(p)?.boarding
    const icon = p.kind === 'full' ? pin(p.color, p.band, boarding) : smallIcon(p.color, boarding)
    const mk = L.marker([p.lat, p.lon], { icon }).addTo(publicLayer).on('click', () => selectPoint(p))
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
      .on('click', () => selectPoint(p))
      .bindTooltip(shortName(p.name), { direction: 'top', offset: [0, -6], className: 'map-lbl' })
  })
  if (layers.minban) privateLayer.addTo(mapInst)

  if (bounds.length) mapInst.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
}
function renderMap() {
  const res = result.value
  if (!res) return
  selectedPoint.value = null
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
// 切回地图页时重算尺寸（v-show 隐藏期间容器宽高为 0，会导致瓦片错位）
watch(tab, (t) => { if (t === 'map' && mapInst) nextTick(() => mapInst.invalidateSize()) })

/* ---------------- 列表辅助 ---------------- */
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

    <!-- 输入区：全部条件常驻显示，方便反复改条件对比 -->
    <section class="card form">
      <div class="fields">
        <label class="f-rank">区排名<small>一模/二模</small>
          <input type="number" v-model.number="form.rank" min="1" placeholder="如 4500" />
        </label>
        <label class="f-home">家庭住址<small>留空只看全区分布</small>
          <input type="text" v-model="form.home" placeholder="如 朝阳区大屯金泉家园" />
        </label>
        <label class="f-mode">通勤方式
          <select v-model="form.mode">
            <option v-for="m in MODES" :key="m.v" :value="m.v">{{ m.label }}</option>
          </select>
        </label>
        <label class="f-km">通勤上限<small>km</small>
          <input type="number" v-model="form.max_km" min="1" placeholder="8" :disabled="form.boarding" />
        </label>
        <label class="f-board switch">接受住宿
          <span class="sw-line">
            <input type="checkbox" v-model="form.boarding" />
            <span class="sw-hint">开启后不限距离</span>
          </span>
        </label>
        <button class="go" :disabled="loading" @click="submit">
          {{ loading ? '匹配中…' : '生成志愿建议' }}
        </button>
      </div>
      <div class="interests">
        <span class="il">兴趣偏好<small>（软匹配，命中置顶不硬筛）</small></span>
        <button v-for="t in INTEREST_TAGS" :key="t" type="button"
          class="chip" :class="{ on: form.interests.includes(t) }" @click="toggleInterest(t)">{{ t }}</button>
      </div>
      <p v-if="form.boarding" class="board-note">🛏 已开启住宿：距离不再参与筛选，范围放开到全朝阳（距离仍展示作参考）。</p>
      <p v-if="errMsg" class="err">{{ errMsg }}</p>
    </section>

    <section v-if="result" class="results">
      <!-- 地图 / 志愿草表 两个并列 TAB -->
      <div class="tabs">
        <button class="tab" :class="{ on: tab === 'map' }" @click="tab = 'map'">📍 志愿地图</button>
        <button class="tab" :class="{ on: tab === 'draft' }" @click="tab = 'draft'">
          📝 志愿草表<span class="tab-cnt">{{ filledSlots }}/{{ ZHIYUAN_SLOTS }}</span>
        </button>
      </div>

      <!-- TAB 1：地图 -->
      <div class="mapwrap" v-show="tab === 'map'">
        <div class="map-head">
          <h2>全{{ result.district }}学校分布</h2>
          <div class="layer-chips">
            <button class="lchip" :class="{ on: layers.gongban }" @click="layers.gongban = !layers.gongban">公办普高</button>
            <button class="lchip" :class="{ on: layers.coop }" @click="layers.coop = !layers.coop">中外合作/国际班</button>
            <button class="lchip" :class="{ on: layers.minban }" @click="layers.minban = !layers.minban">民办·国际校</button>
          </div>
        </div>
        <div class="map-detail">
          <div class="map-col">
            <div id="zmap"></div>
            <div class="legend">
              <span><i class="d" style="background:#e74c3c"></i>冲</span>
              <span><i class="d" style="background:#f1c40f"></i>稳</span>
              <span><i class="d" style="background:#2ecc71"></i>保</span>
              <span><i class="s" style="background:#9b59b6"></i>位次够不上</span>
              <span><i class="s" style="background:#e67e22"></i>超通勤</span>
              <span><i class="s" style="background:#3498db"></i>民办/国际</span>
              <span><i class="bd-leg">宿</i>可寄宿</span>
              <span v-if="result.home_coord"><i class="d" style="background:#2c3e50"></i>家</span>
            </div>
          </div>

          <!-- 右侧：选中学校详情面板（替代地图气泡） -->
          <aside class="detail-panel">
            <template v-if="selectedPoint">
              <div class="dp-head">
                <span class="dp-band" :style="{ background: selectedPoint.color }">{{ selectedPoint.band }}</span>
                <h3>{{ cleanName(selectedPoint.name) }}</h3>
              </div>
              <div class="dp-sub">
                {{ selectedPoint.level }}
                <span v-if="selCard?.school_code" class="dp-code">招生码 {{ selCard.school_code }}</span>
              </div>
              <div class="dp-badges">
                <span v-if="selCard?.boarding" class="bdg b-board">🛏 有住宿</span>
                <span v-if="selCard?.coop" class="bdg b-coop">🌐 中外合作班</span>
                <span v-if="selectedPoint.matched && selectedPoint.matched.length" class="bdg b-match">🎯{{ selectedPoint.matched.join('·') }}</span>
              </div>

              <dl class="dp-kv">
                <div v-if="selectedPoint.rank !== '—'">
                  <dt>录取参考位次</dt>
                  <dd>≈ {{ selectedPoint.rank }} 名<span class="dp-mg">margin {{ selectedPoint.margin }}</span>
                    <span v-if="selCard && selCard.volatility >= 0.4" class="dp-vol">⚠️波动大</span></dd>
                </div>
                <div v-if="selectedPoint.dist && selectedPoint.dist !== '距离未知'">
                  <dt>通勤</dt>
                  <dd>{{ selectedPoint.dist }}
                    <span v-if="selCard?.nearest?.over_max" class="dp-vol">⚠️超通勤上限</span></dd>
                </div>
              </dl>

              <!-- 历年录取分数线：2025 → 2024 → 2023 -->
              <div v-if="selCard?.score_lines && selCard.score_lines.length" class="dp-block">
                <div class="dp-title">历年录取分数线</div>
                <table class="dp-table">
                  <thead><tr><th>年份</th><th>分数线</th><th>区排名</th></tr></thead>
                  <tbody>
                    <tr v-for="sl in selCard.score_lines" :key="sl.year">
                      <td>{{ sl.year }}</td>
                      <td>{{ sl.score != null ? sl.score + '分' : '—' }}</td>
                      <td>{{ sl.rank != null ? sl.rank + '名' : '—' }}</td>
                    </tr>
                  </tbody>
                </table>
                <p class="dp-tip">分数跨年口径不同（2025 起总分调整），<b>区排名</b>才是跨年可比的录取参考。</p>
              </div>

              <!-- 招生专业(班) -->
              <div v-if="selCard?.majors && selCard.majors.length" class="dp-block">
                <div class="dp-title">招生专业(班)</div>
                <div v-for="m in selCard.majors" :key="m.major_code" class="dp-mj">
                  <b>{{ m.major_code }}</b> {{ cleanName(m.major_name) }}
                  <em v-if="m.plan_chaoyang">· 朝阳{{ m.plan_chaoyang }}</em>
                </div>
              </div>

              <div v-if="selectedPoint.style" class="dp-line">🏫 {{ selectedPoint.style }}</div>
              <div v-if="selectedPoint.gaokao" class="dp-line dp-muted">🎓 高考(民间·非官方)：{{ selectedPoint.gaokao }}</div>
              <div v-if="selectedPoint.note" class="dp-line dp-muted">{{ selectedPoint.note }}</div>
              <div v-if="selectedPoint.reason" class="dp-warn">🚫 不在报名范围：{{ selectedPoint.reason }}</div>
            </template>
            <div v-else class="dp-empty">
              <div class="dp-empty-ic">🏫</div>
              点击地图上的学校查看详细信息
            </div>
          </aside>
        </div>
      </div>

      <!-- TAB 2：志愿草表（统招 12×2），镜像官方填报 -->
      <div class="draftwrap" v-show="tab === 'draft'">
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
          <div v-for="(s, i) in draft" :key="i" class="slot" :class="{ empty: !s.name, filled: s.name }">
            <div class="slot-top">
              <span class="slot-no" :class="{ on: s.name }">{{ i + 1 }}</span>
              <select v-model="s.name" @change="onSlotSchool(i)" class="school-sel">
                <option :value="null">＋ 选择学校（空）</option>
                <option v-for="c in reportable" :key="c.name" :value="c.name">
                  [{{ bandOf(c.name) }}] {{ cleanName(c.name) }}（{{ c.school_code }}）
                </option>
              </select>
              <button v-if="s.name" class="x" title="清空" @click="clearSlot(i)">✕</button>
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
        <p v-if="result.admission_source" class="src">数据来源：{{ result.admission_source }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { max-width: 1180px; margin: 0 auto; padding: 16px; background: var(--bg); min-height: 100%; }
.hero h1 { font-size: 20px; color: var(--brand-deeper); }
.hero .sub { color: var(--gray-600); font-size: 13px; margin-top: 4px; }
.disclaimer { background: var(--warning-bg); border: 1px solid var(--accent);
  color: var(--gray-800); font-size: 12.5px; padding: 10px 12px;
  border-radius: var(--radius-sm); margin: 12px 0; }
.card { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 16px; }

/* 输入区：全部条件常驻，一行紧凑排开 */
.form .fields { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
.form label { display: flex; flex-direction: column; font-size: 12px; font-weight: 600;
  color: var(--gray-700); gap: 4px; }
.form label small { font-weight: 400; color: var(--gray-400); font-size: 11px; margin-left: 4px; }
.form input, .form select { padding: 9px 10px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); font-size: 14px; background: #fff; height: 38px; box-sizing: border-box; }
.form input:disabled { background: var(--gray-100); color: var(--gray-400); }
.f-rank { width: 110px; }
.f-home { flex: 1; min-width: 200px; }
.f-mode { width: 100px; }
.f-km { width: 90px; }
.f-board .sw-line { display: flex; align-items: center; gap: 6px; height: 38px; }
.f-board .sw-line input { width: 17px; height: 17px; }
.sw-hint { font-size: 11px; font-weight: 400; color: var(--gray-500); }
.go { padding: 0 22px; height: 38px; background: var(--brand); color: #fff; border: none;
  border-radius: var(--radius-sm); font-size: 15px; font-weight: 600; white-space: nowrap; cursor: pointer; }
.go:disabled { opacity: .6; }
.interests { margin-top: 14px; }
.interests .il { font-size: 12px; font-weight: 600; color: var(--gray-700); display: block; margin-bottom: 6px; }
.interests .il small { font-weight: 400; color: var(--gray-400); }
.chip { font-size: 12px; padding: 5px 10px; border: 1px solid var(--gray-300);
  background: #fff; border-radius: var(--radius-full); margin: 0 6px 6px 0; color: var(--gray-700); cursor: pointer; }
.chip.on { background: var(--brand); color: #fff; border-color: var(--brand); }
.board-note { font-size: 12px; color: var(--brand-dark); background: var(--brand-50);
  border-radius: var(--radius-xs); padding: 7px 10px; margin-top: 10px; }
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
/* 地图 + 详情面板：左图右栏 */
.map-detail { display: flex; gap: 12px; align-items: stretch; }
.map-col { flex: 1; min-width: 0; }
.detail-panel { width: 320px; flex-shrink: 0; height: 460px; overflow-y: auto;
  background: var(--surface); border: 1px solid var(--gray-100); border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm); padding: 14px; }
.dp-empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; color: var(--gray-400); font-size: 13px; text-align: center; }
.dp-empty-ic { font-size: 32px; opacity: .5; }
.dp-head { display: flex; align-items: center; gap: 8px; }
.dp-head h3 { font-size: 16px; font-weight: 700; color: var(--gray-900); margin: 0; line-height: 1.3; }
.dp-band { flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; color: #fff;
  font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.dp-sub { font-size: 12.5px; color: var(--gray-600); margin-top: 6px; }
.dp-code { background: var(--gray-100); color: var(--gray-500); font-size: 11px;
  padding: 1px 6px; border-radius: var(--radius-xs); margin-left: 6px; }
.dp-badges { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; }
.dp-kv { margin: 12px 0 0; display: flex; flex-direction: column; gap: 8px; }
.dp-kv > div { display: flex; flex-direction: column; gap: 2px; }
.dp-kv dt { font-size: 11px; color: var(--gray-400); }
.dp-kv dd { margin: 0; font-size: 13px; color: var(--gray-800); font-weight: 600; }
.dp-mg { font-size: 11px; color: var(--gray-400); font-weight: 400; margin-left: 8px; }
.dp-vol { font-size: 11px; color: var(--accent); font-weight: 400; margin-left: 6px; }
.dp-block { margin-top: 14px; }
.dp-title { font-size: 12px; font-weight: 700; color: var(--brand-dark); margin-bottom: 6px;
  padding-left: 7px; border-left: 3px solid var(--brand); }
.dp-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.dp-table th { text-align: left; color: var(--gray-400); font-weight: 500; font-size: 11px;
  padding: 3px 6px; border-bottom: 1px solid var(--gray-100); }
.dp-table td { padding: 4px 6px; color: var(--gray-800); border-bottom: 1px solid var(--gray-50); }
.dp-table tbody tr:first-child td { font-weight: 700; color: var(--gray-900); }
.dp-tip { font-size: 11px; color: var(--gray-400); margin-top: 6px; line-height: 1.5; }
.dp-mj { font-size: 12.5px; color: var(--gray-700); padding: 3px 0; line-height: 1.4; }
.dp-mj b { color: var(--brand-dark); }
.dp-mj em { color: var(--gray-400); font-style: normal; font-size: 11px; }
.dp-line { font-size: 12.5px; color: var(--gray-700); margin-top: 10px; line-height: 1.5; }
.dp-muted { color: var(--gray-500); }
.dp-warn { font-size: 12.5px; color: #c0392b; background: #fef2f2; border-radius: var(--radius-xs);
  padding: 7px 9px; margin-top: 12px; line-height: 1.5; }
/* 底色用页面同色：瓦片降透明度后由它透上来，实现"洗白"而不碰标记 */
#zmap { height: 460px; border-radius: var(--radius-sm); overflow: hidden;
  box-shadow: var(--shadow-sm); background: var(--bg); }
/* 柔和底图：去饱和 + 提亮 + 降对比把高德又黑又粗的注记压成浅灰细字；
   再降透明度让页面底色透上来，街道注记后退、彩色学校标记凸显，色调与界面统一。
   filter/opacity 只作用于瓦片层，markerPane 不受影响，标记仍清晰。 */
#zmap :deep(.leaflet-tile-pane) {
  filter: grayscale(0.85) brightness(1.5) contrast(0.82) saturate(0.6);
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
/* 寄宿角标：图标右上角"宿"字标记 */
#zmap :deep(.bd-badge) {
  position: absolute; top: -7px; right: -7px; z-index: 5;
  width: 15px; height: 15px; border-radius: 50%;
  background: #0d9488; color: #fff; border: 1.5px solid #fff;
  font-size: 9px; font-weight: 700; line-height: 12px; text-align: center;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
}
.legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--gray-600); margin-top: 8px; }
.legend i { display: inline-block; vertical-align: middle; margin-right: 4px; }
.legend i.d { width: 11px; height: 11px; border-radius: 50%; }
.legend i.s { width: 8px; height: 8px; border-radius: 50%; }
.legend i.bd-leg { width: 14px; height: 14px; border-radius: 50%; background: #0d9488;
  color: #fff; font-size: 9px; font-weight: 700; line-height: 14px; text-align: center; font-style: normal; }

/* 地图 / 草表 Tab 切换 */
.tabs { display: flex; gap: 6px; margin-bottom: 12px; }
.tab { font-size: 14px; font-weight: 600; padding: 9px 18px; border: 1px solid var(--gray-200);
  background: var(--surface); color: var(--gray-500); border-radius: var(--radius-sm); cursor: pointer;
  display: flex; align-items: center; gap: 6px; transition: all .15s; }
.tab:hover { color: var(--gray-700); }
.tab.on { background: var(--brand); color: #fff; border-color: var(--brand); box-shadow: var(--shadow-sm); }
.tab-cnt { font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: var(--radius-full);
  background: rgba(0, 0, 0, .12); }
.tab.on .tab-cnt { background: rgba(255, 255, 255, .25); }

/* 徽标颜色复用 */
.bdg { font-size: 11px; padding: 1px 7px; border-radius: var(--radius-full); }
.b-board { background: #ede9fe; color: #6d28d9; }
.b-coop { background: #e0f2fe; color: #0369a1; }
.b-match { background: #d1fae5; color: #047857; }

/* 志愿草表 */
.draftwrap { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 16px; }
.draft-note { font-size: 12.5px; color: var(--gray-600); margin-bottom: 10px; line-height: 1.6; }
.draft-actions { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.ghost { font-size: 12.5px; padding: 6px 12px; border: 1px solid var(--gray-300); background: #fff;
  border-radius: var(--radius-xs); color: var(--gray-700); cursor: pointer; }
.copyhint { font-size: 12px; color: var(--success); }
/* 12 志愿用两列网格铺开，消除单列下拉右侧大段空白 */
.slots { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.slot { padding: 10px 12px; border: 1px solid var(--gray-100); border-radius: var(--radius-sm);
  background: var(--gray-50); transition: border-color .15s, background .15s; }
.slot.filled { background: var(--surface); border-color: var(--brand-50); }
.slot.empty { opacity: .85; }
.slot-top { display: flex; gap: 8px; align-items: center; min-width: 0; }
.slot-no { flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  background: var(--gray-200); color: var(--gray-500); }
.slot-no.on { background: var(--brand); color: #fff; }
.school-sel { flex: 1; min-width: 0; padding: 7px 9px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); font-size: 13px; background: #fff; cursor: pointer; }
.x { flex-shrink: 0; width: 26px; height: 30px; font-size: 12px; border: 1px solid var(--gray-200);
  background: #fff; border-radius: var(--radius-xs); color: var(--gray-400); cursor: pointer; }
.x:hover { color: var(--error); border-color: var(--error); }
.slot-majors { margin-top: 8px; padding-left: 30px; display: flex; flex-wrap: wrap; gap: 6px; }
.mchip { font-size: 12px; padding: 4px 9px; border: 1px solid var(--gray-300); background: #fff;
  border-radius: var(--radius-full); color: var(--gray-600); cursor: pointer; }
.mchip.on { background: var(--brand); color: #fff; border-color: var(--brand); }
.mchip.on b { color: #fff; }
.mchip b { color: var(--brand-dark); }
.nomajor { font-size: 12px; color: var(--gray-400); }
.src { font-size: 11px; color: var(--gray-400); margin-top: 14px; }

/* 移动端 */
@media (max-width: 860px) {
  .map-detail { flex-direction: column; }
  .detail-panel { width: auto; height: auto; max-height: 420px; }
  .slots { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .page { padding: 12px; }
  #zmap { height: 340px; }
  .form .fields { gap: 10px; }
  .f-rank, .f-home, .f-mode, .f-km { flex: 1 1 100%; width: auto; }
  .go { flex: 1 1 100%; width: 100%; }
}
</style>
