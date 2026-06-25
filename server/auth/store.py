"""accounts.sqlite3 — 项目级用户库(stdlib sqlite3,延续 server/db.py 风格)。

表:
  users         项目级身份(手机号 + 预留微信字段),全 app 共享
  login_codes   短信验证码(只存哈希·过期·尝试次数·发码 IP,用于限流防刷)
  app_profiles  按 (user_id, app) 命名空间的资料 JSON(zhiyuan 表单等)
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "accounts.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  phone         TEXT UNIQUE,
  email         TEXT,
  wx_unionid    TEXT,
  wx_openid     TEXT,
  nickname      TEXT,
  created_at    REAL NOT NULL,
  last_login_at REAL
);
CREATE TABLE IF NOT EXISTS login_codes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  phone       TEXT NOT NULL,
  code_hash   TEXT NOT NULL,
  expires_at  REAL NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0,
  consumed    INTEGER NOT NULL DEFAULT 0,
  send_ip     TEXT,
  created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_codes_phone ON login_codes(phone, created_at);
CREATE INDEX IF NOT EXISTS idx_codes_ip ON login_codes(send_ip, created_at);
CREATE TABLE IF NOT EXISTS app_profiles (
  user_id     INTEGER NOT NULL,
  app         TEXT NOT NULL,
  data        TEXT NOT NULL,
  updated_at  REAL NOT NULL,
  PRIMARY KEY (user_id, app)
);
CREATE TABLE IF NOT EXISTS events (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       REAL NOT NULL,
  kind     TEXT NOT NULL,        -- 'login' / 'recommend' / ...
  user_id  INTEGER,
  ip       TEXT,
  meta     TEXT                  -- JSON,如 {"district":"chaoyang","rank":5000}
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, ts);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(SCHEMA)
        # 旧库迁移:补 email 列(CREATE TABLE IF NOT EXISTS 不会改已存在表)。
        # 唯一索引必须在列存在后建,故放这里(不放 SCHEMA,否则旧库 executescript 先建索引会报错)。
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
        if "email" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")


# ---------- 验证码 ----------

def _hash_code(phone: str, code: str) -> str:
    """只存哈希,不存明文。掺 phone + 进程密钥,防撞库/防直接读表。"""
    salt = os.environ.get("AUTH_JWT_SECRET", "dev-insecure-secret")
    return hashlib.sha256(f"{phone}:{code}:{salt}".encode()).hexdigest()


def count_codes_since(phone: str, ip: str | None, since_ts: float) -> tuple[int, int]:
    """返回 (该手机号自 since_ts 起发码数, 该 IP 自 since_ts 起发码数)。供限流。"""
    with _conn() as c:
        n_phone = c.execute(
            "SELECT COUNT(*) FROM login_codes WHERE phone=? AND created_at>=?",
            (phone, since_ts),
        ).fetchone()[0]
        n_ip = 0
        if ip:
            n_ip = c.execute(
                "SELECT COUNT(*) FROM login_codes WHERE send_ip=? AND created_at>=?",
                (ip, since_ts),
            ).fetchone()[0]
    return n_phone, n_ip


def last_code_ts(phone: str) -> float:
    with _conn() as c:
        row = c.execute(
            "SELECT MAX(created_at) FROM login_codes WHERE phone=?", (phone,)
        ).fetchone()
    return float(row[0]) if row and row[0] else 0.0


def save_code(phone: str, code: str, ttl_sec: int, ip: str | None) -> None:
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO login_codes(phone, code_hash, expires_at, send_ip, created_at) "
            "VALUES (?,?,?,?,?)",
            (phone, _hash_code(phone, code), now + ttl_sec, ip, now),
        )


def verify_code(phone: str, code: str, max_attempts: int = 5) -> bool:
    """校验最近一条未消费、未过期的验证码;成功后标记 consumed。
    每次失败 attempts+1,超过 max_attempts 直接作废该码。"""
    now = time.time()
    want = _hash_code(phone, code)
    with _conn() as c:
        row = c.execute(
            "SELECT id, code_hash, attempts FROM login_codes "
            "WHERE phone=? AND consumed=0 AND expires_at>? "
            "ORDER BY created_at DESC LIMIT 1",
            (phone, now),
        ).fetchone()
        if not row:
            return False
        if row["attempts"] >= max_attempts:
            c.execute("UPDATE login_codes SET consumed=1 WHERE id=?", (row["id"],))
            return False
        if row["code_hash"] == want:
            c.execute("UPDATE login_codes SET consumed=1 WHERE id=?", (row["id"],))
            return True
        c.execute("UPDATE login_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
        return False


# ---------- 用户 ----------

def upsert_user_by_phone(phone: str) -> dict:
    now = time.time()
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        if row:
            c.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, row["id"]))
            u = dict(row)
            u["last_login_at"] = now
            return u
        cur = c.execute(
            "INSERT INTO users(phone, created_at, last_login_at) VALUES (?,?,?)",
            (phone, now, now),
        )
        return {"id": cur.lastrowid, "phone": phone,
                "created_at": now, "last_login_at": now}


def upsert_user_by_email(email: str) -> dict:
    now = time.time()
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            c.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, row["id"]))
            u = dict(row)
            u["last_login_at"] = now
            return u
        cur = c.execute(
            "INSERT INTO users(email, created_at, last_login_at) VALUES (?,?,?)",
            (email, now, now),
        )
        return {"id": cur.lastrowid, "email": email,
                "created_at": now, "last_login_at": now}


def get_user(uid: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


# ---------- 资料(按 app 命名空间) ----------

def get_profile(uid: int, app: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT data FROM app_profiles WHERE user_id=? AND app=?", (uid, app)
        ).fetchone()
    return json.loads(row["data"]) if row else None


def put_profile(uid: int, app: str, data: dict) -> None:
    now = time.time()
    blob = json.dumps(data, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            "INSERT INTO app_profiles(user_id, app, data, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, app) DO UPDATE SET data=excluded.data, "
            "updated_at=excluded.updated_at",
            (uid, app, blob, now),
        )


# ---------- 轻量埋点(事件日志) ----------

def log_event(kind: str, *, user_id: int | None = None,
              ip: str | None = None, meta: dict | None = None) -> None:
    """落一条事件埋点。绝不让埋点失败影响主请求(吞掉所有异常)。"""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO events(ts, kind, user_id, ip, meta) VALUES (?,?,?,?,?)",
                (time.time(), kind, user_id, ip,
                 json.dumps(meta, ensure_ascii=False) if meta else None),
            )
    except Exception:
        pass


def daily_stats(days: int = 7) -> list[dict]:
    """近 days 天逐日汇总:新注册数 / 登录次数 / recommend 次数 + 独立 IP。
    new_users 取自 users.created_at(历史可回溯);logins/recommends 取自 events
    (埋点上线后才有数据)。日期按服务器本地时区切分。"""
    import datetime
    since = time.time() - days * 86400

    def _day(ts):
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")

    agg: dict[str, dict] = {}

    def slot(d):
        return agg.setdefault(d, {"date": d, "new_users": 0, "logins": 0,
                                  "recommends": 0, "_rec_ips": set()})

    with _conn() as c:
        for (ts,) in c.execute(
                "SELECT created_at FROM users WHERE created_at>=?", (since,)):
            slot(_day(ts))["new_users"] += 1
        for ts, kind, ip in c.execute(
                "SELECT ts, kind, ip FROM events WHERE ts>=?", (since,)):
            s = slot(_day(ts))
            if kind == "login":
                s["logins"] += 1
            elif kind == "recommend":
                s["recommends"] += 1
                if ip:
                    s["_rec_ips"].add(ip)
    out = []
    for d in sorted(agg):
        s = agg[d]
        s["rec_unique_ips"] = len(s.pop("_rec_ips"))
        out.append(s)
    return out
