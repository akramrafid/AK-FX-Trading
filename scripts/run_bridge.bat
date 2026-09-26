@echo off
REM =============================================================================
REM AK Forex Trading System — Windows VPS Launcher
REM =============================================================================

echo [INFO] Starting AK Forex Trading MT4 Bridge...
cd /d "%~dp0\.."

REM Verify Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

REM Run health and configuration check
python -c "import config; cfg = config.load_config(); print(f'[CONFIG] Loaded symbol: {cfg.symbol}, MT4 dir: {cfg.mt4_files_dir}')"
if errorlevel 1 (
    echo [ERROR] Configuration validation failed! Check .env file.
    pause
    exit /b 1
)

REM Launch Bridge with auto-restart supervisor
:loop
echo [INFO] Launching bridge process...
python -m bridge.executor
echo [WARNING] Bridge exited with code %ERRORLEVEL%. Restarting in 5 seconds (Press Ctrl+C to abort)...
timeout /t 5 >nul
goto loop
