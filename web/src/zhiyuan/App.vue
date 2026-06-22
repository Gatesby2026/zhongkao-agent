<script setup lang="ts">
// 志愿模块入口:登录网关 + 志愿主应用。
import AuthGate from '../shared/auth/AuthGate.vue'
import type { Intro } from '../shared/auth/Login.vue'
import Zhiyuan from './Zhiyuan.vue'

const intro: Intro = {
  title: '北京中考志愿参考 · 全市',
  tagline: '按区排名做冲稳保匹配，给一份有依据、能落地的志愿草表。',
  feats: [
    '<b>冲稳保推荐</b>：用你的区排名对齐各校历年录取位次（朝阳/海淀/西城/东城）',
    '<b>通勤距离</b>：高德路网算到家的真实骑行/驾车里程',
    '<b>校额到校 · 市级统筹</b>：研判定向名额值不值得用',
    '<b>查学校</b>：全市 16 区统招计划、专业(班)、位置一站浏览',
  ],
  note: '仅辅助参考，最终以官方招生简章与老师建议为准。',
}
</script>

<template>
  <AuthGate app-name="zhiyuan" :intro="intro"><Zhiyuan /></AuthGate>
</template>
