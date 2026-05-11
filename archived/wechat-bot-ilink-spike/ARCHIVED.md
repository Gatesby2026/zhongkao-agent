# 归档说明 — iLink Bot Spike

> 归档日期：2026-05-10
> 状态：⛔ 已废弃，不再开发

## 这是什么

这是 2026-05-10 当天做的一个 **iLink Bot API 接入预研（spike）**，目的是验证「个人微信 + iLink 协议」能否作为「中考私人教研组」产品的接入通道。

代码本身是工作的：
- ✅ 实现了完整的 iLink 登录流程（QR 码 + 长轮询）
- ✅ 修复了 `iLink-App-Id` / `iLink-App-ClientVersion` / `AuthorizationType` 三个必要 header 缺失导致的 session timeout
- ✅ 跑通了 echo 链路（接收消息 → AI 回复）

## 为什么废弃

预研结果发现 **iLink/ClawBot 的设计与产品需求根本不匹配**：

| 我们要的 | iLink 实际支持的 |
|---------|----------------|
| 一个 Bot 服务多个家长 | 个人微信账号 ↔ 自己的 AI Agent（1对1） |
| 家长加好友/扫码 → 跟 Bot 对话 | 用户扫 QR = 把自己的微信交给 OpenClaw 控制 |
| 多老师群聊感 | 单个微信账号只能连一个 OpenClaw |

详细分析见 `memory/wechat-platform-decision.md`。

## 替代方案

最终选型：**服务号 + 微信小程序（自建群聊 UI）+ 多 Agent 后端**

详见 [`../../docs/product/PRD.md`](../../docs/product/PRD.md) v5.0。

## 这份代码的研究价值

如果未来 iLink 协议演进或有类似产品场景，这份代码可以作为参考：
- 完整的 iLink 协议接入示例
- session timeout 处理 + 自动重新登录
- macOS LibreSSL → Homebrew Python 3.14 + OpenSSL 的踩坑记录

但**不要**直接基于这份代码继续开发产品功能。
