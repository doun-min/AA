# Team Chat 트레이 상주형 데스크톱 런처 (PyInstaller / pywebview 버전).
# main.js와 동일한 목적: 창을 닫아도 프로세스(및 webview의 socket.io 연결)는
# 트레이에 남아있고, 그 상태에서 멘션이 오면 웹앱의 기존 Notification 코드가
# 그대로 OS 팝업을 띄운다.
import json
import os
import ssl
import sys
import threading
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

APP_NAME = "Team Chat"
KST = timezone(timedelta(hours=9))


def app_dir():
    # PyInstaller onefile은 실행 시 임시 폴더(_MEIPASS)에 압축을 풀지만,
    # sys.executable은 (electron portable과 달리) 항상 실제 exe 위치를 가리킨다.
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def asset_path(*parts):
    # PyInstaller onefile로 --add-data 번들된 리소스는 실행 중엔 _MEIPASS 밑에서 찾아야 한다.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def log_path():
    return os.path.join(app_dir(), "teamchat-error.log")


def log_error(label, err):
    line = f"[{datetime.now(KST).isoformat()}] {label}: {err}\n"
    print(line, file=sys.stderr)
    try:
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        # 로그조차 못 쓰는 상황이면 콘솔 출력만으로 만족한다.
        pass


def load_config():
    config_path = os.path.join(app_dir(), "desktop_config.json")
    fallback = {"server_url": "http://192.168.0.10:5000"}
    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(fallback, f, ensure_ascii=False, indent=2)
        return fallback
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {**fallback, **raw}
    except (OSError, json.JSONDecodeError) as e:
        log_error("desktop_config.json 파싱 실패, 기본값 사용", e)
        return fallback


def probe_server(url, timeout=5):
    """서버가 실제로 응답하는지 미리 확인한다(자체서명 인증서는 검증 없이 통과).

    Electron 버전은 Chromium의 did-fail-load 이벤트로 사후 감지했지만, 여기서는
    webview 창을 띄우기 전에 먼저 확인해서 실패 시 에러 페이지를 바로 보여준다.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return True, None
    except (urllib.error.URLError, ssl.SSLError, ValueError) as e:
        return False, str(e)


def error_html(server_url, detail):
    import html as html_mod

    safe_url = html_mod.escape(server_url)
    safe_detail = html_mod.escape(detail)
    return f"""
    <html><body style="font-family:sans-serif;padding:40px;color:#333">
      <h2>서버에 연결할 수 없습니다</h2>
      <pre style="white-space:pre-wrap">{safe_detail}</pre>
      <p>desktop_config.json의 server_url({safe_url})이 실제 서버 주소/프로토콜(http/https)과
      맞는지 확인하세요.</p>
    </body></html>
    """


def grant_webview2_notification_permission(window):
    """WebView2(edgechromium) 백엔드는 pywebview 6.x 기준 PermissionRequested를
    전혀 처리하지 않는다(Qt 백엔드는 자동 승인 코드가 있는데 여기는 없음). 트레이
    상주 앱 특성상 사용자가 권한 팝업을 볼 기회가 없을 수 있으므로, 알림 권한만
    네이티브 레벨에서 직접 승인한다.

    pywebview의 내부 구현(webview.platforms.winforms.BrowserView,
    webview.platforms.edgechromium.EdgeChrome)에 기대는 best-effort 처리라
    pywebview 버전이 바뀌면 깨질 수 있다. 실패해도 앱 동작에는 영향 없다
    (그냥 알림 자동 승인이 안 되고 기본 동작으로 남을 뿐).
    """
    try:
        from Microsoft.Web.WebView2.Core import (
            CoreWebView2PermissionKind,
            CoreWebView2PermissionState,
        )
        from webview.platforms.winforms import BrowserView

        def on_permission_requested(sender, args):
            if args.PermissionKind == CoreWebView2PermissionKind.Notifications:
                args.State = CoreWebView2PermissionState.Allow

        def on_core_ready(sender, args):
            if sender.CoreWebView2 is not None:
                sender.CoreWebView2.PermissionRequested += on_permission_requested

        form = BrowserView.instances.get(window.uid)
        core_control = getattr(getattr(form, "browser", None), "webview", None)
        if core_control is None:
            return
        if core_control.CoreWebView2 is not None:
            core_control.CoreWebView2.PermissionRequested += on_permission_requested
        else:
            core_control.CoreWebView2InitializationCompleted += on_core_ready
    except Exception as e:
        log_error("WebView2 알림 권한 자동 승인 훅 실패 (기본 동작으로 진행)", e)


def main():
    import webview

    config = load_config()
    server_url = config["server_url"]

    # 서버(app.py)는 certs/cert.pem이 있으면 자동으로 https로 전환된다(알림 API가
    # secure context를 요구하기 때문). 여기서 별도의 insecure-origin 허용은 필요
    # 없고, 대신 자체서명 인증서를 WebView2가 거부하지 않도록만 해주면 된다.
    webview.settings["IGNORE_SSL_ERRORS"] = True

    ok, err = probe_server(server_url)
    if ok:
        target_url = server_url
    else:
        log_error("서버 접속 확인 실패", err)
        target_url = None

    window = webview.create_window(
        APP_NAME,
        url=target_url,
        html=None if target_url else error_html(server_url, err),
        width=1100,
        height=800,
    )

    is_quitting = threading.Event()

    def on_closing():
        # X 버튼을 눌러도 완전 종료하지 않고 트레이로 내린다 (프로세스/소켓 연결 유지).
        if is_quitting.is_set():
            return None
        window.hide()
        return False

    window.events.closing += on_closing

    def show_window():
        window.show()
        window.restore()

    def quit_app(icon=None, item=None):
        is_quitting.set()
        if icon is not None:
            icon.stop()
        window.destroy()

    tray_thread = threading.Thread(target=run_tray, args=(show_window, quit_app), daemon=True)
    tray_thread.start()

    def on_gui_ready():
        if sys.platform == "win32":
            grant_webview2_notification_permission(window)

    webview.start(func=on_gui_ready)


def run_tray(show_window, quit_app):
    import pystray
    from PIL import Image

    try:
        image = Image.open(asset_path("assets", "tray.png"))
    except OSError as e:
        # 트레이 아이콘 생성 실패는 치명적이지 않아야 한다 — 메인 창은 이미 떠 있어야
        # 하므로 여기서 죽이지 않고 로그만 남긴다.
        log_error("createTray 실패 (트레이 없이 계속 진행)", e)
        return

    menu = pystray.Menu(
        pystray.MenuItem("열기", lambda: show_window(), default=True),
        pystray.MenuItem("종료", lambda: quit_app()),
    )
    icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)

    try:
        icon.run()
    except Exception as e:
        log_error("createTray 실패 (트레이 없이 계속 진행)", e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error("uncaughtException", traceback.format_exc())
        raise
