<script setup lang="ts">
// 通用登录网关:未登录只见 Login(带本模块简介),登录后渲染 <slot/>。
// 志愿/学情两模块共用;同域 Cookie → 一处登录两端通用。
import { ref, onMounted } from 'vue'
import Login, { type Intro } from './Login.vue'
import { fetchMe } from './auth'

const props = defineProps<{ appName?: string; intro: Intro }>()

const ready = ref(false)
const authed = ref(false)

async function check() {
  const me = await fetchMe(props.appName).catch(() => null)
  authed.value = !!me
  ready.value = true
}
onMounted(check)
</script>

<template>
  <div v-if="!ready" class="splash">加载中…</div>
  <Login v-else-if="!authed" :intro="intro" @logged-in="authed = true" />
  <slot v-else />
</template>

<style scoped>
.splash { min-height: 100vh; display: flex; align-items: center; justify-content: center;
  color: #6b7280; font-size: 14px; }
</style>
