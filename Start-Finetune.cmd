@echo off
cd /d "%~dp0"
set "IONO_TRAIN_PY=%USERPROFILE%\.t3\training-envs\ionoreview\Scripts\python.exe"
if not exist "%IONO_TRAIN_PY%" goto missing
if "%~1"=="" goto usage
"%IONO_TRAIN_PY%" -m ionoreview.finetune prepare
if errorlevel 1 goto failed
"%IONO_TRAIN_PY%" -m ionoreview.finetune inspect
if errorlevel 1 goto failed
"%IONO_TRAIN_PY%" -m ionoreview.finetune train --name "%~1"
if errorlevel 1 goto failed
exit /b 0
:missing
echo Run Install-Training.cmd first.
goto failed
:usage
echo Usage: Start-Finetune.cmd round001
:failed
pause
exit /b 1
