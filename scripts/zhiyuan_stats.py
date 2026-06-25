#!/usr/bin/env python3
"""志愿系统使用埋点速览:近 N 天每日 新注册/登录/冲稳保 + 累计用户。

在服务器上跑(读 server/accounts.sqlite3,埋点表 events):
    python3 scripts/zhiyuan_stats.py [days]   # days 默认 7

new_users 取自 users.created_at(历史可回溯);logins/recommends 取自 events
表(埋点上线后才开始累计)。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 直接按文件加载 store.py(纯 stdlib),绕开 auth 包 __init__ 对 fastapi 的依赖,
# 这样不在服务 venv 里也能跑(系统 python3 即可)。
_spec = importlib.util.spec_from_file_location(
    "zk_store", ROOT / "server" / "auth" / "store.py")
store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store)


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    store.init_db()        # 幂等:确保 events 等表存在(对全新/旧库也能跑)
    rows = store.daily_stats(days)
    print(f"=== 近 {days} 天每日使用 ===")
    print("日期 | 新注册 | 登录 | 冲稳保 | 独立IP")
    for r in rows:
        print(f"{r['date']} | {r['new_users']} | {r['logins']} | "
              f"{r['recommends']} | {r['rec_unique_ips']}")
    with store._conn() as c:
        total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        ev = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"\n累计注册用户: {total} | 累计埋点事件: {ev}")


if __name__ == "__main__":
    main()
