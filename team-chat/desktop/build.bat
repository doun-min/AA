@echo off
setlocal

cd /d "%~dp0"

python -m pip install -r requirements.txt
if errorlevel 1 goto :error

python -c "from PIL import Image; im = Image.open('assets/icon.png'); im.save('assets/icon.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])"
if errorlevel 1 goto :error

python -m PyInstaller --onefile --windowed --name TeamChat --icon assets\icon.ico --add-data "assets;assets" main.py
if errorlevel 1 goto :error

echo.
echo 빌드 완료: dist\TeamChat.exe
goto :eof

:error
echo 빌드 실패
exit /b 1
