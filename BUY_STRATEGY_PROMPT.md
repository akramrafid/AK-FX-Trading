# Claude Code Prompt — 1-Minute Buy Strategy (Scenarios 1–2 + "Mission Impossible" 3-run)

**Attach three files with this prompt:**
1. Buy image "scenerio 1 BUY SETUP" (equal lows on 5/15m)
2. Buy image "scenerio 2 BUY SETUP" (sweep on 5/15m)
3. `Mission_Impossible_Pine_Script.docx` (rules of the 1-minute 3-run detector)

If you can't open the .docx directly, extract it (pandoc, python-docx, or unzip `word/document.xml` and `word/media/`). Every rule in it is also written out in §4.3 of this prompt, so nothing depends on reading it.

---

## 0. Your role and working method

You are a senior software engineer (30 years) working with a senior hedge-fund trader (30 years). The trader's strategy below is final. Implement it **exactly** inside the existing codebase — no reinterpretation, no extra filters, no "improvements".

Work in three steps:

1. **Explore first (read-only).**
   - Read the repo's own rules first (`CLAUDE.md`, `GLOBAL-RULES.md`, `AGENTS.md` if present) and obey them.
   - Find: language/platform; how 1m candles are loaded; how 5m/15m candles are built; the strategy interface; the backtester; order and position management (the repo appears to contain `dwx_client.py` and `DWX_Server.mq4` — likely the Python↔MT4 order bridge — and `AK_Strategy_TradingView.pine`); spread/slippage model; config; trade journal; time-zone handling; tests.
   - **Find the sell strategy** built from `SELL_STRATEGY_PROMPT.md`, if it exists. Reuse its infrastructure (HTF candle builder, armed-setup logic, order layer, journal, chart drawing) and mirror it for buys. Do not change the sell behaviour.
   - **Find the "Mission Impossible" Pine Script v6 indicator** described in the doc (search for "Mission Impossible", `streakEligible`, `prevStreakLow`). If it exists, it is the reference for the 1m 3-run logic: port it faithfully.
2. **Report before editing.** Send me: (a) the buy strategy restated in your own words, (b) files you will add or change, (c) how each parameter in §8 maps onto the existing config, (d) every difference between the doc, the original Pine code (if found), the sell implementation and this prompt, and (e) your answers to the "confirm" items in §4.5. **Wait for my "go".**
3. **Implement → test → backtest → report** (§12 and §13).

Rules of engagement:
- Don't change other strategies, the sell side, existing defaults, session/day filters or the risk model.
- Every value marked **ASSUMPTION** in §8 must be a config parameter with the stated default.
- If something isn't covered here, ask. Don't invent rules.

---

## 1. Sources and which one wins

| Source | What it decides |
|---|---|
| The two buy images | The trade plan: HTF condition (5m/15m), the 1m trigger shape, entry, stop loss, take profit |
| The doc (Mission Impossible) | How the 1m 3-run is detected: doji definition, how dojis count, "prior run", equal/sweep using `<=` |
| Original Mission Impossible Pine code (if in repo) | Wins over the doc's prose for the 1m detector. Report every difference you find |
| This prompt | Exact rules, defaults, algorithm and tests. If it disagrees with the images or doc, stop and ask |

---

## 2. How to read the images and the doc

**Buy images**
- **Blue** = bullish (close > open). **Black** = bearish (close < open).
- **Pink box** = risk zone of a TradingView long-position tool (entry → stop loss). **Cyan box** = reward zone (entry → take profit). The pink/cyan boundary is the entry = close of the 3rd bullish candle.
- The 3rd bullish candle looks purple only because the box overlaps it. It is a blue (bullish) candle.
- Each image: the **top-left drawing** is the 5m/15m condition; the **three lower drawings** are the accepted 1m triggers:
  1. equal lows, then 3 consecutive bullish candles
  2. bullish wick sweeps a bearish candle that has no lower wick (its body bottom is its low), then 3 bullish
  3. bullish wick sweeps a bearish candle's lower wick, then 3 bullish
- "swap" means **sweep** (taking out a previous low).
- **Text-box typos — read them as follows:**
  - Step 5 says "place **sell** where the candle closed". In a BUY setup this means **place the buy**.
  - The second image's text box is headed "How to take the buy for scenerio **1**". It is Scenario **2** (step 1 differs).
  - "stop loss loss" = stop loss.

**Doc (Mission Impossible)**
- Green = bullish, red = bearish, grey cross = doji. "P1–P3" = the prior run, "1-2-3" = the new run.
- The doc describes both directions. This prompt uses only the **bullish** 3-run.

---

## 3. Trader's briefing — the rules as written

(The trader's words, spelling and the sell/buy typo fixed.)

**Scenario 1 — BUY**
1. Look for an Equal Low on the 5 or 15 minute timeframe. *(The equal low can be by body or wick.)*
2. Then move to the 1 minute timeframe.
3. On 1 minute, look for an equal low (body or wick), or a bearish candle swept by a bullish candle's wick, or a bearish candle's wick swept by a bullish candle's wick.
4. 3 consecutive bullish candles start on 1 minute. The 1st candle is the one that made the equal low, swept the body, or swept the wick of the bearish candle.
5. Make sure the 3 consecutive candles formed on 1 minute. After the 3rd candle closes, **place the buy where the candle closed**. Stop loss goes below the 1st candle of the 3 consecutive candles.
6. Take profit = 10 × the pip distance from the stop loss to the entry.

**Scenario 2 — BUY** — identical, except step 1: look for a **bearish candle's low swept by a bullish candle's wick** on 5 or 15 minute. *(The sweep can be by the body or the wick of the bullish candle.)*

**Doc — 1m 3-run rules (Mission Impossible)**
- Doji = body ≤ 5% of the candle's range (adjustable). It is neutral.
- Bullish run is valid when its first candle's low is **at or below** the prior run's low (`<=`: equal or sweep both count; exact price, no tolerance — a 1-tick miss is rejected).
- The signal fires once, when the run reaches 3 candles.
- Up to 2 dojis can sit in a run, with special counting rules (§4.3).

**Trader's summary:** the HTF filter is the only difference between the two scenarios. The 1m trigger, entry, stop and target are the same: a bearish candle or run is swept or equalled by the first candle of a 3-candle bullish run, then buy at the close of the 3rd candle, with the stop below the 1st candle and the target at 10R.

---

## 4. Exact definitions

Convert every price to integer **points** before comparing: `pts(p) = round(p / point_size)`. USDCAD: point = 0.00001 (= TradingView's one tick), pip = 10 points. Never compare raw floats.

### 4.1 Candle kind — from the doc (evaluate in this order)
1. `DOJI` if `|close − open| ≤ DOJI_BODY_PCT × (high − low) / 100` (default 5%). A zero-range candle is a doji.
2. `BULL` if `close > open`
3. `BEAR` if `close < open`

Use the same `kind()` on every timeframe.

### 4.2 HTF pattern (5m or 15m) — from the images
`X` = a `BEAR` HTF candle, `Y` = the next HTF candle, which must be `BULL`. Both closed and adjacent.
- `EQUAL_LOW` (Scenario 1): `|low(Y) − low(X)| ≤ HTF_EQ_TOL` (default 0 = exactly equal)
- `SWEEP_LOW` (Scenario 2): `low(Y) < low(X) − HTF_EQ_TOL` — Y's body or wick may do it (the image allows both). No other condition on Y.
- otherwise `NONE`

**Trader's note on "by body or wick" (important):**
- In the drawings, when a candle has no lower wick, its body bottom is its low. When it has a wick, the wick tip is its low. Comparing **true lows** reproduces every drawing in both images and matches the doc's code (`low <= prior low`). This is the default: `EQUAL_LOW_MODE = low`.
- The alternative, comparing **body bottoms** of candles that *do* have wicks (bearish close vs bullish open), is available as `EQUAL_LOW_MODE = body | either` but is **off**. On FX data a bullish candle almost always opens at the previous close, so that comparison would accept nearly every bearish→bullish pair and the HTF filter would stop filtering. Do not switch it on without my approval.

```
 EQUAL_LOW (low = low)               SWEEP_LOW (low(Y) < low(X))
    |   |                               |   |
    #  [Y]                              #  [Y]
    #  [Y]                              #  [Y]
    |   |   <- same low                 |   |
                                            |  <- Y goes below X's low
 # = bearish (black)   [Y] = bullish (blue)
```

### 4.3 1-minute 3-run detector — from the doc
Process closed 1m candles one at a time.

**State**
- *Current run*: direction (BULL or BEAR), `count`, merged `run_high`/`run_low` (including merged dojis), `first` candle (may be a doji), `eligible`, `fired`.
- *Prior run*: the run immediately before the current one (opposite direction). `prior_low` = its lowest low, `prior_high` = its highest high, both including merged dojis.
- *Pending dojis*: up to 2 dojis waiting to be assigned.

**On a doji**
- **a. Completes the run** — if the current run has ≥ 1 real candle and `count + pending + 1 = 3`: merge pending + this doji, set `count = 3`, clear pending, fire if `eligible` and not `fired`.
  This covers "doji = 3rd candle" (Bull, Bull, **Doji**) and "Bull, Doji, **Doji**".
- **b. Third doji in a row** — else if 2 dojis are already pending: clear pending. This doji is dropped too.
- **c. Otherwise** — add to pending.

**On a real candle**
- **d. Same direction as the current run (continuation)** — `count += 1`. Pending dojis are merged into the range but are **not counted** (the doc's "doji = 2nd candle" rule: Bull, Doji, Bull, Bull fires on bar 4). Fire when `count` reaches 3 and the run is eligible.
- **e. Opposite direction (or first run ever)** — the current run becomes the prior run. A new run starts:
  - pending dojis become its first candles, so `count = 1 + pending`
  - `first` = the first pending doji if any, else this candle
  - eligibility is tested on `first`: BULL → `low(first) ≤ prior_low`; BEAR → `high(first) ≥ prior_high`; no prior run → not eligible
  - if `count` is already 3 (Doji, Doji, **Bull**), fire now if eligible

A run fires **at most once**, only at the bar where `count` reaches 3, and only if eligible. The buy strategy uses **BULL** signals only.

### 4.4 Doji cases — expected signal bar (from the doc, bullish side)

| New run (after a 3-candle bearish prior run) | Signal fires on |
|---|---|
| Bull, Bull, Bull | 3rd candle |
| **Doji**, Bull, Bull | 3rd candle (the doji is candle 1; eligibility tested on the doji) |
| Bull, **Doji**, Bull, Bull | 4th candle (single doji in position 2 is not counted) |
| Bull, Bull, **Doji** | the doji |
| Doji, Bull, Doji | 2nd doji |
| Doji, Doji, Bull | the bull |
| Bull, Doji, Doji | 2nd doji |
| Doji, Doji, Doji, … | pending dojis dropped; the next real candle starts fresh |

### 4.5 Derived behaviours — implement as stated, and confirm with me in your step-2 report
1. **Position-2 quirk.** One doji in position 2 is not counted (signal on bar 4), but two dojis after one bull are counted (signal on bar 3). The doc documents both, so replicate both. Option `DOJI_COUNTING = every_doji_counts` (every doji simply counts as one of the 3, max 2) exists, but the default is `doc_exact`.
2. **Short prior runs absorb dojis.** In the buy images the prior run is a single bearish candle. Under rule (a), `Bear, Doji, Doji` completes that *bearish* run, so `Bear, Doji, Doji, Bull` gives **no** bullish signal (test N3). `Bear, Doji, Bull, Bull` still works (test B3). The doc's examples always use a 3-candle prior run, so they never show this.
3. **Eligibility with a doji first.** The doc's prose says eligibility is tested on the first doji. Its code line uses `newLow`, which may be the merged low of the dojis plus the first real candle. If the original code is in the repo, follow the code and tell me which it is. Test N4 assumes the prose.
4. **Third doji.** "Drops the pending dojis" is read as: all three are dropped and don't count toward any run.

### 4.6 Strategy-level checks on a bullish signal
Let `first` = the first candle of the run, `S` = the signal bar.
- `FIRST_MUST_BE_LOWEST` (ASSUMPTION, default true): `run_low == low(first)`. No later candle or merged doji in the run may go below the first candle's low. Otherwise there is no trade, because the stop "below the 1st candle" would already have been touched. This mirrors the sell side's "B1 stays highest".

```
   P     1     2     3
   |                 |      <- BUY at the close of candle 3 (the signal bar)
   #          |    [ ]
   #     |   [ ]   [ ]
   #    [ ]  [ ]    |
   |    [ ]   |
   ^     |              <- candle 1 low <= prior run low (equal or sweep)
   prior low            SL = low(candle 1) − SL_BUFFER
                        TP = entry + 10 × (entry − SL)
```

---

## 5. Scenario matrix

| Scenario | HTF pattern (5m **or** 15m) | 1m trigger | Entry / SL / TP |
|---|---|---|---|
| 1 | `EQUAL_LOW` (bearish X, bullish Y) | Bullish 3-run per §4.3, eligible (`low(first) ≤ prior_low`) | Buy at signal-bar close; SL below 1st candle; TP 10R |
| 2 | `SWEEP_LOW` (bearish X, bullish Y) | Same | Same |

Dojis are allowed in both scenarios, following the doc's rules. Log the doji count and positions with every trade.

---

## 6. Linking the HTF to the 1m chart (no look-ahead)

1. Build 5m and 15m candles from 1m data (or use native HTF data), clock-aligned (5m on :00, :05 …; 15m on :00, :15, :30, :45) in the data feed's time zone, matching TradingView FXCM. **Reuse the sell side's HTF builder if it exists.**
2. Scan each timeframe in `HTF_TIMEFRAMES` independently. A pattern on either is enough.
3. An HTF pattern exists only after `Y` has closed: `t_conf = close_time(Y)`. Never use a forming candle.
4. On confirmation, arm a bullish setup: `{id, tf, type, X, Y, setup_low = min(low X, low Y), t_conf, t_exp = t_conf + HTF_SETUP_EXPIRY_BARS × tf}`.
5. A bullish 1m signal may use a setup only if `open_time(first) ≥ t_conf` and `close_time(S) ≤ t_exp`. The **prior bearish run may begin before** `t_conf` — it is only the reference low (ASSUMPTION `RUN_MUST_START_AFTER_HTF = true` applies to the new run only).
6. Optional (ASSUMPTION, default OFF): cancel the setup if a 1m candle closes below `setup_low` before entry.
7. One trade per setup (`MAX_TRADES_PER_SETUP = 1`).
8. If several setups match one signal: take one trade. Label it from the 15m setup before the 5m one; on a tie, the latest `t_conf`. Log all matching setup ids.
9. The 1m trigger does **not** have to sit at the HTF low (not required by the images). Optional proximity filter `LTF_NEAR_HTF_LOW_PIPS`, default OFF.

---

## 7. Orders and trade management

- **BUY only** in this strategy. Don't touch the sell logic.
- **Trigger:** confirmed close of the signal bar S.
- **Entry:** "place the buy where the candle closed" → `ENTRY_FILL = signal_close`. Live: market buy immediately when S closes. Backtest: fill at S's close; a long fills at the ask, so with bid data `entry = close(S) + spread` per the existing spread model. Alternative `next_bar_open` is available.
- **Stop loss:** `SL = low(first) − SL_BUFFER` (default 1 point, i.e. strictly below). Fixed, sent with the order, never moved.
- **Take profit:** `TP = entry_fill + RR × (entry_fill − SL)` with `RR = 10`, computed from the actual fill.
- **Exits:** SL or TP only. No break-even, trailing stop, partials, time exit or reverse-signal exit.
- **Long-side pricing with bid OHLC:** SL is hit when `bid_low ≤ SL`; TP when `bid_high ≥ TP`.
- **SL and TP touched in the same 1m bar:** count it as SL first unless tick data is available.
- **Position size:** use the existing risk model; if there is none, risk `RISK_PER_TRADE_PCT` of equity over the SL distance.
- **Concurrency:** `MAX_OPEN_POSITIONS = 1` per symbol, **shared with the sell strategy** (no hedging). A signal while any position is open is logged as skipped.
- **Session / day filters:** keep whatever exists (the existing backtester shows `0700-1800`, Mon–Fri). Add none.
- If `entry_fill − SL ≤ 0`, skip the trade and log it.

---

## 8. Parameters (trader–engineer review decisions)

| Parameter | Default | Source | Meaning |
|---|---|---|---|
| `ENABLED_SCENARIOS` | `[1, 2]` | Image | Buy scenarios allowed |
| `SIDE` | `BUY` | Image | This strategy only buys |
| `HTF_TIMEFRAMES` | `[5m, 15m]` | Image | "5 or 15 minute" |
| `LTF_TIMEFRAME` | `1m` | Image | Trigger chart |
| `RUN_LENGTH` | `3` | Image + doc | 3 consecutive bullish candles |
| `RR` | `10` | Image | TP = 10 × SL distance |
| `ENTRY_FILL` | `signal_close` | Image | "Where the candle closed" |
| `DOJI_BODY_PCT` | `5` | Doc | Doji = body ≤ 5% of range |
| `MAX_DOJI_IN_RUN` | `2` | Doc | Up to 2 dojis per run |
| `DOJI_COUNTING` | `doc_exact` | Doc | Alternative: `every_doji_counts` |
| `LTF_EQ_TOL_POINTS` | `0` | Doc | Exact; a 1-tick miss is rejected |
| `EQUAL_LOW_MODE` | `low` | ASSUMPTION | `body` / `either` available, off (§4.2) |
| `HTF_EQ_TOL_POINTS` | `0` | ASSUMPTION | 0 = HTF lows exactly equal |
| `SL_BUFFER_POINTS` | `1` | ASSUMPTION | "Below" the 1st candle = 1 point below |
| `FIRST_MUST_BE_LOWEST` | `true` | ASSUMPTION | No candle in the run below the 1st candle's low |
| `HTF_SETUP_EXPIRY_BARS` | `3` | ASSUMPTION | Setup armed for 3 HTF candles |
| `RUN_MUST_START_AFTER_HTF` | `true` | ASSUMPTION | New run starts at/after `t_conf`; prior run may be earlier |
| `INVALIDATE_ON_CLOSE_BELOW_HTF_LOW` | `false` | ASSUMPTION | Optional cancel rule |
| `LTF_NEAR_HTF_LOW_PIPS` | `off` | ASSUMPTION | Optional proximity filter |
| `MAX_TRADES_PER_SETUP` | `1` | ASSUMPTION | One trade per HTF setup |
| `MAX_OPEN_POSITIONS` | `1` per symbol, shared with sell | ASSUMPTION | No hedging |
| `SAME_BAR_SL_TP` | `SL_FIRST` | ASSUMPTION | Conservative |
| `RISK_PER_TRADE_PCT` | existing model, else `1.0` | ASSUMPTION | Only if no risk model exists |
| Session / day filter | unchanged | Codebase | Keep existing |

---

## 9. Reference algorithm (language-agnostic)

```text
kind(c):
    rng = c.high - c.low ; body = abs(c.close - c.open)
    if body * 100 <= DOJI_BODY_PCT * rng: return DOJI
    return BULL if c.close > c.open else BEAR

# ---------- HTF: when an HTF candle Y closes (each tf) ----------
on_htf_close(tf, X, Y):
    if kind(X) != BEAR or kind(Y) != BULL: return
    d = Y.low - X.low                         # EQUAL_LOW_MODE = low
    if   abs(d) <= HTF_EQ_TOL: t = EQUAL_LOW
    elif d < -HTF_EQ_TOL:      t = SWEEP_LOW
    else: return
    armed.add(Setup(tf, t, X, Y, setup_low=min(X.low, Y.low),
                    t_conf=Y.close_time, t_exp=Y.close_time + HTF_SETUP_EXPIRY_BARS*tf))

# ---------- 1m 3-run detector (doc_exact) ----------
on_1m_close(c):
    k = kind(c)
    if k == DOJI:
        if run.dir and run.count >= 1 and run.count + len(pending) + 1 == 3:   # (a)
            merge(run, pending + [c]); run.count = 3; pending = []
            if run.eligible and not run.fired: fire(run, c)
        elif len(pending) == 2: pending = []                                   # (b)
        else: pending.append(c)                                                # (c)
        return
    if k == run.dir:                                                            # (d)
        run.count += 1; merge(run, pending + [c]); pending = []
        if run.count == 3 and run.eligible and not run.fired: fire(run, c)
        return
    prior = run (if any)                                                        # (e)
    run = Run(dir=k, members=pending + [c], first=(pending + [c])[0],
              count=1 + len(pending))
    run.eligible = prior exists and (
        (k == BULL and run.first.low  <= prior.low) or
        (k == BEAR and run.first.high >= prior.high))
    pending = []
    if run.count == 3 and run.eligible: fire(run, c)

# ---------- strategy layer: on a BULL fire at signal bar S ----------
on_bull_signal(run, S):
    expire / invalidate armed setups
    if FIRST_MUST_BE_LOWEST and run.low < run.first.low: log_skip("first not lowest"); return
    matches = [s for s in armed
               if run.first.open_time >= s.t_conf and S.close_time <= s.t_exp
               and proximity_ok(s, run.first)]
    if not matches: return
    s = pick(matches)                        # 15m before 5m, then latest t_conf
    scenario = 1 if s.type == EQUAL_LOW else 2
    if scenario not in ENABLED_SCENARIOS:       log_skip("scenario disabled"); return
    if open_positions >= MAX_OPEN_POSITIONS:    log_skip("position open");     return
    sl = run.first.low - SL_BUFFER
    place_buy(fill=ENTRY_FILL, sl=sl, rr=RR, tags={scenario, s, run, dojis, matches})
    consume(s)

# on fill: tp = fill + RR * (fill - sl); skip if fill - sl <= 0
```

Keep the 3-run detector a pure, separately tested module. It produces both bullish and bearish runs, so the prior bearish run is tracked correctly; the buy strategy consumes only BULL signals.

---

## 10. Platform notes (use whichever matches the codebase)

**Pine Script v6 (TradingView)**
- Run on a 1m chart. Read closed HTF candles without repainting: `request.security(syminfo.tickerid, "15", [open[1], high[1], low[1], close[1], open[2], high[2], low[2], close[2], time_close[1]], lookahead = barmerge.lookahead_on)` — index `[1]` is Y, `[2]` is X. Repeat with `"5"`. Detect a new HTF close with `ta.change(time("15")) != 0`.
- Port the Mission Impossible state with `var` variables. Evaluate only on `barstate.isconfirmed`.
- `strategy.entry("B", strategy.long)` + `strategy.exit("B-x", "B", stop = sl, limit = tp)` with `process_orders_on_close = true` (= `signal_close`).

**Python / pandas**
- `resample("15min", label="left", closed="left", origin="start_day")`. An HTF candle is usable from `label + tf`, not from its label. Join with `merge_asof` on that availability time.

**MT4 via the DWX bridge (if that's the live path)**
- Trigger on each new closed M1 bar. Read M5/M15 with shift 1 (Y) and 2 (X). Send the buy with SL and TP in the same request, normalized to `_Digits`, respecting the broker's minimum stop distance.

---

## 11. Trade journal and chart drawing

Log one row per trade **and** per skipped signal:
`trade_id, side=BUY, scenario (1/2), htf_tf, htf_pattern, htf_X_time, htf_Y_time, setup_low, t_conf, prior_run_start, prior_run_end, prior_low, ltf_type (EQUAL/SWEEP), run candle times + OHLC, first_candle_time, doji_count, doji_positions, signal_bar_time, entry_time, entry_price, sl, tp, risk_pips, spread_at_entry, exit_time, exit_price, exit_reason (TP/SL), r_multiple, matching_setup_ids, skip_reason`.
Write timestamps in the data time zone and in UTC+6 (the trader's TradingView chart time zone).

If the codebase draws on charts: label the HTF pair ("EQ LOW 15m" / "SWEEP 5m"), mark the prior-run low line and candles 1-2-3, and draw a pink risk box (entry → SL) and a cyan reward box (entry → TP) like the images, tagged "B1"/"B2".

---

## 12. Tests (write these before wiring into the live/backtest loop)

USDCAD prices, spread 0, `ENTRY_FILL = signal_close`, default parameters unless stated. All expected values below were checked by running the §9 logic.

**HTF fixtures (15m)** — `t_conf` 10:30, `t_exp` 11:15

| Candle | Time | O | H | L | C | Result with HX |
|---|---|---|---|---|---|---|
| `HX` bear | 10:00 | 1.40100 | 1.40110 | 1.40050 | 1.40060 | — |
| `HY_eq` bull | 10:15 | 1.40060 | 1.40120 | 1.40050 | 1.40110 | EQUAL_LOW |
| `HY_sw` bull | 10:15 | 1.40060 | 1.40120 | 1.40035 | 1.40110 | SWEEP_LOW |
| `HY_none` bull | 10:15 | 1.40060 | 1.40120 | 1.40052 | 1.40110 | NONE |

**1m fixtures** — candles in a sequence occupy consecutive minutes; `P` is at 10:30 (or `P1` at 10:28 when listed).

| Candle | Kind | O | H | L | C |
|---|---|---|---|---|---|
| `P1` | bear | 1.40110 | 1.40112 | 1.40085 | 1.40090 |
| `P2` | bear | 1.40090 | 1.40093 | 1.40060 | 1.40065 |
| `P` | bear | 1.40070 | 1.40072 | 1.40040 | 1.40045 |
| `R1_eq` | bull | 1.40045 | 1.40060 | 1.40040 | 1.40055 |
| `R1_sw` | bull | 1.40045 | 1.40060 | 1.40033 | 1.40055 |
| `R1_miss` | bull | 1.40045 | 1.40060 | 1.40041 | 1.40055 |
| `D1` | doji | 1.40048 | 1.40060 | 1.40040 | 1.40048 |
| `D1_hi` | doji | 1.40050 | 1.40056 | 1.40045 | 1.40050 |
| `R2` | bull | 1.40055 | 1.40070 | 1.40050 | 1.40065 |
| `R2_low` | bull | 1.40055 | 1.40070 | 1.40035 | 1.40065 |
| `Dm` | doji | 1.40055 | 1.40062 | 1.40050 | 1.40055 |
| `Dx` | doji | 1.40050 | 1.40056 | 1.40044 | 1.40050 |
| `R3` | bull | 1.40065 | 1.40080 | 1.40060 | 1.40075 |
| `D3` | doji | 1.40065 | 1.40072 | 1.40058 | 1.40065 |
| `D5` | doji | 1.40055 | 1.40065 | 1.40045 | 1.40056 |
| `D10` | bull | 1.40055 | 1.40065 | 1.40045 | 1.40057 |

`D5` (body 1 pt, range 20 = 5%) must classify as DOJI; `D10` (10%) as BULL.

**Positive cases**

| # | HTF | 1m sequence | Expected |
|---|---|---|---|
| B1 | HY_eq | P, R1_eq, R2, R3 | **Scenario 1**, signal on R3, entry 1.40075, SL 1.40039, risk 3.6 pips, TP 1.40435 |
| B2 | HY_sw | P, R1_sw, R2, R3 | **Scenario 2**, signal on R3, entry 1.40075, SL 1.40032, risk 4.3 pips, TP 1.40505 |
| B3 | HY_eq | P, D1, R2, R3 | Scenario 1, doji is candle 1, signal on R3, entry 1.40075, SL 1.40039, TP 1.40435 |
| B4 | HY_sw | P, R1_eq, Dm, R2, R3 | Scenario 2, signal on the **4th** bar (R3), entry 1.40075, SL 1.40039, TP 1.40435 |
| B5 | HY_eq | P, R1_eq, R2, D3 | Scenario 1, signal on D3, entry 1.40065, SL 1.40039, risk 2.6 pips, TP 1.40325 |
| B6 | HY_eq | P1, P2, P, D1, Dm, R3 | Scenario 1 (Doji, Doji, Bull), signal on R3, entry 1.40075, SL 1.40039, TP 1.40435 |
| B7 | HY_sw | P, R1_eq, Dm, D3 | Scenario 2 (Bull, Doji, Doji), signal on D3, entry 1.40065, SL 1.40039, TP 1.40325 |
| B8 | HY_eq | P, D1, R2, D3 | Scenario 1 (Doji, Bull, Doji), signal on D3, entry 1.40065, SL 1.40039, TP 1.40325 |
| B9 | HY_eq | B1 shifted so the run's 1st candle is at 11:12 (signal bar closes 11:15 = `t_exp`) | Trade (boundary inclusive) |

**Negative cases — all must produce no trade**

| # | Setup | Reason |
|---|---|---|
| N1 | HY_none + B1 sequence | No HTF pattern |
| N2 | P, R1_miss, R2, R3 | 1-tick miss of the prior low |
| N3 | P, D1, Dm, R3 (1-candle prior run) | Dojis complete the bearish run (§4.5-2); no bullish signal |
| N4 | P, D1_hi, R1_sw, R2 | First candle (doji) misses the prior low; the later sweep doesn't count (§4.5-3) |
| N5 | P, R1_eq, R2_low, R3 | Signal fires, but the 1st candle is not the lowest |
| N6 | B1 shifted so the run's 1st candle is at 10:29 | Run starts before `t_conf` |
| N7 | B1 shifted so the run's 1st candle is at 11:13 | Setup expired |
| N8 | Evaluate at 10:29 while HY is still forming | HTF candle not closed |
| N9 | HX or HY replaced by a doji (body ≤ 5% of range) | HTF pair must be bear then bull |
| N10 | P1, P2, P, D1, Dm, Dx, R2, R3, R3 | Third doji drops the pending dojis; R2 restarts the run and misses the prior low |
| N11 | B1 while any position (buy or sell) is open | Skipped and logged |
| N12 | B1 with `ENABLED_SCENARIOS = [2]` | Scenario 1 disabled |

**Exit cases (after B1, long, spread 0)**
- E1: a later bar with high 1.40435 → TP, +10R.
- E2: a later bar with low 1.40039 → SL, −1R.
- E3: one bar with both → SL first, −1R.

**No-look-ahead tests**
- Replay test: streaming (one candle at a time) and batch runs give identical signals.
- Mutation test: changing any candle after time T changes no signal before T.

**Parity test (if the original Mission Impossible Pine code is found)**
- Run the ported detector on the same history and compare signal bars with the Pine indicator's signals. Report any mismatch.

---

## 13. Definition of done and report

1. All tests in §12 pass.
2. Backtest on the available USDCAD 1m history. Report per scenario (1, 2) and in total: trades, win rate, average R, net R, max drawdown (R and %), longest losing streak, average SL distance in pips, average spread as a % of risk. Also count trades with 0, 1 and 2 dojis. (At 1:10, break-even win rate is about 9.1% before costs; long losing streaks are expected — report them, don't "fix" them.)
3. If the sell strategy is implemented, also report the combined buy + sell results with the shared one-position rule.
4. List 10 sample buy trades with all timestamps (data time zone and UTC+6) so the trader can check them on TradingView against the images.
5. A short diff summary of every file added or changed.

---

## 14. Do not

- Add filters not in this document (trend, RSI, news, extra sessions, minimum candle size).
- Move the stop, take partials, or close early.
- Use any forming / unclosed candle on any timeframe.
- Treat a doji as bullish or bearish.
- Switch `EQUAL_LOW_MODE` to `body`/`either`, or change `DOJI_COUNTING`, without my approval.
- Modify the sell strategy. If its doji or "prior candle" rules differ from the doc, report it — don't change it.
