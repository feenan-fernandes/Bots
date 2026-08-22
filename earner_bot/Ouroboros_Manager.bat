@echo off
title Ouroboros Bot Manager
color 0B
:menu
cls
echo ==================================================
echo             Ouroboros BOT MANAGER v3.1              
echo ==================================================
echo.
echo    1. Start Bot (Background)
echo    2. Start Bot (Visible Window)
echo    3. Stop Bot
echo    4. View Logs
echo    5. Exit
echo.
echo ==================================================
set /p choice="Select an option (1-5): "

if "%choice%"=="1" goto start_bg
if "%choice%"=="2" goto start_fg
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto exit

:start_bg
echo Starting Ouroboros Bot in the background...
if not exist output mkdir output
start /b python app.py > output\run.log 2>&1
echo Bot started!
timeout /t 3
goto menu

:start_fg
echo Starting Ouroboros Bot...
start "Ouroboros Bot" cmd /k "python app.py"
goto menu

:stop
echo Stopping Ouroboros Bot...
:: Find process holding port 8080 and kill it
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo Bot stopped!
timeout /t 3
goto menu

:logs
echo Opening log files...
if exist logs\Ouroboros_trades.log start notepad logs\Ouroboros_trades.log
if exist logs\Ouroboros_errors.log start notepad logs\Ouroboros_errors.log
if exist output\run.log start notepad output\run.log
goto menu

:exit
exit
