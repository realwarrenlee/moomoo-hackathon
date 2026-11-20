@echo off
setlocal
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
cd /d "%ROOT%\backend"
rem Autonomous execution (Mode B): enabled by the owner's explicit, durable
rem AUTO_PAPER activation pin recorded in the ledger. ORDER_WRITES_ENABLED
rem stays false here; schedule_auto_paper scopes writes=true to the executor
rem subprocess only, and every submission still requires the unexpired
rem risk-v3 activation pin plus all per-run RiskGate checks.
set "TRADING_MODE=AUTO_PAPER"
set "ORDER_WRITES_ENABLED=false"
"%ROOT%\.venv\Scripts\python.exe" -m scripts.schedule_auto_paper --scheduled >> "%ROOT%\data\auto-scheduler-task.log" 2>&1
exit /b %ERRORLEVEL%
