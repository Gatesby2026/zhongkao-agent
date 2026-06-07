<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { api, type ReportResp, type ManualChoicesResp, type TraceQuestion } from './api'

const step = ref(0)                       // 0 首屏 1 上传 2 小分 3 分析 4 报告
// step1 子阶段：pick 选图 / detecting 识别中 / confirm 确认 / failed 识别失败
const phase = ref<'pick'|'uploading'|'detecting'|'confirm'|'failed'>('pick')
const detectErr = ref('')
const analysisId = ref<string | null>(null)
const photos = ref<File[]>([])
const photoUrls = ref<string[]>([])
const detected = ref<any>(null)
const studentName = ref('')               // 确认页可纠正（OCR 偶错）
const coverage = ref<any>(null)           // 已支持范围（按需加载）
const coverageOpen = ref(false)           // 首页"支持范围"卡折叠状态
const scoreMode = ref<'teacher'|'auto'>('auto')   // 默认无小分→自动判分
const scoreFile = ref<File | null>(null)
const scoreInfo = ref<string>('')
const stageIdx = ref(0)
const stageName = ref('')
const report = ref<ReportResp | null>(null)
const errorMsg = ref('')
let pollTimer: number | undefined

// step5 选择题人工确认
const manual = ref<ManualChoicesResp | null>(null)
const manualChoices = ref<Record<string, string>>({})   // 可编辑：Qx → 字母
const manualBusy = ref(false)
const showAllChoices = ref(false)


const STAGES = [
  '识别考试信息（区/科目/年份）',
  '识别答题卡作答',
  '对照标准答案，标注失分题',
  'AI 分析失分主因',
  '生成知识点提分建议',
]

// 极简 3 节点：答题卡（含上传/识别/确认/判分方式）→ 分析 → 报告
// 判分方式（step2）属"答题卡"环节的最后一步（数据准备），不单列节点
const stepperSteps = ['答题卡', '分析', '报告']
const journeyStage = computed(() => {
  if (step.value === 0) return 0
  if (step.value === 1 || step.value === 2) return 1   // 答题卡 阶段含判分方式
  if (step.value === 5) return 1                        // 选择题人工确认 仍属答题卡
  if (step.value === 3) return 2                        // 分析中
  return 3                                              // step 4 报告
})
function stepState(n: number) {
  const j = journeyStage.value
  return n < j ? 'done' : (n === j ? 'active' : '')
}

function onPick(e: Event) {
  const fl = (e.target as HTMLInputElement).files
  if (!fl) return
  for (const f of Array.from(fl)) {
    if (photos.value.length >= 8) break
    photos.value.push(f)
    photoUrls.value.push(URL.createObjectURL(f))
  }
}
function delPhoto(i: number) {
  photos.value.splice(i, 1)
  photoUrls.value.splice(i, 1)
}
function onScorePick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) scoreFile.value = f
}

// step1：上传并识别
async function uploadAndDetect() {
  errorMsg.value = ''
  if (!photos.value.length) { errorMsg.value = '请先上传答题卡照片'; return }
  phase.value = 'uploading'          // 立即反馈：进入上传中（按钮置灰 + 内联进度）
  try {
    const r = await api.createAnalysis(photos.value)
    analysisId.value = r.id
  } catch (e: any) {
    phase.value = 'pick'             // 上传失败回到选图，可重选重试
    errorMsg.value = '上传失败：' + e.message; return
  }
  if (phase.value !== 'uploading') return   // 用户上传中点了"重新选择"，放弃本次结果
  phase.value = 'detecting'
  pollDetect()
}

function pollDetect() {
  const id = analysisId.value!
  clearInterval(pollTimer)
  const tick = async () => {
    try {
      const r = await api.detect(id)
      if (r.status === 'ready_confirm') {
        clearInterval(pollTimer)
        detected.value = r.detected
        studentName.value = r.detected?.student_name || ''
        phase.value = 'confirm'
      } else if (r.status === 'failed' || r.status === 'need_manual') {
        clearInterval(pollTimer)
        detectErr.value = r.error ||
          '没能从答题卡识别出考试信息，请重拍含顶部标题行的照片重新上传'
        phase.value = 'failed'
      }
    } catch {}
  }
  tick()
  pollTimer = window.setInterval(tick, 2500)
}

function retryUpload() {        // 识别失败 → 重新选图
  clearInterval(pollTimer)
  phase.value = 'pick'
  detectErr.value = ''
  analysisId.value = null
  photos.value = []
  photoUrls.value = []
}

function confirmExam() {        // 确认无误 → 进小分步骤
  step.value = 2
}

function goStart() {            // 首屏 → 上传流程
  resetToStart()
  step.value = 1
}

async function onNext() {       // 底部主按钮
  errorMsg.value = ''
  if (step.value === 1) {
    if (phase.value === 'pick') return uploadAndDetect()
    if (phase.value === 'confirm') return confirmExam()
    if (phase.value === 'failed') return retryUpload()
    return
  }
  if (step.value === 2) {
    if (scoreMode.value === 'teacher') {
      if (!scoreFile.value) { errorMsg.value = '请上传小分表，或改选「AI 自动判分」'; return }
      try {
        const r: any = await api.uploadScores(analysisId.value!, scoreFile.value)
        scoreInfo.value = `${r.student_name||''} ${r.exam_total?.scored}/${r.exam_total?.fullScore} · ${r.n_questions}题`
      } catch (e: any) { errorMsg.value = '小分解析失败：' + e.message; return }
    }
    try { await api.startPipeline(analysisId.value!, studentName.value.trim()) }
    catch (e: any) { errorMsg.value = '启动分析失败：' + e.message; return }
    step.value = 3
    startPolling()
  } else if (step.value === 4) {
    openPdf(api.reportPdfUrl(analysisId.value!), '学情分析报告')
  }
}

function prev() {
  if (step.value === 4) { resetToStart(); return }
  if (step.value === 2) { step.value = 1; phase.value = 'confirm'; return }
  if (step.value === 1) { resetToStart(); return }
}
function resetToStart() {
  step.value = 0; phase.value = 'pick'
  analysisId.value = null; report.value = null
  photos.value = []; photoUrls.value = []
  detected.value = null; scoreFile.value = null; stageIdx.value = 0
  manual.value = null; manualChoices.value = {}; showAllChoices.value = false
  errorMsg.value = ''
}

function startPolling() {
  const id = analysisId.value!
  clearInterval(pollTimer)
  const tick = async () => {
    try {
      const s = await api.status(id)
      stageIdx.value = s.stage
      stageName.value = s.stage_name
      if (s.status === 'done') {
        clearInterval(pollTimer)
        report.value = await api.report(id)
        step.value = 4
      } else if (s.status === 'need_manual') {
        clearInterval(pollTimer)
        await enterManual(id)
      } else if (s.status === 'failed') {
        clearInterval(pollTimer)
        errorMsg.value = '分析失败：' + s.error
      }
    } catch {}
  }
  tick()
  pollTimer = window.setInterval(tick, 2500)
}
// need_manual → 拉取识别 trace，进入选择题人工确认页（step5）
async function enterManual(id: string) {
  try {
    const m = await api.getManualChoices(id)
    manual.value = m
    // 编辑态初始化：以识别值为底，逐题可改
    const init: Record<string, string> = { ...(m.current || {}) }
    for (const q of m.recognition_trace?.questions || [])
      if (!init['Q' + q.qid]) init['Q' + q.qid] = q.final || ''
    manualChoices.value = init
    showAllChoices.value = false
    step.value = 5
  } catch (e: any) {
    errorMsg.value = '加载待确认选择题失败：' + e.message
  }
}
// 已对齐则按 trace 逐题展示；先列待确认（黄/红），高置信题折叠
const traceQs = computed<TraceQuestion[]>(() =>
  (manual.value?.recognition_trace?.aligned &&
    manual.value?.recognition_trace?.questions) || [])
const reviewQs = computed(() => traceQs.value.filter(q => q.status !== 'green'))
const greenQs = computed(() => traceQs.value.filter(q => q.status === 'green'))
// 未对齐兜底：直接列 current 的所有选择题
const plainQids = computed(() =>
  traceQs.value.length ? [] :
    Object.keys(manual.value?.current || {})
      .sort((a, b) => (+a.slice(1)) - (+b.slice(1))))
function setManual(qid: string, letter: string) {
  manualChoices.value = { ...manualChoices.value, [qid]: letter }
}
function densPct(q: TraceQuestion, L: string) {
  return Math.round((q.probe?.dens?.[L] || 0) * 100)
}
function statusLabel(s: string) {
  return s === 'red' ? '未识别' : s === 'yellow' ? '请确认' : '高置信'
}
async function submitManual() {
  if (!analysisId.value) return
  manualBusy.value = true; errorMsg.value = ''
  try {
    await api.submitManualChoices(analysisId.value, manualChoices.value)
    step.value = 3
    startPolling()
  } catch (e: any) {
    errorMsg.value = '提交失败：' + e.message
  } finally { manualBusy.value = false }
}

onMounted(async () => {
  try { coverage.value = await api.coverage() } catch {}
})

// 报告里的 $...$ 公式让 KaTeX 渲染（CDN auto-render；脚本 defer 加载）
function renderMath() {
  const fn = (window as any).renderMathInElement
  if (!fn) return
  // 多个 step 各有自己的 .scroll-area，全部扫一遍（含 step4 报告页的 .wrong-q）
  document.querySelectorAll<HTMLElement>('.scroll-area').forEach(el => {
    fn(el, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
      ],
      throwOnError: false,
      ignoredClasses: ['no-math'],
    })
  })
}
watch(() => report.value, async () => {
  if (!report.value) return
  await nextTick()
  renderMath()
  // KaTeX script defer 可能尚未就绪 → 200ms 后再试一次
  setTimeout(renderMath, 200)
})
onUnmounted(() => clearInterval(pollTimer))

const NEXT_LABEL = computed(() => {
  if (step.value === 1) {
    if (phase.value === 'pick') return '上传并识别'
    if (phase.value === 'uploading') return '上传中…'
    if (phase.value === 'detecting') return '识别中…'
    if (phase.value === 'confirm') return '确认无误，下一步'
    if (phase.value === 'failed') return '重新选择图片上传'
  }
  if (step.value === 2) return '开始分析'
  if (step.value === 4) return '下载报告 PDF'
  return '请稍候…'
})
const nextDisabled = computed(() =>
  step.value === 1 && (
    phase.value === 'uploading' ||
    phase.value === 'detecting' ||
    (phase.value === 'pick' && !photos.value.length)))

const progressPct = computed(() => {
  const n = STAGES.length
  const done = Math.max(0, Math.min(stageIdx.value, n))
  return Math.max(6, Math.round((done / n) * 100))   // 至少 6% 体现"已启动"
})

// images 模式用于静态多页 PDF 的可滚动展示（如示例报告 12 页），
// 解决移动端 iframe 嵌 PDF 滚动受限；url 模式仍用于真实报告/试卷
const pdfView = ref<{
  url?: string; images?: string[]; downloadUrl?: string; title: string
} | null>(null)
function openPdf(url: string, title: string) {
  pdfView.value = { url, title }
}
function openImages(images: string[], title: string, downloadUrl?: string) {
  pdfView.value = { images, title, downloadUrl }
}
function closePdf() { pdfView.value = null }

const SAMPLE_PAGES = Array.from({ length: 12 }, (_, i) =>
  `/sample-report-pages/page-${String(i + 1).padStart(2, '0')}.png`)
function openSampleReport() {
  openImages(SAMPLE_PAGES, '示例学情报告（脱敏）', '/sample-report.pdf')
}

function openPaper() {
  if (analysisId.value)
    openPdf(api.paperPdfUrl(analysisId.value), '试卷原卷（含答案）')
}

const pct = (r: number) => Math.round(r * 100)
const barClass = (r: number) => r >= 0.8 ? 'green' : (r >= 0.6 ? 'yellow' : 'red')
const correctCnt = computed(() =>
  report.value ? report.value.n_questions - report.value.n_lost : 0)

// 失分题界面按题号升序（PDF 报告侧 aggregate.lost_questions 仍按失分降序）
const wrongByNum = computed(() => {
  if (!report.value) return []
  const num = (q: string) => parseInt(String(q).replace(/\D+/g, ''), 10) || 0
  return [...report.value.wrong_questions].sort((a, b) => num(a.qid) - num(b.qid))
})
</script>

<template>
<div class="app-shell">
    <!-- 顶部蓝条已删；返回 + stepper + 计数 合并一行（方案 B）-->
    <div class="stepper" v-show="step>=1">
      <div class="stepper-back" @click="prev" role="button" aria-label="返回">‹</div>
      <template v-for="(nm, i) in stepperSteps" :key="i">
        <div class="step" :class="stepState(i+1)">
          <div class="dot"><span v-if="stepState(i+1)!=='done'">{{ i+1 }}</span></div>{{ nm }}
        </div>
        <div v-if="i < 2" class="step-line" :class="{ done: i+1 < journeyStage }"></div>
      </template>
      <div class="stepper-count">{{ journeyStage>=3 ? '完成' : journeyStage + '/3' }}</div>
    </div>

    <!-- Step 0 首屏引导 -->
    <div v-show="step===0" class="scroll-area">
      <div class="home-hero">
        <div class="home-badge">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <rect x="5" y="3.5" width="14" height="17" rx="2.2"/>
            <path d="M9.2 3.5h5.6v2.4H9.2z"/>
            <path d="M9 16.5v-3M12 16.5v-5.5M15 16.5v-2"/>
          </svg>
        </div>
        <div class="home-h1">北京中考一模&amp;二模学情分析</div>
        <div class="home-sub">拍下孩子的答题卡，AI 自动还原失分点，<br>给出每道错题的原因与提分建议</div>
      </div>

      <div class="home-flow">
        <div class="flow-item">
          <span class="flow-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3.5 9A2 2 0 0 1 5.5 7h1.6l1.1-1.7h7.6L17 7h1.5a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>
            <circle cx="12" cy="13" r="3.1"/></svg></span>拍答题卡
        </div>
        <div class="flow-link"></div>
        <div class="flow-item">
          <span class="flow-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.5 3.5l1.9 4.8 4.8 1.9-4.8 1.9-1.9 4.8-1.9-4.8L3.8 10.2 8.6 8.3z"/>
            <path d="M17.5 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg></span>AI 分析
        </div>
        <div class="flow-link"></div>
        <div class="flow-item">
          <span class="flow-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4.5 19.5h15"/><rect x="6.2" y="12" width="3" height="5.5" rx="0.7"/>
            <rect x="10.8" y="8" width="3" height="9.5" rx="0.7"/>
            <rect x="15.4" y="4.5" width="3" height="13" rx="0.7"/></svg></span>看报告
        </div>
      </div>

      <!-- 已支持范围（折叠展开）-->
      <div class="card coverage-card" v-if="coverage">
        <div class="coverage-head" @click="coverageOpen = !coverageOpen">
          <span class="coverage-icon">📋</span>
          <span class="coverage-summary">
            已支持 {{ coverage.city }} {{ coverage.total_papers }} 卷
            <span class="coverage-mini">
              ({{ coverage.subjects.length }} 科 ·
              <template v-for="(s, i) in coverage.subjects" :key="s.subject_en"><template v-if="i>0">/</template>{{ s.subject_cn }}</template>)
            </span>
          </span>
          <span class="coverage-toggle">{{ coverageOpen ? '收起 ▴' : '展开 ▾' }}</span>
        </div>
        <div v-if="coverageOpen" class="coverage-body">
          <div v-for="s in coverage.subjects" :key="s.subject_en" class="cov-subject">
            <div class="cov-subj-name">{{ s.subject_cn }}</div>
            <div v-for="t in s.by_exam_type" :key="t.exam_type_en" class="cov-type">
              <span class="cov-type-label">{{ t.exam_type_cn }}({{ t.n_districts }} 区):</span>
              <span class="cov-districts">{{ t.districts.join(' ') }}</span>
            </div>
          </div>
          <div class="cov-note">
            <div>⚠ 二模/三模、外省、2026 年以外暂未支持(陆续上新)</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="section-title" style="margin-bottom:4px">开始前请准备</div>
        <div class="section-desc" style="margin-bottom:10px">
          以物理为例：常见 4 页（2 张纸正反面）。下方为示意（脱敏）</div>
        <div class="sample-pages">
          <div class="sample-page">
            <div class="schem">
              <div class="schem-title">北京市 ⬤⬤ 区九年级综合练习（一）物理答题卡</div>
              <div class="schem-row"><span class="schem-k">姓名</span><span class="schem-blur">░░░</span>
                <span class="schem-k">准考证</span><span class="schem-blur">░░░░░</span></div>
              <div class="schem-grid"><i v-for="n in 12" :key="n"></i></div>
              <div class="schem-lines"><b></b><b></b><b></b></div>
            </div>
            <div class="cap">第 1 页 · 含标题行</div>
          </div>
          <div class="sample-page">
            <div class="schem">
              <div class="schem-lines tall"><b></b><b></b><b></b><b></b><b></b></div>
              <div class="schem-grid"><i v-for="n in 8" :key="n"></i></div>
              <div class="schem-lines"><b></b><b></b></div>
            </div>
            <div class="cap">第 2 页 · 作答区</div>
          </div>
        </div>
        <div class="prep-li" style="margin-top:10px">
          <svg class="prep-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3.5 9A2 2 0 0 1 5.5 7h1.6l1.1-1.7h7.6L17 7h1.5a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>
            <circle cx="12" cy="13" r="3.1"/></svg>
          拍全部页，必须含「考生须知页」顶部标题行（如图第 1 页）
        </div>
        <div class="prep-li">
          <svg class="prep-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3.8"/>
            <path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6 18 18M18 6l-1.4 1.4M7.4 16.6 6 18"/></svg>
          光线均匀、四角入框、字迹清晰
        </div>
        <div class="prep-li">
          <svg class="prep-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4" y="5" width="16" height="14" rx="2"/>
            <path d="M4 10h16M10 5v14"/></svg>
          小分表（可选）——没有也行，系统自动判分
        </div>
      </div>

      <div class="card sample-report" @click="openSampleReport">
        <div class="sr-ico">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M7.5 3.5h6l4.5 4.5v11a1.6 1.6 0 0 1-1.6 1.6H7.5A1.6 1.6 0 0 1 5.9 19V5.1A1.6 1.6 0 0 1 7.5 3.5z"/>
            <path d="M13.5 3.5V8h4.5"/><path d="M9 12.5h6M9 15.5h6M9 18h4"/></svg>
        </div>
        <div class="sr-txt">
          <div class="sr-h">看一份示例报告</div>
          <div class="sr-d">脱敏样例：失分诊断 + 逐题精析 + 提分建议</div>
        </div>
        <div class="sr-arrow">›</div>
      </div>

      <button class="btn btn-primary" style="width:100%;margin-top:4px"
              @click="goStart">开始分析 →</button>
    </div>

    <!-- Step 1 答题卡：上传 + 识别 + 确认 同页渐进展开 -->
    <div v-show="step===1" class="scroll-area">
      <div class="section-title">上传答题卡</div>
      <div class="section-desc">拍照或从相册选择，可多张（含「考生须知页」——上面印有考试名称）</div>

      <!-- 上传区：仅"选图"阶段显示大拖拽框 -->
      <label v-if="phase==='pick'" class="upload-area">
        <div class="big-icon">📷</div>
        <div style="font-weight:600;color:var(--gray-700)">拍照或上传图片</div>
        <div class="hint">支持 JPG/PNG/HEIC · 单张 ≤ 10 MB</div>
        <input type="file" accept="image/*" multiple hidden @change="onPick">
        <span class="btn btn-primary btn-sm" style="margin-top:12px;display:inline-flex">+ 选择文件</span>
      </label>

      <!-- 已选缩略图：所有阶段保持可见，单页连贯 -->
      <div v-if="photos.length" style="margin-top:14px">
        <div class="section-title" style="margin-bottom:6px">已选 {{ photos.length }} 张</div>
        <div class="photo-grid">
          <div v-for="(u,i) in photoUrls" :key="i" class="photo-cell" :style="{backgroundImage:`url(${u})`}">
            <div v-if="phase==='pick'" class="del" @click.stop="delPhoto(i)">×</div>
            <div class="label">{{ i+1 }}</div>
          </div>
        </div>
      </div>

      <!-- 上传/识别中：就地两步进度（缩略图仍在上方） -->
      <div v-if="phase==='uploading' || phase==='detecting'" class="card"
           style="padding:18px 16px;margin-top:14px">
        <div class="mini-steps">
          <div class="mini-step" :class="phase==='uploading' ? 'active' : 'done'">
            <span class="ms-dot">{{ phase==='uploading' ? '' : '✓' }}</span>上传图片
          </div>
          <div class="mini-line" :class="{ done: phase!=='uploading' }"></div>
          <div class="mini-step" :class="phase==='detecting' ? 'active' : ''">
            <span class="ms-dot"></span>识别考试信息
          </div>
        </div>
        <div style="text-align:center;margin-top:14px">
          <div class="spinner"></div>
          <div class="section-title" style="margin:10px 0 4px">
            {{ phase==='uploading' ? '正在上传答题卡照片…' : '正在识别考试信息…' }}</div>
          <div class="section-desc" style="margin:0">
            {{ phase==='uploading'
               ? '照片较多或网络较慢时需要几秒，请勿离开'
               : '读取顶部标题（区/科目/年份）+ 学生信息 + 卷面完整性' }}</div>
        </div>
        <div class="card" style="background:var(--brand-50);font-size:12.5px;
             color:var(--gray-600);margin:14px 0 0;padding:10px 12px">
          识别有误？用上方「+ 选择文件」重新选择，再点底部「上传并识别」。
        </div>
        <button class="btn btn-ghost btn-sm" style="width:100%;margin-top:10px"
                @click="retryUpload">重新选择图片</button>
      </div>

      <!-- 识别结果：同页展开核对 + 确认 -->
      <template v-else-if="phase==='confirm'">
        <div class="section-title" style="margin-top:18px">请核对识别结果</div>
        <div class="section-desc">下方为系统识别内容，确认无误后点底部「确认无误，下一步」</div>
        <div class="card">
          <div style="font-size:17px;font-weight:700;margin-bottom:8px">
            {{ detected?.exam_title || (detected?.year+' '+detected?.district+' '+detected?.exam_type+' '+detected?.subject) }}
          </div>
          <div style="font-size:13px;color:var(--gray-600);line-height:1.9">
            <div style="display:flex;align-items:center;gap:8px;margin:2px 0 6px">
              <span style="flex:none">学生：</span>
              <input v-model="studentName" class="name-input"
                     placeholder="请填写学生姓名" />
              <span v-if="detected?.student_id" style="flex:none;color:var(--gray-500)">
                准考证 {{ detected.student_id }}</span>
            </div>
            <div style="font-size:12px;color:var(--gray-500);margin:-4px 0 4px">
              ✏️ 姓名由系统识别，可能有误，请核对修改（将用于报告抬头）
            </div>
            <div>考试：{{ detected?.year }} 北京{{ detected?.district }} {{ detected?.exam_type }} · {{ detected?.subject }}</div>
            <div>卷面：<span :style="{color: detected?.pages_complete ? 'var(--success)' : 'var(--warning)'}">
              {{ detected?.pages_complete ? '完整 ✓' : '可能不完整 ⚠' }}</span>
              <span style="color:var(--gray-500)"> {{ detected?.completeness_note }}</span></div>
          </div>
          <button class="btn btn-outline btn-sm" style="margin-top:12px;width:100%"
                  @click="openPaper">📄 查看试卷原卷（含答案）核对</button>
        </div>
        <div v-if="detected?.precheck?.warn?.length"
             class="card" style="background:var(--warning-bg);border:1px solid var(--warning)">
          <div style="font-size:13px;font-weight:700;color:var(--gray-800);margin-bottom:6px">
            ⚠ 预检提醒（不影响继续，建议核对）</div>
          <div v-for="(w,i) in detected.precheck.warn" :key="i"
               style="font-size:12px;color:var(--gray-700);line-height:1.8">· {{ w }}</div>
        </div>
        <div class="card" style="background:var(--brand-50);font-size:13px;color:var(--gray-700)">
          请核对试卷原卷与孩子所考是否一致；不一致点下方「重新选择图片上传」重拍。
        </div>
        <button class="btn btn-ghost btn-sm" style="width:100%" @click="retryUpload">重新选择图片上传</button>
      </template>

      <!-- 识别失败：内联错误 -->
      <div v-else-if="phase==='failed'" class="card state-card state-fail"
           style="margin-top:14px">
        <div class="state-emoji">📷</div>
        <div class="section-title" style="margin:8px 0 6px">答题卡未通过检查，请重拍</div>
        <div style="font-size:13px;color:var(--gray-600);line-height:1.7;white-space:pre-line;text-align:left">{{ detectErr }}</div>
        <div style="font-size:12px;color:var(--gray-500);margin-top:12px">
          关键：拍清「考生须知页」最顶部的标题行<br>
          如「北京市朝阳区九年级综合练习（一）物理答题卡」
        </div>
      </div>
    </div>

    <!-- Step 2 小分（二选一）-->
    <div v-show="step===2" class="scroll-area">
      <div class="section-title">如何给主观题判分？</div>
      <div class="section-desc">选择题系统自动判（准）。主观题二选一：</div>

      <div class="opt-card" :class="{'is-sel': scoreMode==='teacher'}" @click="scoreMode='teacher'">
        <div class="opt-head"><span class="opt-radio"></span>
          <b>我有老师小分表</b><span class="opt-tag green">最精确</span></div>
        <div class="opt-desc">班小二等工具导出的 Excel/截图，按老师实际阅卷分逐题对齐</div>
        <div v-if="scoreMode==='teacher'" style="margin-top:10px">
          <label v-if="!scoreFile" class="upload-area" style="padding:18px">
            <div style="font-size:13px;color:var(--gray-600)">📊 点此上传小分表（.xlsx/.xls/.csv/截图）</div>
            <input type="file" accept=".xlsx,.xls,.csv,image/*" hidden @change="onScorePick">
          </label>
          <div v-else class="file-preview">
            <div class="f-icon">📊</div>
            <div class="f-info">
              <div class="f-name">{{ scoreFile.name }}</div>
              <div class="f-meta">{{ scoreInfo || '已选择，点开始分析解析' }}</div>
            </div>
            <a href="#" @click.prevent.stop="scoreFile=null" style="color:var(--error);font-size:13px">删除</a>
          </div>
        </div>
      </div>

      <div class="opt-card" :class="{'is-sel': scoreMode==='auto'}" @click="scoreMode='auto'">
        <div class="opt-head"><span class="opt-radio"></span>
          <b>没有，用 AI 自动判分</b><span class="opt-tag amber">智能估分</span></div>
        <div class="opt-desc">系统看答题卡照片对照标答给主观题估分；结果标注"估"，拿到老师小分后可再上传校准</div>
      </div>
    </div>

    <!-- Step 3 分析中 -->
    <div v-show="step===3" class="scroll-area">
      <!-- 失败态（与首屏失败卡视觉统一） -->
      <div v-if="errorMsg" class="card state-card state-fail">
        <div class="state-emoji">⚠️</div>
        <div class="section-title" style="margin:8px 0 6px">分析未能完成</div>
        <div style="font-size:13px;color:var(--gray-600);line-height:1.7">{{ errorMsg }}</div>
        <button class="btn btn-primary btn-sm" style="margin-top:16px;width:100%"
                @click="resetToStart">返回首页重试</button>
      </div>

      <div v-else class="processing">
        <div class="spinner"></div>
        <div class="section-title" style="margin-bottom:4px">正在生成学情分析…</div>
        <div class="section-desc">{{ stageName || '排队中' }}</div>

        <div class="progress-wrap">
          <div class="progress-bar" :style="{ width: progressPct + '%' }"></div>
        </div>
        <div class="eta-hint">预计 1–3 分钟，请保持页面打开 · 进度 {{ progressPct }}%</div>

        <div class="stages">
          <div v-for="(s,i) in STAGES" :key="i" class="stage-item"
               :class="i+1 < stageIdx ? 'done' : (i+1 === stageIdx ? 'active' : 'pending')">
            <div class="ico"></div><span>{{ s }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 4 报告 -->
    <div v-show="step===4 && report" class="scroll-area">
      <template v-if="report">
        <div class="src-banner" :class="report.score_source">
          <span v-if="report.score_source==='teacher'">✅ 教师小分（精确）</span>
          <span v-else>🤖 AI 自动判分 · 已对照标答，主观题为智能评分；上传小分表可校准更精确</span>
        </div>
        <div class="summary-card">
          <div class="student-name">学生：{{ report.student_name }}</div>
          <div class="exam">{{ report.exam_title }}</div>
          <div class="score-row"><span class="score">{{ report.total_scored }}</span><span class="full">/ {{ report.full_score }}</span>
            <span v-if="report.score_source==='auto'" class="est">估</span></div>
          <div class="rank-hint">得分率 {{ pct(report.rate) }}% · 失分 {{ report.lost_total }} 分</div>
        </div>
        <div class="stat-row">
          <div class="stat-cell"><div class="num">{{ correctCnt }}</div><div class="lbl">答对题数</div></div>
          <div class="stat-cell"><div class="num warn">{{ report.n_lost }}</div><div class="lbl">失分题</div></div>
          <div class="stat-cell"><div class="num bad">{{ report.lost_total }}</div><div class="lbl">失分合计</div></div>
        </div>

        <div class="section-title">📊 知识板块得分率</div>
        <div class="card">
          <div v-for="m in report.modules" :key="m.name" class="module-row">
            <div class="module-meta"><span class="name">{{ m.name }}</span>
              <span class="frac"><strong>{{ m.scored }}</strong> / {{ m.full }}（{{ pct(m.rate) }}%）</span></div>
            <div class="bar"><div :class="barClass(m.rate)" :style="{width: pct(m.rate)+'%'}"></div></div>
          </div>
        </div>

        <div class="section-title">❌ 失分题分析（{{ report.wrong_questions.length }} 题）</div>
        <div v-for="w in wrongByNum" :key="w.qid" class="wrong-q"
             :class="{ partial: w.lost < w.score }">
          <div class="qhead">
            <span><span class="qid">{{ w.qid }}</span><span class="qtype">{{ w.type_cn }} · {{ w.module_cn }}</span></span>
            <span class="lost">−{{ w.lost }} / {{ w.score }}</span>
          </div>
          <div class="kp" v-if="w.knowledge_points.length">考点：<span v-for="k in w.knowledge_points" :key="k" class="tag">{{ k }}</span></div>
          <div class="reason"><b>{{ w.error_type }}：</b>{{ w.why_wrong.join('；') }}</div>
          <div v-if="w.fix.length" class="reason" style="background:var(--brand-50);color:var(--gray-800);margin-top:4px">
            <b style="color:var(--brand-dark)">怎么改：</b>{{ w.fix.join('；') }}
          </div>
        </div>

        <div class="card">
          <div class="section-title">📄 试卷原卷</div>
          <button class="btn btn-outline btn-sm" @click="openPaper">查看本卷原卷（含答案）</button>
        </div>
      </template>
    </div>

    <!-- Step 5 选择题人工确认 -->
    <div v-show="step===5" class="scroll-area">
      <div class="card mc-intro">
        <div class="section-title" style="margin-bottom:4px">✋ 请核对选择题识别结果</div>
        <div class="section-desc">系统对部分选择题把握不足。请确认或修改后再继续，避免报告大面积判错。</div>
        <ul v-if="manual?.reliability?.reasons?.length" class="mc-reasons">
          <li v-for="(r,i) in manual.reliability.reasons" :key="i">{{ r }}</li>
        </ul>
        <div v-if="manual?.recognition_trace?.summary" class="mc-tally">
          <span class="t-red">🔴 未识别 {{ manual.recognition_trace.summary.red }}</span>
          <span class="t-yellow">🟡 请确认 {{ manual.recognition_trace.summary.yellow }}</span>
          <span class="t-green">🟢 高置信 {{ manual.recognition_trace.summary.green }}</span>
        </div>
      </div>

      <!-- 对齐：先列需确认（黄/红），高置信题折叠 -->
      <template v-if="traceQs.length">
        <div class="section-title" v-if="reviewQs.length">需你确认（{{ reviewQs.length }} 题）</div>
        <div v-for="q in reviewQs" :key="q.qid" class="card mc-q" :class="q.status">
          <div class="mc-q-head">
            <span class="mc-num">第 {{ q.qid }} 题</span>
            <span class="mc-flag" :class="q.status">{{ statusLabel(q.status) }}</span>
          </div>
          <div class="mc-reason">{{ q.reason }}</div>
          <div class="mc-dens">
            <div v-for="L in ['A','B','C','D']" :key="L" class="mc-dens-row">
              <span class="mc-dens-l">{{ L }}</span>
              <div class="mc-dens-track"><div class="mc-dens-fill" :style="{ width: densPct(q,L) + '%' }"></div></div>
            </div>
          </div>
          <div class="mc-pick">
            <button v-for="L in ['A','B','C','D']" :key="L"
                    class="mc-opt" :class="{ on: manualChoices['Q'+q.qid]===L }"
                    @click="setManual('Q'+q.qid, L)">{{ L }}</button>
          </div>
        </div>

        <button v-if="greenQs.length" class="btn btn-ghost btn-sm mc-toggle"
                @click="showAllChoices = !showAllChoices">
          {{ showAllChoices ? '收起' : ('其余 ' + greenQs.length + ' 题已高置信，点此核对') }}
        </button>
        <div v-if="showAllChoices">
          <div v-for="q in greenQs" :key="q.qid" class="card mc-q green compact">
            <div class="mc-q-head">
              <span class="mc-num">第 {{ q.qid }} 题</span>
              <span class="mc-flag green">高置信</span>
            </div>
            <div class="mc-pick">
              <button v-for="L in ['A','B','C','D']" :key="L"
                      class="mc-opt" :class="{ on: manualChoices['Q'+q.qid]===L }"
                      @click="setManual('Q'+q.qid, L)">{{ L }}</button>
            </div>
          </div>
        </div>
      </template>

      <!-- 未对齐兜底：直接列所有选择题 -->
      <template v-else>
        <div class="section-title">请逐题核对选择题（{{ plainQids.length }} 题）</div>
        <div v-for="qid in plainQids" :key="qid" class="card mc-q compact">
          <div class="mc-q-head"><span class="mc-num">{{ qid }}</span></div>
          <div class="mc-pick">
            <button v-for="L in ['A','B','C','D']" :key="L"
                    class="mc-opt" :class="{ on: manualChoices[qid]===L }"
                    @click="setManual(qid, L)">{{ L }}</button>
          </div>
        </div>
      </template>

      <button class="btn btn-primary mc-submit" :disabled="manualBusy" @click="submitManual">
        {{ manualBusy ? '提交中…' : '确认并继续分析' }}
      </button>
      <div v-if="errorMsg" class="mc-err">{{ errorMsg }}</div>
    </div>

    <!-- 底部按钮（step5 选择题确认页用页内按钮，不走通用底栏）-->
    <div v-show="step!==0 && step!==3 && step!==5" class="action-bar">
      <button v-if="step===4 || step===2" class="btn btn-ghost btn-sm btn-secondary" @click="prev">
        {{ step===4 ? '重新开始' : '上一步' }}
      </button>
      <button class="btn btn-primary" :disabled="nextDisabled" @click="onNext">
        {{ NEXT_LABEL }}
      </button>
    </div>

    <!-- 应用内 PDF 预览（不跳新标签）-->
    <div v-if="pdfView" class="pdf-overlay">
      <div class="pdf-bar">
        <div class="pdf-close" @click="closePdf">‹ 返回</div>
        <div class="pdf-title">{{ pdfView.title }}</div>
        <a v-if="pdfView.url || pdfView.downloadUrl" class="pdf-ext"
           :href="pdfView.url || pdfView.downloadUrl"
           target="_blank" rel="noopener">{{ pdfView.images ? '下载 PDF' : '新窗口' }}</a>
      </div>
      <!-- 多页 PDF 预渲染为 PNG 栈（移动端可顺畅滚动）-->
      <div v-if="pdfView.images" class="pdf-pages">
        <img v-for="(src, i) in pdfView.images" :key="i"
             :src="src" :alt="'第 ' + (i+1) + ' 页'" loading="lazy" />
      </div>
      <!-- 直接 PDF 走 iframe（真实报告/试卷）-->
      <iframe v-else class="pdf-frame" :src="pdfView.url"></iframe>
    </div>
</div>
</template>

<style>
/* 真机全屏：无模拟器外壳。移动端占满视口，桌面端居中限宽便于查看 */
.app-shell {
  display:flex; flex-direction:column;
  width:100%; min-height:100vh; min-height:100dvh;
  background:var(--bg);
}
@media (min-width:520px) {
  html, body { background:var(--gray-200); }
  .app-shell {
    max-width:480px; margin:0 auto; min-height:100vh;
    box-shadow:0 0 24px rgba(0,0,0,0.08);
  }
}
/* 旧 .hdr 蓝条已弃用（方案 B：返回按钮合入 stepper 行） */
.stepper { background:var(--surface); padding:8px 10px; display:flex;
  align-items:center; gap:6px; border-bottom:1px solid var(--gray-100);
  flex-shrink:0; position:sticky; top:0; z-index:10;
  padding-top:calc(8px + env(safe-area-inset-top)); }
.stepper-back { width:30px; height:30px; border-radius:50%;
  background:var(--gray-100); color:var(--brand); font-size:18px;
  font-weight:600; display:flex; align-items:center; justify-content:center;
  flex-shrink:0; cursor:pointer; user-select:none; line-height:1; }
.stepper-back:active { background:var(--gray-200); }
.stepper-count { color:var(--gray-500); font-size:12px; flex-shrink:0;
  padding-left:4px; }
.step { display:flex; align-items:center; gap:6px; color:var(--gray-400); font-size:12px; }
.step .dot { width:22px; height:22px; border-radius:50%; background:var(--gray-200);
  color:#fff; display:flex; align-items:center; justify-content:center;
  font-size:12px; font-weight:600; }
.step.active { color:var(--brand); font-weight:600; }
.step.active .dot { background:var(--brand); }
.step.done .dot { background:var(--success); }
.step.done .dot::before { content:'✓'; }
.step-line { flex:1; height:2px; background:var(--gray-200); margin:0 6px; }
.step-line.done { background:var(--success); }
.mini-steps { display:flex; align-items:center; justify-content:center; }
.mini-step { display:flex; align-items:center; gap:6px; font-size:12.5px;
  color:var(--gray-400); }
.mini-step .ms-dot { width:20px; height:20px; border-radius:50%;
  background:var(--gray-200); color:#fff; font-size:12px; display:flex;
  align-items:center; justify-content:center; }
.mini-step.active { color:var(--brand); font-weight:600; }
.mini-step.active .ms-dot { background:var(--brand); }
.mini-step.done { color:var(--success); }
.mini-step.done .ms-dot { background:var(--success); }
.mini-line { width:42px; height:2px; background:var(--gray-200); margin:0 8px; }
.mini-line.done { background:var(--success); }
.scroll-area { padding:16px; }
.scroll-area::-webkit-scrollbar { display:none; }
.btn { display:inline-flex; align-items:center; justify-content:center; gap:6px;
  border:none; border-radius:var(--radius-sm); padding:11px 18px; font-size:14px;
  font-weight:600; cursor:pointer; transition:all .15s var(--ease); }
.btn:active { transform:scale(0.97); }
.btn-primary { background:var(--brand); color:#fff; }
.btn-outline { background:transparent; color:var(--brand); border:1.5px solid var(--brand); }
.btn-ghost { background:var(--gray-100); color:var(--gray-700); }
.btn-sm { padding:7px 12px; font-size:13px; border-radius:var(--radius-xs); }
.card { background:var(--surface); border-radius:var(--radius); padding:14px;
  margin-bottom:12px; box-shadow:var(--shadow-sm); }
.section-title { font-size:15px; font-weight:700; color:var(--gray-800); margin-bottom:10px; }
.section-desc { color:var(--gray-500); font-size:13px; margin-bottom:12px; }
.sel { width:100%; height:42px; border:1.5px solid var(--gray-200);
  border-radius:var(--radius-sm); padding:0 12px; font-size:15px;
  background:var(--surface); color:var(--gray-900); }
.btn:disabled { opacity:.5; cursor:not-allowed; }
/* 按钮跟随内容，不固定底部 */
.action-bar { padding:4px 16px 20px;
  padding-bottom:calc(20px + env(safe-area-inset-bottom));
  display:flex; gap:10px; }
.action-bar .btn { flex:1; }
.action-bar .btn-secondary { flex:0 0 auto; }
.sample-card { background:var(--surface); border-radius:var(--radius); padding:14px;
  margin-bottom:12px; border:1px solid var(--gray-200); }
.sample-label { font-size:12px; color:var(--gray-500); margin-bottom:10px; }
.sample-pages { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.sample-page { background:var(--gray-50); border-radius:6px; overflow:hidden;
  box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.sample-page img { width:100%; display:block; }
.schem { background:#fff; padding:8px; aspect-ratio:3/4;
  display:flex; flex-direction:column; gap:6px; }
.schem-title { font-size:8px; font-weight:700; color:var(--gray-700);
  text-align:center; line-height:1.3; padding:3px;
  background:var(--brand-50); border:1px solid var(--brand-light);
  border-radius:3px; }
.schem-row { display:flex; align-items:center; gap:4px; font-size:8px;
  color:var(--gray-500); }
.schem-k { flex:none; }
.schem-blur { flex:1; height:8px; border-radius:2px;
  background:repeating-linear-gradient(90deg,var(--gray-300) 0 3px,transparent 3px 6px); }
.schem-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:3px; }
.schem-grid i { aspect-ratio:1; border:1px solid var(--gray-300);
  border-radius:50%; }
.schem-lines { display:flex; flex-direction:column; gap:4px; flex:1; }
.schem-lines.tall { gap:5px; }
.schem-lines b { height:5px; border-radius:2px; background:var(--gray-100);
  border-bottom:1px dashed var(--gray-300); }
.sample-page .cap { text-align:center; font-size:11px; padding:4px 0;
  color:var(--gray-500); background:#fff; border-top:1px solid var(--gray-100); }
.sample-tips { font-size:12px; color:var(--gray-600); margin-top:10px; line-height:1.65; }
.upload-area { display:block; background:var(--surface); border:2px dashed var(--gray-300);
  border-radius:var(--radius); padding:28px 16px; text-align:center;
  color:var(--gray-500); cursor:pointer; }
.upload-area .big-icon { font-size:40px; margin-bottom:8px; }
.upload-area .hint { font-size:12px; margin-top:4px; color:var(--gray-400); }
.photo-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-top:10px; }
.photo-cell { aspect-ratio:3/4; border-radius:6px; position:relative;
  border:1px solid var(--gray-200); background-size:cover; background-position:center; }
.photo-cell .del { position:absolute; top:3px; right:3px; background:rgba(0,0,0,.55);
  color:#fff; width:16px; height:16px; border-radius:50%; font-size:11px;
  display:flex; align-items:center; justify-content:center; cursor:pointer; }
.photo-cell .label { position:absolute; left:3px; bottom:3px; background:rgba(0,0,0,.55);
  color:#fff; font-size:9px; padding:1px 4px; border-radius:2px; }
.detected-bar { background:var(--brand-50); border:1px solid var(--brand-light);
  border-radius:var(--radius); padding:12px 14px; margin-top:14px; }
.detected-head { font-size:12px; color:var(--brand-deeper); margin-bottom:4px; }
.detected-title { font-size:14px; font-weight:600; color:var(--gray-900); }
.detected-title .ok { color:var(--success); font-size:11px; margin-left:6px; }
.detected-meta { font-size:12px; color:var(--gray-500); margin-top:4px; }
.toggle-row { display:flex; justify-content:space-between; align-items:center; padding:4px 0; }
.toggle-row .label-text { flex:1; font-size:14px; font-weight:500; color:var(--gray-800); }
.toggle-row .label-text small { display:block; font-weight:400; color:var(--gray-500); margin-top:2px; }
.switch { width:46px; height:26px; background:var(--gray-300); border-radius:13px;
  position:relative; transition:background .2s; flex-shrink:0; cursor:pointer; }
.switch::after { content:''; position:absolute; top:2px; left:2px; width:22px;
  height:22px; background:#fff; border-radius:50%; transition:transform .2s;
  box-shadow:0 1px 3px rgba(0,0,0,0.2); }
.switch.on { background:var(--success); }
.switch.on::after { transform:translateX(20px); }
.file-preview { background:var(--surface); border-radius:var(--radius); padding:12px;
  display:flex; align-items:center; gap:10px; box-shadow:var(--shadow-sm); }
.file-preview .f-icon { width:36px; height:36px; background:var(--success);
  border-radius:6px; display:flex; align-items:center; justify-content:center;
  color:#fff; font-size:18px; }
.file-preview .f-info { flex:1; min-width:0; }
.file-preview .f-name { font-weight:500; font-size:14px; }
.file-preview .f-meta { font-size:12px; color:var(--gray-500); margin-top:2px; }
.processing { padding:30px 24px; text-align:center; }
.spinner { width:56px; height:56px; border:4px solid var(--gray-200);
  border-top-color:var(--brand); border-radius:50%;
  animation:spin 1s linear infinite; margin:0 auto 18px; }
@keyframes spin { to { transform:rotate(360deg); } }
.stages { text-align:left; margin-top:18px; background:var(--surface);
  border-radius:var(--radius); padding:6px 14px; }
.stage-item { display:flex; align-items:center; gap:10px; padding:10px 0;
  font-size:14px; border-bottom:1px solid var(--gray-100); }
.stage-item:last-child { border-bottom:0; }
.stage-item .ico { width:22px; text-align:center; }
.stage-item.pending { color:var(--gray-400); }
.stage-item.pending .ico::before { content:'○'; }
.stage-item.active { color:var(--brand); font-weight:500; }
.stage-item.active .ico::before { content:'◐'; }
.stage-item.done { color:var(--gray-500); }
.stage-item.done .ico::before { content:'✓'; color:var(--success); font-weight:bold; }
.pdf-overlay { position:fixed; inset:0; z-index:50; background:var(--bg);
  display:flex; flex-direction:column; }
@media (min-width:520px) {
  .pdf-overlay { max-width:480px; margin:0 auto; }
}
.pdf-bar { display:flex; align-items:center; gap:10px; padding:12px 14px;
  background:var(--surface); border-bottom:1px solid var(--gray-200);
  flex-shrink:0; }
.pdf-close { font-size:15px; color:var(--brand); font-weight:600; cursor:pointer; }
.pdf-title { flex:1; text-align:center; font-size:15px; font-weight:700;
  color:var(--gray-900); overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; }
.pdf-ext { font-size:13px; color:var(--gray-500); text-decoration:none; }
.pdf-frame { flex:1; width:100%; border:0; background:var(--gray-100); }
.pdf-pages { flex:1; overflow-y:auto; background:var(--gray-200);
  -webkit-overflow-scrolling:touch; padding:8px; }
.pdf-pages img { display:block; width:100%; margin:0 auto 8px;
  background:#fff; box-shadow:0 1px 4px rgba(0,0,0,0.08); }
.pdf-pages img:last-child { margin-bottom:24px; }
.state-card { text-align:center; padding:28px 16px; }
.state-emoji { font-size:42px; line-height:1; }
.state-fail { border:1px solid var(--warning); background:#fff8f0; }
.progress-wrap { width:100%; height:8px; border-radius:6px;
  background:var(--gray-200); overflow:hidden; margin:18px 0 8px; }
.progress-bar { height:100%; border-radius:6px; background:var(--brand);
  transition:width .5s ease; }
.eta-hint { font-size:12px; color:var(--gray-500); margin-bottom:16px; }
.home-hero { text-align:center; padding:22px 12px 18px; }
.home-badge { width:62px; height:62px; margin:0 auto; border-radius:50%;
  background:var(--brand-50); color:#5E8DEA;
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 0 0 7px rgba(94,141,234,0.05); }
.home-badge svg { width:30px; height:30px; }
.home-h1 { font-size:21px; font-weight:800; color:var(--gray-900); margin:15px 0 8px; }
.home-sub { font-size:13px; color:var(--gray-600); line-height:1.7; }
.home-flow { display:flex; align-items:flex-start; justify-content:space-between;
  background:var(--brand-50); border-radius:var(--radius); padding:15px 6px;
  margin-bottom:14px; }
.flow-item { display:flex; flex-direction:column; align-items:center; gap:7px;
  font-size:12px; color:var(--gray-600); flex:1; text-align:center; }
.flow-ico { width:38px; height:38px; border-radius:12px;
  background:var(--surface); color:#5E8DEA;
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 1px 3px rgba(30,58,138,0.07); }
.flow-ico svg { width:21px; height:21px; }
.flow-link { flex:0 0 14px; height:2px; margin-top:18px;
  background:repeating-linear-gradient(90deg,#C7D9F5 0 4px,transparent 4px 7px); }
.coverage-card { padding:10px 14px; }
.coverage-head { display:flex; align-items:center; gap:8px; cursor:pointer;
  user-select:none; }
.coverage-icon { font-size:16px; flex:none; }
.coverage-summary { flex:1; font-size:13px; color:var(--gray-800);
  font-weight:600; line-height:1.5; }
.coverage-mini { font-weight:400; color:var(--gray-500); font-size:12px; }
.coverage-toggle { font-size:12px; color:#5E8DEA; flex:none; }
.coverage-body { margin-top:10px; padding-top:10px;
  border-top:1px dashed var(--gray-200); }
.cov-subject { margin-bottom:8px; }
.cov-subj-name { font-size:13px; font-weight:700; color:var(--gray-900);
  margin-bottom:3px; }
.cov-type { font-size:12px; color:var(--gray-700); line-height:1.7;
  padding-left:8px; }
.cov-type-label { color:var(--gray-500); margin-right:4px; }
.cov-districts { color:var(--gray-700); }
.cov-note { margin-top:8px; padding-top:8px; border-top:1px dashed var(--gray-200);
  font-size:11px; color:var(--gray-500); line-height:1.7; }
.prep-li { display:flex; align-items:flex-start; gap:9px;
  font-size:13px; color:var(--gray-700); line-height:1.55; padding:6px 0; }
.prep-ico { width:18px; height:18px; flex:none; color:#8FA9D8; margin-top:1px; }
.sample-report { display:flex; align-items:center; gap:12px; cursor:pointer; }
.sample-report:active { background:var(--brand-50); }
.sr-ico { width:38px; height:38px; flex:none; border-radius:10px;
  background:var(--brand-50); color:#5E8DEA;
  display:flex; align-items:center; justify-content:center; }
.sr-ico svg { width:21px; height:21px; }
.sr-txt { flex:1; min-width:0; }
.sr-h { font-size:14px; font-weight:700; color:var(--gray-900); }
.sr-d { font-size:12px; color:var(--gray-500); margin-top:2px; }
.sr-arrow { flex:none; color:var(--gray-400); font-size:18px; }
.name-input { flex:1; min-width:0; font-size:15px; font-weight:700;
  color:var(--gray-900); padding:7px 10px; border:1.5px solid var(--brand-light);
  border-radius:8px; background:var(--brand-50); outline:none; }
.name-input:focus { border-color:var(--brand); background:var(--surface); }
.opt-card { background:var(--surface); border:1.5px solid var(--gray-200);
  border-radius:var(--radius); padding:14px; margin-bottom:12px; cursor:pointer;
  transition:border-color .15s,background .15s; }
.opt-card.is-sel { border-color:var(--brand); background:var(--brand-50); }
.opt-head { display:flex; align-items:center; gap:8px; font-size:15px; }
.opt-radio { width:16px; height:16px; border-radius:50%;
  border:2px solid var(--gray-300); flex-shrink:0; }
.opt-card.is-sel .opt-radio { border-color:var(--brand);
  background:radial-gradient(var(--brand) 40%, transparent 45%); }
.opt-tag { margin-left:auto; font-size:11px; padding:2px 8px; border-radius:8px; }
.opt-tag.green { background:var(--success-bg); color:#15803d; }
.opt-tag.amber { background:var(--accent-bg); color:#b45309; }
.opt-desc { font-size:12px; color:var(--gray-500); margin-top:6px; line-height:1.6; }
.src-banner { font-size:12px; padding:8px 12px; border-radius:var(--radius-sm);
  margin-bottom:10px; line-height:1.5; }
.src-banner.teacher { background:var(--success-bg); color:#15803d; }
.src-banner.auto { background:var(--accent-bg); color:#b45309; }
.summary-card .est { font-size:11px; background:rgba(255,255,255,.25); color:#fff;
  padding:1px 6px; border-radius:8px; align-self:center; }
.summary-card { background:linear-gradient(135deg,var(--brand-deeper),var(--brand));
  color:#fff; border-radius:var(--radius); padding:18px; margin-bottom:12px; }
.summary-card .student-name { font-size:13px; opacity:.9; }
.summary-card .exam { font-size:13px; opacity:.85; margin-top:2px; }
.summary-card .score-row { display:flex; align-items:baseline; gap:6px; margin-top:12px; }
.summary-card .score { font-size:36px; font-weight:700; }
.summary-card .full { font-size:15px; opacity:.7; }
.summary-card .rank-hint { font-size:12px; opacity:.85; margin-top:6px; }
.stat-row { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:12px; }
.stat-cell { background:var(--surface); border-radius:var(--radius-sm);
  padding:12px 8px; text-align:center; box-shadow:var(--shadow-sm); }
.stat-cell .num { font-size:22px; font-weight:700; }
.stat-cell .num.warn { color:var(--warning); }
.stat-cell .num.bad { color:var(--error); }
.stat-cell .lbl { font-size:11px; color:var(--gray-500); margin-top:2px; }
.module-row { margin-bottom:10px; }
.module-row:last-child { margin-bottom:0; }
.module-meta { display:flex; justify-content:space-between; font-size:13px; margin-bottom:4px; }
.module-meta .name { font-weight:500; color:var(--gray-800); }
.module-meta .frac { color:var(--gray-500); }
.module-meta .frac strong { color:var(--gray-900); }
.bar { width:100%; height:6px; background:var(--gray-100); border-radius:3px; overflow:hidden; }
.bar > div { height:100%; border-radius:3px; }
.bar > .green { background:var(--success); }
.bar > .yellow { background:var(--warning); }
.bar > .red { background:var(--error); }
.wrong-q { background:var(--surface); border-radius:var(--radius); padding:14px;
  margin-bottom:10px; border-left:3px solid var(--error); box-shadow:var(--shadow-sm); }
.wrong-q.partial { border-left-color:var(--warning); }
.wrong-q .qhead { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }
.wrong-q .qid { font-size:14px; font-weight:600; }
.wrong-q .qtype { font-size:11px; background:var(--gray-100); color:var(--gray-500);
  padding:1px 6px; border-radius:3px; margin-left:6px; }
.wrong-q .lost { font-size:12px; color:var(--error); font-weight:600; }
.wrong-q .kp { font-size:12px; color:var(--gray-600); margin-bottom:6px; }
.wrong-q .kp .tag { display:inline-block; background:var(--brand-50);
  color:var(--brand); padding:1px 6px; border-radius:3px; margin-right:4px; font-size:11px; }
.wrong-q .reason { font-size:13px; color:var(--gray-800); background:var(--accent-bg);
  padding:8px 10px; border-radius:6px; margin-top:6px; }
.wrong-q .reason b { color:#B45309; }

/* ---- step5 选择题人工确认 ---- */
.mc-intro { background:var(--warning-bg); border:1px solid var(--warning); }
.mc-reasons { margin:8px 0 0; padding-left:18px; font-size:12.5px; color:var(--gray-700); }
.mc-reasons li { margin:2px 0; }
.mc-tally { display:flex; gap:12px; margin-top:10px; font-size:12.5px; font-weight:600; }
.mc-tally .t-red { color:var(--error); }
.mc-tally .t-yellow { color:#B45309; }
.mc-tally .t-green { color:var(--success); }
.mc-q { border-left:3px solid var(--gray-200); }
.mc-q.yellow { border-left-color:var(--warning); }
.mc-q.red { border-left-color:var(--error); }
.mc-q.green { border-left-color:var(--success); }
.mc-q.compact { padding:10px 14px; }
.mc-q-head { display:flex; align-items:center; gap:8px; }
.mc-num { font-size:14px; font-weight:600; }
.mc-flag { font-size:11px; padding:1px 7px; border-radius:10px; font-weight:600; }
.mc-flag.yellow { background:var(--warning-bg); color:#B45309; }
.mc-flag.red { background:#FEE2E2; color:var(--error); }
.mc-flag.green { background:#DCFCE7; color:var(--success); }
.mc-reason { font-size:12.5px; color:var(--gray-600); margin:6px 0 8px; line-height:1.6; }
.mc-dens { margin:8px 0; }
.mc-dens-row { display:flex; align-items:center; gap:8px; margin:3px 0; }
.mc-dens-l { width:14px; font-size:12px; color:var(--gray-500); font-weight:600; }
.mc-dens-track { flex:1; height:8px; background:var(--gray-100); border-radius:4px; overflow:hidden; }
.mc-dens-fill { height:100%; background:var(--brand); border-radius:4px; transition:width .2s; }
.mc-pick { display:flex; gap:8px; margin-top:8px; }
.mc-opt { flex:1; height:42px; border:1.5px solid var(--gray-200); background:var(--surface);
  border-radius:10px; font-size:16px; font-weight:600; color:var(--gray-700);
  cursor:pointer; user-select:none; transition:all .12s; }
.mc-opt:active { transform:scale(0.96); }
.mc-opt.on { background:var(--brand); border-color:var(--brand); color:#fff;
  box-shadow:0 2px 8px rgba(37,99,235,0.25); }
.mc-toggle { width:100%; margin:2px 0 10px; }
.mc-submit { width:100%; margin-top:8px; }
.mc-err { color:var(--error); font-size:13px; text-align:center; margin-top:10px; }
</style>
