@echo off
cd /d "%~dp0"
python -m ionoreview.archive inventory "F:\MyData\ND\lfs" reports\inventory.json --pilot datasets\pilot
if errorlevel 1 exit /b 1
python -m ionoreview.archive hydrate reports\inventory.json reports\hydration.json --workers 64
if errorlevel 1 exit /b 1
python -m ionoreview.archive build reports\inventory.json datasets --loader vendor\ionograms_handler --hydration reports\hydration.json --workers 4
if errorlevel 1 exit /b 1
python -m ionoreview.verify_archive "%~dp0"
if errorlevel 1 pause
