"""SQLite 任务/报告索引。文件产物仍在 students/ 目录，DB 只存元数据与状态。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "server" / "data.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
  id            TEXT PRIMARY KEY,
  student_name  TEXT,
  exam_slug     TEXT,
  status        TEXT NOT NULL,      -- queued | running | done | failed
  stage         INTEGER DEFAULT 0,  -- 0..5
  stage_name    TEXT DEFAULT '',
  error         TEXT DEFAULT '',
  student_dir   TEXT,
  report_pdf    TEXT DEFAULT '',
  created_at    REAL NOT NULL,
  updated_at    REAL NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(SCHEMA)


def create_analysis(aid: str, student_name: str, exam_slug: str,
                     student_dir: str) -> None:
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO analyses(id, student_name, exam_slug, status, "
            "stage, stage_name, student_dir, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (aid, student_name, exam_slug, "queued", 0, "排队中",
             student_dir, now, now),
        )


def update_stage(aid: str, stage: int, stage_name: str,
                 status: str = "running") -> None:
    with _conn() as c:
        c.execute(
            "UPDATE analyses SET stage=?, stage_name=?, status=?, updated_at=? "
            "WHERE id=?",
            (stage, stage_name, status, time.time(), aid),
        )


def set_exam_info(aid: str, student_name: str, exam_slug: str,
                  student_dir: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE analyses SET student_name=?, exam_slug=?, student_dir=?, "
            "updated_at=? WHERE id=?",
            (student_name, exam_slug, student_dir, time.time(), aid),
        )


def mark_done(aid: str, report_pdf: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE analyses SET status='done', stage=5, "
            "stage_name='完成', report_pdf=?, updated_at=? WHERE id=?",
            (report_pdf, time.time(), aid),
        )


def mark_failed(aid: str, error: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE analyses SET status='failed', error=?, updated_at=? "
            "WHERE id=?",
            (error[:1000], time.time(), aid),
        )


def get_analysis(aid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM analyses WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None


def list_analyses(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
