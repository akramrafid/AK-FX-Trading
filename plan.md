# AK Forex Trading — Plan

> Filled in once, at bootstrap (`PROMPT_LIBRARY.md` §1 or `akstack init`).
> Revised only via the cross-cutting change prompt (`PROMPT_LIBRARY.md` §6.3) — never edited silently mid-build.

## 0. Track

**Hybrid** — combines deterministic core algorithmic backend rule engine, risk guardrails, MT4 file bridge, and PostgreSQL trade journaling with a future Phase 8 ML/RL trade management optimization layer.

## 1. What & Why

A production-grade automated algorithmic Forex trading system executing a proprietary wick-sweep and 3-candle confirmation breakout strategy with a fixed 10:1 reward-to-risk (R:R) ratio directly on a MetaTrader 4 (MT4) account. The system eliminates emotional execution, removes manual order placement, enforces non-negotiable risk guardrails, and guarantees mathematical parity between historical backtesting, demo forward-testing, and live market execution.

- **Primary user outcome:** Fully automated, rules-based execution of high-R:R Forex trades on MT4 without intrabar latency chasing or manual intervention, safeguarded by strict capital preservation controls.
- **Commercial model:** Prop-firm / private account capital compounding; maximizing expectancy per unit of risk through strict adherence to positive expectancy (10:1 R:R) and low drawdown.
- **Acquisition surfaces:** Internal execution system; desktop/VPS headless background runtime with local or web status dashboard.
- **North-star metric:** Realized Sharpe ratio and profit factor across >= 300 executed trades with divergence between backtest, demo, and live execution kept under 5%.

## 2. Users & Roles

| Role | Can do | Cannot do |
|---|---|---|
| **Trader / Operator** | Review performance, configure pair list, adjust risk % within allowed range, trigger emergency kill-switch | Cannot override active trade stop-losses mid-flight or bypass daily loss limit |
| **System Engine (Autonomous)** | Evaluate closed candles, compute position sizing, generate orders, log fills & slippage | Cannot exceed risk limits, cannot trade intrabar, cannot place orders without valid SL/TP |

## 3. Domain & Hard Rules

**The most critical section in the file.** Financial market automation carries catastrophic downside if invariants are violated.

1. **Closed Candles Only (Zero Look-Ahead / Intrabar Bias):** The rule engine evaluates signals and places orders ONLY upon new-bar confirmation after a candle has closed. Never evaluate or trigger on live/intrabar ticks.
2. **Single Codebase Rule Engine Parity:** The exact same Python rule engine class/functions must execute historical backtesting, demo polling, and live trading. No parallel backtest-only or live-only logic.
3. **Dynamic Position Sizing & Hard Sanity Clamping:** Lot sizes MUST be calculated dynamically per trade:
   `lot_size = (account_balance × risk_%) / (stop_loss_distance_in_pips × pip_value_per_lot)`
   Hard sanity bounds (e.g. min 0.01 lot, max broker lot limit, absolute max lot clamp) must wrap this formula so sizing bugs can never multiply exposure. Hard-coded lot sizes are strictly forbidden.
4. **Non-Bypassable Risk Guardrails Layer:** The risk engine sits between the rule engine and the order execution bridge.
   - Max risk per trade: fixed % (e.g., 1.0% or 0.5%) of current balance.
   - Daily loss circuit breaker: if cumulative daily realized + unrealized loss hits threshold (e.g., 3-4%), trading is halted for the rest of the 24h trading day.
   - Max concurrent open positions limit.
   - This layer can NEVER be bypassed or relaxed by any rule engine update or future ML/RL model.
5. **Fixed 10:1 Reward-to-Risk & Asymmetrical Stop-Loss Placement:**
   - Long trades: Stop-loss sits just below the low of the first candle in the 3-candle confirmation sequence (`SL = candle_1.low - buffer`).
   - Short trades: Stop-loss sits just above the high of the first candle in the 3-candle confirmation sequence (`SL = candle_1.high + spread + buffer`).
   - Take-profit: Strictly fixed at 10x the stop-loss distance (`TP = entry ± 10 × stop_distance`).
6. **Execution Timeframe Invariant (5-Minute / M5):** Strategy rules, bar close events, and historical data testing operate on the M5 timeframe.
7. **3 Consecutive Candles Confirmation Test:** Following a qualifying sweep candle (Variant A candle-to-candle or Variant B swing-level), the subsequent 3 closed candles must all close in the trade's direction (3 consecutive bullish/green candles for Long, 3 consecutive bearish/red candles for Short).
8. **Order Idempotency & Magic Numbers:** Every generated order must carry a unique timestamp-derived deterministic magic number/idempotency key. The execution bridge must verify whether an order for the current closed bar has already been dispatched before writing an execution command to prevent duplicate orders during network lag or EA polling delays.
9. **Comprehensive Trade Journaling from Day 1:** Every detected sweep signal, confirmation status, rejected order (due to risk limits), theoretical entry, actual fill price, slippage in pips, and final trade outcome must be permanently logged to PostgreSQL.

## 4. Architecture & Stack

- **Rule Engine & Backtester:** Pure Python 3.11+, NumPy, Pandas. Deterministic event-driven bar-by-bar walk.
- **Historical Data Pipeline:** Dukascopy / broker M5 OHLC CSV data parser with realistic bid/ask spread and tick slippage simulation.
- **Execution Bridge:** DWX Connect (`darwinex/dwxconnect`) file-based interface between Python and MT4 Expert Advisor (EA), requiring zero external C-extensions or ZeroMQ binaries.
- **Risk Guardrails:** Independent Python module (`risk/risk_guardrails.py`) intercepting every signal before bridge dispatch.
- **Database & Logging:** PostgreSQL (asyncpg / SQLAlchemy) storing candles, signals, execution events, fills, slippage, and PnL metrics.
- **Future ML/RL Layer (Phase 8):** Post-live enhancement trained on logged PostgreSQL execution data for session-based confidence scoring and dynamic trade management.
- **Hosting/Infra:** Windows VPS / Local dedicated trading environment with watchdog process supervision.

## 5. Data & Storage Invariants

- **Pip Calculations:** Quote currency precision handled explicitly (0.0001 for 4/5-digit pairs, 0.01 for JPY pairs).
- **Timezone Invariant:** All candle timestamps, signal logs, and order events stored strictly in UTC.
- **Auditability:** Append-only event log for every state transition: `SIGNAL_DETECTED`, `RISK_VALIDATED`, `ORDER_DISPATCHED`, `ORDER_FILLED`, `ORDER_CLOSED`.

## 6. Service Level Objectives (SLOs) & Performance Budget

- **Signal Evaluation Latency:** < 50ms from candle close event file receipt to order command write.
- **Bridge File Polling Interval:** EA poll rate <= 250ms on new bar open.
- **Max Drawdown Budget:** < 10% peak-to-trough before mandatory halt.
- **Execution Parity:** Live slippage monitored against backtest simulated slippage; alert triggered if median slippage exceeds 1.5 pips.

## 7. Phases & Milestones

Aligned with the user specification:
- **Phase 0:** Requirements & Strategy Ambiguity Resolution (Completed).
- **Phase 1:** Deterministic Rule Engine (`engine/rule_engine.py`, closed candle pattern detection).
- **Phase 2:** Backtest Engine (3+ years historical data, spread/slippage modeling, performance metrics).
- **Phase 3:** MT4 Execution Bridge (DWX Connect EA + file-watcher + dynamic lot sizing).
- **Phase 4:** Risk Guardrails & Circuit Breaker (loss limits, position caps, sanity clamps).
- **Phase 5:** PostgreSQL Logging & Trade Journal (signal and fill telemetry).
- **Phase 6:** Demo Account Forward Testing (several weeks execution parity check).
- **Phase 7:** Live Rollout (micro-lot initial deployment, phased scaling).
- **Phase 8:** Optional ML/RL Layer (trained on PostgreSQL logged live distribution).

## 8. Non-Goals

- No intrabar / tick scalping.
- No limit orders at candle close (market orders only upon confirmed bar close).
- No manual trading override through the automated EA magic number.
- No third-party proprietary black-box signals.
- No scaling of live position sizes while backtest, demo, and live metrics diverge.

## 9. Strategy Decisions & Invariants (Resolved with Trader)

1. **Short-Side Stop-Loss Rule:**
   - *Decision:* Confirmed. For short setups, Stop-Loss sits just above the first candle's high (+ spread/buffer).
2. **Operational Timeframe:**
   - *Decision:* Confirmed. 5-Minute (M5) candle sweep and execution.
3. **"3 Consecutive Candles" Confirmation Exact Definition:**
   - *Decision:* Confirmed. Candle Color/Direction only: all 3 confirmation candles must close strictly in the trade direction (3 bullish/green for long, 3 bearish/red for short).
