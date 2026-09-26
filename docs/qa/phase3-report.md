# Phase 3 QA Report: MT4 Execution Bridge

**Component:** MT4 File-Based DWX Connect Bridge (`bridge/dwx_client.py`, `bridge/sizing.py`, `bridge/executor.py`)  
**Interface:** Multi-Timeframe Poller (`BridgeExecutor.step_multitimeframe`)  
**Position Sizing:** Non-negotiable dynamic lot computation formula based on balance and stop distance  
**Dependencies:** Zero external dependencies (Windows file lock exponential backoff, atomic rename, pure Python stdlib)  

---

## 1. Multi-Timeframe Bridge Architecture

The execution bridge connects the Phase 1 multi-timeframe rule engine directly to any broker MT4 terminal via DWX Connect:
1. **Multi-Timeframe Ingestion:**
   - Watches `DWX_Bars_<Symbol>_M15.txt` and `DWX_Bars_<Symbol>_M5.txt` for closed higher-timeframe bars.
   - Feeds HTF bars to `RuleEngine.on_htf_candle()` to detect liquidity sweeps and arm the 1-minute watch.
   - Watches `DWX_Bars_<Symbol>_M1.txt` for newly closed 1-minute bars.
   - Evaluates 3-candle confirmation sequence on 1m bars via `RuleEngine.on_m1_candle()`.
2. **Dynamic Position Sizing:**
   - Formula: `lot_size = (account_balance * risk_%) / (stop_loss_distance_in_pips * pip_value_per_lot)`.
   - Quote currency precision handled explicitly (USD, JPY, EUR, GBP, AUD).
   - Floored (`ROUND_DOWN`) to broker 0.01 lot steps.
   - Hard sanity bounds enforced: min 0.01 lot, max 50.00 lots ceiling.
3. **Atomic Execution Dispatch:**
   - Order command written atomically with `.tmp` staging and safe rename.
   - Deterministic 32-bit signed integer MT4 Magic Number generation prevents collision.
   - In-memory and database idempotency tracking prevents duplicate order execution.

---

## 2. Verification Matrix

| Test Case | Description | Result |
|---|---|---|
| `test_step_multitimeframe_execution` | M5 sweep + M1 3-candle confirmation trigger and execution report | PASSED |
| `test_step_live_signal_execution` | Single-timeframe backward compatibility | PASSED |
| `test_calculate_lots_eurusd` | Exact lot sizing: $10,000 balance @ 1.5% risk on 15 pip SL = 1.00 lot | PASSED |
| `test_calculate_lots_round_down` | Conservative rounding floor: 17 pip SL = 0.88 lot (not 0.89) | PASSED |
| `test_min_lot_rejection` | Sub-0.01 lot account balance rejection | PASSED |
| `test_max_lot_cap` | 50.00 lot absolute safety ceiling clamp | PASSED |
| `test_atomic_write_and_read` | Exponential backoff Windows file concurrency | PASSED |
| `test_idempotency_duplicate_prevention` | Subsequent steps on same bar do not duplicate orders | PASSED |

---

## 3. Status
**Phase 3 Status:** COMPLETED & VERIFIED.
