# Phase 3 Verification Report — MT4 Execution Bridge

**Project:** AK Forex Trading System  
**Track:** Hybrid  
**Phase:** Phase 3 (MT4 Execution Bridge & Automated Trade Execution)  
**Date:** 2026-09-24  
**Evaluator:** Coordinator / Senior Integration Engineer / Senior QA Architect  
**Status:** PASS — 100% Green (All Verification Gates Passed)

---

## 1. Executive Summary

Phase 3 establishes the end-to-end automated execution bridge connecting the Python algorithmic trading system to MetaTrader 4 (MT4) via the open-source, file-based DWX Connect protocol.

The bridge operates exclusively on closed M5 bars exported by the MT4 Expert Advisor, strictly enforces dynamic position sizing (Hard Rule 3), prevents duplicate order submissions through deterministic 32-bit magic numbers and signal idempotency caches, and verifies trade execution tickets with a 10-second timeout alert.

The execution bridge directly integrates the Phase 1 `RuleEngine` (`engine/rule_engine.py`), guaranteeing complete code parity between historical backtesting and live forward trading.

---

## 2. Component Deliverables & Architectural Verification

### 2.1 DWX Connect Client Protocol (`bridge/dwx_client.py`)
- **Protocol**: File-based communication inside MT4's `MQL4/Files/` directory.
  - `DWX_Commands.txt`: Formatted JSON trade orders written by Python.
  - `DWX_Reports.txt`: Real-time execution reports written by MT4 EA.
  - `DWX_Bars_<SYMBOL>_<TIMEFRAME>.txt`: Real-time closed-bar OHLCV feeds exported by MT4 EA.
- **Concurrency & File Locks**:
  - Implements atomic writes (`.tmp` staging file with atomic `os.replace`).
  - Exponential backoff with random jitter on Windows `PermissionError` and `BlockingIOError`.
- **Duplicate Prevention & Verification**:
  - Tracks submitted magic numbers; immediately rejects duplicate magic submissions.
  - Polls `DWX_Reports.txt` for ticket confirmation within 10 seconds.
  - Unconfirmed orders trigger a critical alert callback and strictly suppress duplicate retries.

### 2.2 Dynamic Position Sizing Engine (`bridge/sizing.py`)
- **Hard Rule 3 Compliance**:
  - Dynamically sizes positions:
    $$\text{Lots} = \left\lfloor \frac{\text{Account Balance} \times \text{Risk \%}}{\text{Stop Loss Distance (pips)} \times \text{Pip Value per Lot}} \times 100 \right\rfloor \div 100$$
  - Rounds down to the nearest 0.01 lot step (never rounds up).
  - Handles pip sizing: $0.01$ for JPY pairs (e.g., USD/JPY, EUR/JPY), $0.0001$ for major/cross pairs.
  - Quote currency exchange rate conversion:
    - USD Quote (EUR/USD, GBP/USD, AUD/USD): Fixed $\$10.00$ per standard lot.
    - USD Base (USD/JPY): $\frac{100,000 \times 0.01}{\text{USD/JPY rate}}$.
    - Cross Pairs (EUR/JPY, EUR/GBP): Converts quote pip value to USD via corresponding major rate.
  - Sanity bounds: Rejects setups where calculated lot size $< 0.01$ lot; caps excessive sizing at $50.00$ lots.

### 2.3 Live Bridge Executor (`bridge/executor.py`)
- **Closed-Bar Processing**:
  - Ingests closed bars from MT4; invokes `RuleEngine.evaluate_completed_candle()`.
  - Guarantees zero look-ahead bias and zero intrabar execution.
- **Magic Number Engineering**:
  - MT4 requires a 32-bit signed integer (`int`, max $2,147,483,647$).
  - Implements `generate_mt4_magic_number(dt, seq)` which strictly guarantees magic numbers remain $< 2,000,000,000$, eliminating 32-bit overflow bugs.
- **Idempotency**:
  - Combines symbol, direction, and bar close timestamp into a unique execution hash.
  - Prevents double-execution on re-polled identical bars.

### 2.4 Production MQL4 Expert Advisor (`bridge/mql4/DWX_AutoTrader.mq4`)
- **Compatibility**: Native MQL4 code for MetaEditor compilation with `#property strict`.
- **Bar-Close Detection**:
  - Evaluates `Time[0] != g_lastBarTime` on every incoming tick.
  - On new bar, immediately writes completed bar 1 OHLCV to `DWX_Bars_<Symbol>_<Period>.txt`.
- **Command Dispatcher (`OnTimer()`)**:
  - Polls `DWX_Commands.txt` at 200ms intervals.
  - Self-contained string-based JSON extractor (zero external DLLs or third-party libraries).
  - Executes market orders via `OrderSend()` with configurable slippage (`MaxSlippagePips`).
  - Appends order execution tickets or error codes directly to `DWX_Reports.txt`.
  - Supports `OPEN`, `MODIFY`, and `CLOSE` commands.

---

## 3. Verification & Test Results

### 3.1 Bridge Test Suite (`tests/test_bridge.py`)
A comprehensive test suite of 14 tests was executed:

| Test Case | Scope | Status |
|:---|:---|:---:|
| `test_atomic_write_and_read` | File lock collision handling & atomic replacement | **PASS** |
| `test_send_order_writes_json_command` | JSON command formatting and serialization | **PASS** |
| `test_duplicate_magic_prevention` | Magic number collision rejection | **PASS** |
| `test_poll_order_confirmation_success` | Report polling and ticket extraction | **PASS** |
| `test_poll_order_confirmation_timeout_alerts` | 10s timeout alerting and non-duplicate invariant | **PASS** |
| `test_read_closed_bars` | MT4 CSV bar parsing to Candle domain models | **PASS** |
| `test_pip_size` | Pip scale for USD/JPY, EUR/JPY, EUR/USD | **PASS** |
| `test_pip_value_usd` | Conversion for USD quote, USD base, and cross rates | **PASS** |
| `test_calculate_lots_eurusd` | Exact lot sizing for 1.5% risk on $10k account | **PASS** |
| `test_calculate_lots_round_down` | Fractional lot floor rounding to 0.01 step | **PASS** |
| `test_min_lot_rejection` | Lot size < 0.01 rejection on small balance | **PASS** |
| `test_max_lot_cap` | Lot size > 50.00 capping | **PASS** |
| `test_magic_number_fits_32bit_signed_int` | 32-bit signed integer bounds check (< 2.14B) | **PASS** |
| `test_step_triggers_order_on_strategy_signal` | End-to-end bar arrival -> signal -> order -> fill | **PASS** |

### 3.2 Regression Suite Across All Phases
- `tests/test_rule_engine.py`: **15 / 15 PASS**
- `tests/test_backtester.py`: **9 / 9 PASS**
- `tests/test_bridge.py`: **14 / 14 PASS**
- Orchestrator Engine Unit Tests: **34 / 34 PASS**
- **Total Workspace Tests**: **72 / 72 PASS (100% Green)**

---

## 4. Phase Sign-Off & Verdict

All criteria for Phase 3 (MT4 Execution Bridge) have been completely fulfilled. The system is ready to advance to Phase 4 (Non-Bypassable Risk Guardrails).

**Gate P3-G1 Verdict: APPROVED.**
