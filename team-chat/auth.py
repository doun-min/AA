import threading
from functools import wraps

from flask import redirect, session, url_for

import config

_lock = threading.Lock()
_active_nicknames = set()


def try_register_nickname(nickname):
    """현재 아무도 쓰고 있지 않은 닉네임이면 예약하고 True, 아니면 False."""
    with _lock:
        if nickname in _active_nicknames:
            return False
        _active_nicknames.add(nickname)
        return True


def release_nickname(nickname):
    with _lock:
        _active_nicknames.discard(nickname)


def mark_active(nickname):
    """이미 로그인(세션 보유)된 사용자의 소켓이 (재)연결됐을 때 무조건 active로 표시한다.
    트레이 최소화/절전/네트워크 순단 등으로 소켓이 끊겨 release된 뒤 자동 재연결되는
    경우, 재로그인 없이도 다시 active 상태로 복구하기 위함이다.
    반환값: 이전에 active가 아니었다가 이번에 새로 표시됐으면 True."""
    with _lock:
        was_new = nickname not in _active_nicknames
        _active_nicknames.add(nickname)
        return was_new


def is_active(nickname):
    with _lock:
        return nickname in _active_nicknames


def list_active():
    with _lock:
        return sorted(_active_nicknames)


def is_superadmin(nickname):
    return nickname in config.SUPERADMIN_NAMES


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("nickname"):
            return redirect(url_for("pages.login_page"))
        return view(*args, **kwargs)

    return wrapped
