"""SQLite 存取层：连接管理、建表、审计日志。

设计原则：数据库是唯一事实来源，页面上看到的一切都从这里派生。
"""
import json
import sqlite3
from datetime import datetime, timezone

from flask import g

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'admin',
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  code            TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  real_name       TEXT,
  contact_qq      TEXT,
  contact_discord TEXT,
  contact_email   TEXT,
  phone           TEXT,
  age             INTEGER,
  experience      TEXT NOT NULL DEFAULT 'newbie',
  hunts_played    INTEGER NOT NULL DEFAULT 0,
  best_result     TEXT,
  intent          TEXT NOT NULL DEFAULT 'any',
  wants_mentor    INTEGER NOT NULL DEFAULT 0,
  mentor_capacity INTEGER NOT NULL DEFAULT 0,
  hours_available INTEGER,
  sleep_schedule  TEXT NOT NULL DEFAULT 'flexible',
  voice_ok        INTEGER NOT NULL DEFAULT 1,
  skills          TEXT NOT NULL DEFAULT '{}',
  notes           TEXT,
  status          TEXT NOT NULL DEFAULT 'active',
  source_batch    INTEGER,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT NOT NULL UNIQUE,
  kind           TEXT NOT NULL DEFAULT 'casual',
  captain_id     INTEGER REFERENCES members(id) ON DELETE SET NULL,
  pitch          TEXT,
  goal           TEXT,
  capacity       INTEGER NOT NULL DEFAULT 6,
  newbie_quota   INTEGER NOT NULL DEFAULT 2,
  voice_required INTEGER NOT NULL DEFAULT 0,
  status         TEXT NOT NULL DEFAULT 'recruiting',
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id   INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  role      TEXT NOT NULL DEFAULT 'member',
  joined_at TEXT NOT NULL,
  left_at   TEXT
);

-- 一个成员同时只能属于一支在队队伍
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_membership
  ON team_members(member_id) WHERE left_at IS NULL;

CREATE TABLE IF NOT EXISTS events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  slug          TEXT UNIQUE,
  kind          TEXT NOT NULL DEFAULT 'external',
  start_date    TEXT,
  end_date      TEXT,
  team_size_min INTEGER NOT NULL DEFAULT 1,
  team_size_max INTEGER NOT NULL DEFAULT 6,
  reg_deadline  TEXT,
  url           TEXT,
  notes         TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_teams (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  team_id         INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  status          TEXT NOT NULL DEFAULT 'registered',
  roster_snapshot TEXT,
  note            TEXT,
  created_at      TEXT NOT NULL,
  UNIQUE (event_id, team_id)
);

CREATE TABLE IF NOT EXISTS import_batches (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  filename      TEXT NOT NULL,
  mapping       TEXT,
  total_rows    INTEGER NOT NULL DEFAULT 0,
  created_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  detail        TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor      TEXT,
  action     TEXT NOT NULL,
  target     TEXT,
  detail     TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_members_experience ON members(experience);
CREATE INDEX IF NOT EXISTS idx_members_status ON members(status);
CREATE INDEX IF NOT EXISTS idx_tm_team ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_logs_created ON audit_logs(created_at DESC);
"""

SCHEMA_VERSION = "2"

# 老库升级用：列不存在就补上。SQLite 的 ALTER TABLE ADD COLUMN 很便宜，重复跑也无害。
COLUMN_MIGRATIONS = {
    "members": [
        ("age", "INTEGER"),
    ],
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    for table, columns in COLUMN_MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def now() -> str:
    """统一用 UTC ISO 秒级时间戳存储，展示时再转本地时间。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    # busy_timeout 必须先设：切换 WAL 本身要拿锁，多进程同时启动时会撞上
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """幂等建表。每次启动都跑一遍，结构变化靠 ALTER 语句兼容。"""
    own = conn is None
    conn = conn or connect()
    try:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


# ------------------------------------------------------------------ 审计日志
def log(conn: sqlite3.Connection, actor: str, action: str, target: str = "", detail="") -> None:
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False)
    conn.execute(
        "INSERT INTO audit_logs(actor, action, target, detail, created_at) VALUES(?,?,?,?,?)",
        (actor or "system", action, target or "", str(detail or ""), now()),
    )


# ------------------------------------------------------------------ 会员号
def next_member_code(conn: sqlite3.Connection, prefix: str) -> str:
    """生成 CAAR-0001 这样的会员号，用 meta 表做自增，避免删人后号码重复。"""
    row = conn.execute("SELECT value FROM meta WHERE key='member_seq'").fetchone()
    seq = int(row["value"]) if row else 0
    while True:
        seq += 1
        code = f"{prefix}-{seq:04d}"
        exists = conn.execute("SELECT 1 FROM members WHERE code=?", (code,)).fetchone()
        if not exists:
            break
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('member_seq', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(seq),),
    )
    return code
