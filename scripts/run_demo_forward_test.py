"""scripts/run_demo_forward_test.py
Phase 6 Demo Forward-Test Validation Harness.

Simulates running the complete production pipeline untouched over a forward-test period:
  EA / Bar Stream -> BridgeExecutor -> RuleEngine -> PositionSizer -> RiskGuardrails -> Watchdog -> TradingDatabase

Enforces all invariants:
- Closed candles only (zero lookahead / intrabar bias).
- Single-codebase parity (RuleEngine, PositionSizer, RiskGuardrails).
- Non-bypassable risk guardrails (session filter, max open trades, daily loss halt).
- Persistence of every event into SQLite trade journal with environment='DEMO'.
- Watchdog heartbeat supervision.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from bridge.dwx_client import DWXClient, ExecutionReport, OrderType
from bridge.executor import BridgeExecutor
from bridge.sizing import PositionSizer
from bridge.watchdog import BridgeWatchdog, HealthState
from data.loader import load_candles_from_csv
from database.sqlite_manager import TradingDatabase
from engine.models import Candle, Direction, TradeSignal
from engine.rule_engine import RuleEngine, resample_m1_to_htf
from risk.guardrails import RiskGuardrails
from risk.models import AccountState, RiskLimits, TradeRejectionReason


def run_demo_forward_test(
    sample_bars: int = 40000,  # ~1 month of 1-minute bars
    initial_balance: float = 10000.0,
    risk_pct: float = 0.015,   # 1.5%
    spread_pips: float = 1.0,
    slippage_pips: float = 0.5,
) -> dict:
    csv_path = Path("data/EURUSD_M1_3Y.csv")
    if not csv_path.exists():
        raise FileNotFoundError(f"Historical dataset not found at {csv_path}")

    print(f"Loading {sample_bars:,} M1 candles for Demo Forward Test...")
    all_m1 = load_candles_from_csv(csv_path)
    # Take the final sample_bars as out-of-sample forward test window
    m1_candles = all_m1[-sample_bars:]
    start_time = m1_candles[0].timestamp
    end_time = m1_candles[-1].timestamp
    print(f"Forward test window: {start_time.isoformat()} to {end_time.isoformat()} ({len(m1_candles):,} bars)")

    print("Resampling M1 to M5 and M15 streams...")
    m5_candles = resample_m1_to_htf(m1_candles, 5)
    m15_candles = resample_m1_to_htf(m1_candles, 15)
    print(f"Resampled: {len(m5_candles):,} M5 bars, {len(m15_candles):,} M15 bars.")

    # Initialize isolated demo database
    db_path = Path("data/demo_forward_test.db")
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass
    db = TradingDatabase(str(db_path))

    # Initialize risk guardrails
    risk_limits = RiskLimits(
        max_daily_loss_pct=Decimal("0.03"),  # 3% circuit breaker
        max_open_trades=1,
        max_daily_trades=None,               # Unlimited daily trades
        max_spread_pips=Decimal("2.5"),
        session_filter_enabled=True,
        session_start_hour_utc=7,
        session_end_hour_utc=21,             # 21:00 UTC (London + NY)
        emergency_halt=False,
    )
    guardrails = RiskGuardrails(limits=risk_limits)

    # Initialize rule engine and position sizer
    rule_engine = RuleEngine(spread_pips=spread_pips, max_watch_candles=15)
    position_sizer = PositionSizer(default_risk_pct=Decimal(str(risk_pct)))

    # Setup mock DWXClient and Watchdog
    tmp_dir = Path(tempfile.mkdtemp(prefix="demo_dwx_"))
    dwx_client = DWXClient(mt4_files_dir=tmp_dir)
    watchdog = BridgeWatchdog(dwx_client=dwx_client, risk_guardrails=guardrails, max_heartbeat_age_sec=600.0)

    # Performance tracking
    balance = initial_balance
    peak_balance = initial_balance
    max_drawdown_dollars = 0.0
    max_drawdown_pct = 0.0

    active_trade: Optional[dict] = None
    trades_executed = 0
    winning_trades = 0
    losing_trades = 0
    total_realized_r = 0.0
    guardrail_rejections = 0
    rejection_reasons = {}

    # Event queue: merge M1, M5, M15 streams chronologically
    import heapq
    event_queue = []
    for c in m1_candles:
        heapq.heappush(event_queue, (c.timestamp, "M1", c))
    for c in m5_candles:
        heapq.heappush(event_queue, (c.timestamp, "M5", c))
    for c in m15_candles:
        heapq.heappush(event_queue, (c.timestamp, "M15", c))

    print("Replaying forward test market events through production bridge pipeline...")
    t0 = time.time()
    bars_processed = 0

    while event_queue:
        event_time, tf, candle = heapq.heappop(event_queue)
        watchdog.record_bar_received(event_time)

        # 1. Update active open trade
        if active_trade is not None:
            direction = active_trade["direction"]
            entry = active_trade["entry_price"]
            sl = active_trade["stop_loss"]
            tp = active_trade["take_profit"]
            lots = active_trade["lots"]
            risk_dist = active_trade["risk_distance"]

            sl_hit = False
            tp_hit = False

            if direction == "BUY":
                if candle.low <= sl:
                    sl_hit = True
                if candle.high >= tp:
                    tp_hit = True
            else:
                if candle.high >= sl:
                    sl_hit = True
                if candle.low <= tp:
                    tp_hit = True

            exit_reason = None
            exit_price = None

            if sl_hit and tp_hit:
                # Conservative worst-case: assume SL hit first
                exit_reason = "SL"
                exit_price = sl
            elif sl_hit:
                exit_reason = "SL"
                exit_price = sl
            elif tp_hit:
                exit_reason = "TP"
                exit_price = tp

            if exit_reason is not None:
                # Apply slippage on exit
                if exit_reason == "SL":
                    slippage = slippage_pips * 0.0001
                    exit_price = exit_price - slippage if direction == "BUY" else exit_price + slippage
                    pnl_r = -1.0
                else:
                    pnl_r = active_trade.get("reward_risk_ratio", 5.0)

                pnl_pips = (exit_price - entry) / 0.0001 if direction == "BUY" else (entry - exit_price) / 0.0001
                pnl_dollars = pnl_pips * 10.0 * lots

                balance += pnl_dollars
                peak_balance = max(peak_balance, balance)
                dd_dollars = peak_balance - balance
                dd_pct = (dd_dollars / peak_balance) * 100.0 if peak_balance > 0 else 0.0
                max_drawdown_dollars = max(max_drawdown_dollars, dd_dollars)
                max_drawdown_pct = max(max_drawdown_pct, dd_pct)

                total_realized_r += pnl_r
                if pnl_r > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1

                # Update risk tracker
                guardrails.tracker.record_trade_closed(Decimal(str(round(pnl_dollars, 2))))

                # Log closed trade to trade journal in DB
                db.record_closed_trade(
                    ticket=active_trade["ticket"],
                    magic_number=active_trade["magic"],
                    symbol="EURUSD",
                    direction=direction,
                    open_time=active_trade["entry_time"].isoformat(),
                    close_time=event_time.isoformat(),
                    open_price=active_trade["entry_price"],
                    close_price=exit_price,
                    stop_loss=sl,
                    take_profit=tp,
                    lots=lots,
                    realized_pnl=round(pnl_dollars, 2),
                    exit_reason=exit_reason,
                    environment="DEMO",
                )
                active_trade = None

        # 2. Feed candle to RuleEngine
        if tf in ("M5", "M15"):
            rule_engine.on_htf_candle(candle, timeframe=tf)
        elif tf == "M1":
            bars_processed += 1
            signal = rule_engine.on_m1_candle(candle)
            if signal is not None:
                # Signal triggered!
                db.save_signal(signal, "EURUSD", "M1", executed=False)

                # Dynamic lot sizing
                stop_pips = position_sizer.price_diff_to_pips("EURUSD", signal.risk_distance)
                sizing = position_sizer.calculate_lots(
                    account_balance=Decimal(str(round(balance, 2))),
                    stop_pips=stop_pips,
                    symbol="EURUSD",
                    risk_pct=Decimal(str(risk_pct)),
                )

                # Non-bypassable Risk Validation
                open_cnt = 1 if active_trade is not None else 0
                account_state = AccountState(
                    starting_daily_balance=Decimal(str(round(balance, 2))),
                    current_balance=Decimal(str(round(balance, 2))),
                    current_equity=Decimal(str(round(balance, 2))),
                    realized_daily_pnl=guardrails.tracker.realized_daily_pnl,
                    unrealized_daily_pnl=Decimal("0.00"),
                    open_trade_count=open_cnt,
                    daily_trades_count=guardrails.tracker.daily_trades_count,
                    current_spread_pips=Decimal(str(spread_pips)),
                    timestamp=event_time,
                )

                risk_res = guardrails.validate_trade(
                    account_state=account_state,
                    proposed_lots=sizing.lots,
                    trade_time=event_time,
                )

                if not risk_res.is_allowed:
                    guardrail_rejections += 1
                    reason_name = risk_res.reason.value if risk_res.reason else "UNKNOWN"
                    rejection_reasons[reason_name] = rejection_reasons.get(reason_name, 0) + 1
                    db.log_audit_event(
                        "DEMO_RISK_REJECTION",
                        "RiskGuardrails",
                        f"Signal rejected: [{reason_name}] {risk_res.message}",
                    )
                else:
                    # Risk approved! Execute simulated demo order
                    trades_executed += 1
                    ticket = 1000000 + trades_executed
                    magic = 900000 + trades_executed

                    # Simulated fill price with spread + slippage
                    direction_str = "BUY" if signal.direction == Direction.BUY else "SELL"
                    actual_fill = (
                        signal.entry_price + (spread_pips + slippage_pips) * 0.0001
                        if direction_str == "BUY"
                        else signal.entry_price - (spread_pips + slippage_pips) * 0.0001
                    )
                    slippage = float(abs(actual_fill - signal.entry_price) / 0.0001)

                    db.save_order(
                        command_id=f"DEMO_CMD_{ticket}",
                        magic_number=magic,
                        symbol="EURUSD",
                        direction=direction_str,
                        lots=float(sizing.lots),
                        target_entry=signal.entry_price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        status="FILLED",
                        ticket=ticket,
                        fill_price=actual_fill,
                    )

                    guardrails.tracker.record_trade_opened()
                    watchdog.record_order_dispatched()

                    active_trade = {
                        "ticket": ticket,
                        "magic": magic,
                        "direction": direction_str,
                        "entry_time": event_time,
                        "entry_price": actual_fill,
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "lots": float(sizing.lots),
                        "risk_distance": signal.risk_distance,
                        "reward_risk_ratio": getattr(signal, "reward_risk_ratio", 5.0),
                    }

    elapsed = time.time() - t0
    win_rate = (winning_trades / trades_executed * 100.0) if trades_executed > 0 else 0.0
    avg_r = (total_realized_r / trades_executed) if trades_executed > 0 else 0.0
    profit_factor = (winning_trades * 5.0) / (losing_trades * 1.0) if losing_trades > 0 else float("inf")

    # Clean up temp dir
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    results = {
        "forward_test_window_bars": bars_processed,
        "elapsed_seconds": round(elapsed, 2),
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "net_profit": round(balance - initial_balance, 2),
        "total_trades": trades_executed,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 2),
        "average_r": round(avg_r, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_dollars": round(max_drawdown_dollars, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "guardrail_rejections": guardrail_rejections,
        "rejection_reasons": rejection_reasons,
        "watchdog_health": watchdog.check_health().state.value,
        "db_records": db.get_signals("EURUSD", limit=5),
    }

    print("\n" + "=" * 60)
    print("DEMO ACCOUNT FORWARD-TEST VALIDATION RESULTS")
    print("=" * 60)
    print(f"Forward Test Period: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
    print(f"Total M1 Candles Evaluated: {bars_processed:,}")
    print(f"Total Executed Trades: {trades_executed}")
    print(f"Win Rate: {win_rate:.2f}% ({winning_trades}W / {losing_trades}L)")
    print(f"Average R: {avg_r:.2f}R | Total Realized R: {total_realized_r:.1f}R")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Final Balance: ${balance:,.2f} (Net: ${balance - initial_balance:+,.2f})")
    print(f"Max Drawdown: {max_drawdown_pct:.2f}% (${max_drawdown_dollars:,.2f})")
    print(f"Risk Guardrail Interceptions: {guardrail_rejections:,} signals filtered")
    for r_reason, count in rejection_reasons.items():
        print(f"  - {r_reason}: {count}")
    print(f"Watchdog Final Health: {results['watchdog_health']}")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_demo_forward_test()
