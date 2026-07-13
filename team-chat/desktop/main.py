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


def patch_webview2_insecure_origin(origin_str):
    """cert 없이 http로 운영할 때, http origin을 secure context로 취급하게 해서
    Notification API가 켜지도록 한다(Electron의
    app.commandLine.appendSwitch('unsafely-treat-insecure-origin-as-secure', ...)와
    동등한 처리).

    pywebview에는 이걸 위한 공개 API가 없다 — edgechromium.EdgeChrome.__init__이
    CoreWebView2CreationProperties.AdditionalBrowserArguments를 코드에서 항상
    채워버리기 때문에(WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS 환경변수는 이 값이
    비어있을 때만 적용됨), 그 인자 문자열에 우리 플래그를 끼워 넣을 방법이 API
    레벨엔 없다. 그래서 EdgeChrome.__init__ 자체를 이 함수 작성 시점의
    pywebview(edgechromium.py, 6.2.1) 구현 그대로 복사해서 마지막에 플래그 한 줄만
    추가한 버전으로 통째로 교체한다.

    이런 이유로 pywebview 내부 구현에 강하게 의존하는 fragile한 패치다.
    pywebview를 업그레이드하면(6.x 안에서도) 조용히 안 먹힐 수 있으니, 업그레이드
    후에는 반드시 실제 창에서 Notification.permission이 "granted"가 되는지
    확인해야 한다. 패치가 실패해도 앱 자체는 정상 동작한다(그냥 http에서
    알림이 안 될 뿐).
    """
    try:
        import webview.platforms.edgechromium as edge

        def patched_init(self, form, window, cache_dir):
            self.pywebview_window = window
            self.webview = edge.WebView2()
            props = edge.CoreWebView2CreationProperties()

            runtime_path = edge.webview_settings["WEBVIEW2_RUNTIME_PATH"]
            if runtime_path:
                if not edge.os.path.isabs(runtime_path):
                    runtime_path = edge.os.path.join(edge.get_app_root(), runtime_path)
                if edge.os.path.exists(runtime_path):
                    props.BrowserExecutableFolder = runtime_path
                    edge.logger.debug(f"Using custom WebView2 runtime: {runtime_path}")
                else:
                    edge.logger.warning(
                        f"Custom WebView2 runtime path does not exist: {runtime_path}. Using system WebView2."
                    )

            props.UserDataFolder = cache_dir
            self.user_data_folder = props.UserDataFolder
            props.set_IsInPrivateModeEnabled(edge._state["private_mode"])
            props.AdditionalBrowserArguments = "--disable-features=ElasticOverscroll"

            if edge.webview_settings["ALLOW_FILE_URLS"]:
                props.AdditionalBrowserArguments += " --allow-file-access-from-files"

            if edge.webview_settings["REMOTE_DEBUGGING_PORT"] is not None:
                props.AdditionalBrowserArguments += (
                    f" --remote-debugging-port={edge.webview_settings['REMOTE_DEBUGGING_PORT']}"
                )

            # team-chat 추가분: http 서버를 secure context로 취급해서 Notification API를 켠다.
            props.AdditionalBrowserArguments += (
                f" --unsafely-treat-insecure-origin-as-secure={origin_str}"
            )

            self.webview.CreationProperties = props

            self.form = form
            form.Controls.Add(self.webview)

            self.js_results = {}
            self.js_result_semaphore = edge.Semaphore(0)
            self.webview.Dock = edge.WinForms.DockStyle.Fill
            self.webview.BringToFront()
            self.webview.CoreWebView2InitializationCompleted += self.on_webview_ready
            self.webview.NavigationStarting += self.on_navigation_start
            self.webview.NavigationCompleted += self.on_navigation_completed
            self.webview.WebMessageReceived += self.on_script_notify
            self.syncContextTaskScheduler = edge.TaskScheduler.FromCurrentSynchronizationContext()
            self.webview.DefaultBackgroundColor = edge.Color.FromArgb(
                255,
                int(window.background_color.lstrip("#")[0:2], 16),
                int(window.background_color.lstrip("#")[2:4], 16),
                int(window.background_color.lstrip("#")[4:6], 16),
            )

            if window.transparent:
                self.webview.DefaultBackgroundColor = edge.Color.Transparent

            self.url = None
            self.ishtml = False
            self.html = edge.DEFAULT_HTML

            self.webview.EnsureCoreWebView2Async(None)

        edge.EdgeChrome.__init__ = patched_init
    except Exception as e:
        log_error("WebView2 insecure-origin 패치 실패 (http에서는 알림이 안 될 수 있음)", e)


def main():
    import webview

    config = load_config()
    server_url = config["server_url"]
    origin = urlsplit(server_url)

    # 서버(app.py)가 certs/cert.pem으로 https를 켜준 경우엔 그 자체로 secure
    # context라 아래 patch가 필요 없다. 자체서명 인증서를 WebView2가 거부하지
    # 않도록만 해주면 된다.
    webview.settings["IGNORE_SSL_ERRORS"] = True

    # cert 없이 http로 운영하는 경우, Notification API를 켜려면 이 origin을
    # secure context로 취급하도록 WebView2에 직접 패치를 걸어야 한다(위
    # patch_webview2_insecure_origin 참고). 반드시 webview.start() 전에,
    # 즉 실제 창(EdgeChrome)이 만들어지기 전에 걸어야 한다.
    if origin.scheme == "http" and sys.platform == "win32":
        patch_webview2_insecure_origin(f"{origin.scheme}://{origin.netloc}")

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
