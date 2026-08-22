@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title 招聘自动化工作台 - 首次安装

where py >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python Launcher。请安装 Python 3.10 或更高版本。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建隔离运行环境...
    py -3.10 -m venv .venv 2>nul
    if errorlevel 1 py -m venv .venv
)

set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

 echo [2/3] 安装固定范围依赖...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PIP%" install -r requirements.txt
if errorlevel 1 goto :fail

 echo [3/3] 安装后备 Chromium 浏览器...
"%PY%" -m playwright install chromium
if errorlevel 1 (
    echo [提示] Chromium 安装失败，但系统已安装 Chrome/Edge 时仍可运行。
)

"%PY%" -m workbench.healthcheck
if errorlevel 1 (
    echo [提示] 健康检查发现问题，请查看上方结果。
)

echo.
echo 安装完成。之后双击 run.bat 启动。
pause
exit /b 0

:fail
echo.
echo [失败] 安装未完成，请检查网络与 Python 环境。
pause
exit /b 1
