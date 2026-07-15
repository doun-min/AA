import os
import uuid

from flask import Blueprint, abort, jsonify, request, send_from_directory, session
from werkzeug.utils import secure_filename

import config
import db
from extensions import socketio

files_bp = Blueprint("files", __name__)


def _check_room_access(room_id, nickname):
    room = db.get_room(room_id)
    if not room:
        abort(404)
    if not db.can_access_room(room, nickname):
        abort(403)
    return room


def _split_ext(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


@files_bp.route("/api/rooms/<int:room_id>/upload", methods=["POST"])
def upload_file(room_id):
    nickname = session.get("nickname")
    if not nickname:
        abort(401)
    room = _check_room_access(room_id, nickname)

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify(error="업로드할 파일을 선택해주세요."), 400

    ext = _split_ext(upload.filename)
    if ext not in config.ALLOWED_EXTENSIONS:
        return jsonify(error="허용되지 않는 파일 형식입니다."), 400

    safe_name = secure_filename(upload.filename) or f"file.{ext}"
    stored_filename = f"{uuid.uuid4().hex}_{safe_name}"
    room_dir = os.path.join(config.UPLOAD_FOLDER, str(room_id))
    os.makedirs(room_dir, exist_ok=True)
    upload.save(os.path.join(room_dir, stored_filename))

    msg_type = "image" if ext in config.IMAGE_EXTENSIONS else "file"
    msg = db.add_message(
        room_id,
        nickname,
        msg_type,
        file_path=stored_filename,
        original_filename=upload.filename,
    )
    unread_count = db.get_messages_unread_counts(room_id, [msg["id"]]).get(msg["id"], 0)
    payload = {
        "id": msg["id"],
        "room_id": room_id,
        "sender": nickname,
        "type": msg_type,
        "file_path": stored_filename,
        "original_filename": upload.filename,
        "created_at": msg["created_at"],
        "unread_count": unread_count,
    }
    socketio.emit("new_message", payload, room=str(room_id))

    if room["type"] == "direct":
        # 1:1 방에서 파일/이미지를 보낸 경우에도 상대방 방 목록 배지를 즉시 갱신한다
        # (텍스트 메시지의 sockets.handle_send_message와 동일한 처리).
        from sockets import emit_room_badge_counts

        for member in db.get_room_member_nicknames(room_id, "direct"):
            if member != nickname:
                emit_room_badge_counts(member)

    return jsonify(message=payload), 201


@files_bp.route("/files/<int:room_id>/<path:filename>")
def get_file(room_id, filename):
    nickname = session.get("nickname")
    if not nickname:
        abort(401)
    _check_room_access(room_id, nickname)
    room_dir = os.path.join(config.UPLOAD_FOLDER, str(room_id))
    return send_from_directory(room_dir, filename)
