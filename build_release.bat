@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title 发布招聘自动化工作台 V0.9

call build.bat
if errorlevel 1 exit /b 1

set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
    echo.
    echo [提示] 未检测到 Inno Setup 6。
    echo ZIP 已生成；安装包需要安装 Inno Setup 后重新运行 build_release.bat。
    exit /b 0
)

echo [安装包] 正在生成每用户安装程序...
"%ISCC%" installer\RecruitmentWorkbench.iss
if errorlevel 1 (
    echo [失败] 安装包生成失败。
    exit /b 1
)

echo.
echo 发布产物：
echo   dist\招聘自动化工作台-v0.9.zip
echo   dist\installer\招聘自动化工作台-v0.9-Setup.exe
exit /b 0
