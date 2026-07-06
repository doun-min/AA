import re
import threading

from flask import request, session
from flask_socketio import join_room, leave_room, emit

import auth
import db
from extensions import socketio

# sid <-> nickname 매핑 (여러 탭에서 동시 접속 가능하도록 nickname -> sid 집합)
sid_to_nickname = {}
nickname_to_sids = {}
# room_id -> 현재 그 방에 join 되어 있는 닉네임 집합 (연결 종료 시 정리용)
room_members = {}

MENTION_RE = re.compile(r"@([^\s@,]+)")

# 페이지 이동(소켓 재연결) 중 닉네임이 잠깐 풀렸다가 다른 사람이 선점하는 것을 막기 위한 유예 시간
GRACE_SECONDS = 5
_release_timers = {}
_timer_lock = threading.Lock()


def _cancel_pending_release(nickname):
    with _timer_lock:
        timer = _release_timers.pop(nickname, None)
        if timer:
            timer.cancel()


def _schedule_release(nickname):
    def _do_release():
        with _timer_lock:
            _release_timers.pop(nickname, None)
        if not nickname_to_sids.get(nickname):
            auth.release_nickname(nickname)
            for members in room_members.values():
                members.discard(nickname)

    with _timer_lock:
        old = _release_timers.get(nickname)
        if old:
            old.cancel()
        timer = threading.Timer(GRACE_SECONDS, _do_release)
        timer.daemon = True
        _release_timers[nickname] = timer
        timer.start()


@socketio.on("connect")
def handle_connect():
    nickname = session.get("nickname")
    if not nickname:
        return False
    _cancel_pending_release(nickname)
    sid_to_nickname[request.sid] = nickname
    nickname_to_sids.setdefault(nickname, set()).add(request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    nickname = sid_to_nickname.pop(sid, None)
    if not nickname:
        return
    sids = nickname_to_sids.get(nickname)
    if sids:
        sids.discard(sid)
        if not sids:
            nickname_to_sids.pop(nickname, None)
            _schedule_release(nickname)


@socketio.on("join")
def handle_join(data):
    nickname = session.get("nickname")
    room_id = (data or {}).get("room_id")
    if not nickname or room_id is None:
        return
    room = db.get_room(room_id)
    if not room:
        return
    if room["type"] == "direct" and not db.is_direct_participant(room_id, nickname):
        return
    join_room(str(room_id))
    room_members.setdefault(room_id, set()).add(nickname)
    db.ensure_room_participant(room_id, nickname)


@socketio.on("leave")
def handle_leave(data):
    nickname = session.get("nickname")
    room_id = (data or {}).get("room_id")
    if room_id is None:
        return
    leave_room(str(room_id))
    if room_id in room_members:
        room_members[room_id].discard(nickname)


@socketio.on("send_message")
def handle_send_message(data):
    nickname = session.get("nickname")
    room_id = (data or {}).get("room_id")
    text = ((data or {}).get("text") or "").strip()
    if not nickname or room_id is None or not text:
        return

    room = db.get_room(room_id)
    if not room:
        return
    if room["type"] == "direct" and not db.is_direct_participant(room_id, nickname):
        return

    msg = db.add_message(room_id, nickname, "text", content=text)
    unread_count = db.get_messages_unread_counts(room_id, [msg["id"]]).get(msg["id"], 0)
    payload = {
        "id": msg["id"],
        "room_id": room_id,
        "sender": nickname,
        "type": "text",
        "content": text,
        "created_at": msg["created_at"],
        "unread_count": unread_count,
    }
    emit("new_message", payload, room=str(room_id))

    mentioned_names = set(MENTION_RE.findall(text))
    for name in mentioned_names:
        if name == nickname:
            continue
        sids = nickname_to_sids.get(name)
        if not sids:
            continue
        for sid in sids:
            emit(
                "mention",
                {
                    "room_id": room_id,
                    "room_name": room["name"],
                    "sender": nickname,
                    "text": text,
                },
                room=sid,
            )


@socketio.on("mark_read")
def handle_mark_read(data):
    nickname = session.get("nickname")
    room_id = (data or {}).get("room_id")
    up_to_message_id = (data or {}).get("up_to_message_id")
    if not nickname or room_id is None or up_to_message_id is None:
        return

    room = db.get_room(room_id)
    if not room:
        return
    if room["type"] == "direct" and not db.is_direct_participant(room_id, nickname):
        return

    msg_ids = db.mark_messages_read(room_id, nickname, up_to_message_id)
    if not msg_ids:
        return

    counts = db.get_messages_unread_counts(room_id, msg_ids)
    emit(
        "read_update",
        {
            "room_id": room_id,
            "updates": [{"id": mid, "unread_count": c} for mid, c in counts.items()],
        },
        room=str(room_id),
    )
