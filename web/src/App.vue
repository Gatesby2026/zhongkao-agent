<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { api, type ReportResp } from './api'

const step = ref(1)                       // 1 上传 2 小分 3 分析 4 报告
const analysisId = ref<string | null>(null)
const photos = ref<File[]>([])
const photoUrls = ref<string[]>([])
const scoresEnabled = ref(true)
const scoreFile = ref<File | null>(null)
const stageIdx = ref(0)
const stageName = ref('')
const report = ref<ReportResp | null>(null)
const errorMsg = ref('')
let pollTimer: number | undefined

const STAGES = [
  '识别考试信息（区/科目/年份）',
  '识别答题卡作答',
  '对照标准答案，标注失分题',
  'AI 分析失分主因',
  '生成知识点提分建议',
]
const NEXT_LABEL = ['', '下一步', '开始分析', '请稍候…', '下载报告 PDF']

const stepperSteps = ['答题卡', '小分', '分析']
function stepState(n: number) {
  return n < step.value ? 'done' : (n === step.value ? 'active' : '')
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

async function next() {
  errorMsg.value = ''
  if (step.value === 1) {
    // 创建分析（后台任务即刻启动）
    try {
      const r = await api.createAnalysis(photos.value)
      analysisId.value = r.id
    } catch (e: any) { errorMsg.value = '创建分析失败：' + e.message; return }
    step.value = 2
  } else if (step.value === 2) {
    if (scoresEnabled.value && scoreFile.value && analysisId.value) {
      try { await api.uploadScores(analysisId.value, scoreFile.value) } catch {}
    }
    step.value = 3
    startPolling()
  } else if (step.value === 4) {
    if (analysisId.value)
      window.open(api.reportPdfUrl(analysisId.value), '_blank')
  }
}
function prev() {
  if (step.value === 4) { resetToStart(); return }
  if (step.value > 1 && step.value !== 3) step.value--
}
function resetToStart() {
  step.value = 1
  report.value = null
  stageIdx.value = 0
}

function startPolling() {
  if (!analysisId.value) return
  const id = analysisId.value
  const tick = async () => {
    try {
      const s = await api.status(id)
      stageIdx.value = s.stage
      stageName.value = s.stage_name
      if (s.status === 'done') {
        clearInterval(pollTimer)
        report.value = await api.report(id)
        step.value = 4
      } else if (s.status === 'failed') {
        clearInterval(pollTimer)
        errorMsg.value = '分析失败：' + s.error
      }
    } catch (e: any) { /* 网络抖动忽略，下次轮询继续 */ }
  }
  tick()
  pollTimer = window.setInterval(tick, 2000)
}
onUnmounted(() => clearInterval(pollTimer))

function openPaper() {
  if (analysisId.value)
    window.open(api.paperPdfUrl(analysisId.value), '_blank')
}

const pct = (r: number) => Math.round(r * 100)
const barClass = (r: number) => r >= 0.8 ? 'green' : (r >= 0.6 ? 'yellow' : 'red')
const correctCnt = computed(() =>
  report.value ? report.value.n_questions - report.value.n_lost : 0)
</script>

<template>
<div class="app-shell">
    <div class="hdr">
      <div class="hdr-back" @click="prev">‹</div>
      <div class="hdr-title">北京中考一模试卷学情分析</div>
      <div class="hdr-right">{{ step <= 3 ? step + '/3' : '完成' }}</div>
    </div>

    <div class="stepper">
      <template v-for="(nm, i) in stepperSteps" :key="i">
        <div class="step" :class="stepState(i+1)">
          <div class="dot"><span v-if="stepState(i+1)!=='done'">{{ i+1 }}</span></div>{{ nm }}
        </div>
        <div v-if="i < 2" class="step-line" :class="{ done: i+1 < step }"></div>
      </template>
    </div>

    <!-- Step 1 上传答题卡 -->
    <div v-show="step===1" class="scroll-area">
      <div class="section-title">上传答题卡</div>
      <div class="section-desc">拍照或从相册选择，可上传多张（每张照片对应答题卡一页）</div>

      <div class="sample-card">
        <div class="sample-label">📋 示例：物理常见 4 页（2 张纸正反面）</div>
        <div class="sample-pages">
          <div class="sample-page"><img src="/sample-card-page1.jpg"><div class="cap">第 1 页</div></div>
          <div class="sample-page"><img src="/sample-card-page2.jpg"><div class="cap">第 2 页</div></div>
        </div>
        <div class="sample-tips">✓ 光线均匀，避免阴影<br>✓ 四角定位标尽量入框<br>✓ 文字、涂卡清晰可读</div>
      </div>

      <label class="upload-area">
        <div class="big-icon">📷</div>
        <div style="font-weight:600;color:var(--gray-700)">拍照或上传图片</div>
        <div class="hint">支持 JPG/PNG/HEIC · 单张 ≤ 10 MB</div>
        <input type="file" accept="image/*" multiple hidden @change="onPick">
        <span class="btn btn-primary btn-sm" style="margin-top:12px;display:inline-flex">+ 选择文件</span>
      </label>

      <div v-if="photos.length" style="margin-top:14px">
        <div class="section-title" style="margin-bottom:6px">已上传 {{ photos.length }} 张</div>
        <div class="photo-grid">
          <div v-for="(u,i) in photoUrls" :key="i" class="photo-cell" :style="{backgroundImage:`url(${u})`}">
            <div class="del" @click.stop="delPhoto(i)">×</div>
            <div class="label">{{ i+1 }}</div>
          </div>
        </div>
        <div class="detected-bar">
          <div class="detected-head">🔍 上传后将自动识别考试信息</div>
          <div class="detected-title">2026 北京朝阳区初三一模 · 物理 <span class="ok">（reference 演示数据）</span></div>
          <div class="detected-meta">点「下一步」创建分析任务</div>
        </div>
      </div>
    </div>

    <!-- Step 2 小分 -->
    <div v-show="step===2" class="scroll-area">
      <div class="section-title">上传小分表（可选）</div>
      <div class="section-desc">学校通过班小二等工具发的 Excel 小分表，对齐到每道题得分；可跳过仅用答题卡结果。</div>
      <div class="card">
        <div class="toggle-row">
          <div class="label-text">启用小分对齐<small>关闭则跳过此步</small></div>
          <div class="switch" :class="{on:scoresEnabled}" @click="scoresEnabled=!scoresEnabled"></div>
        </div>
      </div>
      <div v-show="scoresEnabled">
        <label v-if="!scoreFile" class="upload-area">
          <div class="big-icon">📊</div>
          <div style="font-weight:600;color:var(--gray-700)">上传小分表文件</div>
          <div class="hint">支持 .xlsx / .xls / .csv / 截图</div>
          <input type="file" accept=".xlsx,.xls,.csv,image/*" hidden @change="onScorePick">
          <span class="btn btn-primary btn-sm" style="margin-top:12px;display:inline-flex">+ 选择文件</span>
        </label>
        <div v-else class="file-preview">
          <div class="f-icon">📊</div>
          <div class="f-info">
            <div class="f-name">{{ scoreFile.name }}</div>
            <div class="f-meta">已选择 · Phase 1 演示使用 reference 小分</div>
          </div>
          <a href="#" @click.prevent="scoreFile=null" style="color:var(--error);font-size:13px">删除</a>
        </div>
      </div>
    </div>

    <!-- Step 3 分析中 -->
    <div v-show="step===3" class="scroll-area">
      <div class="processing">
        <div class="spinner"></div>
        <div class="section-title" style="margin-bottom:4px">正在生成学情分析…</div>
        <div class="section-desc">{{ stageName || '排队中' }}</div>
        <div class="stages">
          <div v-for="(s,i) in STAGES" :key="i" class="stage-item"
               :class="i+1 < stageIdx ? 'done' : (i+1 === stageIdx ? 'active' : 'pending')">
            <div class="ico"></div><span>{{ s }}</span>
          </div>
        </div>
        <div v-if="errorMsg" style="color:var(--error);margin-top:14px;font-size:13px">{{ errorMsg }}</div>
      </div>
    </div>

    <!-- Step 4 报告 -->
    <div v-show="step===4 && report" class="scroll-area">
      <template v-if="report">
        <div class="summary-card">
          <div class="student-name">学生：{{ report.student_name }}</div>
          <div class="exam">{{ report.exam_title }}</div>
          <div class="score-row"><span class="score">{{ report.total_scored }}</span><span class="full">/ {{ report.full_score }}</span></div>
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
        <div v-for="w in report.wrong_questions" :key="w.qid" class="wrong-q"
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

    <!-- 底部按钮 -->
    <div v-show="step!==3" class="action-bar">
      <button v-if="step>1 && step!==3" class="btn btn-ghost btn-sm btn-secondary" @click="prev">
        {{ step===4 ? '重新分析' : '上一步' }}
      </button>
      <button class="btn btn-primary" @click="next">{{ NEXT_LABEL[step] }}</button>
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
.hdr { position:sticky; top:0; z-index:10; height:var(--header-h);
  background:var(--brand-deeper); display:flex;
  align-items:center; padding:0 14px; gap:10px; flex-shrink:0;
  padding-top:env(safe-area-inset-top); box-sizing:content-box; }
.hdr-back { width:30px; height:30px; border-radius:50%;
  background:rgba(255,255,255,.12); display:flex; align-items:center;
  justify-content:center; color:#fff; font-size:16px; }
.hdr-title { color:#fff; font-size:16px; font-weight:600; flex:1; text-align:center; }
.hdr-right { color:rgba(255,255,255,.85); font-size:12px; }
.stepper { background:var(--surface); padding:10px 16px; display:flex;
  align-items:center; border-bottom:1px solid var(--gray-100); flex-shrink:0; }
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
.scroll-area { flex:1; padding:16px; }
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
.action-bar { position:sticky; bottom:0; flex-shrink:0; padding:10px 16px;
  padding-bottom:calc(10px + env(safe-area-inset-bottom));
  background:var(--surface); border-top:1px solid var(--gray-200);
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
</style>
