@echo off
title AK Forex Quant Trading Desk
cd /d "%~dp0"

echo ======================================================================
echo           AK FOREX TRADING SYSTEM -- STANDALONE DESKTOP LAUNCHER
echo ======================================================================
echo.

echo [1/3] Checking MetaTrader 4 Terminal ...
tasklist /fi "imagename eq terminal.exe" 2>nul | findstr /i "terminal.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo       [OK] MetaTrader 4 is active and connected to Exness.
) else (
    echo       Starting MetaTrader 4 terminal in background...
    if exist "C:\Program Files (x86)\MetaTrader 4\terminal.exe" (
        start "" "C:\Program Files (x86)\MetaTrader 4\terminal.exe"
        timeout /t 3 /nobreak > nul
        echo       [OK] MetaTrader 4 launched.
    ) else (
        echo       [NOTE] MT4 not at default path. Will auto-open when you click 'Start Live Trading'.
    )
)

echo [2/3] Checking AK Forex Local API Bridge Server ...
powershell -Command "try { if ((Invoke-WebRequest -Uri 'http://127.0.0.1:8642/api/status' -UseBasicParsing -TimeoutSec 1).StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo       [OK] API Server is already online.
) else (
    echo       Starting API bridge server daemon in background...
    start "AK Forex API Server" /min python -m api.server
    echo       Waiting for API server readiness...
    powershell -Command "$i=0; while($i -lt 15) { try { if ((Invoke-WebRequest -Uri 'http://127.0.0.1:8642/api/status' -UseBasicParsing -TimeoutSec 1).StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500; $i++ }; exit 1" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo       [OK] API Server ready on http://127.0.0.1:8642.
    ) else (
        echo       [WARNING] Starting in background...
    )
)

echo [3/3] Opening Quant Trading Desk Application ...

:: Prefer frameless app window via Microsoft Edge
where msedge >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" msedge --app=http://127.0.0.1:8642 --window-size=1440,900 --window-name="AK Forex Quant Trading Desk"
    goto :done
)

:: Alternative frameless app window via Google Chrome
where chrome >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" chrome --app=http://127.0.0.1:8642 --window-size=1440,900
    goto :done
)

:: Default browser fallback
start http://127.0.0.1:8642

:done
echo.
echo ======================================================================
echo   Quant Trading Desk launched successfully!
echo   Click 'Start Live Trading' in the app to begin multi-pair trading.
echo ======================================================================
timeout /t 3 > nul
exit
