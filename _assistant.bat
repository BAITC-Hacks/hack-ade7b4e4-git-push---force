@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title HackAlem AI assistant
echo ============================================
echo  HACKALEM - AI assistant for the analyst
echo  Browser opens http://localhost:8000 in 4 seconds.
echo  To stop the assistant: close this window.
echo ============================================
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
python -m uvicorn app.main:app --port 8000
echo.
echo The assistant stopped. If there is an error above, copy this window text to Claude.
pause
