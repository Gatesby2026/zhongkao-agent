<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { sendSms, verifySms } from './auth'

const emit = defineEmits<{ (e: 'logged-in'): void }>()

const phone = ref('')
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
const canSend = computed(() => phoneOk.value && cooldown.value === 0 && !sending.value)
const canLogin = computed(() => phoneOk.value && /^\d{4,6}$/.test(code.value.trim()) && agree.value && !submitting.value)

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
  if (!phoneOk.value) { err.value = '请输入正确的手机号'; return }
  if (!agree.value) { err.value = '请先阅读并勾选下方隐私说明'; return }
  sending.value = true
  startCooldown(60)                                    // 点击即进入冷却，成功与否都挡住 60s
  try {
    const r = await sendSms(cleanPhone.value)
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
    await verifySms(cleanPhone.value, code.value.trim())
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
        <h1>北京中考志愿参考 · 朝阳</h1>
        <p class="tag">按区排名做冲稳保匹配，给一份有依据、能落地的志愿草表。</p>
        <ul class="feats">
          <li><b>冲稳保推荐</b>：用你的区排名对齐各校 2026 预估录取位次</li>
          <li><b>通勤距离</b>：高德路网算到家的真实骑行/驾车里程</li>
          <li><b>校额到校 · 市级统筹</b>：按朝阳口径研判值不值得用</li>
          <li><b>查学校</b>：统招线、高考出口、班型特色一站浏览</li>
        </ul>
        <p class="note">仅辅助参考，最终以官方招生简章与老师建议为准。</p>
      </div>

      <div class="form">
        <h2>手机号登录</h2>
        <label class="fld">
          <span>手机号</span>
          <input v-model="phone" type="tel" maxlength="18" inputmode="tel"
                 placeholder="请输入手机号（支持 +86）" autocomplete="tel" />
        </label>
        <label class="fld">
          <span>验证码</span>
          <div class="code-row">
            <input v-model="code" type="text" maxlength="6" inputmode="numeric"
                   placeholder="短信验证码" autocomplete="one-time-code" />
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
          <span>我已阅读并同意：仅收集手机号、家庭住址、初中校等用于本工具的志愿匹配与距离计算，不作他用。</span>
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
.form h2 { font-size: 18px; margin: 0 0 20px; color: #111827; }
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
