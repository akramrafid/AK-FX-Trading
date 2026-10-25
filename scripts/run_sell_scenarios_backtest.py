"""scripts/run_sell_scenarios_backtest.py
Backtest the 1-minute Sell Scenarios 1-4 (SELL_STRATEGY_PROMPT.md) on the recorded USDCAD history.

Data: data/trading.db, both symbol spellings (USDCAD and USDCADm): 1m bars plus the broker's
own 5m and 15m bars, all UTC. Writes docs/qa/sell-scenarios-backtest-report.md and one journal
CSV per spread case (one row per trade and per skipped signal, times in UTC and UTC+6).

Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.models import Candle
from engine.sell_scenarios import M1, UTC_PLUS_6, SellScenarioParams, SkipReason
from engine.sell_scenarios_backtest import (
    JOURNAL_COLUMNS,
    ScenarioStats,
    SellBacktestResult,
    SellBacktestSettings,
    SellTrade,
    journal_rows,
    run_sell_backtest,
    scenario_stats,
    summarize,
)

SENSITIVITY_SPREADS = (0.0, 0.3, 0.5, 1.0)
SAMPLE_TRADES = 10


def load_db_candles(db_path: Path, timeframe: str) -> List[Candle]:
    """USDCAD candles of one timeframe from both symbol spellings, one per timestamp (read-only)."""
    conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT timestamp, open, high, low, close, volume FROM candles "
            "WHERE symbol LIKE 'USDCAD%' AND timeframe = ? ORDER BY timestamp, symbol",
            (timeframe,),
        ).fetchall()
    finally:
        conn.close()
    candles: Dict[str, Candle] = {}
    for ts, o, h, low, c, v in rows:
        if ts not in candles:
            when = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            candles[ts] = Candle(when, float(o), float(h), float(low), float(c), float(v))
    return [candles[ts] for ts in sorted(candles)]


def write_journal(result: SellBacktestResult, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(journal_rows(result))


def _stats_table(rows: Sequence[ScenarioStats]) -> List[str]:
    lines = [
        "| Scenario | Trades | Win rate | Avg R | Net R | Max DD (R) | Max DD (%) | Longest losing streak "
        "| Avg SL (pips) | Avg spread % of risk | Net R after $7/lot commission |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in rows:
        lines.append(
            f"| {s.label} | {s.trades} | {s.win_rate_pct:.1f}% | {s.avg_r:+.2f} | {s.net_r:+.1f} | {s.max_dd_r:.1f} "
            f"| {s.max_dd_pct:.1f}% | {s.longest_losing_streak} | {s.avg_sl_pips:.1f} | {s.avg_spread_pct_of_risk:.1f}% "
            f"| {s.net_r_after_commission:+.1f} |"
        )
    return lines


def _hm(ts: datetime, tz: timezone) -> str:
    return f"{ts.astimezone(tz):%m-%d %H:%M}"


def _sample(trades: Sequence[SellTrade], n: int) -> List[SellTrade]:
    """Up to n trades, taken in turn from Scenarios 1-4 so every scenario shows up, then by entry time."""
    queues = {k: sorted((t for t in trades if t.scenario == k), key=lambda t: t.entry_time) for k in (1, 2, 3, 4)}
    picked: List[SellTrade] = []
    while len(picked) < n and any(queues.values()):
        for k in (1, 2, 3, 4):
            if queues[k] and len(picked) < n:
                picked.append(queues[k].pop(0))
    return sorted(picked, key=lambda t: t.entry_time)


def _sample_rows(trades: Sequence[SellTrade]) -> List[str]:
    lines = [
        "| # | Scen. | HTF setup | Times UTC (data feed) | Times UTC+6 (your TradingView) | Entry / SL / TP | Exit |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in trades:
        d = t.decision
        s = d.setup
        cells = []
        for tz in (timezone.utc, UTC_PLUS_6):
            cells.append(
                f"X {_hm(s.x.timestamp, tz)}, Y {_hm(s.y.timestamp, tz)}, conf {_hm(s.t_conf, tz)}; "
                f"A {_hm(d.a.timestamp, tz)}, B1 {_hm(d.b1.timestamp, tz)}, B2 {_hm(d.b2.timestamp, tz)}, "
                f"B3 {_hm(d.b3.timestamp, tz)}; entry {_hm(t.entry_time, tz)}, exit {_hm(t.exit_time, tz)}"
            )
        doji = "" if d.doji_position == "none" else f", doji B{d.doji_position}"
        lines.append(
            f"| {t.trade_id} | S{d.scenario} | {s.timeframe} {s.pattern.value} (1m {d.ltf_pattern.value}{doji}) "
            f"| {cells[0]} | {cells[1]} | {t.entry_price:.5f} / {t.stop_loss:.5f} / {t.take_profit:.5f} "
            f"({t.risk_pips:.1f} pips) | {t.exit_reason} at {t.exit_price:.5f}, {t.r_multiple:+.2f}R |"
        )
    return lines


def render_report(
    m1: Sequence[Candle],
    htf: Dict[str, List[Candle]],
    params: SellScenarioParams,
    report_spreads: Sequence[float],
    results: Dict[float, SellBacktestResult],
    one_position: Dict[float, SellBacktestResult],
    journals: Dict[float, Path],
) -> str:
    trading_days = sorted({c.timestamp.date() for c in m1})
    now = datetime.now(timezone.utc)
    first = report_spreads[0]
    lines = [
        "# Backtest Report: 1-Minute Sell Scenarios 1-4",
        "",
        f"**Generated:** {now:%Y-%m-%d %H:%M} UTC by `scripts/run_sell_scenarios_backtest.py`  ",
        "**Strategy:** `SELL_STRATEGY_PROMPT.md` (trader decisions of 2026-10-25 in `plan.md` §9)  ",
        f"**Data:** `data/trading.db`, Exness MT4 USDCAD bid bars in UTC: {len(m1):,} 1m bars from "
        f"{m1[0].timestamp:%Y-%m-%d %H:%M} to {m1[-1].timestamp:%Y-%m-%d %H:%M} over {len(trading_days)} trading days; "
        f"the broker's own 5m ({len(htf['M5']):,}) and 15m ({len(htf['M15']):,}) bars  ",
        f"**Execution:** entry at the {'next 1m bar open' if params.entry_fill == 'next_bar_open' else 'close of B3'}; "
        "a short closes at the ask (bid + constant spread); SL and TP in one bar count as SL; no slippage; "
        "SL/TP only (no break-even, trailing or partial close)  ",
        f"**Risk:** {results[first].settings.risk_pct:.1f}% of balance per trade from "
        f"${results[first].settings.initial_balance:,.0f}; 1:{params.rr:g} reward:risk; "
        f"open positions: {'no limit' if params.max_open_positions is None else params.max_open_positions}  ",
        f"**Session:** {params.session_start_hour:02d}:00-{params.session_end_hour:02d}:00 UTC, Monday-Friday, "
        "on the open time of B3 (London, London-NY and NY)  ",
        "",
        "At 1:10 the break-even win rate is about 9.1% before costs, so long losing streaks are expected.",
        "R is measured on price. The commission column applies the live sizing rule (bridge/sizing.py R4): "
        "the $7/lot round-turn commission is part of the 1% risk, so a stop-out still costs 1R and a "
        "winner pays less than 10R.",
        "",
    ]
    for n, spread in enumerate(report_spreads, start=1):
        result = results[spread]
        clean = [t for t in result.trades if not t.held_through_feed_gap]
        gap_wins = sum(1 for t in result.trades if t.held_through_feed_gap and t.r_multiple > 0)
        wins = sum(1 for t in result.trades if t.r_multiple > 0)
        lines += [f"## {n}. Results by scenario, spread {spread:.1f} pips", ""]
        lines += _stats_table(
            scenario_stats(result) + [summarize("Total without feed-gap trades", clean, result.settings.risk_pct)]
        )
        lines += [
            "",
            f"{len(result.trades) - len(clean)} trade(s) stayed open through a recording gap, so their exit was "
            f"never observed; {gap_wins} of the {wins} winners are among them (see Caveats).",
            "",
            f"Journal: `{journals[spread].relative_to(WORKSPACE_ROOT).as_posix()}`",
            "",
        ]

    section = len(report_spreads) + 1
    lines += [f"## {section}. Spread sensitivity (all scenarios)", ""]
    lines += ["| Spread (pips) | Trades | Win rate | Net R | Max DD (%) | Net R after commission |", "|---|---|---|---|---|---|"]
    for spread in sorted(results):
        total = scenario_stats(results[spread])[-1]
        lines.append(
            f"| {spread:.1f} | {total.trades} | {total.win_rate_pct:.1f}% | {total.net_r:+.1f} | "
            f"{total.max_dd_pct:.1f}% | {total.net_r_after_commission:+.1f} |"
        )

    lines += ["", f"## {section + 1}. No position limit (your setting) vs one position at a time (spec default)", ""]
    lines += [
        "| Spread (pips) | Open positions | Trades | Win rate | Net R | Max DD (%) | Net R without feed-gap trades "
        "| Skipped: position open |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for spread in report_spreads:
        for label, result in (("no limit", results[spread]), ("1", one_position[spread])):
            total = scenario_stats(result)[-1]
            clean_r = sum(t.r_multiple for t in result.trades if not t.held_through_feed_gap)
            blocked = sum(1 for s in result.skips if s.reason is SkipReason.POSITION_OPEN)
            lines.append(
                f"| {spread:.1f} | {label} | {total.trades} | {total.win_rate_pct:.1f}% | {total.net_r:+.1f} | "
                f"{total.max_dd_pct:.1f}% | {clean_r:+.1f} | {blocked} |"
            )

    lines += ["", f"## {section + 2}. Skipped signals", ""]
    lines += ["| Reason | " + " | ".join(f"Spread {s:.1f}" for s in report_spreads) + " |", "|---|" + "---|" * len(report_spreads)]
    for reason in SkipReason:
        counts = [sum(1 for s in results[spread].skips if s.reason is reason) for spread in report_spreads]
        lines.append(f"| {reason.value} | " + " | ".join(str(c) for c in counts) + " |")

    sample = _sample(results[first].trades, SAMPLE_TRADES)
    lines += ["", f"## {section + 3}. Sample trades (spread {first:.1f} pips)", ""]
    lines += [
        "Check these on the chart: X and Y are the HTF pair, conf is when Y closed (the setup arms), "
        "A-B3 are the 1m candles and entry is the next bar's open. Dates are month-day.",
        "",
    ]
    lines += _sample_rows(sample)

    gap_trades = [t for t in results[first].trades if t.held_through_feed_gap]
    end_trades = [t for t in results[first].trades if t.exit_reason == "END_OF_DATA"]
    lines += [
        "",
        f"## {section + 4}. Caveats",
        "",
        "- The history is the Exness MT4 feed, not TradingView FXCM. With zero equal-top tolerance an equal "
        "top on one feed may not be one on the other, so a few trades will not match the FXCM chart exactly. "
        "`docs/qa/AK_Sell_Scenarios_TradingView.pine` runs the same rules on the FXCM chart.",
        "- The 1m history was recorded only while the bridge ran, so it has overnight gaps. No 1m sequence "
        f"spans a gap longer than {params.max_1m_gap_minutes} minutes, and no fill is simulated across one. "
        f"{len(gap_trades)} trade(s) at spread {first:.1f} stayed open through a gap: their exit is the first "
        "recorded bar after it, at the SL/TP level (or the bar's open when it opened through the SL). "
        "They are marked `held_through_feed_gap` in the journal and left out of the \"without feed-gap trades\" rows.",
        "- A sell is skipped when the ask at the fill is already at or above the SL (FILL_AT_OR_ABOVE_SL): "
        "MT4 rejects such a stop. With spread 0 this is the spec's \"fill at or above SL\" rule.",
        f"- {len(end_trades)} trade(s) at spread {first:.1f} were still open at the end of the data and are "
        "closed at the last ask (END_OF_DATA, fractional R).",
        "- No spread history is stored, so spread is a constant per run; the sensitivity table shows its effect.",
        f"- {len(trading_days)} trading days is a small sample: treat per-scenario figures as anecdotal.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the 1-minute Sell Scenarios 1-4 on recorded USDCAD data.")
    parser.add_argument("--db", type=Path, default=WORKSPACE_ROOT / "data" / "trading.db", help="SQLite database")
    parser.add_argument("--spreads", default="0.0,0.5", help="Comma-separated constant spreads (pips) for the full report")
    parser.add_argument("--entry-fill", choices=("next_bar_open", "b3_close"), default="next_bar_open")
    parser.add_argument("--out-dir", type=Path, default=WORKSPACE_ROOT / "docs" / "qa", help="Report and journal folder")
    args = parser.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database not found: {args.db}")
    m1 = load_db_candles(args.db, "M1")
    if not m1:
        raise SystemExit(f"No USDCAD 1m candles in {args.db}")
    end = m1[-1].timestamp + M1
    htf = {tf: [c for c in load_db_candles(args.db, tf) if c.timestamp < end] for tf in ("M5", "M15")}

    params = SellScenarioParams(entry_fill=args.entry_fill)
    report_spreads = [float(s) for s in args.spreads.split(",") if s.strip()]
    spreads = sorted(set(report_spreads) | set(SENSITIVITY_SPREADS))
    results = {s: run_sell_backtest(m1, htf, params, SellBacktestSettings(spread_pips=s)) for s in spreads}
    one_position = {
        s: run_sell_backtest(m1, htf, replace(params, max_open_positions=1), SellBacktestSettings(spread_pips=s))
        for s in report_spreads
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    journals: Dict[float, Path] = {}
    for spread in report_spreads:
        journals[spread] = args.out_dir / f"sell-scenarios-journal-spread-{spread:.1f}.csv"
        write_journal(results[spread], journals[spread])
    report_path = args.out_dir / "sell-scenarios-backtest-report.md"
    report_path.write_text(
        render_report(m1, htf, params, report_spreads, results, one_position, journals), encoding="utf-8"
    )

    for spread in report_spreads:
        print(f"\nSpread {spread:.1f} pips")
        print("\n".join(_stats_table(scenario_stats(results[spread]))))
    print(f"\n[OK] Report: {report_path}")
    for path in journals.values():
        print(f"[OK] Journal: {path}")


if __name__ == "__main__":
    main()
