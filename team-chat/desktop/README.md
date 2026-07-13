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
- **자체서명 인증서 / 알림용 insecure-origin 허용**: `main.js`는 Electron API로
  origin 단위로 세밀하게 처리했지만, `main.py`는 WebView2가 읽는 환경변수
  (`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`)에 `--ignore-certificate-errors`와
  `--unsafely-treat-insecure-origin-as-secure=<origin>`을 실어 보내는 방식으로
  대응한다. Windows에서 실기 검증이 필요하다.
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

- `app.commandLine.appendSwitch('unsafely-treat-insecure-origin-as-secure', ...)`가
  HTTP 서버에서 `Notification.requestPermission()`을 실제로 풀어주는지
- 트레이 아이콘/메뉴("열기"/"종료") 동작, X 버튼으로 닫아도 트레이에 남는지
- 알림 클릭 시 `window.focus()`가 트레이로 숨겨진 창을 실제로 복원하는지 —
  숨겨진 상태에서는 안 될 수 있음. 필요하면 알림 클릭을 메인 프로세스로 넘겨
  `mainWindow.show()`를 직접 호출하도록 보완해야 한다 (다음 단계).

## 창은 뜨는데 흰 화면만 보일 때

서버(`app.py`)는 `certs/cert.pem`이 있으면 **자동으로 https로 전환**된다
(알림 API가 secure context를 요구하기 때문). 이때 아래 두 가지 중 하나가
원인인 경우가 대부분이다.

1. `desktop_config.json`의 `server_url`이 실제 서버 프로토콜과 다름
   (서버는 `https://내부IP:5000`인데 설정은 `http://...`로 되어 있는 경우 등).
   브라우저로 먼저 `http://서버IP:5000`과 `https://서버IP:5000`을 각각
   열어봐서 어느 쪽이 실제로 뜨는지 확인하고 `desktop_config.json`을 그에 맞춘다.
2. 서버가 자체서명 인증서를 쓰는 https라서 Electron이 인증서를 신뢰하지 않고
   조용히 로딩을 실패시킴 → `main.js`의 `certificate-error` 핸들러가 설정된
   `server_url`의 origin에 한해 이를 허용하도록 이미 처리해뒀다.

지금은 로딩 실패 시 흰 화면 대신 오류 내용(URL, 에러 코드)을 창에 그대로
띄우고, `teamchat.exe`와 같은 폴더에 `teamchat-error.log`로도 남기도록
고쳤다. 여전히 흰 화면만 보인다면 그 로그 파일 내용을 확인할 것.

또한 `portable` 빌드는 실행할 때마다 exe를 `%TEMP%`에 풀고 그 경로를
`process.execPath`로 주기 때문에, exe 옆에 둔 `desktop_config.json`을
찾지 못하고 매번 기본값(`http://192.168.0.10:5000`)으로 덮어쓰는 버그가
있었다. `PORTABLE_EXECUTABLE_DIR` 환경변수(electron-builder가 portable
빌드에서 실제 exe 폴더를 알려주기 위해 설정함)를 쓰도록 고쳤다.
