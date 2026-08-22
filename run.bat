@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 云只智联 候选人筛选排序工具

rem 依赖检查
python -c "import playwright" 2>nul
if errorlevel 1 (
    echo [首次运行] 正在安装依赖，请稍候...
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple playwright requests
    python -m playwright install chromium
)

echo 正在启动 云只智联 候选人筛选排序工具 ...
python app.py
pause