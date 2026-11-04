@echo off
cd /d "%~dp0"
set "IONO_TRAIN_PY=%USERPROFILE%\.t3\training-envs\ionoreview\Scripts\python.exe"
set "IONO_EXPERIMENT=experiments\student-model-v1\training_config.json"
if not exist "%IONO_EXPERIMENT%" goto missing
if "%~1"=="" goto usage
"%IONO_TRAIN_PY%" -m ionoreview.finetune --config "%IONO_EXPERIMENT%" prepare
if errorlevel 1 goto failed
"%IONO_TRAIN_PY%" -m ionoreview.finetune --config "%IONO_EXPERIMENT%" inspect
if errorlevel 1 goto failed
"%IONO_TRAIN_PY%" -m ionoreview.finetune --config "%IONO_EXPERIMENT%" train --name "%~1"
if errorlevel 1 goto failed
exit /b 0
:missing
echo Build the experiment with python -m ionoreview.experiment first.
goto failed
:usage
echo Usage: Start-Experiment-Training.cmd round001
:failed
pause
exit /b 1
