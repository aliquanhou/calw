@echo off
chcp 65001 >nul
title Building AI Agent EXE...

echo ============================================
echo  AI Agent - 打包安装程序
echo  支持: DeepSeek / Anthropic Claude / OpenAI
echo ============================================
echo.

:: Install PyInstaller if not already installed
pip install pyinstaller 2>nul | findstr /C:"already satisfied" >nul
if %errorlevel% neq 0 (
    echo [*] 安装 PyInstaller...
    pip install pyinstaller
)

echo [*] 开始打包，请稍候...
echo.

pyinstaller ^
    --name "AIAgent" ^
    --windowed ^
    --onefile ^
    --noconfirm ^
    --add-data "agent;agent" ^
    --hidden-import "agent.core" ^
    --hidden-import "agent.tools" ^
    --hidden-import "agent.prompt" ^
    --hidden-import "agent.app" ^
    --hidden-import "agent.providers" ^
    --hidden-import "anthropic" ^
    --hidden-import "openai" ^
    --hidden-import "customtkinter" ^
    --hidden-import "tkinter" ^
    --collect-all "anthropic" ^
    --collect-all "openai" ^
    --clean ^
    main.py

echo.
if %errorlevel% equ 0 (
    echo ============================================
    echo  [SUCCESS] 打包完成!
    echo  输出路径: dist\AIAgent.exe
    echo ============================================
    echo.
    echo  提示: 首次运行会生成 config.json
) else (
    echo ============================================
    echo  [FAILED] 打包失败，请检查错误信息
    echo ============================================
)

pause
