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

// 升学渠道科普（来源：bjeea.cn / 北京市教委 / 首都之窗 T1 原文交叉核验，2025现状+2026已知变化）
const GUIDE = [
  { t: '总览：3 个批次，顺序录取', h:
    '中考总分 <b>510 分</b>（2024 是 670，2025 改革后降为 510）。录取分三批次按先后进行，<b>被前一批次录取就锁定、不再参加后面的批次</b>：<br>' +
    '<span class="g-flow">① 提前招生 → ② 指标分配 → ③ 统一招生</span>' +
    '2025 一个考生最多可填 <b>28 个志愿</b>（提招贯通 8 + 指标分配 8×2专业 + 统招 12×2专业）。' },
  { t: '① 提前招生（提招）', h:
    '<ul><li><b>贯通培养</b>：380 分门槛，8 个志愿（详见"贯通 vs 五年制"）</li>' +
    '<li><b>中外合作办学班</b></li>' +
    '<li><b>特长生</b>：体育/艺术各 ≤ 招生计划 4%，科技 ≤ 2%</li>' +
    '<li><b>中职自主招生</b>（专业测试录取，中考分只记合格/不合格）</li>' +
    '<li><b>登记入学、自主招生</b>也在这一阶段处理</li></ul>' },
  { t: '② 指标分配（校额到校 + 市级统筹）', h:
    '中间批次，8 志愿×2 专业。<br>' +
    '<b>校额到校</b>：优质高中名额<b>定向分到每所初中，校内竞争</b>（同校学生比，不是全区比）。门槛＝<b>连续三年本校学籍 + 综合素质 B + 中考总分达线</b>（2025 = 430/510 ≈ 84%）。' +
    '<span class="g-warn">往届生、外省回京、回户籍报考者不能报。</span><br>' +
    '<b>市级统筹（一/二/三）</b>：优质资源跨区招生（统筹一不在东西海招、统筹二名校郊区分校面向全市、统筹三高校与普高联合培养）。' },
  { t: '③ 统一招生（统招，本系统核心）', h:
    '最后批次，按总分从高到低、依志愿录取。<b>12 个志愿 × 每志愿 2 专业</b>——<b>这就是本系统的"志愿草表"</b>。' },
  { t: '贯通培养 vs 五年制高职（易混）', h:
    '<table class="g-tbl"><thead><tr><th></th><th>学制</th><th>出口文凭</th><th>门槛</th><th>户籍</th></tr></thead><tbody>' +
    '<tr><td><b>贯通培养</b><br>(中本/高本贯通)</td><td>7 年</td><td><b>本科</b></td><td>统一 380 分</td><td><b>仅限京籍</b></td></tr>' +
    '<tr><td><b>五年制高职</b><br>(3+2)</td><td>5 年</td><td><b>大专</b></td><td>按中考分</td><td>京籍+非京籍均可</td></tr>' +
    '</tbody></table><span class="g-warn">名字像、层级与户籍门槛不同：随迁子女能报 5 年制大专，不能报 7 年贯通本科。</span>' },
  { t: '职业教育（中专 / 职高 / 技校 / 综合高中班）', h:
    '<ul><li><b>中专</b>(代码 4，市教委+发改委，全市招生)</li>' +
    '<li><b>职高</b>(代码 6，区教委)</li>' +
    '<li><b>技校</b>(代码 5，<b>归人社部门</b>，但仍走中考统一平台填志愿)</li>' +
    '<li><b>五年制高职/3+2</b>(代码 8，5 年→大专)</li>' +
    '<li><b>综合高中班</b>：职普融通试点，按普高标准收费，2026 适度扩招</li></ul>' +
    '升学出口：单考单招("三校生高考")、高职单招(专科)、五年制/3+2 直升、贯通转段升本科。' },
  { t: '登记入学（免试登记普高）', h:
    '2025：<b>东城、西城</b>试点；2026：<b>加平谷</b>（4 校 555 个计划）。' +
    '<span class="g-warn">网传"海淀/朝阳登记入学"经核实没有——朝阳考生用不上。</span>' },
  { t: '京籍 vs 非京籍（随迁子女）', h:
    '<b>非京籍随迁子女不能报普通高中</b>（统招/校额到校/统筹/登记入学/贯通都不行），<b>只能报中职</b>（中专/职高/技校/五年制/3+2），且要满足"五条件"：居住证 + 稳定住所 + 在京职业满 3 年 + 社保满 3 年 + 本市学籍连续就读初中 3 年。' },
  { t: '📌 2026 两条硬变化', h:
    '<ul><li><b>贯通从"提招"移入"统一招生"批次</b>（380 分门槛不变）→ 28 志愿结构会变</li>' +
    '<li><b>登记入学扩到平谷</b></li></ul>' +
    '<span class="g-src">来源：北京教育考试院 bjeea.cn / 北京市教委 / 首都之窗（2025政策原文+2026已知变化）。市级统筹各年校数名额、贯通各项目精确学制、2026 完整时间表等以当年 bjeea 正式简章为准。</span>' },
]
const showGuide = ref(false)
const openG = ref<number | null>(null)
const XED_OFFICIAL = 'https://www.bjeea.cn/html/zkzh/jhcx/2025/0701/87193.html'

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
interface PubSchool {
  name: string; level: string; band: string; ref_rank: number | string
  margin_pct: string; score_lines?: { year: number; score: number | null; rank: number | null }[]
  campus: string; address: string; address_exact: boolean
  address_confidence: string; address_flag: string
  boarding?: boolean; coop?: boolean
  nearest: { campus: string; km: number; mins: number; over_max: boolean } | null
  over_max: boolean; reportable: boolean
}
interface PrivSchool {
  name: string; code: string; nature: string; aliases: string[]
  direction: string; in_minban_list: boolean; in_intl_list: boolean
  curriculum: string[]; tuition: string | null; tuition_confidence: string
  admission: string; admission_note: string; score_2025: number | null
  boarding: boolean | null; phone: string | null; postcode: string | null; website: string | null
  location: { address: string | null; confidence: string; action: string; flag?: string; lat?: number; lon?: number }
  note: string
  dist: { km: number; mins: number; over_max: boolean; label: string } | null
}
interface PrivBlock { meta: Record<string, any>; schools: PrivSchool[] }
interface VocSchool {
  name: string; type: string; address: string; addr_conf: string
  specialties: string[]; boarding: boolean | null; admission: string
  website: string | null; five_year: boolean | null; note: string
  lat?: number; lon?: number
  dist: { km: number; mins: number; over_max: boolean; label: string } | null
}
interface VocBlock { meta: Record<string, any>; schools: VocSchool[] }
interface GtProject { school: string; type: string; major: string; benke: string; plan: number; district: string }
interface GuantongBlock {
  overall: { year: number; xuezhi: string; min_score: number; huji: string; batch: string; total_plan: number }
  projects: GtProject[]; data_warning: string; source_T1: string; official_url: string
}
interface Result {
  district: string; rank: number; home: string | null
  home_coord: [number, number] | null; mode: string; mode_label: string
  max_km: number | null; boarding: boolean; interests: string[] | null
  admission_source: string | null
  bands: Record<string, Card[]>; public_list: PubSchool[]
  private_schools: PrivBlock | null
  vocational: VocBlock | null
  guantong: GuantongBlock | null
  points: Point[]; private: Point[]
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
const tab = ref<'map' | 'list' | 'minban' | 'intl' | 'voc' | 'gt' | 'xed' | 'draft'>('map')   // +贯通+校额到校
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
  const fg = contrastText(color)
  return L.divIcon({
    className: '', iconSize: [24, 24], iconAnchor: [12, 24],
    html: `<div style="position:relative;width:24px;height:24px">`
      + `<div style="background:${color};width:24px;height:24px;border-radius:50% 50% 50% 0;`
      + `transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);`
      + `display:flex;align-items:center;justify-content:center;">`
      + `<span class="lbl" style="transform:rotate(45deg);font-size:11px;font-weight:700;color:${fg}">${txt}</span></div>`
      + (boarding ? boardBadge : '') + `</div>`,
  })
}
// 按背景亮度自动取对比文字色（深色 pin 用白字、浅色 pin 用深字），避免“家”等字看不见
function contrastText(hex: string): string {
  const c = hex.replace('#', '')
  if (c.length < 6) return '#fff'
  const r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16)
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return lum > 0.6 ? '#1f2937' : '#fff'
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

/* ---------------- 民办 / 国际清单 ---------------- */
const privAll = computed<PrivSchool[]>(() => result.value?.private_schools?.schools || [])
const minbanList = computed<PrivSchool[]>(() => privAll.value.filter(s => s.in_minban_list))
const intlList = computed<PrivSchool[]>(() => privAll.value.filter(s => s.in_intl_list))
// 当前展示的民办/国际清单（按激活的 Tab）
const privView = computed<PrivSchool[]>(() => tab.value === 'intl' ? intlList.value : minbanList.value)
const vocList = computed<VocSchool[]>(() => result.value?.vocational?.schools || [])
const gtBlock = computed<GuantongBlock | null>(() => result.value?.guantong || null)
function shortCampusName(name: string): string {
  // 去掉"北京市朝阳区"前缀让表格更紧凑
  return (name || '').replace(/^北京市朝阳区/, '').replace(/^北京市/, '')
}

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

    <!-- 升学渠道科普（折叠） -->
    <section class="guide">
      <button class="guide-head" type="button" @click="showGuide = !showGuide">
        <span>📖 北京中考升学有哪些渠道？（提招 / 校额到校 / 统招 / 贯通 / 中职…）</span>
        <span class="guide-toggle">{{ showGuide ? '收起 ▲' : '展开 ▼' }}</span>
      </button>
      <div v-show="showGuide" class="guide-body">
        <div v-for="(g, i) in GUIDE" :key="i" class="g-item" :class="{ open: openG === i }">
          <button class="g-q" type="button" @click="openG = openG === i ? null : i">
            <span>{{ g.t }}</span><span class="g-chev">{{ openG === i ? '−' : '+' }}</span>
          </button>
          <div v-show="openG === i" class="g-a" v-html="g.h"></div>
        </div>
      </div>
    </section>

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
      <!-- 标签页：地图 / 普高清单 / 志愿草表 -->
      <div class="tabs" role="tablist">
        <button class="tab" :class="{ on: tab === 'map' }" @click="tab = 'map'">
          <span class="tab-ic">📍</span>志愿地图
        </button>
        <button class="tab" :class="{ on: tab === 'list' }" @click="tab = 'list'">
          <span class="tab-ic">🏫</span>普高清单<span class="tab-cnt">{{ result.public_list.length }}</span>
        </button>
        <button v-if="minbanList.length" class="tab" :class="{ on: tab === 'minban' }" @click="tab = 'minban'">
          <span class="tab-ic">🏛️</span>民办普高<span class="tab-cnt">{{ minbanList.length }}</span>
        </button>
        <button v-if="intlList.length" class="tab" :class="{ on: tab === 'intl' }" @click="tab = 'intl'">
          <span class="tab-ic">🌐</span>国际学校<span class="tab-cnt">{{ intlList.length }}</span>
        </button>
        <button v-if="vocList.length" class="tab" :class="{ on: tab === 'voc' }" @click="tab = 'voc'">
          <span class="tab-ic">🛠️</span>中职/职教<span class="tab-cnt">{{ vocList.length }}</span>
        </button>
        <button v-if="gtBlock" class="tab" :class="{ on: tab === 'gt' }" @click="tab = 'gt'">
          <span class="tab-ic">🎓</span>贯通培养<span class="tab-cnt">{{ gtBlock.projects.length }}</span>
        </button>
        <button class="tab" :class="{ on: tab === 'xed' }" @click="tab = 'xed'">
          <span class="tab-ic">🎯</span>校额到校
        </button>
        <button class="tab" :class="{ on: tab === 'draft' }" @click="tab = 'draft'">
          <span class="tab-ic">📝</span>志愿草表<span class="tab-cnt">{{ filledSlots }}/{{ ZHIYUAN_SLOTS }}</span>
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

      <!-- TAB 2：普高（统招公办）清单 -->
      <div class="listwrap" v-show="tab === 'list'">
        <p class="list-note">
          全{{ result.district }}统招公办普高{{ result.public_list.length }}所，按 2025 录取位次升序。
          <b>录取位次</b>跨年可比（分数因总分调整不可比）；<b>住宿</b>派生自 bjeea 2025 计划册；
          <b>地址</b>低可信/有提示的请以学校官方/电话为准。
        </p>
        <div class="table-scroll">
          <table class="list-table">
            <thead>
              <tr>
                <th>学校</th><th>层次</th><th>档位</th>
                <th class="num">录取位次<small>2025</small></th>
                <th>住宿</th><th>通勤</th><th>地址</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in result.public_list" :key="p.name" :class="{ unreach: !p.reportable }">
                <td class="t-name">
                  {{ cleanName(p.name) }}
                  <span v-if="p.coop" class="mini-bdg b-coop">国际/合作</span>
                </td>
                <td class="t-lvl">{{ p.level }}</td>
                <td><span class="t-band" :class="'band-' + p.band">{{ p.band }}</span></td>
                <td class="num"><b>{{ p.ref_rank }}</b></td>
                <td>
                  <span v-if="p.boarding" class="t-yes">🛏 可住</span>
                  <span v-else class="t-no">—</span>
                </td>
                <td class="t-dist">
                  <template v-if="p.nearest">
                    {{ p.nearest.km }}km
                    <span v-if="p.over_max && !p.boarding" class="t-over">超上限</span>
                  </template>
                  <span v-else class="t-no">—</span>
                </td>
                <td class="t-addr">
                  {{ p.address || '—' }}
                  <span v-if="p.address && !p.address_exact" class="addr-tag" title="非精确门牌，需核验">概址</span>
                  <span v-if="p.address_confidence === 'low'" class="addr-tag warn" title="低可信，请以官方为准">待核</span>
                  <span v-if="p.address_flag" class="addr-flag" :title="p.address_flag">⚠️</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="list-tip">⚠️ 标「待核 / 概址 / ⚠️」的地址来自非权威或迁址提示，报到校区请以招生简章与学校电话确认。</p>
      </div>

      <!-- TAB 3/4：民办普高 / 国际学校 清单（共用表格，按 Tab 过滤）-->
      <div class="listwrap" v-show="tab === 'minban' || tab === 'intl'">
        <p class="list-note" v-if="result.private_schools">
          <template v-if="tab === 'minban'">朝阳区<b>民办</b>高中（含国内高考方向 / 双轨）{{ minbanList.length }} 所。</template>
          <template v-else>朝阳区<b>国际 / 双语</b>高中（国际课程 / 出国方向）{{ intlList.length }} 所。</template>
          地址/电话/住宿来自 <b>bjeea 2025 官方统招计划册</b>；<b>办学性质 / 方向 / 课程 / 学费</b>为公开网络交叉核验
          （多为升学平台口径，约 2024–2025，<b>仅供参考</b>）；民办校无公开统一中考录取分数线，多为<b>自主招生 / 面试</b>。
        </p>
        <div class="table-scroll">
          <table class="list-table">
            <thead>
              <tr>
                <th>学校</th><th>方向</th><th>课程体系</th>
                <th>学费<small>万/年·参考</small></th>
                <th>住宿</th><th>通勤</th><th>地址</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in privView" :key="p.code">
                <td class="t-name">{{ shortCampusName(p.name) }}</td>
                <td>
                  <span class="t-dir" :class="'dir-' + p.direction">{{ p.direction === 'unknown' ? '待核' : p.direction }}</span>
                </td>
                <td class="t-curr">
                  <span v-if="p.curriculum.length">{{ p.curriculum.join('·') }}</span>
                  <span v-else class="t-no">—</span>
                </td>
                <td class="t-fee">
                  <template v-if="p.tuition">{{ p.tuition }}
                    <span v-if="p.tuition_confidence === 'low'" class="addr-tag warn" title="可信度低，请向招生办核实">待核</span>
                  </template>
                  <span v-else class="t-no">—</span>
                </td>
                <td>
                  <span v-if="p.boarding === true" class="t-yes">🛏 可住</span>
                  <span v-else-if="p.boarding === false" class="t-no">不住</span>
                  <span v-else class="addr-tag" title="未核实">待核</span>
                </td>
                <td class="t-dist">
                  <template v-if="p.dist">
                    {{ p.dist.km }}km
                    <span v-if="p.dist.over_max" class="t-over">超上限</span>
                  </template>
                  <span v-else class="t-no">—</span>
                </td>
                <td class="t-addr">
                  {{ p.location.address || '—' }}
                  <span v-if="p.location.confidence !== 'high'" class="addr-tag" title="地址仅到路/片区，需核验">概址</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="list-tip">
          ⚠️ <b>学费仅供参考</b>：随学年/班型/课程方向变动，且多为升学平台口径而非学校官网逐字，务必以学校招生办当年公布为准。
          「双轨」校在<b>民办普高</b>与<b>国际学校</b>两个清单中都会出现（分别对应其国内 / 国际方向）。
          数据来源：{{ result.private_schools?.meta?.source_T1 }}（{{ result.private_schools?.meta?.collected }}）。
        </p>
      </div>

      <!-- TAB 6：中职 / 职教（校址在朝阳）-->
      <div class="listwrap" v-show="tab === 'voc'" v-if="result.vocational">
        <p class="list-note">
          校址在<b>朝阳区</b>的中职 {{ vocList.length }} 所（中专 / 职高，含 1 所特教校）。
          名单取自<b>北京市教委 2025 具招生资格中等职业学校名单</b>。
          <span class="g-warn" style="display:inline-block;margin-top:6px">{{ result.vocational.meta.guantong_note }}</span>
        </p>
        <div class="table-scroll">
          <table class="list-table">
            <thead>
              <tr><th>学校</th><th>类型</th><th>特色专业</th><th>3+2</th><th>住宿</th><th>通勤</th><th>地址</th></tr>
            </thead>
            <tbody>
              <tr v-for="v in vocList" :key="v.name">
                <td class="t-name">{{ shortCampusName(v.name) }}</td>
                <td><span class="t-dir" :class="v.type.includes('中专') ? 'dir-国内' : 'dir-双轨'">{{ v.type }}</span></td>
                <td class="t-curr">
                  <span v-if="v.specialties.length">{{ v.specialties.join('·') }}</span>
                  <span v-else class="t-no">—</span>
                </td>
                <td>
                  <span v-if="v.five_year === true" class="t-yes">有</span>
                  <span v-else class="t-no">—</span>
                </td>
                <td>
                  <span v-if="v.boarding === true" class="t-yes">🛏 可住</span>
                  <span v-else class="addr-tag" title="未核实">待核</span>
                </td>
                <td class="t-dist">
                  <template v-if="v.dist">{{ v.dist.km }}km<span v-if="v.dist.over_max" class="t-over">超上限</span></template>
                  <span v-else class="t-no">—</span>
                </td>
                <td class="t-addr">
                  {{ v.address }}
                  <span v-if="v.addr_conf !== 'high'" class="addr-tag" title="需核验">概址</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="list-tip">
          ⚠️ {{ result.vocational.meta.coverage_note }} 数据来源：{{ result.vocational.meta.source_T1 }}。
          中职升学出口：单考单招 / 高职单招 / 3+2 直升大专 / 贯通转段升本科（详见顶部「升学渠道说明」）。
        </p>
      </div>

      <!-- TAB 7：贯通培养（全市招生）-->
      <div class="listwrap" v-show="tab === 'gt'" v-if="gtBlock">
        <p class="list-note">
          <b>贯通培养</b>＝<b>7 年学制 → 本科</b>（中职/高职段 + 本科段，专升本性质）。{{ gtBlock.overall.year }} 年全市
          <b>{{ gtBlock.projects.length }}</b> 个项目 / 8 所承办院校，计划合计 <b>{{ gtBlock.overall.total_plan }}</b> 人。
          <span class="g-warn" style="display:inline-block;margin-top:6px">
            ⚠️ 报考门槛：中考总分 ≥ <b>{{ gtBlock.overall.min_score }}</b> 分；<b>{{ gtBlock.overall.huji }}</b>；在<b>{{ gtBlock.overall.batch }}</b>录取。全市招生不分区，朝阳京籍考生均可报。
          </span>
        </p>
        <div class="table-scroll">
          <table class="list-table">
            <thead>
              <tr><th>承办院校</th><th>类型</th><th>中职/高职专业</th><th>对接本科（高校·专业）</th><th class="num">计划</th><th>校区(区)</th></tr>
            </thead>
            <tbody>
              <tr v-for="(p, i) in gtBlock.projects" :key="i">
                <td class="t-name">{{ shortCampusName(p.school) }}</td>
                <td><span class="t-dir" :class="p.type === '中本贯通' ? 'dir-双轨' : 'dir-国际'">{{ p.type }}</span></td>
                <td class="t-curr">{{ p.major }}</td>
                <td class="t-curr">{{ p.benke }}</td>
                <td class="num"><b>{{ p.plan }}</b></td>
                <td class="t-dist">{{ p.district }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="list-tip">
          数据来源：{{ gtBlock.source_T1 }}（<a :href="gtBlock.official_url" target="_blank" rel="noopener">官方通知</a>，计划合计 {{ gtBlock.overall.total_plan }} 人逐项核验一致）。
          中本贯通=中职校+本科高校；高本贯通=高职院校+本科高校。各专业代码/对接本科以官方简章为准；2026 计划发布后须刷新。
        </p>
      </div>

      <!-- TAB 8：校额到校（指标分配批次）-->
      <div class="listwrap" v-show="tab === 'xed'">
        <div class="xed-intro">
          <h3>🎯 校额到校（指标分配批次）</h3>
          <p>优质高中拿出名额<b>定向分配到每所初中校、校内竞争</b>录取——同校学生之间按中考总分从高到低排名，<b>不是全区竞争</b>。所以"普通初中"的孩子，反而更可能用相对低的分数进入优质高中。</p>
          <div class="xed-rules">
            <div class="xed-rule"><span class="xed-k">报考门槛(2025)</span>中考总分 ≥ <b>430/510</b> + 综合素质评价 ≥ <b>B</b> 等</div>
            <div class="xed-rule"><span class="xed-k">学籍要求</span>具普高升学资格 + <b>同一初中连续三年学籍</b>的应届生</div>
            <div class="xed-rule"><span class="xed-k">不能报</span>往届生 / 回户籍 / 外省回京 考生</div>
            <div class="xed-rule"><span class="xed-k">录取分</span>无官方"各初中录取线"——按本校内排名事后形成，逐校逐年不同；430 仅是统一资格门槛</div>
          </div>
          <p class="xed-hl">📋 下方为<b>北京教育考试院官方</b>《2025 年初中学校校额到校分配名额》中的<b>朝阳区</b>页：在表中找到孩子的<b>初中校</b>那一行，对应各优质高中列的数字＝该校能分到的名额数。</p>
        </div>
        <div class="xed-imgs">
          <a :href="XED_OFFICIAL" target="_blank" rel="noopener"><img src="/xed/chaoyang-xeddx-2025-p1.jpg" alt="朝阳校额到校分配名额 第1页" loading="lazy" /></a>
          <a :href="XED_OFFICIAL" target="_blank" rel="noopener"><img src="/xed/chaoyang-xeddx-2025-p2.jpg" alt="朝阳校额到校分配名额 第2页（上半部分为朝阳）" loading="lazy" /></a>
        </div>
        <p class="list-tip">
          ⚠️ 上图为官方原图（朝阳区；第 2 页上半部分为朝阳、下半为丰台）。名额数字<b>请以官方原图为准</b>，本系统不另行转录以免出错。
          原始来源：<a :href="XED_OFFICIAL" target="_blank" rel="noopener">北京教育考试院《2025年初中学校校额到校分配名额》</a>（2025-07-01，每年 7 月初更新）。
          录取按校内总分排名 + 志愿顺序；2026 计划发布后须刷新。
        </p>
      </div>

      <!-- TAB 8：志愿草表（统招 12×2），镜像官方填报 -->
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

/* 升学渠道科普折叠 */
.guide { margin-bottom: 12px; }
.guide-head { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px;
  background: var(--surface); border: 1px solid var(--gray-200); border-radius: var(--radius-sm);
  padding: 11px 14px; font-size: 13.5px; font-weight: 600; color: var(--brand-dark); cursor: pointer;
  text-align: left; box-shadow: var(--shadow-sm); }
.guide-head:hover { border-color: var(--brand); }
.guide-toggle { flex-shrink: 0; font-size: 12px; color: var(--gray-500); font-weight: 400; }
.guide-body { margin-top: 8px; background: var(--surface); border: 1px solid var(--gray-100);
  border-radius: var(--radius-sm); overflow: hidden; }
.g-item { border-bottom: 1px solid var(--gray-100); }
.g-item:last-child { border-bottom: none; }
.g-q { width: 100%; display: flex; align-items: center; justify-content: space-between;
  background: none; border: none; padding: 11px 14px; font-size: 13px; font-weight: 600;
  color: var(--gray-800); cursor: pointer; text-align: left; }
.g-q:hover { background: var(--gray-50); }
.g-item.open .g-q { color: var(--brand-dark); }
.g-chev { flex-shrink: 0; font-size: 16px; color: var(--gray-400); width: 18px; text-align: center; }
.g-a { padding: 2px 14px 14px; font-size: 12.5px; color: var(--gray-700); line-height: 1.7; }
.g-a :deep(ul) { margin: 4px 0; padding-left: 18px; }
.g-a :deep(li) { margin: 2px 0; }
.g-a :deep(b) { color: var(--gray-900); }
.g-a :deep(.g-flow) { display: block; margin: 8px 0; padding: 7px 10px; background: var(--brand-50);
  color: var(--brand-dark); border-radius: var(--radius-xs); font-weight: 700; text-align: center; }
.g-a :deep(.g-warn) { display: block; margin-top: 6px; color: #b45309; background: var(--warning-bg);
  padding: 6px 9px; border-radius: var(--radius-xs); }
.g-a :deep(.g-src) { display: block; margin-top: 8px; font-size: 11px; color: var(--gray-400); }
.g-a :deep(.g-tbl) { width: 100%; border-collapse: collapse; margin: 6px 0; font-size: 12px; }
.g-a :deep(.g-tbl th), .g-a :deep(.g-tbl td) { border: 1px solid var(--gray-200); padding: 5px 8px; text-align: left; }
.g-a :deep(.g-tbl th) { background: var(--gray-50); color: var(--gray-500); font-weight: 600; }

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
  filter: grayscale(0.88) brightness(1.85) contrast(0.75) saturate(0.55);
  opacity: 0.82;
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

/* 标签页：贴着内容卡片的页签条（活动页签连到内容区，强化“翻页”感）*/
.tabs { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 4px; }
.tab { position: relative; font-size: 14px; font-weight: 600; padding: 10px 16px 12px; white-space: nowrap;
  border: 1px solid transparent; border-bottom: none; background: transparent; color: var(--gray-500);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0; cursor: pointer;
  display: flex; align-items: center; gap: 6px; transition: color .15s, background .15s; }
.tab .tab-ic { font-size: 15px; }
.tab:hover { color: var(--gray-800); background: var(--gray-50); }
.tab.on { color: var(--brand-dark); background: var(--surface);
  border-color: var(--gray-100); box-shadow: 0 -2px 6px rgba(0, 0, 0, .04); }
/* 活动页签底部色条 + 用一条白线盖住下方边框，形成与内容连为一体的效果 */
.tab.on::after { content: ''; position: absolute; left: 0; right: 0; top: 0; height: 3px;
  background: var(--brand); border-radius: 3px 3px 0 0; }
.tab.on::before { content: ''; position: absolute; left: 0; right: 0; bottom: -1px; height: 2px;
  background: var(--surface); }
.tab-cnt { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: var(--radius-full);
  background: var(--gray-100); color: var(--gray-500); }
.tab.on .tab-cnt { background: var(--brand-50); color: var(--brand-dark); }
/* 内容卡片统一顶边，跟页签条衔接 */
.results .mapwrap, .results .listwrap, .results .draftwrap {
  border: 1px solid var(--gray-100); border-radius: 0 var(--radius) var(--radius) var(--radius); }

/* 徽标颜色复用 */
.bdg { font-size: 11px; padding: 1px 7px; border-radius: var(--radius-full); }
.b-board { background: #ede9fe; color: #6d28d9; }
.b-coop { background: #e0f2fe; color: #0369a1; }
.b-match { background: #d1fae5; color: #047857; }

/* 普高清单表格 */
.listwrap { background: var(--surface); box-shadow: var(--shadow-sm); padding: 16px; }
.list-note { font-size: 12.5px; color: var(--gray-600); margin-bottom: 12px; line-height: 1.6; }
.table-scroll { overflow-x: auto; border: 1px solid var(--gray-100); border-radius: var(--radius-sm); }
.list-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 640px; }
.list-table thead th { position: sticky; top: 0; background: var(--gray-50); text-align: left;
  font-size: 11.5px; font-weight: 700; color: var(--gray-500); padding: 9px 12px;
  border-bottom: 1px solid var(--gray-200); white-space: nowrap; }
.list-table th small { font-weight: 400; color: var(--gray-400); margin-left: 3px; }
.list-table th.num, .list-table td.num { text-align: right; }
.list-table td { padding: 9px 12px; border-bottom: 1px solid var(--gray-50); color: var(--gray-700);
  vertical-align: top; }
.list-table tbody tr:hover { background: var(--brand-50); }
.list-table tr.unreach { color: var(--gray-400); }
.list-table tr.unreach .t-name { color: var(--gray-500); }
.t-name { font-weight: 600; color: var(--gray-900); white-space: nowrap; }
.t-lvl { font-size: 12px; color: var(--gray-500); white-space: nowrap; }
.list-table td:nth-child(3) { white-space: nowrap; }
.t-band { display: inline-block; min-width: 20px; text-align: center; font-size: 11px; font-weight: 700;
  padding: 1px 6px; border-radius: var(--radius-xs); white-space: nowrap; }
.band-冲 { background: #fde8e6; color: #c0392b; }
.band-稳 { background: #fdf3d4; color: #9a7d0a; }
.band-保 { background: #d8f5e3; color: #1e8e4e; }
.band-够不上 { background: var(--gray-100); color: var(--gray-400); }
.t-yes { color: #6d28d9; font-size: 12px; white-space: nowrap; }
.t-no { color: var(--gray-300); }
.t-dist { white-space: nowrap; font-size: 12.5px; }
.t-over { color: var(--accent); font-size: 11px; margin-left: 4px; }
.t-addr { font-size: 12px; color: var(--gray-600); line-height: 1.5; min-width: 180px; }
.t-dir { display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: var(--radius-xs); white-space: nowrap; }
.dir-国内 { background: #d8f5e3; color: #1e8e4e; }
.dir-双轨 { background: #e0e7ff; color: #4338ca; }
.dir-国际 { background: #e0f2fe; color: #0369a1; }
.dir-unknown { background: var(--gray-100); color: var(--gray-400); }
.t-curr { font-size: 12px; color: var(--gray-600); line-height: 1.5; min-width: 150px; }
.t-fee { font-size: 12px; color: var(--gray-800); line-height: 1.5; min-width: 140px; white-space: normal; }
.mini-bdg { font-size: 10px; padding: 0 5px; border-radius: var(--radius-xs); margin-left: 4px; }
.addr-tag { font-size: 10px; padding: 0 5px; border-radius: var(--radius-xs); margin-left: 4px;
  background: var(--gray-100); color: var(--gray-500); }
.addr-tag.warn { background: var(--warning-bg); color: #b45309; }
.addr-flag { margin-left: 3px; cursor: help; }
.list-tip { font-size: 11px; color: var(--gray-400); margin-top: 10px; line-height: 1.5; }

/* 校额到校 */
.xed-intro h3 { font-size: 16px; color: var(--brand-deeper); margin: 0 0 8px; }
.xed-intro > p { font-size: 13px; color: var(--gray-700); line-height: 1.7; margin: 0 0 10px; }
.xed-rules { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.xed-rule { font-size: 12.5px; color: var(--gray-700); line-height: 1.5; background: var(--gray-50);
  border-radius: var(--radius-xs); padding: 7px 10px; }
.xed-k { display: inline-block; min-width: 92px; font-weight: 700; color: var(--brand-dark); }
.xed-hl { font-size: 12.5px; color: var(--brand-dark); background: var(--brand-50);
  border-radius: var(--radius-xs); padding: 9px 11px; line-height: 1.6; margin: 0 0 12px; }
.xed-imgs { display: flex; flex-direction: column; gap: 10px; }
.xed-imgs img { width: 100%; height: auto; border: 1px solid var(--gray-200); border-radius: var(--radius-xs);
  display: block; }
.list-tip a { color: var(--brand-dark); }

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
