@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title 构建招聘自动化工作台 V0.9

set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

%PY% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [准备] 安装构建依赖...
    %PY% -m pip install -r requirements-dev.txt
    if errorlevel 1 goto :failed
)

%PY% -m compileall -q workbench workbench_app.py app.py code tests tests_qt
if errorlevel 1 goto :failed
%PY% -m unittest discover -s tests -v
if errorlevel 1 goto :failed

rem 将受控 Chromium 放入发布目录，客户不需要预装 Google Chrome。
set PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime-browsers
if not exist "%PLAYWRIGHT_BROWSERS_PATH%" mkdir "%PLAYWRIGHT_BROWSERS_PATH%"
echo [浏览器] 准备工作台 Chromium...
%PY% -m playwright install chromium
if errorlevel 1 goto :failed

echo [打包] 生成可独立分发的 onedir 目录...
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name "招聘自动化工作台" ^
    --paths . ^
    --paths code ^
    --collect-all playwright ^
    --collect-all PySide6 ^
    --add-data "runtime-browsers;runtime-browsers" ^
    --hidden-import searcher ^
    --hidden-import bot ^
    --hidden-import workbench.qt_ui ^
    --hidden-import workbench.qt_workspace ^
    --hidden-import workbench.qt_job_dialog ^
    --hidden-import workbench.browser_worker ^
    app.py
if errorlevel 1 goto :failed

if exist "dist\招聘自动化工作台-v0.9.zip" del /q "dist\招聘自动化工作台-v0.9.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\招聘自动化工作台\*' -DestinationPath 'dist\招聘自动化工作台-v0.9.zip' -Force"

echo.
echo 构建完成：
echo   dist\招聘自动化工作台\招聘自动化工作台.exe
echo   dist\招聘自动化工作台-v0.9.zip
exit /b 0

:failed
echo.
echo [失败] 构建未完成。请查看上方错误。
pause
exit /b 1
