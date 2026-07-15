import re
import threading

from flask import request, session
from flask_socketio import join_room, leave_room, emit

import auth
import config
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


def emit_room_badge_counts(nickname):
    sids = nickname_to_sids.get(nickname)
    if not sids:
        return
    # 방 목록 배지(rooms.html)는 그룹/전체 방은 멘션 카운트, 1:1 방은 안 읽은
    # 메시지 카운트를 쓴다. 사이드바 총합 배지(total)도 두 카운트를 합산해서
    # "채팅" 메뉴만 봐도 안 읽은 멘션/1:1 메시지가 있는지 알 수 있게 한다.
    # (OS 알림(Notification)은 이 total과 무관하게 멘션 기준 그대로.)
    mention_counts = db.get_unread_mention_counts(nickname)
    direct_counts = db.get_unread_direct_message_counts(nickname)
    room_counts = {**mention_counts, **direct_counts}
    total = sum(mention_counts.values()) + sum(direct_counts.values())
    payload = {"total": total, "rooms": room_counts}
    for sid in sids:
        emit("mention_count_update", payload, room=sid)


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
    if not db.can_access_room(room, nickname):
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
    if not db.can_access_room(room, nickname):
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

    mentioned_names = set(MENTION_RE.findall(text)) - {nickname}
    if config.MENTION_ALL in mentioned_names:
        mentioned_names.discard(config.MENTION_ALL)
        mentioned_names |= set(db.get_room_member_nicknames(room_id, room["type"])) - {nickname}
    # 방에 접근 권한이 없는 사람(예: 비공개 방 비멤버)은 멘션 대상에서 제외한다.
    # 안 그러면 방 이름/메시지 내용이 담긴 알림이 그 사람에게 그대로 새어나간다.
    mentioned_names = {n for n in mentioned_names if db.can_access_room(room, n)}
    if mentioned_names:
        db.add_mentions(msg["id"], room_id, mentioned_names)
    for name in mentioned_names:
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
        emit_room_badge_counts(name)

    # 1:1 방은 멘션 여부와 무관하게 메시지가 오면 방 목록 배지를 띄워야 하므로,
    # 멘션으로 이미 알림을 보낸 상대가 아니라면 여기서 별도로 배지만 갱신한다
    # (OS 알림(emit("mention", ...))은 위 멘션 루프에서만 발생하며 여기서는 건드리지 않는다).
    if room["type"] == "direct":
        for member in db.get_room_member_nicknames(room_id, "direct"):
            if member != nickname and member not in mentioned_names:
                emit_room_badge_counts(member)


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
    if not db.can_access_room(room, nickname):
        return

    msg_ids = db.mark_messages_read(room_id, nickname, up_to_message_id)
    mentions_changed = db.mark_mentions_read(room_id, nickname, up_to_message_id)
    # direct 방은 메시지를 읽음 처리한 것 자체가 배지 카운트에 영향을 주므로
    # (멘션 여부와 무관하게) 메시지가 실제로 읽음 처리됐다면 항상 다시 계산해 보낸다.
    if mentions_changed or (room["type"] == "direct" and msg_ids):
        emit_room_badge_counts(nickname)
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
