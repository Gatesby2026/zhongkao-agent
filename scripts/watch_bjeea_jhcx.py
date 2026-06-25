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


def main() -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
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
    if any(is_alert(it) for it in new):
        banner = (f"[{_now()}] >>> 2026 普高/各校招生计划疑似已发布 "
                  f"({sum(is_alert(it) for it in new)} 条),尽快核对并刷新 registry <<<")
        log(banner)
        print(banner)


if __name__ == "__main__":
    main()
