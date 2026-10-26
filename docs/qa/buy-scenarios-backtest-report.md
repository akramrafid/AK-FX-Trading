# Backtest Report: 1-Minute Buy Scenarios 1-2

**Generated:** 2026-10-25 21:08 UTC by `scripts/run_buy_scenarios_backtest.py`  
**Strategy:** `BUY_STRATEGY_PROMPT.md` with the Mission Impossible 3-run (trader decisions of 2026-10-26 in `plan.md` §9)  
**Data:** `data/trading.db`, Exness MT4 USDCAD bid bars in UTC: 9,517 1m bars from 2026-10-05 10:48 to 2026-10-23 16:22 over 14 trading days; the broker's own 5m (3,841) and 15m (1,260) bars  
**Execution:** buy at the close of the signal bar plus the spread (a long fills at the ask); exits at the bid; SL and TP in one bar count as SL; no slippage; SL/TP only (no break-even, trailing or partial close)  
**Risk:** 1.0% of balance per trade from $5,000; 1:10 reward:risk; open buys: no limit  
**Session:** 07:00-21:00 UTC, Monday-Friday, on the open time of the signal bar (London, London-NY and NY)  

At 1:10 the break-even win rate is about 9.1% before costs, so long losing streaks are expected.
R is measured on price. The commission column applies the live sizing rule (bridge/sizing.py R4): the $7/lot round-turn commission is part of the 1% risk, so a stop-out still costs 1R and a winner pays less than 10R.

## 1. Buy results by scenario, spread 0.0 pips

| Scenario | Trades | Win rate | Avg R | Net R | Max DD (R) | Max DD (%) | Longest losing streak | Avg SL (pips) | Avg spread % of risk | Net R after $7/lot commission |
|---|---|---|---|---|---|---|---|---|---|---|
| Scenario 1 | 11 | 18.2% | +0.04 | +0.5 | 16.5 | 15.6% | 6 | 2.6 | 0.0% | -1.8 |
| Scenario 2 | 84 | 4.8% | -1.11 | -93.6 | 107.4 | 67.0% | 61 | 3.2 | 0.0% | -94.9 |
| Total | 95 | 6.3% | -0.98 | -93.2 | 109.0 | 67.8% | 53 | 3.1 | 0.0% | -96.7 |
| Total without feed-gap trades | 81 | 6.2% | -0.41 | -33.3 | 44.1 | 36.2% | 44 | 3.0 | 0.0% | -44.8 |

Trades by doji count in the run:

| Scenario | Trades | 0 dojis | 1 doji | 2 dojis |
|---|---|---|---|---|
| Scenario 1 | 11 | 8 | 3 | 0 |
| Scenario 2 | 84 | 64 | 20 | 0 |
| Total | 95 | 72 | 23 | 0 |

14 trade(s) stayed open through a recording gap, so their exit was never observed; together they account for -59.8R, and 1 of the 6 winners are among them. A stop crossed during a gap is filled at the first recorded bar's open, which can be many R beyond the stop (see Caveats).

Journal: `docs/qa/buy-scenarios-journal-spread-0.0.csv`

## 2. Buy results by scenario, spread 0.5 pips

| Scenario | Trades | Win rate | Avg R | Net R | Max DD (R) | Max DD (%) | Longest losing streak | Avg SL (pips) | Avg spread % of risk | Net R after $7/lot commission |
|---|---|---|---|---|---|---|---|---|---|---|
| Scenario 1 | 11 | 9.1% | -0.79 | -8.7 | 15.7 | 14.8% | 7 | 3.1 | 18.1% | -8.5 |
| Scenario 2 | 84 | 3.6% | -1.18 | -98.9 | 107.3 | 66.8% | 67 | 3.7 | 16.3% | -96.6 |
| Total | 95 | 4.2% | -1.13 | -107.6 | 113.0 | 68.9% | 65 | 3.6 | 16.5% | -105.1 |
| Total without feed-gap trades | 81 | 4.9% | -0.55 | -44.6 | 55.1 | 42.5% | 55 | 3.5 | 16.7% | -52.1 |

Trades by doji count in the run:

| Scenario | Trades | 0 dojis | 1 doji | 2 dojis |
|---|---|---|---|---|
| Scenario 1 | 11 | 8 | 3 | 0 |
| Scenario 2 | 84 | 64 | 20 | 0 |
| Total | 95 | 72 | 23 | 0 |

14 trade(s) stayed open through a recording gap, so their exit was never observed; together they account for -62.9R, and 0 of the 4 winners are among them. A stop crossed during a gap is filled at the first recorded bar's open, which can be many R beyond the stop (see Caveats).

Journal: `docs/qa/buy-scenarios-journal-spread-0.5.csv`

## 3. Spread sensitivity (buys, all scenarios)

| Spread (pips) | Trades | Win rate | Net R | Max DD (%) | Net R after commission |
|---|---|---|---|---|---|
| 0.0 | 95 | 6.3% | -93.2 | 67.8% | -96.7 |
| 0.3 | 95 | 5.3% | -99.3 | 68.6% | -100.7 |
| 0.5 | 95 | 4.2% | -107.6 | 68.9% | -105.1 |
| 1.0 | 95 | 3.2% | -113.1 | 70.0% | -109.6 |

## 4. No limit within the buy side (your setting) vs one position (spec default)

| Spread (pips) | Open buys | Trades | Win rate | Net R | Max DD (%) | Net R without feed-gap trades | Skipped: position open |
|---|---|---|---|---|---|---|---|
| 0.0 | no limit | 95 | 6.3% | -93.2 | 67.8% | -33.3 | 0 |
| 0.0 | 1 | 56 | 10.7% | -20.9 | 40.6% | +1.7 | 50 |
| 0.5 | no limit | 95 | 4.2% | -107.6 | 68.9% | -44.6 | 0 |
| 0.5 | 1 | 51 | 7.8% | -35.2 | 40.7% | -4.6 | 55 |

## 5. Sell + buy together (STRATEGY_MODE=ak_scenarios, no hedging)

Sells use their own defaults (entry at the next bar's open, no limit within the side). While one side has a position open, the other side's signals are skipped; a sell and a buy on the same bar would both be skipped (SAME_BAR_CONFLICT).

### Spread 0.0 pips

| Scenario | Trades | Win rate | Avg R | Net R | Max DD (R) | Max DD (%) | Longest losing streak | Avg SL (pips) | Avg spread % of risk | Net R after $7/lot commission |
|---|---|---|---|---|---|---|---|---|---|---|
| Sell alone | 65 | 7.7% | -0.15 | -10.1 | 40.1 | 33.5% | 32 | 3.1 | 0.0% | -25.5 |
| Buy alone | 95 | 6.3% | -0.98 | -93.2 | 109.0 | 67.8% | 53 | 3.1 | 0.0% | -96.7 |
| Sell, with buys | 54 | 7.4% | -0.19 | -10.1 | 36.1 | 30.8% | 30 | 3.1 | 0.0% | -20.1 |
| Buy, with sells | 55 | 5.5% | -1.17 | -64.6 | 72.4 | 53.1% | 37 | 3.1 | 0.0% | -64.1 |
| Sell + buy | 109 | 6.4% | -0.68 | -74.6 | 102.4 | 65.5% | 44 | 3.1 | 0.0% | -84.2 |

Skipped by the no-hedging rule: 18 sell(s) while a buy was open, 51 buy(s) while a sell was open. Same-bar conflicts: 0.

Journal (both sides): `docs/qa/ak-scenarios-journal-spread-0.0.csv`

### Spread 0.5 pips

| Scenario | Trades | Win rate | Avg R | Net R | Max DD (R) | Max DD (%) | Longest losing streak | Avg SL (pips) | Avg spread % of risk | Net R after $7/lot commission |
|---|---|---|---|---|---|---|---|---|---|---|
| Sell alone | 64 | 7.8% | -0.14 | -9.0 | 40.0 | 33.4% | 32 | 3.2 | 20.8% | -24.5 |
| Buy alone | 95 | 4.2% | -1.13 | -107.6 | 113.0 | 68.9% | 65 | 3.6 | 16.5% | -105.1 |
| Sell, with buys | 49 | 6.1% | -0.33 | -16.0 | 33.0 | 28.6% | 30 | 3.2 | 20.6% | -23.2 |
| Buy, with sells | 62 | 3.2% | -1.27 | -78.6 | 81.1 | 56.8% | 50 | 3.6 | 16.5% | -76.3 |
| Sell + buy | 111 | 4.5% | -0.85 | -94.6 | 111.1 | 68.2% | 57 | 3.5 | 18.3% | -99.6 |

Skipped by the no-hedging rule: 23 sell(s) while a buy was open, 43 buy(s) while a sell was open. Same-bar conflicts: 0.

Journal (both sides): `docs/qa/ak-scenarios-journal-spread-0.5.csv`

## 6. Skipped buy signals

| Reason | Spread 0.0 | Spread 0.5 |
|---|---|---|
| FIRST_NOT_LOWEST | 13 | 13 |
| TOO_MANY_DOJIS | 0 | 0 |
| SCENARIO_DISABLED | 0 | 0 |
| OUTSIDE_SESSION | 14 | 14 |
| POSITION_OPEN | 0 | 0 |
| FILL_AT_OR_BELOW_SL | 0 | 0 |
| NO_NEXT_BAR | 0 | 0 |

## 7. Sample buy trades (spread 0.0 pips)

Check these on the chart: X and Y are the HTF pair, conf is when Y closed (the setup arms), the prior run is the bearish run whose low the 1st candle equalled or swept, signal is the bar whose close places the buy. Dates are month-day; the other times are on the same day as the date before them.

| # | Scen. | HTF setup | Times UTC (data feed) | Times UTC+6 (your TradingView) | Entry / SL / TP | Exit |
|---|---|---|---|---|---|---|
| 1 | B2 | M15 SWEEP_LOW (1m EQUAL) | X 10-05 12:00, Y 12:15, conf 12:30; prior run 12:44-12:44; 1st 12:45, signal 12:47; entry 12:48, exit 10-05 12:52 | X 10-05 18:00, Y 18:15, conf 18:30; prior run 18:44-18:44; 1st 18:45, signal 18:47; entry 18:48, exit 10-05 18:52 | 1.42540 / 1.42501 / 1.42930 (3.9 pips) | SL at 1.42501, -1.00R |
| 2 | B2 | M15 SWEEP_LOW (1m EQUAL, doji 2) | X 10-05 12:30, Y 12:45, conf 13:00; prior run 13:06-13:06; 1st 13:07, signal 13:10; entry 13:11, exit 10-05 13:18 | X 10-05 18:30, Y 18:45, conf 19:00; prior run 19:06-19:06; 1st 19:07, signal 19:10; entry 19:11, exit 10-05 19:18 | 1.42554 / 1.42511 / 1.42984 (4.3 pips) | SL at 1.42511, -1.00R |
| 3 | B2 | M15 SWEEP_LOW (1m SWEEP, doji 3) | X 10-05 13:30, Y 13:45, conf 14:00; prior run 14:30-14:31; 1st 14:32, signal 14:34; entry 14:35, exit 10-05 14:42 | X 10-05 19:30, Y 19:45, conf 20:00; prior run 20:30-20:31; 1st 20:32, signal 20:34; entry 20:35, exit 10-05 20:42 | 1.42560 / 1.42535 / 1.42810 (2.5 pips) | SL at 1.42535, -1.00R |
| 4 | B2 | M5 SWEEP_LOW (1m SWEEP) | X 10-05 14:50, Y 14:55, conf 15:00; prior run 15:06-15:07; 1st 15:08, signal 15:10; entry 15:11, exit 10-06 13:03 | X 10-05 20:50, Y 20:55, conf 21:00; prior run 21:06-21:07; 1st 21:08, signal 21:10; entry 21:11, exit 10-06 19:03 | 1.42430 / 1.42369 / 1.43040 (6.1 pips) | SL at 1.42369, -1.00R |
| 5 | B2 | M15 SWEEP_LOW (1m SWEEP, doji 2) | X 10-05 14:45, Y 15:00, conf 15:15; prior run 15:25-15:29; 1st 15:30, signal 15:33; entry 15:34, exit 10-05 15:41 | X 10-05 20:45, Y 21:00, conf 21:15; prior run 21:25-21:29; 1st 21:30, signal 21:33; entry 21:34, exit 10-05 21:41 | 1.42458 / 1.42424 / 1.42798 (3.4 pips) | SL at 1.42424, -1.00R |
| 14 | B1 | M5 EQUAL_LOW (1m SWEEP) | X 10-07 15:55, Y 16:00, conf 16:05; prior run 16:07-16:07; 1st 16:08, signal 16:10; entry 16:11, exit 10-07 16:13 | X 10-07 21:55, Y 22:00, conf 22:05; prior run 22:07-22:07; 1st 22:08, signal 22:10; entry 22:11, exit 10-07 22:13 | 1.42583 / 1.42558 / 1.42833 (2.5 pips) | SL at 1.42558, -1.00R |
| 15 | B1 | M15 EQUAL_LOW (1m SWEEP) | X 10-07 15:45, Y 16:00, conf 16:15; prior run 16:36-16:37; 1st 16:38, signal 16:40; entry 16:41, exit 10-07 16:46 | X 10-07 21:45, Y 22:00, conf 22:15; prior run 22:36-22:37; 1st 22:38, signal 22:40; entry 22:41, exit 10-07 22:46 | 1.42602 / 1.42578 / 1.42842 (2.4 pips) | SL at 1.42578, -1.00R |
| 17 | B1 | M5 EQUAL_LOW (1m EQUAL, doji 3) | X 10-07 19:15, Y 19:20, conf 19:25; prior run 19:29-19:29; 1st 19:30, signal 19:32; entry 19:33, exit 10-07 19:59 | X 10-08 01:15, Y 01:20, conf 01:25; prior run 01:29-01:29; 1st 01:30, signal 01:32; entry 01:33, exit 10-08 01:59 | 1.42583 / 1.42569 / 1.42723 (1.4 pips) | SL at 1.42569, -1.00R |
| 28 | B1 | M5 EQUAL_LOW (1m SWEEP) | X 10-09 06:50, Y 06:55, conf 07:00; prior run 07:02-07:02; 1st 07:03, signal 07:05; entry 07:06, exit 10-09 12:30 | X 10-09 12:50, Y 12:55, conf 13:00; prior run 13:02-13:02; 1st 13:03, signal 13:05; entry 13:06, exit 10-09 18:30 | 1.42195 / 1.42157 / 1.42575 (3.8 pips) | TP at 1.42575, +10.00R |
| 32 | B1 | M5 EQUAL_LOW (1m SWEEP, doji 1) | X 10-09 16:10, Y 16:15, conf 16:20; prior run 16:30-16:30; 1st 16:31, signal 16:33; entry 16:34, exit 10-09 16:36 | X 10-09 22:10, Y 22:15, conf 22:20; prior run 22:30-22:30; 1st 22:31, signal 22:33; entry 22:34, exit 10-09 22:36 | 1.42746 / 1.42729 / 1.42916 (1.7 pips) | SL at 1.42729, -1.00R |

## 8. Caveats

- The history is the Exness MT4 feed, not TradingView FXCM. With exact-price equal lows (no tolerance) an equal low or a 3-run on one feed may not be one on the other, so some trades will not match the FXCM chart. `docs/qa/AK_Buy_Scenarios_TradingView.pine` runs the same rules on the FXCM chart.
- The 1m history was recorded only while the bridge ran, so it has overnight gaps. No 3-run spans a gap longer than 5 minutes. 14 buy trade(s) at spread 0.0 stayed open through a gap: their exit is the first recorded bar after it. They are marked `held_through_feed_gap` and left out of the "without feed-gap trades" rows.
- A buy is skipped when the bid at the fill is at or below the SL (FILL_AT_OR_BELOW_SL): MT4 rejects such a stop. With the signal-close fill the 1st candle is the run's lowest, so this cannot happen at spread 0.
- 1 buy trade(s) at spread 0.0 were still open at the end of the data and are closed at the last bid (END_OF_DATA, fractional R).
- The live daily loss circuit breaker (MAX_DAILY_LOSS_PCT) is not simulated here; it can only stop trades.
- No spread history is stored, so spread is a constant per run; the sensitivity table shows its effect.
- 14 trading days is a small sample: treat per-scenario figures as anecdotal.
