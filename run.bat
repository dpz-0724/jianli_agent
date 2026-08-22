@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title 招聘自动化工作台 V1

set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到可用的 Python。请先运行 setup.bat。
    pause
    exit /b 1
)

%PY% -c "import playwright" >nul 2>nul
if errorlevel 1 (
    echo [首次运行] 正在安装浏览器自动化依赖...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

echo 正在启动招聘自动化工作台...
%PY% app.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo [失败] 启动未完成。请查看 %%LOCALAPPDATA%%\RecruitmentWorkbench\logs\workbench.log
pause
exit /b 1
