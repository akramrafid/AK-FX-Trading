# Phase 1 Verification Report — Multi-Timeframe Core Rule Engine

**Project:** AK Forex Trading System  
**Track:** Hybrid  
**Phase:** Phase 1 (Multi-Timeframe Core Rule Engine)  
**Date:** 2026-09-26  
**Evaluator:** Senior Software Engineer / 20-Year Hedge Fund Trader / Senior AI/ML Engineer  
**Status:** PASS — 100% Green (All 137 System & Engine Tests Passing)

---

## 1. Executive Summary

Phase 1 delivers the production-grade, deterministic, zero-dependency algorithmic rule engine executing the user's proprietary liquidity sweep and confirmation breakout strategy across two simultaneous candle streams:
1. **Higher-Timeframe (5-minute and 15-minute bars):** Detection of liquidity sweeps where a candle's wick sweeps beyond a prior opposite-colored candle's extreme and closes back within range. Either 5m or 15m is sufficient to arm the 1-minute confirmation watch.
2. **Lower-Timeframe (1-minute bars):** 3 consecutive directional candles (all bullish for Buy, all bearish for Sell).
3. **Execution & Risk Pricing:**
   - **Entry:** Market order at the close of the 3rd confirming 1-minute candle.
   - **Stop-Loss:** At the extreme (highest high for Sell, lowest low for Buy) across all 3 confirming candles (+ spread/buffer).
   - **Take-Profit:** Strictly fixed at 10x the stop-loss distance (10:1 Reward-to-Risk).
4. **Armed State Lifecycle:**
   - **Expiry:** Strict 15-candle (15-minute) timeout. If 3 consecutive candles do not complete within 15 1-minute bars, the state disarms.
   - **Direction Break:** If a 1-minute candle breaks the required direction before 3 form, the watch state disarms immediately and returns to watching the higher timeframe.

All logic is pure Python with zero third-party dependencies, guaranteeing single-codebase parity across historical backtesting, demo forward-testing, and live MT4 execution.

---

## 2. Key Architecture & Deliverables

### 2.1 Domain & State Models (`engine/models.py`)
- **`ArmedState`**: Explicit state machine tracking active liquidity sweeps awaiting 1-minute confirmation:
  - `direction`: `BUY` or `SELL`
  - `sweep_timeframe`: `"M5"` or `"M15"`
  - `sweep_candle`: Closed HTF candle that triggered the sweep
  - `swept_level`: Prior opposite candle's extreme price
  - `candles_watched`: Running count of 1-minute closed bars (up to `max_watch_candles = 15`)
  - `confirming_candles`: List of accumulated consecutive same-direction 1-minute bars
- **`TradeSignal`**: Immutable trade order directive with entry, stop loss, take profit (10:1), risk/reward distance, timestamp, and timeframe tags.

### 2.2 Reusable Confirmation & 10:1 R:R Math (`engine/confirmation.py`)
- **`evaluate_3_candles`**:
  - Validates 3 consecutive closed bars in the trade direction.
  - **Sell Setup:** `stop_loss = max(c1.high, c2.high, c3.high) + spread_pips * pip_size + buffer_pips * pip_size`.
  - **Buy Setup:** `stop_loss = min(c1.low, c2.low, c3.low) - buffer_pips * pip_size`.
  - **Reward Math:** `risk_distance = abs(entry - stop_loss)`, `take_profit = entry ± (10.0 * risk_distance)`.

### 2.3 Multi-Timeframe Rule Engine (`engine/rule_engine.py`)
- **`on_htf_candle(candle, timeframe="M5"|"M15")`**:
  - Ingests closed 5m or 15m candles; detects wick sweep of prior opposite candle.
  - Arms the 1-minute watch state upon valid sweep.
- **`on_m1_candle(candle)`**:
  - Ingests closed 1m candles while armed.
  - Generates `TradeSignal` the instant the 3rd consecutive confirming candle closes.
  - Disarms immediately if a candle breaks direction before 3 form, or upon 15-candle expiry.
- **`feed_candle(timeframe, candle)`**:
  - Unified streaming ingress returning `{direction, entry_price, stop_loss, take_profit, ...}` when an entry fires.
- **`resample_m1_to_htf(m1_candles, timeframe_minutes)`**:
  - Resamples 1-minute closed bars into exact 5-minute and 15-minute bars with zero look-ahead bias.
- **`scan_multitimeframe_streams(m1_candles, m5_candles, m15_candles)`**:
  - Deterministic event-driven chronological replay for historical backtesting.

---

## 3. Test Suite & Validation Evidence

### Dedicated Multi-Timeframe Suite (`tests/test_multitimeframe_rule_engine.py`)
Ran 7 dedicated tests in 0.001s:
- `test_sell_setup_m5_sweep_with_m1_confirmation`: **PASS** (Entry = 1.0845, SL = 1.0878, TP = 1.0515, R:R = 10.0).
- `test_buy_setup_m15_sweep_with_m1_confirmation`: **PASS** (Entry = 1.0890, SL = 1.0842, TP = 1.1370, R:R = 10.0).
- `test_disarm_when_direction_breaks_before_3_form`: **PASS** (Immediately disarms on direction break).
- `test_armed_state_expiry_after_15_candles`: **PASS** (Expires after exactly 15 candles).
- `test_resample_m1_to_htf`: **PASS** (Exact OHLCV aggregation into M5 and M15 bars).
- `test_feed_candle_dictionary_interface`: **PASS** (Returns clean dictionary signal upon trigger).
- `test_scan_multitimeframe_streams_integration`: **PASS** (Full multi-stream replay).

### Full Regression Suite
```bash
python -m unittest discover -s tests -v
Ran 137 tests in 3.606s — OK (100% Green, 0 Failures, 0 Errors)
```

---

## 4. Hard Rules Compliance Matrix

| Rule ID | Invariant | Status | Verification Evidence |
|---|---|---|---|
| **HR-1** | Closed Candles Only (Zero Look-Ahead / Intrabar Bias) | COMPLIANT | Evaluates only finalized M1, M5, M15 bars upon bar close. |
| **HR-2** | Strict 10:1 Reward-to-Risk Math | COMPLIANT | Tested with float precision `1e-7`; `take_profit == entry ± (10.0 * stop_distance)`. |
| **HR-3** | Stop-Loss at 3-Candle Extreme | COMPLIANT | Highest high of 3 candles (Sell) / Lowest low of 3 candles (Buy) validated. |
| **HR-4** | Single Codebase Engine Parity | COMPLIANT | Same `RuleEngine` class runs live streaming and historical replay. |
| **HR-5** | Zero Third-Party Dependencies | COMPLIANT | Pure Python standard library (`datetime`, `dataclasses`, `enum`, `typing`). |
| **HR-6** | 15-Candle Armed Expiry & Disarm on Break | COMPLIANT | Tested in `test_armed_state_expiry_after_15_candles` and `test_disarm_when_direction_breaks_before_3_form`. |

---

## 5. Phase Sign-Off & Handoff to Phase 2

Phase 1 has met all technical and trading specifications. The engine is ready for Phase 2 (Backtesting with 3+ years of historical data, spread/slippage modeling, and risk/expectancy analytics).
