<script setup lang="ts">
// 头像账号菜单:默认只显示头像图标,点击弹出 脱敏账号 + 退出登录。志愿/学情共用。
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchMe, logout } from './auth'

const props = defineProps<{ appName?: string }>()
const phone = ref('')
const email = ref('')
const open = ref(false)

const has = computed(() => !!(phone.value || email.value))
const label = computed(() =>
  phone.value ? phone.value.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2') : email.value)

async function load() {
  const me = await fetchMe(props.appName).catch(() => null)
  if (me?.user) { phone.value = me.user.phone || ''; email.value = me.user.email || '' }
}
async function doLogout() { try { await logout() } finally { location.reload() } }
function onDoc(e: Event) {
  if (!(e.target as HTMLElement).closest('.acctm')) open.value = false
}
onMounted(() => { load(); document.addEventListener('click', onDoc) })
onUnmounted(() => document.removeEventListener('click', onDoc))
</script>

<template>
  <div v-if="has" class="acctm">
    <button type="button" class="acctm-av" :class="{ on: open }" @click.stop="open = !open" aria-label="账号">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="8" r="3.6" /><path d="M5 19.5c1.3-3 4-4.5 7-4.5s5.7 1.5 7 4.5" />
      </svg>
    </button>
    <div v-if="open" class="acctm-pop">
      <div class="acctm-id">{{ label }}</div>
      <button type="button" class="acctm-out" @click="doLogout">退出登录</button>
    </div>
  </div>
</template>

<style scoped>
.acctm { position: relative; display: inline-flex; }
.acctm-av { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--gray-300, #d1d5db);
  background: #fff; color: var(--gray-600, #4b5563); display: inline-flex; align-items: center;
  justify-content: center; cursor: pointer; padding: 0; }
.acctm-av svg { width: 19px; height: 19px; }
.acctm-av.on, .acctm-av:hover { border-color: var(--brand, #2563eb); color: var(--brand, #2563eb); }
.acctm-pop { position: absolute; top: 40px; right: 0; z-index: 1600; min-width: 150px;
  background: #fff; border: 1px solid var(--gray-200, #e5e7eb); border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,.14); padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.acctm-id { font-size: 13px; font-weight: 600; color: var(--gray-800, #1f2937); text-align: center;
  padding-bottom: 8px; border-bottom: 1px solid var(--gray-100, #f3f4f6); word-break: break-all; }
.acctm-out { height: 34px; border: none; border-radius: 8px; background: var(--brand, #2563eb);
  color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; }
</style>
