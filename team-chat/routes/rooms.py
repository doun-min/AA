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
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify(error="방 이름을 입력해주세요."), 400
    if len(name) > config.ROOM_NAME_MAX_LENGTH:
        return jsonify(error=f"방 이름은 {config.ROOM_NAME_MAX_LENGTH}자 이하로 입력해주세요."), 400
    room = db.create_group_room(name, nickname)
    return jsonify(room=room), 201


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

    db.transfer_ownership(room_id, new_owner)
    socketio.emit("owner_changed", {"room_id": room_id, "new_owner": new_owner}, room=str(room_id))
    return jsonify(ok=True, new_owner=new_owner)


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
