"""SQLite のデータベース（設計書 4-3）。

**健康情報（持病・薬など）を入れる列は1つもない。**
サーバーにあるのは LINE の ID・呼び名・電話番号・時刻の設定・押した時刻だけ。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    line_user_id  TEXT NOT NULL UNIQUE,
    nickname      TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL CHECK (role IN ('self', 'family')),  -- 本人 / 家族
    district      TEXT NOT NULL DEFAULT '',          -- 地区（鵜戸・酒谷など）
    phone         TEXT NOT NULL DEFAULT '',          -- 家族からの「電話する」ボタン用
    remind_time   TEXT NOT NULL DEFAULT '10:00',     -- 再通知時刻
    family1_time  TEXT NOT NULL DEFAULT '11:00',     -- 家族通知時刻
    family2_time  TEXT NOT NULL DEFAULT '13:00',     -- 第2通知時刻
    holiday_from  TEXT,                              -- お休み期間（YYYY-MM-DD）
    holiday_to    TEXT,
    invite_code   TEXT UNIQUE,                       -- 家族とつなぐための6けたのコード（本人のみ）
    watch_from    TEXT,                              -- 見守りを始める日（YYYY-MM-DD）
    consent_at    TEXT NOT NULL,                     -- 同意日時
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS links (
    self_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    priority   INTEGER NOT NULL CHECK (priority IN (1, 2)),  -- 第1・第2
    PRIMARY KEY (self_id, family_id),
    UNIQUE (self_id, priority)
);

CREATE TABLE IF NOT EXISTS daily_status (
    self_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date          TEXT NOT NULL,
    state         TEXT NOT NULL,
    genki_at      TEXT,
    confirmed_at  TEXT,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (self_id, date)
);

CREATE TABLE IF NOT EXISTS quake_events (
    event_id      TEXT PRIMARY KEY,
    intensity     TEXT NOT NULL,
    headline      TEXT NOT NULL DEFAULT '',
    sent_at       TEXT NOT NULL,
    followup_done INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS safety_responses (
    event_id  TEXT NOT NULL REFERENCES quake_events(event_id) ON DELETE CASCADE,
    self_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    answer    TEXT NOT NULL CHECK (answer IN ('safe', 'help', 'no_response')),
    at        TEXT NOT NULL,
    PRIMARY KEY (event_id, self_id)
);

-- 送った通知の記録（実証実験の評価：誤報の数・通数の確認に使う）
CREATE TABLE IF NOT EXISTS notifications (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    to_id     INTEGER,
    about_id  INTEGER,
    is_push   INTEGER NOT NULL   -- 1=プッシュ（無料通数を使う） 0=応答メッセージ
);

-- 一度読んだ気象庁の電文（同じ電文を何度も取りに行かない）
CREATE TABLE IF NOT EXISTS seen_feed (
    entry_id TEXT PRIMARY KEY,
    at       TEXT NOT NULL
);

-- ドライラン（LINEの鍵なし）のときに「送ったはず」のメッセージを残す
CREATE TABLE IF NOT EXISTS outbox (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL,
    kind     TEXT NOT NULL,   -- reply / push
    to_line  TEXT NOT NULL,
    body     TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn
