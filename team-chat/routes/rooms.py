from flask import Blueprint, abort, jsonify, request, session

import auth
import config
import db
from extensions import socketio

rooms_bp = Blueprint("rooms_api", __name__, url_prefix="/api")


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

    members = {m.strip() for m in (body.get("members") or []) if isinstance(m, str) and m.strip()}
    members.discard(nickname)
    invalid = [m for m in members if not auth.is_active(m)]
    if invalid:
        return jsonify(error=f"현재 접속 중이 아닌 사용자는 초대할 수 없습니다: {', '.join(invalid)}"), 400

    room = db.create_group_room(name, nickname, members)
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
    if not (is_owner or auth.is_superadmin(nickname)):
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
    if not (is_owner or auth.is_superadmin(nickname)):
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
    if not (is_owner or auth.is_superadmin(nickname)):
        return jsonify(error="멤버를 초대할 권한이 없습니다."), 403

    target = ((request.get_json(silent=True) or {}).get("nickname") or "").strip()
    if not target:
        return jsonify(error="초대할 사용자를 선택해주세요."), 400
    if not auth.is_active(target):
        return jsonify(error="현재 접속 중인 사용자만 초대할 수 있습니다."), 400
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
        {"room_id": room_id, "room_name": room["name"], "nickname": target},
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
    if not (is_owner or auth.is_superadmin(nickname)):
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
