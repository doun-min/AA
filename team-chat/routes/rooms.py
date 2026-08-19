import os

from flask import Blueprint, abort, jsonify, request, session

import auth
import config
import db
from extensions import socketio

rooms_bp = Blueprint("rooms_api", __name__, url_prefix="/api")


def _backup_messages_to_file(room, admin_nickname, start_date, end_date, messages):
    """삭제 대상 메시지를 지우기 전에, 방별로 계속 이어 쓰는(append) 백업 txt 파일에 기록해둔다."""
    os.makedirs(config.LOG_BACKUP_FOLDER, exist_ok=True)
    path = os.path.join(config.LOG_BACKUP_FOLDER, f"room_{room['id']}_log_backup.txt")
    header = (
        f"===== 삭제일시: {db.now_iso()} | 삭제자: {admin_nickname} | "
        f"방: {room['name']} | 대상 기간: {start_date} ~ {end_date} | {len(messages)}건 ====="
    )
    lines = [header] + [db.format_message_line(m) for m in messages] + [""]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _require_login():
    nickname = session.get("nickname")
    if not nickname:
        abort(401)
    return nickname


@rooms_bp.route("/rooms", methods=["POST"])
def create_room():
    nickname = _require_login()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify(error="방 이름을 입력해주세요."), 400
    if len(name) > config.ROOM_NAME_MAX_LENGTH:
        return jsonify(error=f"방 이름은 {config.ROOM_NAME_MAX_LENGTH}자 이하로 입력해주세요."), 400

    is_private = bool(body.get("is_private"))
    members = set()
    if is_private:
        members = {m.strip() for m in (body.get("members") or []) if isinstance(m, str) and m.strip()}
        members.discard(nickname)
        invalid = [m for m in members if not db.user_exists(m)]
        if invalid:
            return jsonify(error=f"등록되지 않은 사용자는 초대할 수 없습니다: {', '.join(invalid)}"), 400

    room = db.create_group_room(name, nickname, members, is_private=is_private)
    for member in members:
        _notify_member(member, "room_member_added", {"room_id": room["id"], "room_name": room["name"]})
    return jsonify(room=room), 201


def _notify_member(nickname, event, payload):
    """특정 닉네임이 현재 열어둔 모든 탭/소켓에 이벤트를 보낸다."""
    from sockets import nickname_to_sids

    for sid in nickname_to_sids.get(nickname, ()):
        socketio.emit(event, payload, room=sid)


@rooms_bp.route("/rooms/<int:room_id>", methods=["DELETE"])
def delete_room(room_id):
    nickname = _require_login()
    room = db.get_room(room_id)
    if not room:
        abort(404)
    if not room["is_deletable"]:
        return jsonify(error="전체 채팅방은 삭제할 수 없습니다."), 400

    is_owner = room.get("owner_nickname") == nickname
    if not (is_owner or auth.is_admin(nickname)):
        return jsonify(error="방을 삭제할 권한이 없습니다."), 403

    db.delete_room(room_id)
    socketio.emit("room_deleted", {"room_id": room_id}, room=str(room_id))
    return jsonify(ok=True)


@rooms_bp.route("/rooms/<int:room_id>/transfer", methods=["POST"])
def transfer_room(room_id):
    nickname = _require_login()
    room = db.get_room(room_id)
    if not room or room["type"] == "direct":
        abort(404)

    is_owner = room.get("owner_nickname") == nickname
    if not (is_owner or auth.is_admin(nickname)):
        return jsonify(error="방장 권한을 위임할 권한이 없습니다."), 403

    new_owner = ((request.get_json(silent=True) or {}).get("new_owner") or "").strip()
    if not new_owner:
        return jsonify(error="새 방장 닉네임을 입력해주세요."), 400
    if new_owner == room.get("owner_nickname"):
        return jsonify(error="이미 방장인 사용자입니다."), 400
    if not auth.is_active(new_owner):
        return jsonify(error="현재 접속 중인 사용자만 방장으로 지정할 수 있습니다."), 400
    if room["is_private"] and not db.is_room_participant(room_id, new_owner):
        return jsonify(error="방 멤버에게만 방장을 위임할 수 있습니다."), 400

    db.transfer_ownership(room_id, new_owner)
    socketio.emit("owner_changed", {"room_id": room_id, "new_owner": new_owner}, room=str(room_id))
    return jsonify(ok=True, new_owner=new_owner)


@rooms_bp.route("/rooms/<int:room_id>/members", methods=["POST"])
def invite_room_member(room_id):
    nickname = _require_login()
    room = db.get_room(room_id)
    if not room or room["type"] == "direct":
        abort(404)
    if not room["is_private"]:
        return jsonify(error="공개 방은 초대가 필요 없습니다."), 400

    is_owner = room.get("owner_nickname") == nickname
    if not (is_owner or auth.is_admin(nickname)):
        return jsonify(error="멤버를 초대할 권한이 없습니다."), 403

    target = ((request.get_json(silent=True) or {}).get("nickname") or "").strip()
    if not target:
        return jsonify(error="초대할 사용자를 선택해주세요."), 400
    if not db.user_exists(target):
        return jsonify(error="등록되지 않은 사용자입니다."), 400
    if db.is_room_participant(room_id, target):
        return jsonify(error="이미 참여 중인 사용자입니다."), 400

    db.add_room_member(room_id, target)
    text = f"{nickname}님이 {target}님을 초대했습니다."
    sys_msg = db.add_message(room_id, nickname, "system", content=text)
    socketio.emit(
        "new_message",
        {
            "id": sys_msg["id"], "room_id": room_id, "sender": nickname, "type": "system",
            "content": text, "created_at": sys_msg["created_at"], "unread_count": 0,
        },
        room=str(room_id),
    )
    socketio.emit(
        "room_member_added",
        {"room_id": room_id, "room_name": room["name"], "nickname": target, "online": auth.is_active(target)},
        room=str(room_id),
    )
    _notify_member(target, "room_member_added", {"room_id": room_id, "room_name": room["name"]})
    return jsonify(ok=True, nickname=target), 201


@rooms_bp.route("/rooms/<int:room_id>/members/<target_nickname>", methods=["DELETE"])
def remove_room_member(room_id, target_nickname):
    nickname = _require_login()
    room = db.get_room(room_id)
    if not room or room["type"] == "direct":
        abort(404)
    if not room["is_private"]:
        return jsonify(error="공개 방은 멤버 제거를 지원하지 않습니다."), 400

    is_owner = room.get("owner_nickname") == nickname
    if not (is_owner or auth.is_admin(nickname)):
        return jsonify(error="멤버를 제거할 권한이 없습니다."), 403
    if target_nickname == room.get("owner_nickname"):
        return jsonify(error="방장은 제거할 수 없습니다. 먼저 방장 위임을 해주세요."), 400
    if not db.is_room_participant(room_id, target_nickname):
        return jsonify(error="방 멤버가 아닙니다."), 400

    db.remove_room_member(room_id, target_nickname)
    text = f"{nickname}님이 {target_nickname}님을 내보냈습니다."
    sys_msg = db.add_message(room_id, nickname, "system", content=text)
    socketio.emit(
        "new_message",
        {
            "id": sys_msg["id"], "room_id": room_id, "sender": nickname, "type": "system",
            "content": text, "created_at": sys_msg["created_at"], "unread_count": 0,
        },
        room=str(room_id),
    )
    socketio.emit("room_member_removed", {"room_id": room_id, "nickname": target_nickname}, room=str(room_id))
    _notify_member(target_nickname, "room_member_removed", {"room_id": room_id, "room_name": room["name"]})
    return jsonify(ok=True)


@rooms_bp.route("/rooms/direct", methods=["POST"])
def start_direct_room():
    nickname = _require_login()
    target = ((request.get_json(silent=True) or {}).get("target") or "").strip()
    if not target or target == nickname:
        return jsonify(error="대화 상대를 선택해주세요."), 400
    if not auth.is_active(target):
        return jsonify(error="현재 접속 중인 사용자가 아닙니다."), 400
    room = db.get_or_create_direct_room(nickname, target)
    return jsonify(room=room), 201


@rooms_bp.route("/active_users")
def active_users():
    nickname = _require_login()
    return jsonify(users=[u for u in auth.list_active() if u != nickname])


@rooms_bp.route("/all_users")
def all_users():
    """방 생성/초대 후보 목록: 접속 여부와 무관하게 DB에 로그인 이력이 있는 전체 사용자."""
    nickname = _require_login()
    users = sorted(
        ({"nickname": u, "online": auth.is_active(u)} for u in db.list_all_users() if u != nickname),
        key=lambda u: (not u["online"], u["nickname"]),
    )
    return jsonify(users=users)


@rooms_bp.route("/messages/<int:message_id>/reactions", methods=["POST"])
def toggle_message_reaction(message_id):
    nickname = _require_login()
    body = request.get_json(silent=True) or {}
    reaction = body.get("reaction")
    if reaction not in db.REACTION_TYPES:
        return jsonify(error="올바르지 않은 반응입니다."), 400

    msg = db.get_message(message_id)
    if not msg or msg["type"] == "system":
        abort(404)
    room = db.get_room(msg["room_id"])
    if not room or not db.can_access_room(room, nickname):
        abort(403)

    added = db.toggle_message_reaction(message_id, nickname, reaction)
    counts = db.get_message_reaction_counts([message_id]).get(message_id, {})
    reactors = db.get_message_reactions_grouped([message_id]).get(message_id, {})
    payload = {
        "message_id": message_id,
        "room_id": msg["room_id"],
        "reaction": reaction,
        "nickname": nickname,
        "added": added,
        "counts": counts,
        "reactors": reactors,
    }
    socketio.emit("reaction_update", payload, room=str(msg["room_id"]))
    return jsonify(added=added, counts=counts)


@rooms_bp.route("/messages/<int:message_id>", methods=["DELETE"])
def delete_message(message_id):
    nickname = _require_login()
    msg = db.get_message(message_id)
    if not msg or msg["type"] == "system" or msg["deleted_at"]:
        abort(404)
    is_own = msg["sender"] == nickname
    is_admin = auth.is_admin(nickname)
    if not is_own and not is_admin:
        return jsonify(error="본인 메시지만 삭제할 수 있습니다."), 403

    # 관리자가 타인의 메시지를 지울 때는 완전 삭제(하드 삭제), 본인 메시지는 기존처럼
    # '삭제된 메시지입니다' 흔적만 남기는 소프트 삭제를 유지한다.
    hard = is_admin and not is_own
    if hard:
        db.hard_delete_message(message_id)
    else:
        db.delete_message(message_id)
    socketio.emit(
        "message_deleted",
        {"message_id": message_id, "room_id": msg["room_id"], "hard": hard},
        room=str(msg["room_id"]),
    )
    return jsonify(ok=True)


@rooms_bp.route("/rooms/<int:room_id>/messages", methods=["DELETE"])
def clear_room_log(room_id):
    """관리자 전용: 지정한 기간의 메시지 로그를 백업 후 삭제한다(방은 유지)."""
    nickname = _require_login()
    if not auth.is_admin(nickname):
        return jsonify(error="로그를 초기화할 권한이 없습니다."), 403
    room = db.get_room(room_id)
    if not room:
        abort(404)

    body = request.get_json(silent=True) or {}
    start_date = (body.get("start_date") or "").strip()
    end_date = (body.get("end_date") or "").strip()
    if not start_date or not end_date:
        return jsonify(error="삭제할 시작일과 종료일을 선택해주세요."), 400
    if start_date > end_date:
        return jsonify(error="시작일이 종료일보다 늦을 수 없습니다."), 400

    messages = db.list_messages_in_range(room_id, start_date, end_date)
    if not messages:
        return jsonify(error="해당 기간에 삭제할 로그가 없습니다."), 400

    _backup_messages_to_file(room, nickname, start_date, end_date, messages)
    deleted_ids = [m["id"] for m in messages]
    db.clear_room_messages_in_range(room_id, start_date, end_date)

    text = f"{nickname}님이 {start_date} ~ {end_date} 기간의 로그({len(deleted_ids)}건)를 삭제했습니다."
    sys_msg = db.add_message(room_id, nickname, "system", content=text)
    socketio.emit(
        "room_log_cleared",
        {
            "room_id": room_id,
            "deleted_message_ids": deleted_ids,
            "system_message": {
                "id": sys_msg["id"], "room_id": room_id, "sender": nickname, "type": "system",
                "content": text, "created_at": sys_msg["created_at"], "unread_count": 0,
            },
        },
        room=str(room_id),
    )
    return jsonify(ok=True, deleted_count=len(deleted_ids))


@rooms_bp.route("/users/<nickname>", methods=["DELETE"])
def delete_user(nickname):
    """관리자 전용: 사용자 계정을 시스템에서 완전히 삭제한다."""
    requester = _require_login()
    if not auth.is_admin(requester):
        return jsonify(error="사용자를 삭제할 권한이 없습니다."), 403
    if nickname == requester:
        return jsonify(error="본인 계정은 삭제할 수 없습니다."), 400
    if not db.user_exists(nickname):
        return jsonify(error="존재하지 않는 사용자입니다."), 404
    if auth.is_admin(nickname):
        return jsonify(error="관리자 계정은 삭제할 수 없습니다."), 400

    db.delete_user_account(nickname)
    auth.release_nickname(nickname)
    _notify_member(nickname, "account_deleted", {})
    socketio.emit("user_account_deleted", {"nickname": nickname})

    from sockets import broadcast_active_users

    broadcast_active_users()
    return jsonify(ok=True)


@rooms_bp.route("/admins", methods=["POST"])
def promote_admin():
    """기존 관리자 전용: 일반 사용자를 관리자로 지정한다."""
    requester = _require_login()
    if not auth.is_admin(requester):
        return jsonify(error="관리자를 지정할 권한이 없습니다."), 403

    target = ((request.get_json(silent=True) or {}).get("nickname") or "").strip()
    if not target:
        return jsonify(error="지정할 사용자를 선택해주세요."), 400
    if not db.user_exists(target):
        return jsonify(error="존재하지 않는 사용자입니다."), 404
    if auth.is_admin(target):
        return jsonify(error="이미 관리자입니다."), 400

    db.set_user_role(target, "admin")
    socketio.emit("admin_role_changed", {"nickname": target, "role": "admin"})
    return jsonify(ok=True)


@rooms_bp.route("/admins/<nickname>", methods=["DELETE"])
def demote_admin(nickname):
    """기존 관리자 전용: 다른 관리자의 권한을 해제한다.
    본인 해제는 막아서, 이 규칙만으로 관리자가 0명이 되는 상황을 원천 차단한다."""
    requester = _require_login()
    if not auth.is_admin(requester):
        return jsonify(error="관리자를 해제할 권한이 없습니다."), 403
    if nickname == requester:
        return jsonify(error="본인은 해제할 수 없습니다. 다른 관리자에게 요청해주세요."), 400
    if not db.user_exists(nickname):
        return jsonify(error="존재하지 않는 사용자입니다."), 404
    if not auth.is_admin(nickname):
        return jsonify(error="관리자가 아닙니다."), 400

    db.set_user_role(nickname, "member")
    socketio.emit("admin_role_changed", {"nickname": nickname, "role": "member"})
    return jsonify(ok=True)
