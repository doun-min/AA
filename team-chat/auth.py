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
