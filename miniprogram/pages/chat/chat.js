// pages/chat/chat.js
// 私人教研组群聊 UI - 原型阶段
// 当前所有消息为 mock 数据；正式版将从后端 API 拉取

// ============== 老师/角色配置（前端展示用，正式版同步到后端） ==============
const ROLES = {
  banzhuren: {
    id: 'banzhuren',
    name: '李老师',
    role: '班主任',
    avatarChar: '李',
    avatarBg: '#3b82f6',
    side: 'left',
  },
  shuxue: {
    id: 'shuxue',
    name: '王老师',
    role: '数学',
    avatarChar: '王',
    avatarBg: '#10b981',
    side: 'left',
  },
  yuwen: {
    id: 'yuwen',
    name: '陈老师',
    role: '语文',
    avatarChar: '陈',
    avatarBg: '#ef4444',
    side: 'left',
  },
  yingyu: {
    id: 'yingyu',
    name: '孙老师',
    role: '英语',
    avatarChar: '孙',
    avatarBg: '#8b5cf6',
    side: 'left',
  },
  wuli: {
    id: 'wuli',
    name: '刘老师',
    role: '物理',
    avatarChar: '刘',
    avatarBg: '#f97316',
    side: 'left',
  },
  daofa: {
    id: 'daofa',
    name: '周老师',
    role: '道法',
    avatarChar: '周',
    avatarBg: '#a16207',
    side: 'left',
  },
  parent: {
    id: 'parent',
    name: '我',
    role: '',
    avatarChar: '我',
    avatarBg: '#6b7280',
    side: 'right',
  },
  student: {
    id: 'student',
    name: '子涵',
    role: '',
    avatarChar: '子',
    avatarBg: '#06b6d4',
    side: 'right',
  },
}

// ============== Mock 对话数据 ==============
const MOCK_MESSAGES = [
  {
    type: 'system',
    text: '王子涵的私人教研组 已成立',
  },
  {
    type: 'system',
    text: '李老师 邀请 王老师、陈老师、孙老师、刘老师、周老师 加入了教研组',
  },
  {
    type: 'text',
    role: 'banzhuren',
    time: '昨天 19:32',
    showTime: true,
    text: '王子涵家长您好！我是班主任李老师 👋\n\n从今天开始，我和数学王老师、语文陈老师、英语孙老师、物理刘老师、道法周老师 5 位学科老师会在这里陪伴子涵备考中考 🎯\n\n先来认识一下——子涵现在是初三了吗？',
  },
  {
    type: 'text',
    role: 'parent',
    text: '是的，初三',
  },
  {
    type: 'text',
    role: 'banzhuren',
    text: '好的！上次模考（或期末考）总分大概多少？想冲哪所高中？',
  },
  {
    type: 'text',
    role: 'parent',
    text: '395 分，想上八十中',
  },
  {
    type: 'text',
    role: 'banzhuren',
    text: '八十中近几年录取线在 450 分左右，差距 55 分，有挑战但完全可以冲！\n\n各科分别多少？我帮你看看从哪里补最有效率 👇',
  },
  {
    type: 'system',
    text: '——— 今天 ———',
  },
  {
    type: 'text',
    role: 'banzhuren',
    time: '今天 07:30',
    showTime: true,
    text: '☀️ 早！子涵今天的学习任务：',
  },
  {
    type: 'card',
    role: 'banzhuren',
    cardTitle: '今日学习计划',
    cardItems: [
      { icon: '📐', label: '数学 · 函数基础', value: '45 分钟' },
      { icon: '🔤', label: '英语 · 听说模拟', value: '30 分钟' },
      { icon: '⚖️', label: '道法 · 答题框架', value: '20 分钟' },
    ],
    cardFooter: '总计 95 分钟 · 做完把数学题发给王老师看看 💪',
  },
  {
    type: 'text',
    role: 'parent',
    text: '孩子今天状态不太好，能不能少一点任务？',
  },
  {
    type: 'text',
    role: 'banzhuren',
    text: '没问题，今天减半，保持状态比数量更重要 💛\n\n明天补回来就好。',
  },
  {
    type: 'text',
    role: 'student',
    time: '今天 15:42',
    showTime: true,
    text: '老师这道题不会做',
  },
  {
    type: 'image',
    role: 'student',
    imageDesc: '[一道二次函数题的照片]',
  },
  {
    type: 'text',
    role: 'banzhuren',
    text: '这是数学题，让王老师来看看 →',
  },
  {
    type: 'text',
    role: 'shuxue',
    text: '这道题考的是配方法的应用。\n\n先把 y = 2x² + 4x − 3 配方：\ny = 2(x² + 2x) − 3\n  = 2(x + 1)² − 5\n\n所以顶点是 (−1, −5)，开口向上 ✓',
  },
  {
    type: 'card',
    role: 'shuxue',
    cardTitle: '完整解题步骤',
    cardItems: [
      { icon: '📝', label: '步骤 1', value: '提取二次项系数' },
      { icon: '📝', label: '步骤 2', value: '配方变形' },
      { icon: '📝', label: '步骤 3', value: '确定顶点和开口' },
    ],
    cardFooter: '点击查看动画解析 →',
    cardAction: 'detail',
  },
  {
    type: 'text',
    role: 'shuxue',
    text: '理解了告诉我，我让你再出 2 道类似题练手 🎯',
  },
  {
    type: 'text',
    role: 'banzhuren',
    text: '王老师讲得很清楚，子涵理解了的话回复"嗯"就行～\n\n今天物理周测怎么样？刘老师也想看看 👀',
  },
]

// ============== 页面逻辑 ==============
Page({
  data: {
    messages: [],
    inputValue: '',
    scrollIntoView: '',
  },

  onLoad() {
    // 把 role 字符串展开成完整角色对象，方便模板使用
    const messages = MOCK_MESSAGES.map((m, idx) => {
      const enriched = { ...m, _idx: idx, _key: `msg_${idx}` }
      if (m.role && ROLES[m.role]) {
        enriched._role = ROLES[m.role]
      }
      return enriched
    })

    this.setData({ messages }, () => {
      // 滚动到最后一条
      const lastKey = `msg_${messages.length - 1}`
      this.setData({ scrollIntoView: lastKey })
    })
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value })
  },

  onSend() {
    const text = this.data.inputValue.trim()
    if (!text) return

    const newMsg = {
      type: 'text',
      role: 'parent',
      _role: ROLES.parent,
      text,
      _idx: this.data.messages.length,
      _key: `msg_${this.data.messages.length}`,
    }

    const messages = [...this.data.messages, newMsg]
    this.setData(
      {
        messages,
        inputValue: '',
        scrollIntoView: newMsg._key,
      },
      () => {
        // 模拟班主任 1.5 秒后回复
        setTimeout(() => this.mockBanzhurenReply(text), 1500)
      },
    )
  },

  mockBanzhurenReply(userText) {
    const reply = {
      type: 'text',
      role: 'banzhuren',
      _role: ROLES.banzhuren,
      text: `[原型 mock 回复] 收到："${userText}"。\n\n正式版这里会接入后端 AI Agent，由班主任判断后路由到对应学科老师。`,
      _idx: this.data.messages.length,
      _key: `msg_${this.data.messages.length}`,
    }
    const messages = [...this.data.messages, reply]
    this.setData({ messages, scrollIntoView: reply._key })
  },

  onCardTap(e) {
    const action = e.currentTarget.dataset.action
    if (action === 'detail') {
      wx.showToast({
        title: '正式版跳转详细解析页',
        icon: 'none',
      })
    }
  },
})
