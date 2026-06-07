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
const batchOpen = reactive({ early: true, ind: true, uni: true })   // 三批次折叠
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
const tab = ref<'map' | 'list' | 'minban' | 'intl' | 'voc' | 'gt' | 'xed' | 'tc' | 'draft'>('map')   // +贯通+校额到校+统筹
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
function selectPoint(p: Point) { selectedPoint.value = p; selectedTc.value = null }
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
const XED_TAG_COLOR: Record<string, string> = { worth: '#e74c3c', similar: '#e67e22', waste: '#95a5a6', unknown: '#2980b9' }
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
    const coop = isCoopPoint(p)
    // 图层过滤：gongban 控普通公办点，coop 控中外合作校
    if (!layers.gongban && !(coop && layers.coop)) return
    if (coop && !layers.coop && !layers.gongban) return
    bounds.push([p.lat, p.lon])
    const boarding = !!cardOfPoint(p)?.boarding
    const icon = p.kind === 'full' ? pin(p.color, p.band, boarding) : smallIcon(p.color, boarding)
    const mk = L.marker([p.lat, p.lon], { icon }).addTo(publicLayer).on('click', () => selectPoint(p))
    // 缺省常驻显示学校名：重点推荐校(冲/稳/保)常驻，其余小点悬停显示，避免拥挤
    // 校额到校徽标：选定初中分到该校名额时，名字后挂"🎯N"
    const q = xedQuotaByName.value[p.name]
    const lbl = shortName(p.name) + (q ? ` <span class="map-xed">🎯${q}</span>` : '')
    if (p.kind === 'full') {
      mk.bindTooltip(lbl, { permanent: true, direction: 'bottom', offset: [0, 2], className: 'map-lbl' })
    } else {
      mk.bindTooltip(lbl, { direction: 'top', offset: [0, -6], className: 'map-lbl' })
    }
  })
  if (layers.gongban || layers.coop) publicLayer.addTo(mapInst)

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
    const icon = big ? pin(color, j.label) : smallIcon(color)
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
    const color = j ? j.color : '#b9770e'
    L.marker([p.lat, p.lon], { icon: pin(color, `🎯${q}`) }).addTo(xedLayer)
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
// 统筹校研判：估分 vs 该校统招线。因统筹实际线通常比统招线低（最多约20-30分），
// 故可够范围按"统招线下"放宽：稳/冲/搏(有机会)/够不上。
// 线优先用 2025 双源确认(score_2025_tongzhao)，缺则退用历年参考(score_ref，标"历年线")。
function tcJudge(s: any): { label: string; cls: string; d: number | null; line: number | null; ref: boolean } {
  const conf = typeof s.score_2025_tongzhao === 'number' ? s.score_2025_tongzhao : null
  const ref = typeof s.score_ref === 'number' ? s.score_ref : null
  const line = conf ?? ref
  const isRef = conf == null && ref != null
  if (line == null || estScore.value == null) return { label: '线待核', cls: 'tj-unk', d: null, line: null, ref: false }
  const d = Math.round(estScore.value - line)
  const band = d >= 10 ? { label: '稳', cls: 'tj-wen' }
    : d >= -10 ? { label: '冲', cls: 'tj-chong' }
    : d >= -30 ? { label: '搏', cls: 'tj-bo' }     // 统招线下10~30：靠统筹降分,有机会但长线
    : { label: '够不上', cls: 'tj-no' }
  return { ...band, d, line, ref: isRef }
}

const newSchools = computed<any[]>(() => (result.value as any)?.new_schools?.schools || [])

const privAll = computed<PrivSchool[]>(() => result.value?.private_schools?.schools || [])
const minbanList = computed<PrivSchool[]>(() => privAll.value.filter(s => s.in_minban_list))
const intlList = computed<PrivSchool[]>(() => privAll.value.filter(s => s.in_intl_list))
// 当前展示的民办/国际清单（按激活的 Tab）
// 学费筛选：从"15.8万/年"、"8-16.8万"、"22.7-26.2万"等串里取最大数字作上限分档
const tuitionBand = ref<'all' | 'le10' | 'mid' | 'gt20'>('all')
function tuitionMax(s: any): number | null {
  const t = s?.tuition
  if (!t) return null
  const nums = String(t).match(/\d+(\.\d+)?/g)
  if (!nums) return null
  return Math.max(...nums.map(Number))
}
const privView = computed<PrivSchool[]>(() => {
  let list = tab.value === 'intl' ? intlList.value : minbanList.value
  if (tuitionBand.value !== 'all') {
    list = list.filter(s => {
      const m = tuitionMax(s)
      if (m == null) return false   // 无标价不进档位筛选
      if (tuitionBand.value === 'le10') return m <= 10
      if (tuitionBand.value === 'mid') return m > 10 && m <= 20
      return m > 20
    })
  }
  return list
})
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
        <label class="f-mode">考生身份
          <select v-model="form.identity">
            <option v-for="x in IDENTITIES" :key="x.v" :value="x.v">{{ x.label }}</option>
          </select>
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
      <!-- 标签页：地图 / 普高清单 / 志愿草表 -->
      <div class="tabs" role="tablist">
        <button class="tab" :class="{ on: tab === 'map' }" @click="tab = 'map'">
          <span class="tab-ic">📍</span>志愿地图
        </button>
        <button class="tab" :class="{ on: tab === 'list' }" @click="tab = 'list'">
          普高清单<span class="tab-cnt">{{ result.public_list.length }}</span>
        </button>
        <button v-if="minbanList.length" class="tab" :class="{ on: tab === 'minban' }" @click="tab = 'minban'">
          民办普高<span class="tab-cnt">{{ minbanList.length }}</span>
        </button>
        <button v-if="intlList.length" class="tab" :class="{ on: tab === 'intl' }" @click="tab = 'intl'">
          国际学校<span class="tab-cnt">{{ intlList.length }}</span>
        </button>
        <button v-if="vocList.length" class="tab" :class="{ on: tab === 'voc' }" @click="tab = 'voc'">
          中职/职教<span class="tab-cnt">{{ vocList.length }}</span>
        </button>
        <button v-if="gtBlock" class="tab" :class="{ on: tab === 'gt' }" @click="tab = 'gt'">
          贯通培养<span class="tab-cnt">{{ gtBlock.projects.length }}</span>
        </button>
        <button class="tab" :class="{ on: tab === 'xed' }" @click="tab = 'xed'">
          校额到校
        </button>
        <button class="tab" :class="{ on: tab === 'tc' }" @click="tab = 'tc'">
          市级统筹
        </button>
        <button class="tab" :class="{ on: tab === 'draft' }" @click="tab = 'draft'">
          志愿草表<span class="tab-cnt">{{ filledSlots }}/{{ ZHIYUAN_SLOTS }}</span>
        </button>
      </div>

      <!-- TAB 1：地图 -->
      <div class="mapwrap" v-show="tab === 'map'">
        <div class="map-head">
          <h2>全{{ result.district }}学校分布</h2>
          <div class="layer-chips">
            <button class="lchip" :class="{ on: layers.gongban }" @click="layers.gongban = !layers.gongban">公办普高</button>
            <button class="lchip" :class="{ on: layers.coop }" @click="layers.coop = !layers.coop">中外合作/国际班</button>
            <button class="lchip lc-minban" :class="{ on: layers.minban }" @click="layers.minban = !layers.minban">民办普高</button>
            <button class="lchip lc-intl" :class="{ on: layers.intl }" @click="layers.intl = !layers.intl">国际/双语</button>
            <button class="lchip lc-voc" :class="{ on: layers.voc }" @click="layers.voc = !layers.voc">中职/职教</button>
            <button class="lchip lc-gt" :class="{ on: layers.gt }" @click="layers.gt = !layers.gt">贯通(全市)</button>
            <button v-if="tongchou" class="lchip lc-tc" :class="{ on: layers.tc }" @click="layers.tc = !layers.tc">市级统筹</button>
            <button class="lchip lc-xed" :class="{ on: layers.xed }" @click="layers.xed = !layers.xed">🎯校额到校</button>
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
                <div v-if="xedQuotaByName[selectedPoint.name]">
                  <dt>🎯 校额到校（{{ cleanName(xedSel?.name || '') }}）</dt>
                  <dd>分到本校 <b>{{ xedQuotaByName[selectedPoint.name] }}</b> 个名额
                    <span v-if="xedJudgeByName[selectedPoint.name]" class="tj" :class="'rt-' + xedJudgeByName[selectedPoint.name].tag">{{ XED_TAG[xedJudgeByName[selectedPoint.name].tag].label }}</span>
                    <span class="dp-muted">（校内竞争·录取即锁定）</span></dd>
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

              <!-- 市级统筹结构化信息 -->
              <div v-if="selectedTc" class="dp-block dp-tc">
                <div class="dp-title">市级统筹信息</div>
                <dl class="dp-kv">
                  <div><dt>类别 · 投朝阳名额</dt><dd>{{ selectedTc._tier }} · 投朝阳 <b>{{ selectedTc.quota_chaoyang }}</b> 名</dd></div>
                  <div><dt>办学层次</dt><dd>{{ selectedTc.level || '待核' }}</dd></div>
                  <div><dt>研判（你估≈{{ estScore }}）</dt>
                    <dd><span class="tj" :class="tcJudge(selectedTc).cls">{{ tcJudge(selectedTc).label }}</span>
                      <span v-if="tcJudge(selectedTc).d != null" class="dp-mg">
                        {{ tcJudge(selectedTc).ref ? '历年线' : '线' }}{{ tcJudge(selectedTc).line }}·Δ{{ (tcJudge(selectedTc).d ?? 0) > 0 ? '+' : '' }}{{ tcJudge(selectedTc).d }}</span></dd></div>
                  <div><dt>通勤（到家）</dt>
                    <dd v-if="selectedTc.dist">{{ selectedTc.dist.km }}km · {{ selectedTc.dist.mins }}分钟<small>（{{ selectedTc.dist.label }}）</small></dd>
                    <dd v-else class="dp-muted">填家庭住址后显示</dd></div>
                  <div><dt>住宿</dt>
                    <dd><span v-if="selectedTc.boarding === true" class="t-yes">🛏 可住宿</span>
                      <span v-else-if="selectedTc.boarding === false">不提供（{{ selectedTc.district }}，需走读/自理）</span>
                      <span v-else class="dp-muted">待核</span></dd></div>
                </dl>
                <table v-if="selectedTc.score_lines && selectedTc.score_lines.length" class="dp-table">
                  <thead><tr><th>年</th><th>统招线</th><th>口径</th></tr></thead>
                  <tbody>
                    <tr v-for="sl in selectedTc.score_lines" :key="sl.year">
                      <td>{{ sl.year }}</td><td>{{ sl.score }}<small>（{{ sl.scale }}制）</small></td><td>{{ sl.conf }}</td>
                    </tr>
                  </tbody>
                </table>
                <div v-if="selectedTc.style" class="dp-line">🏫 {{ selectedTc.style }}</div>
                <div v-if="selectedTc.gaokao" class="dp-line dp-muted">🎓 高考(民间·非官方)：{{ selectedTc.gaokao }}</div>
                <div class="dp-line dp-muted">📍 {{ selectedTc.address }}</div>
                <div class="dp-line dp-warn">⚠️ 比的是<b>统招线</b>(非统筹实际线，统筹线通常更低、偏保守)；能否录取看朝外当年报该校统筹的名次，以《简章》为准。</div>
              </div>
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
        <p v-if="!canPuhao" class="board-note">⚠️ 非京籍随迁子女<b>不能报普通高中统招</b>，以下普高清单<b>仅供了解</b>（你可报中职：中专/职高/技校/五年制）。</p>
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

        <!-- 2026 新增公办普高（无历史线） -->
        <template v-if="newSchools.length">
          <h4 class="batch-sub">🆕 2026 新增公办普高（{{ newSchools.length }} 所·无历史线，仅供了解）</h4>
          <p class="list-note">这些是 2026 新取得招生资格的新校 / 新高中，<b>无往年录取线、不做冲/稳/保研判</b>。
            招生计划官方约 <b>6 月</b>发布（网传数未采）。判断主要看 <b>办学体系 + 可类比的母体/同体系校</b>，并参加学校招生说明会。</p>
          <div class="table-scroll">
            <table class="list-table">
              <thead><tr><th>学校</th><th>办学体系</th><th>可类比参考</th><th>方向</th><th>通勤</th><th>住宿</th><th>地址</th></tr></thead>
              <tbody>
                <tr v-for="s in newSchools" :key="s.name">
                  <td class="t-name">{{ cleanName(s.name) }} <span class="addr-tag warn">新校</span></td>
                  <td class="t-curr">{{ s.system }}</td>
                  <td class="t-curr"><span v-if="s.analog && s.analog.length">{{ s.analog.join('、') }}</span><span v-else class="t-no">待核</span></td>
                  <td>{{ s.direction }}</td>
                  <td class="t-dist">{{ s.dist ? s.dist.km + 'km' : '—' }}</td>
                  <td><span v-if="s.boarding === true" class="t-yes">🛏</span><span v-else-if="s.boarding === false" class="t-no">—</span><span v-else class="addr-tag">待核</span></td>
                  <td class="t-addr">{{ s.address }}<span v-if="!s.lat" class="addr-tag">概址</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="list-tip">来源：北京市教委 2026-05-16《具有招生资格的高级中等学校名单》（朝阳 #28/29/30/48）。
            <b>各校 2026 招生计划/班数官方未发布</b>；报考前以 6 月官方简章 + 学校招生说明会为准。新校首届有磨合风险、出口（高考）3 年后才有。</p>
        </template>
      </div>

      <!-- TAB 3/4：民办普高 / 国际学校 清单（共用表格，按 Tab 过滤）-->
      <div class="listwrap" v-show="tab === 'minban' || tab === 'intl'">
        <p class="list-note" v-if="result.private_schools">
          <template v-if="tab === 'minban'">朝阳区<b>民办</b>高中（含国内高考方向 / 双轨）{{ minbanList.length }} 所。</template>
          <template v-else>朝阳区<b>国际 / 双语</b>高中（国际课程 / 出国方向）{{ intlList.length }} 所。</template>
          地址/电话/住宿来自 <b>bjeea 2025 官方统招计划册</b>；<b>办学性质 / 方向 / 课程 / 学费</b>为公开网络交叉核验
          （多为升学平台口径，约 2024–2025，<b>仅供参考</b>）。
        </p>
        <div class="priv-filter" v-if="result.private_schools">
          <span class="pf-k">学费</span>
          <button class="pf-b" :class="{ on: tuitionBand === 'all' }" @click="tuitionBand = 'all'">全部</button>
          <button class="pf-b" :class="{ on: tuitionBand === 'le10' }" @click="tuitionBand = 'le10'">≤10万</button>
          <button class="pf-b" :class="{ on: tuitionBand === 'mid' }" @click="tuitionBand = 'mid'">10–20万</button>
          <button class="pf-b" :class="{ on: tuitionBand === 'gt20' }" @click="tuitionBand = 'gt20'">&gt;20万</button>
          <span class="pf-n">{{ privView.length }} 所</span>
          <span class="pf-note">本区民办/国际校<b>均在中考统招计划内</b>填报；<b>无公开统一录取线</b>（按分/自主），故不设"录取分/计划内外"筛选。</span>
        </div>
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
        <p v-if="!canGuantong" class="board-note">⚠️ 贯通培养<b>仅限京籍考生</b>；当前「{{ identityLabel }}」身份不可报，以下<b>仅供了解</b>。</p>
        <p class="list-note">
          <b>贯通培养</b>＝<b>7 年学制 → 本科</b>（中职/高职段 + 本科段，专升本性质）。{{ gtBlock.overall.year }} 年全市
          <b>{{ gtBlock.projects.length }}</b> 个项目 / 8 所承办院校，计划合计 <b>{{ gtBlock.overall.total_plan }}</b> 人。
          <span class="g-warn" style="display:inline-block;margin-top:6px">
            ⚠️ 报考门槛：中考总分 ≥ <b>{{ gtBlock.overall.min_score }}</b> 分；<b>{{ gtBlock.overall.huji }}</b>；2025 在<b>{{ gtBlock.overall.batch }}</b>录取，<b>2026 起并入统一招生批次</b>（380 分门槛不变）。全市招生不分区，朝阳京籍考生均可报。
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
          <label class="xed-qlabel">孩子初中校
            <input list="xedSchoolList" v-model="xedQuery" placeholder="输入/选择，如 朝阳外国语学校" class="xed-input" />
          </label>
          <datalist id="xedSchoolList">
            <option v-for="r in xedBlock.rows" :key="r.code" :value="r.name" />
          </datalist>
          <div v-if="xedQuery && !xedSel" class="xed-miss">未匹配到该初中（试试更短的关键词，或在下方官方原图核对）</div>
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
      <div class="listwrap" v-show="tab === 'tc'">
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
            <span class="tj tj-wen">稳</span>Δ≥+10　<span class="tj tj-chong">冲</span>−10~+10　<span class="tj tj-bo">搏</span>−30~−10　<span class="tj tj-no">够不上</span>Δ&lt;−30　<span class="tj tj-unk">线待核</span>无公开线。
            「搏」=估分虽低于统招线 10–30 分，但<b>统筹线通常更低、仍有机会</b>（长线，依赖该校统筹降分幅度，热门校未必降这么多）。
            <b>估分随你填的区排名动态变化</b>（不是写死）。⚠️ 比的是各校<b>统招线（非统筹实际线）</b>，<b>统筹线通常更低</b>，故偏保守——"够不上"才基本无望，"冲"档实际机会更大。估分为一分一段插值近似。<b>「历年线」</b>=单源/历年参考(可信度低于 2025 双源确认的"线")；新校无历史则保持"线待核"。
          </p>
        </template>

        <p class="list-tip">
          ✓ 上方清单据 <b>bjeea 2025 官方简章</b>逐格核 + 合计对账（统筹一各校合计=405 与官方一致）；“投朝阳”=该校 2025 投放朝阳区的名额。
          ⚠️ 研判用的是各校<b>统招线</b>（全市可比的强度参考），<b>统筹实际录取线官方不公开、通常更低</b>；最终能否录取取决于<b>朝外当年报该校统筹的同学名次</b>，须查简章「本初中分配名额」+ 问初中部。各年随计划变。
          市级统筹与校额到校同批次：<b>被录即锁定、后续批次作废</b>；在「志愿草表 → 批次② 指标分配」里填写。
        </p>
      </div>

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
            <label class="xed-qlabel" style="max-width:440px">孩子初中校（与「校额到校」页共用）
              <input list="xedSchoolList2" v-model="xedQuery" class="xed-input" placeholder="输入/选择，如 朝阳外国语学校" />
            </label>
            <datalist id="xedSchoolList2"><option v-for="r in (xedBlock ? xedBlock.rows : [])" :key="r.code" :value="r.name" /></datalist>
            <p v-if="xedSel && xedSel.by_school" class="xed-src">{{ cleanName(xedSel.name) }}：校额到校共 {{ xedSel.total }} 个，下面按名额选优质高中（括号为本校名额）。</p>
            <p v-else-if="xedSel" class="xed-note warn">{{ cleanName(xedSel.name) }}：合计 {{ xedSel.total }}，明细待核——优质高中与专业请对照官方原图手填。</p>
            <p v-else class="xed-src">先填上面的初中校，下面才能按名额选优质高中。</p>

            <!-- 按分数的报名方案推荐 + 风险 -->
            <div v-if="xedRecommend.length" class="xed-rec">
              <p class="xed-rec-warn">⚠️ <b>风险</b>：校额到校在统招<b>之前</b>录取、<b>一旦录取就锁定、后续批次作废</b>。建议<b>只填比你统招更够得着的好学校</b>（下方 ✅），<b>别填你统招本来就能上的</b>（⚠️），否则等于用校额到校把自己锁进更差的结果。</p>
              <div class="xed-rec-list">
                <div v-for="e in xedRecommend" :key="e.school" class="xed-rec-row">
                  <span class="rt" :class="XED_TAG[e.tag].cls">{{ XED_TAG[e.tag].label }}</span>
                  <b class="rt-name">{{ e.school }}</b>
                  <span class="rt-meta">名额{{ e.n }}<template v-if="e.ref"> · 统招位次≈{{ e.ref }}</template></span>
                </div>
              </div>
              <p class="xed-src">推荐依据：各优质高中“统招录取位次”对比你的区排名 <b>{{ form.rank }}</b>。✅=统招够不上、校额到校才有机会；⚠️=统招本可达、占名额意义小。校额到校实际按本初中<b>校内排名</b>录取、无官方各校线，仅作策略参考。</p>
            </div>

            <div v-if="xedEligible.length" class="draft-actions" style="margin:10px 0 6px">
              <button class="ghost" @click="prefillXed">↻ 按推荐重填校额到校志愿</button>
              <span class="xed-src" style="margin:0">已按"值得冲→相当"自动填入（可手动改/清空；专业请手填）</span>
            </div>
            <div class="uni-list">
              <div v-for="(s, i) in draftXed" :key="i" class="urow" :class="{ filled: s.school }">
                <span class="slot-no" :class="{ on: s.school }">{{ i + 1 }}</span>
                <select v-model="s.school" class="school-sel uni-sel" :disabled="!xedEligible.length">
                  <option :value="null">＋ 选优质高中（校额到校）</option>
                  <option v-for="e in xedEligible" :key="e.school" :value="e.school">{{ e.school }}（名额{{ e.n }}）</option>
                </select>
                <input v-if="s.school" v-model="s.majors" class="early-input" style="flex:1;min-width:0"
                  placeholder="专业(班)手填——专业代码待核，可沿用该校统招专业" />
                <span v-else class="uni-empty">未选</span>
                <button v-if="s.school" class="op x-op" title="清空" @click="s.school = null; s.majors = ''">✕</button>
              </div>
            </div>
            <h4 class="batch-sub">市级统筹（统筹一/二/三）</h4>
            <div class="tc-ref">
              <p class="xed-src" style="margin:0 0 6px">⚠️ 下表仅为<b>三档方向说明（待核）</b>，<b>不是朝阳可报名单</b>；本区好校（人朝/清华附中朝阳·望京/东师朝/对外经贸94中）请走统招·校额到校。具体可填统筹校须按<b>朝外在《招生简章》分到的名额</b>逐校核对：</p>
              <div v-for="t in TONGCHOU_REF" :key="t.tier" class="tc-tier">
                <span class="tc-tag">{{ t.tier }}</span><span class="tc-desc">{{ t.desc }}</span>
                <span class="tc-schools">{{ t.schools.join('、') }}</span>
              </div>
            </div>
            <div class="early-rows" style="margin-top:8px">
              <div v-for="(s, i) in draftTongchou" :key="i" class="early-row">
                <span class="slot-no">{{ i + 1 }}</span>
                <input v-model="s.text" list="tcList" class="early-input" placeholder="输入/选择统筹学校 + 专业(班) …" />
              </div>
            </div>
            <datalist id="tcList">
              <option v-for="s in tcOptions" :key="s" :value="s" />
            </datalist>
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
#zmap :deep(.leaflet-tile-pane) {
  filter: saturate(0.92);
  opacity: 1;
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
