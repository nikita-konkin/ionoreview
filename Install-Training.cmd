@echo off
cd /d "%~dp0"
python training\bootstrap.py
if errorlevel 1 goto failed
exit /b 0
:failed
pause
exit /b 1
