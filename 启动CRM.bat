@echo off
chcp 65001 >nul
title Smart CRM Launcher
cd /d "%~dp0"

echo ============================================
echo   Smart CRM Launcher (default Agent: react)
echo   Backend  : http://localhost:8000
echo   Frontend : http://localhost:3000
echo ============================================
echo.

:: Force UTF-8 output from Python (match chcp 65001)
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

python start_agent.py

echo.
echo Services stopped. Press any key to close...
pause >nul
