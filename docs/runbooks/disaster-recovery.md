# Disaster Recovery & Failure Triage Runbook

**Role:** Operator / DevOps / SRE  
**Version:** 1.0.0  
**Status:** Production  

---

## 1. Scenario 1: VPS Unexpected Reboot or Power Failure

### Impact:
The MT4 terminal and Python bridge process were forcefully terminated.

### Recovery Procedure:
1. **Log in to VPS.**
2. **Start MetaTrader 4:** Ensure terminal reconnects to broker server (green connection bars bottom right).
3. **Verify Chart & EA:** Confirm M5 chart is active and `DWX_Server` has a smiley face.
4. **Reconcile Active Positions:**
   - In MT4 Terminal "Trade" tab, inspect if any position opened by the bot is still active (check Magic Number).
   - If an open position exists, verify its Stop-Loss and Take-Profit are registered on the broker's server.
   - *Note:* MT4 server-side SL and TP will protect the position even when Python was down.
5. **Start Bridge:** Run `scripts\run_bridge.bat`.
   - The bridge loads closed bar history, connects to `MQL4/Files`, syncs account balance and open position count, and resumes monitoring.

---

## 2. Scenario 2: Stale MT4 Heartbeat / Communication Loss

### Impact:
MT4 terminal froze, lost internet connection, or EA crashed. New M5 bars are no longer being written to `DWX_Bars_EURUSD_M5.txt`.

### Watchdog Action:
1. When heartbeat exceeds `max_heartbeat_age_sec` (default 600s / 10 minutes), `BridgeWatchdog` automatically trips:
   `Watchdog trigger: CRITICAL: MT4 heartbeat stale! No updates for 605s`.
2. Risk guardrails trigger an emergency halt to prevent stale signals.
3. Alert is fired to Telegram / Webhook:
   `🚨 [CRITICAL] Bridge Watchdog Alert: CRITICAL: MT4 heartbeat stale!`

### Operator Triage:
1. Check VPS internet connectivity and broker server ping.
2. In MT4, check the **Experts** and **Journal** tabs at the bottom of the screen for error messages (e.g., `Error 4066: Custom indicator error` or `Account disabled`).
3. Re-attach the `DWX_Server` EA to the chart if it was unloaded.
4. Once MT4 resumes writing bar files, verify fresh timestamp:
   ```cmd
   python -c "from bridge.watchdog import BridgeWatchdog; from bridge.dwx_client import DWXClient; w = BridgeWatchdog(DWXClient('./mt4_files')); print('Freshness:', w.inspect_file_freshness())"
   ```
5. Clear emergency halt once verified:
   ```python
   guardrails.reset_emergency_halt()
   ```

---

## 3. Scenario 3: Order Confirmation Timeout / Unconfirmed State

### Impact:
The bridge dispatched an order command to `DWX_Commands.txt`, but MT4 did not produce a matching ticket confirmation in `DWX_Reports.txt` within `confirmation_timeout_sec` (10 seconds).

### System Behavior:
1. `DWXClient` raises timeout warning and invokes alert callback.
2. Order status is marked `UNCONFIRMED`.
3. The magic number remains tracked in `_sent_magics` to prevent sending duplicate orders on subsequent ticks.

### Operator Triage:
1. Open MT4 "Trade" tab. Check if the order was actually opened.
   - If **Filled**: Locate the ticket number and update order record if journaling.
   - If **Not Filled**: Check MT4 **Journal** tab for broker rejection (e.g. `Requote`, `Off quotes`, `Trade context busy`, `Invalid S/L`).
2. Bridge will NOT dispatch any duplicate orders for that closed bar.

---

## 4. Scenario 4: Emergency Manual Flattening

If an immediate manual close of all bot-managed positions is required:

### Method A — Via MT4 Terminal (Recommended)
1. In MT4 Terminal "Trade" tab, find orders with the bot's Magic Number.
2. Right-click the order and select **Close Order**.

### Method B — Via Python Command
```python
from bridge.dwx_client import DWXClient, TradeCommand, CommandAction
client = DWXClient("C:/path/to/MT4/MQL4/Files")
# Close by ticket
client.close_order(ticket=1234567, lots=0.01)
```

---

## 5. Scenario 5: Database Telemetry Backup & Restore

### Backup PostgreSQL Schema & Data:
```bash
pg_dump -U postgres -d ak_forex_trading -F c -b -v -f ./backups/ak_forex_$(date +%Y%m%d).dump
```

### Restore Database Snapshot:
```bash
pg_restore -U postgres -d ak_forex_trading -v ./backups/ak_forex_20260924.dump
```
