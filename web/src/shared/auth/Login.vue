<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { sendCode, verifyCode } from './auth'

// 各模块自传简介(标题/一句话/能力点/脚注),登录组件本身通用。
export interface Intro { title: string; tagline: string; feats: string[]; note?: string }
defineProps<{ intro: Intro }>()
const emit = defineEmits<{ (e: 'logged-in'): void }>()

const mode = ref<'phone' | 'email'>('phone')   // 登录方式:手机号 / 邮箱
const phone = ref('')
const email = ref('')
const code = ref('')
const agree = ref(false)
const sending = ref(false)
const submitting = ref(false)
const err = ref('')
const cooldown = ref(0)
let timer: number | undefined

// 归一化：去空格/横线，去掉 +86 / 86 国家码 → 纯 11 位号码
function normPhone(raw: string): string {
  let s = (raw || '').replace(/\D/g, '')
  if (s.length === 13 && s.startsWith('86')) s = s.slice(2)
  return s
}
const cleanPhone = computed(() => normPhone(phone.value))
const phoneOk = computed(() => /^1[3-9]\d{9}$/.test(cleanPhone.value))
const emailOk = computed(() => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim()))
// 提交给后端的账号(后端自动识别手机号/邮箱)
const account = computed(() => mode.value === 'phone' ? cleanPhone.value : email.value.trim())
const accountOk = computed(() => mode.value === 'phone' ? phoneOk.value : emailOk.value)
const canSend = computed(() => accountOk.value && cooldown.value === 0 && !sending.value)
const canLogin = computed(() => accountOk.value && /^\d{4,6}$/.test(code.value.trim()) && agree.value && !submitting.value)

function switchMode(m: 'phone' | 'email') {   // 切换方式:清掉验证码/错误/冷却,避免错配
  if (mode.value === m) return
  mode.value = m; code.value = ''; err.value = ''
  cooldown.value = 0; if (timer) clearInterval(timer)
}

function startCooldown(sec: number) {
  cooldown.value = sec
  if (timer) clearInterval(timer)
  timer = window.setInterval(() => {
    if (--cooldown.value <= 0) { clearInterval(timer); cooldown.value = 0 }
  }, 1000)
}
onUnmounted(() => timer && clearInterval(timer))

async function onSend() {
  err.value = ''
  if (sending.value || cooldown.value > 0) return     // 防重复点击/冷却中
  if (!accountOk.value) { err.value = mode.value === 'phone' ? '请输入正确的手机号' : '请输入正确的邮箱'; return }
  if (!agree.value) { err.value = '请先阅读并勾选下方隐私说明'; return }
  sending.value = true
  startCooldown(60)                                    // 点击即进入冷却，成功与否都挡住 60s
  try {
    const r = await sendCode(account.value)
    if (r.cooldown) startCooldown(r.cooldown)
  } catch (e: any) {
    cooldown.value = 0                                 // 发送失败放开，允许立即重试
    err.value = e.message || '发送失败'
  } finally {
    sending.value = false
  }
}

async function onLogin() {
  err.value = ''
  if (submitting.value) return
  submitting.value = true
  try {
    await verifyCode(account.value, code.value.trim())
    emit('logged-in')
  } catch (e: any) {
    err.value = e.message || '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="card">
      <div class="intro">
        <h1>{{ intro.title }}</h1>
        <p class="tag">{{ intro.tagline }}</p>
        <ul class="feats">
          <li v-for="(f, i) in intro.feats" :key="i" v-html="f"></li>
        </ul>
        <p v-if="intro.note" class="note">{{ intro.note }}</p>
      </div>

      <div class="form">
        <h2>登录 / 注册</h2>
        <div class="mode-tabs">
          <button type="button" :class="{ on: mode === 'phone' }" @click="switchMode('phone')">手机号</button>
          <button type="button" :class="{ on: mode === 'email' }" @click="switchMode('email')">邮箱</button>
        </div>
        <label v-if="mode === 'phone'" class="fld">
          <span>手机号</span>
          <input v-model="phone" type="tel" maxlength="18" inputmode="tel"
                 placeholder="请输入手机号（支持 +86）" autocomplete="tel" />
        </label>
        <label v-else class="fld">
          <span>邮箱</span>
          <input v-model="email" type="email" maxlength="64" inputmode="email"
                 placeholder="请输入邮箱地址" autocomplete="email" />
        </label>
        <label class="fld">
          <span>验证码</span>
          <div class="code-row">
            <input v-model="code" type="text" maxlength="6" inputmode="numeric"
                   :placeholder="mode === 'phone' ? '短信验证码' : '邮件验证码'" autocomplete="one-time-code" />
            <button type="button" class="send-btn" :disabled="!canSend" @click="onSend">
              {{ cooldown > 0 ? cooldown + 's' : (sending ? '发送中…' : '获取验证码') }}
            </button>
          </div>
        </label>

        <p v-if="err" class="err">{{ err }}</p>

        <button type="button" class="login-btn" :disabled="!canLogin" @click="onLogin">
          {{ submitting ? '登录中…' : '登录 / 注册' }}
        </button>

        <label class="agree">
          <input type="checkbox" v-model="agree" />
          <span>我已阅读并同意：仅收集手机号及本工具所需信息（如成绩/答题卡），用于志愿匹配或学情分析，不作他用。</span>
        </label>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login { min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 16px; background: linear-gradient(135deg, #eef2ff, #f7fafc); }
.card { width: 100%; max-width: 860px; background: #fff; border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0,0,0,.10); overflow: hidden; display: grid;
  grid-template-columns: 1.1fr 1fr; }
.intro { padding: 32px 28px; background: linear-gradient(160deg, #1e3a8a, #2563eb); color: #fff; }
.intro h1 { font-size: 22px; margin: 0 0 8px; line-height: 1.3; }
.tag { font-size: 13.5px; opacity: .92; margin: 0 0 18px; line-height: 1.6; }
.feats { list-style: none; padding: 0; margin: 0 0 16px; }
.feats li { font-size: 13px; line-height: 1.6; padding: 6px 0 6px 20px; position: relative; opacity: .95; }
.feats li::before { content: '✓'; position: absolute; left: 0; color: #93c5fd; font-weight: 700; }
.feats b { color: #fff; }
.note { font-size: 11.5px; opacity: .8; margin: 0; }
.form { padding: 32px 28px; display: flex; flex-direction: column; }
.form h2 { font-size: 18px; margin: 0 0 16px; color: #111827; }
.mode-tabs { display: flex; gap: 6px; margin-bottom: 16px; }
.mode-tabs button { flex: 1; height: 36px; border: 1px solid #d1d5db; background: #fff;
  color: #6b7280; border-radius: 8px; font-size: 13.5px; cursor: pointer; }
.mode-tabs button.on { border-color: #2563eb; color: #2563eb; background: #eff6ff; font-weight: 600; }
.fld { display: block; margin-bottom: 14px; }
.fld > span { display: block; font-size: 12px; color: #6b7280; margin-bottom: 6px; }
.fld input { width: 100%; box-sizing: border-box; height: 42px; padding: 0 12px;
  border: 1px solid #d1d5db; border-radius: 8px; font-size: 16px; outline: none; }
.fld input:focus { border-color: #2563eb; }
.code-row { display: flex; gap: 8px; }
.code-row input { flex: 1; }
.send-btn { flex: 0 0 auto; padding: 0 14px; height: 42px; border: 1px solid #2563eb;
  background: #fff; color: #2563eb; border-radius: 8px; font-size: 13px; cursor: pointer;
  white-space: nowrap; }
.send-btn:disabled { border-color: #d1d5db; color: #9ca3af; cursor: not-allowed; }
.login-btn { height: 44px; margin-top: 6px; border: none; border-radius: 8px;
  background: #2563eb; color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; }
.login-btn:disabled { background: #93b4f0; cursor: not-allowed; }
.err { color: #dc2626; font-size: 12.5px; margin: 0 0 10px; }
.agree { display: flex; gap: 8px; align-items: flex-start; margin-top: 16px;
  font-size: 11.5px; color: #6b7280; line-height: 1.5; cursor: pointer; }
.agree input { margin-top: 2px; flex: 0 0 auto; }
@media (max-width: 640px) {
  .card { grid-template-columns: 1fr; max-width: 440px; }
  .intro { padding: 24px 20px; }
  .intro h1 { font-size: 20px; }
  .form { padding: 24px 20px; }
}
</style>
