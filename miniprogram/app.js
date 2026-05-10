// app.js
App({
  onLaunch() {
    // 原型阶段：暂不接入云开发/登录/unionid
    // TODO 正式版：在此处初始化云开发 wx.cloud.init({ env: 'xxx' })
  },
  globalData: {
    studentName: '王子涵', // mock，正式版从档案读取
  },
})
