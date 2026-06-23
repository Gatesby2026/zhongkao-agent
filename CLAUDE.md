# zhongkao-agent — 项目说明

## 线上部署 / 构建流程

线上站点：**https://zhongkao.gatesby.xyz**
ECS：阿里云 `39.103.70.47`（root，密码见全局 `~/.claude/CLAUDE.md`，勿写进本仓库）
仓库路径：`/opt/zhongkao-agent`（与本地同一 git 仓库，部署靠 `git pull`，**不要**直接在服务器改代码）

SSH：本机已装 `sshpass`，用法 `export SSHPASS='<密码>'; sshpass -e ssh -o StrictHostKeyChecking=no root@39.103.70.47 '...'`

### 服务拓扑（nginx 按路径分流，详见 `deploy/README-split.md`）

| 页面 / 接口 | 后端 | 端口 | systemd |
|---|---|---|---|
| 学情分析 `/`、`/xueqing` | `server/main.py` | 8200 | `zhongkao.service` |
| 志愿填报 `/zhiyuan`、`/api/zhiyuan/` | `server/zhiyuan_app.py` | 8201 | `zhiyuan.service` |
| 静态资源 `/assets/*` | nginx 直出磁盘 `/opt/zhongkao-agent/web/dist/assets/` | — | — |

前端是 `web/`（Vue3 + Vite），**一次 `npm run build` 产出 `web/dist`**：
`index.html`/`xueqing.html`=学情，`zhiyuan.html`=志愿，三页共用 `assets/`。
服务器已装 `node v20` + `npm` + `web/node_modules`，**直接在服务器上构建**。

### A. 纯前端改动（改了 `web/` 下任意文件）

后端不用动，nginx 直出静态，**无需重启任何服务**：

```bash
# 1. 本地：提交并推送（缺省直接推 main，不开分支/PR）
git add web/... && git commit -m "..." && git push origin main

# 2. 服务器：拉取 + 重新构建（assets 带 hash，自动 cache-bust）
export SSHPASS='<密码>'
sshpass -e ssh -o StrictHostKeyChecking=no root@39.103.70.47 '
  cd /opt/zhongkao-agent && git pull --ff-only origin main &&
  cd web && npm run build'

# 3. 验证：构建产物含改动 + 线上下发的是新 hash
sshpass -e ssh ... 'grep -o "zhiyuan-[A-Za-z0-9_-]*\.js" /opt/zhongkao-agent/web/dist/zhiyuan.html'
curl -s https://zhongkao.gatesby.xyz/zhiyuan | grep -o "zhiyuan-[A-Za-z0-9_-]*\.js" | head -1   # 应与上面一致
```

浏览器看不到更新时先**硬刷新**（`Cmd+Shift+R`）清旧 JS 缓存。

### B. 后端改动（改了 `server/` 或 `scripts/admission/`）

```bash
git push origin main
sshpass -e ssh ... '
  cd /opt/zhongkao-agent && git pull --ff-only origin main &&
  systemctl restart zhiyuan      # 志愿；学情则 restart zhongkao
  curl -s 127.0.0.1:8201/api/health'   # 自检
```

> 志愿的招生数据（统招专业/班名额等）由 registry 驱动（`REGISTRY_SOURCE=1` 默认）。
> registry 数据本身随 `git pull` 生效，改 `knowledge-base/admission/.../registry/` 后按 B 重启即可。

### 回滚

```bash
git revert <commit> && git push        # 代码回滚后按 A/B 重新部署
# nginx 层回滚见 deploy/README-split.md
```

## 提交规范

- 缺省直接推送到 `main`，不开分支、不开 PR。
- commit message 末尾保留 `Co-Authored-By: Claude ...`。
- 提交时只 `git add` 本次改动文件，仓库内常有未追踪的采集/审核中间产物（`_staging/`、`_audits/`、`.tmpb/` 等），勿一并提交。
