from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

import auth
import config
import db
from routes.schedules import format_banner

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    if session.get("nickname"):
        return redirect(url_for("pages.rooms_page"))
    return redirect(url_for("pages.login_page"))


@pages_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("login.html", error=None)

    nickname = (request.form.get("nickname") or "").strip()
    if not nickname:
        return render_template("login.html", error="닉네임을 입력해주세요.")
    if len(nickname) > config.NICKNAME_MAX_LENGTH:
        return render_template(
            "login.html", error=f"닉네임은 {config.NICKNAME_MAX_LENGTH}자 이하로 입력해주세요."
        )
    if "@" in nickname:
        return render_template("login.html", error="닉네임에 '@' 문자는 사용할 수 없습니다.")

    if not auth.try_register_nickname(nickname):
        return render_template("login.html", error="이미 사용 중인 닉네임입니다.")

    session.clear()
    session["nickname"] = nickname
    session.permanent = True
    return redirect(url_for("pages.rooms_page"))


@pages_bp.route("/logout", methods=["POST"])
def logout():
    nickname = session.get("nickname")
    if nickname:
        auth.release_nickname(nickname)
    session.clear()
    return redirect(url_for("pages.login_page"))


@pages_bp.route("/rooms")
@auth.login_required
def rooms_page():
    nickname = session["nickname"]
    group_rooms = db.list_group_rooms()
    direct_rooms = db.list_direct_rooms_for(nickname)
    active_users = [u for u in auth.list_active() if u != nickname]
    return render_template(
        "rooms.html",
        nickname=nickname,
        is_superadmin=auth.is_superadmin(nickname),
        group_rooms=group_rooms,
        direct_rooms=direct_rooms,
        active_users=active_users,
    )


@pages_bp.route("/chat/<int:room_id>")
@auth.login_required
def chat_page(room_id):
    nickname = session["nickname"]
    room = db.get_room(room_id)
    if not room:
        abort(404)
    if room["type"] == "direct" and not db.is_direct_participant(room_id, nickname):
        abort(403)

    db.ensure_room_participant(room_id, nickname)
    messages = db.list_messages_with_unread(room_id)
    is_owner = room.get("owner_nickname") == nickname
    is_superadmin = auth.is_superadmin(nickname)
    active_users = [u for u in auth.list_active() if u != nickname]

    today_schedules = db.list_schedules_for_date(date.today().isoformat())
    schedule_banner = format_banner(today_schedules)

    return render_template(
        "chat.html",
        room=room,
        messages=messages,
        nickname=nickname,
        is_owner=is_owner,
        is_superadmin=is_superadmin,
        can_manage=is_owner or is_superadmin,
        room_deletable=bool(room["is_deletable"]),
        active_users=active_users,
        schedule_banner=schedule_banner,
    )
