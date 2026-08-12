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
    if nickname == config.MENTION_ALL:
        return render_template(
            "login.html", error=f"'{config.MENTION_ALL}'은(는) 예약어라 닉네임으로 사용할 수 없습니다."
        )

    if not auth.try_register_nickname(nickname):
        return render_template("login.html", error="이미 사용 중인 닉네임입니다.")

    db.upsert_user_login(nickname)

    session.clear()
    session["nickname"] = nickname
    session.permanent = True

    from sockets import broadcast_active_users

    broadcast_active_users()
    return redirect(url_for("pages.rooms_page"))


@pages_bp.route("/logout", methods=["POST"])
def logout():
    nickname = session.get("nickname")
    if nickname:
        auth.release_nickname(nickname)

        from sockets import broadcast_active_users

        broadcast_active_users()
    session.clear()
    return redirect(url_for("pages.login_page"))


@pages_bp.route("/rooms")
@auth.login_required
def rooms_page():
    nickname = session["nickname"]
    group_rooms = db.list_group_rooms_for(nickname)
    direct_rooms = db.list_direct_rooms_for(nickname)
    active_users = [u for u in auth.list_active() if u != nickname]
    # 방 생성 시 초대 후보는 접속 여부와 무관하게 DB에 로그인 이력이 있는 전체 사용자로 노출하고,
    # 온라인 상태는 화면에서 구분 표시만 한다.
    all_users = sorted(
        ({"nickname": u, "online": auth.is_active(u)} for u in db.list_all_users() if u != nickname),
        key=lambda u: (not u["online"], u["nickname"]),
    )
    # 1:1 방은 멘션 여부와 무관하게 안 읽은 메시지 수로 배지를 표시하므로,
    # 멘션 카운트 위에 direct 방 카운트를 덮어씌운다(그룹/전체 방은 멘션 카운트 그대로).
    mention_counts = {
        **db.get_unread_mention_counts(nickname),
        **db.get_unread_direct_message_counts(nickname),
    }
    return render_template(
        "rooms.html",
        nickname=nickname,
        is_superadmin=auth.is_superadmin(nickname),
        group_rooms=group_rooms,
        direct_rooms=direct_rooms,
        active_users=active_users,
        all_users=all_users,
        mention_counts=mention_counts,
    )


@pages_bp.route("/schedule")
@auth.login_required
def schedule_page():
    return render_template("schedule.html", nickname=session["nickname"])


@pages_bp.route("/excel")
@auth.login_required
def excel_page():
    return render_template("excel.html", nickname=session["nickname"])


@pages_bp.route("/defect")
@auth.login_required
def defect_page():
    nickname = session["nickname"]
    return render_template(
        "defect.html",
        nickname=nickname,
        is_superadmin=auth.is_superadmin(nickname),
        subjects=db.list_subjects(),
        issue_fields=db.list_issue_fields(),
    )


@pages_bp.route("/chat/<int:room_id>")
@auth.login_required
def chat_page(room_id):
    nickname = session["nickname"]
    room = db.get_room(room_id)
    if not room:
        abort(404)
    if not db.can_access_room(room, nickname):
        abort(403)

    db.ensure_room_participant(room_id, nickname)
    messages = db.list_messages_with_unread(room_id)
    is_owner = room.get("owner_nickname") == nickname
    is_superadmin = auth.is_superadmin(nickname)
    can_manage = is_owner or is_superadmin
    room_members = [n for n in db.get_room_member_nicknames(room_id, room["type"]) if n != nickname]

    # 참여 인원 모달에 표시할 목록: 나(항상 온라인) + 다른 참여자(온라인 우선 정렬), 각자 접속 상태 포함
    other_participants = sorted(
        ({"nickname": n, "online": auth.is_active(n)} for n in room_members),
        key=lambda p: (not p["online"], p["nickname"]),
    )
    participants = [{"nickname": nickname, "online": True, "is_self": True}] + [
        {**p, "is_self": False} for p in other_participants
    ]

    # 비공개 방 초대 후보: 접속 여부와 무관하게 DB에 등록된 전체 사용자 중 아직 멤버가 아닌 사용자
    # (공개 방은 누구나 접근 가능해 멤버 초대/제거 개념이 없으므로 비공개 방에서만 필요하다)
    invitable_users = []
    if room["is_private"]:
        invitable_users = sorted(
            (
                {"nickname": u, "online": auth.is_active(u)}
                for u in db.list_all_users()
                if u != nickname and u not in room_members
            ),
            key=lambda u: (not u["online"], u["nickname"]),
        )

    message_ids = [m["id"] for m in messages if m["type"] != "system"]
    reaction_counts = db.get_message_reaction_counts(message_ids)
    reaction_users = db.get_message_reactions_grouped(message_ids)
    my_reactions = db.get_message_reactions_by_user(message_ids, nickname)

    today_schedules = db.list_schedules_for_date(db.today_kst().isoformat())
    schedule_banner = format_banner(today_schedules)

    return render_template(
        "chat.html",
        room=room,
        messages=messages,
        nickname=nickname,
        is_owner=is_owner,
        is_superadmin=is_superadmin,
        can_manage=can_manage,
        room_deletable=bool(room["is_deletable"]),
        participants=participants,
        room_members=room_members,
        invitable_users=invitable_users,
        schedule_banner=schedule_banner,
        reaction_counts=reaction_counts,
        reaction_users=reaction_users,
        my_reactions=my_reactions,
    )
