@echo off
chcp 65001 >nul
title Smart CRM Auto Reply
cd /d "%~dp0"

echo ============================================
echo   Smart CRM Auto Reply
echo   Target contacts: configured in config.py
echo   Poll interval  : 10 seconds
echo   Ctrl+C to stop
echo ============================================
echo.

:: Force UTF-8 output from Python (match chcp 65001)
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

:: First-run / guided launcher: calibrate if needed, then detect & reply
python -m wechat_rpa.launcher

echo.
echo Stopped. Press any key to close...
pause >nul