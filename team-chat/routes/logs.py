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
    if room["type"] == "direct" and not db.is_direct_participant(room_id, nickname):
        abort(403)

    messages = db.list_messages(room_id, limit=None)
    lines = []
    for m in messages:
        ts = m["created_at"].replace("T", " ").split("+")[0]
        if m["type"] == "text":
            body = m["content"]
        elif m["type"] == "system":
            body = f"* {m['content']}"
        else:
            body = f"[파일] {m['original_filename']}"
        lines.append(f"[{ts}] {m['sender']}: {body}")
    text = "\n".join(lines) + "\n"

    filename = f"{room['name']}_log.txt"
    resp = Response(text, mimetype="text/plain; charset=utf-8")
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=\"chat_log.txt\"; filename*=UTF-8''{quote(filename)}"
    )
    return resp
