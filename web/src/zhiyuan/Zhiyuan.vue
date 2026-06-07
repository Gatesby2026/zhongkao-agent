<script setup lang="ts">
import { ref, reactive, computed, nextTick, watch } from 'vue'
import { USER_DEFAULTS } from './user-defaults'

declare const L: any

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
    '<ul><li><b>贯通培养</b>：380 分门槛，8 个志愿（详见"贯通 vs 五年制"；<b>2026 起并入统一招生</b>）</li>' +
    '<li><b>特长生</b>：体育/艺术各 ≤ 招生计划 4%，科技 ≤ 2%</li>' +
    '<li><b>中职自主招生</b>（专业测试录取，中考分只记合格/不合格）</li>' +
    '<li><b>登记入学、自主招生</b>也在这一阶段处理</li></ul>' },
  { t: '② 指标分配（校额到校 + 市级统筹）', h:
    '中间批次，8 志愿×2 专业。<br>' +
    '<b>校额到校</b>：优质高中名额<b>定向分到每所初中，校内竞争</b>（同校学生比，不是全区比）。门槛＝<b>连续三年本校学籍 + 综合素质 B + 中考总分达线</b>（2025 = 430/510 ≈ 84%）。' +
    '<span class="g-warn">往届生、外省回京、回户籍报考者不能报。</span><br>' +
    '<b>市级统筹（一/二/三）</b>：优质资源跨区招生（统筹一不在东西海招、统筹二名校郊区分校面向全市、统筹三高校与普高联合培养）。' },
  { t: '③ 统一招生（统招，本系统核心）', h:
    '最后批次，按总分从高到低、依志愿录取。<b>12 个志愿 × 每志愿 2 专业</b>——<b>这就是本系统的"志愿草表"</b>。<br>' +
    '<b>中外合作办学项目</b>自 2025 年起<b>按统一招生模式录取</b>（不在提前招生）：填志愿前先做外语资格性测试，合格后在统招批次按志愿+分数录取。' },
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
// 校额到校：按初中查名额
const showXedImg = ref(false)
const xedQuery = ref(USER_DEFAULTS.chuzhong)
const batchOpen = reactive({ early: false, ind: false, uni: false })   // 三批次默认折叠
const xedBlock = computed<XeddxBlock | null>(() => result.value?.xeddx || null)
const xedSel = computed<XeddxRow | null>(() => {
  const b = xedBlock.value; const q = xedQuery.value.trim()
  if (!b || !q) return null
  return b.rows.find(r => r.name === q) || b.rows.find(r => cleanName(r.name).includes(cleanName(q))) || null
})

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
interface XeddxRow { code: string; name: string; total: number; by_school: Record<string, number> | null; verified: boolean }
interface XeddxBlock {
  columns: string[]; source_T1: string; official_url: string; data_warning: string
  verified_count: number; total_count: number; rows: XeddxRow[]
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
  xeddx: XeddxBlock | null
  points: Point[]; private: Point[]
}

const form = reactive({
  rank: USER_DEFAULTS.rank,
  home: USER_DEFAULTS.home,
  mode: USER_DEFAULTS.mode,
  max_km: USER_DEFAULTS.max_km,
  boarding: USER_DEFAULTS.boarding,
  identity: USER_DEFAULTS.identity,   // 京籍应届/非京籍/往届
})
const IDENTITIES = [
  { v: 'jjyj', label: '京籍应届' },
  { v: 'feijing', label: '非京籍' },
  { v: 'wangjie', label: '往届/回京' },
]
// 学校类型图层开关（地图上显示哪些点）
const layers = reactive({ gongban: true, coop: true, minban: false, intl: false, voc: false, gt: false, tc: false, xed: false })
// 一级导航：地图 / 草表 / 查学校(统一浏览器) / 渠道科普
type TabKey = 'map' | 'draft' | 'explore' | 'channels'
const tab = ref<TabKey>('map')
function goTab(t: TabKey) { tab.value = t }
const chSub = ref<'guide' | 'xed' | 'tc'>('guide')   // 渠道科普子页
const loading = ref(false)
const errMsg = ref('')
const result = ref<Result | null>(null)
let mapInst: any = null
let publicLayer: any = null
let minbanLayer: any = null
let intlLayer: any = null
let vocLayer: any = null
let gtLayer: any = null
let tcLayer: any = null
let xedLayer: any = null
// 民办校名 → {民办?, 国际?} 标记（用于地图拆层）
const privFlags = computed<Record<string, { minban: boolean; intl: boolean }>>(() => {
  const m: Record<string, { minban: boolean; intl: boolean }> = {}
  for (const s of (result.value?.private_schools?.schools || []))
    m[s.name] = { minban: !!s.in_minban_list, intl: !!s.in_intl_list }
  return m
})

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
      identity: form.identity,
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
const selectedTc = ref<any>(null)   // 选中统筹校时的结构化数据（右侧详情用）
const selectedNew = ref<any>(null)  // 选中 2026 新校时的结构化数据
function selectPoint(p: Point) { selectedPoint.value = p; selectedTc.value = null; selectedNew.value = null }
// 由点位反查冲稳保卡片：多校区点名形如 "和平街一中·和平街校区(...)"，取 · 前主名匹配
function cardOfPoint(p: Point | null): Card | null {
  if (!p) return null
  const base = p.name.split('·')[0]
  return findCard(base) || findCard(p.name)
}
const selCard = computed<Card | null>(() => cardOfPoint(selectedPoint.value))
const boardBadge = '<span class="bd-badge" title="可寄宿/有住宿">宿</span>'
function pin(color: string, txt: string, boarding = false, corner = '') {
  const fg = contrastText(color)
  return L.divIcon({
    className: '', iconSize: [24, 24], iconAnchor: [12, 24],
    html: `<div style="position:relative;width:24px;height:24px">`
      + `<div style="background:${color};width:24px;height:24px;border-radius:50% 50% 50% 0;`
      + `transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);`
      + `display:flex;align-items:center;justify-content:center;">`
      + `<span class="lbl" style="transform:rotate(45deg);font-size:11px;font-weight:700;color:${fg}">${txt}</span></div>`
      + (boarding ? boardBadge : '')
      + (corner ? `<span class="qt-badge" title="校额到校名额">${corner}</span>` : '')
      + `</div>`,
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
// 校额到校简称 → 我方数据全名（取统招位次用）
const XED_FULLNAME: Record<string, string> = {
  '八十中': '北京市第八十中学', '陈经纶': '陈经纶中学', '日坛': '日坛中学',
  '和平街(和平街)': '和平街一中', '和平街(莲葩园)': '和平街一中（北苑莲葩园校区）',
  '对外经贸94中': '对外经济贸易大学附属中学', '十七中': '北京十七中', '工大附中': '北京工业大学附属中学',
  '人朝': '人大附中朝阳学校', '东方德才': '东方德才学校', '东师朝': '东北师大附中朝阳学校', '清华朝阳': '清华附中朝阳学校',
}
// 选定初中(xedQuery，缺省朝外)分到各优质高中的校额到校名额：全名→名额。
// 供地图 pin 徽标 + 学校详情卡展示（校额到校目标校全在朝阳，已是图上已有 pin）。
const xedQuotaByName = computed<Record<string, number>>(() => {
  const r = xedSel.value
  if (!r || !r.by_school) return {}
  const out: Record<string, number> = {}
  for (const [abbr, n] of Object.entries(r.by_school)) {
    const full = XED_FULLNAME[abbr]
    if (full) out[full] = (out[full] || 0) + (n as number)
  }
  return out
})
// 校额到校研判（按统筹方式）：高中统招位次 vs 孩子区排 → worth(值得冲)/similar(相当)/waste(统招可达)。
// 全名→{tag,color}，供地图 pin 着色 + 详情卡显示。自包含(不依赖后置的 xedRecommend)。
const XED_TAG_COLOR: Record<string, string> = { worth: '#e74c3c', similar: '#2ecc71', waste: '#95a5a6', unknown: '#2980b9' }
const XED_BAND: Record<string, string> = { worth: '冲', similar: '稳', waste: '达', unknown: '?' }  // 地图 pin 简标(达=统招可达)
const xedJudgeByName = computed<Record<string, { tag: string; color: string; ref: number | null }>>(() => {
  const r = xedSel.value
  const m: Record<string, { tag: string; color: string; ref: number | null }> = {}
  if (!r || !r.by_school) return m
  const rank = Number(form.rank) || 0
  const byName: Record<string, any> = {}
  ;(result.value?.public_list || []).forEach((p: any) => { byName[p.name] = p })
  for (const abbr of Object.keys(r.by_school)) {
    const full = XED_FULLNAME[abbr]
    if (!full) continue
    const card = byName[full]
    const ref = card && typeof card.ref_rank === 'number' ? card.ref_rank : null
    let tag = 'unknown'
    if (ref != null && rank) tag = ref <= rank * 0.95 ? 'worth' : ref >= rank * 1.1 ? 'waste' : 'similar'
    m[full] = { tag, color: XED_TAG_COLOR[tag], ref }
  }
  return m
})
// 该点是不是中外合作/国际班学校（用于 coop 图层过滤）
function isCoopPoint(p: Point): boolean {
  const c = findCard(p.name)
  return !!(c && c.coop)
}
function renderMarkers() {
  const res = result.value
  if (!res || !mapInst) return
  for (const lyr of [publicLayer, minbanLayer, intlLayer, vocLayer, gtLayer, tcLayer, xedLayer])
    if (lyr) mapInst.removeLayer(lyr)
  publicLayer = minbanLayer = intlLayer = vocLayer = gtLayer = tcLayer = xedLayer = null
  const bounds: any[] = []
  if (res.home_coord) bounds.push(res.home_coord)

  publicLayer = L.layerGroup()
  res.points.forEach((p) => {
    // 公办普高图层（中外合作校并入其中，不再单独图层；详情仍标“🌐中外合作班”）
    if (!layers.gongban) return
    bounds.push([p.lat, p.lon])
    const boarding = !!cardOfPoint(p)?.boarding
    const icon = p.kind === 'full' ? pin(p.color, p.band, boarding) : smallIcon(p.color, boarding)
    const mk = L.marker([p.lat, p.lon], { icon }).addTo(publicLayer).on('click', () => selectPoint(p))
    // 缺省常驻显示学校名：重点推荐校(冲/稳/保)常驻，其余小点悬停显示，避免拥挤
    const lbl = shortName(p.name)
    if (p.kind === 'full') {
      mk.bindTooltip(lbl, { permanent: true, direction: 'bottom', offset: [0, 2], className: 'map-lbl' })
    } else {
      mk.bindTooltip(lbl, { direction: 'top', offset: [0, -6], className: 'map-lbl' })
    }
  })
  // 2026 新增公办普高：随"公办普高"图层显示，用"新"pin（有住宿带"宿"角标），无研判
  ;((res as any).new_schools?.schools || []).forEach((s: any) => {
    if (!s.lat || !s.lon) return
    const np: Point = {
      name: s.name, lat: s.lat, lon: s.lon, kind: 'small', color: '#8e44ad',
      band: '新', level: '2026 新增·无历史线', rank: '—', margin: '—',
      dist: s.dist ? `${s.dist.km}km · ${s.dist.mins}分钟（${s.dist.label}）` : '距离未知',
      hist: '', style: '', note: '', reason: '', tags: [], gaokao: '', matched: [],
    }
    L.marker([s.lat, s.lon], { icon: pin('#8e44ad', '新', s.boarding === true) }).addTo(publicLayer)
      .on('click', () => { selectPoint(np); selectedNew.value = s })
      .bindTooltip(shortName(s.name), { permanent: true, direction: 'bottom', offset: [0, 2], className: 'map-lbl' })
    if (layers.gongban) bounds.push([s.lat, s.lon])
  })
  if (layers.gongban) publicLayer.addTo(mapInst)

  // 民办/国际：按标拆两层（同一所若既民办又国际，两层都画）
  minbanLayer = L.layerGroup()
  intlLayer = L.layerGroup()
  const flags = privFlags.value
  res.private.forEach((p) => {
    const f = flags[p.name] || { minban: true, intl: false }
    const mk = (color: string) => L.marker([p.lat, p.lon], { icon: smallIcon(color) })
      .on('click', () => selectPoint(p))
      .bindTooltip(shortName(p.name), { direction: 'top', offset: [0, -6], className: 'map-lbl' })
    if (f.intl) mk('#9b59b6').addTo(intlLayer)
    if (f.minban || (!f.minban && !f.intl)) mk('#e67e22').addTo(minbanLayer)
    if (layers.minban || layers.intl) bounds.push([p.lat, p.lon])
  })
  if (layers.minban) minbanLayer.addTo(mapInst)
  if (layers.intl) intlLayer.addTo(mapInst)

  // 中职/职教（默认关）—— 点击走右侧详情面板（同普高）
  vocLayer = L.layerGroup()
  ;(res.vocational?.schools || []).forEach((s: any) => {
    if (!s.lat || !s.lon) return
    const vp: Point = {
      name: s.name, lat: s.lat, lon: s.lon, kind: 'small', color: '#16a085',
      band: '中职', level: s.type || '中职/职教', rank: '—', margin: '—',
      dist: s.dist ? `${s.dist.km}km · ${s.dist.mins}分钟（${s.dist.label}）${s.dist.over_max ? ' ⚠️超通勤上限' : ''}` : '距离未知',
      hist: '',
      style: (s.specialties && s.specialties.length) ? '专业：' + s.specialties.join('·') : '',
      note: [s.address, s.five_year ? '含五年制(3+2)→大专' : '', s.note].filter(Boolean).join(' · '),
      reason: '', tags: [], gaokao: '', matched: [],
    }
    L.marker([s.lat, s.lon], { icon: smallIcon('#16a085') }).addTo(vocLayer)
      .on('click', () => selectPoint(vp))
      .bindTooltip(shortName(s.name), { direction: 'top', offset: [0, -6], className: 'map-lbl' })
    if (layers.voc) bounds.push([s.lat, s.lon])
  })
  if (layers.voc) vocLayer.addTo(mapInst)

  // 贯通承办院校（全市·默认关）—— 点击走右侧详情面板（同普高）
  gtLayer = L.layerGroup()
  const gtProjects = (res.guantong as any)?.projects || []
  Object.entries((res.guantong as any)?.school_coords || {}).forEach(([nm, c]: any) => {
    if (!c?.lat || !c?.lon) return
    const approx = c.geo === 'approx' ? '（坐标近似）' : ''
    const projs = gtProjects.filter((p: any) => p.school === nm)
    const projTxt = projs.map((p: any) => `${p.type}：${p.major}→${p.benke}（${p.plan}人）`).join('；')
    const gp: Point = {
      name: nm, lat: c.lat, lon: c.lon, kind: 'small', color: '#2980b9',
      band: '贯通', level: '贯通承办院校（全市招生·7年→本科）', rank: '—', margin: '—',
      dist: '距离未知', hist: '',
      style: `承办院校 · ${c.district || ''}${approx}`,
      note: [projTxt, c.note].filter(Boolean).join('　|　'),
      reason: '', tags: [], gaokao: '', matched: [],
    }
    L.marker([c.lat, c.lon], { icon: smallIcon('#2980b9') }).addTo(gtLayer)
      .on('click', () => selectPoint(gp))
      .bindTooltip(shortName(nm), { direction: 'top', offset: [0, -6], className: 'map-lbl' })
    if (layers.gt) bounds.push([c.lat, c.lon])
  })
  if (layers.gt) gtLayer.addTo(mapInst)

  // 市级统筹（默认关）—— 26 校按研判着色，点击走右侧详情
  tcLayer = L.layerGroup()
  const tcColor: Record<string, string> = { 'tj-wen': '#2ecc71', 'tj-chong': '#e74c3c', 'tj-bo': '#e67e22', 'tj-no': '#95a5a6', 'tj-unk': '#2980b9' }
  const tcAll = [...(tongchou.value?.tongchou_er || []), ...(tongchou.value?.tongchou_yi || [])]
  tcAll.forEach((s: any) => {
    if (!s.lat || !s.lon || !s.faces_chaoyang) return
    const j = tcJudge(s)
    const tier = (tongchou.value?.tongchou_er || []).includes(s) ? '统筹二' : '统筹一'
    const color = tcColor[j.cls] || '#2980b9'
    const tp: Point = {
      name: s.name, lat: s.lat, lon: s.lon, kind: 'small', color,
      band: j.label, level: `市级统筹·${tier}${s.campus ? '（' + s.campus + '）' : ''}`, rank: '—', margin: '—',
      dist: '距离未知', hist: '', style: '', note: '', reason: '', tags: [], gaokao: '', matched: [],
    }
    // 参照普高：可冲/稳 用大 pin（带研判档），够不上/待核 用小图标
    const big = j.cls === 'tj-wen' || j.cls === 'tj-chong' || j.cls === 'tj-bo'
    const icon = big ? pin(color, j.label, s.boarding === true) : smallIcon(color, s.boarding === true)
    L.marker([s.lat, s.lon], { icon }).addTo(tcLayer)
      .on('click', () => { selectPoint(tp); selectedTc.value = { ...s, _tier: tier } })
      .bindTooltip(shortName(s.name), big
        ? { permanent: true, direction: 'bottom', offset: [0, 2], className: 'map-lbl' }
        : { direction: 'top', offset: [0, -6], className: 'map-lbl' })
    if (layers.tc) bounds.push([s.lat, s.lon])
  })
  if (layers.tc) tcLayer.addTo(mapInst)

  // 校额到校（默认关，按统筹方式）—— 有名额的朝阳优质高中用大 pin，按研判着色，标"🎯名额"
  xedLayer = L.layerGroup()
  res.points.forEach((p) => {
    const q = xedQuotaByName.value[p.name]
    if (!q) return
    const j = xedJudgeByName.value[p.name]
    const color = j ? j.color : '#95a5a6'
    const lbl = j ? XED_BAND[j.tag] : '校'
    const sboard = !!cardOfPoint(p)?.boarding
    // 参照统筹：研判作主标(冲/稳/达),名额作左上角标,住宿"宿"右上角
    L.marker([p.lat, p.lon], { icon: pin(color, lbl, sboard, String(q)) }).addTo(xedLayer)
      .on('click', () => selectPoint(p))
      .bindTooltip(shortName(p.name), { permanent: true, direction: 'bottom', offset: [0, 2], className: 'map-lbl' })
    if (layers.xed) bounds.push([p.lat, p.lon])
  })
  if (layers.xed) xedLayer.addTo(mapInst)

  if (bounds.length) mapInst.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
}
function renderMap() {
  const res = result.value
  if (!res) return
  selectedPoint.value = null
  if (mapInst) { mapInst.remove(); mapInst = null; publicLayer = minbanLayer = intlLayer = vocLayer = gtLayer = tcLayer = xedLayer = null }
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
// 初中变更 → 校额到校名额变 → 重绘 pin 徽标
watch(xedQuotaByName, () => { if (mapInst) renderMarkers() })
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
// 下拉可选学校：冲→稳→保→够不上 全部有官方代码的（够不上也列出，供手动冲刺）
const selectable = computed<Card[]>(() => {
  const res = result.value
  if (!res) return []
  const out: Card[] = []
  for (const band of ['冲', '稳', '保', '够不上']) {
    for (const c of (res.bands[band] || [])) {
      if (c.school_code) out.push(c)
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
// 市级统筹官方清单（据 2025 简章逐格核 + 合计对账）
const tongchou = computed<any>(() => result.value ? (result.value as any).tongchou : null)
const tcYi = computed<any[]>(() => (tongchou.value?.tongchou_yi || [])
  .filter((x: any) => x.faces_chaoyang).sort((a: any, b: any) => (b.quota_chaoyang || 0) - (a.quota_chaoyang || 0)))
const tcEr = computed<any[]>(() => (tongchou.value?.tongchou_er || [])
  .filter((x: any) => x.faces_chaoyang).sort((a: any, b: any) => (b.quota_chaoyang || 0) - (a.quota_chaoyang || 0)))
// 你孩子区排→估中考分（后端按本区一分一段插值）
const estScore = computed<number | null>(() => result.value ? (result.value as any).est_score : null)
// 分数→档位（估分 vs 某条统招线）。统筹实际线通常比统招线低(约20-30)，故"可够"放宽到线下20。
// 稳 Δ≥+10 / 冲 −10~+10 / 搏 −20~−10 / 够不上 <−20 / 线待核(无线)。统筹/校额共用。
function scoreBand(line: number | null): { label: string; cls: string; d: number | null } {
  if (line == null || estScore.value == null) return { label: '线待核', cls: 'tj-unk', d: null }
  const d = Math.round(estScore.value - line)
  if (d >= 10) return { label: '稳', cls: 'tj-wen', d }
  if (d >= -10) return { label: '冲', cls: 'tj-chong', d }
  if (d >= -20) return { label: '搏', cls: 'tj-bo', d }
  return { label: '够不上', cls: 'tj-no', d }
}
function tcJudge(s: any): { label: string; cls: string; d: number | null; line: number | null; ref: boolean } {
  const conf = typeof s.score_2025_tongzhao === 'number' ? s.score_2025_tongzhao : null
  const ref = typeof s.score_ref === 'number' ? s.score_ref : null
  const line = conf ?? ref
  const isRef = conf == null && ref != null
  if (line == null || estScore.value == null) return { label: '线待核', cls: 'tj-unk', d: null, line: null, ref: false }
  const band = scoreBand(line)
  const d = band.d
  return { ...band, d, line, ref: isRef }
}

// ───── 统一详情面板（§12）：把 schools_unified 记录声明式渲染 ─────
const uByName = computed<Record<string, any>>(() => {
  const m: Record<string, any> = {}
  for (const s of ((result.value as any)?.schools_unified || [])) m[s.name] = s
  return m
})
// 选中校的统一记录；公办校再按选定初中补"校额到校"渠道（依赖前端 xedQuery）
const selSchool = computed<any>(() => {
  const p = selectedPoint.value
  if (!p) return null
  const base = uByName.value[p.name]
  if (!base) return null
  const s = { ...base, channels: [...(base.channels || [])] }
  const q = xedQuotaByName.value[p.name]
  if (q && s.type === '公办普高') {
    s.channels.push({ channel: '校额到校', metric: { kind: 'in_school_rank' }, quota: q,
      _xedtag: (xedJudgeByName.value[p.name] || {}).tag || 'unknown' })
  }
  return s
})
const PUB_BAND_CLS: Record<string, string> = { 冲: 'tj-chong', 稳: 'tj-wen', 保: 'tj-wen', 够不上: 'tj-no' }
// 单渠道 → 展示对象
function chDisp(ch: any): { name: string; band: string; cls: string; detail: string; caveat?: string } {
  const k = ch.metric?.kind
  if (k === 'district_rank') return {
    name: '统招', band: ch.band || '—', cls: PUB_BAND_CLS[ch.band] || 'tj-unk',
    detail: ch.metric.refRank != null ? `录取位次≈${ch.metric.refRank}` : '', caveat: ch.caveat }
  if (k === 'city_score') {
    const b = scoreBand(ch.metric.refLine ?? null)
    return { name: '市级统筹' + (ch.tier ? '·' + ch.tier : ''), band: b.label, cls: b.cls,
      detail: (b.d != null ? `统招线${ch.metric.refLine}·Δ${b.d > 0 ? '+' : ''}${b.d}` : '统招线待核')
        + (ch.quota ? ` · 投朝阳${ch.quota}名` : ''), caveat: ch.caveat }
  }
  if (k === 'in_school_rank') {
    const tag = ch._xedtag || 'unknown'
    return { name: '校额到校', band: (XED_TAG[tag] || {}).label || '—', cls: 'rt-' + tag,
      detail: (ch.quota ? `本校名额${ch.quota} · ` : '') + '校内竞争', caveat: '按本初中校内排名+志愿录取' }
  }
  if (k === 'threshold') return {
    name: ch.channel, band: '门槛', cls: 'tj-unk',
    detail: ch.metric.refLine ? `≥${ch.metric.refLine}分` : '按分填报', caveat: ch.caveat }
  if (k === 'route_choice') return {
    name: '自主', band: '路线选择', cls: 'tj-unk', detail: '无统一录取线', caveat: ch.caveat }
  return { name: ch.channel || '研判', band: ch.band || '待核', cls: 'tj-unk', detail: '', caveat: ch.caveat }
}
const channelViews = computed(() => (selSchool.value?.channels || []).map(chDisp))
const schoolLines = computed<any[]>(() => {
  for (const ch of (selSchool.value?.channels || [])) if (ch.lines && ch.lines.length) return ch.lines
  return []
})
const caveats = computed<string[]>(() => {
  const set = new Set<string>()
  channelViews.value.forEach((v: any) => { if (v.caveat) set.add(v.caveat) })
  return [...set]
})

const newSchools = computed<any[]>(() => (result.value as any)?.new_schools?.schools || [])

const privAll = computed<PrivSchool[]>(() => result.value?.private_schools?.schools || [])
const minbanList = computed<PrivSchool[]>(() => privAll.value.filter(s => s.in_minban_list))
const intlList = computed<PrivSchool[]>(() => privAll.value.filter(s => s.in_intl_list))
// ───── 查学校：统一浏览器（§12·步骤3）。唯一数据源 = schools_unified ─────
const uList = computed<any[]>(() => ((result.value as any)?.schools_unified) || [])
const EX_TYPES = [
  { v: 'all', label: '全部' }, { v: '公办', label: '公办普高' }, { v: '民办', label: '民办' },
  { v: '国际', label: '国际/双语' }, { v: '中职', label: '中职/职教' }, { v: '贯通', label: '贯通' },
  { v: '新校', label: '2026新校' }, { v: '统筹', label: '外区统筹' },
]
const exType = ref('all')
const exChannel = ref<'all' | 'tc' | 'xed'>('all')   // 渠道：全部 / 可走统筹 / 可走校额
const exBand = ref<'all' | '稳' | '冲' | '搏'>('all')
const exBoarding = ref(false)
const exCommute = ref(false)
const exFee = ref<'all' | 'le10' | 'mid' | 'gt20'>('all')
function exTypeMatch(rec: any, t: string): boolean {
  const ty = rec.type || ''
  if (t === 'all') return true
  if (t === '公办') return ty === '公办普高'
  if (t === '民办') return ty.includes('民办')
  if (t === '国际') return ty.includes('国际') || ty.includes('双语')
  if (t === '中职') return ty.includes('中职') || ty.includes('职教')
  if (t === '贯通') return ty === '贯通'
  if (t === '新校') return ty.includes('新校')
  if (t === '统筹') return ty === '市级统筹'
  return true
}
// 该校"主档位"：公办取统招渠道，统筹/外区统筹取 city_score
function exBandOf(rec: any): { label: string; cls: string } | null {
  for (const ch of (rec.channels || [])) {
    if (ch.metric?.kind === 'district_rank') return { label: ch.band || '—', cls: PUB_BAND_CLS[ch.band] || 'tj-unk' }
    if (ch.metric?.kind === 'city_score') { const b = scoreBand(ch.metric.refLine ?? null); return { label: b.label, cls: b.cls } }
  }
  return null
}
// 渠道短标：统/筹/校
function exChannelTags(rec: any): string[] {
  const tags: string[] = []
  for (const ch of (rec.channels || [])) {
    if (ch.metric?.kind === 'district_rank') tags.push('统')
    if (ch.metric?.kind === 'city_score') tags.push('筹')
  }
  if (rec.type === '公办普高' && xedQuotaByName.value[rec.name]) tags.push('校')
  return tags
}
function exHasTc(rec: any): boolean {
  return rec.type === '市级统筹' || (rec.channels || []).some((c: any) => c.metric?.kind === 'city_score')
}
function exHasXed(rec: any): boolean {
  return rec.type === '公办普高' && !!xedQuotaByName.value[rec.name]
}
function exFeeMax(rec: any): number | null {
  const t = rec.extra?.tuition
  if (!t) return null
  const nums = String(t).match(/\d+(\.\d+)?/g)
  return nums ? Math.max(...nums.map(Number)) : null
}
// 关键数（随类型自适应）
function exKey(rec: any): { k: string; v: string } {
  const ty = rec.type || ''
  if (ty === '公办普高') {
    const ch = (rec.channels || []).find((c: any) => c.metric?.kind === 'district_rank')
    const r = ch?.metric?.refRank
    return { k: '位次', v: r != null ? String(r) : '—' }
  }
  if (ty === '市级统筹') return { k: '投朝阳', v: rec.extra?.quota_chaoyang != null ? rec.extra.quota_chaoyang + '名' : '—' }
  if (ty.includes('民办') || ty.includes('国际') || ty.includes('双语')) return { k: '学费', v: rec.extra?.tuition || '—' }
  if (ty.includes('中职') || ty.includes('职教')) { const sp = rec.extra?.specialties; return { k: '专业', v: sp && sp.length ? sp.slice(0, 2).join('·') : '—' } }
  if (ty === '贯通') { const ps = rec.extra?.projects; return { k: '对接本科', v: ps && ps.length ? ps.length + '个项目' : '—' } }
  if (ty.includes('新校')) { const a = rec.extra?.analog; return { k: '可类比', v: a && a.length ? a[0] : '待核' } }
  return { k: '', v: '' }
}
const TYPE_ORDER: Record<string, number> = {
  '公办普高': 0, '市级统筹': 1, '民办普高': 2, '国际/双语': 2, '民办普高/国际/双语': 2,
  '贯通': 3, '中职/职教': 4, '2026新校': 5,
}
const exFeeApplies = computed(() => exType.value === '民办' || exType.value === '国际' || exType.value === 'all')
const exploreView = computed<any[]>(() => {
  let list = uList.value.filter(r => exTypeMatch(r, exType.value))
  if (exChannel.value === 'tc') list = list.filter(exHasTc)
  if (exChannel.value === 'xed') list = list.filter(exHasXed)
  if (exBand.value !== 'all') list = list.filter(r => (exBandOf(r) || {}).label === exBand.value)
  if (exBoarding.value) list = list.filter(r => r.boarding === true)
  if (exCommute.value) list = list.filter(r => r.commute && !r.commute.over_max)
  if (exFee.value !== 'all') list = list.filter(r => {
    const m = exFeeMax(r); if (m == null) return false
    if (exFee.value === 'le10') return m <= 10
    if (exFee.value === 'mid') return m > 10 && m <= 20
    return m > 20
  })
  return [...list].sort((a, b) => {
    const ta = TYPE_ORDER[a.type] ?? 9, tb = TYPE_ORDER[b.type] ?? 9
    if (ta !== tb) return ta - tb
    if (a.type === '公办普高' && b.type === '公办普高') {
      const na = Number(exKey(a).v) || 9e9, nb = Number(exKey(b).v) || 9e9
      return na - nb
    }
    return (a.name || '').localeCompare(b.name || '')
  })
})
function exSelect(rec: any) { selectPoint({ name: rec.name } as any) }
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

/* ---------------- 志愿草表 v2：三批次（2026 口径）---------------- */
// 批次资格（按考生身份灰掉）
const identityLabel = computed(() => (IDENTITIES.find(i => i.v === form.identity) || {}).label || '')
const canIndicator = computed(() => form.identity === 'jjyj')   // 指标分配=校额到校/统筹：京籍应届
const canGuantong = computed(() => form.identity === 'jjyj')    // 贯通：京籍应届
const canPuhao = computed(() => form.identity !== 'feijing')    // 普高统招：非京籍不可
const identityNote = computed(() => {
  if (form.identity === 'feijing') return '非京籍随迁子女不能报普通高中（统招/指标分配/贯通），只能报中职类；下列普高批次仅供了解。'
  if (form.identity === 'wangjie') return '往届/回户籍/外省回京考生不能报指标分配(校额到校/统筹)与贯通；普高统招可报。'
  return ''
})
// ① 提前招生：自由填写（2026 不含贯通、不含中外合作；特长/中职自主/登记入学无官方结构化代码）
const draftEarly = ref<{ text: string }[]>(Array.from({ length: 8 }, () => ({ text: '' })))
// ② 指标分配-市级统筹：自由填写
const draftTongchou = ref<{ text: string }[]>(Array.from({ length: 4 }, () => ({ text: '' })))
// ② 指标分配-校额到校：选优质高中(来自孩子初中的名额) + 专业手填
interface XedSlot { school: string | null; majors: string }
const draftXed = ref<XedSlot[]>(Array.from({ length: 8 }, () => ({ school: null, majors: '' })))
// 当前初中(复用 xedQuery)可报的优质高中 + 名额；待核校(无明细)返回空并由模板提示
const xedEligible = computed<{ school: string; n: number }[]>(() => {
  const r = xedSel.value
  if (!r || !r.by_school) return []
  return Object.entries(r.by_school).map(([school, n]) => ({ school, n: n as number }))
})
// 按孩子位次给校额到校推荐：高中统招位次 vs 孩子rank → 值得冲/相当/统招本可达
const xedRecommend = computed(() => {
  const rank = Number(form.rank) || 0
  const pl = result.value?.public_list || []
  const byName: Record<string, PubSchool> = {}
  pl.forEach(p => { byName[p.name] = p })
  return xedEligible.value.map(e => {
    const full = XED_FULLNAME[e.school]
    const card = full ? byName[full] : null
    const ref = card && typeof card.ref_rank === 'number' ? card.ref_rank as number : null
    let tag = 'unknown'
    if (ref != null && rank) {
      if (ref <= rank * 0.95) tag = 'worth'        // 统招位次比孩子靠前→统招够不上→校额到校是机会
      else if (ref >= rank * 1.1) tag = 'waste'    // 统招位次比孩子靠后→统招本可达→校额占用意义小
      else tag = 'similar'
    }
    return { ...e, full, ref, tag }
  }).sort((a, b) => (a.ref ?? 9e9) - (b.ref ?? 9e9))
})
const XED_TAG: Record<string, { label: string; cls: string }> = {
  worth: { label: '✅值得冲(统招够不上)', cls: 'rt-worth' },
  similar: { label: '≈与统招相当', cls: 'rt-similar' },
  waste: { label: '⚠️统招本可达·占用浪费', cls: 'rt-waste' },
  unknown: { label: '—', cls: 'rt-unknown' },
}

function copyAll() {
  const res = result.value
  if (!res) return
  const L: string[] = [`中考志愿草表（${res.district} · 三批次 · 2026口径 · 仅参考，以官方网报为准）`,
    `考生身份：${(IDENTITIES.find(i => i.v === form.identity) || {}).label}`, '']
  L.push('【批次① 提前招生】(2026不含贯通；手填)')
  draftEarly.value.forEach((s, i) => { if (s.text.trim()) L.push(`  提招${i + 1}　${s.text.trim()}`) })
  L.push('', '【批次② 指标分配】校额到校 + 市级统筹')
  draftXed.value.forEach((s, i) => {
    if (!s.school) return
    const n = xedEligible.value.find(e => e.school === s.school)?.n
    L.push(`  校额到校${i + 1}　${s.school}${n ? `(本校名额${n})` : ''}　专业:${s.majors.trim() || '(手填)'}`)
  })
  draftTongchou.value.forEach((s, i) => { if (s.text.trim()) L.push(`  统筹${i + 1}　${s.text.trim()}`) })
  L.push('', `【批次③ 统一招生】(2026含贯通) 共${ZHIYUAN_SLOTS}志愿×2专业`)
  draft.value.forEach((s, i) => {
    if (!s.name) { L.push(`  志愿${i + 1}　（空）`); return }
    const c = findCard(s.name)
    const ms = majorsOf(s.name).filter(m => s.picks.includes(m.major_code))
    const mtxt = ms.map(m => `${m.major_code} ${cleanName(m.major_name)}`).join('　')
    L.push(`  志愿${i + 1}　${cleanName(s.name)}(${c?.school_code || ''})　${mtxt}`)
  })
  navigator.clipboard?.writeText(L.join('\n')).then(
    () => { copyHint.value = '已复制全部三批次到剪贴板'; setTimeout(() => copyHint.value = '', 2500) },
    () => { copyHint.value = '复制失败，请手动选择' },
  )
}

// 校额到校：按推荐(值得冲→相当，排除浪费，最好的在前)缺省填入志愿
function prefillXed() {
  const rec = xedRecommend.value.filter(e => e.tag === 'worth' || e.tag === 'similar' || e.tag === 'unknown')
  draftXed.value = Array.from({ length: 8 }, (_, i) =>
    rec[i] ? { school: rec[i].school, majors: '' } : { school: null, majors: '' })
}
// 初中校变化时自动按推荐预填（有明细时）
watch(() => (xedSel.value ? xedSel.value.code : ''), () => {
  if (xedSel.value && xedSel.value.by_school) prefillXed()
}, { immediate: true })

// 统一招生：上移/下移/在上方插入（用于在中间或最前插入志愿）
function moveUni(i: number, dir: number) {
  const j = i + dir
  if (j < 0 || j >= draft.value.length) return
  const a = draft.value
  ;[a[i], a[j]] = [a[j], a[i]]
}
function insertUniAbove(i: number) {
  // 在第 i 个志愿上方插入一个空志愿，其余顺延；超过 12 个则挤出末位
  const a = draft.value.slice()
  a.splice(i, 0, { name: null, picks: [] })
  if (a.length > ZHIYUAN_SLOTS) {
    const dropped = a.pop()
    if (dropped && dropped.name) {
      copyHint.value = `已在第${i + 1}位插入；超出12个，末位「${cleanName(dropped.name)}」被挤出`
      setTimeout(() => copyHint.value = '', 3500)
    }
  }
  draft.value = a
}
function deleteUni(i: number) {
  // 直接删除整行（想再加用"插入"）
  draft.value = draft.value.slice(0, i).concat(draft.value.slice(i + 1))
}
// 通用志愿行操作（提前招生 / 市级统筹 / 校额到校 都用这套，跟统招一致）：上移/下移/上方插入/删除
function moveRow(a: any[], i: number, dir: number) {
  const j = i + dir
  if (j < 0 || j >= a.length) return
  ;[a[i], a[j]] = [a[j], a[i]]
}
function insertRow(a: any[], i: number, make: () => any) { a.splice(i, 0, make()); a.pop() }
function deleteRow(a: any[], i: number, make: () => any) { a.splice(i, 1); a.push(make()) }
const mkText = () => ({ text: '' })
const mkXed = () => ({ school: null, majors: '' })

// 市级统筹（统筹一/二/三）方向说明。
// ⚠️ 重要订正：曾用《朝阳指标分配计划·高中侧》里本区校（人朝/对外经贸/东师朝/清华附中朝阳·望京）的统筹名额数反推“朝阳可报统筹校”——这是把“高中对外供给的名额”误当成“朝阳考生可报”。
// 那些名额按全市各初中校分配、多流向外区；它们是朝阳本区优质高中，朝阳考生应走【统招/校额到校】去够，而非市级统筹。
// 朝阳考生“市级统筹”能填的，是外区/郊区的统筹校；权威逐校名单只在《招生简章》按“朝外这所初中分到的统筹名额”里查，本系统暂无可靠该向数据，统一标“待核”。
const TONGCHOU_REF = [
  { tier: '统筹一', desc: '城区顶尖名校本部跨区招生（明确“不在东西海招”，面向朝阳等区；门槛高、名额少）', schools: ['具体校与名额以当年 bjeea《市级统筹招生计划》为准（待核）'] },
  { tier: '统筹二', desc: '名校在郊区/新城的分校或城乡一体化校，面向全市分配', schools: ['方向示例：人大附中通州、首师大附中通州、人朝丰台/石景山学校等外区分校（仅示意方向，非确定可报名单，以简章为准）'] },
  { tier: '统筹三', desc: '高校与普高联合培养实验班（名额少；部分年份已调整/取消）', schools: ['以当年 bjeea 计划为准（待核）'] },
]
// 不再从高中侧供给表反推“可报名单”，datalist 不预置具体校名，避免误导。
const tcOptions: string[] = []
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
        <label class="f-mode">考生身份
          <select v-model="form.identity">
            <option v-for="x in IDENTITIES" :key="x.v" :value="x.v">{{ x.label }}</option>
          </select>
        </label>
        <label class="f-rank">区排名<small>一模/二模</small>
          <input type="number" v-model.number="form.rank" min="1" placeholder="如 4500" />
        </label>
        <label class="f-home">初中学校<small>校额/统筹用</small>
          <input list="xedSchoolListMain" v-model="xedQuery" placeholder="如 朝阳外国语学校" />
        </label>
        <datalist id="xedSchoolListMain"><option v-for="r in (xedBlock ? xedBlock.rows : [])" :key="r.code" :value="r.name" /></datalist>
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
      <p v-if="form.boarding" class="board-note">🛏 已开启住宿：距离不再参与筛选，范围放开到全朝阳（距离仍展示作参考）。</p>
      <p v-if="errMsg" class="err">{{ errMsg }}</p>
    </section>

    <section v-if="result" class="results">
      <!-- 一级导航：地图 / 草表 / 查学校 / 渠道科普 -->
      <div class="tabbar">
        <div class="tabs" role="tablist">
          <button class="tab" :class="{ on: tab === 'map' }" @click="goTab('map')"><span class="tab-ic">📍</span>志愿地图</button>
          <button class="tab" :class="{ on: tab === 'draft' }" @click="goTab('draft')"><span class="tab-ic">📝</span>志愿草表<span class="tab-cnt">{{ filledSlots }}/{{ ZHIYUAN_SLOTS }}</span></button>
          <button class="tab" :class="{ on: tab === 'explore' }" @click="goTab('explore')"><span class="tab-ic">🔎</span>查学校<span class="tab-cnt">{{ uList.length }}</span></button>
          <button class="tab" :class="{ on: tab === 'channels' }" @click="goTab('channels')"><span class="tab-ic">📖</span>渠道科普</button>
        </div>
      </div><!-- /tabbar -->

      <!-- TAB 1：地图 -->
      <div class="mapwrap" v-show="tab === 'map'">
        <div class="map-head">
          <h2>全{{ result.district }}学校分布</h2>
          <div class="layer-chips">
            <button v-if="tongchou" class="lchip lc-tc" :class="{ on: layers.tc }" @click="layers.tc = !layers.tc">市级统筹</button>
            <button class="lchip lc-xed" :class="{ on: layers.xed }" @click="layers.xed = !layers.xed">校额到校</button>
            <button class="lchip" :class="{ on: layers.gongban }" @click="layers.gongban = !layers.gongban">公办普高</button>
            <button class="lchip lc-minban" :class="{ on: layers.minban }" @click="layers.minban = !layers.minban">民办普高</button>
            <button class="lchip lc-intl" :class="{ on: layers.intl }" @click="layers.intl = !layers.intl">国际/双语</button>
            <button class="lchip lc-gt" :class="{ on: layers.gt }" @click="layers.gt = !layers.gt">贯通(全市)</button>
            <button class="lchip lc-voc" :class="{ on: layers.voc }" @click="layers.voc = !layers.voc">中职/职教</button>
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
              <template v-if="selSchool">
                <div class="dp-head">
                  <span class="dp-type">{{ selSchool.type }}</span>
                  <h3>{{ cleanName(selSchool.name) }}</h3>
                </div>
                <div class="dp-sub">
                  {{ selSchool.level || '' }}
                  <span v-if="selSchool.extra.coop" class="bdg b-coop">🌐中外合作班</span>
                </div>

                <div class="dp-block">
                  <div class="dp-title">录取研判<small v-if="estScore"> 你估≈{{ estScore }}</small></div>
                  <div v-for="(v, ci) in channelViews" :key="ci" class="dp-ch">
                    <span class="dp-ch-name">{{ v.name }}</span>
                    <span class="tj" :class="v.cls">{{ v.band }}</span>
                    <span class="dp-ch-detail">{{ v.detail }}</span>
                  </div>
                  <p v-for="(c, idx) in caveats" :key="idx" class="dp-tip">⚠️ {{ c }}</p>
                </div>

                <div v-if="schoolLines.length" class="dp-block">
                  <div class="dp-title">历年录取线</div>
                  <table class="dp-table">
                    <thead><tr><th>年</th><th>线</th><th>口径/区排</th></tr></thead>
                    <tbody>
                      <tr v-for="sl in schoolLines" :key="sl.year">
                        <td>{{ sl.year }}</td>
                        <td>{{ sl.score != null ? sl.score + (sl.scale ? '(' + sl.scale + '制)' : '分') : '—' }}</td>
                        <td>{{ sl.rank != null ? sl.rank + '名' : (sl.conf || '') }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <p class="dp-tip">分数跨年口径不同(2025起510制)；同年/区排名才可比。</p>
                </div>

                <dl class="dp-kv">
                  <div v-if="selSchool.commute"><dt>通勤(到家)</dt>
                    <dd>{{ selSchool.commute.km }}km · {{ selSchool.commute.mins }}分钟
                      <span v-if="selSchool.commute.over_max" class="dp-vol">⚠️超上限</span></dd></div>
                  <div><dt>住宿</dt><dd>
                    <span v-if="selSchool.boarding === true" class="t-yes">🛏 可住宿</span>
                    <span v-else-if="selSchool.boarding === false">不提供</span>
                    <span v-else class="dp-muted">待核</span></dd></div>
                </dl>

                <div v-if="selSchool.extra.tuition" class="dp-line">💰 学费：{{ selSchool.extra.tuition }}</div>
                <div v-if="selSchool.extra.curriculum && selSchool.extra.curriculum.length" class="dp-line">📚 课程：{{ selSchool.extra.curriculum.join('·') }}<template v-if="selSchool.extra.direction"> · {{ selSchool.extra.direction }}</template></div>
                <div v-if="selSchool.extra.specialties && selSchool.extra.specialties.length" class="dp-line">🛠 专业：{{ selSchool.extra.specialties.join('·') }}</div>
                <div v-if="selSchool.extra.projects && selSchool.extra.projects.length" class="dp-block">
                  <div class="dp-title">贯通项目（→本科）</div>
                  <div v-for="(pj, pi) in selSchool.extra.projects" :key="pi" class="dp-mj">{{ pj.type }}：{{ pj.major }} → {{ pj.benke }}<em v-if="pj.plan"> · {{ pj.plan }}人</em></div>
                </div>
                <div v-if="selSchool.extra.system" class="dp-line">🏛 体系：{{ selSchool.extra.system }}</div>
                <div v-if="selSchool.extra.analog && selSchool.extra.analog.length" class="dp-line dp-muted">↔ 可类比：{{ selSchool.extra.analog.join('、') }}</div>
                <div v-if="selSchool.extra.direction && !(selSchool.extra.curriculum && selSchool.extra.curriculum.length)" class="dp-line dp-muted">方向：{{ selSchool.extra.direction }}</div>

                <div v-if="selSchool.features.style" class="dp-line">🏫 {{ selSchool.features.style }}</div>
                <div v-if="selSchool.features.gaokao" class="dp-line dp-muted">🎓 高考(民间·非官方)：{{ selSchool.features.gaokao }}</div>
                <div v-if="selSchool.geo.address" class="dp-line dp-muted">📍 {{ selSchool.geo.address }}<span v-if="selSchool.geo.confidence === 'low' || !selSchool.geo.lat" class="addr-tag">待核</span></div>
              </template>
              <div v-else class="dp-line dp-muted">{{ cleanName(selectedPoint.name) }}（暂无结构化信息）</div>
            </template>
            <div v-else class="dp-empty">
              <div class="dp-empty-ic">🏫</div>
              点击地图上的学校查看详细信息
            </div>
          </aside>
        </div>
      </div>

      <!-- 查学校：统一浏览器（schools_unified 驱动·学校唯一·渠道多个） -->
      <div class="explorewrap" v-show="tab === 'explore'">
        <p v-if="identityNote" class="board-note">⚠️ {{ identityNote }}</p>
        <div class="ex-filters">
          <div class="ex-row">
            <span class="ex-k">类型</span>
            <button v-for="t in EX_TYPES" :key="t.v" class="ex-chip" :class="{ on: exType === t.v }" @click="exType = t.v">{{ t.label }}</button>
          </div>
          <div class="ex-row">
            <span class="ex-k">渠道</span>
            <button class="ex-chip" :class="{ on: exChannel === 'all' }" @click="exChannel = 'all'">全部</button>
            <button class="ex-chip" :class="{ on: exChannel === 'tc' }" @click="exChannel = 'tc'">可走统筹</button>
            <button class="ex-chip" :class="{ on: exChannel === 'xed' }" @click="exChannel = 'xed'">可走校额</button>
            <span class="ex-k ex-k2">档位</span>
            <button class="ex-chip" :class="{ on: exBand === 'all' }" @click="exBand = 'all'">全部</button>
            <button class="ex-chip" :class="{ on: exBand === '稳' }" @click="exBand = '稳'">稳</button>
            <button class="ex-chip" :class="{ on: exBand === '冲' }" @click="exBand = '冲'">冲</button>
            <button class="ex-chip" :class="{ on: exBand === '搏' }" @click="exBand = '搏'">搏</button>
          </div>
          <div class="ex-row">
            <label class="ex-sw"><input type="checkbox" v-model="exBoarding" />可住宿</label>
            <label class="ex-sw"><input type="checkbox" v-model="exCommute" />通勤≤上限</label>
            <template v-if="exFeeApplies">
              <span class="ex-k ex-k2">学费</span>
              <button class="ex-chip" :class="{ on: exFee === 'all' }" @click="exFee = 'all'">全部</button>
              <button class="ex-chip" :class="{ on: exFee === 'le10' }" @click="exFee = 'le10'">≤10万</button>
              <button class="ex-chip" :class="{ on: exFee === 'mid' }" @click="exFee = 'mid'">10–20万</button>
              <button class="ex-chip" :class="{ on: exFee === 'gt20' }" @click="exFee = 'gt20'">&gt;20万</button>
            </template>
            <span class="ex-n">命中 {{ exploreView.length }} 所</span>
          </div>
        </div>
        <div class="ex-main">
          <div class="ex-listcol">
            <div class="table-scroll">
              <table class="list-table ex-table">
                <thead><tr><th>学校</th><th>类型</th><th>层次</th><th>档位</th><th>渠道</th><th>关键</th><th>通勤</th><th>住</th></tr></thead>
                <tbody>
                  <tr v-for="r in exploreView" :key="r.id || r.name" class="ex-tr" :class="{ on: selectedPoint && selectedPoint.name === r.name }" @click="exSelect(r)">
                    <td class="t-name">{{ cleanName(r.name) }}<span v-if="r.type === '2026新校'" class="addr-tag warn">新</span></td>
                    <td class="ex-ty">{{ r.type }}</td>
                    <td class="t-lvl">{{ r.level || '—' }}</td>
                    <td><span v-if="exBandOf(r)" class="t-band" :class="exBandOf(r)?.cls">{{ exBandOf(r)?.label }}</span><span v-else class="t-no">—</span></td>
                    <td class="ex-cht"><span v-for="(g, gi) in exChannelTags(r)" :key="gi" class="ex-cbg">{{ g }}</span><span v-if="!exChannelTags(r).length" class="t-no">—</span></td>
                    <td class="ex-keycol"><small>{{ exKey(r).k }}</small> <b>{{ exKey(r).v }}</b></td>
                    <td class="t-dist">{{ r.commute && r.commute.km != null ? r.commute.km + 'km' : '—' }}<span v-if="r.commute && r.commute.over_max" class="t-over">超</span></td>
                    <td><span v-if="r.boarding === true" class="t-yes">🛏</span><span v-else class="t-no">—</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="list-tip">点任意行看右侧详情与逐渠道研判。<b>渠道标</b>：统=统招 / 筹=市级统筹 / 校=校额到校。<b>关键数</b>随类型变（公办=录取位次 · 统筹=投朝阳名额 · 民办/国际=学费 · 中职=专业 · 贯通=对接本科）。机制与门槛见「渠道科普」。</p>
          </div>
          <aside class="detail-panel">
            <template v-if="selectedPoint">
              <template v-if="selSchool">
                <div class="dp-head">
                  <span class="dp-type">{{ selSchool.type }}</span>
                  <h3>{{ cleanName(selSchool.name) }}</h3>
                </div>
                <div class="dp-sub">
                  {{ selSchool.level || '' }}
                  <span v-if="selSchool.extra.coop" class="bdg b-coop">🌐中外合作班</span>
                </div>

                <div class="dp-block">
                  <div class="dp-title">录取研判<small v-if="estScore"> 你估≈{{ estScore }}</small></div>
                  <div v-for="(v, ci) in channelViews" :key="ci" class="dp-ch">
                    <span class="dp-ch-name">{{ v.name }}</span>
                    <span class="tj" :class="v.cls">{{ v.band }}</span>
                    <span class="dp-ch-detail">{{ v.detail }}</span>
                  </div>
                  <p v-for="(c, idx) in caveats" :key="idx" class="dp-tip">⚠️ {{ c }}</p>
                </div>

                <div v-if="schoolLines.length" class="dp-block">
                  <div class="dp-title">历年录取线</div>
                  <table class="dp-table">
                    <thead><tr><th>年</th><th>线</th><th>口径/区排</th></tr></thead>
                    <tbody>
                      <tr v-for="sl in schoolLines" :key="sl.year">
                        <td>{{ sl.year }}</td>
                        <td>{{ sl.score != null ? sl.score + (sl.scale ? '(' + sl.scale + '制)' : '分') : '—' }}</td>
                        <td>{{ sl.rank != null ? sl.rank + '名' : (sl.conf || '') }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <p class="dp-tip">分数跨年口径不同(2025起510制)；同年/区排名才可比。</p>
                </div>

                <dl class="dp-kv">
                  <div v-if="selSchool.commute"><dt>通勤(到家)</dt>
                    <dd>{{ selSchool.commute.km }}km · {{ selSchool.commute.mins }}分钟
                      <span v-if="selSchool.commute.over_max" class="dp-vol">⚠️超上限</span></dd></div>
                  <div><dt>住宿</dt><dd>
                    <span v-if="selSchool.boarding === true" class="t-yes">🛏 可住宿</span>
                    <span v-else-if="selSchool.boarding === false">不提供</span>
                    <span v-else class="dp-muted">待核</span></dd></div>
                </dl>

                <div v-if="selSchool.extra.tuition" class="dp-line">💰 学费：{{ selSchool.extra.tuition }}</div>
                <div v-if="selSchool.extra.curriculum && selSchool.extra.curriculum.length" class="dp-line">📚 课程：{{ selSchool.extra.curriculum.join('·') }}<template v-if="selSchool.extra.direction"> · {{ selSchool.extra.direction }}</template></div>
                <div v-if="selSchool.extra.specialties && selSchool.extra.specialties.length" class="dp-line">🛠 专业：{{ selSchool.extra.specialties.join('·') }}</div>
                <div v-if="selSchool.extra.projects && selSchool.extra.projects.length" class="dp-block">
                  <div class="dp-title">贯通项目（→本科）</div>
                  <div v-for="(pj, pi) in selSchool.extra.projects" :key="pi" class="dp-mj">{{ pj.type }}：{{ pj.major }} → {{ pj.benke }}<em v-if="pj.plan"> · {{ pj.plan }}人</em></div>
                </div>
                <div v-if="selSchool.extra.system" class="dp-line">🏛 体系：{{ selSchool.extra.system }}</div>
                <div v-if="selSchool.extra.analog && selSchool.extra.analog.length" class="dp-line dp-muted">↔ 可类比：{{ selSchool.extra.analog.join('、') }}</div>
                <div v-if="selSchool.extra.direction && !(selSchool.extra.curriculum && selSchool.extra.curriculum.length)" class="dp-line dp-muted">方向：{{ selSchool.extra.direction }}</div>

                <div v-if="selSchool.features.style" class="dp-line">🏫 {{ selSchool.features.style }}</div>
                <div v-if="selSchool.features.gaokao" class="dp-line dp-muted">🎓 高考(民间·非官方)：{{ selSchool.features.gaokao }}</div>
                <div v-if="selSchool.geo.address" class="dp-line dp-muted">📍 {{ selSchool.geo.address }}<span v-if="selSchool.geo.confidence === 'low' || !selSchool.geo.lat" class="addr-tag">待核</span></div>
              </template>
              <div v-else class="dp-line dp-muted">{{ cleanName(selectedPoint.name) }}（暂无结构化信息）</div>
            </template>
            <div v-else class="dp-empty">
              <div class="dp-empty-ic">🏫</div>
              点击地图上的学校查看详细信息
            </div>
          </aside>
        </div>
      </div>
      <!-- 渠道科普：科普总览 + 校额到校 + 市级统筹（数据工具内嵌） -->
      <div class="chwrap" v-show="tab === 'channels'">
        <div class="ch-subnav">
          <button class="ch-sb" :class="{ on: chSub === 'guide' }" @click="chSub = 'guide'">📖 升学渠道科普</button>
          <button class="ch-sb" :class="{ on: chSub === 'xed' }" @click="chSub = 'xed'">🎯 校额到校</button>
          <button class="ch-sb" :class="{ on: chSub === 'tc' }" @click="chSub = 'tc'">🌆 市级统筹</button>
        </div>
        <div class="listwrap ch-guide" v-show="chSub === 'guide'">
          <p class="list-note">北京中考升学的批次与渠道全景（提招 / 指标分配 / 统招 / 贯通 / 中职）。点条目展开。具体校额名额、统筹投朝阳名额与逐校研判见上方「校额到校 / 市级统筹」子页。</p>
          <div v-for="(g, i) in GUIDE" :key="i" class="g-item" :class="{ open: openG === i }">
            <button class="g-q" type="button" @click="openG = openG === i ? null : i"><span>{{ g.t }}</span><span class="g-chev">{{ openG === i ? '−' : '+' }}</span></button>
            <div v-show="openG === i" class="g-a" v-html="g.h"></div>
          </div>
        </div>
        <!-- 校额到校 -->
        <div class="listwrap" v-show="chSub === 'xed'">
        <p v-if="!canIndicator" class="board-note">⚠️ 指标分配（校额到校）<b>仅京籍应届可报</b>；往届/回户籍/外省回京/非京籍<b>不可报</b>，以下<b>仅供了解</b>。</p>
        <div class="xed-intro">
          <h3>🎯 校额到校（指标分配批次）</h3>
          <p>优质高中拿出名额<b>定向分配到每所初中校、校内竞争</b>录取——同校学生之间按中考总分从高到低排名，<b>不是全区竞争</b>。所以"普通初中"的孩子，反而更可能用相对低的分数进入优质高中。</p>
          <div class="xed-rules">
            <div class="xed-rule"><span class="xed-k">报考门槛(2025)</span>中考总分 ≥ <b>430/510</b> + 综合素质评价 ≥ <b>B</b> 等</div>
            <div class="xed-rule"><span class="xed-k">学籍要求</span>具普高升学资格 + <b>同一初中连续三年学籍</b>的应届生</div>
            <div class="xed-rule"><span class="xed-k">不能报</span>往届生 / 回户籍 / 外省回京 考生</div>
            <div class="xed-rule"><span class="xed-k">录取分</span>无官方"各初中录取线"——按本校内排名事后形成，逐校逐年不同；430 仅是统一资格门槛</div>
          </div>
          <p class="xed-hl">📋 输入孩子的<b>初中校</b>即可查该校 2025 年校额到校名额。需逐格核对时，再展开下方官方原图。</p>
        </div>

        <!-- 按初中查名额 -->
        <div v-if="xedBlock" class="xed-query">
          <p class="xed-qlabel">孩子初中校：<b>{{ xedQuery || '（未填）' }}</b>　<span class="xed-src" style="margin:0">— 在<b>首页"初中学校"</b>修改</span></p>
          <div v-if="xedQuery && !xedSel" class="xed-miss">未匹配到该初中（在首页换更短的关键词，或在下方官方原图核对）</div>
          <div v-if="xedSel" class="xed-card">
            <div class="xed-card-head">
              <b>{{ cleanName(xedSel.name) }}</b>
              <span class="xed-total">校额到校共 <b>{{ xedSel.total }}</b> 个名额</span>
            </div>
            <template v-if="xedSel.by_school">
              <div class="xed-grid">
                <span v-for="(n, sch) in xedSel.by_school" :key="sch" class="xed-cell"><i>{{ sch }}</i>{{ n }}</span>
              </div>
              <p class="xed-note">＝该校分到各优质高中的名额数（已与“合计”自检一致）。能否录取＝在本初中校内按中考总分排名 + 志愿顺序，门槛 总分≥430、综合素质B、连续三年学籍。</p>
            </template>
            <p v-else class="xed-note warn">本行明细未通过自检，仅“合计 {{ xedSel.total }}”可靠；各优质高中明细请在下方官方原图中按行核对（避免转录出错）。</p>
          </div>
          <p class="xed-src">数据：{{ xedBlock.source_T1 }}；明细自检通过 {{ xedBlock.verified_count }}/{{ xedBlock.total_count }} 校，其余仅给合计、明细以原图为准。</p>
        </div>

        <!-- 研判 + 填报（从志愿草表移来）：仅京籍应届可报 -->
        <template v-if="canIndicator">
          <div v-if="xedRecommend.length" class="xed-rec">
            <p class="xed-rec-warn">⚠️ <b>风险</b>：校额到校在统招<b>之前</b>录取、<b>一旦录取就锁定、后续批次作废</b>。建议<b>只填比你统招更够得着的好学校</b>（✅），<b>别填你统招本来就能上的</b>（⚠️），否则等于把自己锁进更差的结果。</p>
            <div class="xed-rec-list">
              <div v-for="e in xedRecommend" :key="e.school" class="xed-rec-row">
                <span class="rt" :class="XED_TAG[e.tag].cls">{{ XED_TAG[e.tag].label }}</span>
                <b class="rt-name">{{ e.school }}</b>
                <span class="rt-meta">名额{{ e.n }}<template v-if="e.ref"> · 统招位次≈{{ e.ref }}</template></span>
              </div>
            </div>
            <p class="xed-src">研判依据：各优质高中“统招录取位次”对比你的区排名 <b>{{ form.rank }}</b>。✅=统招够不上、校额才有机会；⚠️=统招本可达、占名额意义小。实际按本初中<b>校内排名</b>录取、无官方各校线，仅作策略参考。</p>
          </div>
          <p v-if="xedEligible.length" class="xed-src">📝 校额到校<b>志愿填报</b>在「<a class="lnk" @click="goTab('draft')">志愿草表 → ②指标分配</a>」里（支持插入/上下移）。本页负责看名额与研判。</p>
        </template>

        <button class="xed-imgtoggle" type="button" @click="showXedImg = !showXedImg">
          {{ showXedImg ? '▲ 收起官方原图' : '▼ 展开官方原图（逐格核对用）' }}
        </button>
        <div v-show="showXedImg" class="xed-imgs">
          <a :href="XED_OFFICIAL" target="_blank" rel="noopener"><img src="/xed/chaoyang-xeddx-2025-p1.jpg" alt="朝阳校额到校分配名额 第1页" loading="lazy" /></a>
          <a :href="XED_OFFICIAL" target="_blank" rel="noopener"><img src="/xed/chaoyang-xeddx-2025-p2.jpg" alt="朝阳校额到校分配名额 第2页（上半部分为朝阳）" loading="lazy" /></a>
        </div>
        <p v-show="showXedImg" class="list-tip">
          ⚠️ 上图为官方原图（朝阳区；第 2 页上半部分为朝阳、下半为丰台）。名额数字<b>请以官方原图为准</b>，本系统不另行转录以免出错。
          原始来源：<a :href="XED_OFFICIAL" target="_blank" rel="noopener">北京教育考试院《2025年初中学校校额到校分配名额》</a>（2025-07-01，每年 7 月初更新）。
          录取按校内总分排名 + 志愿顺序；2026 计划发布后须刷新。
        </p>
      </div>

      <!-- TAB：市级统筹（指标分配批次）-->
        <div class="listwrap" v-show="chSub === 'tc'">
        <p v-if="!canIndicator" class="board-note">⚠️ 市级统筹与校额到校同属指标分配批次，<b>仅京籍应届可报</b>；往届/回户籍/外省回京/非京籍<b>不可报</b>，以下<b>仅供了解</b>。</p>
        <div class="xed-intro">
          <h3>🌆 市级统筹（指标分配批次）</h3>
          <p>市级统筹＝优质高中拿名额<b>跨区 / 面向全市</b>分配，和校额到校<b>同属指标分配批次</b>（在统招之前、<b>录取即锁定、后续作废</b>）。门槛同：中考总分 ≥ 430 + 综合素质 B + 同一初中连续三年学籍（往届/回京不可）。</p>
          <div class="xed-rules">
            <div class="xed-rule"><span class="xed-k">统筹一</span>中心城区优质高中跨区招生（不在东西海招）——给其他区考生进城区名校的机会</div>
            <div class="xed-rule"><span class="xed-k">统筹二</span>优质高中的郊区分校 / 新建校面向全市招生</div>
            <div class="xed-rule"><span class="xed-k">统筹三</span>高校与普通高中联合培养实验班（名额较少）</div>
            <div class="xed-rule"><span class="xed-k">方向</span>市级统筹是优质资源<b>跨区/向郊区·新城均衡</b>的机制——朝阳考生用它能填的是<b>外区/郊区</b>的统筹校；<b>朝阳本区的好学校（人朝、清华附中朝阳·望京、东师朝、对外经贸94中 等）请走【统招/校额到校】去够，不是统筹</b></div>
            <div class="xed-rule"><span class="xed-k">报名策略</span>① 与校额到校同批次、共用门槛、<b>录取即锁定、后续作废</b>；② 统筹是<b>全市按分竞争</b>（不像校额到校是校内竞争），更看绝对分数/区位次，去外区/郊区前先掂量是否真比本区统招更好，把握不大别盲填把自己锁低；③ 通常和校额到校一起在指标分配批次填报</div>
          </div>
          <p class="xed-hl">下方三档为机制说明；再下方<b>「朝阳可报统筹校」清单</b>已据 bjeea 2025 官方简章逐格核出（含投朝阳名额/地址）。⚠️ 但<b>能否录取</b>仍取决于<b>朝外在简章里分到的名额 + 报该校统筹的同学名次</b>，须向初中部核实。</p>
        </div>
        <div class="tc-ref">
          <div v-for="t in TONGCHOU_REF" :key="t.tier" class="tc-tier">
            <span class="tc-tag">{{ t.tier }}</span><span class="tc-desc">{{ t.desc }}</span>
            <span class="tc-schools">{{ t.schools.join('、') }}</span>
          </div>
        </div>

        <!-- 官方清单（据 2025 简章逐格核 + 合计对账）-->
        <template v-if="tongchou">
          <h4 class="batch-sub">📋 朝阳可报统筹校（2025 官方简章·朝阳列名额）</h4>
          <p class="tc-verdict">
            对<b>朝外约 4000 名</b>：<b>统筹一</b>（{{ tcYi.length }} 所名校本部）统招线多对应区排 500–2900，门槛太高、<b>基本陪跑</b>；
            真正有意义的是<b>统筹二</b>——尤其 <b>清华附中将台路校区（学籍在朝阳·28 名额）</b>、央民大附（20）。
            <b>统筹三 2025 已取消</b>。⚠️ 录取在统招<b>之前、录取即锁定</b>，志愿顺序别把远郊校排在你统招能上的好校前。
          </p>
          <div class="table-scroll">
            <table class="list-table tc-tbl">
              <thead><tr><th>统筹二·学校(校区)</th><th class="num">投朝阳</th><th>区</th><th>研判<small v-if="estScore">你估≈{{ estScore }}</small></th><th>通勤</th><th>住宿</th><th>地址</th></tr></thead>
              <tbody>
                <tr v-for="s in tcEr" :key="s.name + s.campus">
                  <td class="t-name">{{ s.name }}<small v-if="s.campus" class="tc-campus">{{ s.campus }}</small></td>
                  <td class="num"><b>{{ s.quota_chaoyang }}</b></td>
                  <td>{{ s.district }}</td>
                  <td><span class="tj" :class="tcJudge(s).cls">{{ tcJudge(s).label }}</span>
                    <small v-if="tcJudge(s).d != null" class="tj-d">{{ tcJudge(s).ref ? "历年线" : "线" }}{{ tcJudge(s).line }}·Δ{{ (tcJudge(s).d ?? 0) > 0 ? "+" : "" }}{{ tcJudge(s).d }}</small></td>
                  <td class="t-dist">{{ s.dist ? s.dist.km + 'km' : '—' }}</td>
                  <td><span v-if="s.boarding === true" class="t-yes">🛏</span><span v-else-if="s.boarding === false" class="t-no">—</span><span v-else class="addr-tag">待核</span></td>
                  <td class="t-addr">{{ s.address }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <details class="tc-yi">
            <summary>展开统筹一 {{ tcYi.length }} 所（名校本部·门槛高，4000 名陪跑）</summary>
            <div class="table-scroll">
              <table class="list-table tc-tbl">
                <thead><tr><th>统筹一·学校</th><th class="num">投朝阳</th><th>区</th><th>研判<small v-if="estScore">你估≈{{ estScore }}</small></th><th>通勤</th><th>住宿</th><th>地址</th></tr></thead>
                <tbody>
                  <tr v-for="s in tcYi" :key="s.name">
                    <td class="t-name">{{ s.name }}</td>
                    <td class="num">{{ s.quota_chaoyang }}</td>
                    <td>{{ s.district }}</td>
                    <td><span class="tj" :class="tcJudge(s).cls">{{ tcJudge(s).label }}</span>
                      <small v-if="tcJudge(s).d != null" class="tj-d">{{ tcJudge(s).ref ? "历年线" : "线" }}{{ tcJudge(s).line }}·Δ{{ (tcJudge(s).d ?? 0) > 0 ? "+" : "" }}{{ tcJudge(s).d }}</small></td>
                    <td class="t-dist">{{ s.dist ? s.dist.km + 'km' : '—' }}</td>
                    <td><span v-if="s.boarding === true" class="t-yes">🛏</span><span v-else-if="s.boarding === false" class="t-no">—</span><span v-else class="addr-tag">待核</span></td>
                    <td class="t-addr">{{ s.address }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
          <p class="tc-judge-note">
            <b>研判口径</b>：你区排 <b>{{ form.rank }}</b> 名 → 按本区一分一段估中考分 <b>≈{{ estScore }}</b> 分，与各校 <b>2025 统招线</b>比（Δ=估分−线）。
            <span class="tj tj-wen">稳</span>Δ≥+10　<span class="tj tj-chong">冲</span>−10~+10　<span class="tj tj-bo">搏</span>−20~−10　<span class="tj tj-no">够不上</span>Δ&lt;−20　<span class="tj tj-unk">线待核</span>无公开线。
            「搏」=估分虽低于统招线 10–20 分，但<b>统筹线通常更低、仍有机会</b>（长线，依赖该校统筹降分幅度，热门校未必降这么多）。
            <b>估分随你填的区排名动态变化</b>（不是写死）。⚠️ 比的是各校<b>统招线（非统筹实际线）</b>，<b>统筹线通常更低</b>，故偏保守——"够不上"才基本无望，"冲"档实际机会更大。估分为一分一段插值近似。<b>「历年线」</b>=单源/历年参考(可信度低于 2025 双源确认的"线")；新校无历史则保持"线待核"。
          </p>
        </template>

        <p class="list-tip">
          ✓ 上方清单据 <b>bjeea 2025 官方简章</b>逐格核 + 合计对账（统筹一各校合计=405 与官方一致）；“投朝阳”=该校 2025 投放朝阳区的名额。
          ⚠️ 研判用的是各校<b>统招线</b>（全市可比的强度参考），<b>统筹实际录取线官方不公开、通常更低</b>；最终能否录取取决于<b>朝外当年报该校统筹的同学名次</b>，须查简章「本初中分配名额」+ 问初中部。各年随计划变。
          市级统筹与校额到校同批次：<b>被录即锁定、后续批次作废</b>；在「志愿草表 → 批次② 指标分配」里填写。
        </p>
      </div>

      </div><!-- /chwrap 渠道科普 -->

      <!-- TAB 8：志愿草表 v2（三批次 · 2026 口径）-->
      <div class="draftwrap" v-show="tab === 'draft'">
        <p class="draft-note">
          三批次按 <b>①提前招生 → ②指标分配 → ③统一招生</b> 顺序录取，<b>被前一批次录取即锁定，后批次作废</b>。
          下表镜像官方网报，<b>2026 口径</b>（贯通已并入统招）；志愿数/代码以当年官方网报系统为准。
        </p>
        <p v-if="identityNote" class="board-note">⚠️ {{ identityNote }}</p>
        <div class="draft-actions">
          <button class="ghost" @click="copyAll">📋 复制全部三批次</button>
          <span v-if="copyHint" class="copyhint">{{ copyHint }}</span>
        </div>

        <!-- 批次① 提前招生 -->
        <section class="batch">
          <button class="batch-h" type="button" @click="batchOpen.early = !batchOpen.early">
            <span class="bc">{{ batchOpen.early ? '▾' : '▸' }}</span>① 提前招生
            <small>2026 不含贯通、不含中外合作（均按统一招生录取）；特长生 / 中职自主 / 登记入学——无官方结构化代码，<b>手填</b></small>
          </button>
          <div v-show="batchOpen.early" class="early-rows">
            <div v-for="(s, i) in draftEarly" :key="i" class="early-row">
              <span class="slot-no">{{ i + 1 }}</span>
              <input v-model="s.text" class="early-input" placeholder="如：XX中学 美术特长 / XX中职 自主招生 / XX校 登记入学 …" />
              <span class="urow-ops">
                <button class="op" title="上移" :disabled="i === 0" @click="moveRow(draftEarly, i, -1)">↑</button>
                <button class="op" title="下移" :disabled="i === draftEarly.length - 1" @click="moveRow(draftEarly, i, 1)">↓</button>
                <button class="op" title="上方插入" @click="insertRow(draftEarly, i, mkText)">插入</button>
                <button class="op x-op" title="删除整行" @click="deleteRow(draftEarly, i, mkText)">✕</button>
              </span>
            </div>
          </div>
        </section>

        <!-- 批次② 指标分配 -->
        <section class="batch">
          <button class="batch-h" type="button" @click="batchOpen.ind = !batchOpen.ind">
            <span class="bc">{{ batchOpen.ind ? '▾' : '▸' }}</span>② 指标分配（校额到校 + 市级统筹）
            <small>门槛 总分≥430 + 综合素质B + 同一初中连续三年学籍</small>
          </button>
          <template v-if="batchOpen.ind && canIndicator">
            <!-- 校额到校填报（名额/研判在校额到校页看） -->
            <h4 class="batch-sub">校额到校志愿<small style="font-weight:400;color:var(--gray-500)">（名额·研判见「<a class="lnk" @click="chSub = 'xed'; goTab('channels')">校额到校</a>」页）</small></h4>
            <div v-if="xedEligible.length" class="draft-actions" style="margin:6px 0">
              <button class="ghost" @click="prefillXed">↻ 按推荐重填</button>
              <span class="xed-src" style="margin:0">已按"值得冲→相当"自动填入（可改/清空；专业手填）</span>
            </div>
            <div v-if="xedEligible.length" class="uni-list">
              <div v-for="(s, i) in draftXed" :key="i" class="urow" :class="{ filled: s.school }">
                <span class="slot-no" :class="{ on: s.school }">{{ i + 1 }}</span>
                <select v-model="s.school" class="school-sel uni-sel">
                  <option :value="null">＋ 选优质高中（校额到校）</option>
                  <option v-for="e in xedEligible" :key="e.school" :value="e.school">{{ e.school }}（名额{{ e.n }}）</option>
                </select>
                <input v-if="s.school" v-model="s.majors" class="early-input" style="flex:1;min-width:0"
                  placeholder="专业(班)手填——专业代码待核，可沿用该校统招专业" />
                <span v-else class="uni-empty">未选</span>
                <span class="urow-ops">
                  <button class="op" title="上移" :disabled="i === 0" @click="moveRow(draftXed, i, -1)">↑</button>
                  <button class="op" title="下移" :disabled="i === draftXed.length - 1" @click="moveRow(draftXed, i, 1)">↓</button>
                  <button class="op" title="上方插入" @click="insertRow(draftXed, i, mkXed)">插入</button>
                  <button class="op x-op" title="删除整行" @click="deleteRow(draftXed, i, mkXed)">✕</button>
                </span>
              </div>
            </div>
            <p v-else class="xed-src">先在<b>首页填初中学校</b>，这里才能按名额选校额到校志愿。</p>

            <h4 class="batch-sub">市级统筹（统筹一/二）</h4>
            <div class="tc-ref">
              <p class="xed-src" style="margin:0 0 6px">⚠️ 可填统筹校以「<a class="lnk" @click="chSub = 'tc'; goTab('channels')">市级统筹</a>」页清单为准（含研判/名额/通勤）；这里手填"学校 + 专业(班)"。</p>
            </div>
            <div class="early-rows" style="margin-top:8px">
              <div v-for="(s, i) in draftTongchou" :key="i" class="early-row">
                <span class="slot-no">{{ i + 1 }}</span>
                <input v-model="s.text" class="early-input" placeholder="输入统筹学校 + 专业(班) …" />
                <span class="urow-ops">
                  <button class="op" title="上移" :disabled="i === 0" @click="moveRow(draftTongchou, i, -1)">↑</button>
                  <button class="op" title="下移" :disabled="i === draftTongchou.length - 1" @click="moveRow(draftTongchou, i, 1)">↓</button>
                  <button class="op" title="上方插入" @click="insertRow(draftTongchou, i, mkText)">插入</button>
                  <button class="op x-op" title="删除整行" @click="deleteRow(draftTongchou, i, mkText)">✕</button>
                </span>
              </div>
            </div>
          </template>
          <p v-else-if="batchOpen.ind && !canIndicator" class="xed-note warn">当前「{{ (IDENTITIES.find(x => x.v === form.identity) || {}).label }}」身份不可报指标分配（校额到校 / 市级统筹）。</p>
        </section>

        <!-- 批次③ 统一招生 -->
        <section class="batch">
          <button class="batch-h" type="button" @click="batchOpen.uni = !batchOpen.uni">
            <span class="bc">{{ batchOpen.uni ? '▾' : '▸' }}</span>③ 统一招生
            <small>2026 含贯通；{{ ZHIYUAN_SLOTS }} 志愿 ×2 专业，已按冲→稳→保预填 {{ filledSlots }}/{{ ZHIYUAN_SLOTS }}</small>
          </button>
          <template v-if="batchOpen.uni && canPuhao">
            <div class="draft-actions"><button class="ghost" @click="resetDraft">重置为推荐顺序</button></div>
            <div class="uni-list">
              <div v-for="(s, i) in draft" :key="i" class="urow" :class="{ filled: s.name }">
                <span class="slot-no" :class="{ on: s.name }">{{ i + 1 }}</span>
                <select v-model="s.name" @change="onSlotSchool(i)" class="school-sel uni-sel">
                  <option :value="null">＋ 选择学校（空）</option>
                  <option v-for="c in selectable" :key="c.name" :value="c.name">
                    [{{ bandOf(c.name) }}] {{ cleanName(c.name) }}（{{ c.school_code }}）
                  </option>
                </select>
                <div v-if="s.name" class="uni-majors">
                  <button v-for="m in majorsOf(s.name)" :key="m.major_code" type="button"
                    class="mchip" :class="{ on: s.picks.includes(m.major_code) }"
                    @click="togglePick(i, m.major_code)">
                    <b>{{ m.major_code }}</b> {{ cleanName(m.major_name) }}
                  </button>
                  <span v-if="!majorsOf(s.name).length" class="nomajor">该校暂无官方专业代码数据</span>
                </div>
                <span v-else class="uni-empty">未选</span>
                <span class="urow-ops">
                  <button class="op" title="上移" :disabled="i === 0" @click="moveUni(i, -1)">↑</button>
                  <button class="op" title="下移" :disabled="i === draft.length - 1" @click="moveUni(i, 1)">↓</button>
                  <button class="op" title="在此上方插入一个空志愿（其余顺延）" @click="insertUniAbove(i)">插入</button>
                  <button class="op x-op" title="删除整行" @click="deleteUni(i)">✕</button>
                </span>
              </div>
            </div>
            <div v-if="canGuantong && gtBlock" class="gt-ref">
              <h4 class="batch-sub">贯通培养可选项（2026 并入统招；380 分·仅限京籍；具体填报位以官方网报为准）</h4>
              <div class="gt-ref-list">
                <span v-for="(p, i) in gtBlock.projects" :key="i" class="xed-cell">{{ shortCampusName(p.school) }}·{{ p.major }}</span>
              </div>
            </div>
          </template>
          <p v-else class="xed-note warn">非京籍随迁子女不能报普通高中统招（只能报中职类）；上方仅供了解。</p>
        </section>

        <p v-if="result.admission_source" class="src">数据来源：{{ result.admission_source }}（统招）。提招/统筹/校额到校专业为手填占位，三批次为 2026 口径推断，一切以当年官方网报系统与简章为准。</p>
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

/* 输入区：全部条件常驻，紧凑排开 */
.form.card { padding: 12px 14px; }
.form .fields { display: flex; gap: 8px 10px; align-items: flex-end; flex-wrap: wrap; }
.form .frow + .frow { margin-top: 8px; }
.form label { display: flex; flex-direction: column; font-size: 11.5px; font-weight: 600;
  color: var(--gray-700); gap: 3px; }
.form label small { font-weight: 400; color: var(--gray-400); font-size: 10.5px; margin-left: 3px; }
.form input, .form select { padding: 0 9px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); font-size: 13px; background: #fff; height: 34px; box-sizing: border-box; }
.form input:disabled { background: var(--gray-100); color: var(--gray-400); }
.f-rank { width: 84px; }
.f-home { flex: 1; min-width: 150px; }
.f-mode { width: 88px; }
.f-km { width: 70px; }
.f-board .sw-line { display: flex; align-items: center; gap: 5px; height: 34px; }
.f-board .sw-line input { width: 16px; height: 16px; }
.sw-hint { font-size: 10.5px; font-weight: 400; color: var(--gray-500); }
.go { padding: 0 20px; height: 34px; background: var(--brand); color: #fff; border: none;
  border-radius: var(--radius-sm); font-size: 14px; font-weight: 600; white-space: nowrap; cursor: pointer; }
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
/* 图层 chip 按类着色（与地图小图标同色系，开启时实心）*/
.lchip.lc-minban.on { background: #fdf0e3; color: #b9601a; border-color: #e67e22; }
.lchip.lc-intl.on { background: #f4ecf7; color: #76448a; border-color: #9b59b6; }
.lchip.lc-voc.on { background: #e8f6f3; color: #117a65; border-color: #16a085; }
.lchip.lc-gt.on { background: #eaf2f8; color: #1f618d; border-color: #2980b9; }
.lchip.lc-tc.on { background: #fdecea; color: #a93226; border-color: #c0392b; }
.lchip.lc-xed.on { background: #fef9e7; color: #b9770e; border-color: #f1c40f; }
/* 校额到校 🎯 高亮环（叠加在公办 pin 上）*/
#zmap :deep(.xed-ring .xr) { transform: translate(-50%, -120%); background: #fff3cd; color: #b9770e;
  border: 1.5px solid #f1c40f; border-radius: var(--radius-full); font-size: 11px; font-weight: 700;
  padding: 0 5px; white-space: nowrap; box-shadow: 0 1px 3px rgba(0,0,0,.2); }
/* 民办/国际 学费筛选条 */
.priv-filter { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 0 0 8px; }
.priv-filter .pf-k { font-size: 12.5px; color: var(--gray-600); font-weight: 600; }
.pf-b { font-size: 12px; padding: 3px 9px; border: 1px solid var(--gray-300); background: #fff;
  border-radius: var(--radius-full); color: var(--gray-600); cursor: pointer; }
.pf-b.on { background: var(--brand-50); color: var(--brand-dark); border-color: var(--brand); }
.priv-filter .pf-n { font-size: 12px; color: var(--gray-500); margin-left: 2px; }
.priv-filter .pf-note { flex: 1 1 100%; font-size: 11.5px; color: var(--gray-500); line-height: 1.4; }
/* 市级统筹清单 */
.tc-verdict { font-size: 12.5px; line-height: 1.55; background: #fff8e1; border: 1px solid #ffe082;
  border-radius: var(--radius-xs); padding: 8px 10px; margin: 4px 0 8px; }
.tc-tbl .tc-campus { display: block; font-size: 11px; color: var(--gray-500); font-weight: 400; }
/* 统筹研判标 */
.tj { display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: var(--radius-full); white-space: nowrap; }
.tj-wen { background: #eafaf1; color: #1e8449; }     /* 稳(绿) */
.tj-bo { background: #fef5e7; color: #b9770e; }      /* 搏·有机会(橙) */
.tj-chong { background: #fdecea; color: #c0392b; }   /* 冲(红=拼一下) */
.tj-no { background: var(--gray-100); color: var(--gray-500); }  /* 够不上(灰) */
.tj-unk { background: #eaf2f8; color: #2471a3; }     /* 线待核(蓝) */
.tj-d { display: block; font-size: 10.5px; color: var(--gray-500); font-weight: 400; margin-top: 1px; }
.tc-judge-note { font-size: 11.5px; line-height: 1.6; color: var(--gray-600); background: var(--gray-50);
  border-radius: var(--radius-xs); padding: 7px 10px; margin: 8px 0 0; }
.tc-judge-note .tj { margin: 0 1px; }
.tc-yi { margin: 6px 0; }
.tc-yi > summary { font-size: 12.5px; color: var(--brand-dark); cursor: pointer; padding: 4px 0; }
/* 地图 + 详情面板：左图右栏 */
.map-detail { display: flex; gap: 12px; align-items: stretch; }
.map-col { flex: 1; min-width: 0; }

/* ── 查学校：统一浏览器 ── */
.explorewrap { background: var(--surface); box-shadow: var(--shadow-sm); padding: 14px 16px; }
.ex-filters { display: flex; flex-direction: column; gap: 7px; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--gray-100); }
.ex-row { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
.ex-k { font-size: 12px; font-weight: 700; color: var(--gray-600); margin-right: 2px; }
.ex-k.ex-k2 { margin-left: 10px; }
.ex-chip { font-size: 12px; padding: 3px 10px; border: 1px solid var(--gray-300); background: #fff; border-radius: var(--radius-full); cursor: pointer; color: var(--gray-700); }
.ex-chip:hover { border-color: var(--brand); }
.ex-chip.on { background: var(--brand-50); color: var(--brand-dark); border-color: var(--brand); font-weight: 700; }
.ex-sw { font-size: 12.5px; color: var(--gray-700); display: inline-flex; align-items: center; gap: 4px; cursor: pointer; margin-right: 6px; }
.ex-n { font-size: 12px; color: var(--gray-500); margin-left: auto; font-weight: 600; }
.ex-main { display: flex; gap: 12px; align-items: stretch; }
.ex-listcol { flex: 1; min-width: 0; }
.ex-table { min-width: 560px; }
.ex-table tbody tr { cursor: pointer; }
.ex-tr.on { background: var(--brand-50) !important; box-shadow: inset 3px 0 0 var(--brand); }
.ex-ty { font-size: 11.5px; color: var(--gray-500); white-space: nowrap; }
.ex-cht { white-space: nowrap; }
.ex-cbg { display: inline-block; min-width: 16px; text-align: center; font-size: 10.5px; font-weight: 700; padding: 1px 4px; margin-right: 2px; border-radius: 3px; background: var(--brand-50); color: var(--brand-dark); }
.ex-keycol { white-space: nowrap; }
.ex-keycol small { color: var(--gray-400); font-size: 10.5px; margin-right: 2px; }
/* ── 渠道科普 ── */
.chwrap { background: var(--surface); box-shadow: var(--shadow-sm); }
.ch-subnav { display: flex; gap: 4px; padding: 8px 12px 0; border-bottom: 1px solid var(--gray-100); flex-wrap: wrap; }
.ch-sb { font-size: 13px; font-weight: 600; padding: 8px 12px; border: 0; background: none; cursor: pointer; color: var(--gray-500); border-bottom: 2px solid transparent; }
.ch-sb:hover { color: var(--gray-800); }
.ch-sb.on { color: var(--brand-dark); border-bottom-color: var(--brand); }
.chwrap .listwrap { box-shadow: none; }
.ch-guide .g-item { border-bottom: 1px solid var(--gray-100); }
@media (max-width: 720px) { .ex-main { flex-direction: column; } }

.detail-panel { width: 320px; flex-shrink: 0; height: 460px; overflow-y: auto;
  background: var(--surface); border: 1px solid var(--gray-100); border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm); padding: 14px; }
.dp-empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; color: var(--gray-400); font-size: 13px; text-align: center; }
.dp-empty-ic { font-size: 32px; opacity: .5; }
.dp-head { display: flex; align-items: center; gap: 8px; }
.dp-head h3 { font-size: 16px; font-weight: 700; color: var(--gray-900); margin: 0; line-height: 1.3; }
.dp-type { flex-shrink: 0; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: var(--radius-full); background: var(--brand-50); color: var(--brand-dark); }
.dp-ch { display: flex; align-items: baseline; gap: 8px; padding: 4px 0; flex-wrap: wrap; }
.dp-ch-name { font-size: 12.5px; font-weight: 700; color: var(--gray-700); min-width: 62px; }
.dp-ch-detail { font-size: 12px; color: var(--gray-600); }
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
.dp-tc { border-top: 2px solid var(--brand-50); padding-top: 10px; }
.dp-tc .dp-title { color: #a93226; }
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
/* 底图保持清晰可读：注记已用 tileSize:128 缩小不再扎眼，故不再做大幅洗白。
   仅轻微降饱和让色调与界面协调，全对比、全透明保证街道/注记清楚。
   filter 只作用瓦片层，markerPane 不受影响，彩色学校标记照常凸显。 */
/* 底图压低调：大幅去饱和 + 提亮 + 微降对比，让彩色学校 pin 跳出来 */
#zmap :deep(.leaflet-tile-pane) {
  filter: saturate(0.4) brightness(1.08) contrast(0.93);
  opacity: 0.92;
}
/* 学校名常驻标签：紧凑、用界面字体，半透明白底，无箭头 */
#zmap :deep(.map-lbl) {
  background: rgba(255, 255, 255, 0.86); color: var(--gray-700);
  border: none; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  font-size: 11px; line-height: 1.2; font-weight: 600;
  padding: 1px 5px; border-radius: 4px; white-space: nowrap;
}
#zmap :deep(.map-lbl::before) { display: none; } /* 去掉小三角箭头 */
#zmap :deep(.map-lbl .map-xed) { color: #c0392b; font-weight: 700; margin-left: 2px; }
/* 寄宿角标：图标右上角"宿"字标记 */
#zmap :deep(.bd-badge) {
  position: absolute; top: -7px; right: -7px; z-index: 5;
  width: 15px; height: 15px; border-radius: 50%;
  background: #0d9488; color: #fff; border: 1.5px solid #fff;
  font-size: 9px; font-weight: 700; line-height: 12px; text-align: center;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
}
/* 校额到校名额角标(左上,区别于右上的"宿") */
#zmap :deep(.qt-badge) {
  position: absolute; top: -7px; left: -7px; z-index: 5;
  min-width: 15px; height: 15px; padding: 0 2px; border-radius: 8px;
  background: #f1c40f; color: #5b4708; border: 1.5px solid #fff;
  font-size: 9px; font-weight: 800; line-height: 12px; text-align: center;
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
.tab { position: relative; font-size: 13.5px; font-weight: 600; padding: 9px 11px 11px; white-space: nowrap;
  border: 1px solid transparent; border-bottom: none; background: transparent; color: var(--gray-500);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0; cursor: pointer;
  display: flex; align-items: center; gap: 5px; transition: color .15s, background .15s; }
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
/* 主入口(地图/草表)更突出 */
.tab-main { font-size: 14.5px; }
.tab-main .tab-ic { font-size: 16px; }
/* 二级聚合入口 */
.tab-more { color: var(--gray-500); margin-left: auto; }
.tab-more.on { color: var(--brand-dark); }
.more-caret { font-size: 10px; margin-left: 2px; }
/* 二级菜单浮层：就地下拉，锚在"查学校"按钮一侧，不再跳到最左 */
.tabbar { position: relative; z-index: 1000; }
.more-menu { position: absolute; top: 100%; right: 4px; z-index: 2000;
  min-width: 260px; max-width: min(94vw, 420px);
  background: var(--surface); border: 1px solid var(--gray-200); border-radius: var(--radius-sm);
  margin-top: 2px; padding: 10px 12px; box-shadow: 0 6px 18px rgba(0,0,0,.14); }
.mm-group { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.mm-k { font-size: 12px; color: var(--gray-500); font-weight: 600; margin-right: 2px; }
.mchip { font-size: 13px; padding: 5px 11px; border: 1px solid var(--gray-300); background: #fff;
  border-radius: var(--radius-full); color: var(--gray-700); cursor: pointer; display: inline-flex; align-items: center; gap: 4px; }
.mchip.on { background: var(--brand-50); color: var(--brand-dark); border-color: var(--brand); }
.mchip i { font-style: normal; font-size: 11px; font-weight: 700; color: var(--gray-400); }
.mchip.on i { color: var(--brand-dark); }
.mm-tip { font-size: 11.5px; color: var(--gray-400); margin: 2px 0 0; }
.lnk { color: var(--brand-dark); font-weight: 700; cursor: pointer; text-decoration: underline; }
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
.t-curr { font-size: 12px; color: var(--gray-600); line-height: 1.5;
  width: 175px; min-width: 150px; max-width: 200px; white-space: normal; overflow-wrap: break-word; }
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
/* 校额到校：按初中查名额 */
.xed-query { margin: 0 0 14px; }
.xed-qlabel { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; font-weight: 600; color: var(--gray-700); max-width: 420px; }
.xed-input { padding: 9px 11px; border: 1px solid var(--gray-300); border-radius: var(--radius-xs); font-size: 14px; background: #fff; }
.xed-miss { font-size: 12.5px; color: var(--gray-500); margin-top: 8px; }
.xed-card { margin-top: 10px; border: 1px solid var(--brand-50); background: var(--surface); border-radius: var(--radius-sm); box-shadow: var(--shadow-sm); padding: 12px 14px; }
.xed-card-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px; }
.xed-card-head b { font-size: 15px; color: var(--gray-900); }
.xed-total { font-size: 13px; color: var(--brand-dark); background: var(--brand-50); padding: 2px 9px; border-radius: var(--radius-full); }
.xed-total b { font-size: 15px; color: var(--brand-dark); }
.xed-grid { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.xed-cell { font-size: 12.5px; color: var(--gray-800); background: var(--gray-50); border: 1px solid var(--gray-100); border-radius: var(--radius-xs); padding: 4px 9px; }
.xed-cell i { color: var(--gray-500); font-style: normal; margin-right: 5px; }
.xed-cell b { color: var(--brand-dark); }
.xed-note { font-size: 11.5px; color: var(--gray-500); margin-top: 9px; line-height: 1.6; }
.xed-note.warn { color: #b45309; background: var(--warning-bg); padding: 7px 9px; border-radius: var(--radius-xs); }
.xed-src { font-size: 11px; color: var(--gray-400); margin-top: 8px; }
/* 校额到校 报名方案推荐 */
.xed-rec { margin: 10px 0 14px; border: 1px solid var(--gray-100); border-radius: var(--radius-sm); padding: 12px 14px; background: var(--surface); }
.xed-rec-warn { font-size: 12.5px; color: #b45309; background: var(--warning-bg); border-radius: var(--radius-xs); padding: 9px 11px; line-height: 1.6; margin: 0 0 10px; }
.xed-rec-list { display: flex; flex-direction: column; gap: 5px; }
.xed-rec-row { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.rt { flex: 0 0 auto; font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: var(--radius-xs); white-space: nowrap; }
.rt-worth { background: #d8f5e3; color: #1e8e4e; }
.rt-similar { background: #fdf3d4; color: #9a7d0a; }
.rt-waste { background: var(--warning-bg); color: #b45309; }
.rt-unknown { background: var(--gray-100); color: var(--gray-400); }
.rt-name { color: var(--gray-900); }
.rt-meta { color: var(--gray-500); font-size: 11.5px; }
.xed-imgtoggle { margin: 4px 0 10px; background: var(--gray-50); border: 1px solid var(--gray-200);
  border-radius: var(--radius-sm); padding: 9px 14px; font-size: 13px; font-weight: 600;
  color: var(--brand-dark); cursor: pointer; }
.xed-imgtoggle:hover { border-color: var(--brand); }
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
/* 三批次分区（可折叠）*/
.batch { margin-top: 10px; }
.batch-h { width: 100%; text-align: left; display: block; cursor: pointer;
  font-size: 15px; font-weight: 700; color: var(--brand-deeper);
  background: var(--gray-50); border: 1px solid var(--gray-100); border-radius: var(--radius-sm);
  padding: 10px 12px; margin: 0 0 10px; }
.batch-h:hover { border-color: var(--brand); }
.batch-h .bc { display: inline-block; width: 16px; color: var(--gray-400); font-weight: 400; }
.batch-h small { font-weight: 400; font-size: 12px; color: var(--gray-500); margin-left: 6px; }
.batch-sub { font-size: 13px; color: var(--gray-700); margin: 14px 0 8px; }
.early-rows { display: flex; flex-direction: column; gap: 6px; }
.early-row { display: flex; align-items: center; gap: 8px; }
.early-input { flex: 1; min-width: 0; padding: 7px 9px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); font-size: 12.5px; background: #fff; }
.gt-ref { margin-top: 14px; }
.gt-ref-list { display: flex; flex-wrap: wrap; gap: 6px; }
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
/* 统招：学校+专业同一行，去空白 */
.uni-list { display: flex; flex-direction: column; gap: 6px; }
.urow { display: flex; align-items: center; gap: 8px; padding: 6px 10px; min-width: 0;
  border: 1px solid var(--gray-100); border-radius: var(--radius-xs); background: var(--gray-50); }
.urow.filled { background: var(--surface); border-color: var(--brand-50); }
.uni-sel { flex: 0 0 300px; width: 300px; }
.uni-majors { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.uni-empty { flex: 1; color: var(--gray-300); font-size: 12px; }
.urow-ops { flex: 0 0 auto; display: flex; gap: 3px; }
.op { height: 26px; min-width: 26px; padding: 0 6px; font-size: 12px; border: 1px solid var(--gray-200);
  background: #fff; border-radius: var(--radius-xs); color: var(--gray-500); cursor: pointer; }
.op:hover:not(:disabled) { border-color: var(--brand); color: var(--brand-dark); }
.op:disabled { opacity: .35; cursor: default; }
.op.x-op:hover { color: var(--error); border-color: var(--error); }
@media (max-width: 640px) { .uni-sel { flex-basis: 130px; width: 130px; } }
/* 市级统筹参考 */
.tc-ref { background: var(--gray-50); border-radius: var(--radius-xs); padding: 9px 11px; margin-bottom: 4px; }
.tc-tier { font-size: 12px; line-height: 1.7; }
.tc-tag { display: inline-block; font-weight: 700; color: var(--brand-dark); background: var(--brand-50);
  border-radius: var(--radius-xs); padding: 0 6px; margin-right: 6px; }
.tc-desc { color: var(--gray-500); margin-right: 6px; }
.tc-schools { color: var(--gray-800); }

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
