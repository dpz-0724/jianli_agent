@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title 招聘自动化工作台 V0.9

set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到可用的 Python。源码运行请先执行 setup.bat。
    pause
    exit /b 1
)

%PY% -c "import PySide6, playwright" >nul 2>nul
if errorlevel 1 (
    echo [首次运行] 正在安装桌面与浏览器依赖...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

echo 正在启动招聘自动化工作台...
%PY% app.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo [失败] 启动未完成。
echo 日志：%%LOCALAPPDATA%%\RecruitmentWorkbench\logs\workbench.log
pause
exit /b 1
