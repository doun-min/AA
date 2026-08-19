from urllib.parse import quote

from flask import Blueprint, Response, abort, session

import db

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/api/rooms/<int:room_id>/log.txt")
def download_log(room_id):
    nickname = session.get("nickname")
    if not nickname:
        abort(401)
    room = db.get_room(room_id)
    if not room:
        abort(404)
    if not db.can_access_room(room, nickname):
        abort(403)

    messages = db.list_messages(room_id, limit=None)
    lines = [db.format_message_line(m) for m in messages]
    text = "\n".join(lines) + "\n"

    filename = f"{room['name']}_log.txt"
    resp = Response(text, mimetype="text/plain; charset=utf-8")
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=\"chat_log.txt\"; filename*=UTF-8''{quote(filename)}"
    )
    return resp
