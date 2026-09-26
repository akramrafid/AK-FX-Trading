# Operations Runbook: AK Forex Trading System

**Role:** Operator / Trader  
**Version:** 1.0.0  
**Status:** Production  

---

## 1. System Overview

The AK Forex Trading system is a fully automated algorithmic trading solution executing a 10:1 reward-to-risk breakout strategy on MetaTrader 4 (MT4). It consists of:
1. **MT4 Terminal + DWX Connect EA:** Running on a Windows VPS or dedicated desktop, exporting closed bar data and listening for atomic trade commands.
2. **Bridge Engine (`bridge/executor.py`):** Pure Python runtime evaluating closed M5 candles, applying dynamic lot sizing, and coordinating execution.
3. **Risk Guardrails (`risk/guardrails.py`):** Non-bypassable gate enforcing a 3.0% daily loss limit, max 1 open position, max 3 daily trades, 2.5 pip spread ceiling, session filters (07:00–17:00 UTC), and emergency stop.
4. **Bridge Watchdog (`bridge/watchdog.py`):** Process supervisor monitoring MT4 file heartbeat and triggering an emergency halt if MT4 feed stalls.
5. **Alerts Dispatcher (`integrations/alerts.py`):** Telegram and webhook broadcaster for critical events.

---

## 2. Initial Setup Procedure

### 2.1 MetaTrader 4 Terminal Setup
1. Launch MT4 terminal.
2. Go to **Tools > Options > Expert Advisors**:
   - Check **"Allow automated trading"**.
   - Check **"Allow DLL imports"** (required by DWX file protocol).
3. Open an M5 chart for the trading pair (e.g. `EURUSD`, Period: M5).
4. Copy `DWX_Server.mq4` into `MQL4/Experts/` folder.
5. In MT4 Navigator, drag `DWX_Server` onto the M5 chart.
6. Verify smiley face icon appears in the upper right corner of the chart.

### 2.2 Environment Configuration
1. In the repository root, copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and set `MT4_FILES_DIR` to your MT4 terminal's data folder:
   - In MT4: click **File > Open Data Folder**, then navigate to `MQL4/Files`.
   - Paste the path into `MT4_FILES_DIR` in `.env`.
3. Configure your Telegram bot credentials (optional but recommended):
   - `TELEGRAM_BOT_TOKEN=...`
   - `TELEGRAM_CHAT_ID=...`

---

## 3. Starting the Trading Bridge

### On Windows VPS:
Run the automated launcher:
```cmd
scripts\run_bridge.bat
```
The script validates configuration, checks Python environment, and enters an automatic restart supervisor loop.

### On Linux / Container:
```bash
chmod +x scripts/run_bridge.sh
./scripts/run_bridge.sh
```

---

## 4. Daily Operational Checklist

| Time (UTC) | Event | Action / Verification |
|---|---|---|
| **06:45 UTC** | Pre-London Session | Verify bridge console shows `HEALTHY`. Check MT4 chart smiley face. |
| **07:00 UTC** | London Open | Session window opens. Bridge transitions from session-filtered to active evaluation. |
| **12:00 UTC** | London / NY Overlap | High liquidity period. Verify spread remains below 2.5 pip ceiling. |
| **17:00 UTC** | NY Close | Session window closes. No new trades evaluated until 07:00 UTC next day. |
| **00:00 UTC** | UTC Day Rollover | Circuit breaker counters, daily trade count, and daily loss tracker automatically reset. |

---

## 5. Circuit Breaker & Emergency Procedures

### 5.1 When the 3.0% Daily Loss Limit Breaches
1. The risk engine immediately trips the circuit breaker:
   `TradeRejectionReason.DAILY_LOSS_LIMIT_EXCEEDED`.
2. A critical alert is dispatched to Telegram:
   `🚨 [CRITICAL] Risk Guardrail Event: Daily loss limit breached! Cumulative daily loss is 3.0%...`
3. All new trade setups are strictly rejected for the remainder of the calendar day.
4. Active position management continues until the open trade reaches TP or SL.
5. **Operator action:** Do NOT attempt to restart or bypass the circuit breaker. Review trade logs in `docs/qa/` or console. Trading automatically resumes at 00:00 UTC.

### 5.2 Manual Emergency Kill-Switch Activation
If abnormal broker spread, flash crash, or high-impact geopolitical event occurs:
- **Option A (Environment):** Set `EMERGENCY_HALT=true` in `.env`.
- **Option B (Python REPL / Code):**
  ```python
  from risk.guardrails import RiskGuardrails
  guardrails.trigger_emergency_halt("Operator manual emergency halt")
  ```
- **Option C (MT4 level):** Click the "AutoTrading" button on the MT4 toolbar to disable all EA execution.

---

## 6. Desktop Application (Flutter GUI Control Room)

The system includes a standalone Flutter Windows Desktop control room (`flutter_app/`) modeled with a dark glassmorphic interface, real-time price action charting, interactive trade signal markers, account telemetry, and one-click execution controls.

### 6.1 One-Click Launch

To launch both the local Python API bridge (`http://127.0.0.1:8642`) and the Flutter Desktop Application simultaneously:

```cmd
scripts\run_app.bat
```

This batch launcher:
1. Verifies the Python 3.10+ virtual environment and Flutter SDK.
2. Spawns the background HTTP & RFC-6455 WebSocket API server (`python -m api.server`).
3. Launches the Flutter Windows desktop app (`flutter run -d windows`).

### 6.2 Manual Component Startup (Development Mode)

If developing or running components individually:

1. **Start the API Server**:
   ```cmd
   python -m api.server
   ```
2. **Launch the Flutter Application**:
   ```cmd
   cd flutter_app
   flutter run -d windows
   ```

### 6.3 GUI Features & Controls

- **Live Navigation & Status (`HeaderNav`):**
  - Displays real-time WebSocket connection state (`LIVE`, `CONNECTING`, `OFFLINE`).
  - Quick-switch tabs for Dashboard, Trades, Signals, Risk, and Settings.
  - "Bridge: Running / Stopped" status badge with one-click settings launcher.
- **Top Pair Selector (`MarketChips`):**
  - Multi-market switcher between `EURUSDm`, `GBPUSDm`, `USDJPYm`, and `XAUUSDm` with live pip change and spread indicators.
- **Interactive Price Canvas (`TradingChart`):**
  - Live M5 candle price action rendered via `fl_chart` with gradient glow.
  - Timeframe switcher (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`).
  - Automated visual entry pins: `[B]` (Buy) and `[S]` (Sell) markers anchored to sweep/confirmation levels.
- **Account & Strategy Card (`AccountCard`):**
  - Live account balance (`$500.00`), dynamic risk budget (`$7.50 / 1.5%`), and auto-calculated lot size (`0.11 lots`).
  - **"Start Live Trading" / "Stop Trading"**: Dispatches bridge startup/shutdown to the local quant engine.
  - **"EMERGENCY KILL-SWITCH"**: Instant red button triggering non-bypassable system halt.
- **Risk & Watchdog Telemetry (`RiskMeterCard`):**
  - Multi-segment risk budget bar.
  - Daily trades counter (`1/3`) and daily loss limit gauge (`0.0% / 3.0%`).
  - Watchdog heartbeat health indicator (`HEAL` / `STALL`).
- **Audit Ledger (`TransactionsTable`):**
  - Live scrollable table of dispatched trades and signal confirmations with entry price, SL, TP, PnL, and timestamps.
- **In-App Configuration (`SettingsDialog`):**
  - Real-time adjustment of Risk per Trade (%), Max Daily Loss (%), Spread Ceiling (pips), Session Window (UTC), and Telegram alerts.

