<script setup lang="ts">
// 学情模块入口:登录网关 + 学情主应用。
import AuthGate from './shared/auth/AuthGate.vue'
import type { Intro } from './shared/auth/Login.vue'
import Xueqing from './views/Xueqing.vue'

const intro: Intro = {
  title: '北京中考 一模·二模 学情分析',
  tagline: '上传答题卡，自动诊断失分，给出逐题精析与提分计划。',
  feats: [
    '<b>答题卡识别</b>：拍照上传，自动识别考试信息与作答',
    '<b>失分诊断</b>：对照标准答案逐题标注，分析失分主因',
    '<b>提分计划</b>：按知识点给出针对性巩固建议',
    '<b>历史报告</b>：登录后每次分析自动留存，换设备也能查',
  ],
  note: '仅辅助参考，具体以学校老师讲评为准。',
}
</script>

<template>
  <AuthGate app-name="xueqing" :intro="intro"><Xueqing /></AuthGate>
</template>
