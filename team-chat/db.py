import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config


def get_conn():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor(commit=False):
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('global','group','direct')),
    owner_nickname TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    is_deletable INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    sender TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('text','file','image','system')),
    content TEXT,
    file_path TEXT,
    original_filename TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS direct_participants (
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    nickname TEXT NOT NULL,
    PRIMARY KEY (room_id, nickname)
);

CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_direct_nickname ON direct_participants(nickname);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with db_cursor(commit=True) as cur:
        cur.executescript(SCHEMA)
        cur.execute("SELECT id FROM rooms WHERE type='global' LIMIT 1")
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO rooms (name, type, owner_nickname, created_by, created_at, is_deletable) "
                "VALUES (?,?,?,?,?,0)",
                (config.GLOBAL_ROOM_NAME, "global", None, None, _now()),
            )


def get_room(room_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_group_rooms():
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM rooms WHERE type IN ('global','group') "
            "ORDER BY (type='global') DESC, created_at ASC"
        )
        return [dict(r) for r in cur.fetchall()]


def create_group_room(name, creator):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO rooms (name, type, owner_nickname, created_by, created_at, is_deletable) "
            "VALUES (?,?,?,?,?,1)",
            (name, "group", creator, creator, _now()),
        )
        room_id = cur.lastrowid
        cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
        return dict(cur.fetchone())


def delete_room(room_id):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM rooms WHERE id=?", (room_id,))


def transfer_ownership(room_id, new_owner):
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE rooms SET owner_nickname=? WHERE id=?", (new_owner, room_id))


def get_or_create_direct_room(nick_a, nick_b):
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT dp1.room_id AS room_id FROM direct_participants dp1
            JOIN direct_participants dp2 ON dp1.room_id = dp2.room_id
            JOIN rooms r ON r.id = dp1.room_id
            WHERE dp1.nickname=? AND dp2.nickname=? AND r.type='direct'
            """,
            (nick_a, nick_b),
        )
        row = cur.fetchone()
        if row:
            cur.execute("SELECT * FROM rooms WHERE id=?", (row["room_id"],))
            return dict(cur.fetchone())

        name = f"{nick_a}, {nick_b}"
        cur.execute(
            "INSERT INTO rooms (name, type, owner_nickname, created_by, created_at, is_deletable) "
            "VALUES (?,?,?,?,?,1)",
            (name, "direct", None, nick_a, _now()),
        )
        room_id = cur.lastrowid
        cur.executemany(
            "INSERT INTO direct_participants (room_id, nickname) VALUES (?,?)",
            [(room_id, nick_a), (room_id, nick_b)],
        )
        cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
        return dict(cur.fetchone())


def list_direct_rooms_for(nickname):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.created_at,
                   (SELECT dp2.nickname FROM direct_participants dp2
                    WHERE dp2.room_id = r.id AND dp2.nickname != ? LIMIT 1) AS other
            FROM rooms r
            JOIN direct_participants dp ON dp.room_id = r.id
            WHERE dp.nickname = ? AND r.type='direct'
            ORDER BY r.created_at DESC
            """,
            (nickname, nickname),
        )
        return [dict(r) for r in cur.fetchall()]


def is_direct_participant(room_id, nickname):
    with db_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM direct_participants WHERE room_id=? AND nickname=?",
            (room_id, nickname),
        )
        return cur.fetchone() is not None


def add_message(room_id, sender, type_, content=None, file_path=None, original_filename=None):
    created_at = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO messages (room_id, sender, type, content, file_path, original_filename, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (room_id, sender, type_, content, file_path, original_filename, created_at),
        )
        msg_id = cur.lastrowid
        return {"id": msg_id, "created_at": created_at}


def list_messages(room_id, limit=200):
    with db_cursor() as cur:
        if limit:
            cur.execute(
                "SELECT * FROM (SELECT * FROM messages WHERE room_id=? ORDER BY id DESC LIMIT ?) "
                "sub ORDER BY sub.id ASC",
                (room_id, limit),
            )
        else:
            cur.execute("SELECT * FROM messages WHERE room_id=? ORDER BY id ASC", (room_id,))
        return [dict(r) for r in cur.fetchall()]
