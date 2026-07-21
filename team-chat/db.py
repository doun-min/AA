import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import config

# 화면/로그 어디서든 created_at을 그대로(타임존 부분만 잘라서) 보여주는 구조라서,
# 저장 시점에 KST로 기록해두면 별도 변환 없이 모든 표시 위치가 한국 시간으로 나온다.
KST = timezone(timedelta(hours=9))


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
    is_deletable INTEGER NOT NULL DEFAULT 1,
    is_private INTEGER NOT NULL DEFAULT 0
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

CREATE TABLE IF NOT EXISTS message_reactions (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    nickname TEXT NOT NULL,
    reaction TEXT NOT NULL CHECK(reaction IN ('o','x','like','dislike','check')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (message_id, nickname, reaction)
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

CREATE TABLE IF NOT EXISTS mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    target_nickname TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT
);

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    tc_num TEXT,
    body TEXT,
    steps_to_reproduce TEXT,
    reporter TEXT NOT NULL,
    custom_fields TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issue_custom_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_direct_nickname ON direct_participants(nickname);
CREATE INDEX IF NOT EXISTS idx_room_participants_room ON room_participants(room_id);
CREATE INDEX IF NOT EXISTS idx_message_reads_message ON message_reads(message_id);
CREATE INDEX IF NOT EXISTS idx_message_reactions_message ON message_reactions(message_id);
CREATE INDEX IF NOT EXISTS idx_schedules_date ON schedules(date);
CREATE INDEX IF NOT EXISTS idx_schedules_nickname ON schedules(nickname);
CREATE INDEX IF NOT EXISTS idx_mentions_target ON mentions(target_nickname, read_at);
CREATE INDEX IF NOT EXISTS idx_mentions_room_target ON mentions(room_id, target_nickname);
CREATE INDEX IF NOT EXISTS idx_issues_subject ON issues(subject_id);
CREATE INDEX IF NOT EXISTS idx_issues_reporter ON issues(reporter);
"""


def _now():
    return datetime.now(KST).isoformat(timespec="seconds")


def today_kst():
    """서버 OS의 타임존 설정과 무관하게 '오늘'을 한국 기준으로 반환한다."""
    return datetime.now(KST).date()


def init_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with db_cursor(commit=True) as cur:
        cur.executescript(SCHEMA)
        cur.execute("PRAGMA table_info(schedules)")
        columns = {row["name"] for row in cur.fetchall()}
        if "end_date" not in columns:
            cur.execute("ALTER TABLE schedules ADD COLUMN end_date TEXT")
            cur.execute("UPDATE schedules SET end_date = date WHERE end_date IS NULL")
        cur.execute("PRAGMA table_info(rooms)")
        columns = {row["name"] for row in cur.fetchall()}
        if "is_private" not in columns:
            # 기존에 이미 만들어진 방들은 지금처럼 공개(누구나 접근 가능)로 유지한다.
            cur.execute("ALTER TABLE rooms ADD COLUMN is_private INTEGER NOT NULL DEFAULT 0")
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


def list_group_rooms_for(nickname):
    """공개 방은 누구나, 비공개 방은 room_participants에 등록된 사람에게만 보인다."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM rooms
            WHERE type IN ('global','group')
              AND (is_private = 0 OR id IN (
                  SELECT room_id FROM room_participants WHERE nickname = ?
              ))
            ORDER BY (type='global') DESC, created_at ASC
            """,
            (nickname,),
        )
        return [dict(r) for r in cur.fetchall()]


def create_group_room(name, creator, members=None, is_private=False):
    """비공개(멤버제) 방은 만든 사람 + 지정한 멤버만 볼 수 있다. 공개 방은 예전처럼
    누구나 볼 수 있고, 참여자는 각자 방을 방문할 때 자연스럽게 등록된다."""
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO rooms (name, type, owner_nickname, created_by, created_at, is_deletable, is_private) "
            "VALUES (?,?,?,?,?,1,?)",
            (name, "group", creator, creator, now, 1 if is_private else 0),
        )
        room_id = cur.lastrowid
        if is_private:
            participants = {creator, *(members or [])}
            cur.executemany(
                "INSERT OR IGNORE INTO room_participants (room_id, nickname, joined_at) VALUES (?,?,?)",
                [(room_id, n, now) for n in participants],
            )
        cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
        return dict(cur.fetchone())


def is_room_participant(room_id, nickname):
    with db_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM room_participants WHERE room_id=? AND nickname=?",
            (room_id, nickname),
        )
        return cur.fetchone() is not None


def can_access_room(room, nickname):
    """direct 방은 참가자만, 비공개 그룹방은 멤버만, 그 외(공개 그룹/전체)는 누구나."""
    if room["type"] == "direct":
        return is_direct_participant(room["id"], nickname)
    if room["is_private"]:
        return is_room_participant(room["id"], nickname)
    return True


def add_room_member(room_id, nickname):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT OR IGNORE INTO room_participants (room_id, nickname, joined_at) VALUES (?,?,?)",
            (room_id, nickname, _now()),
        )


def remove_room_member(room_id, nickname):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM room_participants WHERE room_id=? AND nickname=?",
            (room_id, nickname),
        )


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


REACTION_TYPES = ("o", "x", "like", "dislike", "check")


def get_message(message_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM messages WHERE id=?", (message_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def toggle_message_reaction(message_id, nickname, reaction):
    """이미 남긴 반응이면 취소(삭제), 아니면 추가한다. 반환값: 추가됐으면 True."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT 1 FROM message_reactions WHERE message_id=? AND nickname=? AND reaction=?",
            (message_id, nickname, reaction),
        )
        if cur.fetchone():
            cur.execute(
                "DELETE FROM message_reactions WHERE message_id=? AND nickname=? AND reaction=?",
                (message_id, nickname, reaction),
            )
            return False
        cur.execute(
            "INSERT INTO message_reactions (message_id, nickname, reaction, created_at) VALUES (?,?,?,?)",
            (message_id, nickname, reaction, _now()),
        )
        return True


def get_message_reaction_counts(message_ids):
    """{message_id: {reaction: count}} 형태로 반환한다."""
    if not message_ids:
        return {}
    placeholders = ",".join("?" for _ in message_ids)
    with db_cursor() as cur:
        cur.execute(
            f"SELECT message_id, reaction, COUNT(*) AS c FROM message_reactions "
            f"WHERE message_id IN ({placeholders}) GROUP BY message_id, reaction",
            message_ids,
        )
        result = {}
        for r in cur.fetchall():
            result.setdefault(r["message_id"], {})[r["reaction"]] = r["c"]
        return result


def get_message_reactions_by_user(message_ids, nickname):
    """{message_id: [reaction, ...]} 형태로, nickname 본인이 남긴 반응만 반환한다."""
    if not message_ids:
        return {}
    placeholders = ",".join("?" for _ in message_ids)
    with db_cursor() as cur:
        cur.execute(
            f"SELECT message_id, reaction FROM message_reactions "
            f"WHERE message_id IN ({placeholders}) AND nickname=?",
            message_ids + [nickname],
        )
        result = {}
        for r in cur.fetchall():
            result.setdefault(r["message_id"], []).append(r["reaction"])
        return result


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


def add_mentions(message_id, room_id, target_nicknames):
    if not target_nicknames:
        return
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.executemany(
            "INSERT INTO mentions (message_id, room_id, target_nickname, created_at, read_at) "
            "VALUES (?,?,?,?,NULL)",
            [(message_id, room_id, name, now) for name in target_nicknames],
        )


def get_unread_direct_message_counts(nickname):
    """1:1(direct) 방에서 상대가 보낸, 아직 읽지 않은 메시지 개수를 방별로 센다.
    멘션 여부와 무관하게 모든 메시지를 카운트한다 — 1:1 대화는 특성상 서로 멘션을
    안 붙이는 경우가 많아 멘션 배지만으로는 새 메시지 도착을 알아채기 어렵기 때문."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT m.room_id AS room_id, COUNT(*) AS c
            FROM messages m
            JOIN direct_participants dp ON dp.room_id = m.room_id AND dp.nickname = ?
            WHERE m.sender != ? AND m.type != 'system'
              AND m.id NOT IN (SELECT message_id FROM message_reads WHERE user_id = ?)
            GROUP BY m.room_id
            """,
            (nickname, nickname, nickname),
        )
        return {r["room_id"]: r["c"] for r in cur.fetchall()}


def get_unread_mention_counts(nickname):
    with db_cursor() as cur:
        cur.execute(
            "SELECT room_id, COUNT(*) AS c FROM mentions "
            "WHERE target_nickname=? AND read_at IS NULL GROUP BY room_id",
            (nickname,),
        )
        return {r["room_id"]: r["c"] for r in cur.fetchall()}


def mark_mentions_read(room_id, nickname, up_to_message_id):
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE mentions SET read_at=? WHERE room_id=? AND target_nickname=? "
            "AND read_at IS NULL AND message_id<=?",
            (now, room_id, nickname, up_to_message_id),
        )
        return cur.rowcount > 0


def create_subject(name):
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO subjects (name, status, created_at) VALUES (?,?,?)",
            (name, "active", now),
        )
        subject_id = cur.lastrowid
        cur.execute("SELECT * FROM subjects WHERE id=?", (subject_id,))
        return dict(cur.fetchone())


def list_subjects(status=None):
    with db_cursor() as cur:
        if status:
            cur.execute("SELECT * FROM subjects WHERE status=? ORDER BY created_at ASC", (status,))
        else:
            cur.execute("SELECT * FROM subjects ORDER BY created_at ASC")
        return [dict(r) for r in cur.fetchall()]


def get_subject(subject_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM subjects WHERE id=?", (subject_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def set_subject_status(subject_id, status):
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE subjects SET status=? WHERE id=?", (status, subject_id))
        cur.execute("SELECT * FROM subjects WHERE id=?", (subject_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_issue_fields():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM issue_custom_fields ORDER BY created_at ASC")
        return [dict(r) for r in cur.fetchall()]


def create_issue_field(label):
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO issue_custom_fields (label, created_at) VALUES (?,?)",
            (label, now),
        )
        field_id = cur.lastrowid
        cur.execute("SELECT * FROM issue_custom_fields WHERE id=?", (field_id,))
        return dict(cur.fetchone())


def _issue_row_to_dict(row):
    d = dict(row)
    try:
        d["custom_fields"] = json.loads(d["custom_fields"]) if d["custom_fields"] else {}
    except (TypeError, ValueError):
        d["custom_fields"] = {}
    return d


def create_issue(subject_id, tc_num, body, steps_to_reproduce, reporter, custom_fields):
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO issues (subject_id, tc_num, body, steps_to_reproduce, reporter, "
            "custom_fields, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (subject_id, tc_num, body, steps_to_reproduce, reporter,
             json.dumps(custom_fields or {}, ensure_ascii=False), now, now),
        )
        issue_id = cur.lastrowid
        cur.execute("SELECT * FROM issues WHERE id=?", (issue_id,))
        return _issue_row_to_dict(cur.fetchone())


def update_issue(issue_id, subject_id, tc_num, body, steps_to_reproduce, custom_fields):
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE issues SET subject_id=?, tc_num=?, body=?, steps_to_reproduce=?, "
            "custom_fields=?, updated_at=? WHERE id=?",
            (subject_id, tc_num, body, steps_to_reproduce,
             json.dumps(custom_fields or {}, ensure_ascii=False), now, issue_id),
        )
        cur.execute("SELECT * FROM issues WHERE id=?", (issue_id,))
        row = cur.fetchone()
        return _issue_row_to_dict(row) if row else None


def delete_issue(issue_id):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM issues WHERE id=?", (issue_id,))
        return cur.rowcount > 0


def get_issue(issue_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM issues WHERE id=?", (issue_id,))
        row = cur.fetchone()
        return _issue_row_to_dict(row) if row else None


def list_issues(subject_id=None, reporter=None):
    query = "SELECT * FROM issues"
    clauses = []
    params = []
    if subject_id:
        clauses.append("subject_id=?")
        params.append(subject_id)
    if reporter:
        clauses.append("reporter=?")
        params.append(reporter)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with db_cursor() as cur:
        cur.execute(query, params)
        return [_issue_row_to_dict(r) for r in cur.fetchall()]
