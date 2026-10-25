# Claude Code Prompt — 1-Minute Sell Strategy (Scenarios 1–4)

**Attach both TradingView screenshots with this prompt:** "Scenario 1 & 2" and "Scenario 3 & 4" (USDCAD, FXCM, 1m chart).
The screenshots show the *shape* of each pattern. This document gives the *exact rules, parameters, algorithm and tests*. If the two ever seem to disagree, stop and ask me.

---

## 0. Your role and working method

You are a senior software engineer with 30 years of experience, working with a senior hedge-fund trader with 30 years of experience. The trader's strategy below is final. Your job is to implement it **exactly** inside the existing codebase — no reinterpretation, no extra filters, no "improvements".

Work in three steps:

1. **Explore first (read-only).** Find: language/platform; how 1m candles are loaded; how higher timeframes are built; the strategy interface/registry; the backtester; order and position management; spread/slippage model; config system; logging / trade journal; time-zone handling; test framework.
   Look specifically for an existing TradingView strategy named **"AK Strategy Backtester (Strict Compliance)"** — it is loaded on the chart in the screenshots with inputs `10 1 2 15 0 0700-1800:23456`. If it is in this repo, it is the integration target. Verify what each input means in code; do not guess.
2. **Report before editing.** Send me: (a) the four scenarios restated in your own words, (b) the files you will add or change, (c) how each parameter in §7 maps onto the existing config, (d) any conflict between this spec and the codebase. **Wait for my "go".**
3. **Implement → test → backtest → report** (§11 and §12).

Rules of engagement:
- Do not change other strategies, existing defaults, session/day filters, or the risk model unless this document says so.
- Every value marked **ASSUMPTION** in §7 must be a config parameter with the stated default.
- If something is not covered here, ask. Do not invent rules.

---

## 1. How to read the screenshots

- **Blue candle** = bullish (close > open). **Black candle** = bearish (close < open). **"+" shape** = indecisive candle / doji (no body).
- The candles are hand-drawn schematics, not real prices.
- In every scenario panel, the **top drawing** is the higher-timeframe (HTF) condition on **5m or 15m**. The **two lower drawings** are the two accepted **1-minute** entry patterns:
  - left = **equal top** + 3 consecutive bearish candles
  - right = **bullish candle's wick swept by a bearish candle's wick** + 3 consecutive bearish candles
  Either 1m pattern is valid in every scenario.
- **Grey box** = risk zone of TradingView's short-position tool (entry → stop loss). **Light-blue box** = reward zone (entry → take profit). The grey/blue boundary is the entry = close of the third bearish candle. The top of the grey box sits just above the high of the **first** of the three bearish candles.
- The trader writes "wick **swap**" — read it as **wick sweep**: a wick that takes out the previous candle's high, after which the candle closes back below that high.
- In the second screenshot the text boxes under Scenario 3 and Scenario 4 are headed "scenario 1" and "scenario 2". That is a copy-paste label. They describe Scenario 3 and Scenario 4; the only new sentence in them is the indecisive-candle rule.
- The "Asian Session Range" indicator on the chart is **not** part of this strategy. Ignore it.

---

## 2. Trader's briefing — the rules as written

(The trader's own words; only spelling fixed.)

**Scenario 1**
1. Look for an Equal Top in the 5 or 15 minute timeframe.
2. Then move to the 1 minute timeframe.
3. In 1 minute, look for an equal top **or** a bullish candle's wick swept by a bearish candle's wick.
4. Make sure 3 consecutive bearish candles form in 1 minute. After the third bearish candle closes, instantly place the sell. Stop loss goes above the first consecutive candle.
Risk : Reward must be 1 : 10.

**Scenario 2** — identical to Scenario 1 except step 1: look for a **bullish candle's wick swept by a bearish candle's wick** in the 5 or 15 minute timeframe.

**Scenario 3** — Scenario 1 plus: "This is an indecisive candle. It has no body. Most importantly, it can form in any of the 3 consecutive candles — make sure the setup is still valid."

**Scenario 4** — Scenario 2 plus the same indecisive-candle rule.

**Trader's summary:** it is one mechanical 1m trigger. Scenarios 1/3 and 2/4 differ only in the HTF pattern. Scenarios 3/4 allow one no-body candle inside the three consecutive candles.

---

## 3. Exact definitions

Convert every price to integer **points** before comparing: `pts(p) = round(p / point_size)`. USDCAD: point = 0.00001, pip = 0.0001 = 10 points. Never compare raw floats.

### 3.1 Candle kind (evaluate in this order)
1. `DOJI` if `|close − open| ≤ DOJI_BODY_TOL` (default 0 → open == close). Wicks are not required.
2. `BULL` if `close > open`
3. `BEAR` if `close < open`

A doji is never counted as bullish or bearish.

### 3.2 Two-candle top pattern — `top_pattern(X, Y, tol)`
X and Y are **adjacent, closed** candles on the same timeframe. X must be `BULL`.
- `EQUAL_TOP` — `|high(Y) − high(X)| ≤ tol`
- `WICK_SWEEP` — `high(Y) > high(X) + tol` **and** `open(Y) ≤ high(X)` **and** `close(Y) < high(X)`
  (only Y's upper wick went above X's high, and Y closed back below it)
- otherwise `NONE`

The two results are mutually exclusive.

```
 EQUAL_TOP                          WICK_SWEEP
   |  |   <- same high                   |   <- Y's wick above X's high
  [X] #                               |  |
  [X] #                              [X] #
   |  #                              [X] #
      |                               |  #
                                         |
 [X] = bullish (blue)      # = bearish (black)
```

### 3.3 HTF pattern (5m or 15m)
`X` = a bullish HTF candle, `Y` = the next HTF candle, which must be `BEAR`. Both closed.
- Scenarios 1 and 3 require `top_pattern(X, Y, HTF_EQ_TOL) = EQUAL_TOP`.
- Scenarios 2 and 4 require `top_pattern(X, Y, HTF_EQ_TOL) = WICK_SWEEP`.

### 3.4 1-minute entry sequence — `A, B1, B2, B3`
Four adjacent, closed 1m candles:
- `A` is `BULL`.
- `top_pattern(A, B1, LTF_EQ_TOL)` is `EQUAL_TOP` or `WICK_SWEEP` (both accepted in all four scenarios).
- `B1, B2, B3` are "the 3 consecutive candles":
  - no doji, every one `BEAR` → labelled Scenario 1 or 2
  - 1 to `MAX_DOJI_IN_SEQUENCE` dojis, all others `BEAR` → labelled Scenario 3 or 4. The doji may be B1, B2 or B3. If B1 is the doji, its upper wick must still form the equal top / sweep with A.
  - any `BULL` among B1–B3 → no setup
- `B1` stays the highest of the three: `high(B2) ≤ high(B1)` and `high(B3) ≤ high(B1)` (ASSUMPTION `B1_MUST_BE_HIGHEST`).

```
  A    B1   B2   B3
  |    |                       <- SL = high(B1) + SL_BUFFER
 [A]   #    |
 [A]   #    #
  |    #    #    |
       |    #    #
            |    #             <- SELL immediately after B3 closes
                 |
       TP = entry − 10 × (SL − entry)
```

---

## 4. Scenario matrix

| Scenario | HTF pattern (5m **or** 15m) | 1m pattern (A, B1) | B1–B3 |
|---|---|---|---|
| 1 | EQUAL_TOP | EQUAL_TOP or WICK_SWEEP | 3 bearish, no doji |
| 2 | WICK_SWEEP | EQUAL_TOP or WICK_SWEEP | 3 bearish, no doji |
| 3 | EQUAL_TOP | EQUAL_TOP or WICK_SWEEP | bearish + one doji in any position |
| 4 | WICK_SWEEP | EQUAL_TOP or WICK_SWEEP | bearish + one doji in any position |

Entry, stop loss and take profit are identical in all four. Every trade gets exactly one scenario label.

---

## 5. Linking the HTF to the 1m chart (no look-ahead)

1. Build 5m and 15m candles from 1m data (or use native HTF data if the codebase has it), clock-aligned — 5m on :00, :05 …; 15m on :00, :15, :30, :45 — in the data feed's time zone, matching TradingView FXCM.
2. Scan every timeframe in `HTF_TIMEFRAMES` independently. A pattern on either 5m or 15m is enough ("5 **or** 15").
3. An HTF pattern exists only after `Y` has **closed**: `t_conf = close_time(Y)`. Never use a forming HTF candle.
4. On confirmation, create an armed setup:
   `{id, tf, type, X, Y, setup_high = max(high(X), high(Y)), t_conf, t_exp = t_conf + HTF_SETUP_EXPIRY_BARS × tf}`
5. A 1m sequence may use an armed setup only if `open_time(A) ≥ t_conf` and `close_time(B3) ≤ t_exp` — the whole 1m pattern forms after the HTF pattern is confirmed and before it expires.
6. Optional (ASSUMPTION, default OFF): cancel the setup if any 1m candle closes above `setup_high` before an entry.
7. One trade per setup (`MAX_TRADES_PER_SETUP = 1`); the setup is then consumed.
8. If several armed setups match the same 1m sequence: take one trade only. Label it from the 15m setup before the 5m one; on a tie, the most recent `t_conf`. Log every matching setup id.
9. The 1m pattern does **not** have to sit at the HTF high — the screenshots don't require it. Optional proximity filter `LTF_NEAR_HTF_HIGH_PIPS`, default OFF.

---

## 6. Orders and trade management

- **SELL only.** No long logic.
- **Trigger:** confirmed close of B3.
- **Entry:** live — market sell the moment B3 closes. Backtest — fill at the open of the next 1m bar (`ENTRY_FILL = next_bar_open`; the alternative `b3_close` is the same as Pine's `process_orders_on_close = true`). Apply the codebase's existing spread/slippage model.
- **Stop loss:** `SL = high(B1) + SL_BUFFER` (default 1 point, i.e. strictly above B1's high). Fixed price, sent with the order, never moved.
- **Take profit:** `TP = entry_fill − RR × (SL − entry_fill)` with `RR = 10`. Compute from the actual fill so realised risk:reward is exactly 1:10.
- **Exits:** SL or TP only. No break-even, trailing stop, partial close, time exit or reverse-signal exit — none of these are in the strategy.
- **Short-side pricing:** a short is closed at the ask. With bid OHLC data, SL is hit when `bid_high + spread ≥ SL` and TP when `bid_low + spread ≤ TP`. Use the existing spread model; if there is none, say so in your report.
- **SL and TP touched in the same 1m bar:** count it as SL first (conservative) unless tick data is available.
- **Position size:** use the existing risk model; if there is none, risk `RISK_PER_TRADE_PCT` of equity over the SL distance.
- **Concurrency:** `MAX_OPEN_POSITIONS = 1`. A signal while a position is open is logged as skipped.
- **Session / day filters:** keep whatever the codebase already has (the existing backtester in the screenshot shows `0700-1800`, Monday–Friday). Add none.
- If `SL − entry_fill ≤ 0` (fill at or above SL), skip the trade and log it.

---

## 7. Parameters (trader–engineer review decisions)

"Image" = stated in the screenshots, fixed. "ASSUMPTION" = the screenshots don't say; this default was chosen and must stay configurable.

| Parameter | Default | Source | Meaning |
|---|---|---|---|
| `ENABLED_SCENARIOS` | `[1, 2, 3, 4]` | Image | Scenario labels allowed to trade |
| `SIDE` | `SELL` | Image | Sell-only strategy |
| `HTF_TIMEFRAMES` | `[5m, 15m]` | Image | "5 or 15 minute" |
| `LTF_TIMEFRAME` | `1m` | Image | Entry chart |
| `CONSECUTIVE_CANDLES` | `3` | Image | B1, B2, B3 |
| `RR` | `10` | Image | TP = 10 × risk |
| `HTF_EQ_TOL_PIPS` | `0.0` | ASSUMPTION | 0 = HTF highs exactly equal |
| `LTF_EQ_TOL_PIPS` | `0.0` | ASSUMPTION | 0 = 1m highs exactly equal |
| `DOJI_BODY_TOL_PIPS` | `0.0` | ASSUMPTION | 0 = open == close ("no body") |
| `MAX_DOJI_IN_SEQUENCE` | `1` | ASSUMPTION | The image says "an" indecisive candle |
| `SL_BUFFER_POINTS` | `1` | ASSUMPTION | "Above" B1's high = 1 point above |
| `B1_MUST_BE_HIGHEST` | `true` | ASSUMPTION | B2/B3 may not exceed B1's high |
| `HTF_SETUP_EXPIRY_BARS` | `3` | ASSUMPTION | Setup stays armed for 3 HTF candles after confirmation |
| `INVALIDATE_ON_CLOSE_ABOVE_HTF_HIGH` | `false` | ASSUMPTION | Optional cancel rule |
| `LTF_NEAR_HTF_HIGH_PIPS` | `off` | ASSUMPTION | Optional proximity filter |
| `MAX_TRADES_PER_SETUP` | `1` | ASSUMPTION | One trade per HTF setup |
| `MAX_OPEN_POSITIONS` | `1` | ASSUMPTION | One position at a time |
| `ENTRY_FILL` | `next_bar_open` | ASSUMPTION | Alternative: `b3_close` |
| `SAME_BAR_SL_TP` | `SL_FIRST` | ASSUMPTION | Conservative bar-data rule |
| `RISK_PER_TRADE_PCT` | existing model, else `1.0` | ASSUMPTION | Only if the codebase has no risk model |
| Session / day filter | unchanged | Codebase | Keep existing behaviour |

---

## 8. Reference algorithm (language-agnostic)

```text
# --- primitives (all prices already converted to integer points) ---
kind(c):
    if abs(c.close - c.open) <= DOJI_TOL: return DOJI
    if c.close > c.open:                  return BULL
    return BEAR

top_pattern(X, Y, tol):
    if kind(X) != BULL: return NONE
    if abs(Y.high - X.high) <= tol: return EQUAL_TOP
    if Y.high > X.high + tol and Y.open <= X.high and Y.close < X.high:
        return WICK_SWEEP
    return NONE

# --- HTF: runs when an HTF candle Y closes, for each tf in HTF_TIMEFRAMES ---
on_htf_close(tf, X = previous closed HTF candle, Y = just-closed HTF candle):
    if kind(Y) != BEAR: return
    p = top_pattern(X, Y, HTF_EQ_TOL)
    if p == NONE: return
    armed.add(Setup(tf, p, X, Y,
                    setup_high = max(X.high, Y.high),
                    t_conf     = Y.close_time,
                    t_exp      = Y.close_time + HTF_SETUP_EXPIRY_BARS * tf))

# --- 1m: runs when a 1m candle closes (that candle is B3) ---
on_1m_close(bars):
    drop armed setups whose t_exp has passed
    if INVALIDATE_ON_CLOSE_ABOVE_HTF_HIGH: drop setups with bars[-1].close > setup_high
    A, B1, B2, B3 = bars[-4], bars[-3], bars[-2], bars[-1]
    if kind(A) != BULL: return
    seq   = [B1, B2, B3]
    if any(kind(b) == BULL for b in seq): return
    dojis = [i for i, b in enumerate(seq, start=1) if kind(b) == DOJI]
    if len(dojis) > MAX_DOJI_IN_SEQUENCE: return
    ltf = top_pattern(A, B1, LTF_EQ_TOL)
    if ltf == NONE: return
    if B1_MUST_BE_HIGHEST and max(B2.high, B3.high) > B1.high: return
    matches = [s for s in armed
               if A.open_time >= s.t_conf and B3.close_time <= s.t_exp
               and proximity_ok(s, B1)]            # always true when filter is off
    if not matches: return
    s = pick(matches)                              # 15m before 5m, then latest t_conf
    scenario = (1 if s.type == EQUAL_TOP else 2) + (2 if dojis else 0)
    if scenario not in ENABLED_SCENARIOS:  log_skip("scenario disabled"); return
    if open_positions >= MAX_OPEN_POSITIONS: log_skip("position open");   return
    sl = B1.high + SL_BUFFER
    place_sell(sl = sl, rr = RR, fill = ENTRY_FILL,
               tags = {scenario, s, ltf, dojis, A, B1, B2, B3, matches})
    consume(s)

# on fill: tp = fill - RR * (sl - fill); skip if sl - fill <= 0
```

---

## 9. Platform notes (use whichever matches the codebase)

**Pine Script (TradingView)**
- Run on a 1m chart. Read closed HTF candles without repainting:
  `request.security(syminfo.tickerid, "15", [open[1], high[1], low[1], close[1], open[2], high[2], low[2], close[2], time_close[1]], lookahead = barmerge.lookahead_on)` — index `[1]` is Y, `[2]` is X. Repeat with `"5"`.
- Detect a newly closed HTF candle with `ta.change(time("15")) != 0` (and `"5"`).
- Keep armed setups in `var` arrays or an array of a user-defined type. Evaluate the 1m logic only when `barstate.isconfirmed`.
- `strategy.entry("S", strategy.short)` + `strategy.exit("S-x", "S", stop = sl, limit = tp)`. In Pine, use `process_orders_on_close = true` (`ENTRY_FILL = b3_close`) so the TP computed at B3's close gives exactly 1:10.

**Python / pandas**
- `resample("15min", label="left", closed="left", origin="start_day")`. An HTF candle becomes usable at `label + tf`, not at its label. Join to 1m with `merge_asof` on that availability time.

**MQL5 / MQL4**
- On each new M1 bar, read `PERIOD_M5` / `PERIOD_M15` with shift 1 (Y) and shift 2 (X). Send the sell with SL and TP in the same request, normalized to `_Digits`, respecting the broker's minimum stop distance.

---

## 10. Trade journal and chart drawing

Log one row per trade **and** per skipped signal:
`trade_id, scenario (1–4), htf_tf, htf_pattern, htf_X_time, htf_Y_time, setup_high, t_conf, ltf_pattern, A/B1/B2/B3 open times + OHLC, doji_position (none/1/2/3), entry_time, entry_price, sl, tp, risk_pips, spread_at_entry, exit_time, exit_price, exit_reason (TP/SL), r_multiple, matching_setup_ids, skip_reason`.
Write timestamps in both the data time zone and UTC+6 (the trader's TradingView chart time zone) so trades can be checked by eye.

If the codebase can draw on charts: label the HTF pair ("EQ TOP 15m" / "SWEEP 5m"), label A/B1/B2/B3, and draw a grey risk box (entry → SL) and a light-blue reward box (entry → TP) like the screenshots, tagged "S1"–"S4".

---

## 11. Tests (write these before wiring into the live/backtest loop)

All fixtures use USDCAD prices, spread 0, `ENTRY_FILL = next_bar_open`, default parameters unless stated.

**HTF fixtures (15m)**

| Candle | Time | O | H | L | C |
|---|---|---|---|---|---|
| `HX` bull | 10:00 | 1.40050 | 1.40100 | 1.40040 | 1.40090 |
| `HY_eq` bear | 10:15 | 1.40090 | 1.40100 | 1.40030 | 1.40040 |
| `HY_sw` bear | 10:15 | 1.40090 | 1.40115 | 1.40030 | 1.40040 |

`HX + HY_eq` → EQUAL_TOP, `t_conf` 10:30, `t_exp` 11:15. `HX + HY_sw` → WICK_SWEEP.

**1m fixtures**

| Candle | Time | O | H | L | C |
|---|---|---|---|---|---|
| `A` bull | 10:30 | 1.40060 | 1.40080 | 1.40055 | 1.40075 |
| `B1_eq` bear | 10:31 | 1.40075 | 1.40080 | 1.40060 | 1.40062 |
| `B1_sw` bear | 10:31 | 1.40075 | 1.40088 | 1.40060 | 1.40062 |
| `B1_doji` | 10:31 | 1.40070 | 1.40080 | 1.40060 | 1.40070 |
| `B2` bear | 10:32 | 1.40062 | 1.40064 | 1.40050 | 1.40052 |
| `B2_doji` | 10:32 | 1.40062 | 1.40066 | 1.40056 | 1.40062 |
| `B3` bear | 10:33 | 1.40052 | 1.40054 | 1.40040 | 1.40042 |
| `B3_doji` | 10:33 | 1.40052 | 1.40056 | 1.40046 | 1.40052 |
| next bar open | 10:34 | = B3 close | | | |

**Positive cases**

| # | HTF | 1m sequence | Expected |
|---|---|---|---|
| T1 | HY_eq | A, B1_eq, B2, B3 | **Scenario 1**, entry 1.40042, SL 1.40081, risk 3.9 pips, TP 1.39652 |
| T2 | HY_sw | A, B1_sw, B2, B3 | **Scenario 2**, entry 1.40042, SL 1.40089, risk 4.7 pips, TP 1.39572 |
| T3 | HY_eq | A, B1_sw, B2_doji, B3 | **Scenario 3**, entry 1.40042, SL 1.40089, TP 1.39572 |
| T4 | HY_sw | A, B1_eq, B2, B3_doji | **Scenario 4**, entry 1.40052, SL 1.40081, risk 2.9 pips, TP 1.39762 |
| T5 | HY_eq | A, B1_doji, B2, B3 | **Scenario 3** (doji in position 1 forms the equal top), entry 1.40042, SL 1.40081, TP 1.39652 |
| T6 | HY_eq | T1 shifted so A = 11:11 (B3 closes 11:15 = `t_exp`) | Trade (boundary inclusive) |

**Negative cases — all must produce no trade**

| # | Change from T1 | Reason |
|---|---|---|
| N1 | B2 bullish (O 1.40052, C 1.40062) | Bullish candle inside the three |
| N2 | B2_doji and B3_doji together | Two dojis > `MAX_DOJI_IN_SEQUENCE` |
| N3 | B1 high 1.40079 | Neither equal top nor sweep |
| N4 | A at 10:29 | 1m pattern starts before `t_conf` |
| N5 | A at 11:12 (B3 closes 11:16) | Setup expired |
| N6 | B2 high 1.40085 | B1 is no longer the highest |
| N7 | T3 data with `ENABLED_SCENARIOS = [1, 2]` | Doji present → label 3, disabled |
| N8 | Evaluate at 10:29 while HY is still forming | HTF candle not closed |
| N9 | B1 = O 1.40085 H 1.40090 L 1.40060 C 1.40062 | Opened above A's high → not a wick sweep |
| N10 | HY bullish | HTF second candle must be bearish |
| N11 | T1 while a position is already open | Skipped and logged |

**Exit cases (after T1)**
- E1: a later bar with low 1.39650 → TP, +10R.
- E2: a later bar with high 1.40081 → SL, −1R.
- E3: one bar with both → SL first, −1R.

**No-look-ahead tests**
- Replay test: feed candles one at a time (streaming) and run the full history in batch; signals must be identical.
- Mutation test: change any candle after time T; no signal before T may change.

---

## 12. Definition of done and report

1. All tests in §11 pass.
2. Backtest on the available USDCAD 1m history. Report per scenario (1–4) and in total: number of trades, win rate, average R, net R, max drawdown (R and %), longest losing streak, average SL distance in pips, and average spread as a % of risk. (At 1:10, break-even win rate is about 9.1% before costs, so long losing streaks are expected — report them, don't "fix" them.)
3. List 10 sample trades with all timestamps (data time zone and UTC+6) so the trader can check them on TradingView against the screenshots.
4. A short diff summary of every file added or changed.

---

## 13. Do not

- Add filters that are not in this document (trend, RSI, news, extra sessions, minimum candle size).
- Move the stop, take partials, or close early.
- Use any forming / unclosed candle on any timeframe.
- Treat a doji as bullish or bearish.
- Change a default silently — ask first.
