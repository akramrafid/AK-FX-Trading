"""scripts/run_current_strategy_backtest.py
Production Backtest Runner for User's Active Live Strategy.

Strategy Fingerprint:
- Mode: strict_compliance (AK S1-S6 / B1-B6 rules)
- Sweep Detection: M5 and M15 liquidity wick sweeps (Variant A, Intrabar sweep enabled)
- Confirmation: 3 consecutive directional M1 candle closes
- Stop Loss: C1 wick extreme (ultra-tight invalidation distance)
- Take Profit: 1:10 Reward-to-Risk ratio (10.0R)
- Breakeven Rule: At +2.0R, Stop Loss moved to entry price
- Session Hours: 07:00 to 18:00 UTC
- Sizing: Dynamic 1% risk per trade based on equity curve
- Concurrency: Up to 5 concurrent open positions

Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import heapq
from pathlib import Path
import sqlite3
import sys
import time
from typing import List, Optional, Sequence, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.models import Candle
from engine.rule_engine import RuleEngine, resample_m1_to_htf
from engine.backtester import BacktestTrade, BacktestResult, BacktestConfig
from engine.metrics import calculate_metrics, PerformanceMetrics
from data.loader import load_candles_from_csv


def load_candles_from_db(symbol: str = "USDCAD") -> List[Candle]:
    """Load historical M1 candles recorded in trading.db."""
    db_path = Path("data/trading.db")
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT timestamp, open, high, low, close, volume 
        FROM candles 
        WHERE symbol LIKE ? AND timeframe='M1' 
        ORDER BY timestamp ASC
    """, (f"{symbol}%",)).fetchall()
    conn.close()

    seen = set()
    candles: List[Candle] = []
    for ts_str, o, h, l, c, v in rows:
        if ts_str in seen:
            continue
        seen.add(ts_str)
        try:
            dt = datetime.fromisoformat(ts_str)
        except Exception:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        candles.append(Candle(timestamp=dt, open=float(o), high=float(h), low=float(l), close=float(c), volume=float(v)))

    candles.sort(key=lambda x: x.timestamp)
    return candles


def run_strategy_backtest(
    candles: Sequence[Candle],
    symbol: str = "USDCAD",
    initial_balance: float = 5000.0,
    risk_pct: float = 1.0,
    pip_size: float = 0.0001,
    pip_value_per_lot: float = 7.14,
    spread_pips: float = 0.0,
    slippage_pips: float = 0.0,
    breakeven_r: float = 2.0,
    reward_risk_ratio: float = 10.0,
    max_open_trades: int = 5,
    session_filter: bool = True,
    session_start_hour: int = 7,
    session_end_hour: int = 18,
) -> BacktestResult:
    """Execute event-driven multi-timeframe backtest with exact strategy rules."""
    if not candles:
        return BacktestResult(config=BacktestConfig(initial_balance=initial_balance))

    m1 = list(candles)
    m5 = resample_m1_to_htf(m1, 5)
    m15 = resample_m1_to_htf(m1, 15)

    engine = RuleEngine.strict_compliance_preset(
        symbol=symbol,
        check_m5=True,
        check_m15=True,
    )
    engine.reward_risk_ratio = reward_risk_ratio

    # Priority queue event stream: M15 close (1) -> M5 close (2) -> M1 close (3)
    events = heapq.merge(
        ((c.timestamp + timedelta(minutes=15), 1, "M15", c) for c in m15),
        ((c.timestamp + timedelta(minutes=5), 2, "M5", c) for c in m5),
        ((c.timestamp + timedelta(minutes=1), 3, "M1", c) for c in m1),
        key=lambda x: (x[0], x[1])
    )

    balance = initial_balance
    slip = slippage_pips * pip_size
    spread = spread_pips * pip_size

    open_trades: List[dict] = []
    closed_trades: List[BacktestTrade] = []
    equity_curve: List[Tuple[datetime, float]] = [(m1[0].timestamp, balance)]
    trade_id = 0

    for close_time, priority, tf, bar in events:
        if tf in ("M5", "M15"):
            engine.on_htf_candle(bar, timeframe=tf)
        elif tf == "M1":
            # 1. Manage Active Positions on this M1 bar
            still_open: List[dict] = []
            for t in open_trades:
                t["bars_held"] += 1
                direction = t["direction"]
                sl = t["stop_loss"]
                tp = t["take_profit"]
                entry = t["entry_price"]
                risk_dist = t["risk_distance"]
                lots = t["lots"]

                # Breakeven Adjustment at +2.0R
                if not t["sl_moved_to_be"] and breakeven_r is not None:
                    if direction == "BUY":
                        be_price = entry + (breakeven_r * risk_dist)
                        if bar.high >= be_price:
                            t["stop_loss"] = entry
                            t["sl_moved_to_be"] = True
                            sl = entry
                    else:
                        be_price = entry - (breakeven_r * risk_dist)
                        if bar.low <= be_price:
                            t["stop_loss"] = entry
                            t["sl_moved_to_be"] = True
                            sl = entry

                # SL / TP Hit Detection
                exit_price = None
                exit_reason = None
                realized_r = 0.0

                if direction == "BUY":
                    sl_hit = bar.low <= sl
                    tp_hit = bar.high >= tp
                    if sl_hit and tp_hit:
                        exit_price = sl - slip
                        exit_reason = "BE" if t["sl_moved_to_be"] else "SL"
                        realized_r = 0.0 if t["sl_moved_to_be"] else -1.0
                    elif sl_hit:
                        exit_price = sl - slip
                        exit_reason = "BE" if t["sl_moved_to_be"] else "SL"
                        realized_r = 0.0 if t["sl_moved_to_be"] else -1.0
                    elif tp_hit:
                        exit_price = tp - slip
                        exit_reason = "TP"
                        realized_r = reward_risk_ratio
                else:  # SELL
                    sl_hit = bar.high >= sl
                    tp_hit = bar.low <= tp
                    if sl_hit and tp_hit:
                        exit_price = sl + slip
                        exit_reason = "BE" if t["sl_moved_to_be"] else "SL"
                        realized_r = 0.0 if t["sl_moved_to_be"] else -1.0
                    elif sl_hit:
                        exit_price = sl + slip
                        exit_reason = "BE" if t["sl_moved_to_be"] else "SL"
                        realized_r = 0.0 if t["sl_moved_to_be"] else -1.0
                    elif tp_hit:
                        exit_price = tp + slip
                        exit_reason = "TP"
                        realized_r = reward_risk_ratio

                if exit_price is not None:
                    if direction == "BUY":
                        pnl_pips = (exit_price - entry) / pip_size
                    else:
                        pnl_pips = (entry - exit_price) / pip_size

                    pnl_cash = pnl_pips * lots * pip_value_per_lot
                    balance += pnl_cash

                    closed_trades.append(
                        BacktestTrade(
                            trade_id=t["trade_id"],
                            direction=direction,
                            entry_time=t["entry_time"],
                            exit_time=bar.timestamp,
                            entry_price=entry,
                            exit_price=exit_price,
                            stop_loss=sl,
                            take_profit=tp,
                            lots=lots,
                            pnl_currency=pnl_cash,
                            pnl_pips=pnl_pips,
                            realized_r=realized_r,
                            exit_reason=exit_reason,
                            bars_held=t["bars_held"],
                        )
                    )
                    equity_curve.append((bar.timestamp, balance))
                else:
                    still_open.append(t)
            open_trades = still_open

            # 2. Check for New Signal on this M1 bar
            sig = engine.on_m1_candle(bar)
            if sig is not None:
                in_session = True
                if session_filter:
                    in_session = (session_start_hour <= bar.timestamp.hour < session_end_hour)

                if in_session and len(open_trades) < max_open_trades:
                    trade_id += 1
                    risk_dist = sig.risk_distance
                    risk_pips = risk_dist / pip_size
                    risk_cash = balance * (risk_pct / 100.0)
                    cost_per_lot = risk_pips * pip_value_per_lot
                    raw_lot = risk_cash / cost_per_lot if cost_per_lot > 0 else 0.01
                    lots = max(0.01, min(round(raw_lot, 2), 50.0))

                    exec_entry = (
                        sig.entry_price + spread + slip
                        if sig.direction == "BUY"
                        else sig.entry_price - slip
                    )

                    open_trades.append(
                        {
                            "trade_id": trade_id,
                            "direction": sig.direction,
                            "entry_time": bar.timestamp,
                            "entry_price": exec_entry,
                            "stop_loss": sig.stop_loss,
                            "take_profit": sig.take_profit,
                            "lots": lots,
                            "risk_distance": risk_dist,
                            "bars_held": 0,
                            "sl_moved_to_be": False,
                        }
                    )

    return BacktestResult(
        config=BacktestConfig(
            initial_balance=initial_balance,
            risk_pct=risk_pct,
            pip_size=pip_size,
            pip_value_per_lot=pip_value_per_lot,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
            max_concurrent_trades=max_open_trades,
            breakeven_trigger_r=breakeven_r,
        ),
        trades=closed_trades,
        equity_curve=equity_curve,
        initial_balance=initial_balance,
        final_balance=balance,
    )


def main():
    parser = argparse.ArgumentParser(description="Backtest runner for current live trading strategy.")
    parser.add_argument("--mode", choices=["usdcad", "3yr", "all"], default="all", help="Target dataset")
    parser.add_argument("--spread", type=float, default=0.0, help="Spread penalty in pips")
    parser.add_argument("--slippage", type=float, default=0.0, help="Slippage penalty in pips")
    args = parser.parse_args()

    print("================================================================================")
    print("BACKTEST: ACTIVE LIVE TRADING STRATEGY (STRICT COMPLIANCE 1:10 RR + BE @ 2R)")
    print("================================================================================")

    reports = []
    
    # 1. USDCAD Backtest (Live Recorded Data)
    if args.mode in ("usdcad", "all"):
        print("\n[1/2] Loading recorded USDCAD M1 candles from data/trading.db...")
        usdcad_candles = load_candles_from_db("USDCAD")
        print(f"Loaded {len(usdcad_candles):,} unique M1 bars ({usdcad_candles[0].timestamp} to {usdcad_candles[-1].timestamp}).")

        # Full recorded dataset
        print("\n--- Running USDCAD Full Recorded Dataset (Sept 25 - Oct 23, 2026) ---")
        t0 = time.time()
        res_usdcad_full = run_strategy_backtest(
            usdcad_candles,
            symbol="USDCAD",
            initial_balance=5000.0,
            risk_pct=1.0,
            pip_size=0.0001,
            pip_value_per_lot=7.14,
            spread_pips=args.spread,
            slippage_pips=args.slippage,
            breakeven_r=2.0,
            reward_risk_ratio=10.0,
            max_open_trades=5,
            session_filter=True,
        )
        print(f"Completed in {time.time() - t0:.2f}s.")
        m_usdcad_full = calculate_metrics(res_usdcad_full)
        print(m_usdcad_full.format_summary())

        # Oct 22-23 Live Week
        oct22_candles = [c for c in usdcad_candles if c.timestamp >= datetime(2026, 10, 22, tzinfo=timezone.utc)]
        print("\n--- Running USDCAD Live Trading Week (Oct 22 - 23, 2026) ---")
        t1 = time.time()
        res_usdcad_week = run_strategy_backtest(
            oct22_candles,
            symbol="USDCAD",
            initial_balance=5000.0,
            risk_pct=1.0,
            pip_size=0.0001,
            pip_value_per_lot=7.14,
            spread_pips=args.spread,
            slippage_pips=args.slippage,
            breakeven_r=2.0,
            reward_risk_ratio=10.0,
            max_open_trades=5,
            session_filter=True,
        )
        print(f"Completed in {time.time() - t1:.2f}s.")
        m_usdcad_week = calculate_metrics(res_usdcad_week)
        print(m_usdcad_week.format_summary())

        reports.append(("USDCAD Full Month", m_usdcad_full, len(usdcad_candles)))
        reports.append(("USDCAD Live Week (Oct 22-23)", m_usdcad_week, len(oct22_candles)))

    # 2. 3-Year Historical Backtest (EUR/USD)
    if args.mode in ("3yr", "all"):
        csv_path = Path("data/EURUSD_M1_3Y.csv")
        if csv_path.exists():
            print("\n[2/2] Loading 3-year EUR/USD M1 dataset (2021 - 2024)...")
            t2 = time.time()
            eur_candles = load_candles_from_csv(csv_path)
            print(f"Loaded {len(eur_candles):,} M1 bars in {time.time() - t2:.2f}s.")

            # Raw Baseline
            print("\n--- Running 3-Year Backtest (Raw Zero-Friction Baseline) ---")
            t3 = time.time()
            res_3yr_raw = run_strategy_backtest(
                eur_candles,
                symbol="EURUSD",
                initial_balance=5000.0,
                risk_pct=1.0,
                pip_size=0.0001,
                pip_value_per_lot=10.0,
                spread_pips=0.0,
                slippage_pips=0.0,
                breakeven_r=2.0,
                reward_risk_ratio=10.0,
                max_open_trades=5,
                session_filter=True,
            )
            print(f"Completed in {time.time() - t3:.2f}s.")
            m_3yr_raw = calculate_metrics(res_3yr_raw)
            print(m_3yr_raw.format_summary())
            reports.append(("3-Year EURUSD (Zero Friction)", m_3yr_raw, len(eur_candles)))

            # Realistic Broker Friction
            print("\n--- Running 3-Year Backtest (With Realistic 1.0 pip Spread + 0.5 pip Slippage) ---")
            t4 = time.time()
            res_3yr_frict = run_strategy_backtest(
                eur_candles,
                symbol="EURUSD",
                initial_balance=5000.0,
                risk_pct=1.0,
                pip_size=0.0001,
                pip_value_per_lot=10.0,
                spread_pips=1.0,
                slippage_pips=0.5,
                breakeven_r=2.0,
                reward_risk_ratio=10.0,
                max_open_trades=5,
                session_filter=True,
            )
            print(f"Completed in {time.time() - t4:.2f}s.")
            m_3yr_frict = calculate_metrics(res_3yr_frict)
            print(m_3yr_frict.format_summary())
            reports.append(("3-Year EURUSD (Realistic Friction)", m_3yr_frict, len(eur_candles)))

    # Save detailed report
    report_file = Path("docs/qa/current-strategy-backtest-report.md")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# Backtest Report: Current Active Strategy (Strict Compliance 1:10 R:R + BE @ 2R)\n\n")
        f.write(f"**Execution Timestamp:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  \n")
        f.write("**Strategy:** Multi-Timeframe M5/M15 Liquidity Sweep + M1 3-Candle Confirmation + C1 Extreme SL + 1:10 R:R + Breakeven @ 2R  \n")
        f.write("**Position Sizing:** Dynamic 1.0% Risk of Account Balance per trade  \n")
        f.write("**Session Window:** 07:00 – 18:00 UTC (1:00 PM – 12:00 AM Dhaka)  \n")
        f.write("**Max Concurrency:** 5 Concurrent Positions  \n\n")
        f.write("---\n\n")
        
        for name, m, bar_count in reports:
            f.write(f"## {name}\n")
            f.write(f"- **Bars Evaluated:** {bar_count:,} M1 candles\n")
            f.write(m.format_summary())
            f.write("\n---\n\n")
            
    print(f"\n[OK] Backtest report generated at: {report_file}")


if __name__ == "__main__":
    main()
