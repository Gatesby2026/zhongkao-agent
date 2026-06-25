#!/usr/bin/env python3
"""每日盯北京教育考试院"计划查询"(jhcx)列表页,发现新条目就记一条;
命中 2026 普高/各校招生计划则标 ALERT(这是我们等的——普高各校招生名额发布)。

零第三方依赖(urllib + re)。cron 友好:
  - 首跑:把当前全部条目作 baseline 落库,不告警。
  - 之后每跑:只对"新出现的 url"记录;命中普高关键词的额外打 ALERT。
  - 无变化:静默(只在 LOG 末尾留一行 no change)。

状态/日志默认放 $WATCH_DIR(默认 /var/lib/zhiyuan-watch),**不入 git**,
故 git pull 不受影响。手动跑:
    WATCH_DIR=/var/lib/zhiyuan-watch python3 scripts/watch_bjeea_jhcx.py
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.bjeea.cn/html/zkzh/jhcx/"
BASE = "https://www.bjeea.cn"
WATCH_DIR = Path(os.environ.get("WATCH_DIR", "/var/lib/zhiyuan-watch"))
SEEN_F = WATCH_DIR / "jhcx_seen.json"
LOG_F = WATCH_DIR / "jhcx_watch.log"

# 列表项:<span class="li-time m-r-15">2026-04-30</span><a href="..." title="标题" ...>
ITEM_RE = re.compile(
    r'<span\s+class="li-time[^"]*">\s*(\d{4}-\d{2}-\d{2})\s*</span>\s*'
    r'<a\s+href="([^"]+)"\s+title="([^"]*)"',
    re.S,
)
# 我们等的:2026 普高/各校/校额到校/市级统筹/中招计划说明,且不是中职/职高/技工那类
PUHAO_RE = re.compile(r"(普通高中|普高|优质高中|校额到校|市级统筹|统筹|中招计划说明|各校)")
VOC_RE = re.compile(r"(中职|中等职业|职业高中|技工|技术学校|中等专业|五年制|贯通)")


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (zhiyuan-watch)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def parse(html: str) -> list[dict]:
    out, seen = [], set()
    for date, href, title in ITEM_RE.findall(html):
        if "/jhcx/" not in href:
            continue
        url = href if href.startswith("http") else BASE + href
        if url in seen:
            continue
        seen.add(url)
        out.append({"date": date, "url": url, "title": title.strip()})
    return out


def is_alert(it: dict) -> bool:
    t = it["title"]
    return ("2026" in t) and bool(PUHAO_RE.search(t)) and not VOC_RE.search(t)


def log(line: str) -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_F, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_mailer():
    """按文件直载 server/auth/email.py(只依赖 os + 惰性导入 SDK),绕开 auth 包的 fastapi 依赖。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "zk_mail", ROOT / "server" / "auth" / "email.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def send_alert_email(items: list[dict]) -> None:
    """命中 2026 普高条目时发邮件到 $WATCH_ALERT_EMAIL。失败只记日志,不影响盯哨主流程。"""
    to = os.environ.get("WATCH_ALERT_EMAIL")
    if not to:
        log(f"[{_now()}] (未配置 WATCH_ALERT_EMAIL,跳过发信)")
        return
    rows = "".join(
        f'<li><b>{it["date"]}</b> — {it["title"]}<br>'
        f'<a href="{it["url"]}">{it["url"]}</a></li>' for it in items)
    html = (
        '<div style="font-family:sans-serif;font-size:15px;color:#222">'
        '<p>🔔 北京教育考试院"计划查询"页出现 <b>2026 普高/各校招生计划</b> 相关新条目：</p>'
        f'<ul>{rows}</ul>'
        f'<p style="color:#888;font-size:13px">来源 <a href="{URL}">{URL}</a>。'
        '请尽快核对并把 2026 名额刷进 registry。本邮件由志愿盯哨 cron 自动发送。</p></div>'
    )
    try:
        ok, msg = _load_mailer().send_mail(to, "【志愿盯哨】2026 普高招生计划疑似发布", html)
        log(f"[{_now()}] email -> {to}: {'OK' if ok else 'FAIL'} {msg}")
    except Exception as e:                       # noqa: BLE001
        log(f"[{_now()}] email -> {to}: EXC {e!r}")


def main() -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    if "--test-email" in sys.argv:               # 自检:直接发一封样例告警邮件,验证投递链路
        sample = [{"date": "2026-07-01",
                   "title": "2026年普通高中学校统一招生计划（样例·测试)",
                   "url": "https://www.bjeea.cn/html/zkzh/jhcx/"}]
        send_alert_email(sample)
        print("test email triggered (看日志确认 OK/FAIL):", LOG_F)
        return
    try:
        items = parse(fetch(URL))
    except Exception as e:                      # 网络/解析失败:记一行,非 0 退出供 cron 感知
        log(f"[{_now()}] ERROR fetch/parse: {e!r}")
        print(f"watch error: {e!r}", file=sys.stderr)
        sys.exit(1)
    if not items:                               # 一条没解析到→页面结构大概率变了,需人工看
        log(f"[{_now()}] WARN 0 items parsed(页面结构可能变了,需检查正则)")
        print("0 items parsed", file=sys.stderr)
        sys.exit(2)

    seen = set(json.loads(SEEN_F.read_text(encoding="utf-8"))) if SEEN_F.exists() else set()
    new = [it for it in items if it["url"] not in seen]
    SEEN_F.write_text(json.dumps([it["url"] for it in items], ensure_ascii=False),
                      encoding="utf-8")

    if not seen:                                # 首跑:只做基线,不告警
        log(f"[{_now()}] baseline seeded {len(items)} items (首跑,不告警)")
        print(f"baseline seeded {len(items)} items")
        return
    if not new:
        log(f"[{_now()}] no change ({len(items)} items)")
        return

    for it in new:
        tag = "ALERT-普高" if is_alert(it) else "new"
        line = f"[{_now()}] {tag} | {it['date']} | {it['title']} | {it['url']}"
        log(line)
        print(line)
    alerts = [it for it in new if is_alert(it)]
    if alerts:
        banner = (f"[{_now()}] >>> 2026 普高/各校招生计划疑似已发布 "
                  f"({len(alerts)} 条),尽快核对并刷新 registry <<<")
        log(banner)
        print(banner)
        send_alert_email(alerts)                 # 命中即发邮件提醒


if __name__ == "__main__":
    main()
