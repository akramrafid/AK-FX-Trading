# Backtest Report: 1-Minute Sell Scenarios 1-4

**Generated:** 2026-10-25 19:45 UTC by `scripts/run_sell_scenarios_backtest.py`  
**Strategy:** `SELL_STRATEGY_PROMPT.md` (trader decisions of 2026-10-25 in `plan.md` §9)  
**Data:** `data/trading.db`, Exness MT4 USDCAD bid bars in UTC: 9,517 1m bars from 2026-10-05 10:48 to 2026-10-23 16:22 over 14 trading days; the broker's own 5m (3,841) and 15m (1,260) bars  
**Execution:** entry at the next 1m bar open; a short closes at the ask (bid + constant spread); SL and TP in one bar count as SL; no slippage; SL/TP only (no break-even, trailing or partial close)  
**Risk:** 1.0% of balance per trade from $5,000; 1:10 reward:risk; open positions: no limit  
**Session:** 07:00-21:00 UTC, Monday-Friday, on the open time of B3 (London, London-NY and NY)  

At 1:10 the break-even win rate is about 9.1% before costs, so long losing streaks are expected.
R is measured on price. The commission column applies the live sizing rule (bridge/sizing.py R4): the $7/lot round-turn commission is part of the 1% risk, so a stop-out still costs 1R and a winner pays less than 10R.

## 1. Results by scenario, spread 0.0 pips

| Scenario | Trades | Win rate | Avg R | Net R | Max DD (R) | Max DD (%) | Longest losing streak | Avg SL (pips) | Avg spread % of risk | Net R after $7/lot commission |
|---|---|---|---|---|---|---|---|---|---|---|
| Scenario 1 | 7 | 0.0% | -1.00 | -7.0 | 7.0 | 6.8% | 7 | 2.7 | 0.0% | -7.0 |
| Scenario 2 | 45 | 6.7% | -0.27 | -12.1 | 29.1 | 25.7% | 23 | 3.5 | 0.0% | -19.3 |
| Scenario 3 | 2 | 0.0% | -1.00 | -2.0 | 2.0 | 2.0% | 2 | 2.0 | 0.0% | -2.0 |
| Scenario 4 | 11 | 18.2% | +1.00 | +11.0 | 8.0 | 7.7% | 8 | 2.1 | 0.0% | +2.8 |
| Total | 65 | 7.7% | -0.15 | -10.1 | 40.1 | 33.5% | 32 | 3.1 | 0.0% | -25.5 |
| Total without feed-gap trades | 56 | 3.6% | -0.61 | -34.1 | 48.1 | 38.3% | 48 | 2.9 | 0.0% | -40.1 |

9 trade(s) stayed open through a recording gap, so their exit was never observed; 3 of the 5 winners are among them (see Caveats).

Journal: `docs/qa/sell-scenarios-journal-spread-0.0.csv`

## 2. Results by scenario, spread 0.5 pips

| Scenario | Trades | Win rate | Avg R | Net R | Max DD (R) | Max DD (%) | Longest losing streak | Avg SL (pips) | Avg spread % of risk | Net R after $7/lot commission |
|---|---|---|---|---|---|---|---|---|---|---|
| Scenario 1 | 7 | 0.0% | -1.00 | -7.0 | 7.0 | 6.8% | 7 | 2.7 | 21.5% | -7.0 |
| Scenario 2 | 45 | 6.7% | -0.27 | -12.0 | 29.0 | 25.7% | 23 | 3.5 | 17.8% | -19.2 |
| Scenario 3 | 2 | 0.0% | -1.00 | -2.0 | 2.0 | 2.0% | 2 | 2.0 | 27.1% | -2.0 |
| Scenario 4 | 10 | 20.0% | +1.20 | +12.0 | 7.0 | 6.8% | 7 | 2.3 | 32.2% | +3.8 |
| Total | 64 | 7.8% | -0.14 | -9.0 | 40.0 | 33.4% | 32 | 3.2 | 20.8% | -24.5 |
| Total without feed-gap trades | 55 | 3.6% | -0.60 | -33.0 | 48.0 | 38.3% | 48 | 2.9 | 21.7% | -39.1 |

9 trade(s) stayed open through a recording gap, so their exit was never observed; 3 of the 5 winners are among them (see Caveats).

Journal: `docs/qa/sell-scenarios-journal-spread-0.5.csv`

## 3. Spread sensitivity (all scenarios)

| Spread (pips) | Trades | Win rate | Net R | Max DD (%) | Net R after commission |
|---|---|---|---|---|---|
| 0.0 | 65 | 7.7% | -10.1 | 33.5% | -25.5 |
| 0.3 | 64 | 7.8% | -9.2 | 33.6% | -24.6 |
| 0.5 | 64 | 7.8% | -9.0 | 33.4% | -24.5 |
| 1.0 | 62 | 3.2% | -40.0 | 38.0% | -43.9 |

## 4. No position limit (your setting) vs one position at a time (spec default)

| Spread (pips) | Open positions | Trades | Win rate | Net R | Max DD (%) | Net R without feed-gap trades | Skipped: position open |
|---|---|---|---|---|---|---|---|
| 0.0 | no limit | 65 | 7.7% | -10.1 | 33.5% | -34.1 | 0 |
| 0.0 | 1 | 31 | 12.9% | +12.9 | 10.5% | -15.1 | 42 |
| 0.5 | no limit | 64 | 7.8% | -9.0 | 33.4% | -33.0 | 0 |
| 0.5 | 1 | 32 | 12.5% | +12.0 | 12.2% | -16.0 | 39 |

## 5. Skipped signals

| Reason | Spread 0.0 | Spread 0.5 |
|---|---|---|
| SCENARIO_DISABLED | 0 | 0 |
| OUTSIDE_SESSION | 7 | 7 |
| POSITION_OPEN | 0 | 0 |
| FILL_AT_OR_ABOVE_SL | 0 | 1 |
| NO_NEXT_BAR | 0 | 0 |

## 6. Sample trades (spread 0.0 pips)

Check these on the chart: X and Y are the HTF pair, conf is when Y closed (the setup arms), A-B3 are the 1m candles and entry is the next bar's open. Dates are month-day.

| # | Scen. | HTF setup | Times UTC (data feed) | Times UTC+6 (your TradingView) | Entry / SL / TP | Exit |
|---|---|---|---|---|---|---|
| 1 | S4 | M5 WICK_SWEEP (1m WICK_SWEEP, doji B3) | X 10-05 13:05, Y 10-05 13:10, conf 10-05 13:15; A 10-05 13:15, B1 10-05 13:16, B2 10-05 13:17, B3 10-05 13:18; entry 10-05 13:19, exit 10-05 13:22 | X 10-05 19:05, Y 10-05 19:10, conf 10-05 19:15; A 10-05 19:15, B1 10-05 19:16, B2 10-05 19:17, B3 10-05 19:18; entry 10-05 19:19, exit 10-05 19:22 | 1.42512 / 1.42554 / 1.42092 (4.2 pips) | SL at 1.42554, -1.00R |
| 2 | S2 | M15 WICK_SWEEP (1m WICK_SWEEP) | X 10-05 13:45, Y 10-05 14:00, conf 10-05 14:15; A 10-05 14:42, B1 10-05 14:43, B2 10-05 14:44, B3 10-05 14:45; entry 10-05 14:46, exit 10-05 16:35 | X 10-05 19:45, Y 10-05 20:00, conf 10-05 20:15; A 10-05 20:42, B1 10-05 20:43, B2 10-05 20:44, B3 10-05 20:45; entry 10-05 20:46, exit 10-05 22:35 | 1.42522 / 1.42560 / 1.42142 (3.8 pips) | SL at 1.42560, -1.00R |
| 3 | S4 | M15 WICK_SWEEP (1m EQUAL_TOP, doji B2) | X 10-05 16:15, Y 10-05 16:30, conf 10-05 16:45; A 10-05 17:25, B1 10-05 17:26, B2 10-05 17:27, B3 10-05 17:28; entry 10-05 17:29, exit 10-05 17:29 | X 10-05 22:15, Y 10-05 22:30, conf 10-05 22:45; A 10-05 23:25, B1 10-05 23:26, B2 10-05 23:27, B3 10-05 23:28; entry 10-05 23:29, exit 10-05 23:29 | 1.42552 / 1.42553 / 1.42542 (0.1 pips) | SL at 1.42553, -1.00R |
| 4 | S2 | M5 WICK_SWEEP (1m WICK_SWEEP) | X 10-06 10:40, Y 10-06 10:45, conf 10-06 10:50; A 10-06 10:57, B1 10-06 10:58, B2 10-06 10:59, B3 10-06 11:00; entry 10-06 11:01, exit 10-06 11:40 | X 10-06 16:40, Y 10-06 16:45, conf 10-06 16:50; A 10-06 16:57, B1 10-06 16:58, B2 10-06 16:59, B3 10-06 17:00; entry 10-06 17:01, exit 10-06 17:40 | 1.42737 / 1.42759 / 1.42517 (2.2 pips) | TP at 1.42517, +10.00R |
| 5 | S2 | M15 WICK_SWEEP (1m WICK_SWEEP) | X 10-06 10:30, Y 10-06 10:45, conf 10-06 11:00; A 10-06 11:36, B1 10-06 11:37, B2 10-06 11:38, B3 10-06 11:39; entry 10-06 11:40, exit 10-07 12:19 | X 10-06 16:30, Y 10-06 16:45, conf 10-06 17:00; A 10-06 17:36, B1 10-06 17:37, B2 10-06 17:38, B3 10-06 17:39; entry 10-06 17:40, exit 10-07 18:19 | 1.42531 / 1.42575 / 1.42091 (4.4 pips) | SL at 1.42575, -1.00R |
| 7 | S1 | M5 EQUAL_TOP (1m WICK_SWEEP) | X 10-06 12:30, Y 10-06 12:35, conf 10-06 12:40; A 10-06 12:44, B1 10-06 12:45, B2 10-06 12:46, B3 10-06 12:47; entry 10-06 12:48, exit 10-07 11:55 | X 10-06 18:30, Y 10-06 18:35, conf 10-06 18:40; A 10-06 18:44, B1 10-06 18:45, B2 10-06 18:46, B3 10-06 18:47; entry 10-06 18:48, exit 10-07 17:55 | 1.42436 / 1.42489 / 1.41906 (5.3 pips) | SL at 1.42489, -1.00R |
| 16 | S1 | M15 EQUAL_TOP (1m EQUAL_TOP) | X 10-08 09:00, Y 10-08 09:15, conf 10-08 09:30; A 10-08 09:50, B1 10-08 09:51, B2 10-08 09:52, B3 10-08 09:53; entry 10-08 09:54, exit 10-08 10:05 | X 10-08 15:00, Y 10-08 15:15, conf 10-08 15:30; A 10-08 15:50, B1 10-08 15:51, B2 10-08 15:52, B3 10-08 15:53; entry 10-08 15:54, exit 10-08 16:05 | 1.42624 / 1.42647 / 1.42394 (2.3 pips) | SL at 1.42647, -1.00R |
| 25 | S1 | M15 EQUAL_TOP (1m EQUAL_TOP) | X 10-09 09:00, Y 10-09 09:15, conf 10-09 09:30; A 10-09 09:59, B1 10-09 10:00, B2 10-09 10:01, B3 10-09 10:02; entry 10-09 10:03, exit 10-09 10:14 | X 10-09 15:00, Y 10-09 15:15, conf 10-09 15:30; A 10-09 15:59, B1 10-09 16:00, B2 10-09 16:01, B3 10-09 16:02; entry 10-09 16:03, exit 10-09 16:14 | 1.42271 / 1.42290 / 1.42081 (1.9 pips) | SL at 1.42290, -1.00R |
| 48 | S3 | M15 EQUAL_TOP (1m WICK_SWEEP, doji B1) | X 10-20 09:45, Y 10-20 10:00, conf 10-20 10:15; A 10-20 10:32, B1 10-20 10:33, B2 10-20 10:34, B3 10-20 10:35; entry 10-20 10:36, exit 10-20 11:55 | X 10-20 15:45, Y 10-20 16:00, conf 10-20 16:15; A 10-20 16:32, B1 10-20 16:33, B2 10-20 16:34, B3 10-20 16:35; entry 10-20 16:36, exit 10-20 17:55 | 1.40535 / 1.40549 / 1.40395 (1.4 pips) | SL at 1.40549, -1.00R |
| 49 | S3 | M15 EQUAL_TOP (1m WICK_SWEEP, doji B3) | X 10-20 10:45, Y 10-20 11:00, conf 10-20 11:15; A 10-20 11:44, B1 10-20 11:45, B2 10-20 11:46, B3 10-20 11:47; entry 10-20 11:48, exit 10-20 11:52 | X 10-20 16:45, Y 10-20 17:00, conf 10-20 17:15; A 10-20 17:44, B1 10-20 17:45, B2 10-20 17:46, B3 10-20 17:47; entry 10-20 17:48, exit 10-20 17:52 | 1.40501 / 1.40528 / 1.40231 (2.7 pips) | SL at 1.40528, -1.00R |

## 7. Caveats

- The history is the Exness MT4 feed, not TradingView FXCM. With zero equal-top tolerance an equal top on one feed may not be one on the other, so a few trades will not match the FXCM chart exactly. `docs/qa/AK_Sell_Scenarios_TradingView.pine` runs the same rules on the FXCM chart.
- The 1m history was recorded only while the bridge ran, so it has overnight gaps. No 1m sequence spans a gap longer than 5 minutes, and no fill is simulated across one. 9 trade(s) at spread 0.0 stayed open through a gap: their exit is the first recorded bar after it, at the SL/TP level (or the bar's open when it opened through the SL). They are marked `held_through_feed_gap` in the journal and left out of the "without feed-gap trades" rows.
- A sell is skipped when the ask at the fill is already at or above the SL (FILL_AT_OR_ABOVE_SL): MT4 rejects such a stop. With spread 0 this is the spec's "fill at or above SL" rule.
- 0 trade(s) at spread 0.0 were still open at the end of the data and are closed at the last ask (END_OF_DATA, fractional R).
- No spread history is stored, so spread is a constant per run; the sensitivity table shows its effect.
- 14 trading days is a small sample: treat per-scenario figures as anecdotal.
