# Team Chat 데스크톱 (트레이 상주형)

내부망 HTTP 서버(`http://내부IP:포트`)를 감싸는 Electron 창. 창을 닫아도 트레이에
상주하며 socket.io 연결을 유지하고, 그 상태에서 멘션이 오면 웹앱의 기존
Notification 코드가 OS 팝업을 그대로 띄운다. 자동 시작, 프로세스 완전 종료
후 알림은 다루지 않는다.

## 준비

`desktop_config.json`에서 실제 서버 주소로 바꾼다.

```json
{ "server_url": "http://192.168.0.10:5000" }
```

## 개발 실행 (Windows)

```
cd desktop
npm install
npm start
```

## exe 빌드 (Windows)

```
cd desktop
npm install
npm run build:win
```

`dist/` 아래에 포터블 `TeamChat.exe` 하나가 나온다(설치 없이 실행 가능).
빌드는 반드시 Windows에서 해야 한다 — Linux/맥에서 `electron-builder --win`을
돌리면 서명/네이티브 모듈 이슈가 날 수 있다.

## 확인해야 할 것 (Windows에서 직접 테스트 필요)

이 프로젝트는 Linux 샌드박스에서 작성되어 아래 항목은 실제 Windows PC에서
검증되지 않았다:

- `app.commandLine.appendSwitch('unsafely-treat-insecure-origin-as-secure', ...)`가
  HTTP 서버에서 `Notification.requestPermission()`을 실제로 풀어주는지
- 트레이 아이콘/메뉴("열기"/"종료") 동작, X 버튼으로 닫아도 트레이에 남는지
- 알림 클릭 시 `window.focus()`가 트레이로 숨겨진 창을 실제로 복원하는지 —
  숨겨진 상태에서는 안 될 수 있음. 필요하면 알림 클릭을 메인 프로세스로 넘겨
  `mainWindow.show()`를 직접 호출하도록 보완해야 한다 (다음 단계).
