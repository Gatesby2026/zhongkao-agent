# 志愿 / 学情 双服务拆分（B 档：同仓双服务）

两个独立功能拆成两个后端进程，nginx 按路径分流，可各自独立部署/重启，互不牵连。

## 端口与服务

| 服务 | 进程 | 端口 | 代码 | systemd |
|---|---|---|---|---|
| 学情分析 | `main.py`（已去掉志愿尾部） | 8200（现状） | `server/main.py` + db/tasks/pipeline/imgnorm... | `zhongkao.service`（现有） |
| 志愿填报 | `zhiyuan_app.py`（新） | **8201** | `server/zhiyuan_app.py` + `scripts/admission/` | `zhiyuan.service`（新，见 `deploy/zhiyuan.service`） |

- 志愿服务依赖很轻：`server/requirements-zhiyuan.txt`（fastapi/uvicorn/pyyaml），不装学情那套 OCR/重依赖。
- 前端仍是一次 `npm run build` 产出 `web/dist`（index.html=学情、zhiyuan.html=志愿）；静态资源 `/assets/*` 由 nginx 直接从磁盘提供，两个页面共用、谁都不依赖另一个服务。

## nginx 路由（加入现有 server 块；注意顺序：精确/前缀长的在前）

```nginx
# 静态资源直出磁盘（两页共用，不经任何后端）
location /assets/ {
    alias /opt/zhongkao-agent/web/dist/assets/;
    access_log off;
    expires 7d;
}

# —— 志愿服务 :8201 ——
location = /zhiyuan {
    proxy_pass http://127.0.0.1:8201;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
location /api/zhiyuan/ {
    proxy_pass http://127.0.0.1:8201;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

# —— 其余（学情）→ :8200 —— （保持现有 / 反代不变）
location / {
    proxy_pass http://127.0.0.1:8200;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## 部署顺序（不中断线上的安全切换）

> 必须先让 :8201 起来 + nginx 分流就绪，再重启 :8200 的精简版 main.py，避免 /zhiyuan 出现空窗。

1. `git pull`（带来 `zhiyuan_app.py`、精简后的 `main.py`、本目录文件）——**先不重启任何服务**。
2. 装志愿依赖：`pip install -r server/requirements-zhiyuan.txt`（同一 venv 即可，已装则跳过）。
3. 放置并启动志愿服务：
   - 把 `deploy/zhiyuan.service` 的 `ExecStart` python 路径、AMAP_KEY 机制**对齐现有 `zhongkao.service`**（`systemctl cat zhongkao` 看），复制到 `/etc/systemd/system/zhiyuan.service`。
   - `systemctl daemon-reload && systemctl enable --now zhiyuan`
   - 自检：`curl -s 127.0.0.1:8201/api/health`
4. 更新 nginx：加入上面的 location 块 → `nginx -t` → `systemctl reload nginx`。
5. 验证 `https://zhongkao.gatesby.xyz/zhiyuan` 正常（此时走 :8201）。
6. 最后重启学情：`systemctl restart zhongkao`（此时 main.py 已无志愿尾部）。
7. 全量验证：学情首页 `/`、志愿 `/zhiyuan`、两个 `/api/...`。

## 回滚
- nginx：去掉新增 location 块、reload，即全部回到 :8200。
- 服务：`systemctl stop zhiyuan`。
- 代码：`git revert` 拆分提交后重新部署。
