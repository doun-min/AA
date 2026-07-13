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
from urllib.parse import urlsplit

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


def main():
    import webview

    config = load_config()
    server_url = config["server_url"]
    origin = urlsplit(server_url)
    origin_str = f"{origin.scheme}://{origin.netloc}"

    # WebView2(Windows의 Chromium 컴포넌트)에 Electron의
    # unsafely-treat-insecure-origin-as-secure / 인증서 무시 옵션과 동등한 플래그를 넘긴다.
    # 반드시 webview 창을 만들기(=WebView2 환경 생성) 전에 설정해야 반영된다.
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        f"--ignore-certificate-errors "
        f"--unsafely-treat-insecure-origin-as-secure={origin_str}"
    )

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

    webview.start()


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
