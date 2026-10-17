@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Ouroboros Institutional Trading Platform Manager
color 0B

:menu
cls
echo ==================================================
echo         OUROBOROS INSTITUTIONAL MANAGER v3.2       
echo ==================================================
echo.
echo    1. Launch Trading Platform (Bento Grid 2.0 GUI)
echo    2. Launch Institutional Control Center
echo    3. Start Full Institutional Stack (Bot + Dead-Man)
echo    4. Start Dead-Man's Switch Supervisor Only
echo    5. Open Obsidian Neural Memory Vault
echo    6. Stop All Bot ^& Supervisor Processes
echo    7. View Trade ^& Error Logs
echo    8. Run Integration Verification Test ^& Backtest
echo    9. Exit
echo.
echo ==================================================
set /p choice="Select an option (1-9): "

if "%choice%"=="1" goto start_bot
if "%choice%"=="2" goto start_gui
if "%choice%"=="3" goto start_all
if "%choice%"=="4" goto start_dms
if "%choice%"=="5" goto open_obsidian
if "%choice%"=="6" goto stop
if "%choice%"=="7" goto logs
if "%choice%"=="8" goto test_verify
if "%choice%"=="9" goto exit

:start_bot
echo Launching Ouroboros Trading Platform...
call "%~dp0Launch_Trading_Platform.bat"
goto menu

:start_gui
echo Launching Ouroboros Control Center...
if exist "%~dp0dist\Ouroboros_Control_Center\Ouroboros_Control_Center.exe" (
    start "" "%~dp0dist\Ouroboros_Control_Center\Ouroboros_Control_Center.exe"
) else (
    start "" pythonw control_center.py
)
goto menu

:start_all
echo Starting Ouroboros Trading Bot and Dead-Man's Switch...
if not exist "%~dp0output" mkdir "%~dp0output"
start "Ouroboros Trading Bot" cmd /k "cd /d "%~dp0" && python app.py"
timeout /t 2 >nul
start "Ouroboros Dead-Man's Switch" cmd /k "cd /d "%~dp0" && python dead_mans_switch.py"
echo Full institutional stack started!
timeout /t 3
goto menu

:start_dms
echo Starting Ouroboros Dead-Man's Switch Supervisor...
start "Ouroboros Dead-Man's Switch" cmd /k "cd /d "%~dp0" && python dead_mans_switch.py"
goto menu

:open_obsidian
echo Opening Obsidian Neural Memory Vault...
if exist "%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe" (
    start "" "%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe"
) else (
    start "" "obsidian://open?path=%~dp0Obsidian_Vault"
)
goto menu

:stop
echo Stopping Ouroboros Bot and Supervisor...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Ouroboros Dead-Man's Switch*" >nul 2>&1
echo All processes halted!
timeout /t 2
goto menu

:logs
echo Opening log files...
if exist "%~dp0logs\Ouroboros_trades.log" start notepad "%~dp0logs\Ouroboros_trades.log"
if exist "%~dp0logs\Ouroboros_errors.log" start notepad "%~dp0logs\Ouroboros_errors.log"
if exist "%~dp0output\run.log" start notepad "%~dp0output\run.log"
goto menu

:test_verify
echo Running Full Institutional Test Suite & AETHERIS Backtest...
cd /d "%~dp0"
python test_institutional_architecture.py
python test_self_learning_vault.py
python backtest_aetheris.py
echo.
pause
goto menu

:exit
exit
