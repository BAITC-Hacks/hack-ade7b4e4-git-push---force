@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title HackAlem pipeline
echo ============================================
echo  HACKALEM - install, run pipeline, tests
echo ============================================
echo.
echo [1/3] install packages (first time 1-2 minutes)
python -m pip install -q -r requirements.txt
if errorlevel 1 goto pipfail
echo OK
echo.
echo [2/3] pipeline: python -m pipeline --data data --out out
python -m pipeline --data data --out out
if errorlevel 1 goto runfail
echo.
echo [3/3] tests
python -m pytest -q tests/test_pipeline.py
echo.
echo ============================================
echo  FINISHED. Copy this window text to Claude.
echo ============================================
pause
exit /b 0

:pipfail
echo ERROR: pip install failed. Copy this window text to Claude.
pause
exit /b 1

:runfail
echo ERROR: pipeline failed. Copy this window text to Claude.
pause
exit /b 1
