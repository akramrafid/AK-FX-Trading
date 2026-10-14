"""Tests for AK Forex exact 1% risk sizing and order execution.

Covers all 8 required test scenarios from the specification:
1. History replay (4 trades from 14 Oct USDCAD history reproducing P/L and commissions)
2. Sizing (balance 10,000, SELL 1.42130, SL 1.42150, tick_value ~ 0.7036 -> lots 4.74, expected loss <= $100.00)
3. Fresh balance (two consecutive signals with balance changed; second uses fresh balance)
4. Balance not equity (open floating loss present; sizing strictly uses balance)
5. Rounding (raw 4.746 sends 4.74, never 4.75)
6. Skips (risk below min lot sends no order and logs MIN_LOT_EXCEEDS_RISK; stale/unreadable balance sends no order)
7. Order shape (single request carrying SL and TP; sell SL above quote, buy SL below; second send blocked)
8. Realized risk (simulated fill 0.5 pip worse than quote logs RISK_DEVIATION)
"""

import json
import logging
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from bridge.dwx_client import DWXClient
from bridge.executor import BridgeExecutor
from bridge.sizing import (
    PositionSizer,
    read_r1_account_balance,
    calculate_r2_risk_amount,
    calculate_r3_quote_distance,
    get_r4_tick_value,
    calculate_r4_per_lot_loss,
    calculate_r5_lot_size,
    prepare_r6_order_prices,
    calculate_r8_realized_risk,
    format_r8_order_record,
)
from config import (
    RISK_PERCENT,
    COMMISSION_PER_LOT_ROUND_TURN,
    A1_ACCOUNT_CURRENCY,
    A2_COMMISSION_PER_LOT_ROUND_TURN,
    A3_RISK_BASIS_IS_BALANCE,
    A4_NO_POST_ENTRY_MODIFICATIONS,
)
from engine.rule_engine import TradeSignal, Direction, Candle


class TestExactRiskSizing(unittest.TestCase):
    """Test suite strictly validating Rules R1 through R8 and the 8 required tests."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="test_exact_risk_")
        self.client = DWXClient(mt4_files_dir=self.temp_dir, initial_backoff_ms=10, max_backoff_ms=100)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Test 1: History Replay
    # -------------------------------------------------------------------------
    def test_1_history_replay(self) -> None:
        """With P/L_USD = lots * 100000 * price_diff / close_price and commission 7.00/lot,
        the four trades must reproduce -55.45, -68.70, 0.00, and -42.91 within $0.02,
        and -267.09 in total including commission.
        """
        trades = [
            # (trade_type, entry, close, lots, expected_price_pl, expected_comm, expected_all_in)
            ("BUY", Decimal("1.42130"), Decimal("1.42110"), Decimal("3.94"), Decimal("-55.45"), Decimal("-27.58"), Decimal("-83.03")),
            ("SELL", Decimal("1.42114"), Decimal("1.42135"), Decimal("4.65"), Decimal("-68.70"), Decimal("-32.55"), Decimal("-101.25")),
            ("SELL", Decimal("1.42195"), Decimal("1.42195"), Decimal("3.26"), Decimal("0.00"), Decimal("-22.82"), Decimal("-22.82")),
            ("BUY", Decimal("1.42167"), Decimal("1.42142"), Decimal("2.44"), Decimal("-42.91"), Decimal("-17.08"), Decimal("-59.99")),
        ]

        total_price_pl = Decimal("0.00")
        total_commission = Decimal("0.00")
        total_all_in = Decimal("0.00")

        for trade_type, entry, close, lots, exp_price_pl, exp_comm, exp_all_in in trades:
            if trade_type == "BUY":
                price_diff = close - entry
            else:
                price_diff = entry - close

            # P/L_USD = lots * 100000 * price_diff / close_price
            calc_price_pl = (lots * Decimal("100000") * price_diff) / close
            calc_price_pl = calc_price_pl.quantize(Decimal("0.01"))
            calc_comm = -(lots * Decimal(str(COMMISSION_PER_LOT_ROUND_TURN))).quantize(Decimal("0.01"))
            calc_all_in = calc_price_pl + calc_comm

            # Verify within $0.02
            self.assertAlmostEqual(float(calc_price_pl), float(exp_price_pl), delta=0.02)
            self.assertAlmostEqual(float(calc_comm), float(exp_comm), delta=0.02)
            self.assertAlmostEqual(float(calc_all_in), float(exp_all_in), delta=0.02)

            total_price_pl += calc_price_pl
            total_commission += calc_comm
            total_all_in += calc_all_in

        # Total checks
        self.assertAlmostEqual(float(total_commission), -100.03, delta=0.02)
        self.assertAlmostEqual(float(total_all_in), -267.09, delta=0.02)

    # -------------------------------------------------------------------------
    # Test 2: Sizing Calculation
    # -------------------------------------------------------------------------
    def test_2_sizing_10k_balance(self) -> None:
        """Balance 10,000, SELL 1.42130, SL 1.42150, tick_value ~ 0.7036
        -> lots 4.74, expected loss <= $100.00.
        """
        balance = Decimal("10000.00")
        quote = Decimal("1.42130")
        sl = Decimal("1.42150")
        tick_size = Decimal("0.00001")

        # R2
        risk_amount = calculate_r2_risk_amount(balance, Decimal("1.0"))
        self.assertEqual(risk_amount, Decimal("100.00"))

        # R3
        _q, distance = calculate_r3_quote_distance(quote, sl)
        self.assertEqual(distance, Decimal("0.00020"))

        # R4
        tick_value = get_r4_tick_value("USDCAD", quote, Decimal("100000"), tick_size)
        self.assertAlmostEqual(float(tick_value), 0.70358, places=4)

        per_lot_loss = calculate_r4_per_lot_loss(
            distance=distance,
            tick_size=tick_size,
            tick_value=tick_value,
            commission_per_lot=Decimal("7.00"),
        )
        # 20 points * 0.7035812... + 7.00 = 14.0716... + 7.00 = ~21.0716
        self.assertAlmostEqual(float(per_lot_loss), 21.0716, places=3)

        # R5
        lots_sent, lots_raw, achieved_risk_pct, status = calculate_r5_lot_size(
            risk_amount=risk_amount,
            per_lot_loss=per_lot_loss,
            lot_step=Decimal("0.01"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("50.00"),
            balance=balance,
        )

        self.assertEqual(lots_sent, Decimal("4.74"))
        self.assertAlmostEqual(float(lots_raw), 4.7457, places=3)

        expected_loss = lots_sent * per_lot_loss
        self.assertLessEqual(expected_loss, Decimal("100.00"))
        self.assertAlmostEqual(float(expected_loss), 99.88, delta=0.05)

        # R6: TP at 10x SL distance
        _q_r, _sl_r, tp_r = prepare_r6_order_prices(quote, sl, "SELL", rr_multiple=10, digits=5)
        self.assertEqual(tp_r, Decimal("1.41930"))

    # -------------------------------------------------------------------------
    # Test 3: Fresh Balance Between Consecutive Signals
    # -------------------------------------------------------------------------
    def test_3_fresh_balance_between_signals(self) -> None:
        """Two consecutive signals with balance changed between them;
        the second order uses the new balance.
        """
        now = datetime.now(timezone.utc)
        self.client.write_mock_account(balance=10000.00, equity=10000.00, timestamp=now)
        self.client.write_mock_market_data("USDCAD", bid=1.42130, ask=1.42132)

        executor = BridgeExecutor(
            symbol="USDCAD",
            dwx_client=self.client,
            exact_risk_sizing=True,
            risk_percent=Decimal("1.0"),
            confirmation_timeout_sec=0.01,
        )

        sig1 = TradeSignal(
            direction="SELL",
            entry_price=1.42130,
            stop_loss=1.42150,
            take_profit=1.41930,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now,
        )
        rec1 = executor._execute_signal(sig1)
        self.assertEqual(rec1.lots, Decimal("4.74"))

        # Now balance increases to 12,000.00
        now2 = now + timedelta(seconds=1)
        self.client.write_mock_account(balance=12000.00, equity=12000.00, timestamp=now2)

        sig2 = TradeSignal(
            direction="SELL",
            entry_price=1.42130,
            stop_loss=1.42150,
            take_profit=1.41930,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now2,
        )
        rec2 = executor._execute_signal(sig2)
        # Risk amount 120 / 21.0716 = 5.6948 -> 5.69 lots
        self.assertEqual(rec2.lots, Decimal("5.69"))

    # -------------------------------------------------------------------------
    # Test 4: Balance Not Equity
    # -------------------------------------------------------------------------
    def test_4_balance_not_equity(self) -> None:
        """Open floating loss present; the sizing must still use balance."""
        now = datetime.now(timezone.utc)
        # Balance = 10,000, Equity = 8,500 (1,500 floating loss)
        self.client.write_mock_account(balance=10000.00, equity=8500.00, timestamp=now)
        self.client.write_mock_market_data("USDCAD", bid=1.42130, ask=1.42132)

        executor = BridgeExecutor(
            symbol="USDCAD",
            dwx_client=self.client,
            exact_risk_sizing=True,
            risk_percent=Decimal("1.0"),
            confirmation_timeout_sec=0.01,
        )

        sig = TradeSignal(
            direction="SELL",
            entry_price=1.42130,
            stop_loss=1.42150,
            take_profit=1.41930,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now,
        )
        rec = executor._execute_signal(sig)
        # Sizing should be based on 10,000 balance ($100 risk -> 4.74 lots), NOT 8,500 ($85 risk -> 4.03 lots)
        self.assertEqual(rec.lots, Decimal("4.74"))

    # -------------------------------------------------------------------------
    # Test 5: Rounding
    # -------------------------------------------------------------------------
    def test_5_lot_rounding_down(self) -> None:
        """Raw 4.746 sends 4.74, never 4.75."""
        risk_amount = Decimal("100.00")
        # Construct per_lot_loss such that 100 / per_lot_loss = 4.746...
        per_lot_loss = Decimal("100.00") / Decimal("4.746")

        lots_sent, lots_raw, _achieved, _status = calculate_r5_lot_size(
            risk_amount=risk_amount,
            per_lot_loss=per_lot_loss,
            lot_step=Decimal("0.01"),
        )
        self.assertEqual(lots_sent, Decimal("4.74"))
        self.assertAlmostEqual(float(lots_raw), 4.746, places=3)

    # -------------------------------------------------------------------------
    # Test 6: Skips (Min lot & Stale/Unreadable Balance)
    # -------------------------------------------------------------------------
    def test_6_skips(self) -> None:
        """Risk below min lot sends no order and logs MIN_LOT_EXCEEDS_RISK;
        unreadable or stale balance sends no order.
        """
        now = datetime.now(timezone.utc)
        # Case A: Small account where calculated lot < min_lot (0.01)
        self.client.write_mock_account(balance=10.00, equity=10.00, timestamp=now)
        self.client.write_mock_market_data("USDCAD", bid=1.42130, ask=1.42132)

        executor = BridgeExecutor(
            symbol="USDCAD",
            dwx_client=self.client,
            exact_risk_sizing=True,
            risk_percent=Decimal("1.0"),
            confirmation_timeout_sec=0.01,
        )

        sig_small = TradeSignal(
            direction="SELL",
            entry_price=1.42130,
            stop_loss=1.42150,
            take_profit=1.41930,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now,
        )
        with self.assertLogs("bridge.sizing", level="WARNING") as cm:
            rec_small = executor._execute_signal(sig_small)
            self.assertEqual(rec_small.status, "REJECTED")
            self.assertIn("MIN_LOT_EXCEEDS_RISK", rec_small.rejection_reason)
            self.assertTrue(any("MIN_LOT_EXCEEDS_RISK" in msg for msg in cm.output))

        # Case B: Stale balance (> 5 seconds old)
        stale_time = now - timedelta(seconds=10)
        self.client.write_mock_account(balance=10000.00, equity=10000.00, timestamp=stale_time)

        sig_stale = TradeSignal(
            direction="SELL",
            entry_price=1.42130,
            stop_loss=1.42150,
            take_profit=1.41930,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now + timedelta(seconds=2),
        )
        with self.assertLogs("bridge.sizing", level="WARNING") as cm:
            rec_stale = executor._execute_signal(sig_stale)
            self.assertEqual(rec_stale.status, "REJECTED")
            self.assertIn("BALANCE_STALE", rec_stale.rejection_reason)
            self.assertTrue(any("BALANCE_STALE" in msg for msg in cm.output))

        # Case C: Unreadable balance (missing file or <= 0)
        self.client.write_mock_account(balance=-10.00, equity=-10.00, timestamp=now)
        sig_invalid = TradeSignal(
            direction="SELL",
            entry_price=1.42130,
            stop_loss=1.42150,
            take_profit=1.41930,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now + timedelta(seconds=3),
        )
        rec_invalid = executor._execute_signal(sig_invalid)
        self.assertEqual(rec_invalid.status, "REJECTED")
        self.assertIn("BALANCE_UNREADABLE", rec_invalid.rejection_reason)

    # -------------------------------------------------------------------------
    # Test 7: Order Shape
    # -------------------------------------------------------------------------
    def test_7_order_shape(self) -> None:
        """One request carrying SL and TP; sell SL above quote, buy SL below;
        second send for same signal blocked.
        """
        now = datetime.now(timezone.utc)
        self.client.write_mock_account(balance=10000.00, equity=10000.00, timestamp=now)
        self.client.write_mock_market_data("USDCAD", bid=1.42130, ask=1.42132)

        executor = BridgeExecutor(
            symbol="USDCAD",
            dwx_client=self.client,
            exact_risk_sizing=True,
            risk_percent=Decimal("1.0"),
            confirmation_timeout_sec=0.01,
        )

        # 1. SELL order check
        sell_sig = TradeSignal(
            direction="SELL",
            entry_price=1.42130,
            stop_loss=1.42150,
            take_profit=1.41930,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now,
        )
        rec_sell = executor._execute_signal(sell_sig)
        self.assertGreater(rec_sell.sl_price, rec_sell.entry_price)  # SELL SL above entry
        self.assertLess(rec_sell.tp_price, rec_sell.entry_price)     # SELL TP below entry

        # Verify command sent to DWX_Commands.txt carries both SL and TP in single request
        cmds = self.client.atomic_read(self.client.commands_file)
        lines = [line for line in cmds.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        cmd_obj = json.loads(lines[0])
        self.assertEqual(cmd_obj["action"], "OPEN")
        self.assertEqual(cmd_obj["type"], "SELL")
        self.assertEqual(cmd_obj["sl"], 1.42150)
        self.assertEqual(cmd_obj["tp"], 1.41930)

        # 2. Block duplicate send for same signal (idempotency)
        rec_dup = executor._execute_signal(sell_sig)
        self.assertIsNone(rec_dup)
        # Commands file still only has 1 command
        cmds_after = self.client.atomic_read(self.client.commands_file)
        lines_after = [line for line in cmds_after.splitlines() if line.strip()]
        self.assertEqual(len(lines_after), 1)

        # 3. BUY order check
        buy_sig = TradeSignal(
            direction="BUY",
            entry_price=1.42130,
            stop_loss=1.42110,
            take_profit=1.42330,
            risk_distance=0.00020,
            reward_distance=0.00200,
            reward_risk_ratio=10.0,
            timeframe="M5",
            timestamp=now + timedelta(seconds=1),
        )
        rec_buy = executor._execute_signal(buy_sig)
        self.assertLess(rec_buy.sl_price, rec_buy.entry_price)     # BUY SL below entry
        self.assertGreater(rec_buy.tp_price, rec_buy.entry_price)  # BUY TP above entry

    # -------------------------------------------------------------------------
    # Test 8: Realized Risk & Slippage Deviation
    # -------------------------------------------------------------------------
    def test_8_realized_risk_slippage_deviation(self) -> None:
        """A simulated fill 0.5 pip worse than the quote logs RISK_DEVIATION."""
        balance = Decimal("10000.00")
        quote = Decimal("1.42130")
        sl = Decimal("1.42150")  # 2 pips distance
        tick_size = Decimal("0.00001")
        tick_value = get_r4_tick_value("USDCAD", quote, Decimal("100000"), tick_size)
        commission_rate = Decimal("7.00")

        # Planned sizing at quote:
        distance_planned = Decimal("0.00020")
        per_lot_loss_planned = calculate_r4_per_lot_loss(distance_planned, tick_size, tick_value, commission_rate)
        lots_sent, _raw, planned_risk_pct, _ = calculate_r5_lot_size(
            risk_amount=Decimal("100.00"),
            per_lot_loss=per_lot_loss_planned,
            balance=balance,
        )
        self.assertEqual(lots_sent, Decimal("4.74"))

        # Case A: Fill exactly at quote (0 slippage)
        risk_pct, dev_pct, dev_flag, dev_cause = calculate_r8_realized_risk(
            balance=balance,
            fill_price=quote,
            sl=sl,
            direction="SELL",
            lots_sent=lots_sent,
            tick_size=tick_size,
            tick_value=tick_value,
            commission_rate=commission_rate,
            planned_risk_pct=planned_risk_pct,
            tolerance_pct=Decimal("5.0"),
            quote=quote,
        )
        self.assertFalse(dev_flag)
        self.assertEqual(dev_pct, Decimal("0.00"))

        # Case B: Fill 0.5 pip worse than quote (SELL filled at 1.42125, stop is 1.42150 -> 2.5 pips stop)
        worse_fill = Decimal("1.42125")
        with self.assertLogs("bridge.sizing", level="WARNING") as cm:
            risk_pct_slip, dev_pct_slip, dev_flag_slip, dev_cause_slip = calculate_r8_realized_risk(
                balance=balance,
                fill_price=worse_fill,
                sl=sl,
                direction="SELL",
                lots_sent=lots_sent,
                tick_size=tick_size,
                tick_value=tick_value,
                commission_rate=commission_rate,
                planned_risk_pct=planned_risk_pct,
                tolerance_pct=Decimal("5.0"),
                quote=quote,
            )
            self.assertTrue(dev_flag_slip)
            self.assertGreater(dev_pct_slip, Decimal("5.0"))
            self.assertIn("RISK_DEVIATION", dev_cause_slip)
            self.assertIn("slippage", dev_cause_slip)
            self.assertTrue(any("RISK_DEVIATION" in msg for msg in cm.output))


if __name__ == "__main__":
    unittest.main()
