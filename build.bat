@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title 构建招聘自动化工作台 V1

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo 正在安装构建依赖...
    python -m pip install -r requirements-dev.txt
    if errorlevel 1 goto :failed
)

python -m unittest discover -s tests -v
if errorlevel 1 goto :failed

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "招聘自动化工作台" ^
    --paths . ^
    --paths code ^
    --collect-all playwright ^
    --hidden-import searcher ^
    --hidden-import bot ^
    --hidden-import workbench.ui ^
    --hidden-import workbench.browser_worker ^
    app.py
if errorlevel 1 goto :failed

echo.
echo 构建完成：dist\招聘自动化工作台.exe
exit /b 0

:failed
echo.
echo [失败] 构建未完成。
pause
exit /b 1
