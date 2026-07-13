# Team Chat 데스크톱 (트레이 상주형)

내부망 HTTP 서버(`http://내부IP:포트`)를 감싸는 창. 창을 닫아도 트레이에
상주하며 socket.io 연결을 유지하고, 그 상태에서 멘션이 오면 웹앱의 기존
Notification 코드가 OS 팝업을 그대로 띄운다. 자동 시작, 프로세스 완전 종료
후 알림은 다루지 않는다.

`main.py`(pywebview + pystray + PyInstaller)가 현재 버전이다. node/npm이
막힌 사내망에서도 Python 툴체인만으로 빌드할 수 있도록 기존 `main.js`
(Electron + electron-builder) 버전을 대체했다. `main.js`/`package.json`은
node를 쓸 수 있는 환경이 생겼을 때를 대비해 참고용으로 남겨뒀다 — 실제로
쓰는 건 `main.py` 쪽이다.

## 준비

`desktop_config.json`에서 실제 서버 주소로 바꾼다. 파일이 없으면 첫 실행 시
아래 기본값으로 자동 생성된다.

```json
{ "server_url": "http://192.168.0.10:5000" }
```

## 개발 실행 (Windows)

```
cd desktop
pip install -r requirements.txt
python main.py
```

## exe 빌드 (Windows)

```
cd desktop
build.bat
```

`dist/` 아래에 `TeamChat.exe` 하나가 나온다(설치 없이 실행 가능). 내부적으로
`pip install -r requirements.txt` 후 `pyinstaller --onefile --windowed`로
빌드한다. 빌드는 반드시 Windows에서 해야 한다 — PyInstaller도 electron-builder와
마찬가지로 크로스 컴파일을 지원하지 않는다.

## Electron 버전과 달라진 점

- **렌더링 엔진**: Electron의 번들 Chromium 대신 Windows에 이미 설치돼 있는
  WebView2(Edge 기반)를 pywebview가 사용한다. Win10 1809+/Win11엔 보통
  기본 탑재돼 있지만, 오래되거나 락다운된 사내 PC엔 없을 수 있으니 실제
  배포 전에 확인이 필요하다.
- **자체서명 인증서**: 서버가 `certs/cert.pem`으로 이미 https를 켜주므로
  insecure-origin 허용 자체는 필요 없다. 대신 자체서명 인증서를 WebView2가
  거부하지 않도록 `webview.settings["IGNORE_SSL_ERRORS"] = True`로 처리한다
  (환경변수로 브라우저 인자를 넘기는 방식은 설치된 pywebview 버전이
  `CoreWebView2CreationProperties.AdditionalBrowserArguments`를 코드에서
  고정값으로 덮어써버려서 동작하지 않는다 — 시도했다가 죽은 코드였음을
  확인하고 제거했다).
- **알림 권한 자동 승인**: pywebview의 Windows(edgechromium) 백엔드는 알림
  권한 요청(`PermissionRequested`)을 아예 처리하지 않는다(Qt 백엔드만 자동
  승인 코드가 있음). 트레이 상주 앱 특성상 사용자가 권한 팝업을 보고 클릭할
  기회가 없을 수 있어서, `grant_webview2_notification_permission()`이
  WebView2 네이티브 이벤트를 직접 훅해 알림 권한만 자동 승인한다. pywebview
  내부 구현에 기대는 best-effort 처리라 버전이 바뀌면 깨질 수 있고, 실패해도
  앱은 정상 동작한다(그냥 자동 승인만 안 됨).
- **서버 접속 실패 감지**: Electron은 Chromium의 `did-fail-load` 이벤트로
  사후 감지했지만, `main.py`는 창을 띄우기 전에 Python으로 먼저
  `server_url`에 접속을 시도해보고, 실패하면 바로 에러 페이지를 띄운다.
- **portable 임시폴더 버그가 없음**: electron-builder portable 빌드는 실행할
  때마다 exe를 `%TEMP%`에 풀어서 `PORTABLE_EXECUTABLE_DIR` 환경변수로
  우회해야 했다. PyInstaller onefile은 `sys.executable`이 항상 실제 exe
  경로를 가리키므로 이 문제 자체가 없다.
- **툴체인**: node/npm이 전혀 필요 없다. `pip install -r requirements.txt`
  하나로 pywebview/pystray/Pillow/PyInstaller가 모두 설치된다.

## 확인해야 할 것 (Windows에서 직접 테스트 필요)

이 프로젝트는 Linux 샌드박스에서 작성되어 아래 항목은 실제 Windows PC에서
검증되지 않았다:

- WebView2 런타임이 배포 대상 PC에 이미 설치돼 있는지 (Win10 1809+/Win11엔
  보통 기본 탑재).
- `grant_webview2_notification_permission()`이 실제로 `Notification.permission`을
  `"granted"`로 만들어주는지. 확인 방법: `python main.py`로 띄운 뒤
  `webview.start(debug=True)`로 잠깐 바꿔 개발자 도구를 열고 콘솔에서
  `Notification.permission` 값을 직접 찍어본다. `"granted"`가 아니면 이
  훅이 실패한 것이니 `teamchat-error.log`에서
  "WebView2 알림 권한 자동 승인 훅 실패" 로그를 확인한다.
- 트레이 아이콘/메뉴("열기"/"종료") 동작, X 버튼으로 닫아도 트레이에 남는지.
- 알림 클릭 시 `window.focus()`가 트레이로 숨겨진 창을 실제로 복원하는지.

## 창은 뜨는데 흰 화면만 보일 때 / 알림이 안 올 때

서버(`app.py`)는 `certs/cert.pem`이 있으면 **자동으로 https로 전환**된다
(알림 API가 secure context를 요구하기 때문). 이때 아래가 원인인 경우가
대부분이다.

1. `desktop_config.json`의 `server_url`이 실제 서버 프로토콜과 다름
   (서버는 `https://내부IP:5000`인데 설정은 `http://...`로 되어 있는 경우 등).
   브라우저로 먼저 `http://서버IP:5000`과 `https://서버IP:5000`을 각각
   열어봐서 어느 쪽이 실제로 뜨는지 확인하고 `desktop_config.json`을 그에 맞춘다.
   `http://`로 남아있으면 애초에 secure context가 아니라서 알림 권한 자체가
   막힌다.
2. 서버가 자체서명 인증서를 쓰는 https인데 WebView2가 이를 신뢰하지 않는
   경우 → `webview.settings["IGNORE_SSL_ERRORS"] = True`로 이미 처리해뒀다.
3. 알림만 안 오고 화면은 정상이라면, WebView2가 알림 권한 요청을 승인해줄
   방법이 없어서(기본 동작에 맡겨짐) `Notification.permission`이
   `"default"`/`"denied"`로 남아있는 경우다 →
   `grant_webview2_notification_permission()`이 이를 자동 승인하도록
   추가했다. 그래도 안 되면 위 "확인해야 할 것" 항목대로 devtools에서
   직접 `Notification.permission` 값을 확인해본다.

로딩 실패 시 흰 화면 대신 오류 내용(URL, 에러 상세)을 창에 그대로 띄우고,
`TeamChat.exe`와 같은 폴더에 `teamchat-error.log`로도 남긴다.
