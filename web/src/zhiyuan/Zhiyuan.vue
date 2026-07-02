<script setup lang="ts">
import { ref, reactive, computed, nextTick, watch, onMounted } from 'vue'
import { USER_DEFAULTS } from './user-defaults'
import JudgeLegend from './JudgeLegend.vue'
import DraftRow from './DraftRow.vue'
import DistrictBrowse from './DistrictBrowse.vue'
import { fetchMe, getProfile, putProfile } from '../shared/auth/auth'
import AccountMenu from '../shared/auth/AccountMenu.vue'

declare const L: any

const MODES = [
  { v: 'driving', label: '驾车' },
  { v: 'transit', label: '公交' },
  { v: 'bicycling', label: '骑行' },
  { v: 'walking', label: '步行' },
]
const ZHIYUAN_SLOTS = 12   // 统一招生志愿数（每志愿 2 专业）
// 区切换:full 区=冲稳保全功能(数据已对标朝阳);其余=browse(校库,见 DistrictBrowse)。
// full/browse 由后端按 <区>.yaml 是否有录取线动态判定(见 districtModes)。
const DISTRICTS: [string, string][] = [
  ['chaoyang', '朝阳'], ['haidian', '海淀'], ['xicheng', '西城'], ['dongcheng', '东城'],
  ['fengtai', '丰台'], ['shijingshan', '石景山'], ['mentougou', '门头沟'], ['fangshan', '房山'],
  ['tongzhou', '通州'], ['shunyi', '顺义'], ['changping', '昌平'], ['daxing', '大兴'],
  ['huairou', '怀柔'], ['pinggu', '平谷'], ['miyun', '密云'], ['yanqing', '延庆'],
]
const curDistrict = ref('chaoyang')
const districtCn = computed(() => (DISTRICTS.find(d => d[0] === curDistrict.value) || ['', '朝阳'])[1])
// 各区模式(full=冲稳保全功能 / browse=校库)由后端 /api/zhiyuan/districts 决定,随数据补齐自动升级。
// 朝阳兜底 full,避免接口未回时首屏空白。
const districtModes = ref<Record<string, string>>({ chaoyang: 'full' })
const curMode = computed(() => districtModes.value[curDistrict.value] || 'browse')
async function loadDistrictModes() {
  try {
    const r = await fetch('/api/zhiyuan/districts')
    const d = await r.json()
    const m: Record<string, string> = {}
    for (const x of (d.districts || [])) m[x.py] = x.mode
    districtModes.value = m
  } catch { /* 保持兜底 */ }
}

// 升学渠道科普(重设计)：渠道卡 / 官方入口 / 时间线。来源 bjeea.cn / 北京市教委 / 首都之窗(T1)。
const BJEEA_ZK = 'https://www.bjeea.cn/'   // 中考中招频道页(/html/zkzh/)已 403,改用考试院首页(稳定·顶部导航进中招)
const XED_OFFICIAL = 'https://www.bjeea.cn/html/zkzh/jhcx/2025/0701/87193.html'
const CHANNELS = [
  { key: '统招', icon: '🎓', name: '统一招生（统招）', one: '最后批次，按总分从高到低、平行志愿录取',
    threshold: '各校录取线（看你的分/位次）',
    detail: ['分数优先、遵循志愿：想冲的放前面零成本，末位放保底', '2025 起总分 510；民办普高、中外合作、(2026)贯通都在这一批填'],
    use: { label: '去「志愿草表 ③」填', tab: 'draft' }, link: BJEEA_ZK, linkName: '考试院·中招' },
  { key: '校额', icon: '🎯', name: '校额到校', one: '名额定向到你初中，只和本校同学比',
    threshold: '中考≥430/510 + 综合素质 B + 连续 3 年本校学籍',
    detail: ['统招前录取、录取即锁定；别填"统招本来就能上的校"，否则锁低自己', '中低位次最大逆袭通道：校内排名靠前 + 初中有好校名额即可进好公办'],
    use: { label: '去「草表 ②」', tab: 'draft' }, link: XED_OFFICIAL, linkName: '名额公示' },
  { key: '统筹', icon: '🌆', name: '市级统筹', one: '跨区/全市名额，按分竞争，线通常更低',
    threshold: '同校额到校（≥430/510 等）',
    detail: ['与校额到校同属指标分配批、统招前录取', '多为外区/郊区远校，需配合住宿'],
    use: { label: '去「草表 ②」', tab: 'draft' }, link: BJEEA_ZK, linkName: '考试院·中招' },
  { key: '贯通', icon: '🏗️', name: '贯通培养', one: '中考≥380，7 年直接到本科',
    threshold: '中考≥380（510 制）·仅限京籍',
    detail: ['中职/高职段公办免学费、本科段按本科收；各阶段需转段考核', '2026 起并入统一招生批填报'],
    use: { label: '查学校筛「贯通」', tab: 'explore', filter: '贯通' }, link: BJEEA_ZK, linkName: '考试院·中招' },
  { key: '民办', icon: '🏫', name: '民办 / 国际', one: '民办普高或国际课程，门槛低、学费高',
    threshold: '门槛低、多可入（学费约 6–33 万/年）',
    detail: ['高考方向（留京高考）或留学方向（海外大学 offer）二选一', '多为面试/自主招生，无统一录取线'],
    use: { label: '查学校筛「民办/国际」', tab: 'explore', filter: '民办' }, link: BJEEA_ZK, linkName: '考试院·中招' },
  { key: '中职', icon: '🛠️', name: '中职 / 职教', one: '中专/职高/技校/五年制/综合高中班',
    threshold: '门槛最低（各身份均可报）',
    detail: ['综合高中班＝职普融通，办普高学籍、可参加高考', '五年制/3+2→大专；贯通转段→本科；单考单招升学'],
    use: { label: '查学校筛「中职」', tab: 'explore', filter: '中职' }, link: BJEEA_ZK, linkName: '考试院·中招' },
]
const OFFICIAL = [
  { name: '北京教育考试院·中招', desc: '政策 / 招生简章 / 计划查询（最权威）', url: BJEEA_ZK },
  { name: '北京市教育委员会', desc: '中考中招政策文件', url: 'http://jw.beijing.gov.cn/' },
  { name: '校额到校名额公示', desc: '各初中分到的优质高中名额（每年 7 月更新）', url: XED_OFFICIAL },
  { name: '首都之窗', desc: '北京市政府门户·权威发布', url: 'https://www.beijing.gov.cn/' },
]
const TIMELINE = [
  { t: '7 月初', d: '官方招生简章 / 招生计划发布' },
  { t: '中考后', d: '网上填报志愿（一个平台填全部批次）' },
  { t: '出分后', d: '公布成绩 + 一分一段表（位次↔分数）' },
  { t: '随后', d: '① 提招 → ② 指标分配 → ③ 统招 顺序录取、录即锁定' },
]
// 填报避坑：家长高频误区(来源:官方规则 + 家长社区高频踩坑)。bad=误区, good=正解。
const PITFALLS = [
  { bad: '把最想去的校"求稳"放后面', good: '平行志愿冲在最前零成本，志愿顺序=优先级，从高到低排，冲不上自动落到稳/保' },
  { bad: '校额到校填"统招本来就能上"的校', good: '校额在统招前录取且锁定，会把你锁在低校；要填统招够不着、但够得着名额的更好公办' },
  { bad: '怕"普高+贯通一起填会被贯通提前录走"', good: '2026 贯通已并入统一招生批，与普高同批按志愿顺序走，放在后面不会被提前录取' },
  { bad: '志愿不填满 / 不放保底', good: '末位必放一所一定能上的校，否则滑档无学可上' },
  { bad: '只看分数、对着去年线填', good: '跨年难度/口径会变（今年数学偏难），按位次比按分数稳' },
]
// 校额到校：按初中查名额
const showXedImg = ref(false)
const xedQuery = ref(USER_DEFAULTS.chuzhong)
const batchOpen = reactive({ early: false, ind: false, uni: false })   // 三批次默认折叠
const noteOpen = reactive({ xed: false, tc: false, uni: false })       // 各块「录取规则/口径」说明默认折叠
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
  name: string; uid?: string; lat: number; lon: number; kind: string; color: string
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
  schoolRank: '' as number | string,  // 校内排名(选填,B1):有则校额中签研判从"未知彩票"精化为"名额n vs 校内排名"
  farBoarding: false,                 // 接受远郊寄宿统筹(B5):开启则 j.far 的统筹校纳入自动填
  risk: 'balanced',                   // 风险偏好:safe保底优先/balanced均衡/aggressive冲高
  orient: 'gaokao',                   // 升学取向:gaokao体制内高考/abroad兼顾出国
  nonpub: 'pub_only',                 // 贯通/中职缺省:仅公办 / no仅公办+民办 / yes智能纳入
  // —— 孩子画像(§5·AI 深度分析专用·全部可选·缺省不阻塞)——
  wenli: '',                          // 文理倾向:偏文/偏理/均衡
  strong: [] as string[],             // 强科(多选)
  weak: [] as string[],               // 弱科(多选)
  stability: '',                      // 发挥稳定性:稳定/偶有起伏/起伏较大
  target: '',                         // 中考目标分或心仪目标校(自由填)
  drive: '',                          // 学习自驱:自驱强/一般/需要盯
  adapt: '',                          // 适应环境:能扛高竞争强校/偏好节奏平稳/不确定
  talent: [] as string[],             // 特长方向(多选)
  valued: [] as string[],             // 家庭最看重(选≤2)
  budget: '',                         // 学费预算上限(民办/国际场景)
})
// 画像问卷选项(§5)
const SUBJECTS = ['语', '数', '英', '物', '化', '道法', '历史']
const TALENTS = ['体育', '艺术', '科技/学科竞赛']
const VALUES = ['升学率', '校风管理', '通勤距离', '师资', '学费', '国际路线', '住宿条件']
const aiStarted = ref(false)   // 点「启用 AI 深度分析」后才展开画像问卷 + 生成按钮
// 多选 chip 切换(可带上限,如家庭最看重≤2)
function toggleArr(arr: string[], v: string, max = 0) {
  const i = arr.indexOf(v)
  if (i >= 0) arr.splice(i, 1)
  else { if (max && arr.length >= max) return; arr.push(v) }
}
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
// 渠道科普(重设计):卡片展开 + 身份自查
const openCh = ref<string | null>(null)
const chId = ref<string>(USER_DEFAULTS.identity)   // 身份自查(默认随用户)
function chEligible(c: any): boolean {
  if (chId.value === 'jjyj') return true                          // 京籍应届:全可
  if (chId.value === 'feijing') return c.key === '中职'           // 非京籍随迁:只中职
  return c.key !== '校额' && c.key !== '统筹' && c.key !== '贯通' // 往届/回京:无指标分配/贯通
}
const loading = ref(false)
const errMsg = ref('')
const result = ref<Result | null>(null)
const formOpen = ref(true)        // 表单展开/折叠：生成后自动折叠成一行摘要
const formDirty = ref(false)      // 折叠态下条件被改、尚未重新生成
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
  if (!form.rank || Number(form.rank) < 1) { errMsg.value = '请填写有效的区排名'; return }
  loading.value = true
  try {
    const body: any = {
      rank: Number(form.rank),
      mode: form.mode,
      boarding: form.boarding,
      identity: form.identity,
      district: curDistrict.value,
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
    prefillTongchou()
    formOpen.value = false   // 生成后折叠表单，把空间让给结果
    formDirty.value = false
    tab.value = 'map'        // 生成后回到地图页，保证地图在可见状态下初始化
    await nextTick()
    renderMap()
    saveProfile()             // 生成成功后把当前填报资料落库(换设备/下次自动回填)
  } catch (e: any) {
    errMsg.value = '推荐失败：' + e.message
  } finally {
    loading.value = false
  }
}

/* ---------------- 资料持久化(账号头像菜单见 AccountMenu) ---------------- */
// 登录后回填该用户已存资料(没有则保持空白缺省)
async function loadProfile() {
  try {
    const me = await fetchMe()
    const p = (me?.profile) ?? (await getProfile().then(r => r.profile).catch(() => null))
    if (!p) return
    for (const k of ['rank', 'home', 'mode', 'max_km', 'boarding', 'identity', 'schoolRank', 'farBoarding', 'risk', 'orient', 'nonpub',
      'wenli', 'strong', 'weak', 'stability', 'target', 'drive', 'adapt', 'talent', 'valued', 'budget'] as const) {
      if (p[k] !== undefined && p[k] !== null) (form as any)[k] = p[k]
    }
    if (p.chuzhong != null) xedQuery.value = p.chuzhong
    if (p.identity) chId.value = p.identity
  } catch { /* 未登录或网络问题:用空白缺省,不打断 */ }
}
onMounted(loadProfile)
onMounted(loadDistrictModes)

function saveProfile() {
  const data = { ...form, chuzhong: xedQuery.value }
  putProfile(data).catch(() => { /* 存档失败不影响使用 */ })
}

/* ---------------- AI 深度分析(P1 灰度) ---------------- */
const aiReport = ref('')
const aiLoading = ref(false)
const aiErr = ref('')
async function genAiReport() {
  if (aiLoading.value) return
  if (!form.rank || Number(form.rank) < 1) { aiErr.value = '请先填区排名'; return }
  aiLoading.value = true; aiErr.value = ''; aiReport.value = ''
  try {
    // 画像:基础 form 字段 + §5 问卷(用中文 key 喂 LLM,空值不传,缺省不阻塞)
    const pf: any = { chuzhong: xedQuery.value, risk: form.risk, orient: form.orient, nonpub: form.nonpub }
    if (form.wenli) pf['文理倾向'] = form.wenli
    if (form.strong.length) pf['强科'] = form.strong
    if (form.weak.length) pf['弱科'] = form.weak
    if (form.stability) pf['发挥稳定性'] = form.stability
    if (form.target.trim()) pf['中考目标(分或心仪校)'] = form.target.trim()
    if (form.drive) pf['学习自驱'] = form.drive
    if (form.adapt) pf['适应环境'] = form.adapt
    if (form.talent.length) pf['特长'] = form.talent
    if (form.valued.length) pf['家庭最看重'] = form.valued
    if (form.budget.trim()) pf['学费预算上限'] = form.budget.trim()
    const body: any = {
      rank: Number(form.rank), mode: form.mode, boarding: form.boarding, identity: form.identity,
      profile: pf,
    }
    if (form.home.trim()) body.home = form.home.trim()
    if (form.max_km !== '' && Number(form.max_km) > 0) body.max_km = Number(form.max_km)
    const r = await fetch('/api/zhiyuan/report', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    const d = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)
    aiReport.value = d.report || ''
    saveProfile()   // 画像问卷落库,换设备/下次自动回填
  } catch (e: any) {
    aiErr.value = 'AI 分析失败:' + (e.message || e) + '(可继续用上方规则版草表)'
  } finally {
    aiLoading.value = false
  }
}
// 极简 markdown 渲染(内容来自我方 LLM):先转义,再 ## 标题/**粗**/列表
function mdToHtml(md: string): string {
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc(md).split('\n').map(line => {
    if (/^##\s+/.test(line)) return '<h4>' + line.replace(/^##\s+/, '') + '</h4>'
    if (/^###\s+/.test(line)) return '<h5>' + line.replace(/^###\s+/, '') + '</h5>'
    let l = line.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    if (/^\s*[-*]\s+/.test(l)) return '<div class="ai-li">• ' + l.replace(/^\s*[-*]\s+/, '') + '</div>'
    if (/^\s*\d+\.\s+/.test(l)) return '<div class="ai-li">' + l.trim() + '</div>'
    return l.trim() ? '<p>' + l + '</p>' : ''
  }).join('')
}
const aiReportHtml = computed(() => aiReport.value ? mdToHtml(aiReport.value) : '')

/* ---------------- 地图 ---------------- */
// 选中学校 → 右侧详情面板（替代地图气泡）
const selectedPoint = ref<Point | null>(null)
function selectPoint(p: Point) { selectedPoint.value = p }
// 地图选中:高亮该 marker(去掉上一个高亮),并打开详情(手机为底部弹层)
let _selEl: any = null
function pick(p: Point, mk: any) {
  selectPoint(p)
  const el = mk && mk._icon
  if (_selEl && _selEl !== el) _selEl.classList.remove('mk-sel')
  if (el) { el.classList.add('mk-sel'); _selEl = el }
  // 切换学校:详情面板/底部弹层滚回顶部(同一 DOM 复用,否则停在上一个的滚动位置)
  nextTick(() => document.querySelectorAll('.detail-panel').forEach((d) => { (d as HTMLElement).scrollTop = 0 }))
}
function closeDetail() {
  selectedPoint.value = null
  if (_selEl) { _selEl.classList.remove('mk-sel'); _selEl = null }
}
// 手机底部弹层打开时锁住背景滚动(iOS 仅靠 overscroll-behavior 仍可能穿透到地图页)
watch(selectedPoint, (v) => {
  if (window.matchMedia('(max-width: 560px)').matches) {
    document.body.style.overflow = v ? 'hidden' : ''
  }
})
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
function renderMarkers(fit = false) {
  const res = result.value
  if (!res || !mapInst) return
  for (const lyr of [publicLayer, minbanLayer, intlLayer, vocLayer, gtLayer, tcLayer, xedLayer])
    if (lyr) mapInst.removeLayer(lyr)
  publicLayer = L.layerGroup(); minbanLayer = L.layerGroup(); intlLayer = L.layerGroup()
  vocLayer = L.layerGroup(); gtLayer = L.layerGroup(); tcLayer = L.layerGroup(); xedLayer = L.layerGroup()
  const bounds: any[] = []
  if (res.home_coord) bounds.push(res.home_coord)
  const tcColor: Record<string, string> = { 'tj-wen': '#2ecc71', 'tj-chong': '#e74c3c', 'tj-bo': '#e67e22', 'tj-no': '#95a5a6', 'tj-unk': '#2980b9' }
  // 地图标签统一显示在标记下方；permanent 决定是常驻还是 hover 显示
  const tipOpts = (permanent = false) => ({ permanent, direction: 'bottom' as const, offset: [0, 2] as [number, number], className: 'map-lbl' })

  // 地图唯一数据源 = schools_unified（每条带 uid；点击按 uid 解析详情，不再做名字匹配）
  for (const r of uList.value) {
    const lat = r.geo?.lat, lon = r.geo?.lon
    if (lat == null || lon == null) continue
    const pt: any = { name: r.name, uid: r.uid, lat, lon }
    const ty = r.type as string
    const lbl = r.short_name || shortName(r.name)   // 地图标签优先用注册表精选短名
    const tipB = (mk: any) => mk.bindTooltip(lbl, tipOpts(true))
    const tipS = (mk: any) => mk.bindTooltip(lbl, tipOpts())

    if (ty === '公办普高') {
      const m = r.map || {}
      const full = m.kind === 'full'
      const icon = full ? pin(m.color || '#7f8c8d', m.band || '', !!r.boarding) : smallIcon(m.color || '#7f8c8d', !!r.boarding)
      const mk = L.marker([lat, lon], { icon }).addTo(publicLayer).on('click', (e: any) => pick(pt, e.target))
      full ? tipB(mk) : tipS(mk)
      if (layers.gongban) bounds.push([lat, lon])
      const q = xedQuotaByName.value[r.name]      // 校额到校图层：该公办校在选定初中的名额
      if (q) {
        const j = xedJudgeByName.value[r.name]
        L.marker([lat, lon], { icon: pin(j ? j.color : '#95a5a6', j ? XED_BAND[j.tag] : '校', !!r.boarding, String(q)) })
          .addTo(xedLayer).on('click', (e: any) => pick(pt, e.target))
          .bindTooltip(lbl, tipOpts(true))
        if (layers.xed) bounds.push([lat, lon])
      }
    } else if (ty === '2026新校') {
      tipB(L.marker([lat, lon], { icon: pin('#8e44ad', '新', !!r.boarding) }).addTo(publicLayer).on('click', (e: any) => pick(pt, e.target)))
      if (layers.gongban) bounds.push([lat, lon])
    } else if (ty === '市级统筹') {
      const m = (r.channels || []).find((c: any) => c.metric?.kind === 'city_score')?.metric || {}
      const b = cityScoreBand(m.entryRank, !!m.belowControl, Number(form.rank) || 0, { label: '', cls: 'tj-unk' })
      const color = tcColor[b.cls] || '#2980b9'
      const big = b.cls === 'tj-wen' || b.cls === 'tj-chong' || b.cls === 'tj-bo'
      const mk = L.marker([lat, lon], { icon: big ? pin(color, b.label, !!r.boarding) : smallIcon(color, !!r.boarding) })
        .addTo(tcLayer).on('click', (e: any) => pick(pt, e.target))
      big ? tipB(mk) : tipS(mk)
      if (layers.tc) bounds.push([lat, lon])
    } else if (ty.includes('民办') || ty.includes('国际') || ty.includes('双语')) {
      const isIntl = !!r.extra?.in_intl || ty.includes('国际') || ty.includes('双语')
      const isMin = !!r.extra?.in_minban || ty.includes('民办')
      if (isIntl) tipS(L.marker([lat, lon], { icon: smallIcon('#9b59b6') }).addTo(intlLayer).on('click', (e: any) => pick(pt, e.target)))
      if (isMin || (!isMin && !isIntl)) tipS(L.marker([lat, lon], { icon: smallIcon('#e67e22') }).addTo(minbanLayer).on('click', (e: any) => pick(pt, e.target)))
      if (layers.minban || layers.intl) bounds.push([lat, lon])
    } else if (ty.includes('中职') || ty.includes('职教')) {
      tipS(L.marker([lat, lon], { icon: smallIcon('#16a085') }).addTo(vocLayer).on('click', (e: any) => pick(pt, e.target)))
      if (layers.voc) bounds.push([lat, lon])
    } else if (ty === '贯通') {
      tipS(L.marker([lat, lon], { icon: smallIcon('#2980b9') }).addTo(gtLayer).on('click', (e: any) => pick(pt, e.target)))
      if (layers.gt) bounds.push([lat, lon])
    }
  }

  // 仅有坐标、无结构化记录的民办/国际：补画兜底点(点击走"暂无详情"友好文案)
  const uNames = uByName.value
  ;(res.private || []).forEach((p) => {
    if (uNames[p.name]) return
    const f = privFlags.value[p.name] || { minban: true, intl: false }
    const mk = (color: string) => L.marker([p.lat, p.lon], { icon: smallIcon(color) })
      .on('click', (e: any) => pick(p, e.target))
      .bindTooltip((p as any).short_name || shortName(p.name), tipOpts())
    if (f.intl) mk('#9b59b6').addTo(intlLayer)
    if (f.minban || (!f.minban && !f.intl)) mk('#e67e22').addTo(minbanLayer)
    if (layers.minban || layers.intl) bounds.push([p.lat, p.lon])
  })

  if (layers.gongban) publicLayer.addTo(mapInst)
  if (layers.minban) minbanLayer.addTo(mapInst)
  if (layers.intl) intlLayer.addTo(mapInst)
  if (layers.voc) vocLayer.addTo(mapInst)
  if (layers.gt) gtLayer.addTo(mapInst)
  if (layers.tc) tcLayer.addTo(mapInst)
  if (layers.xed) xedLayer.addTo(mapInst)

  // 仅首次渲染自动定位；切换图层只增减标记，保持用户当前视野不动
  if (fit && bounds.length) mapInst.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
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
  renderMarkers(true)   // 首次：自动定位到所有点
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
const selectable = computed<any[]>(() => {
  const res = result.value
  if (!res) return []
  const out: Card[] = []
  for (const band of ['冲', '稳', '保', '够不上']) {
    for (const c of (res.bands[band] || [])) {
      if (c.school_code || (c as any).is_estimate) out.push(c)   // 新校无官方码,靠 is_estimate 纳入
    }
  }
  // 全渠道:公办之后追加 贯通/民办/中职综高(可手动选)
  return [...dedupeByKey(out), ...nonPubCands.value]
})
function bandOf(name: string | null): string {
  const res = result.value
  if (!res || !name) return ''
  for (const band of ['冲', '稳', '保', '够不上']) {
    if ((res.bands[band] || []).some(c => c.name === name)) return band
  }
  const np = nonPubByName.value[name]   // 非公办:本科(贯通)/路线(民办)/保底(中职)
  return np ? np.band : ''
}
function majorsOf(name: string | null): Major[] {
  if (!name) return []
  const c = findCard(name)
  if (!c) return []
  return (c.school_code && mergedMajorsByCode.value[c.school_code]) || c.majors || []
}
// 同一录取代码 = 同一志愿单位：把各校区/专业合并；02 等校区专业名后标注校区便于区分
const mergedMajorsByCode = computed<Record<string, Major[]>>(() => {
  const res = result.value
  const m: Record<string, Major[]> = {}
  if (!res) return m
  for (const band of ['冲', '稳', '保', '够不上']) {
    for (const c of (res.bands[band] || [])) {
      const code = c.school_code
      if (!code) continue
      const mm = c.name.match(/（(.+?)）/)
      const campus = mm ? mm[1].replace('校区', '').replace('高中', '') : ''
      if (!m[code]) m[code] = []
      const have = new Set(m[code].map(x => x.major_code))
      for (const mj of (c.majors || [])) {
        if (have.has(mj.major_code)) continue
        m[code].push(campus ? { ...mj, major_name: mj.major_name + '（' + campus + '）' } : mj)
        have.add(mj.major_code)
      }
    }
  }
  return m
})
// 学校稳定标识(P2):优先后端注册表 id;无 id(贯通/民办暂未入注册表)用 chan+code|name 合成,
// 仍唯一稳定。身份不再靠"剥括号取基名"的字符串拼接 → 杜绝校区/本部代表名不一致(和平街 105004 那类)。
function keyOf(c: any): string {
  if (!c) return ''
  if (c.id) return String(c.id)
  return 'np:' + (c.chan || 'pub') + ':' + (c.school_code || c.name || '')
}
// 按稳定标识去重(同 id/多校区合一),代表卡优先"本部"(名称不含 校区/（)。取代 dedupeByCode/dedupeByName。
function dedupeByKey(cards: Card[]): Card[] {
  const idx: Record<string, number> = {}; const out: Card[] = []
  for (const c of cards) {
    const k = keyOf(c)
    if (!(k in idx)) { idx[k] = out.length; out.push(c) }
    else if (/校区|（/.test(out[idx[k]].name) && !/校区|（/.test(c.name)) out[idx[k]] = c
  }
  return out
}
// selectable 是唯一可选名来源:把任意计划卡解析到下拉里"同标识"的代表名
// (<select v-model="s.name"> 需精确匹配)。现按 keyOf(id) 解析,不再剥字符串。
const selNameIndex = computed(() => {
  const byName = new Set<string>(); const byKey: Record<string, string> = {}
  for (const c of selectable.value) {
    byName.add(c.name)
    const k = keyOf(c); if (!(k in byKey)) byKey[k] = c.name
  }
  return { byName, byKey }
})
function toSelName(c: any): string {
  const ix = selNameIndex.value
  if (ix.byName.has(c.name)) return c.name
  return ix.byKey[keyOf(c)] || c.name
}
// 风险偏好 → 草表"往上够几所"。reach=冲高目标数(够不上里最接近你的 N 所,绝不塞远超能力的顶尖校)。
// reach 越多→保底占格越少→整体往上够;reach=0→保底优先(给紧张家长)。冲/稳一律全要,保底只留最强几所+1所深兜底。
const RISK_CFG: Record<string, { reach: number; label: string }> = {
  safe:       { reach: 0, label: '保底优先' },
  balanced:   { reach: 2, label: '均衡' },
  aggressive: { reach: 4, label: '冲高' },
}
const riskCfg = computed(() => RISK_CFG[form.risk] || RISK_CFG.balanced)
// 通勤可达：≤通勤上限即可；超上限的学校，只有"你接受住宿 且 该校确实提供住宿"才算可达
// （远校不提供住宿=没法住校=照样每天通勤，应排除）。用原始 km，不依赖住宿模式下被清零的 over_max。
function reachByCommute(km: number | null | undefined, schoolBoarding: boolean): boolean {
  if (km == null) return true
  const maxKm = Number(form.max_km) || Infinity
  if (km <= maxKm) return true
  return !!(form.boarding && schoolBoarding)
}
// 增值档(捡漏优先):高增值=0 / 其他=1 / 偏低=2。同档内据此优先入选。
function vaRank(c: Card): number {
  const lab = uByName.value[c.name]?.value_added?.label
  return lab === '高增值' ? 0 : lab === '偏低' ? 2 : 1
}
function bandPool(band: string): Card[] {
  const res = result.value
  if (!res) return []
  // 同档内:捡漏(高增值)优先,其次录取位次升序(更硬在前)
  return dedupeByKey((res.bands[band] || []).filter(c => (c.school_code || (c as any).is_estimate) && reachByCommute(c.nearest?.km, !!c.boarding)))
    .slice().sort((a, b) => {
      const va = vaRank(a) - vaRank(b)
      if (va !== 0) return va
      return (Number(a.ref_rank) || 9e9) - (Number(b.ref_rank) || 9e9)
    })
}
function isReachableCard(c: Card): boolean {
  if (!c.nearest) return true
  return !c.nearest.over_max || !!c.boarding
}
// 全渠道草表(梯队式,非"灌满保底"):
//   冲高目标(够不上里最接近的N所) → 冲(全) → 稳(全) → 保只留最强几所 + 末位锁1所深兜底。
//   够位次的(如4500)12格全公办、梯队向上;低位次(如8500)公办填不满→空位让给非公办(贯通/民办/中职保底)。
function buildUniPlan(): any[] {
  const cfg = riskCfg.value
  const chong = dedupeByKey(bandPool('冲')), wen = dedupeByKey(bandPool('稳')), bao = dedupeByKey(bandPool('保'))
  // 冲高目标:够不上里最接近你的 N 所(按位次降序取最近的;绝不塞远超能力的顶尖校,如8500冲八十中)
  const reachTop = cfg.reach > 0
    ? dedupeByKey(bandPool('够不上').slice().sort((a, b) => (Number(b.ref_rank) || 0) - (Number(a.ref_rank) || 0))).slice(0, cfg.reach)
    : []
  // 上半区:冲高目标 + 冲 + 稳(全要),按录取位次升序(硬在前)
  let pub = dedupeByKey([...reachTop, ...chong, ...wen])
    .sort((a, b) => (Number(a.ref_rank) || 9e9) - (Number(b.ref_rank) || 9e9))
    .slice(0, ZHIYUAN_SLOTS)
  // 保底:不堆!按位次升序(强保在前),取最强的几所填到 11 格,末位永远锁"最深的那所保"作真兜底
  const baoSorted = bao.slice().sort((a, b) => (Number(a.ref_rank) || 9e9) - (Number(b.ref_rank) || 9e9))
  if (pub.length < ZHIYUAN_SLOTS && baoSorted.length) {
    const floor = baoSorted[baoSorted.length - 1]   // 最深的保=真兜底,永远留末位
    const room = ZHIYUAN_SLOTS - pub.length
    const strong = baoSorted.slice(0, Math.max(0, room - 1))   // 留 1 格给深兜底
    pub = pub.concat(strong)
    if (pub.length < ZHIYUAN_SLOTS && !pub.some(c => keyOf(c) === keyOf(floor))) pub.push(floor)
    pub = dedupeByKey(pub)
  }
  let plan: any[] = pub.slice(0, ZHIYUAN_SLOTS)
  if (plan.length < ZHIYUAN_SLOTS) {
    // 非公办回填:贯通+民办混(各限额,避免单一渠道刷屏) + 末位锁定中职综高铁保底
    const gt = nonPubCands.value.filter(c => c.chan === '贯通').slice(0, 4)
    const mb = nonPubCands.value.filter(c => c.chan === '民办').slice(0, 4)
    const vc = nonPubCands.value.filter(c => c.chan === '中职')
    const floor = vc[0] || mb[0]   // 铁保底:中职综高优先,无则民办
    const mid = [...gt, ...mb]
    const midTake = floor ? Math.max(0, ZHIYUAN_SLOTS - plan.length - 1) : ZHIYUAN_SLOTS - plan.length
    plan = plan.concat(mid.slice(0, midTake))
    if (floor && plan.length < ZHIYUAN_SLOTS && !plan.some(c => c.name === floor.name)) plan.push(floor)
    if (plan.length < ZHIYUAN_SLOTS) plan = plan.concat(vc.slice(0, ZHIYUAN_SLOTS - plan.length))
  }
  return plan.slice(0, ZHIYUAN_SLOTS)
}
function resetDraft() {
  const plan = buildUniPlan()
  draft.value = Array.from({ length: ZHIYUAN_SLOTS }, (_, i) => {
    const c = plan[i]
    if (!c) return { name: null, picks: [] }
    const name = toSelName(c)   // 必落到下拉里的代表名,杜绝 <select> 空白(校区/本部同代码 105004 不一致问题)
    const mj = c.school_code ? (mergedMajorsByCode.value[c.school_code] || c.majors || []) : []
    return { name, picks: mj.slice(0, 2).map((m: any) => m.major_code) }
  })
}
const filledSlots = computed(() => draft.value.filter(s => s.name).length)
// 只读草表用：仅展示已填条目（规则引擎已生成，不再可编辑）
const uniFilled = computed(() => draft.value.filter(s => s.name))
const xedFilled = computed(() => draftXed.value.filter(s => s.school))
const tcFilled = computed(() => draftTongchou.value.filter(s => s.school))
// 统招某志愿已选的推荐专业(班)（resetDraft 默认取前 2 个）
function pickedMajors(s: { name: string | null; picks: string[] }): Major[] {
  return majorsOf(s.name).filter(m => s.picks.includes(m.major_code))
}

// 只读草表行 view-model（DraftRow 组件统一渲染）：三批次各自 adapter 把源数据归一成同一形状，
// 每行的理由/徽标只算一次（避免模板里 xedReason/slotReason 等被反复调用）。
interface DraftRowVM {
  seq: number; name: string; meta?: string; band?: { label: string; cls: string }
  majors?: { code: string; name?: string }[]; majorsNote?: string
  headline?: string; factors?: string[]; risk?: string
}
const uniRows = computed<DraftRowVM[]>(() => uniFilled.value.map((s, i) => {
  const c: any = findCard(s.name!); const r = slotReason(s.name)
  return {
    seq: i + 1, name: cleanName(s.name!),
    meta: c?.is_estimate ? '新校预测' : (c?.school_code || undefined),
    band: r ? { label: r.band, cls: r.cls } : undefined,
    majors: pickedMajors(s).map(m => ({ code: m.major_code, name: cleanName(m.major_name) })),
    headline: r?.headline, factors: r?.factors, risk: r?.risk || undefined,
  }
}))
const xedRows = computed<DraftRowVM[]>(() => xedFilled.value.map((s, i) => {
  const b = xedBadge(s.school); const r = xedReason(s.school)
  return {
    seq: i + 1, name: xedName(s.school!), band: b || undefined,
    majors: [], majorsNote: '以官方网报为准',
    headline: r?.headline, risk: r?.caveat,
  }
}))
// 统筹 tcReason.cls 是 tj-*（父级 scoped 样式），DraftRow 子组件只认 band-*；按 label 映射到统一 band-*
// （也与本批次摘要 us-b 的 band-保/稳/冲 一致）
const TC_BAND_CLS: Record<string, string> = { 保: 'band-保', 稳: 'band-稳', 冲: 'band-冲', 冲刺: 'band-刺' }
const tcRows = computed<DraftRowVM[]>(() => tcFilled.value.map((s, i) => {
  const r = tcReason(s.school)
  return {
    seq: i + 1, name: tcName(s.school!), meta: tcTier(s.school!) || undefined,
    band: r ? { label: r.label, cls: TC_BAND_CLS[r.label] || 'band-够不上' } : undefined,
    majors: s.majors ? [{ code: s.majors }] : [], majorsNote: '以官方网报为准',
    headline: r?.headline, factors: r?.factors, risk: r?.caveat,
  }
}))

// 单个志愿的"理由"——全部来自真实字段，缺数据则省略，绝不编造
function slotReason(name: string | null): { band: string; cls: string; headline: string; factors: string[]; risk: string } | null {
  if (!name) return null
  // 非公办(贯通/民办/中职综高):走专属研判文案
  const np = nonPubByName.value[name]
  if (np) {
    const u = uByName.value[name]
    const factors: string[] = []
    if (u?.gaokao?.score != null) factors.push('🎓高考U' + u.gaokao.score)
    if (u?.extra?.study_abroad) factors.push('🌍留学走向')
    else if (u?.extra?.exit_paths) factors.push('🚀' + String(u.extra.exit_paths).slice(0, 12))
    if (u?.commute?.km != null) factors.push('🚌' + u.commute.km + 'km')
    const M: Record<string, { band: string; cls: string; head: string }> = {
      贯通: { band: '贯通·本科', cls: 'band-稳', head: '贯通培养——中考≥380 即可报、7 年直通本科（京籍专属）；2026 在统招批内填' },
      民办: { band: '民办', cls: 'band-保', head: '民办普高——门槛低、基本可入；' + (np.note.includes('留学') ? '留学方向' : '可留京高考') + '，注意学费' },
      中职: { band: '保底·可高考', cls: 'band-保', head: '中职综合高中班——门槛最低、办普高学籍可参加高考；作为一定有学上的铁保底' },
    }
    const m = M[np.chan] || M['中职']
    return { band: m.band, cls: m.cls, headline: m.head, factors, risk: '' }
  }
  const c = findCard(name)
  if (!c) return null
  // 2026 新校:无往年线,走"预测位次"专属研判(醒目标注,绝不当硬线)
  if ((c as any).is_estimate) {
    const ce: any = c
    const [lo, hi] = ce.est_range || []
    const band = bandOf(name); const dispBand = band === '够不上' ? '冲刺' : band
    const cls = ({ 冲: 'band-冲', 稳: 'band-稳', 保: 'band-保', 够不上: 'band-刺' } as Record<string, string>)[band] || 'band-稳'
    const factors: string[] = ['🆕新校·预测位次≈' + ce.est_rank + (lo && hi ? '（' + lo + '–' + hi + '）' : '') + '·' + (ce.est_conf || '估')]
    if (c.nearest) factors.push('🚌' + c.nearest.km + 'km' + (c.nearest.over_max ? '·超上限' : ''))
    if (c.boarding) factors.push('🛏可住宿')
    const headline = '🆕 2026 新增普高·无往年录取线 → 按预测位次纳入。' + (ce.est_basis || '')
    const lowConf = ce.est_conf === 'T4' || ce.est_conf === 'T5'
    const risk = '预测仅用于圈定区间、不漏机会,非录取承诺;新校首年波动大,务必参加招生说明会 + 以 6 月官方简章为准'
      + (lowConf ? '。⚠️本校公开信息可靠度低,数据务必自行核实' : '')
    return { band: dispBand, cls, headline, factors, risk }
  }
  const band = bandOf(name)
  const rank = Number(form.rank) || 0
  const ref = typeof c.ref_rank === 'number' ? c.ref_rank : null
  const est = estScore.value
  const sl = (c.score_lines || []).find(x => x.year === 2025) || (c.score_lines || []).slice(-1)[0]
  const lineScore = sl && sl.score != null ? sl.score : null
  const aheadPos = (ref != null && rank) ? ref - rank : null              // >0 你领先；<0 你落后
  const scoreDiff = (lineScore != null && est != null) ? Math.round(est - lineScore) : null  // >0 高出；<0 差
  const refTxt = ref != null ? '≈' + ref : '待核'
  const u = uByName.value[name]            // 统一记录:增值/特色/三年位次波动
  const factors: string[] = []
  if (u?.value_added?.label === '高增值') factors.push('✨捡漏·同档产出更高')
  if (u?.gaokao?.score != null) factors.push('🎓高考U' + u.gaokao.score)
  if (u?.features_std?.tags?.length) factors.push('⭐' + u.features_std.tags[0])
  if (c.nearest) factors.push('🚌' + c.nearest.km + 'km' + (c.nearest.over_max ? '·超上限' : ''))
  if (c.boarding) factors.push('🛏可住宿')
  if (c.style && !u?.features_std?.tags?.length) factors.push('🏫' + c.style.slice(0, 14))
  let risk = ''
  if (typeof c.volatility === 'number' && c.volatility >= 0.25) risk = '近年录取线波动较大、线不稳，谨慎'
  if (u?.line_trend?.volatile) risk = '近年录取位次波动大(' + (u.line_trend.ranks?.['2023'] ?? '—') + '→' + (u.line_trend.ranks?.['2024'] ?? '—') + '→' + (u.line_trend.ranks?.['2025'] ?? '—') + ')、线不稳，建议留余量'
  const isReach = band === '够不上'
  const dispBand = isReach ? '冲刺' : band
  const cls = ({ 冲: 'band-冲', 稳: 'band-稳', 保: 'band-保', 够不上: 'band-刺' } as Record<string, string>)[band] || 'band-稳'
  let headline = ''
  if (band === '冲')
    headline = `冲一冲——该校 2026预估位次${refTxt}，你估区排≈${rank}`
      + (aheadPos != null ? `，落后约 ${Math.abs(aheadPos)} 位` : '')
      + (scoreDiff != null && scoreDiff < 0 ? `、约差 ${-scoreDiff} 分` : '') + '，够一够有机会'
  else if (band === '稳')
    headline = `稳——录取位次${refTxt}与你接近`
      + (aheadPos != null ? `（你${aheadPos >= 0 ? '领先' : '落后'}约 ${Math.abs(aheadPos)} 位）` : '')
      + '，大概率录取，主力志愿'
  else if (band === '保')
    headline = `保底——录取线明显低于你`
      + (aheadPos != null ? `（领先约 ${aheadPos} 位` : '（')
      + (scoreDiff != null && scoreDiff > 0 ? `、约高 ${scoreDiff} 分` : '') + '），基本稳妥'
  else
    headline = `冲刺——该校 2026预估位次${refTxt}，你估区排≈${rank}`
      + (aheadPos != null ? `，落后约 ${Math.abs(aheadPos)} 位` : '')
      + (scoreDiff != null && scoreDiff < 0 ? `、约差 ${-scoreDiff} 分` : '')
      + '，线明显高于你，搏一搏（风险高）'
  return { band: dispBand, cls, headline, factors, risk }
}
// 草表 ③ 顶部策略总览
const uniSummary = computed(() => {
  const cnt: Record<string, number> = { 刺: 0, 冲: 0, 稳: 0, 保: 0, 贯通: 0, 民办: 0, 中职: 0 }
  let lastName = ''
  for (const s of draft.value) {
    if (!s.name) continue
    const np = nonPubByName.value[s.name]
    if (np) { cnt[np.chan] = (cnt[np.chan] || 0) + 1 }   // 非公办按渠道计
    else {
      const b = bandOf(s.name)
      if (b === '够不上') cnt['刺']++
      else if (cnt[b] != null) cnt[b]++
    }
    lastName = s.name
  }
  const filled = draft.value.filter(s => s.name).length
  // 铁保底:公办"保" 或 中职/民办(必进)。三者全无才算无保底。
  const hasFloor = cnt['保'] > 0 || cnt['中职'] > 0 || cnt['民办'] > 0
  const noSafety = filled > 0 && !hasFloor
  const allReach = filled > 0 && (cnt['刺'] + cnt['冲']) === filled
  // 候选受通勤约束:8km 内可报的公办数(冲/稳/保/够不上池去重并集)
  const res: any = result.value
  let reachPool = 0
  if (res?.bands) {
    const seen = new Set<string>()
    for (const band of ['冲', '稳', '保', '够不上']) {
      for (const c of (res.bands[band] || [])) {
        if ((c.school_code || (c as any).is_estimate) && reachByCommute(c.nearest?.km, !!c.boarding)) seen.add(c.school_code || c.name)
      }
    }
    reachPool = seen.size
  }
  return { cnt, lastName, filled, noSafety, allReach, reachPool }
})

// 朝阳中考报名人数(约·估;出分后接一分一段表精化)。用于位次→百分位。
const CHAOYANG_TOTAL = 12000
const rankPct = computed(() => {
  const r = Number(form.rank) || 0
  return r ? Math.min(99, Math.round(r / CHAOYANG_TOTAL * 100)) : null
})
// 公办统招覆盖最低位次(最大的 latest):低于它=统招基本无戏
const publicFloorRank = computed(() => {
  let mx = 0
  for (const s of uList.value) {
    if (s.type === '公办普高' && s.line_trend?.latest) mx = Math.max(mx, s.line_trend.latest)
  }
  return mx || null
})
// 低位次专属方案的具体候选(从已有数据取)
const lowPlan = computed(() => {
  const voc = vocList.value.filter((v: any) => v.comp_high_2025).map(v => shortCampusName(v.name))
  const priv = ((result.value as any)?.private_schools?.schools || [])
    .filter((p: any) => (p.exit_type === '高考' || p.exit_type === '混合') && p.tuition)
    .map((p: any) => shortCampusName(p.name) + '(' + String(p.tuition).slice(0, 12) + ')').slice(0, 3)
  const gt = gtBlock.value?.projects?.length || 0
  return { voc, priv, gt }
})

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
// 位次档判定:你的区排 my vs 门槛位次 ref(越小越好)。**与统招 classify 同一套阈值/标签**
// (SAFETY=0.15 / 0 / REACH=-0.25),统招·统筹·面板·地图·查学校全口径一致;不再有"搏"。
function rankBand(my: number, ref: number): { label: string; cls: string } {
  if (!my || !ref) return { label: '待核', cls: 'tj-unk' }
  const margin = (ref - my) / ref                                      // >0 你领先门槛=更稳
  if (margin >= 0.15) return { label: '保', cls: 'tj-wen' }
  if (margin >= 0) return { label: '稳', cls: 'tj-wen' }
  if (margin >= -0.25) return { label: '冲', cls: 'tj-chong' }
  return { label: '够不上', cls: 'tj-no' }
}
// 市级统筹城市口径档位(面板/地图/草表/查学校共用):校档次低于门槛(线<控制线)→不值;
// 无门槛/无区排→兜底(noLine);否则按门槛位次 vs 你区排判冲稳保。
function cityScoreBand(entry: number | null | undefined, below: boolean, my: number,
                       noLine: { label: string; cls: string } = { label: '待核', cls: 'tj-unk' }): { label: string; cls: string } {
  if (below) return { label: '不值', cls: 'tj-no' }
  if (!entry || !my) return noLine
  return rankBand(my, entry)
}
// 远郊区:即便接受住宿,对朝阳家庭也是"需长期寄宿+周末难回"的重负 → 默认不自动填(可手动加)
const FAR_DISTRICTS = new Set(['门头沟', '平谷', '昌平', '怀柔', '密云', '延庆', '顺义', '房山'])
function tcJudge(s: any): any {
  // 朝阳口径(与面板/地图/查学校同源):门槛位次 vs 你的区排 → 冲稳保;档次<门槛(线<控制线)→不值。
  const R = Number(form.rank) || 0
  const entry = typeof s.tongchou_entry_cy?.rank === 'number' ? s.tongchou_entry_cy.rank : null
  const equiv = typeof s.cy_equiv === 'number' ? s.cy_equiv : null
  const below = !!s.below_control
  const far = FAR_DISTRICTS.has(s.district)
  const b = cityScoreBand(entry, below, R)
  // worth=真 upgrade:够得着门槛(非"够不上",同统招口径) 且 档次"显著"优于你(≥8%,非平级微涨),非不值
  const worth = !below && b.label !== '够不上' && b.label !== '待核' && equiv != null && equiv <= R * 0.92
  return { ...b, entry, equiv, below, far, worth }
}

// ───── 统一详情面板（§12）：把 schools_unified 记录声明式渲染 ─────
const uByName = computed<Record<string, any>>(() => {
  const m: Record<string, any> = {}
  for (const s of ((result.value as any)?.schools_unified || [])) m[s.name] = s
  return m
})
// 以 uid 为主键索引(地图标记/详情面板统一按 uid 解析，不再做名字匹配)
const uByUid = computed<Record<string, any>>(() => {
  const m: Record<string, any> = {}
  for (const s of ((result.value as any)?.schools_unified || [])) if (s.uid) m[s.uid] = s
  return m
})
// 选中校的统一记录；公办校再按选定初中补"校额到校"渠道（依赖前端 xedQuery）
const selSchool = computed<any>(() => {
  const p = selectedPoint.value
  if (!p) return null
  const base = (p.uid && uByUid.value[p.uid]) || uByName.value[p.name]   // uid 优先，名字兜底
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
    detail: '', caveat: ch.caveat }  // 位次统一在"📍2026预估"块显示,此处只留档位,避免重复
  if (k === 'city_score') {
    // 朝阳口径:门槛位次(录取位次) vs 你的区排 → 冲稳保;档次=学校水平;门槛>档次=走统筹不值
    const entry = ch.metric.entryRank ?? null      // 统筹门槛(录取位次)
    const equiv = ch.metric.equivRank ?? null      // 学校档次(线分→朝阳)
    const my = Number(form.rank) || 0
    const quotaTxt = ch.quota ? ` · 投朝阳${ch.quota}名` : ''
    if (!entry) return { name: '市级统筹' + (ch.tier ? '·' + ch.tier : ''), band: '兜底', cls: 'tj-unk',
      detail: '控制线≈460兜底⚠️·务必电话核实' + quotaTxt, caveat: ch.metric.estBasis || ch.caveat }
    const b = cityScoreBand(entry, !!ch.metric.belowControl, my)
    const warn = ch.metric.belowControl ? '⚠校档次低于门槛·走统筹需≈460反不如统招' : ''
    return { name: '市级统筹' + (ch.tier ? '·' + ch.tier : ''), band: b.label, cls: b.cls,
      detail: `统筹门槛≈朝阳第${entry}位 · 学校档次≈朝阳第${equiv}位${quotaTxt}${warn ? ' · ' + warn : ''}`,
      caveat: ch.metric.estBasis || ch.caveat }
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
// 统招招生计划(专业/班 + 区内/全市名额)——直读 uid 解析出的 selSchool.majors(注册表实体下发,不按名 join)
const selMajors = computed<Major[]>(() =>
  selSchool.value?.type === '公办普高' ? (selSchool.value?.majors || []) : [])
// 纯数字名额补"人"单位;含住宿/文字说明(如"30 住15")则原样展示
function planNum(v: any): string {
  const s = String(v ?? '').trim()
  return !s ? '—' : /^\d+$/.test(s) ? s + '人' : s
}
const caveats = computed<string[]>(() => {
  const set = new Set<string>()
  channelViews.value.forEach((v: any) => { if (v.caveat) set.add(v.caveat) })
  return [...set]
})
// 面板只保留"该校特有"提醒;通用机制(校内排名/平行志愿/录取即锁定/跨年口径)归渠道科普,面板里用 ⓘ 链接
const GENERIC_CAVEAT_RE = /校内排名|平行志愿|录取即锁定|遵循志愿|分数优先|统招之前|跨年口径|批次/
const panelCaveats = computed<string[]>(() => caveats.value.filter(c => !GENERIC_CAVEAT_RE.test(c)))

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
const exBand = ref<'all' | '保' | '稳' | '冲'>('all')
const exBoarding = ref(false)
const exCommute = ref(false)
const exFee = ref<'all' | 'le10' | 'mid' | 'gt20'>('all')
const exFeat = ref('all')   // 特色筛选(标准标签)
const FEAT_TAGS = ['科技创新', '学科竞赛', '外语特色', '文科人文', '艺术特长', '体育特长', '国际方向', '课程改革', '综合均衡']
const exSort = ref<'default' | 'va'>('default')   // default=按档位/位次; va=捡漏(按增值residual)
const compareSel = ref<any[]>([])                 // 横向对比集(最多4)
const showCompare = ref(false)
function isCompared(r: any): boolean { return compareSel.value.some(x => x.uid === r.uid) }
function toggleCompare(r: any) {
  const i = compareSel.value.findIndex(x => x.uid === r.uid)
  if (i >= 0) compareSel.value.splice(i, 1)
  else if (compareSel.value.length < 4) compareSel.value.push(r)
}
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
    if (ch.metric?.kind === 'city_score')
      return cityScoreBand(ch.metric.entryRank, !!ch.metric.belowControl, Number(form.rank) || 0)
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
  if (exFeat.value !== 'all') list = list.filter(r => (r.features_std?.tags || []).includes(exFeat.value))
  if (exFee.value !== 'all') list = list.filter(r => {
    const m = exFeeMax(r); if (m == null) return false
    if (exFee.value === 'le10') return m <= 10
    if (exFee.value === 'mid') return m > 10 && m <= 20
    return m > 20
  })
  if (exSort.value === 'va') {
    // 捡漏:按增值 residual 降序(高增值在前);无增值的沉底
    return [...list].sort((a, b) => {
      const ra = a.value_added?.residual, rb = b.value_added?.residual
      if (ra == null && rb == null) return 0
      if (ra == null) return 1
      if (rb == null) return -1
      return rb - ra
    })
  }
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
function exSelect(rec: any) { selectPoint({ name: rec.name, uid: rec.uid } as any) }
const vocList = computed<VocSchool[]>(() => result.value?.vocational?.schools || [])
const gtBlock = computed<GuantongBlock | null>(() => result.value?.guantong || null)
function shortCampusName(name: string): string {
  // 去掉"北京市朝阳区"前缀让表格更紧凑
  return (name || '').replace(/^北京市朝阳区/, '').replace(/^北京市/, '')
}

/* ---------------- 志愿草表 v2：三批次（2026 口径）---------------- */
// 批次资格（按考生身份灰掉）
const identityLabel = computed(() => (IDENTITIES.find(i => i.v === form.identity) || {}).label || '')
const modeLabel = computed(() => (MODES.find(m => m.v === form.mode) || {}).label || '')
const formSummary = computed(() => {
  // 折叠态：无条件显示全部 8 项条件（不省略），便于一眼复核
  const p: string[] = [identityLabel.value, '区排名 ' + (form.rank || '—')]
  p.push(xedQuery.value ? xedQuery.value.replace('北京市', '') : '初中未填')
  p.push(modeLabel.value + '≤' + (form.max_km || '?') + 'km')
  p.push(form.boarding ? '可住宿' : '不住宿')
  p.push(riskCfg.value.label)                                            // 风险偏好
  p.push(form.orient === 'abroad' ? '兼顾出国' : '体制内')                // 升学取向(始终显示)
  p.push(form.nonpub === 'pub_only' ? '仅公办' : form.nonpub === 'no' ? '仅公办+民办' : '考虑贯通中职')  // 贯通/中职(始终显示)
  return p.join(' · ')
})
// 折叠态下改了条件 → 标记 dirty，提示重新生成
watch([form, xedQuery], () => { if (result.value && !formOpen.value) formDirty.value = true }, { deep: true })
// 切区:清掉上一区的结果与草表,展开表单,提示重新生成(不同区录取线/学校完全不同)
watch(curDistrict, () => {
  result.value = null
  formOpen.value = true
  formDirty.value = false
  tab.value = 'map'
})
const canIndicator = computed(() => form.identity === 'jjyj')   // 指标分配=校额到校/统筹：京籍应届
const canGuantong = computed(() => form.identity === 'jjyj')    // 贯通：京籍应届
const canPuhao = computed(() => form.identity !== 'feijing')    // 普高统招：非京籍不可
// 全渠道草表:统招批内除公办,还可纳入 民办普高/中职综合高中班/(2026)贯通 作为志愿+保底
const nonPubCands = computed<any[]>(() => {
  const res: any = result.value
  if (!res) return []
  const out: any[] = []
  const useGtVoc = form.nonpub === 'yes'   // 「贯通/中职」开关;仅 yes 纳入(no/pub_only 均不纳)
  const usePrivate = form.nonpub !== 'pub_only'   // 民办普高:pub_only=仅公办,不纳民办
  if (useGtVoc && canGuantong.value) {            // 贯通(京籍·≥380·2026并入统招)
    const seen = new Set<string>()
    for (const p of (res.guantong?.projects || [])) {
      if (seen.has(p.school)) continue; seen.add(p.school)
      out.push({ name: p.school, chan: '贯通', band: '本科', school_code: '',
                 note: '贯通·中考≥380·7年到本科·' + (p.type || '') })
    }
  }
  for (const p of (usePrivate ? (res.private_schools?.schools || []) : [])) {   // 民办普高
    const ex = p.exit_type
    const wantAbroad = form.orient === 'abroad'   // 升学取向(输入条件区)唯一控制
    if (ex === '高考' || ex === '混合' || (wantAbroad && ex === '留学')) {
      out.push({ id: p.id, name: p.name, chan: '民办', band: '路线', school_code: p.code || '',
                 note: '民办·' + (ex === '留学' ? '留学向·' : '') + (p.tuition || '门槛低·多可入') })
    }
  }
  for (const v of (useGtVoc ? (res.vocational?.schools || []) : [])) {  // 中职综合高中班(保底)
    if (v.comp_high_2025) out.push({ id: v.id, name: v.name, chan: '中职', band: '保底', school_code: '',
                 note: '中职综合高中班·普高学籍可高考·门槛最低(' + (v.line_note ? '劲松线≈9485' : '稳进') + ')' })
  }
  return out
})
const nonPubByName = computed<Record<string, any>>(() => {
  const m: Record<string, any> = {}; for (const c of nonPubCands.value) m[c.name] = c; return m
})
const identityNote = computed(() => {
  if (form.identity === 'feijing') return '非京籍随迁子女不能报普通高中（统招/指标分配/贯通），只能报中职类；下列普高批次仅供了解。'
  if (form.identity === 'wangjie') return '往届/回户籍/外省回京考生不能报指标分配(校额到校/统筹)与贯通；普高统招可报。'
  return ''
})
// ② 指标分配-市级统筹：自由填写
interface TcSlot { school: string | null; majors: string }
const draftTongchou = ref<TcSlot[]>(Array.from({ length: 8 }, () => ({ school: null, majors: '' })))
// ② 指标分配-校额到校：选优质高中(来自孩子初中的名额) + 专业手填
interface XedSlot { school: string | null; majors: string }
const draftXed = ref<XedSlot[]>(Array.from({ length: 8 }, () => ({ school: null, majors: '' })))
// 当前初中(复用 xedQuery)可报的优质高中 + 名额；待核校(无明细)返回空并由模板提示
const xedEligible = computed<{ school: string; n: number }[]>(() => {
  const r = xedSel.value
  if (!r || !r.by_school) return []
  return Object.entries(r.by_school).map(([school, n]) => ({ school, n: n as number }))
})
// 校额缩写 → 官方全名(后端按注册表解析,随 xeddx.resolved 下发);带校区括号的保留校区以区分本部/分校
function xedName(abbr: string): string {
  const base = (xedBlock.value as any)?.resolved?.[abbr]?.name || XED_FULLNAME[abbr] || abbr
  const m = abbr.match(/[（(](.+?)[)）]/)
  return m && !base.includes(m[1]) ? `${base}（${m[1]}）` : base
}
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
    return { ...e, full, ref, tag, km: card?.nearest?.km ?? null, boarding: !!(card && card.boarding) }
  }).sort((a, b) => (a.ref ?? 9e9) - (b.ref ?? 9e9))
})
const XED_TAG: Record<string, { label: string; cls: string }> = {
  worth: { label: '✅值得冲(统招够不上)', cls: 'rt-worth' },
  similar: { label: '≈与统招相当', cls: 'rt-similar' },
  waste: { label: '⚠️统招本可达·占用浪费', cls: 'rt-waste' },
  unknown: { label: '—', cls: 'rt-unknown' },
}
const XED_TAG_BAND: Record<string, string> = { worth: 'band-冲', similar: 'band-稳', waste: 'band-够不上', unknown: 'band-稳' }
// 校额到校右侧短徽标(长说明留在理由 headline 里):统一行格式用
const XED_TAG_SHORT: Record<string, string> = { worth: '值得冲', similar: '相当', waste: '占用', unknown: '—' }
function xedBadge(school: string | null): { label: string; cls: string } | null {
  const r = xedReason(school)
  if (!r) return null
  const e = xedRecommend.value.find(x => x.school === school)
  return { label: XED_TAG_SHORT[e?.tag || 'unknown'] || '—', cls: r.cls }
}
// B1:校内排名 vs 该校名额 n → 中签研判(竞争仅在"本校也报了这所校的人"里,故为倾向非承诺)
function xedWinTier(n: number): { chip: string; note: string } | null {
  const sr = Number(form.schoolRank) || 0
  if (!sr || !n) return null
  if (sr <= n) return { chip: `📈排名${sr}≤名额${n}·大概率中`, note: `你校内排名 ${sr} 已进名额数(${n})内——只要排你前面的同学不都报它,基本能中` }
  if (sr <= n * 3) return { chip: `📊排名${sr}/名额${n}·有戏`, note: `校内排名 ${sr} 在名额(${n})的3倍内——是否中取决于排你前面的同学报不报这所校` }
  return { chip: `🎫排名${sr}/名额${n}·彩票`, note: `校内排名 ${sr} 距名额(${n})较远——除非排你前面的报名者少于名额数,属免费彩票(不中无损失)` }
}
// 校额到校：单行理由（基于 xedRecommend 的 tag/ref/名额）
function xedReason(school: string | null): { label: string; cls: string; headline: string; caveat: string } | null {
  if (!school) return null
  const e = xedRecommend.value.find(x => x.school === school)
  if (!e) return null
  const rank = Number(form.rank) || 0
  const refTxt = e.ref != null ? '≈' + e.ref : '待核'
  let headline = ''
  if (e.tag === 'worth') headline = `统招位次${refTxt}比你(≈${rank})靠前 → 统招够不上、校额(校内排名)才有机会`
  else if (e.tag === 'similar') headline = `统招位次${refTxt}与你相当 → 校额可作多一条进名校通道`
  else if (e.tag === 'waste') headline = `统招位次${refTxt}比你靠后 → 统招本可达，占校额名额意义小`
  else headline = '该校统招位次未知，按本校名额参考'
  const wt = xedWinTier(e.n)
  return { label: (XED_TAG[e.tag] || XED_TAG.unknown).label, cls: XED_TAG_BAND[e.tag] || 'band-稳',
    headline, caveat: (wt ? wt.note + '。' : '') + `本校名额 ${e.n}；按本初中校内排名 + 志愿顺序录取、无官方各校线；录取即锁定` }
}
const xedSummary = computed(() => {
  const cnt: Record<string, number> = { worth: 0, similar: 0, waste: 0, unknown: 0 }
  for (const sl of draftXed.value) {
    if (!sl.school) continue
    const e = xedRecommend.value.find(x => x.school === sl.school)
    if (e) cnt[e.tag]++
  }
  return { cnt, filled: draftXed.value.filter(sl => sl.school).length }
})
// 市级统筹：可报校（统筹二+统筹一）+ 缺省填报 + 单行理由
function tcKey(s: any): string { return s.name + (s.campus ? '·' + s.campus : '') }
const tcEligible = computed<any[]>(() => {
  const all = [
    ...(tcEr.value || []).map((s: any) => ({ s, tier: '统筹二' })),
    ...(tcYi.value || []).map((s: any) => ({ s, tier: '统筹一' })),
  ]
  return all.map(o => ({ key: tcKey(o.s), tier: o.tier, s: o.s, j: tcJudge(o.s) }))
})
function prefillTongchou() {
  // 统筹在统招前·录取即锁定：只填"你估分≤其统招线"的 reach（够一够的 upgrade；没中自动落到统招、无损失）；
  // 排除稳/保（你高于其线=会被锁进比你弱的外区校=陷阱）与线待核。排序从高到低：够不上→搏→冲。
  // 入选优先级：搏(更值得拼)→冲→够不上(仅兜底回填空位)；展示按从高到低（够不上→搏→冲）
  // 通勤同口径(跟随住宿勾选)：≤上限 或 (接受住宿 且 该校提供住宿)；远校无住宿=没法住校又通勤不了→排除
  // 只自动填"够一够的真 upgrade":档次显著优于你 + 够得着门槛 + 非不值 + 非远郊(需寄宿重负·默认不推)
  // + 有朝阳名额 + 通勤可达。远郊/平级校仍在下拉里(可手动加),但不进默认草表,免得朝阳娃被默认锁去郊区。
  // B5:远郊(j.far)默认不自动填;表单勾选"接受远郊寄宿统筹"后纳入(caveat 仍带远郊警示)
  const cand = tcEligible.value
    .filter(e => e.j.worth && (form.farBoarding || !e.j.far) && (e.s.quota_chaoyang || 0) > 0
                 && e.j.label !== '够不上' && reachByCommute(e.s.dist?.km, !!e.s.boarding))
    .sort((a, b) => (a.s.cy_equiv ?? 9e9) - (b.s.cy_equiv ?? 9e9))
    .slice(0, 8)
  draftTongchou.value = Array.from({ length: 8 }, (_, i) =>
    cand[i] ? { school: cand[i].key, majors: cand[i].s.tongchou_major?.major_code || '' } : { school: null, majors: '' })
}
// 远郊开关切换 → 重排统筹自动填(有结果时)
watch(() => form.farBoarding, () => { if (result.value) prefillTongchou() })
// 统筹 key → 纯校名(+校区);档次进右侧徽标、统筹几进 meta(与校额/统招行格式统一)
function tcName(key: string | null): string {
  if (!key) return ''
  const e = tcEligible.value.find(x => x.key === key)
  if (!e) return key
  return `${cleanName(e.s.name)}${e.s.campus ? '·' + e.s.campus : ''}`
}
function tcTier(key: string | null): string {
  if (!key) return ''
  return tcEligible.value.find(x => x.key === key)?.tier || ''
}
function tcReason(key: string | null): { label: string; cls: string; headline: string; factors: string[]; caveat: string } | null {
  if (!key) return null
  const e = tcEligible.value.find(x => x.key === key)
  if (!e) return null
  const j = e.j, s = e.s
  const factors: string[] = []
  if (s.school_code && s.tongchou_major) factors.push('🏷网报 学校码' + s.school_code + '·专业' + s.tongchou_major.major_code)
  if (s.dist) factors.push('🚌' + s.dist.km + 'km')
  if (s.boarding === true) factors.push('🛏可住宿')
  const myR = Number(form.rank) || null
  const lineTxt = j.entry != null
    ? `统筹门槛≈朝阳第${j.entry}位 · 学校档次≈第${j.equiv}位（你区排≈${myR ?? '—'}）`
    : '门槛待核'
  const headline = `${e.tier} · ${s.district} · 投朝阳 ${s.quota_chaoyang} 名 · ${lineTxt}`
  const label = j.label === '够不上' ? '冲刺' : j.label
  const cls = j.label === '够不上' ? 'band-刺' : j.cls
  let caveat = j.below
    ? '⚠️校档次低于门槛(线<控制线460)：朝阳走统筹需≈460分反不如统招，通常不值。'
    : j.worth
      ? '够一够外区名校：你统招够不上该档、统筹够得着；没中自动落统招(无损失)；⚠️一旦录取即锁定、放弃统招——确认更想去再保留。'
      : '⚠️你统招本可达该档(或档次未显著高于你/够不上门槛)：走统筹通常不划算/不可达，慎填。'
  if (j.far) caveat = '⚠️远郊(' + s.district + ')·距朝阳远、需长期寄宿、周末难回：默认不自动填,手动选请确认你确实愿意送孩子去寄宿。' + caveat
  caveat += '朝阳口径门槛=外区线分映射+经验折让(估，非官方线)；朝外能否报 / 分到名额须查简章。'
  if (e.tier === '统筹一') caveat = '统筹一=名校本部、门槛高；' + caveat
  return { label, cls, headline, factors, caveat }
}
const tcSummary = computed(() => {
  const cnt: Record<string, number> = { 保: 0, 稳: 0, 冲: 0 }
  for (const sl of draftTongchou.value) {
    if (!sl.school) continue
    const e = tcEligible.value.find(x => x.key === sl.school)
    if (e && cnt[e.j.label] != null) cnt[e.j.label]++
  }
  return { cnt, filled: draftTongchou.value.filter(sl => sl.school).length }
})

// 校额到校：按推荐(值得冲→相当，排除浪费，最好的在前)缺省填入志愿
function prefillXed() {
  // ②指标分配在统招前·录取即锁定：只填"统招够不上"的 upgrade（✅值得冲），不填≈相当/统招本可达（避免锁进同级或更低校）
  // 通勤同口径：超上限的只有"接受住宿且该校提供住宿"才进自动填（下拉仍可手动选）
  const rec = xedRecommend.value.filter(e => e.tag === 'worth' && reachByCommute(e.km, e.boarding))
  draftXed.value = Array.from({ length: 8 }, (_, i) =>
    rec[i] ? { school: rec[i].school, majors: '' } : { school: null, majors: '' })
}
// 初中校变化时自动按推荐预填（有明细时）
watch(() => (xedSel.value ? xedSel.value.code : ''), () => {
  if (xedSel.value && xedSel.value.by_school) prefillXed()
}, { immediate: true })

// ── 指标分配批合并：校额到校 + 市级统筹 共用 8 个志愿，按"最好且够得着"从前到后排一列（同档校额优先）──
// 官方2026(bjeea 88027)：两类合用「指标分配批」共 8 志愿、按填报顺序从高分到低分录取、录取即锁定。
const IND_CAP = 8
const indicatorRows = computed<DraftRowVM[]>(() => {
  type It = { chan: '校额' | '统筹'; sort: number; vm: DraftRowVM }
  const items: It[] = []
  xedFilled.value.forEach(s => {
    const b = xedBadge(s.school); const r = xedReason(s.school)
    const e = xedRecommend.value.find(x => x.school === s.school)
    const wt = e ? xedWinTier(e.n) : null
    items.push({ chan: '校额', sort: Number(e?.ref ?? 9e9), vm: {
      seq: 0, name: xedName(s.school!), meta: '校额到校', band: b || undefined,
      majors: [], majorsNote: '以官方网报为准', headline: r?.headline,
      factors: e ? [`🎯本校名额${e.n}`, ...(wt ? [wt.chip] : [])] : undefined,   // B2 名额上卡 + B1 中签研判
      risk: r?.caveat,
    } })
  })
  // B3 同校保险:统招草表里分数边缘的目标校(统招位次与你差<5%),本初中有其校额名额且未入清单 → 补入
  {
    const rank = Number(form.rank) || 0
    if (rank) {
      const inXed = new Set(xedFilled.value.map(s => s.school))
      for (const u of uniFilled.value) {
        const c: any = findCard(u.name!)
        const ref = c && typeof c.ref_rank === 'number' ? (c.ref_rank as number) : null
        if (ref == null || !(ref > rank * 0.95 && ref < rank * 1.05)) continue
        const e = xedRecommend.value.find(x => x.full === u.name && (x.n || 0) > 0)
        if (!e || inXed.has(e.school)) continue
        inXed.add(e.school)
        const wt = xedWinTier(e.n)
        items.push({ chan: '校额', sort: ref, vm: {
          seq: 0, name: xedName(e.school), meta: '校额到校', band: { label: '同校保险', cls: 'band-稳' },
          majors: [], majorsNote: '以官方网报为准',
          headline: `统招目标校、分数在边缘(统招位次≈${ref} vs 你≈${rank}) → 校额是同一目标的更稳路径`,
          factors: [`🎯本校名额${e.n}`, ...(wt ? [wt.chip] : [])],
          risk: '锁定=锁进你统招本来想去的校,无损失;按本初中校内排名录取',
        } })
      }
    }
  }
  tcFilled.value.forEach(s => {
    const r = tcReason(s.school); const e = tcEligible.value.find(x => x.key === s.school)
    items.push({ chan: '统筹', sort: Number(e?.s?.cy_equiv ?? 9e9), vm: {
      seq: 0, name: tcName(s.school!), meta: '统筹·' + (tcTier(s.school!) || ''),
      band: r ? { label: r.label, cls: TC_BAND_CLS[r.label] || 'band-够不上' } : undefined,
      majors: s.majors ? [{ code: s.majors }] : [], majorsNote: '以官方网报为准',
      headline: r?.headline, factors: r?.factors, risk: r?.caveat,
    } })
  })
  // 高中位次靠前(更好/更该冲)在前；同位次校额优先于统筹
  items.sort((a, b) => a.sort - b.sort || (a.chan === '校额' ? 0 : 1) - (b.chan === '校额' ? 0 : 1))
  return items.slice(0, IND_CAP).map((it, i) => ({ ...it.vm, seq: i + 1 }))
})
const indicatorSummary = computed(() => {
  const xed = xedFilled.value.length, tc = tcFilled.value.length
  const filled = xed + tc
  return { xed, tc, filled, shown: Math.min(filled, IND_CAP), over: filled > IND_CAP }
})

// B6:一键复制志愿草表(指标批+统招,对齐网报顺序),便于保存/打印/发给家人核对
const copyOk = ref(false)
function copyDraft() {
  const L: string[] = ['【② 指标分配批 · 校额到校＋市级统筹 · 共8志愿·按顺序录取·录取即锁定】']
  if (indicatorRows.value.length)
    indicatorRows.value.forEach(r => L.push(`${r.seq}. ${r.name}（${r.meta || ''}${r.band ? '·' + r.band.label : ''}）`))
  else L.push('（不填——本位次无值得锁定的 upgrade,直接进统招）')
  L.push('', '【③ 统一招生 · 共8志愿】')
  uniRows.value.forEach(r => L.push(`${r.seq}. ${r.name}${r.majors && r.majors.length ? '  专业:' + r.majors.map(m => m.code + (m.name ? ' ' + m.name : '')).join(' / ') : ''}`))
  L.push('', '⚠️ 参考草表,以官方网报系统为准 · 生成于 zhongkao.gatesby.xyz/zhiyuan')
  navigator.clipboard.writeText(L.join('\n'))
    .then(() => { copyOk.value = true; setTimeout(() => (copyOk.value = false), 2000) })
    .catch(() => {})
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
      <div class="hero-top">
        <h1>北京中考志愿参考<select v-model="curDistrict" class="dist-sel"><option v-for="d in DISTRICTS" :key="d[0]" :value="d[0]">{{ d[1] }}{{ (districtModes[d[0]] || 'browse') === 'full' ? '' : '·查校' }}</option></select></h1>
        <AccountMenu app-name="zhiyuan" />
      </div>
      <p class="sub">按区排名做冲稳保匹配，叠加通勤路网距离与学校特色，并镜像官方填报格式生成统招志愿草表。仅辅助参考，最终以官方招生简章与老师建议为准。</p>
    </header>

    <!-- full=全功能(冲稳保+草表+全维,数据已对标朝阳);browse=校库浏览(暂无录取线) -->
    <template v-if="curMode === 'full'">
    <div class="disclaimer">
      ⚠️ 学校代码 / 专业(班)代码及计划数派生自 <b>《2026 北京中招大报纸》官方招生简章</b>（逐校精读核对）；高考成绩为<b>民间·非官方</b>数据，仅作补充参考，请勿据此直接决策。
    </div>

    <!-- 输入区：生成前完整表单；生成后折叠成一行摘要(很少再改) -->
    <section class="card form" :class="{ collapsed: result && !formOpen }">
      <!-- 折叠摘要条 -->
      <button v-if="result && !formOpen" class="form-bar" @click="formOpen = true">
        <svg class="fb-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M6 12h12M10 18h4"/></svg>
        <span class="fb-sum">{{ formSummary }}</span>
        <span v-if="formDirty" class="fb-dirty">条件已改，点此重新生成</span>
        <span class="fb-edit">修改条件 ▾</span>
      </button>
      <!-- 完整表单 -->
      <div v-show="!result || formOpen" class="fields">
        <div class="fgrp-title">学生信息</div>
        <label class="fld fld-id">考生身份
          <select v-model="form.identity">
            <option v-for="x in IDENTITIES" :key="x.v" :value="x.v">{{ x.label }}</option>
          </select>
        </label>
        <label class="fld fld-rank">区排名 <small>一模/二模</small>
          <input type="number" v-model.number="form.rank" min="1" placeholder="如 4500" />
        </label>
        <label class="fld fld-jr">初中学校 <small>校额/统筹用</small>
          <input list="xedSchoolListMain" v-model="xedQuery" placeholder="如 朝阳外国语学校" />
        </label>
        <datalist id="xedSchoolListMain"><option v-for="r in (xedBlock ? xedBlock.rows : [])" :key="r.code" :value="r.name" /></datalist>
        <label class="fld fld-xrank">校内排名 <small>选填·精判校额</small>
          <input type="number" v-model.number="form.schoolRank" min="1" placeholder="如 15（年级名次）" />
        </label>
        <label class="fld fld-farb">远郊寄宿统筹 <small>统筹校多为远郊</small>
          <select v-model="form.farBoarding">
            <option :value="false">不考虑（默认，不自动填）</option>
            <option :value="true">接受（远郊统筹纳入自动填）</option>
          </select>
        </label>
        <label class="fld fld-home">家庭住址 <small>留空只看全区分布</small>
          <input type="text" v-model="form.home" placeholder="如 朝阳区紫玉山庄" />
        </label>

        <div class="fgrp-title">通勤与住宿</div>
        <label class="fld fld-mode">通勤方式
          <select v-model="form.mode">
            <option v-for="m in MODES" :key="m.v" :value="m.v">{{ m.label }}</option>
          </select>
        </label>
        <label class="fld fld-km">通勤上限 <small>km</small>
          <input type="number" v-model="form.max_km" min="1" placeholder="8" />
        </label>
        <div class="fld fld-board">接受住宿
          <label class="switch">
            <input class="sw-input" type="checkbox" v-model="form.boarding" />
            <span class="sw-track"><span class="sw-thumb"></span></span>
            <span class="sw-txt">远校可住校（通勤上限仍生效）</span>
          </label>
        </div>

        <div class="fgrp-title">志愿偏好 <small>影响草表的冲稳保配比与渠道</small></div>
        <label class="fld fld-risk">风险偏好 <small>冲稳保配比</small>
          <select v-model="form.risk" @change="resetDraft">
            <option value="safe">保底优先（稳妥）</option>
            <option value="balanced">均衡（推荐）</option>
            <option value="aggressive">冲高（多冲刺）</option>
          </select>
        </label>
        <label class="fld fld-orient">升学取向 <small>是否纳入民办/国际</small>
          <select v-model="form.orient" @change="resetDraft">
            <option value="gaokao">体制内高考</option>
            <option value="abroad">兼顾出国（含国际/留学向）</option>
          </select>
        </label>
        <label class="fld fld-nonpub">贯通/中职 <small>保底渠道</small>
          <select v-model="form.nonpub" @change="resetDraft">
            <option value="yes">考虑（位次低时自动纳入）</option>
            <option value="no">不考虑（仅公办+民办）</option>
            <option value="pub_only">不考虑（仅公办）</option>
          </select>
        </label>

        <div class="fld fld-go">
          <button class="go" :disabled="loading" @click="submit">
            <svg v-if="!loading" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4-4"/></svg>
            {{ loading ? '匹配中…' : '生成志愿建议' }}
          </button>
        </div>
      </div>
      <div v-if="result && formOpen" class="form-collapse"><button class="fb-edit" @click="formOpen = false">收起 ▴</button></div>
      <p v-if="errMsg" class="err">{{ errMsg }}</p>
    </section>

    <section v-if="result" class="results">
      <!-- 一级导航：地图 / 草表 / 查学校 / 渠道科普 -->
      <div class="tabbar">
        <div class="tabs" role="tablist">
          <button class="tab" :class="{ on: tab === 'map' }" @click="goTab('map')"><span class="tab-ic" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18.5 3 21V6l6-2.5 6 2.5 6-2.5V21l-6-2.5-6 2.5Z"/><path d="M9 3.5v15"/><path d="M15 5.5v15"/></svg></span>志愿地图</button>
          <button class="tab" :class="{ on: tab === 'draft' }" @click="goTab('draft')"><span class="tab-ic" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6a1 1 0 0 1 1 1v1h1.5A1.5 1.5 0 0 1 19 6.5v13A1.5 1.5 0 0 1 17.5 21h-11A1.5 1.5 0 0 1 5 19.5v-13A1.5 1.5 0 0 1 6.5 5H8V4a1 1 0 0 1 1-1Z"/><path d="M9 5h6"/><path d="M8.5 11h7"/><path d="M8.5 15h4.5"/></svg></span>志愿草表<span class="tab-cnt">{{ filledSlots }}/{{ ZHIYUAN_SLOTS }}</span></button>
          <button class="tab" :class="{ on: tab === 'explore' }" @click="goTab('explore')"><span class="tab-ic" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4-4"/></svg></span>查学校<span class="tab-cnt">{{ uList.length }}</span></button>
          <button class="tab" :class="{ on: tab === 'channels' }" @click="goTab('channels')"><span class="tab-ic" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6.5v13"/><path d="M12 6.5C10.7 5.2 8.9 4.5 7 4.5H4a1 1 0 0 0-1 1v11.5a1 1 0 0 0 1 1h3.5c1.6 0 3.2.6 4.5 1.5 1.3-.9 2.9-1.5 4.5-1.5H20a1 1 0 0 0 1-1V5.5a1 1 0 0 0-1-1h-3c-1.9 0-3.7.7-5 2Z"/></svg></span>渠道科普</button>
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
          <div v-if="selectedPoint" class="dp-backdrop" @click="closeDetail"></div>
          <aside class="detail-panel" :class="{ 'dp-sheet': selectedPoint }">
            <button v-if="selectedPoint" class="dp-close" @click="closeDetail" aria-label="关闭">✕</button>
            <template v-if="selectedPoint">
              <template v-if="selSchool">
                <div class="dp-head">
                  <span class="dp-type">{{ selSchool.type }}{{ selSchool.level ? ' · ' + selSchool.level : '' }}</span>
                  <h3>{{ cleanName(selSchool.name) }}</h3>
                </div>
                <div v-if="selSchool.extra.coop" class="dp-sub">
                  <span class="bdg b-coop">🌐中外合作班</span>
                </div>

                <div v-if="selSchool.pred_2026" class="dp-block dp-pred">
                  <div class="dp-title">📍 2026 录取位次预估（核心依据）</div>
                  <div class="dp-line"><b class="dp-predv">≈{{ selSchool.pred_2026.rank }}</b> <span class="dp-muted">区间 {{ selSchool.pred_2026.lo }}–{{ selSchool.pred_2026.hi }}<template v-if="selSchool.pred_2026.pct"> · 约前{{ selSchool.pred_2026.pct }}%</template></span></div>
                  <div class="dp-line dp-muted">{{ selSchool.pred_2026.method === 'new_anchor' ? '新校锚定' : selSchool.pred_2026.method === 'tongchou_cy_equiv' ? '跨区位次映射(外区线→朝阳口径)' : selSchool.pred_2026.method === 'hist' ? ('以' + (selSchool.pred_2026.base_year || '最近年') + '录取位次为参考（非模型预测·网传/历史线）') : '百分位法' }} · 可信度 {{ selSchool.pred_2026.conf }} · 7/9出分接你的精确位次→7/13填报即用（各校实线录取后才有，填报当下靠此预测）</div>
                  <div v-if="selSchool.extra && selSchool.extra.cy_equiv" class="dp-line dp-muted">↑此为<b>走统筹门槛</b>(录取位次) · 学校档次≈朝阳第 {{ selSchool.extra.cy_equiv }} 位(线分→朝阳一分一段,全市可比)<span v-if="selSchool.extra.below_control"> · ⚠档次低于门槛,走统筹需≈460反不如统招,常不值</span></div>
                </div>

                <div class="dp-block">
                  <div class="dp-title">对你的研判<small class="dp-muted">（按2026预估位次）</small></div>
                  <div v-for="(v, ci) in channelViews" :key="ci" class="dp-ch">
                    <span class="dp-ch-name">{{ v.name }}</span>
                    <span class="tj" :class="v.cls">{{ v.band }}</span>
                    <span class="dp-ch-detail">{{ v.detail }}</span>
                  </div>
                  <p v-for="(c, idx) in panelCaveats" :key="idx" class="dp-tip">⚠️ {{ c }}</p>
                </div>

                <!-- 基本信息(前置) -->
                <div class="dp-block" v-if="selSchool.geo.address || selSchool.commute || selSchool.boarding != null || selSchool.extra.tuition || (selSchool.extra.curriculum && selSchool.extra.curriculum.length) || (selSchool.extra.specialties && selSchool.extra.specialties.length) || selSchool.extra.system || (selSchool.extra.analog && selSchool.extra.analog.length) || (selSchool.extra.campuses && selSchool.extra.campuses.length) || selSchool.extra.class_info">
                  <div class="dp-title">基本信息</div>
                  <div v-if="selSchool.geo.address" class="dp-line dp-muted">📍 {{ selSchool.geo.address }}<span v-if="selSchool.geo.confidence === 'low' || !selSchool.geo.lat" class="addr-tag">待核</span></div>
                  <div v-if="selSchool.commute" class="dp-line">🚌 到家 {{ selSchool.commute.km }}km · {{ selSchool.commute.mins }}分钟<span v-if="selSchool.commute.over_max" class="dp-vol">⚠️超上限</span></div>
                  <div class="dp-line">🛏 住宿：<span v-if="selSchool.boarding === true" class="t-yes">可住宿</span><span v-else-if="selSchool.boarding === false">不提供</span><span v-else class="dp-muted">待核</span><template v-if="selSchool.boarding === true && selSchool.campus_life && selSchool.campus_life.boarding_detail"> · <span class="dp-muted">{{ selSchool.campus_life.boarding_detail }}</span></template></div>
                  <div v-if="selSchool.commute && selSchool.commute.over_max && selSchool.boarding === false" class="dp-line dp-vol">⚠️ 家远且不住宿，通勤超上限，慎报</div>
                  <div v-if="selSchool.campus_life && selSchool.campus_life.dining" class="dp-line">🍚 食堂：{{ selSchool.campus_life.dining }}</div>
                  <div v-if="selSchool.extra.tuition" class="dp-line">💰 学费：{{ selSchool.extra.tuition }}</div>
                  <div v-if="selSchool.extra.curriculum && selSchool.extra.curriculum.length" class="dp-line">📚 课程：{{ selSchool.extra.curriculum.join('·') }}<template v-if="selSchool.extra.direction"> · {{ selSchool.extra.direction }}</template></div>
                  <div v-if="selSchool.extra.direction && !(selSchool.extra.curriculum && selSchool.extra.curriculum.length)" class="dp-line dp-muted">方向：{{ selSchool.extra.direction }}</div>
                  <div v-if="selSchool.extra.specialties && selSchool.extra.specialties.length" class="dp-line">🛠 专业：{{ selSchool.extra.specialties.join('·') }}</div>
                  <div v-if="selSchool.extra.system" class="dp-line">🏛 体系：{{ selSchool.extra.system }}</div>
                  <div v-if="selSchool.extra.analog && selSchool.extra.analog.length" class="dp-line dp-muted">↔ 可类比：{{ selSchool.extra.analog.join('、') }}</div>
                  <div v-if="selSchool.extra.campuses && selSchool.extra.campuses.length" class="dp-line dp-muted">🏫 校区：{{ selSchool.extra.campuses.join(' / ') }}</div>
                  <div v-if="selSchool.extra.class_info" class="dp-line dp-muted">👥 {{ selSchool.extra.class_info }}<template v-if="selSchool.extra.enroll_2025"> · 2025招{{ selSchool.extra.enroll_2025 }}人</template></div>
                </div>

                <!-- 贯通项目 -->
                <div v-if="selSchool.extra.projects && selSchool.extra.projects.length" class="dp-block">
                  <div class="dp-title">贯通项目（→本科）</div>
                  <div v-for="(pj, pi) in selSchool.extra.projects" :key="pi" class="dp-mj">{{ pj.type }}：{{ pj.major }} → {{ pj.benke }}<em v-if="pj.plan"> · {{ pj.plan }}人</em></div>
                  <div v-if="selSchool.extra.projects[0].threshold" class="dp-line dp-muted">🎯 门槛：中考≥{{ selSchool.extra.projects[0].threshold }}分 · 学制{{ selSchool.extra.projects[0].years }}年 · 京籍应届 · 提前批</div>
                  <template v-for="(tm, tk) in (selSchool.extra.type_meta || {})" :key="tk"><div v-if="tm" class="dp-line dp-muted">🔁 {{ tk }}：{{ tm.transfer }}；{{ tm.tuition }}</div></template>
                </div>

                <!-- 录取数据 -->
                <div v-if="schoolLines.length || selSchool.line_trend || selSchool.extra.voc_line_note || (selSchool.extra.line_note && (selSchool.extra.in_minban || selSchool.extra.in_intl))" class="dp-block">
                  <div class="dp-title">录取数据</div>
                  <table v-if="schoolLines.length" class="dp-table">
                    <thead><tr><th>年</th><th>线</th><th>口径/区排</th></tr></thead>
                    <tbody>
                      <tr v-for="sl in schoolLines" :key="sl.year">
                        <td>{{ sl.year }}</td>
                        <td>{{ sl.score != null ? sl.score + (sl.scale ? '(' + sl.scale + '制)' : '分') : '—' }}</td>
                        <td>{{ sl.rank != null ? sl.rank + '名' : (sl.conf || '') }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <div v-if="selSchool.line_trend" class="dp-line">📈 录取位次(区)：{{ selSchool.line_trend.ranks['2023'] || '—' }} → {{ selSchool.line_trend.ranks['2024'] || '—' }} → <b>{{ selSchool.line_trend.ranks['2025'] || '—' }}</b><span class="dp-muted">（23/24/25 历史）</span><span v-if="selSchool.line_trend.volatile" class="addr-tag">波动大</span></div>
                  <div v-if="selSchool.extra.voc_line_note" class="dp-line dp-muted">📈 录取线：{{ selSchool.extra.voc_line_note }}</div>
                  <div v-if="selSchool.extra.line_note && (selSchool.extra.in_minban || selSchool.extra.in_intl)" class="dp-line dp-muted">📈 录取：{{ selSchool.extra.line_note }}</div>
                  <p v-if="schoolLines.length" class="dp-tip">分数跨年口径不同(2025起510制)；同年/区排名才可比。</p>
                </div>

                <!-- 招生计划(统招专业/班 名额) -->
                <div v-if="selMajors.length" class="dp-block">
                  <div class="dp-title">招生计划 <small class="dp-muted">· 朝阳·2026官方简章</small></div>
                  <div v-for="(m, mi) in selMajors" :key="mi" class="dp-mj">{{ cleanName(m.major_name) }}<em> · 本区 {{ planNum(m.plan_chaoyang) }}<template v-if="m.plan_total != null && String(m.plan_total) !== String(m.plan_chaoyang)"> · 全市 {{ planNum(m.plan_total) }}</template></em></div>
                  <p class="dp-tip">2026 计划数（派生自《2026 北京中招大报纸》官方招生简章，逐校精读）。</p>
                </div>

                <!-- 出口质量 -->
                <div v-if="selSchool.gaokao || selSchool.value_added || selSchool.extra.study_abroad || selSchool.extra.exit_domestic || selSchool.extra.exit_type || selSchool.extra.comp_high_note || selSchool.extra.exit_paths || selSchool.features.gaokao" class="dp-block">
                  <div class="dp-title">出口质量</div>
                  <div v-if="selSchool.extra.study_abroad" class="dp-line">🎓 留学走向：{{ selSchool.extra.study_abroad }}</div>
                  <div v-else-if="selSchool.extra.exit_domestic" class="dp-line">🎓 高考出口：{{ selSchool.extra.exit_domestic }}</div>
                  <div v-else-if="selSchool.extra.exit_type === '暂无毕业生'" class="dp-line dp-muted">🎓 新建高中部·首届未毕业，暂无升学出口</div>
                  <div v-else-if="selSchool.extra.exit_type === '未公布'" class="dp-line dp-muted">🎓 升学出口：学校未公布</div>
                  <div v-if="selSchool.extra.comp_high_note" class="dp-line">🎓 综合高中班：{{ selSchool.extra.comp_high_note }}</div>
                  <div v-if="selSchool.extra.exit_paths" class="dp-line">🚀 升学路径：{{ selSchool.extra.exit_paths }}</div>
                  <div v-if="selSchool.gaokao && selSchool.gaokao.score != null" class="dp-line">🎓 高考评分 <b>{{ selSchool.gaokao.score }}</b>/100 · {{ selSchool.gaokao.tier }}
                    <span class="dp-muted">（{{ selSchool.gaokao.yiben != null ? '一本' + Math.round(selSchool.gaokao.yiben * 100) + '%' : (selSchool.gaokao.yiben_est != null ? '一本≈' + Math.round(selSchool.gaokao.yiben_est * 100) + '%(估)' : '') }}{{ selSchool.gaokao.qingbei ? ' 清北' + selSchool.gaokao.qingbei : '' }} · {{ selSchool.gaokao.confidence === 'very_low' ? '估算·待核' : selSchool.gaokao.confidence === 'low' ? '民间·低置信' : '民间·中置信' }}）</span></div>
                  <div v-else-if="selSchool.gaokao" class="dp-line dp-muted">🎓 高考 新建高中部·首届未毕业,暂无出口数据（入口位次可参考）</div>
                  <div v-if="selSchool.value_added" class="dp-line">📊 增值：<b :class="'va-' + selSchool.value_added.label">{{ selSchool.value_added.label }}</b><span class="dp-muted"> · {{ selSchool.value_added.basis }}</span></div>
                  <div v-if="selSchool.features.gaokao" class="dp-line dp-muted">🎓 高考(民间·非官方)：{{ selSchool.features.gaokao }}</div>
                </div>

                <!-- 学校特色 -->
                <div v-if="selSchool.features_std || selSchool.features.style || (selSchool.features.tags && selSchool.features.tags.length)" class="dp-block">
                  <div class="dp-title">学校特色</div>
                  <div v-if="selSchool.features_std" class="dp-line">⭐ <span v-for="(tg, ti) in selSchool.features_std.tags" :key="ti" class="feat-chip">{{ tg }}</span><span v-if="selSchool.features_std.highlight" class="dp-muted"> · {{ selSchool.features_std.highlight }}</span></div>
                  <div v-else-if="selSchool.features.tags && selSchool.features.tags.length" class="dp-line">⭐ <span v-for="(tg, ti) in selSchool.features.tags" :key="ti" class="feat-chip">{{ tg }}</span></div>
                  <div v-if="selSchool.features.style" class="dp-line">🏫 {{ selSchool.features.style }}</div>
                </div>

                <!-- 校园生活 -->
                <div v-if="selSchool.campus_life" class="dp-block">
                  <div class="dp-title">🏫 校园生活 <span class="dp-muted">· 白皮书·机构汇编·待核</span></div>
                  <div v-if="selSchool.campus_life.class_system" class="dp-line dp-muted">🎒 班型：{{ selSchool.campus_life.class_system }}</div>
                  <div v-if="selSchool.campus_life.schedule" class="dp-line dp-muted">⏰ 作息：{{ selSchool.campus_life.schedule }}</div>
                  <div v-if="selSchool.campus_life.management" class="dp-line dp-muted">🧭 管理：{{ selSchool.campus_life.management }}</div>
                  <div v-if="selSchool.campus_life.activities" class="dp-line dp-muted">🎨 活动：{{ selSchool.campus_life.activities }}</div>
                  <div v-if="selSchool.campus_life.voices" class="dp-line dp-muted">💬 学生说：{{ selSchool.campus_life.voices }}</div>
                </div>
              </template>
              <div v-else class="dp-fallback">
                <div class="dp-head"><h3>{{ cleanName(selectedPoint.name) }}</h3></div>
                <div class="dp-sub">{{ selectedPoint.level || '民办 / 国际' }}</div>
                <p v-if="selectedPoint.reason" class="dp-line dp-muted">{{ selectedPoint.reason }}</p>
                <div v-if="selectedPoint.dist && selectedPoint.dist !== '距离未知' && selectedPoint.dist !== '—'" class="dp-line dp-muted">🚌 {{ selectedPoint.dist }}</div>
                <p class="dp-tip">📋 该校暂未收录结构化详情（学费 / 课程 / 方向 / 地址等）；已收录的民办 / 国际校见「🔎 查学校」筛民办 / 国际。</p>
              </div>
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
            <button class="ex-chip" :class="{ on: exBand === '保' }" @click="exBand = '保'">保</button>
            <button class="ex-chip" :class="{ on: exBand === '稳' }" @click="exBand = '稳'">稳</button>
            <button class="ex-chip" :class="{ on: exBand === '冲' }" @click="exBand = '冲'">冲</button>
          </div>
          <div class="ex-row">
            <span class="ex-k">特色</span>
            <button class="ex-chip" :class="{ on: exFeat === 'all' }" @click="exFeat = 'all'">全部</button>
            <button v-for="f in FEAT_TAGS" :key="f" class="ex-chip" :class="{ on: exFeat === f }" @click="exFeat = f">{{ f }}</button>
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
            <span class="ex-k ex-k2">排序</span>
            <button class="ex-chip" :class="{ on: exSort === 'default' }" @click="exSort = 'default'">默认</button>
            <button class="ex-chip" :class="{ on: exSort === 'va' }" @click="exSort = 'va'">🔥捡漏(增值)</button>
            <span class="ex-n">命中 {{ exploreView.length }} 所</span>
            <button v-if="compareSel.length" class="ex-cmpbtn" @click="showCompare = true">对比 {{ compareSel.length }} 所 →</button>
          </div>
          <JudgeLegend compact :rank="form.rank" />
        </div>
        <!-- 横向对比浮层 -->
        <div v-if="showCompare && compareSel.length" class="cmp-mask" @click.self="showCompare = false">
          <div class="cmp-box">
            <div class="cmp-head"><b>横向对比（{{ compareSel.length }} 所）</b><button class="cmp-x" @click="showCompare = false">✕</button></div>
            <div class="cmp-scroll">
              <table class="cmp-table">
                <tr><th>维度</th><th v-for="c in compareSel" :key="c.uid">{{ cleanName(c.name) }}<button class="cmp-rm" @click="toggleCompare(c)">移除</button></th></tr>
                <tr><td>类型</td><td v-for="c in compareSel" :key="c.uid">{{ c.type }}</td></tr>
                <tr><td>层次</td><td v-for="c in compareSel" :key="c.uid">{{ c.level || '—' }}</td></tr>
                <tr><td>档位(对你)</td><td v-for="c in compareSel" :key="c.uid"><span v-if="exBandOf(c)" class="t-band" :class="exBandOf(c)?.cls">{{ exBandOf(c)?.label }}</span><span v-else>—</span></td></tr>
                <tr><td>录取位次(25)</td><td v-for="c in compareSel" :key="c.uid">{{ c.line_trend ? c.line_trend.latest : '—' }}</td></tr>
                <tr><td>2026预估</td><td v-for="c in compareSel" :key="c.uid">{{ c.pred_2026 ? '≈' + c.pred_2026.rank : '—' }}<span v-if="c.line_trend && c.line_trend.volatile" class="addr-tag warn">波动</span></td></tr>
                <tr><td>高考U分</td><td v-for="c in compareSel" :key="c.uid">{{ c.gaokao && c.gaokao.score != null ? c.gaokao.score + ' ' + c.gaokao.tier : (c.gaokao ? c.gaokao.tier : '—') }}</td></tr>
                <tr><td>增值</td><td v-for="c in compareSel" :key="c.uid"><span v-if="c.value_added" :class="'va-' + c.value_added.label">{{ c.value_added.label }}</span><span v-else>—</span></td></tr>
                <tr><td>升学出口</td><td v-for="c in compareSel" :key="c.uid">{{ (c.extra && (c.extra.study_abroad || c.extra.exit_domestic || c.extra.exit_paths)) || '—' }}</td></tr>
                <tr><td>学费</td><td v-for="c in compareSel" :key="c.uid">{{ (c.extra && c.extra.tuition) || '—' }}</td></tr>
                <tr><td>通勤</td><td v-for="c in compareSel" :key="c.uid">{{ c.commute && c.commute.km != null ? c.commute.km + 'km' : '—' }}</td></tr>
                <tr><td>住宿</td><td v-for="c in compareSel" :key="c.uid">{{ c.boarding === true ? '✓' : '—' }}</td></tr>
                <tr><td>特色</td><td v-for="c in compareSel" :key="c.uid">{{ c.features_std ? (c.features_std.tags || []).join('·') : '—' }}</td></tr>
              </table>
            </div>
          </div>
        </div>
        <div class="ex-main">
          <div class="ex-listcol">
            <div class="table-scroll">
              <table class="list-table ex-table">
                <thead><tr><th>学校</th><th>类型</th><th>层次</th><th>档位</th><th>渠道</th><th>关键</th><th>通勤</th><th>住</th></tr></thead>
                <tbody>
                  <tr v-for="r in exploreView" :key="r.id || r.name" class="ex-tr" :class="{ on: selectedPoint && selectedPoint.name === r.name }" @click="exSelect(r)">
                    <td class="t-name"><input type="checkbox" class="cmp-cb" :checked="isCompared(r)" :disabled="!isCompared(r) && compareSel.length >= 4" @click.stop="toggleCompare(r)" title="加入对比(最多4所)" />{{ cleanName(r.name) }}<span v-if="r.type === '2026新校'" class="addr-tag warn">新</span><span v-if="r.value_added && r.value_added.label === '高增值'" class="addr-tag va-tag">捡漏</span></td>
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
          <div v-if="selectedPoint" class="dp-backdrop" @click="closeDetail"></div>
          <aside class="detail-panel" :class="{ 'dp-sheet': selectedPoint }">
            <button v-if="selectedPoint" class="dp-close" @click="closeDetail" aria-label="关闭">✕</button>
            <template v-if="selectedPoint">
              <template v-if="selSchool">
                <div class="dp-head">
                  <span class="dp-type">{{ selSchool.type }}{{ selSchool.level ? ' · ' + selSchool.level : '' }}</span>
                  <h3>{{ cleanName(selSchool.name) }}</h3>
                </div>
                <div v-if="selSchool.extra.coop" class="dp-sub">
                  <span class="bdg b-coop">🌐中外合作班</span>
                </div>

                <div v-if="selSchool.pred_2026" class="dp-block dp-pred">
                  <div class="dp-title">📍 2026 录取位次预估（核心依据）</div>
                  <div class="dp-line"><b class="dp-predv">≈{{ selSchool.pred_2026.rank }}</b> <span class="dp-muted">区间 {{ selSchool.pred_2026.lo }}–{{ selSchool.pred_2026.hi }}<template v-if="selSchool.pred_2026.pct"> · 约前{{ selSchool.pred_2026.pct }}%</template></span></div>
                  <div class="dp-line dp-muted">{{ selSchool.pred_2026.method === 'new_anchor' ? '新校锚定' : selSchool.pred_2026.method === 'tongchou_cy_equiv' ? '跨区位次映射(外区线→朝阳口径)' : selSchool.pred_2026.method === 'hist' ? ('以' + (selSchool.pred_2026.base_year || '最近年') + '录取位次为参考（非模型预测·网传/历史线）') : '百分位法' }} · 可信度 {{ selSchool.pred_2026.conf }} · 7/9出分接你的精确位次→7/13填报即用（各校实线录取后才有，填报当下靠此预测）</div>
                  <div v-if="selSchool.extra && selSchool.extra.cy_equiv" class="dp-line dp-muted">↑此为<b>走统筹门槛</b>(录取位次) · 学校档次≈朝阳第 {{ selSchool.extra.cy_equiv }} 位(线分→朝阳一分一段,全市可比)<span v-if="selSchool.extra.below_control"> · ⚠档次低于门槛,走统筹需≈460反不如统招,常不值</span></div>
                </div>

                <div class="dp-block">
                  <div class="dp-title">对你的研判<small class="dp-muted">（按2026预估位次）</small></div>
                  <div v-for="(v, ci) in channelViews" :key="ci" class="dp-ch">
                    <span class="dp-ch-name">{{ v.name }}</span>
                    <span class="tj" :class="v.cls">{{ v.band }}</span>
                    <span class="dp-ch-detail">{{ v.detail }}</span>
                  </div>
                  <p v-for="(c, idx) in panelCaveats" :key="idx" class="dp-tip">⚠️ {{ c }}</p>
                </div>

                <!-- 基本信息(前置) -->
                <div class="dp-block" v-if="selSchool.geo.address || selSchool.commute || selSchool.boarding != null || selSchool.extra.tuition || (selSchool.extra.curriculum && selSchool.extra.curriculum.length) || (selSchool.extra.specialties && selSchool.extra.specialties.length) || selSchool.extra.system || (selSchool.extra.analog && selSchool.extra.analog.length) || (selSchool.extra.campuses && selSchool.extra.campuses.length) || selSchool.extra.class_info">
                  <div class="dp-title">基本信息</div>
                  <div v-if="selSchool.geo.address" class="dp-line dp-muted">📍 {{ selSchool.geo.address }}<span v-if="selSchool.geo.confidence === 'low' || !selSchool.geo.lat" class="addr-tag">待核</span></div>
                  <div v-if="selSchool.commute" class="dp-line">🚌 到家 {{ selSchool.commute.km }}km · {{ selSchool.commute.mins }}分钟<span v-if="selSchool.commute.over_max" class="dp-vol">⚠️超上限</span></div>
                  <div class="dp-line">🛏 住宿：<span v-if="selSchool.boarding === true" class="t-yes">可住宿</span><span v-else-if="selSchool.boarding === false">不提供</span><span v-else class="dp-muted">待核</span><template v-if="selSchool.boarding === true && selSchool.campus_life && selSchool.campus_life.boarding_detail"> · <span class="dp-muted">{{ selSchool.campus_life.boarding_detail }}</span></template></div>
                  <div v-if="selSchool.commute && selSchool.commute.over_max && selSchool.boarding === false" class="dp-line dp-vol">⚠️ 家远且不住宿，通勤超上限，慎报</div>
                  <div v-if="selSchool.campus_life && selSchool.campus_life.dining" class="dp-line">🍚 食堂：{{ selSchool.campus_life.dining }}</div>
                  <div v-if="selSchool.extra.tuition" class="dp-line">💰 学费：{{ selSchool.extra.tuition }}</div>
                  <div v-if="selSchool.extra.curriculum && selSchool.extra.curriculum.length" class="dp-line">📚 课程：{{ selSchool.extra.curriculum.join('·') }}<template v-if="selSchool.extra.direction"> · {{ selSchool.extra.direction }}</template></div>
                  <div v-if="selSchool.extra.direction && !(selSchool.extra.curriculum && selSchool.extra.curriculum.length)" class="dp-line dp-muted">方向：{{ selSchool.extra.direction }}</div>
                  <div v-if="selSchool.extra.specialties && selSchool.extra.specialties.length" class="dp-line">🛠 专业：{{ selSchool.extra.specialties.join('·') }}</div>
                  <div v-if="selSchool.extra.system" class="dp-line">🏛 体系：{{ selSchool.extra.system }}</div>
                  <div v-if="selSchool.extra.analog && selSchool.extra.analog.length" class="dp-line dp-muted">↔ 可类比：{{ selSchool.extra.analog.join('、') }}</div>
                  <div v-if="selSchool.extra.campuses && selSchool.extra.campuses.length" class="dp-line dp-muted">🏫 校区：{{ selSchool.extra.campuses.join(' / ') }}</div>
                  <div v-if="selSchool.extra.class_info" class="dp-line dp-muted">👥 {{ selSchool.extra.class_info }}<template v-if="selSchool.extra.enroll_2025"> · 2025招{{ selSchool.extra.enroll_2025 }}人</template></div>
                </div>

                <!-- 贯通项目 -->
                <div v-if="selSchool.extra.projects && selSchool.extra.projects.length" class="dp-block">
                  <div class="dp-title">贯通项目（→本科）</div>
                  <div v-for="(pj, pi) in selSchool.extra.projects" :key="pi" class="dp-mj">{{ pj.type }}：{{ pj.major }} → {{ pj.benke }}<em v-if="pj.plan"> · {{ pj.plan }}人</em></div>
                  <div v-if="selSchool.extra.projects[0].threshold" class="dp-line dp-muted">🎯 门槛：中考≥{{ selSchool.extra.projects[0].threshold }}分 · 学制{{ selSchool.extra.projects[0].years }}年 · 京籍应届 · 提前批</div>
                  <template v-for="(tm, tk) in (selSchool.extra.type_meta || {})" :key="tk"><div v-if="tm" class="dp-line dp-muted">🔁 {{ tk }}：{{ tm.transfer }}；{{ tm.tuition }}</div></template>
                </div>

                <!-- 录取数据 -->
                <div v-if="schoolLines.length || selSchool.line_trend || selSchool.extra.voc_line_note || (selSchool.extra.line_note && (selSchool.extra.in_minban || selSchool.extra.in_intl))" class="dp-block">
                  <div class="dp-title">录取数据</div>
                  <table v-if="schoolLines.length" class="dp-table">
                    <thead><tr><th>年</th><th>线</th><th>口径/区排</th></tr></thead>
                    <tbody>
                      <tr v-for="sl in schoolLines" :key="sl.year">
                        <td>{{ sl.year }}</td>
                        <td>{{ sl.score != null ? sl.score + (sl.scale ? '(' + sl.scale + '制)' : '分') : '—' }}</td>
                        <td>{{ sl.rank != null ? sl.rank + '名' : (sl.conf || '') }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <div v-if="selSchool.line_trend" class="dp-line">📈 录取位次(区)：{{ selSchool.line_trend.ranks['2023'] || '—' }} → {{ selSchool.line_trend.ranks['2024'] || '—' }} → <b>{{ selSchool.line_trend.ranks['2025'] || '—' }}</b><span class="dp-muted">（23/24/25 历史）</span><span v-if="selSchool.line_trend.volatile" class="addr-tag">波动大</span></div>
                  <div v-if="selSchool.extra.voc_line_note" class="dp-line dp-muted">📈 录取线：{{ selSchool.extra.voc_line_note }}</div>
                  <div v-if="selSchool.extra.line_note && (selSchool.extra.in_minban || selSchool.extra.in_intl)" class="dp-line dp-muted">📈 录取：{{ selSchool.extra.line_note }}</div>
                  <p v-if="schoolLines.length" class="dp-tip">分数跨年口径不同(2025起510制)；同年/区排名才可比。</p>
                </div>

                <!-- 招生计划(统招专业/班 名额) -->
                <div v-if="selMajors.length" class="dp-block">
                  <div class="dp-title">招生计划 <small class="dp-muted">· 朝阳·2026官方简章</small></div>
                  <div v-for="(m, mi) in selMajors" :key="mi" class="dp-mj">{{ cleanName(m.major_name) }}<em> · 本区 {{ planNum(m.plan_chaoyang) }}<template v-if="m.plan_total != null && String(m.plan_total) !== String(m.plan_chaoyang)"> · 全市 {{ planNum(m.plan_total) }}</template></em></div>
                  <p class="dp-tip">2026 计划数（派生自《2026 北京中招大报纸》官方招生简章，逐校精读）。</p>
                </div>

                <!-- 出口质量 -->
                <div v-if="selSchool.gaokao || selSchool.value_added || selSchool.extra.study_abroad || selSchool.extra.exit_domestic || selSchool.extra.exit_type || selSchool.extra.comp_high_note || selSchool.extra.exit_paths || selSchool.features.gaokao" class="dp-block">
                  <div class="dp-title">出口质量</div>
                  <div v-if="selSchool.extra.study_abroad" class="dp-line">🎓 留学走向：{{ selSchool.extra.study_abroad }}</div>
                  <div v-else-if="selSchool.extra.exit_domestic" class="dp-line">🎓 高考出口：{{ selSchool.extra.exit_domestic }}</div>
                  <div v-else-if="selSchool.extra.exit_type === '暂无毕业生'" class="dp-line dp-muted">🎓 新建高中部·首届未毕业，暂无升学出口</div>
                  <div v-else-if="selSchool.extra.exit_type === '未公布'" class="dp-line dp-muted">🎓 升学出口：学校未公布</div>
                  <div v-if="selSchool.extra.comp_high_note" class="dp-line">🎓 综合高中班：{{ selSchool.extra.comp_high_note }}</div>
                  <div v-if="selSchool.extra.exit_paths" class="dp-line">🚀 升学路径：{{ selSchool.extra.exit_paths }}</div>
                  <div v-if="selSchool.gaokao && selSchool.gaokao.score != null" class="dp-line">🎓 高考评分 <b>{{ selSchool.gaokao.score }}</b>/100 · {{ selSchool.gaokao.tier }}
                    <span class="dp-muted">（{{ selSchool.gaokao.yiben != null ? '一本' + Math.round(selSchool.gaokao.yiben * 100) + '%' : (selSchool.gaokao.yiben_est != null ? '一本≈' + Math.round(selSchool.gaokao.yiben_est * 100) + '%(估)' : '') }}{{ selSchool.gaokao.qingbei ? ' 清北' + selSchool.gaokao.qingbei : '' }} · {{ selSchool.gaokao.confidence === 'very_low' ? '估算·待核' : selSchool.gaokao.confidence === 'low' ? '民间·低置信' : '民间·中置信' }}）</span></div>
                  <div v-else-if="selSchool.gaokao" class="dp-line dp-muted">🎓 高考 新建高中部·首届未毕业,暂无出口数据（入口位次可参考）</div>
                  <div v-if="selSchool.value_added" class="dp-line">📊 增值：<b :class="'va-' + selSchool.value_added.label">{{ selSchool.value_added.label }}</b><span class="dp-muted"> · {{ selSchool.value_added.basis }}</span></div>
                  <div v-if="selSchool.features.gaokao" class="dp-line dp-muted">🎓 高考(民间·非官方)：{{ selSchool.features.gaokao }}</div>
                </div>

                <!-- 学校特色 -->
                <div v-if="selSchool.features_std || selSchool.features.style || (selSchool.features.tags && selSchool.features.tags.length)" class="dp-block">
                  <div class="dp-title">学校特色</div>
                  <div v-if="selSchool.features_std" class="dp-line">⭐ <span v-for="(tg, ti) in selSchool.features_std.tags" :key="ti" class="feat-chip">{{ tg }}</span><span v-if="selSchool.features_std.highlight" class="dp-muted"> · {{ selSchool.features_std.highlight }}</span></div>
                  <div v-else-if="selSchool.features.tags && selSchool.features.tags.length" class="dp-line">⭐ <span v-for="(tg, ti) in selSchool.features.tags" :key="ti" class="feat-chip">{{ tg }}</span></div>
                  <div v-if="selSchool.features.style" class="dp-line">🏫 {{ selSchool.features.style }}</div>
                </div>

                <!-- 校园生活 -->
                <div v-if="selSchool.campus_life" class="dp-block">
                  <div class="dp-title">🏫 校园生活 <span class="dp-muted">· 白皮书·机构汇编·待核</span></div>
                  <div v-if="selSchool.campus_life.class_system" class="dp-line dp-muted">🎒 班型：{{ selSchool.campus_life.class_system }}</div>
                  <div v-if="selSchool.campus_life.schedule" class="dp-line dp-muted">⏰ 作息：{{ selSchool.campus_life.schedule }}</div>
                  <div v-if="selSchool.campus_life.management" class="dp-line dp-muted">🧭 管理：{{ selSchool.campus_life.management }}</div>
                  <div v-if="selSchool.campus_life.activities" class="dp-line dp-muted">🎨 活动：{{ selSchool.campus_life.activities }}</div>
                  <div v-if="selSchool.campus_life.voices" class="dp-line dp-muted">💬 学生说：{{ selSchool.campus_life.voices }}</div>
                </div>
              </template>
              <div v-else class="dp-fallback">
                <div class="dp-head"><h3>{{ cleanName(selectedPoint.name) }}</h3></div>
                <div class="dp-sub">{{ selectedPoint.level || '民办 / 国际' }}</div>
                <p v-if="selectedPoint.reason" class="dp-line dp-muted">{{ selectedPoint.reason }}</p>
                <div v-if="selectedPoint.dist && selectedPoint.dist !== '距离未知' && selectedPoint.dist !== '—'" class="dp-line dp-muted">🚌 {{ selectedPoint.dist }}</div>
                <p class="dp-tip">📋 该校暂未收录结构化详情（学费 / 课程 / 方向 / 地址等）；已收录的民办 / 国际校见「🔎 查学校」筛民办 / 国际。</p>
              </div>
            </template>
            <div v-else class="dp-empty">
              <div class="dp-empty-ic">🏫</div>
              点击地图上的学校查看详细信息
            </div>
          </aside>
        </div>
      </div>
      <!-- 渠道科普：科普总览 + 校额到校 + 市级统筹（数据工具内嵌） -->
      <div class="chwrap chwrap2" v-show="tab === 'channels'">
        <!-- ① 三批次流程 -->
        <div class="ch-hero">
          <div class="chh-flow">
            <span class="chh-step">① 提前招生</span><span class="chh-lock">🔒</span>
            <span class="chh-step">② 指标分配</span><span class="chh-lock">🔒</span>
            <span class="chh-step on">③ 统一招生</span>
          </div>
          <p class="chh-note">三批次<b>顺序录取，被前一批次录取即锁定、后批作废</b>。总分 <b>510</b>（2025 改革）。下面是各升学渠道与官方入口。</p>
        </div>

        <!-- 身份自查 -->
        <div class="ch-id">
          <span class="ci-t">按身份看可报</span>
          <button v-for="x in IDENTITIES" :key="x.v" class="ci-b" :class="{ on: chId === x.v }" @click="chId = x.v">{{ x.label }}</button>
          <span class="ci-hint">点身份 → 下方卡片高亮你能报的渠道</span>
        </div>

        <!-- ② 六大渠道卡 -->
        <div class="ch-cards">
          <div v-for="c in CHANNELS" :key="c.key" class="cc" :class="{ dim: !chEligible(c), open: openCh === c.key }">
            <button class="cc-h" type="button" @click="openCh = openCh === c.key ? null : c.key">
              <span class="cc-ic">{{ c.icon }}</span>
              <span class="cc-nm">{{ c.name }}</span>
              <span v-if="!chEligible(c)" class="cc-no">该身份不可报</span>
              <span class="cc-chev">{{ openCh === c.key ? '−' : '+' }}</span>
            </button>
            <div class="cc-one">{{ c.one }}</div>
            <div class="cc-meta"><span class="cc-k">门槛</span>{{ c.threshold }}</div>
            <div v-show="openCh === c.key" class="cc-body">
              <ul><li v-for="(d, di) in c.detail" :key="di">{{ d }}</li></ul>
            </div>
            <div class="cc-acts">
              <a class="cc-link" :href="c.link" target="_blank" rel="noopener">{{ c.linkName }} ↗</a>
            </div>
          </div>
        </div>

        <!-- ④ 关键规则速记 -->
        <div class="ch-rules">
          <div class="cr"><b>平行志愿</b>：冲在前零成本，冲不上自动落到稳/保</div>
          <div class="cr"><b>批次锁定</b>：② 别填"统招本可达"的校，会锁低</div>
          <div class="cr"><b>必有保底</b>：志愿末位放一所一定能上的</div>
          <div class="cr"><b>总分 510</b>：2025 改革口径（2024 是 670）</div>
        </div>

        <!-- ④' 填报避坑 -->
        <div class="ch-sec-t">⚠️ 填报避坑<small>（家长高频踩坑 → 正解）</small></div>
        <div class="ch-pitfalls">
          <div v-for="(p, pi) in PITFALLS" :key="pi" class="pf">
            <div class="pf-bad"><span class="pf-x">❌</span>{{ p.bad }}</div>
            <div class="pf-good"><span class="pf-ok">✅</span>{{ p.good }}</div>
          </div>
        </div>

        <!-- ⑤ 官方权威入口 -->
        <div class="ch-sec-t">🔗 官方权威发布<small>（点击前往官网核对最新原文）</small></div>
        <div class="ch-official">
          <a v-for="o in OFFICIAL" :key="o.url" class="of" :href="o.url" target="_blank" rel="noopener">
            <span class="of-top"><span class="of-badge">官方</span><span class="of-nm">{{ o.name }}</span><span class="of-arr">↗</span></span>
            <span class="of-desc">{{ o.desc }}</span>
          </a>
        </div>

        <!-- ⑥ 时间线 -->
        <div class="ch-sec-t">🗓 2026 关键节点<small>（具体以官方简章为准）</small></div>
        <div class="ch-timeline">
          <div v-for="(t, ti) in TIMELINE" :key="ti" class="tl"><span class="tl-t">{{ t.t }}</span><span class="tl-d">{{ t.d }}</span></div>
        </div>

        <p class="ch-foot">本页为政策科普；学校数据见「🔎 查学校」，志愿填报见「📝 志愿草表」。规则口径以 bjeea 当年正式简章为准。</p>
      </div><!-- /chwrap 渠道科普 -->

      <!-- TAB 8：志愿草表 v2（三批次 · 2026 口径）-->
      <div class="draftwrap" v-show="tab === 'draft'">
        <p class="draft-note">
          三批次按 <b>①提前招生 → ②指标分配 → ③统一招生</b> 顺序录取，<b>被前一批次录取即锁定，后批次作废</b>。
          下表镜像官方网报，<b>2026 口径</b>（贯通已并入统招）；志愿数/代码以当年官方网报系统为准。
        </p>
        <p v-if="identityNote" class="board-note">⚠️ {{ identityNote }}</p>

        <!-- 填报三铁律(始终可见) -->
        <div class="rules-strip">
          <span class="rs-t">填报铁律</span>
          <span class="rs-i" :class="{ bad: xedSummary.cnt.waste > 0 }">① ②指标分配不锁低{{ xedSummary.cnt.waste > 0 ? '（有'+xedSummary.cnt.waste+'所统招本可达，建议移除）' : '✓' }}</span>
          <span class="rs-i">② 冲在前·零成本（平行志愿）</span>
          <span class="rs-i" :class="{ bad: uniSummary.noSafety }">③ 统招末位必有铁保底{{ uniSummary.noSafety ? '（当前无保底！）' : '✓' }}</span>
          <button class="rs-copy" type="button" @click="copyDraft">{{ copyOk ? '✅ 已复制' : '📋 复制草表' }}</button>
        </div>

        <!-- 低位次专属方案:统招进不了公办时,把非统招路径按优先级摆出来 -->
        <section v-if="uniSummary.noSafety" class="lowplan">
          <div class="lp-head">🧭 低位次升学方案
            <span class="lp-sub">你的区位次 ≈ {{ form.rank }}<template v-if="rankPct">（约后 {{ rankPct }}%·朝阳约 1.2 万考生·估）</template>，<template v-if="publicFloorRank">低于公办统招最低线(≈{{ publicFloorRank }} 位)</template>，统招批难录取。以下按优先级给出非统招路径：</span>
          </div>
          <ol class="lp-list">
            <li><b>🎯 校额到校（最该争取·公办）</b>：名额按<b>你的初中</b>分配、只过普高线(远低于统招线)，校内排名靠前即可进好公办——中低位次最大逆袭通道。
              <a class="lnk" @click="batchOpen.ind = true">→ 看「② 指标分配」</a></li>
            <li><b>🌆 市级统筹（公办·外区）</b>：同属指标分配批、统招前录取，线更低；多为外区远校需配合住宿。
              <a class="lnk" @click="batchOpen.ind = true">→ 看「② 指标分配」</a></li>
            <li><b>🎓 贯通培养（≥380分·7年到本科·京籍·中职段免学费）</b>：朝阳可报 {{ lowPlan.gt }} 个项目。
              <a class="lnk" @click="exType = '贯通'; goTab('explore')">→ 查学校筛「贯通」</a></li>
            <li><b>🏫 中职·综合高中班（门槛最低·办普高学籍可高考·保底）</b>：<template v-if="lowPlan.voc.length">{{ lowPlan.voc.join(' / ') }}（劲松线≈区9485，{{ form.rank }}可进）</template>
              <a class="lnk" @click="exType = '中职'; goTab('explore')">→ 查学校筛「中职」</a></li>
            <li><b>💰 民办普高（留京高考·学费亲民）</b>：<template v-if="lowPlan.priv.length">{{ lowPlan.priv.join('、') }}</template>；出国路线见国际校(学费15-33万)。
              <a class="lnk" @click="exType = '民办'; goTab('explore')">→ 查学校筛「民办」</a></li>
          </ol>
          <p class="lp-foot">⚠️ 校额到校 / 市级统筹 / 贯通 需<b>京籍应届</b>；民办 / 中职无此限制。具体名额与门槛以当年官方简章为准。</p>
        </section>

        <!-- 批次① 提前招生（说明，不代填） -->
        <section class="batch">
          <button class="batch-h" type="button" @click="batchOpen.early = !batchOpen.early">
            <span class="bc">{{ batchOpen.early ? '▾' : '▸' }}</span>① 提前招生
            <small>特长生 / 中职自主 / 登记入学等——需到各校自行报名，本系统不代填</small>
          </button>
          <div v-show="batchOpen.early" class="batch-note">
            <p>提前招生包含 <b>体育/艺术/科技特长生</b>、<b>中职自主招生</b>、<b>登记入学</b>、部分校的<b>校园开放日/face-to-face</b> 等。这些渠道各校自定标准、<b>无官方统一的学校/专业结构化代码</b>，报名也走各校自己的入口（简章公布的时间、材料、加试各不相同）。</p>
            <p>因此本系统<b>不在此代填</b>。如有目标，请按<b>目标校当年招生简章</b>的提前招生说明，自行在对应渠道报名。</p>
            <p class="bn-foot">📌 2026 起<b>贯通培养、中外合作</b>均按<b>统一招生（批次③）</b>录取，不在提前招生批。</p>
          </div>
        </section>

        <!-- 批次② 指标分配 -->
        <section class="batch">
          <button class="batch-h" type="button" @click="batchOpen.ind = !batchOpen.ind">
            <span class="bc">{{ batchOpen.ind ? '▾' : '▸' }}</span>② 指标分配（校额到校 + 市级统筹）
            <small>校额+统筹共用 8 志愿 · 门槛 总分≥430 + 综合素质B + 同一初中连续三年学籍</small>
          </button>
          <template v-if="batchOpen.ind && canIndicator">
            <!-- 校额到校 + 市级统筹 合并：指标分配批共 8 志愿，按顺序录取、录取即锁定 -->
            <div v-if="indicatorRows.length" class="uni-summary">
              <div class="us-line"><b>{{ indicatorSummary.shown }}/8 志愿</b>
                <span class="us-b band-冲">校额 {{ indicatorSummary.xed }}</span>
                <span class="us-b band-稳">统筹 {{ indicatorSummary.tc }}</span>
              </div>
              <p v-if="indicatorSummary.over" class="us-warn">⚠️ 校额 + 统筹<b>共用 8 个志愿</b>：你的"值得"候选超过 8，已<b>按"同档校额优先"取前 8</b>（其余可在「查学校」手动权衡）。</p>
              <button class="note-toggle" type="button" @click="noteOpen.tc = !noteOpen.tc">{{ noteOpen.tc ? '▾' : '▸' }} 录取规则与口径</button>
              <div v-show="noteOpen.tc" class="note-body">官方2026：<b>校额到校 + 市级统筹合用「指标分配批」，共 8 个志愿</b>，提招后、统招前，<b>按你填的志愿顺序</b>从高分到低分录取、<b>录取即锁定</b>（锁定后不再进统招）。本表已把两类<b>混排成一列</b>：只选<b>值得</b>（统招够不上的 upgrade）、<b>同档校额优先于统筹</b>（校额比校内排名、本区近校、无住宿；统筹外区远校＋住宿＋名额少）；"统招本可达/相当"不选入（避免锁进同级或更低校）。校额按<b>本初中校内排名</b>录取、无官方各校线；统筹配额 2026 与 2025 一致。均以官方网报为准。机制见「<a class="lnk" @click="goTab('channels')">渠道科普</a>」。</div>
            </div>
            <div v-if="indicatorRows.length" class="uni-list">
              <DraftRow v-for="r in indicatorRows" :key="r.seq" v-bind="r" />
            </div>
            <p v-else-if="xedEligible.length || tcEligible.length" class="us-tip" style="margin:6px 0">
              你这个位次<b>暂无"既够得着又值得"的指标分配志愿</b>：校额/统筹里够得着的多为平级/远郊校、值得的门槛又够不上。<b>建议指标分配批不填，重心放在朝阳统招。</b>完整名单见「<a class="lnk" @click="goTab('explore')">🔎 查学校</a>」。
            </p>
            <p v-else class="xed-src">先在<b>首页填初中学校</b>，这里才能按名额生成指标分配志愿。</p>
            <JudgeLegend v-if="tcEligible.length" :rank="form.rank" />
          </template>
          <p v-else-if="batchOpen.ind && !canIndicator" class="xed-note warn">当前「{{ (IDENTITIES.find(x => x.v === form.identity) || {}).label }}」身份不可报指标分配（校额到校 / 市级统筹）。</p>
        </section>

        <!-- 批次③ 统一招生 -->
        <section class="batch">
          <button class="batch-h" type="button" @click="batchOpen.uni = !batchOpen.uni">
            <span class="bc">{{ batchOpen.uni ? '▾' : '▸' }}</span>③ 统一招生
            <small>全渠道：公办+民办+中职综高+(2026)贯通；{{ ZHIYUAN_SLOTS }} 志愿，位次越低非公办占越多，预填 {{ filledSlots }}/{{ ZHIYUAN_SLOTS }}</small>
          </button>
          <template v-if="batchOpen.uni && canPuhao">
            <div class="uni-summary">
              <div class="us-line">
                <b>{{ uniSummary.filled }} 志愿</b>
                <span v-if="uniSummary.cnt['刺']" class="us-b band-刺">{{ uniSummary.cnt['刺'] }} 冲刺</span>
                <span v-if="uniSummary.cnt['冲']" class="us-b band-冲">{{ uniSummary.cnt['冲'] }} 冲</span>
                <span v-if="uniSummary.cnt['稳']" class="us-b band-稳">{{ uniSummary.cnt['稳'] }} 稳</span>
                <span v-if="uniSummary.cnt['保']" class="us-b band-保">{{ uniSummary.cnt['保'] }} 公办保</span>
                <span v-if="uniSummary.cnt['贯通']" class="us-b band-稳">{{ uniSummary.cnt['贯通'] }} 贯通</span>
                <span v-if="uniSummary.cnt['民办']" class="us-b band-保">{{ uniSummary.cnt['民办'] }} 民办</span>
                <span v-if="uniSummary.cnt['中职']" class="us-b band-保">{{ uniSummary.cnt['中职'] }} 中职保底</span>
                <span v-if="uniSummary.lastName && !uniSummary.noSafety" class="us-bottom">末位保底＝<b>{{ cleanName(uniSummary.lastName) }}</b></span>
              </div>
              <p v-if="uniSummary.noSafety" class="us-warn">⚠️ <b>无稳妥保底</b>：你的区位次低于所列各校近年录取线，{{ uniSummary.allReach ? '12 个志愿全是冲刺/冲' : '没有"保"档' }}，落榜风险高。建议：①放宽「通勤上限」纳入更多学校；②用<b>民办 / 中职 / 贯通</b>做保底；③核实你的位次是否偏低。</p>
              <button class="note-toggle" type="button" @click="noteOpen.uni = !noteOpen.uni">{{ noteOpen.uni ? '▾' : '▸' }} 录取规则与口径</button>
              <div v-show="noteOpen.uni" class="note-body">候选受<b>通勤上限约束</b>：{{ form.max_km }}km 内可报公办约 <b>{{ uniSummary.reachPool }}</b> 所<template v-if="uniSummary.reachPool <= 12">，已全部纳入</template><template v-else>，按录取位次取 12 所填满</template>——改位次主要改变"冲/稳/保"判定，要换一批候选请调通勤上限。按总分从高到低、平行志愿录取，冲在前、保在后；每校已自动选 2 个推荐专业(班)，最终以官方网报为准。</div>
            </div>
            <div class="uni-list">
              <DraftRow v-for="r in uniRows" :key="r.seq" v-bind="r" />
            </div>
          </template>
          <p v-else class="xed-note warn">非京籍随迁子女不能报普通高中统招（只能报中职类）；上方仅供了解。</p>
        </section>

        <p v-if="result.admission_source" class="src">数据来源：{{ result.admission_source }}（统招）。本页为<b>只读草表</b>，由规则引擎按你的位次/通勤/身份自动生成；三批次为 2026 口径推断，专业(班)代码与最终志愿一切以当年官方网报系统与简章为准。</p>

        <!-- AI 深度分析（独立区块·看完免费草表后再按需启用） -->
        <section class="ai-section">
          <div class="ai-sec-head">
            <h3>🤖 AI 深度分析 <small>测试版·暂免费</small></h3>
            <p class="ai-sec-intro">上面是<b>免费规则推荐</b>的志愿草表。如果还想要一份<b>更懂你家</b>的深度方案——结合孩子画像逐条权衡（通勤 vs 层次、强弱科匹配、发挥稳定性）、情形预演（超常/失常怎么调）、跨批次配合，可启用 AI 深度分析。</p>
          </div>

          <!-- 第一步：入口（未启用） -->
          <button v-if="!aiStarted && !aiReportHtml" class="ai-btn ai-cta" @click="aiStarted = true">
            🤖 启用 AI 深度分析（测试·暂免费）
          </button>

          <!-- 第二步：启用后 → 完善画像（可选）+ 生成 -->
          <template v-if="aiStarted || aiReportHtml">
            <div class="pq-card">
              <div class="pq-title">🧒 完善孩子画像 <small>可选·让 AI 更懂你家，留空也能生成</small></div>
              <div class="pq-body">
                <div class="pq-row">
                  <label>文理倾向</label>
                  <select v-model="form.wenli"><option value="">不填</option><option>偏文</option><option>偏理</option><option>均衡</option></select>
                </div>
                <div class="pq-multi">
                  <label>强科 <small>(多选)</small></label>
                  <div class="chips"><button v-for="s in SUBJECTS" :key="'st'+s" type="button" class="pchip" :class="{ on: form.strong.includes(s) }" @click="toggleArr(form.strong, s)">{{ s }}</button></div>
                </div>
                <div class="pq-multi">
                  <label>弱科 <small>(多选)</small></label>
                  <div class="chips"><button v-for="s in SUBJECTS" :key="'wk'+s" type="button" class="pchip" :class="{ on: form.weak.includes(s) }" @click="toggleArr(form.weak, s)">{{ s }}</button></div>
                </div>
                <div class="pq-row">
                  <label>发挥稳定性</label>
                  <select v-model="form.stability"><option value="">不填</option><option>稳定</option><option>偶有起伏</option><option>起伏较大</option></select>
                </div>
                <div class="pq-row">
                  <label>学习自驱</label>
                  <select v-model="form.drive"><option value="">不填</option><option>自驱强</option><option>一般</option><option>需要盯</option></select>
                </div>
                <div class="pq-row">
                  <label>适应环境</label>
                  <select v-model="form.adapt"><option value="">不填</option><option>能扛高竞争强校</option><option>偏好节奏平稳</option><option>不确定</option></select>
                </div>
                <div class="pq-multi">
                  <label>特长 <small>(多选)</small></label>
                  <div class="chips"><button v-for="t in TALENTS" :key="'tl'+t" type="button" class="pchip" :class="{ on: form.talent.includes(t) }" @click="toggleArr(form.talent, t)">{{ t }}</button></div>
                </div>
                <div class="pq-multi">
                  <label>家庭最看重 <small>(选≤2)</small></label>
                  <div class="chips"><button v-for="v in VALUES" :key="'vl'+v" type="button" class="pchip" :class="{ on: form.valued.includes(v) }" @click="toggleArr(form.valued, v, 2)">{{ v }}</button></div>
                </div>
                <div class="pq-row">
                  <label>中考目标</label>
                  <input v-model="form.target" class="pq-input" placeholder="目标分或心仪校,如 510 或 八十中" />
                </div>
                <div class="pq-row">
                  <label>学费预算</label>
                  <input v-model="form.budget" class="pq-input" placeholder="民办/国际才需,如 ≤15 万/年" />
                </div>
              </div>
            </div>
            <div class="ai-gen-row">
              <button class="ai-btn" :disabled="aiLoading" @click="genAiReport">
                {{ aiLoading ? '🤖 AI 分析中…(约30秒)' : (aiReportHtml ? '🔄 重新生成' : '🚀 生成 AI 深度分析报告') }}
              </button>
            </div>
            <p v-if="aiErr" class="err">{{ aiErr }}</p>
            <div v-if="aiReportHtml" class="ai-report">
              <div class="ai-report-head">🤖 AI 深度分析报告 <small>测试版·基于规则草表改良·仅参考,数据以官方简章为准</small></div>
              <div class="ai-report-body" v-html="aiReportHtml"></div>
            </div>
          </template>
        </section>
      </div>
    </section>
    </template>

    <!-- 其余 15 区:校库浏览(学校+专业+位置,暂无录取线) -->
    <DistrictBrowse v-else :py="curDistrict" :cn="districtCn" />
  </div>
</template>

<style scoped>
.page { max-width: 1180px; margin: 0 auto; padding: 16px; background: var(--bg); min-height: 100%; }
.hero h1 { font-size: 20px; color: var(--brand-deeper); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dist-sel { font-size: 14px; font-weight: 600; color: var(--brand-dark); background: var(--brand-50);
  border: 1px solid var(--brand-100, #dbe4ff); border-radius: var(--radius-xs); padding: 3px 8px; cursor: pointer; }
.hero .sub { color: var(--gray-600); font-size: 13px; margin-top: 4px; }
/* 标题与账号头像同一行:标题靠左,头像靠右 */
.hero-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
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

/* 输入区：现代化网格布局 —— 12 列对齐、柔边圆角、焦点高亮环；紧凑 */
.form.card { padding: 12px 14px; }
.form.card.collapsed { padding: 0; }
.form .fields { display: grid; grid-template-columns: repeat(12, 1fr); gap: 9px 12px; align-items: end; }
.fld { display: flex; flex-wrap: wrap; align-items: baseline; column-gap: 5px; row-gap: 4px;
  font-size: 11.5px; font-weight: 600; color: var(--gray-600); }
.fld small { font-weight: 400; color: var(--gray-400); }
/* 标注(<small>)与标签同行；输入控件强制换到下一行、占满整宽 */
.fld > input, .fld > select, .fld > .switch { flex: 0 0 100%; }
/* 折叠摘要条 */
.form-bar { display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 14px;
  background: none; border: none; cursor: pointer; text-align: left; font: inherit; }
.form-bar .fb-ic { width: 16px; height: 16px; color: var(--brand); flex-shrink: 0; }
.fb-sum { flex: 1; min-width: 0; font-size: 13px; font-weight: 600; color: var(--gray-800);
  white-space: normal; line-height: 1.55; }
.fb-dirty { font-size: 11.5px; font-weight: 600; color: #b45309; background: var(--warning-bg);
  padding: 2px 8px; border-radius: var(--radius-full); white-space: nowrap; }
.fb-edit { margin-left: auto; flex-shrink: 0; font-size: 12px; font-weight: 600; color: var(--brand);
  background: none; border: none; cursor: pointer; padding: 2px 4px; }
.form-collapse { text-align: right; margin-top: 8px; }
/* 分组标题：整行占满，分隔三个语义组 */
.fgrp-title { grid-column: 1 / -1; font-size: 11.5px; font-weight: 700; color: var(--gray-500);
  letter-spacing: .03em; margin: 4px 0 -2px; padding-bottom: 4px; border-bottom: 1px solid var(--gray-100);
  display: flex; align-items: baseline; gap: 8px; }
.fgrp-title small { font-weight: 400; color: var(--gray-400); letter-spacing: 0; }
.fgrp-title:first-child { margin-top: 0; }
.fld-id { grid-column: span 2; }
.fld-rank { grid-column: span 2; }
.fld-jr { grid-column: span 4; }
.fld-xrank { grid-column: span 2; }
.fld-farb { grid-column: span 2; }
.fld-home { grid-column: span 4; }
.fld-mode { grid-column: span 3; }
.fld-km { grid-column: span 2; }
.fld-board { grid-column: span 7; }
.fld-risk { grid-column: span 4; }
.fld-orient { grid-column: span 4; }
.fld-nonpub { grid-column: span 4; }
.fld-go { grid-column: 1 / -1; justify-content: flex-end; }
.fld-go .go { width: auto; min-width: 240px; padding: 0 30px; }
.form input:not([type=checkbox]), .form select { width: 100%; box-sizing: border-box; height: 34px; padding: 0 11px;
  border: 1px solid var(--gray-200); border-radius: 8px; font-size: 13px; color: var(--gray-900);
  background: var(--gray-50); transition: border-color .15s, box-shadow .15s, background .15s; -webkit-appearance: none; appearance: none; }
.form select { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 11px center; padding-right: 30px; cursor: pointer; }
.form input::placeholder { color: var(--gray-400); }
.form input:focus, .form select:focus { outline: none; border-color: var(--brand); background: #fff;
  box-shadow: 0 0 0 3px var(--brand-50); }
.form input:disabled { background: var(--gray-100); color: var(--gray-400); }
/* iOS 风格住宿开关 */
.fld-board .switch { display: flex; align-items: center; gap: 9px; height: 34px; cursor: pointer; font-weight: 400; }
.sw-input { position: absolute; opacity: 0; width: 0; height: 0; }
.sw-track { flex-shrink: 0; width: 38px; height: 22px; background: var(--gray-300); border-radius: 999px;
  position: relative; transition: background .2s; }
.sw-thumb { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; background: #fff;
  border-radius: 50%; box-shadow: 0 1px 3px rgba(0, 0, 0, .25); transition: transform .2s; }
.sw-input:checked + .sw-track { background: var(--brand); }
.sw-input:checked + .sw-track .sw-thumb { transform: translateX(16px); }
.sw-input:focus-visible + .sw-track { box-shadow: 0 0 0 3px var(--brand-50); }
.sw-txt { font-size: 12px; color: var(--gray-600); }
.go { width: 100%; height: 34px; display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  background: var(--brand); color: #fff; border: none; border-radius: 10px; font-size: 14px; font-weight: 600;
  white-space: nowrap; cursor: pointer; box-shadow: 0 1px 2px rgba(37, 99, 235, .25);
  transition: background .15s, box-shadow .15s, transform .05s; }
.go svg { width: 16px; height: 16px; }
.go:hover { background: var(--brand-dark); box-shadow: 0 4px 12px rgba(37, 99, 235, .3); }
.go:active { transform: translateY(1px); }
.go:disabled { opacity: .55; box-shadow: none; cursor: default; }
@media (max-width: 760px) {
  .form .fields { grid-template-columns: repeat(2, 1fr); }
  .fgrp-title { grid-column: 1 / -1; }
  .fld-id, .fld-rank, .fld-xrank, .fld-mode, .fld-km { grid-column: span 1; }
  .fld-jr, .fld-home, .fld-board, .fld-go, .fld-farb,
  .fld-risk, .fld-orient, .fld-nonpub { grid-column: span 2; }
  .fld-go .go { width: 100%; min-width: 0; }
}
/* iOS Safari 在输入框字号 <16px 时聚焦会自动放大页面 → 移动端所有文本输入强制 16px 阻止缩放。
   用 :not 排除勾选框,以兼容无 type 属性的输入(如初中学校 datalist 框,默认 type=text 但无属性,[type=text] 选不中) */
@media (max-width: 760px) {
  input:not([type=checkbox]):not([type=radio]):not([type=range]),
  select, textarea { font-size: 16px !important; }
}
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
/* 查学校表格：固定布局占满宽度、所有列默认显示、单元格内容换行(不横向滚动) */
.ex-table { min-width: 0; width: 100%; table-layout: fixed; font-size: 12px; }
.ex-table th, .ex-table td { padding: 6px 7px; white-space: normal; word-break: break-word; vertical-align: top; }
.ex-table th:nth-child(1), .ex-table td:nth-child(1) { width: 23%; }  /* 学校 */
.ex-table th:nth-child(2), .ex-table td:nth-child(2) { width: 12%; }  /* 类型 */
.ex-table th:nth-child(3), .ex-table td:nth-child(3) { width: 12%; }  /* 层次 */
.ex-table th:nth-child(4), .ex-table td:nth-child(4) { width: 8%; }   /* 档位 */
.ex-table th:nth-child(5), .ex-table td:nth-child(5) { width: 9%; }   /* 渠道 */
.ex-table th:nth-child(6), .ex-table td:nth-child(6) { width: 18%; }  /* 关键 */
.ex-table th:nth-child(7), .ex-table td:nth-child(7) { width: 10%; }  /* 通勤 */
.ex-table th:nth-child(8), .ex-table td:nth-child(8) { width: 8%; }   /* 住 */
.ex-table tbody tr { cursor: pointer; }
.ex-tr.on { background: var(--brand-50) !important; box-shadow: inset 3px 0 0 var(--brand); }
.ex-ty { font-size: 11.5px; color: var(--gray-500); }
.ex-cbg { display: inline-block; min-width: 16px; text-align: center; font-size: 10.5px; font-weight: 700; padding: 1px 4px; margin-right: 2px; border-radius: 3px; background: var(--brand-50); color: var(--brand-dark); }
.ex-keycol small { color: var(--gray-400); font-size: 10.5px; margin-right: 2px; }
/* ── 渠道科普(重设计) ── */
.chwrap2 { background: transparent; box-shadow: none; }
.ch-hero { background: linear-gradient(135deg, var(--brand-50), #fff); border: 1px solid var(--gray-100); border-radius: 14px; padding: 16px 18px; }
.chh-flow { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.chh-step { font-size: 14px; font-weight: 700; color: var(--brand-dark); background: #fff; border: 1px solid var(--brand); border-radius: var(--radius-full); padding: 6px 16px; }
.chh-step.on { background: var(--brand); color: #fff; }
.chh-lock { font-size: 13px; }
/* 手机:三批次流程压成一行不换行(收紧字号/内边距/间距) */
@media (max-width: 560px) {
  .chh-flow { flex-wrap: nowrap; gap: 3px; justify-content: space-between; }
  .chh-step { font-size: 12px; padding: 5px 8px; white-space: nowrap; }
  .chh-lock { font-size: 11px; flex-shrink: 0; }
}
.chh-note { font-size: 12.5px; color: var(--gray-600); margin: 10px 0 0; line-height: 1.6; }
/* 身份自查 */
.ch-id { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 14px 0 6px; }
.ci-t { font-size: 13px; font-weight: 700; color: var(--gray-700); }
.ci-b { font-size: 12.5px; padding: 5px 14px; border: 1px solid var(--gray-200); background: #fff; border-radius: var(--radius-full); cursor: pointer; color: var(--gray-700); }
.ci-b.on { background: var(--brand); color: #fff; border-color: var(--brand); }
.ci-hint { font-size: 11.5px; color: var(--gray-400); }
/* 渠道卡 */
.ch-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin: 8px 0 16px; }
.cc { border: 1px solid var(--gray-200); border-radius: 12px; padding: 12px 14px; background: #fff; display: flex; flex-direction: column; transition: opacity .2s, box-shadow .15s; }
.cc:hover { box-shadow: var(--shadow-sm); }
.cc.dim { opacity: .42; }
.cc-h { display: flex; align-items: center; gap: 8px; width: 100%; border: none; background: none; cursor: pointer; padding: 0; text-align: left; }
.cc-ic { font-size: 18px; }
.cc-nm { font-size: 14.5px; font-weight: 700; color: var(--gray-900); }
.cc-no { font-size: 10.5px; color: #b45309; background: var(--warning-bg); border-radius: var(--radius-full); padding: 1px 7px; }
.cc-chev { margin-left: auto; font-size: 16px; color: var(--gray-400); }
.cc-one { font-size: 12.5px; color: var(--gray-700); margin: 7px 0 0; line-height: 1.55; }
.cc-meta { font-size: 11.5px; color: var(--gray-600); margin: 6px 0 0; line-height: 1.5; }
.cc-meta .cc-k { display: inline-block; font-weight: 600; color: var(--gray-400); margin-right: 5px; }
.cc-body { margin: 8px 0 0; }
.cc-body ul { margin: 0; padding-left: 16px; font-size: 12px; color: var(--gray-700); line-height: 1.65; }
.cc-acts { display: flex; align-items: center; gap: 10px; margin-top: 10px; padding-top: 9px; border-top: 1px solid var(--gray-100); }
.cc-use { font-size: 12px; font-weight: 600; color: #fff; background: var(--brand); border: none; border-radius: var(--radius-full); padding: 4px 11px; cursor: pointer; }
.cc-link { margin-left: auto; font-size: 11.5px; color: var(--gray-500); text-decoration: none; }
.cc-link:hover { color: var(--brand-dark); }
/* 铁律速记 */
.ch-rules { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; margin: 0 0 16px; }
.cr { font-size: 12px; color: var(--gray-700); background: var(--gray-50); border: 1px solid var(--gray-100); border-radius: 8px; padding: 8px 11px; line-height: 1.5; }
.cr b { color: var(--brand-dark); }
.ch-pitfalls { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px; margin: 0 0 16px; }
.pf { background: var(--gray-50); border: 1px solid var(--gray-100); border-radius: 8px; padding: 9px 11px; }
.pf-bad { font-size: 12.5px; color: var(--gray-500); line-height: 1.5; text-decoration: line-through; text-decoration-color: var(--gray-300); }
.pf-good { font-size: 12.5px; color: var(--gray-800); line-height: 1.55; margin-top: 4px; }
.pf-x, .pf-ok { margin-right: 5px; text-decoration: none; display: inline-block; }
.pf-bad .pf-x { text-decoration: none; }
/* 区块标题 */
.ch-sec-t { font-size: 14px; font-weight: 700; color: var(--gray-800); margin: 4px 0 8px; }
.ch-sec-t small { font-weight: 400; color: var(--gray-400); font-size: 11.5px; }
/* 官方入口 */
.ch-official { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; margin: 0 0 16px; }
.of { display: flex; flex-direction: column; gap: 4px; border: 1px solid var(--gray-200); border-radius: 10px; padding: 11px 13px; text-decoration: none; background: #fff; transition: border-color .15s, box-shadow .15s; }
.of:hover { border-color: var(--brand); box-shadow: var(--shadow-sm); }
.of-top { display: flex; align-items: center; gap: 7px; }
.of-badge { font-size: 10px; font-weight: 700; color: #fff; background: #16a34a; border-radius: var(--radius-full); padding: 1px 7px; }
.of-nm { font-size: 13px; font-weight: 600; color: var(--brand-dark); }
.of-arr { margin-left: auto; color: var(--gray-400); }
.of-desc { font-size: 11.5px; color: var(--gray-500); line-height: 1.5; }
/* 时间线 */
.ch-timeline { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
.tl { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 150px; border-left: 3px solid var(--brand); background: var(--gray-50); border-radius: 0 8px 8px 0; padding: 8px 11px; }
.tl-t { font-size: 12.5px; font-weight: 700; color: var(--brand-dark); }
.tl-d { font-size: 11.5px; color: var(--gray-600); line-height: 1.45; }
.ch-foot { font-size: 11.5px; color: var(--gray-400); margin: 4px 0 0; line-height: 1.6; }

/* ── 升学全景：批次流程条 + 子页锚定 ── */
.batch-flow { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 2px 0 8px; }
.bf-step { font-size: 13px; font-weight: 700; color: var(--brand-dark); background: var(--brand-50); border: 1px solid var(--brand); border-radius: var(--radius-full); padding: 4px 12px; }
.bf-step.bf-core { background: var(--brand); color: #fff; }
.bf-lock { font-size: 11px; color: #b45309; font-weight: 600; }
.bf-note { font-size: 12.5px; line-height: 1.7; color: var(--gray-700); background: #fff8e1; border: 1px solid #ffe082; border-radius: var(--radius-xs); padding: 9px 11px; margin: 0 0 10px; }
.ch-anchor { margin: 0 0 12px; }
.ch-anchor h3 { font-size: 16px; color: var(--brand-deeper); margin: 0 0 6px; }
.ch-anchor > p { font-size: 12.5px; color: var(--gray-700); line-height: 1.65; margin: 0; }

.ch-tips { font-size: 12.5px; line-height: 1.8; color: var(--gray-700); background: var(--brand-50); border: 1px solid var(--brand); border-radius: var(--radius-xs); padding: 10px 12px; margin: 10px 0 0; }
@media (max-width: 720px) { .ex-main { flex-direction: column; } }

.detail-panel { width: 320px; flex-shrink: 0; height: 460px; overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--surface); border: 1px solid var(--gray-100); border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm); padding: 14px; }
.dp-empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; color: var(--gray-400); font-size: 13px; text-align: center; }
.dp-empty-ic { font-size: 32px; opacity: .5; }
.dp-head { } /* 上下两行:chip 在上,校名独占整行(不再横排挤窄) */
.dp-head h3 { font-size: 16px; font-weight: 700; color: var(--gray-900); margin: 5px 0 0; line-height: 1.3; }
.dp-type { display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: var(--radius-full); background: var(--brand-50); color: var(--brand-dark); }
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
.dp-pred { background: #fffaf0; border: 1px solid #fde8c8; border-radius: var(--radius); padding: 8px 10px; margin-top: 12px; }
.dp-pred .dp-title { color: #b9770e; border-left-color: #e8a33d; }
.dp-predv { font-size: 17px; color: #b9770e; }
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
.tab .tab-ic { display: inline-flex; align-items: center; justify-content: center; color: var(--gray-400); transition: color .15s, transform .15s; }
.tab .tab-ic svg { width: 17px; height: 17px; display: block; }
.tab:hover .tab-ic { color: var(--gray-600); }
.tab.on .tab-ic { color: var(--brand); transform: translateY(-0.5px); }
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
/* 手机:4 个一级页签压成等宽一行,不再换行(图标保留缩小,计数改紧凑纯文字) */
@media (max-width: 560px) {
  .tabs { flex-wrap: nowrap; gap: 2px; padding: 0 2px; }
  .tab, .tab-main { flex: 1 1 0; min-width: 0; justify-content: center;
    font-size: 12px; padding: 7px 2px 9px; gap: 2px; }
  .tab .tab-ic svg { width: 14px; height: 14px; }
  /* 计数去掉药丸底色,压成贴在标签后的小字 */
  .tab-cnt, .tab.on .tab-cnt { font-size: 9px; padding: 0; margin-left: 1px;
    background: none; font-weight: 700; }
}
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
.va-高增值 { color: #16a34a; }
.va-偏低 { color: #dc2626; }
.va-顶部饱和 { color: var(--brand-dark); }
.feat-chip { display: inline-block; font-size: 11px; padding: 1px 7px; margin: 0 4px 2px 0; border-radius: var(--radius-full); background: var(--brand-50); color: var(--brand-dark); }
.va-tag { background: #dcfce7 !important; color: #16a34a !important; }
.cmp-cb { margin-right: 6px; vertical-align: middle; cursor: pointer; }
.ex-cmpbtn { margin-left: 8px; font-size: 12px; font-weight: 600; padding: 3px 10px; border: none; border-radius: var(--radius-full); background: var(--brand); color: #fff; cursor: pointer; }
.cmp-mask { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 3000; display: flex; align-items: center; justify-content: center; padding: 20px; }
.cmp-box { background: #fff; border-radius: 12px; max-width: 920px; width: 100%; max-height: 84vh; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 12px 40px rgba(0,0,0,.25); }
.cmp-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--gray-100); }
.cmp-x { border: none; background: none; font-size: 16px; cursor: pointer; color: var(--gray-500); }
.cmp-scroll { overflow: auto; }
.cmp-table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
.cmp-table th, .cmp-table td { border: 1px solid var(--gray-100); padding: 7px 10px; text-align: left; vertical-align: top; }
.cmp-table th { background: var(--gray-50); position: sticky; top: 0; }
.cmp-table td:first-child, .cmp-table th:first-child { background: var(--gray-50); font-weight: 600; color: var(--gray-600); white-space: nowrap; position: sticky; left: 0; }
.cmp-rm { display: block; margin-top: 3px; font-size: 10px; font-weight: 400; color: var(--gray-400); border: none; background: none; cursor: pointer; padding: 0; }
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
.ai-btn { font-size: 12.5px; padding: 6px 14px; border: none; border-radius: var(--radius-xs);
  background: linear-gradient(135deg, #7c3aed, #2563eb); color: #fff; font-weight: 600; cursor: pointer; }
.ai-btn:disabled { opacity: .6; cursor: not-allowed; }
.ai-report { border: 1px solid #ddd6fe; background: #faf5ff; border-radius: var(--radius);
  padding: 14px 16px; margin: 12px 0 14px; }
.ai-report-head { font-size: 14px; font-weight: 700; color: #6d28d9; margin-bottom: 10px;
  border-bottom: 1px solid #e9d5ff; padding-bottom: 8px; }
.ai-report-head small { font-weight: 400; color: var(--gray-500); font-size: 11px; }
.ai-report-body { font-size: 13.5px; line-height: 1.75; color: var(--gray-800); }
.ai-report-body h4 { font-size: 14.5px; color: #5b21b6; margin: 14px 0 6px; }
.ai-report-body h5 { font-size: 13.5px; color: var(--gray-700); margin: 10px 0 4px; }
.ai-report-body p { margin: 4px 0; }
.ai-report-body .ai-li { margin: 3px 0 3px 6px; }
.ai-report-body b { color: var(--gray-900); }
/* 孩子画像问卷 */
.pq-body { padding: 10px 14px 4px; display: flex; flex-direction: column; gap: 10px; }
.pq-row { display: flex; align-items: center; gap: 10px; }
.pq-row label { flex: 0 0 70px; font-size: 12.5px; color: var(--gray-600); }
.pq-row select, .pq-input { flex: 1; padding: 7px 10px; font-size: 13px; border: 1px solid var(--gray-300);
  border-radius: var(--radius-xs); background: #fff; color: var(--gray-800); min-width: 0; }
.pq-multi label { font-size: 12.5px; color: var(--gray-600); display: block; margin-bottom: 5px; }
.pq-multi label small { color: var(--gray-400); font-weight: 400; }
.pq-multi .chips { display: flex; flex-wrap: wrap; gap: 6px; }
.pchip { padding: 5px 11px; font-size: 12.5px; border: 1px solid var(--gray-300); border-radius: 999px;
  background: #fff; color: var(--gray-600); cursor: pointer; }
.pchip.on { background: #ede9fe; border-color: #c4b5fd; color: #6d28d9; font-weight: 600; }
.pq-foot { font-size: 11.5px; color: var(--gray-400); margin: 2px 0 6px; }
/* AI 深度分析 独立区块（草表之后） */
.ai-section { margin-top: 18px; border: 1px solid #ddd6fe; border-radius: var(--radius);
  background: linear-gradient(180deg, #faf5ff 0%, var(--surface) 60%); padding: 16px; }
.ai-sec-head h3 { font-size: 16px; font-weight: 700; color: #6d28d9; margin: 0 0 6px; }
.ai-sec-head h3 small { font-size: 11.5px; font-weight: 500; color: var(--gray-500); }
.ai-sec-intro { font-size: 12.5px; line-height: 1.7; color: var(--gray-700); margin: 0 0 12px; }
.ai-cta { font-size: 14px; padding: 11px 20px; width: 100%; }
.pq-card { border: 1px solid #ede9fe; border-radius: var(--radius-sm); background: var(--surface); margin: 4px 0 12px; }
.pq-title { padding: 10px 14px; font-size: 13px; font-weight: 600; color: #6d28d9;
  border-bottom: 1px solid #f1ebfe; }
.pq-title small { font-weight: 400; color: var(--gray-400); font-size: 11px; }
.ai-gen-row { display: flex; gap: 10px; margin: 4px 0 6px; }
.ai-gen-row .ai-btn { font-size: 13.5px; padding: 9px 18px; }
/* 三批次分区（可折叠）*/
.batch { margin-top: 10px; }
.batch-h { width: 100%; text-align: left; display: block; cursor: pointer;
  font-size: 15px; font-weight: 700; color: var(--brand-deeper);
  background: var(--gray-50); border: 1px solid var(--gray-100); border-radius: var(--radius-sm);
  padding: 10px 12px; margin: 0 0 10px; }
.batch-h:hover { border-color: var(--brand); }
.batch-h .bc { display: inline-block; width: 16px; color: var(--gray-400); font-weight: 400; }
.batch-h small { font-weight: 400; font-size: 12px; color: var(--gray-500); margin-left: 6px; }
.batch-sub { font-size: 13.5px; font-weight: 700; color: var(--gray-800); margin: 14px 0 8px; }
.batch-sub small { font-weight: 400; font-size: 11.5px; color: var(--gray-400); margin-left: 6px; }
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
.x { flex-shrink: 0; width: 26px; height: 30px; font-size: 12px; border: 1px solid var(--gray-200);
  background: #fff; border-radius: var(--radius-xs); color: var(--gray-400); cursor: pointer; }
.x:hover { color: var(--error); border-color: var(--error); }
.slot-majors { margin-top: 8px; padding-left: 30px; display: flex; flex-wrap: wrap; gap: 6px; }
.nomajor { font-size: 12px; color: var(--gray-400); }
.src { font-size: 11px; color: var(--gray-400); margin-top: 14px; }
/* 统招：学校+专业同一行，去空白 */
.uni-list { display: flex; flex-direction: column; gap: 6px; }

/* ── 统招③ 策略总览 + 志愿理由 ── */
.uni-summary { background: var(--brand-50); border: 1px solid var(--brand); border-radius: var(--radius-sm); padding: 10px 12px; margin: 4px 0 12px; }
.us-line { font-size: 13px; color: var(--gray-800); display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.us-b { display: inline-block; font-size: 12px; font-weight: 700; padding: 1px 8px; border-radius: var(--radius-full); }
.us-bottom { font-size: 12.5px; color: var(--gray-700); margin-left: 4px; }
.us-tip { font-size: 12px; color: var(--gray-600); line-height: 1.6; margin: 6px 0 0; }
.us-warn { font-size: 12.5px; color: #b45309; background: var(--warning-bg); border-radius: var(--radius-xs); padding: 8px 11px; margin: 8px 0 0; line-height: 1.6; }
/* 低位次专属方案 */
.lowplan { border: 1px solid var(--brand-100, #dbeafe); background: linear-gradient(180deg, var(--brand-50), #fff); border-radius: 12px; padding: 14px 16px; margin: 10px 0 14px; }
.lp-head { font-size: 15px; font-weight: 700; color: var(--brand-dark); }
.lp-sub { display: block; font-size: 12px; font-weight: 400; color: var(--gray-600); margin-top: 4px; line-height: 1.6; }
.lp-list { margin: 10px 0 0; padding-left: 20px; font-size: 13px; color: var(--gray-800); line-height: 1.75; }
.lp-list li { margin: 7px 0; }
.lp-list b { color: var(--gray-900); }
.lp-list .lnk { margin-left: 4px; white-space: nowrap; }
.lp-foot { font-size: 11.5px; color: var(--gray-500); margin: 10px 0 0; line-height: 1.6; }
/* 填报三铁律条 */
.rules-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 8px 12px; margin: 8px 0 12px; background: var(--gray-50); border: 1px solid var(--gray-100); border-radius: 10px; font-size: 12px; }
.rules-strip .rs-t { font-weight: 700; color: var(--gray-700); }
.rules-strip .rs-i { color: var(--gray-600); }
.rules-strip .rs-i.bad { color: #dc2626; font-weight: 600; }
.rules-strip .rs-copy { margin-left: auto; flex: 0 0 auto; font-size: 12px; padding: 3px 10px; border-radius: var(--radius-full);
  border: 1px solid var(--brand); background: #fff; color: var(--brand-dark); cursor: pointer; }
.rules-strip .rs-copy:hover { background: var(--brand-50); }
/* 规则与策略结构化卡片 */
.rules-doc { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 10px 0 14px; }
.rd-card { border: 1px solid var(--gray-100); border-radius: 10px; padding: 12px 14px; background: #fff; }
.rd-card h4 { margin: 0 0 8px; font-size: 13.5px; color: var(--brand-dark); }
.rd-card .g-tbl { font-size: 11.5px; }
.rd-card.rd-strat, .rd-card.rd-2026 { grid-column: 1 / -1; }
.rd-ol { margin: 0; padding-left: 18px; font-size: 12.5px; color: var(--gray-800); line-height: 1.7; }
.rd-ol li { margin: 4px 0; }
.rd-card p { font-size: 12.5px; color: var(--gray-700); line-height: 1.7; margin: 6px 0 0; }
.rd-mini { font-size: 11.5px !important; color: var(--gray-500) !important; }
.rd-2026 { background: var(--warning-bg); border-color: #fde68a; }
@media (max-width: 720px) { .rules-doc { grid-template-columns: 1fr; } }
.band-刺 { background: #ede7f6; color: #6a1b9a; }
/* 只读志愿行样式已迁入 DraftRow.vue（②校额/②统筹/③统招 共用）*/
/* 折叠「录取规则与口径」 */
.note-toggle { background: none; border: none; padding: 6px 0 0; font-size: 11.5px; color: var(--brand-dark);
  cursor: pointer; font-weight: 600; }
.note-body { font-size: 11.5px; color: var(--gray-600); line-height: 1.65; margin-top: 5px;
  padding: 8px 10px; background: var(--gray-50); border-radius: var(--radius-xs); }
.note-body .lnk { color: var(--brand-dark); }
/* 批次说明（提前招生） */
.batch-note { padding: 10px 14px 12px; font-size: 12.5px; line-height: 1.7; color: var(--gray-700); }
.batch-note p { margin: 4px 0; }
.batch-note .bn-foot { color: var(--gray-500); font-size: 11.5px; margin-top: 8px; }
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
/* 地图选中 marker 高亮:放大 + 蓝环 + 置顶,与未选中明显区别 */
#zmap :deep(.leaflet-marker-icon.mk-sel) {
  filter: drop-shadow(0 0 0 #2563eb) drop-shadow(0 0 6px rgba(37,99,235,.9));
  transform-origin: bottom center; z-index: 1200 !important; }
#zmap :deep(.leaflet-marker-icon.mk-sel) > * { outline: 3px solid #2563eb; outline-offset: 1px; border-radius: 50%; }
/* 详情面板关闭按钮(桌面隐藏,手机弹层显示) */
.dp-close { display: none; }
.dp-backdrop { display: none; }
/* ── 手机优化(≤560):查学校表瘦身、触控热区、头部压缩、安全区 ── */
@media (max-width: 560px) {
  .page { padding: 10px 10px calc(10px + env(safe-area-inset-bottom)); }
  .hero h1 { font-size: 19px; }
  .hero .sub { font-size: 12px; line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  #zmap { height: 56vh; min-height: 300px; }
  /* 触控热区 ≥38px */
  .tab { min-height: 40px; }
  .ex-chip, .lchip, .chip { min-height: 34px; display: inline-flex; align-items: center; }
  .op { min-width: 34px; min-height: 34px; }
  .mchip { min-height: 32px; }
  /* 查学校表:首列校名固定,隐藏次要列(层次/渠道/通勤/住),保留 校名/类型/档位/关键 */
  .ex-table { font-size: 12px; table-layout: fixed; width: 100%; min-width: 0; }
  .ex-table th, .ex-table td { padding: 6px 6px; white-space: normal; word-break: break-word; min-width: 0; max-width: none; overflow: hidden; }
  .ex-table .t-name { width: 40%; }
  .ex-table th:first-child, .ex-table td:first-child {
    position: sticky; left: 0; background: #fff; z-index: 1; box-shadow: 1px 0 0 var(--gray-100); }
  .ex-table thead th:nth-child(3), .ex-table tbody td:nth-child(3),
  .ex-table thead th:nth-child(5), .ex-table tbody td:nth-child(5),
  .ex-table thead th:nth-child(7), .ex-table tbody td:nth-child(7),
  .ex-table thead th:nth-child(8), .ex-table tbody td:nth-child(8) { display: none; }
  /* 地图选中学校 → 底部弹层(不再上下来回滑);未选中则不占位,地图占满 */
  .map-detail { display: block; }
  .detail-panel { display: none; }
  .detail-panel.dp-sheet {
    display: block; position: fixed; left: 0; right: 0; bottom: 0; width: auto; height: auto;
    max-height: 82vh; overflow-y: auto; -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain; z-index: 1500; margin: 0;
    border-radius: 16px 16px 0 0; box-shadow: 0 -6px 24px rgba(0,0,0,.22);
    padding: 16px 14px calc(16px + env(safe-area-inset-bottom)); background: #fff;
    animation: dpUp .18s ease-out; }
  /* 弹层打开时遮罩吃掉手势,避免下滑穿透到底下的地图页 */
  .dp-backdrop { display: block; position: fixed; inset: 0; background: rgba(0,0,0,.4);
    z-index: 1490; touch-action: none; }
  .dp-close { display: flex; align-items: center; justify-content: center; position: sticky; top: -16px; float: right;
    width: 34px; height: 34px; margin: -6px -4px 0 0; border: none; background: var(--gray-100);
    border-radius: 50%; font-size: 16px; color: var(--gray-600); cursor: pointer; }
}
@keyframes dpUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
</style>
