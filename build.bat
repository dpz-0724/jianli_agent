@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 打包云只智联候选人筛选排序工具

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo 正在安装 PyInstaller ...
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
)

echo 开始打包（约需 1-2 分钟）...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "云只智联候选人筛选排序工具" ^
    --paths code ^
    --collect-all playwright ^
    --hidden-import matcher ^
    --hidden-import searcher ^
    --hidden-import bot ^
    --hidden-import db ^
    --hidden-import scripts ^
    app.py

echo.
echo 打包完成！可执行文件在 dist\云只智联候选人筛选排序工具.exe
echo 注意：浏览器自动化需要 Chromium；可在软件内「系统设置」指向已安装的 Chrome。
pause