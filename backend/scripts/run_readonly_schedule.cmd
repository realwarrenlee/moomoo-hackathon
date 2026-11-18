@echo off
setlocal
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
cd /d "%ROOT%\backend"
"%ROOT%\.venv\Scripts\python.exe" -m scripts.schedule_readonly --scheduled >> "%ROOT%\data\scheduler-task.log" 2>&1
exit /b %ERRORLEVEL%
