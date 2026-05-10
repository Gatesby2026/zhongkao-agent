# wechat-bot

微信 ClawBot iLink Bot API 接入实验。

## 当前阶段

**MVP 0**：最小回声 Bot，验证 iLink 收发消息链路。

## 准备工作

### 微信侧

1. 准备一个微信账号（任意账号即可，建议非主账号）
2. 微信更新到 **v8.0.70+**
3. 在微信里：**我 → 设置 → 插件 → ClawBot → 启用**

### 本地环境

```bash
cd wechat-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行回声 Bot

```bash
python3 echo_bot.py
```

流程：
1. 终端打印登录二维码
2. 用启用了 ClawBot 的微信扫码确认
3. 登录成功后，token 保存到 `bot_token.json`（本地，不提交 git）
4. 用另一个微信号给该账号发消息，会收到 `[ECHO] xxx` 回复

## 验证目标

- [ ] 能成功扫码登录
- [ ] 能接收私聊文字消息
- [ ] 能成功发送回复
- [ ] 长时间运行稳定（24 小时自动续连）
- [ ] 能接收群聊消息（需另测）

## 已知约束

- iLink 回复必须带 `context_token`，**不能任意主动推送**（待进一步验证是否有专门的主动推送接口）
- 一个微信账号只能绑定一个 Bot 通道
- token 有效期 24 小时，需要自动续连机制
