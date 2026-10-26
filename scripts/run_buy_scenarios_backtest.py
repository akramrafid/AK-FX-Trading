"""scripts/run_buy_scenarios_backtest.py
Backtest the 1-minute Buy Scenarios 1-2 (BUY_STRATEGY_PROMPT.md) on the recorded USDCAD history,
alone and together with the Sell Scenarios under the no-hedging rule (STRATEGY_MODE=ak_scenarios).

Data: data/trading.db (read-only), loaded as scripts/run_sell_scenarios_backtest.py loads it.
Writes docs/qa/buy-scenarios-backtest-report.md, a buy journal CSV and a sell + buy journal CSV per
spread case (one row per trade and per skipped signal, times in UTC and UTC+6).

Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.ak_scenarios import SAME_BAR_CONFLICT, AkScenariosEngine, decision_side, no_hedging_params
from engine.buy_scenarios import BuyScenarioEngine, BuyScenarioParams, BuySkipReason
from engine.models import Candle
from engine.scenarios_backtest import (
    BUY_JOURNAL_COLUMNS,
    COMBINED_JOURNAL_COLUMNS,
    BacktestSettings,
    ScenariosBacktestResult,
    ScenarioTrade,
    journal_rows,
    run_scenarios_backtest,
    scenario_stats,
)
from engine.sell_scenarios import M1, UTC_PLUS_6, SellScenarioEngine, SellScenarioParams
from engine.sell_scenarios_backtest import summarize
from scripts.run_sell_scenarios_backtest import _hm, _stats_table, load_db_candles

SENSITIVITY_SPREADS = (0.0, 0.3, 0.5, 1.0)
SAMPLE_TRADES = 10


def buy_only(params: BuyScenarioParams) -> AkScenariosEngine:
    return AkScenariosEngine(buy=BuyScenarioEngine(params))


def sell_only() -> AkScenariosEngine:
    return AkScenariosEngine(sell=SellScenarioEngine(SellScenarioParams()))


def sell_and_buy(params: BuyScenarioParams) -> AkScenariosEngine:
    return AkScenariosEngine(
        sell=SellScenarioEngine(no_hedging_params(SellScenarioParams())),
        buy=BuyScenarioEngine(no_hedging_params(params)),
    )


def write_journal(result: ScenariosBacktestResult, path: Path, columns: Sequence[str], side: Optional[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(journal_rows(result, side))


def _rel(path: Path) -> str:
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def _hhmm(ts: datetime, tz: timezone) -> str:
    return f"{ts.astimezone(tz):%H:%M}"


def _doji_table(trades: Sequence[ScenarioTrade]) -> List[str]:
    lines = ["| Scenario | Trades | 0 dojis | 1 doji | 2 dojis |", "|---|---|---|---|---|"]
    groups = [(f"Scenario {n}", [t for t in trades if t.scenario == n]) for n in (1, 2)] + [("Total", list(trades))]
    for label, group in groups:
        counts = Counter(len(t.decision.run.doji_positions) for t in group)
        lines.append(f"| {label} | {len(group)} | {counts[0]} | {counts[1]} | {counts[2]} |")
    return lines


def _sample(trades: Sequence[ScenarioTrade], n: int) -> List[ScenarioTrade]:
    """Up to n trades, taken in turn from Scenarios 1 and 2 so both show up, then by entry time."""
    queues = {k: sorted((t for t in trades if t.scenario == k), key=lambda t: t.entry_time) for k in (1, 2)}
    picked: List[ScenarioTrade] = []
    while len(picked) < n and any(queues.values()):
        for k in (1, 2):
            if queues[k] and len(picked) < n:
                picked.append(queues[k].pop(0))
    return sorted(picked, key=lambda t: t.entry_time)


def _sample_rows(trades: Sequence[ScenarioTrade]) -> List[str]:
    lines = [
        "| # | Scen. | HTF setup | Times UTC (data feed) | Times UTC+6 (your TradingView) | Entry / SL / TP | Exit |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in trades:
        d = t.decision
        s, run = d.setup, d.run
        cells = []
        for tz in (timezone.utc, UTC_PLUS_6):
            cells.append(
                f"X {_hm(s.x.timestamp, tz)}, Y {_hhmm(s.y.timestamp, tz)}, conf {_hhmm(s.t_conf, tz)}; "
                f"prior run {_hhmm(run.prior_members[0].candle.timestamp, tz)}-"
                f"{_hhmm(run.prior_members[-1].candle.timestamp, tz)}; 1st {_hhmm(run.first.timestamp, tz)}, "
                f"signal {_hhmm(run.signal.timestamp, tz)}; entry {_hhmm(t.entry_time, tz)}, exit {_hm(t.exit_time, tz)}"
            )
        doji = "" if d.doji_positions == "none" else f", doji {d.doji_positions}"
        lines.append(
            f"| {t.trade_id} | B{d.scenario} | {s.timeframe} {s.pattern.value} (1m {d.ltf_type}{doji}) "
            f"| {cells[0]} | {cells[1]} | {t.entry_price:.5f} / {t.stop_loss:.5f} / {t.take_profit:.5f} "
            f"({t.risk_pips:.1f} pips) | {t.exit_reason} at {t.exit_price:.5f}, {t.r_multiple:+.2f}R |"
        )
    return lines


def _skip_counts(result: ScenariosBacktestResult, side: str) -> Counter:
    return Counter(s.reason for s in result.skips if decision_side(s.decision) == side)


def render_report(
    m1: Sequence[Candle],
    htf: Dict[str, List[Candle]],
    params: BuyScenarioParams,
    report_spreads: Sequence[float],
    buys: Dict[float, ScenariosBacktestResult],
    one_position: Dict[float, ScenariosBacktestResult],
    sells: Dict[float, ScenariosBacktestResult],
    combined: Dict[float, ScenariosBacktestResult],
    journals: Dict[str, Dict[float, Path]],
) -> str:
    trading_days = sorted({c.timestamp.date() for c in m1})
    now = datetime.now(timezone.utc)
    first = report_spreads[0]
    settings = buys[first].settings
    lines = [
        "# Backtest Report: 1-Minute Buy Scenarios 1-2",
        "",
        f"**Generated:** {now:%Y-%m-%d %H:%M} UTC by `scripts/run_buy_scenarios_backtest.py`  ",
        "**Strategy:** `BUY_STRATEGY_PROMPT.md` with the Mission Impossible 3-run (trader decisions of 2026-10-26 "
        "in `plan.md` §9)  ",
        f"**Data:** `data/trading.db`, Exness MT4 USDCAD bid bars in UTC: {len(m1):,} 1m bars from "
        f"{m1[0].timestamp:%Y-%m-%d %H:%M} to {m1[-1].timestamp:%Y-%m-%d %H:%M} over {len(trading_days)} trading days; "
        f"the broker's own 5m ({len(htf['M5']):,}) and 15m ({len(htf['M15']):,}) bars  ",
        f"**Execution:** buy at the {'close of the signal bar' if params.entry_fill == 'signal_close' else 'next 1m bar open'} "
        "plus the spread (a long fills at the ask); exits at the bid; SL and TP in one bar count as SL; no slippage; "
        "SL/TP only (no break-even, trailing or partial close)  ",
        f"**Risk:** {settings.risk_pct:.1f}% of balance per trade from ${settings.initial_balance:,.0f}; "
        f"1:{params.rr:g} reward:risk; open buys: {'no limit' if params.max_open_positions is None else params.max_open_positions}  ",
        f"**Session:** {params.session_start_hour:02d}:00-{params.session_end_hour:02d}:00 UTC, Monday-Friday, "
        "on the open time of the signal bar (London, London-NY and NY)  ",
        "",
        "At 1:10 the break-even win rate is about 9.1% before costs, so long losing streaks are expected.",
        "R is measured on price. The commission column applies the live sizing rule (bridge/sizing.py R4): "
        "the $7/lot round-turn commission is part of the 1% risk, so a stop-out still costs 1R and a "
        "winner pays less than 10R.",
        "",
    ]
    for n, spread in enumerate(report_spreads, start=1):
        result = buys[spread]
        clean = [t for t in result.trades if not t.held_through_feed_gap]
        gap_r = sum(t.r_multiple for t in result.trades if t.held_through_feed_gap)
        gap_wins = sum(1 for t in result.trades if t.held_through_feed_gap and t.r_multiple > 0)
        wins = sum(1 for t in result.trades if t.r_multiple > 0)
        lines += [f"## {n}. Buy results by scenario, spread {spread:.1f} pips", ""]
        lines += _stats_table(
            scenario_stats(result, "BUY") + [summarize("Total without feed-gap trades", clean, settings.risk_pct)]
        )
        lines += ["", "Trades by doji count in the run:", ""] + _doji_table(result.trades)
        lines += [
            "",
            f"{len(result.trades) - len(clean)} trade(s) stayed open through a recording gap, so their exit was "
            f"never observed; together they account for {gap_r:+.1f}R, and {gap_wins} of the {wins} winners are "
            "among them. A stop crossed during a gap is filled at the first recorded bar's open, which can be "
            "many R beyond the stop (see Caveats).",
            "",
            f"Journal: `{_rel(journals['buy'][spread])}`",
            "",
        ]

    section = len(report_spreads) + 1
    lines += [f"## {section}. Spread sensitivity (buys, all scenarios)", ""]
    lines += ["| Spread (pips) | Trades | Win rate | Net R | Max DD (%) | Net R after commission |", "|---|---|---|---|---|---|"]
    for spread in sorted(buys):
        total = scenario_stats(buys[spread], "BUY")[-1]
        lines.append(
            f"| {spread:.1f} | {total.trades} | {total.win_rate_pct:.1f}% | {total.net_r:+.1f} | "
            f"{total.max_dd_pct:.1f}% | {total.net_r_after_commission:+.1f} |"
        )

    lines += ["", f"## {section + 1}. No limit within the buy side (your setting) vs one position (spec default)", ""]
    lines += [
        "| Spread (pips) | Open buys | Trades | Win rate | Net R | Max DD (%) | Net R without feed-gap trades "
        "| Skipped: position open |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for spread in report_spreads:
        for label, result in (("no limit", buys[spread]), ("1", one_position[spread])):
            total = scenario_stats(result, "BUY")[-1]
            clean_r = sum(t.r_multiple for t in result.trades if not t.held_through_feed_gap)
            blocked = _skip_counts(result, "BUY")[BuySkipReason.POSITION_OPEN.value]
            lines.append(
                f"| {spread:.1f} | {label} | {total.trades} | {total.win_rate_pct:.1f}% | {total.net_r:+.1f} | "
                f"{total.max_dd_pct:.1f}% | {clean_r:+.1f} | {blocked} |"
            )

    lines += ["", f"## {section + 2}. Sell + buy together (STRATEGY_MODE=ak_scenarios, no hedging)", ""]
    lines += [
        "Sells use their own defaults (entry at the next bar's open, no limit within the side). While one side "
        "has a position open, the other side's signals are skipped; a sell and a buy on the same bar would both "
        "be skipped (SAME_BAR_CONFLICT).",
        "",
    ]
    for spread in report_spreads:
        result = combined[spread]
        rows = [
            summarize("Sell alone", sells[spread].trades, settings.risk_pct),
            summarize("Buy alone", buys[spread].trades, settings.risk_pct),
            summarize("Sell, with buys", [t for t in result.trades if t.side == "SELL"], settings.risk_pct),
            summarize("Buy, with sells", [t for t in result.trades if t.side == "BUY"], settings.risk_pct),
            summarize("Sell + buy", result.trades, settings.risk_pct),
        ]
        conflicts = sum(1 for s in result.skips if s.reason == SAME_BAR_CONFLICT) // 2
        lines += [f"### Spread {spread:.1f} pips", ""] + _stats_table(rows)
        lines += [
            "",
            f"Skipped by the no-hedging rule: {_skip_counts(result, 'SELL')['POSITION_OPEN']} sell(s) while a buy "
            f"was open, {_skip_counts(result, 'BUY')['POSITION_OPEN']} buy(s) while a sell was open. "
            f"Same-bar conflicts: {conflicts}.",
            "",
            f"Journal (both sides): `{_rel(journals['combined'][spread])}`",
            "",
        ]

    lines += [f"## {section + 3}. Skipped buy signals", ""]
    lines += ["| Reason | " + " | ".join(f"Spread {s:.1f}" for s in report_spreads) + " |", "|---|" + "---|" * len(report_spreads)]
    for reason in BuySkipReason:
        counts = [_skip_counts(buys[spread], "BUY")[reason.value] for spread in report_spreads]
        lines.append(f"| {reason.value} | " + " | ".join(str(c) for c in counts) + " |")

    sample = _sample(buys[first].trades, SAMPLE_TRADES)
    lines += ["", f"## {section + 4}. Sample buy trades (spread {first:.1f} pips)", ""]
    lines += [
        "Check these on the chart: X and Y are the HTF pair, conf is when Y closed (the setup arms), the prior run "
        "is the bearish run whose low the 1st candle equalled or swept, signal is the bar whose close places the buy. "
        "Dates are month-day; the other times are on the same day as the date before them.",
        "",
    ]
    lines += _sample_rows(sample)

    result = buys[first]
    gap_trades = [t for t in result.trades if t.held_through_feed_gap]
    end_trades = [t for t in result.trades if t.exit_reason == "END_OF_DATA"]
    lines += [
        "",
        f"## {section + 5}. Caveats",
        "",
        "- The history is the Exness MT4 feed, not TradingView FXCM. With exact-price equal lows (no tolerance) an "
        "equal low or a 3-run on one feed may not be one on the other, so some trades will not match the FXCM chart. "
        "`docs/qa/AK_Buy_Scenarios_TradingView.pine` runs the same rules on the FXCM chart.",
        "- The 1m history was recorded only while the bridge ran, so it has overnight gaps. No 3-run spans a gap "
        f"longer than {params.max_1m_gap_minutes} minutes. {len(gap_trades)} buy trade(s) at spread {first:.1f} "
        "stayed open through a gap: their exit is the first recorded bar after it. They are marked "
        "`held_through_feed_gap` and left out of the \"without feed-gap trades\" rows.",
        "- A buy is skipped when the bid at the fill is at or below the SL (FILL_AT_OR_BELOW_SL): MT4 rejects such a "
        "stop. With the signal-close fill the 1st candle is the run's lowest, so this cannot happen at spread 0.",
        f"- {len(end_trades)} buy trade(s) at spread {first:.1f} were still open at the end of the data and are "
        "closed at the last bid (END_OF_DATA, fractional R).",
        "- The live daily loss circuit breaker (MAX_DAILY_LOSS_PCT) is not simulated here; it can only stop trades.",
        "- No spread history is stored, so spread is a constant per run; the sensitivity table shows its effect.",
        f"- {len(trading_days)} trading days is a small sample: treat per-scenario figures as anecdotal.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the 1-minute Buy Scenarios 1-2 on recorded USDCAD data.")
    parser.add_argument("--db", type=Path, default=WORKSPACE_ROOT / "data" / "trading.db", help="SQLite database")
    parser.add_argument("--spreads", default="0.0,0.5", help="Comma-separated constant spreads (pips) for the full report")
    parser.add_argument("--entry-fill", choices=("signal_close", "next_bar_open"), default="signal_close")
    parser.add_argument("--out-dir", type=Path, default=WORKSPACE_ROOT / "docs" / "qa", help="Report and journal folder")
    args = parser.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database not found: {args.db}")
    m1 = load_db_candles(args.db, "M1")
    if not m1:
        raise SystemExit(f"No USDCAD 1m candles in {args.db}")
    end = m1[-1].timestamp + M1
    htf = {tf: [c for c in load_db_candles(args.db, tf) if c.timestamp < end] for tf in ("M5", "M15")}

    params = BuyScenarioParams(entry_fill=args.entry_fill)
    report_spreads = [float(s) for s in args.spreads.split(",") if s.strip()]
    spreads = sorted(set(report_spreads) | set(SENSITIVITY_SPREADS))

    def run(engine: AkScenariosEngine, spread: float) -> ScenariosBacktestResult:
        return run_scenarios_backtest(m1, htf, engine, BacktestSettings(spread_pips=spread))

    buys = {s: run(buy_only(params), s) for s in spreads}
    one_position = {s: run(buy_only(replace(params, max_open_positions=1)), s) for s in report_spreads}
    sells = {s: run(sell_only(), s) for s in report_spreads}
    combined = {s: run(sell_and_buy(params), s) for s in report_spreads}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    journals: Dict[str, Dict[float, Path]] = {"buy": {}, "combined": {}}
    for spread in report_spreads:
        journals["buy"][spread] = args.out_dir / f"buy-scenarios-journal-spread-{spread:.1f}.csv"
        write_journal(buys[spread], journals["buy"][spread], BUY_JOURNAL_COLUMNS, "BUY")
        journals["combined"][spread] = args.out_dir / f"ak-scenarios-journal-spread-{spread:.1f}.csv"
        write_journal(combined[spread], journals["combined"][spread], COMBINED_JOURNAL_COLUMNS, None)
    report_path = args.out_dir / "buy-scenarios-backtest-report.md"
    report_path.write_text(
        render_report(m1, htf, params, report_spreads, buys, one_position, sells, combined, journals), encoding="utf-8"
    )

    for spread in report_spreads:
        print(f"\nSpread {spread:.1f} pips")
        print("\n".join(_stats_table(scenario_stats(buys[spread], "BUY"))))
    print(f"\n[OK] Report: {report_path}")
    for paths in journals.values():
        for path in paths.values():
            print(f"[OK] Journal: {path}")


if __name__ == "__main__":
    main()
