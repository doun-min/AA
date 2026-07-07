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

CREATE TABLE IF NOT EXISTS room_participants (
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    nickname TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (room_id, nickname)
);

CREATE TABLE IF NOT EXISTS message_reads (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    read_at TEXT NOT NULL,
    PRIMARY KEY (message_id, user_id)
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('annual','half_day','work')),
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    end_date TEXT,
    start_time TEXT,
    end_time TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_direct_nickname ON direct_participants(nickname);
CREATE INDEX IF NOT EXISTS idx_room_participants_room ON room_participants(room_id);
CREATE INDEX IF NOT EXISTS idx_message_reads_message ON message_reads(message_id);
CREATE INDEX IF NOT EXISTS idx_schedules_date ON schedules(date);
CREATE INDEX IF NOT EXISTS idx_schedules_nickname ON schedules(nickname);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with db_cursor(commit=True) as cur:
        cur.executescript(SCHEMA)
        cur.execute("PRAGMA table_info(schedules)")
        columns = {row["name"] for row in cur.fetchall()}
        if "end_date" not in columns:
            cur.execute("ALTER TABLE schedules ADD COLUMN end_date TEXT")
            cur.execute("UPDATE schedules SET end_date = date WHERE end_date IS NULL")
        cur.execute("SELECT id FROM rooms WHERE type='global' LIMIT 1")
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO rooms (name, type, owner_nickname, created_by, created_at, is_deletable) "
                "VALUES (?,?,?,?,?,0)",
                (config.GLOBAL_ROOM_NAME, "global", None, None, _now()),
            )
        cur.execute("SELECT id FROM rooms WHERE type='group' AND name=? LIMIT 1", (config.SCHEDULE_ROOM_NAME,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO rooms (name, type, owner_nickname, created_by, created_at, is_deletable) "
                "VALUES (?,?,?,?,?,0)",
                (config.SCHEDULE_ROOM_NAME, "group", None, None, _now()),
            )


def get_room(room_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_room_by_name(name):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM rooms WHERE name=? LIMIT 1", (name,))
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


def ensure_room_participant(room_id, nickname):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT OR IGNORE INTO room_participants (room_id, nickname, joined_at) VALUES (?,?,?)",
            (room_id, nickname, _now()),
        )


def get_room_member_nicknames(room_id, room_type=None):
    if room_type is None:
        room = get_room(room_id)
        room_type = room["type"] if room else None
    with db_cursor() as cur:
        if room_type == "direct":
            cur.execute("SELECT nickname FROM direct_participants WHERE room_id=?", (room_id,))
        else:
            cur.execute("SELECT nickname FROM room_participants WHERE room_id=?", (room_id,))
        return [r["nickname"] for r in cur.fetchall()]


def mark_messages_read(room_id, nickname, up_to_message_id):
    """nickname이 up_to_message_id까지(포함) 아직 읽지 않은, 본인이 보내지 않은 메시지를 읽음 처리한다."""
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT id FROM messages WHERE room_id=? AND id<=? AND sender != ? AND type != 'system' "
            "AND id NOT IN (SELECT message_id FROM message_reads WHERE user_id=?)",
            (room_id, up_to_message_id, nickname, nickname),
        )
        msg_ids = [r["id"] for r in cur.fetchall()]
        if not msg_ids:
            return []
        cur.executemany(
            "INSERT OR IGNORE INTO message_reads (message_id, user_id, read_at) VALUES (?,?,?)",
            [(mid, nickname, now) for mid in msg_ids],
        )
        return msg_ids


def get_messages_unread_counts(room_id, message_ids):
    """message_ids 각각에 대해 (발신자를 제외한 방 참여자 수 - 읽은 사람 수)를 계산한다."""
    if not message_ids:
        return {}
    members = set(get_room_member_nicknames(room_id))
    placeholders = ",".join("?" for _ in message_ids)
    with db_cursor() as cur:
        cur.execute(
            f"SELECT id, sender FROM messages WHERE id IN ({placeholders})",
            message_ids,
        )
        senders = {r["id"]: r["sender"] for r in cur.fetchall()}
        cur.execute(
            f"SELECT message_id, COUNT(DISTINCT user_id) AS c FROM message_reads "
            f"WHERE message_id IN ({placeholders}) GROUP BY message_id",
            message_ids,
        )
        read_counts = {r["message_id"]: r["c"] for r in cur.fetchall()}

    result = {}
    for mid in message_ids:
        sender = senders.get(mid)
        total_recipients = len(members - {sender}) if sender else len(members)
        result[mid] = max(total_recipients - read_counts.get(mid, 0), 0)
    return result


def list_messages_with_unread(room_id, limit=200):
    messages = list_messages(room_id, limit=limit)
    if not messages:
        return messages
    non_system_ids = [m["id"] for m in messages if m["type"] != "system"]
    counts = get_messages_unread_counts(room_id, non_system_ids)
    for m in messages:
        m["unread_count"] = counts.get(m["id"], 0)
    return messages


def create_schedule(nickname, category, title, date, end_date=None, start_time=None, end_time=None):
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO schedules (nickname, category, title, date, end_date, start_time, end_time, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (nickname, category, title, date, end_date or date, start_time, end_time, now, now),
        )
        schedule_id = cur.lastrowid
        cur.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,))
        return dict(cur.fetchone())


def get_schedule(schedule_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_schedule(schedule_id, category, title, date, end_date=None, start_time=None, end_time=None):
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE schedules SET category=?, title=?, date=?, end_date=?, start_time=?, end_time=?, updated_at=? WHERE id=?",
            (category, title, date, end_date or date, start_time, end_time, now, schedule_id),
        )
        cur.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def delete_schedule(schedule_id):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))


def list_schedules_for_month(year, month):
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM schedules WHERE date < ? AND end_date >= ? "
            "ORDER BY date ASC, (category='work'), (start_time IS NULL), start_time ASC",
            (end, start),
        )
        return [dict(r) for r in cur.fetchall()]


def list_schedules_for_date(date_str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM schedules WHERE date<=? AND end_date>=? "
            "ORDER BY (category='work'), (start_time IS NULL), start_time ASC",
            (date_str, date_str),
        )
        return [dict(r) for r in cur.fetchall()]
