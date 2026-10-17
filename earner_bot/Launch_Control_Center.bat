@echo off
cd /d "%~dp0"
if exist "%~dp0dist\Ouroboros_Control_Center\Ouroboros_Control_Center.exe" (
    start "" "%~dp0dist\Ouroboros_Control_Center\Ouroboros_Control_Center.exe"
) else (
    start "" pythonw control_center.py
)
exit
