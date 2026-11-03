@echo off
cd /d "%~dp0"
python -m ionoreview library "%~dp0datasets"
if errorlevel 1 pause
