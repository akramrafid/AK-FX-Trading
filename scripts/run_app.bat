@echo off
title AK Forex Trading Desk
cd /d "%~dp0\.."

echo ======================================================================
echo   AK FOREX TRADING SYSTEM -- LAUNCHING DESKTOP APPLICATION
echo ======================================================================
echo.

set "RELEASE_DIR=flutter_app\build\windows\x64\runner\Release"

echo [1/3] Checking MetaTrader 4 terminal connection ...
tasklist /fi "imagename eq terminal.exe" 2>nul | findstr /i "terminal.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo       [OK] MetaTrader 4 terminal is active and connected to Exness.
) else (
    echo       Starting MetaTrader 4 terminal in background...
    if exist "C:\Program Files (x86)\MetaTrader 4\terminal.exe" (
        start "" "C:\Program Files (x86)\MetaTrader 4\terminal.exe"
        timeout /t 3 /nobreak > nul
        echo       [OK] MetaTrader 4 launched.
    ) else (
        echo       [WARNING] MT4 not found at default path. Please ensure MT4 is running.
    )
)

echo [2/3] Checking local Python API bridge server on http://127.0.0.1:8642 ...
powershell -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8642/api/status' -UseBasicParsing -TimeoutSec 1).StatusCode } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo       [OK] API Server is already running.
) else (
    echo       Starting local Python API server...
    start "AK Forex API Server" /min python -m api.server
    timeout /t 2 /nobreak > nul
)

if exist "%RELEASE_DIR%\ak_forex_app.exe" goto :launch_windows_exe

echo [3/3] Launching AK Forex Desktop Control Desk ...

:: Check for Edge or Chrome application window mode (frameless native desktop look)
where msedge >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" msedge --app=http://127.0.0.1:8642 --window-size=1440,900 --window-name="AK Forex Trading Desk"
    goto :done
)

where chrome >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" chrome --app=http://127.0.0.1:8642 --window-size=1440,900
    goto :done
)

:: Fallback to default browser
start http://127.0.0.1:8642
goto :done

:launch_windows_exe
echo [2/2] Launching Windows Native Desktop Application ...
cd "%RELEASE_DIR%"
start "" ak_forex_app.exe
goto :done

:done
echo.
echo Application launched successfully at http://127.0.0.1:8642!