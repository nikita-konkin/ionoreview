@echo off
cd /d "%~dp0"
python -m ionoreview review "%~dp0datasets\pilot"
if errorlevel 1 pause
