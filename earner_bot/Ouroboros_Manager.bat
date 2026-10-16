@echo off
title Ouroboros Institutional Trading Terminal
color 0B
:menu
cls
echo ==================================================
echo         OUROBOROS INSTITUTIONAL MANAGER v3.2       
echo ==================================================
echo.
echo    1. Start Full Institutional Stack (Bot + Dead-Man's Switch)
echo    2. Start Trading Bot Only (Desktop GUI)
echo    3. Start Dead-Man's Switch Supervisor Only
echo    4. Open Obsidian Neural Memory Vault
echo    5. Stop All Bot & Supervisor Processes
echo    6. View Trade & Error Logs
echo    7. Run Integration Verification Test
echo    8. Exit
echo.
echo ==================================================
set /p choice="Select an option (1-8): "

if "%choice%"=="1" goto start_all
if "%choice%"=="2" goto start_bot
if "%choice%"=="3" goto start_dms
if "%choice%"=="4" goto open_obsidian
if "%choice%"=="5" goto stop
if "%choice%"=="6" goto logs
if "%choice%"=="7" goto test_verify
if "%choice%"=="8" goto exit

:start_all
echo Starting Ouroboros Trading Bot and Dead-Man's Switch...
if not exist output mkdir output
start "Ouroboros Trading Bot" cmd /k "python app.py"
timeout /t 2 >nul
start "Ouroboros Dead-Man's Switch" cmd /k "python dead_mans_switch.py"
echo Full institutional stack started!
timeout /t 3
goto menu

:start_bot
echo Starting Ouroboros Trading Bot GUI...
if not exist output mkdir output
start "Ouroboros Trading Bot" cmd /k "python app.py"
goto menu

:start_dms
echo Starting Ouroboros Dead-Man's Switch Supervisor...
start "Ouroboros Dead-Man's Switch" cmd /k "python dead_mans_switch.py"
goto menu

:open_obsidian
echo Opening Obsidian Neural Memory Vault...
start "" "obsidian://open?path=%CD%\Obsidian_Vault"
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
if exist logs\Ouroboros_trades.log start notepad logs\Ouroboros_trades.log
if exist logs\Ouroboros_errors.log start notepad logs\Ouroboros_errors.log
if exist output\run.log start notepad output\run.log
goto menu

:test_verify
echo Running Full Institutional Test Suite...
python test_institutional_architecture.py
python test_self_learning_vault.py
echo.
pause
goto menu

:exit
exit
