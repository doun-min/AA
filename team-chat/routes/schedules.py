from flask import Blueprint, abort, jsonify, request, session

import config
import db
from extensions import socketio

schedules_bp = Blueprint("schedules_api", __name__, url_prefix="/api/schedules")

CATEGORY_LABELS = {"annual": "연차", "half_day": "반차", "work": "업무일정"}


def _require_login():
    nickname = session.get("nickname")
    if not nickname:
        abort(401)
    return nickname


def _format_entry(s):
    label = CATEGORY_LABELS.get(s["category"], s["category"])
    if s["category"] in ("annual", "half_day"):
        return f"{s['nickname']} {label}"
    if s.get("start_time"):
        hour = int(s["start_time"].split(":")[0])
        return f"{hour}시 {s['title']}"
    return s["title"]


def _format_range(schedule):
    date = schedule["date"]
    end_date = schedule.get("end_date") or date
    start_time = schedule.get("start_time")
    end_time = schedule.get("end_time")

    start = f"{date} {start_time}" if start_time else date
    if end_date == date:
        end = end_time or ""
    else:
        end = f"{end_date} {end_time}" if end_time else end_date
    if not end:
        return start
    return f"{start} ~ {end}"


def format_banner(schedules):
    if not schedules:
        return "오늘 등록된 일정이 없습니다."
    return "오늘 일정: " + " | ".join(_format_entry(s) for s in schedules)


def _format_detail(schedule):
    label = CATEGORY_LABELS.get(schedule["category"], schedule["category"])
    if schedule["category"] == "work":
        return f"{_format_range(schedule)} {schedule['title']}"
    if schedule.get("end_date") and schedule["end_date"] != schedule["date"]:
        return f"{schedule['date']} ~ {schedule['end_date']} {label}"
    return f"{schedule['date']} {label}"


def _notify_schedule_room(nickname, schedule, action):
    room = db.get_room_by_name(config.SCHEDULE_ROOM_NAME)
    if not room:
        return
    text = f"[일정{action}] {nickname}님이 일정을 {action}했습니다: {_format_detail(schedule)}"
    msg = db.add_message(room["id"], nickname, "system", content=text)
    payload = {
        "id": msg["id"],
        "room_id": room["id"],
        "sender": nickname,
        "type": "system",
        "content": text,
        "created_at": msg["created_at"],
        "unread_count": 0,
    }
    socketio.emit("new_message", payload, room=str(room["id"]))


def _validate_body(body, require_all=True):
    category = (body.get("category") or "").strip()
    title = (body.get("title") or "").strip()
    date_str = (body.get("date") or "").strip()
    end_date_str = (body.get("end_date") or "").strip() or date_str
    start_time = (body.get("start_time") or "").strip() or None
    end_time = (body.get("end_time") or "").strip() or None

    if category not in CATEGORY_LABELS:
        return None, "일정 구분이 올바르지 않습니다."
    if require_all and not title:
        return None, "일정 내용을 입력해주세요."
    if require_all and not date_str:
        return None, "시작 일자를 선택해주세요."
    if require_all and not end_date_str:
        return None, "종료 일자를 선택해주세요."
    if date_str and end_date_str and end_date_str < date_str:
        return None, "종료 일시가 시작 일시보다 빠를 수 없습니다."
    if date_str and end_date_str and date_str == end_date_str and start_time and end_time and end_time < start_time:
        return None, "종료 일시가 시작 일시보다 빠를 수 없습니다."
    return {
        "category": category,
        "title": title,
        "date": date_str,
        "end_date": end_date_str,
        "start_time": start_time,
        "end_time": end_time,
    }, None


@schedules_bp.route("", methods=["GET"])
def list_schedules():
    _require_login()
    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
    except (TypeError, ValueError):
        today = db.today_kst()
        year, month = today.year, today.month
    schedules = db.list_schedules_for_month(year, month)
    return jsonify(schedules=schedules)


@schedules_bp.route("/today", methods=["GET"])
def today_schedules():
    _require_login()
    today_str = db.today_kst().isoformat()
    schedules = db.list_schedules_for_date(today_str)
    return jsonify(schedules=schedules, banner=format_banner(schedules), date=today_str)


@schedules_bp.route("", methods=["POST"])
def create_schedule():
    nickname = _require_login()
    body = request.get_json(silent=True) or {}
    data, error = _validate_body(body)
    if error:
        return jsonify(error=error), 400

    schedule = db.create_schedule(
        nickname, data["category"], data["title"], data["date"],
        data["end_date"], data["start_time"], data["end_time"],
    )
    _notify_schedule_room(nickname, schedule, "등록")
    socketio.emit("schedule_updated", {"date": schedule["date"]})
    return jsonify(schedule=schedule), 201


@schedules_bp.route("/<int:schedule_id>", methods=["PUT"])
def update_schedule(schedule_id):
    nickname = _require_login()
    existing = db.get_schedule(schedule_id)
    if not existing:
        abort(404)
    if existing["nickname"] != nickname:
        return jsonify(error="본인 일정만 수정할 수 있습니다."), 403

    body = request.get_json(silent=True) or {}
    data, error = _validate_body(body)
    if error:
        return jsonify(error=error), 400

    old_date = existing["date"]
    schedule = db.update_schedule(
        schedule_id, data["category"], data["title"], data["date"],
        data["end_date"], data["start_time"], data["end_time"],
    )
    _notify_schedule_room(nickname, schedule, "수정")
    socketio.emit("schedule_updated", {"date": old_date})
    if schedule["date"] != old_date:
        socketio.emit("schedule_updated", {"date": schedule["date"]})
    return jsonify(schedule=schedule)


@schedules_bp.route("/<int:schedule_id>", methods=["DELETE"])
def delete_schedule(schedule_id):
    nickname = _require_login()
    existing = db.get_schedule(schedule_id)
    if not existing:
        abort(404)
    if existing["nickname"] != nickname:
        return jsonify(error="본인 일정만 삭제할 수 있습니다."), 403

    db.delete_schedule(schedule_id)
    socketio.emit("schedule_updated", {"date": existing["date"]})
    return jsonify(ok=True)
