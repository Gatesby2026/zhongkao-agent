<script setup lang="ts">
// 硬门槛:未登录只见登录页,登录后才进主应用。
import { ref, onMounted } from 'vue'
import Login from './Login.vue'
import Zhiyuan from './Zhiyuan.vue'
import { fetchMe } from './auth'

const ready = ref(false)
const authed = ref(false)

async function check() {
  const me = await fetchMe().catch(() => null)
  authed.value = !!me
  ready.value = true
}
onMounted(check)
</script>

<template>
  <div v-if="!ready" class="splash">加载中…</div>
  <Login v-else-if="!authed" @logged-in="authed = true" />
  <Zhiyuan v-else />
</template>

<style scoped>
.splash { min-height: 100vh; display: flex; align-items: center; justify-content: center;
  color: #6b7280; font-size: 14px; }
</style>
