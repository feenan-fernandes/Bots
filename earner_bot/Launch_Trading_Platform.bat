@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Ouroboros Trading Platform
color 0B

echo ==================================================
echo         OUROBOROS INSTITUTIONAL TRADING PLATFORM   
echo ==================================================
echo.
echo Launching your Bento Grid 2.0 Trading Platform...
echo Port: 8080 (http://127.0.0.1:8080)
echo.

if not exist "%~dp0output" mkdir "%~dp0output"
if not exist "%~dp0logs" mkdir "%~dp0logs"

:: Check if port 8080 is already held and prompt or release if stuck
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do (
    echo Port 8080 was active, resetting previous instance...
    taskkill /F /PID %%a >nul 2>&1
)

:: Launch Trading Platform
python app.py
