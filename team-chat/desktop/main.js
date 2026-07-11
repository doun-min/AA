// Team Chat 트레이 상주형 데스크톱 런처.
// 창을 닫아도 프로세스(및 렌더러의 socket.io 연결)는 트레이에 남아있고,
// 그 상태에서 멘션이 오면 웹앱의 기존 Notification 코드가 그대로 OS 팝업을 띄운다.
const { app, BrowserWindow, Tray, Menu, nativeImage } = require("electron");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");

const APP_NAME = "Team Chat";

function appDir() {
  return app.isPackaged ? path.dirname(process.execPath) : __dirname;
}

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
    console.error("desktop_config.json 파싱 실패, 기본값 사용:", err);
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

  // X 버튼을 눌러도 완전 종료하지 않고 트레이로 내린다 (프로세스/소켓 연결 유지).
  mainWindow.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    mainWindow.hide();
  });
}

function createTray() {
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
