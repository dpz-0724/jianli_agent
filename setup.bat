@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title 招聘自动化工作台 - 开发版首次安装

where py >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python Launcher。
    echo 源码运行需要 Python 3.10 或更高版本；正式发布包不需要客户安装 Python。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 创建隔离运行环境...
    py -3.10 -m venv .venv 2>nul
    if errorlevel 1 py -m venv .venv
    if errorlevel 1 goto :fail
)

set PY=.venv\Scripts\python.exe

echo [2/4] 安装固定版本依赖...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [3/4] 安装工作台自带 Chromium...
"%PY%" -m playwright install chromium
if errorlevel 1 (
    echo [提示] Chromium 下载失败。可稍后重试，或在系统设置中选择 Microsoft Edge / Google Chrome。
)

echo [4/4] 执行环境健康检查...
"%PY%" -m compileall -q workbench workbench_app.py app.py code
if errorlevel 1 goto :fail
"%PY%" -m workbench.healthcheck


echo.
echo 安装完成。之后双击 run.bat 启动现代化工作台。
pause
exit /b 0

:fail
echo.
echo [失败] 安装未完成，请检查网络、Python 版本和上方错误。
pause
exit /b 1
