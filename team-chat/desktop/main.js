// Team Chat 트레이 상주형 데스크톱 런처.
// 창을 닫아도 프로세스(및 렌더러의 socket.io 연결)는 트레이에 남아있고,
// 그 상태에서 멘션이 오면 웹앱의 기존 Notification 코드가 그대로 OS 팝업을 띄운다.
const { app, BrowserWindow, Tray, Menu, nativeImage, dialog } = require("electron");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");

const APP_NAME = "Team Chat";

// electron-builder의 portable 타겟은 exe를 실행할 때마다 %TEMP%에 압축을 풀고
// 그 임시 경로를 process.execPath로 준다. 그래서 실제 exe 파일이 놓인 폴더는
// process.execPath가 아니라 PORTABLE_EXECUTABLE_DIR 환경변수로만 알 수 있다.
// (이걸 안 쓰면 desktop_config.json을 %TEMP% 쪽에서 찾아서 매번 기본값으로 덮어씀)
function appDir() {
  if (process.env.PORTABLE_EXECUTABLE_DIR) return process.env.PORTABLE_EXECUTABLE_DIR;
  return app.isPackaged ? path.dirname(process.execPath) : __dirname;
}

function logPath() {
  return path.join(appDir(), "teamchat-error.log");
}

function logError(label, err) {
  const line = `[${new Date().toISOString()}] ${label}: ${err && err.stack ? err.stack : err}\n`;
  console.error(line);
  try {
    fs.appendFileSync(logPath(), line, "utf-8");
  } catch (_) {
    // 로그조차 못 쓰는 상황이면 콘솔 출력만으로 만족한다.
  }
}

process.on("uncaughtException", (err) => {
  logError("uncaughtException", err);
  dialog.showErrorBox(APP_NAME, `예상치 못한 오류로 종료됩니다.\n\n${err.message}\n\n로그: ${logPath()}`);
  app.exit(1);
});

function loadConfig() {
  const configPath = path.join(appDir(), "desktop_config.json");
  const fallback = { server_url: "http://192.168.0.10:5000" };
  if (!fs.existsSync(configPath)) {
    fs.writeFileSync(configPath, JSON.stringify(fallback, null, 2), "utf-8");
    return fallback;
  }
  try {
    const raw = JSON.parse(fs.readFileSync(configPath, "utf-8"));
    return { ...fallback, ...raw };
  } catch (err) {
    logError("desktop_config.json 파싱 실패, 기본값 사용", err);
    return fallback;
  }
}

const config = loadConfig();
const serverUrl = config.server_url;
const origin = new URL(serverUrl).origin;

// HTTP origin을 secure context로 취급하게 해서, 내부망 HTTP 서버에서도
// Notification API(OS 팝업)가 정상 동작하게 한다. app.whenReady() 이전에 호출해야 한다.
app.commandLine.appendSwitch("unsafely-treat-insecure-origin-as-secure", origin);

let mainWindow = null;
let tray = null;
let isQuitting = false;

// 사내망 서버가 자체서명 인증서(https)를 쓰는 경우, Electron은 기본적으로
// 이를 신뢰하지 않고 로딩을 조용히 실패시킨다(에러 페이지 없이 흰 화면만 남는 원인).
// desktop_config.json에 설정된 서버 origin에 한해서만 신뢰하도록 예외를 둔다.
app.on("certificate-error", (event, webContents, url, error, certificate, callback) => {
  if (new URL(url).origin === origin) {
    logError("certificate-error (허용됨: 내부망 자체서명 인증서)", `${url} - ${error}`);
    event.preventDefault();
    callback(true);
  } else {
    callback(false);
  }
});

function showLoadError(errorDescription, errorCode, validatedURL) {
  if (!mainWindow) return;
  const detail = `URL: ${validatedURL}\n오류: ${errorDescription} (${errorCode})`;
  logError("did-fail-load", detail);
  const html = `data:text/html;charset=utf-8,${encodeURIComponent(`
    <html><body style="font-family:sans-serif;padding:40px;color:#333">
      <h2>서버에 연결할 수 없습니다</h2>
      <pre style="white-space:pre-wrap">${detail}</pre>
      <p>desktop_config.json의 server_url(${serverUrl})이 실제 서버 주소/프로토콜(http/https)과 맞는지 확인하세요.</p>
    </body></html>
  `)}`;
  mainWindow.loadURL(html);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 800,
    title: APP_NAME,
    icon: path.join(__dirname, "assets", "icon.png"),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(serverUrl);

  // 로딩 실패(서버 꺼짐, 주소/프로토콜 오류, 인증서 거부 등)를 화면에 그대로 노출한다.
  // 처리 안 하면 흰 화면만 남고 원인을 알 방법이 없다.
  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    // errorCode -3 (ERR_ABORTED)은 리다이렉트 등으로 흔히 발생하는 정상 케이스라 무시한다.
    if (!isMainFrame || errorCode === -3) return;
    showLoadError(errorDescription, errorCode, validatedURL);
  });

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    logError("render-process-gone", JSON.stringify(details));
  });

  // X 버튼을 눌러도 완전 종료하지 않고 트레이로 내린다 (프로세스/소켓 연결 유지).
  mainWindow.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    mainWindow.hide();
  });
}

function createTray() {
  try {
    const trayIcon = nativeImage.createFromPath(path.join(__dirname, "assets", "tray.png"));
    tray = new Tray(trayIcon);
    tray.setToolTip(APP_NAME);
    tray.setContextMenu(
      Menu.buildFromTemplate([
        {
          label: "열기",
          click: () => {
            mainWindow.show();
            mainWindow.focus();
          },
        },
        { type: "separator" },
        {
          label: "종료",
          click: () => {
            isQuitting = true;
            app.quit();
          },
        },
      ])
    );
    tray.on("double-click", () => {
      mainWindow.show();
      mainWindow.focus();
    });
  } catch (err) {
    // 트레이 생성 실패는 치명적이지 않아야 한다 — 메인 창은 이미 떠 있어야 하므로
    // 여기서 죽이지 않고 로그만 남긴다.
    logError("createTray 실패 (트레이 없이 계속 진행)", err);
  }
}

app.whenReady().then(() => {
  createWindow();
  createTray();
});

app.on("before-quit", () => {
  isQuitting = true;
});

// 트레이 상주가 목적이므로, 모든 창이 닫혀도(=숨겨져도) 앱을 종료하지 않는다.
app.on("window-all-closed", (event) => {
  event.preventDefault();
});
