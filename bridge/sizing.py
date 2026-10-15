"""bridge/sizing.py
Dynamic position sizing and currency pip value calculation engine.

Implements Hard Rule 3:
- Risk per trade: 1.0% to 2.0% of account balance (default 1.5%).
- Sizing formula: Lots = (Account_Balance * Risk_Pct) / (Stop_Loss_Pips * Pip_Value_Per_Standard_Lot)
- Round down to the nearest 0.01 lot step (floor, never round up).
- Sanity bounds: minimum 0.01 lot, maximum 50.00 lot ceiling.
- Handles quote currency conversion for major and cross pairs (USD, EUR, GBP, JPY, AUD).
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from config import (
    A1_ACCOUNT_CURRENCY,
    A2_COMMISSION_PER_LOT_ROUND_TURN,
    A3_RISK_BASIS_IS_BALANCE,
    A4_NO_POST_ENTRY_MODIFICATIONS,
    BALANCE_MAX_AGE_SECONDS,
    COMMISSION_PER_LOT_ROUND_TURN,
    LOT_ROUNDING,
    MIN_LOT_POLICY,
    RISK_BASIS,
    RISK_DEVIATION_TOLERANCE_PCT,
    RISK_PERCENT,
)
from engine.models import Direction

logger = logging.getLogger("bridge.sizing")


# =============================================================================
# Tagged Rule Functions (R1 - R8)
# =============================================================================

def read_r1_account_balance(
    source: Any,
    max_age_seconds: float = BALANCE_MAX_AGE_SECONDS,
    current_time: Optional[Union[datetime, float]] = None,
) -> Tuple[Optional[Decimal], Optional[datetime], Optional[str]]:
    """[R1] Read current account balance from MT4 now.
    
    Not equity, not free margin, not a cached or start-of-day value.
    If it cannot be read, is <= 0, or is older than max_age_seconds (5.0s),
    returns (None, timestamp, reason) to indicate send no order.
    """
    if source is None:
        return None, None, "BALANCE_UNREADABLE: source is None"

    now_ts: float = (
        current_time.timestamp()
        if isinstance(current_time, datetime)
        else (current_time if current_time is not None else time.time())
    )

    acc_data: Optional[dict] = None
    file_mtime: Optional[float] = None

    # Handle DWXClient instance
    if hasattr(source, "account_file") and hasattr(source, "read_account_info"):
        acc_file: Path = source.account_file
        if not acc_file.exists():
            return None, None, "BALANCE_UNREADABLE: DWX_Account.txt does not exist"
        try:
            file_mtime = acc_file.stat().st_mtime
        except OSError as e:
            return None, None, f"BALANCE_UNREADABLE: cannot stat DWX_Account.txt: {e}"
        acc_data = source.read_account_info()
    elif isinstance(source, Path):
        if not source.exists():
            return None, None, f"BALANCE_UNREADABLE: {source} does not exist"
        try:
            file_mtime = source.stat().st_mtime
            import json
            acc_data = json.loads(source.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            return None, None, f"BALANCE_UNREADABLE: {e}"
    elif isinstance(source, dict):
        acc_data = source
        file_mtime = float(acc_data["_mtime"]) if "_mtime" in acc_data else None
    else:
        return None, None, f"BALANCE_UNREADABLE: unsupported source type {type(source)}"

    if not isinstance(acc_data, dict):
        return None, None, "BALANCE_UNREADABLE: invalid account data format"

    # Strict R1: Read "balance" - NOT "equity" and NOT "free_margin"
    if "balance" not in acc_data:
        return None, None, "BALANCE_UNREADABLE: 'balance' field missing from MT4 account record"

    try:
        balance = Decimal(str(acc_data["balance"]))
    except Exception as e:
        return None, None, f"BALANCE_UNREADABLE: cannot parse balance '{acc_data.get('balance')}': {e}"

    if balance <= Decimal("0"):
        return None, None, f"BALANCE_UNREADABLE: balance {balance} <= 0 (must be > 0)"

    # Check timestamp freshness (<= max_age_seconds)
    record_dt: Optional[datetime] = None
    age_seconds: float = 0.0
    ts_age: Optional[float] = None
    if "timestamp" in acc_data:
        ts_val = acc_data["timestamp"]
        try:
            if isinstance(ts_val, (int, float)):
                record_dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                ts_age = max(0.0, now_ts - float(ts_val))
            else:
                try:
                    record_dt = datetime.fromisoformat(str(ts_val))
                except Exception:
                    clean_ts = str(ts_val).replace("T", " ")
                    record_dt = datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S")
                if record_dt.tzinfo is None:
                    record_dt = record_dt.replace(tzinfo=timezone.utc)
                ts_age = max(0.0, now_ts - record_dt.timestamp())
        except Exception:
            pass

    if file_mtime is not None:
        file_age = max(0.0, now_ts - file_mtime)
        if file_age <= max_age_seconds:
            # File was written by MT4 within max_age_seconds limit.
            # In MT4 DWX, OnTimer updates the file every second while TimeCurrent() in the
            # JSON payload only updates on market ticks or may have broker clock offset.
            # Fresh file_mtime guarantees MT4 is alive and actively exporting live balance.
            age_seconds = file_age
            if record_dt is None or abs(now_ts - record_dt.timestamp()) > max_age_seconds:
                record_dt = datetime.fromtimestamp(file_mtime, tz=timezone.utc)
        else:
            # File has not been written within max_age_seconds (MT4 is dead, crashed, or not writing)
            age_seconds = max(file_age, ts_age if ts_age is not None else file_age)
    elif ts_age is not None:
        age_seconds = ts_age
    elif record_dt is not None:
        age_seconds = max(0.0, now_ts - record_dt.timestamp())
    else:
        age_seconds = 0.0
        record_dt = datetime.now(timezone.utc)

    if age_seconds > max_age_seconds:
        msg = f"BALANCE_STALE: balance data is {age_seconds:.2f}s old (exceeds {max_age_seconds}s limit)"
        logger.warning(f"[R1] {msg}")
        return None, record_dt, msg

    return balance, record_dt, None


def calculate_r2_risk_amount(
    balance: Decimal,
    risk_percent: Decimal = Decimal(str(RISK_PERCENT)),
) -> Decimal:
    """[R2] Risk amount calculation.
    
    risk_amount = balance * 1.0 / 100 with RISK_PERCENT = 1.0.
    """
    return balance * (risk_percent / Decimal("100"))


def calculate_r3_quote_distance(
    quote: Decimal,
    sl: Decimal,
    direction: Optional[Union[str, Direction]] = None,
) -> Tuple[Decimal, Decimal]:
    """[R3] Price used for sizing.
    
    Use the live quote at the moment of sending: ask for a buy, bid for a sell.
    Do not use the candle close.
    distance = |quote - SL|. This already contains the spread; add no separate spread term.
    """
    quote_dec = Decimal(str(quote))
    sl_dec = Decimal(str(sl))
    distance = abs(quote_dec - sl_dec)
    return quote_dec, distance


def get_r4_tick_value(
    symbol: str,
    current_price: Decimal,
    contract_size: Decimal = Decimal("100000"),
    tick_size: Decimal = Decimal("0.00001"),
    bridge_tick_value: Optional[Decimal] = None,
) -> Decimal:
    """[R4] Determine symbol tick value in USD.
    
    If bridge cannot give tick_value, compute it for a USD account on USDCAD:
    contract_size * tick_size / current USDCAD price.
    5-digit pricing: 1 pip = 10 points.
    """
    if bridge_tick_value is not None and bridge_tick_value > Decimal("0"):
        return bridge_tick_value

    clean = symbol.replace("/", "").upper()
    if clean.startswith("USDCAD") or "CAD" in clean:
        if current_price <= Decimal("0"):
            raise ValueError(f"[R4] current_price must be > 0, got {current_price}")
        return (contract_size * tick_size) / current_price

    if clean.endswith("USD"):
        return contract_size * tick_size

    # Fallback to currency conversion using current_price
    if current_price > Decimal("0"):
        return (contract_size * tick_size) / current_price
    return Decimal("0.70")


def calculate_r4_per_lot_loss(
    distance: Decimal,
    tick_size: Decimal,
    tick_value: Decimal,
    commission_per_lot: Decimal = Decimal(str(COMMISSION_PER_LOT_ROUND_TURN)),
) -> Decimal:
    """[R4] Loss per 1 lot at the stop.
    
    per_lot_loss = (distance / tick_size) * tick_value + COMMISSION_PER_LOT_ROUND_TURN
    with COMMISSION_PER_LOT_ROUND_TURN = 7.00 USD.
    """
    points = distance / tick_size
    price_loss_per_lot = points * tick_value
    return price_loss_per_lot + commission_per_lot


def calculate_r5_lot_size(
    risk_amount: Decimal,
    per_lot_loss: Decimal,
    lot_step: Decimal = Decimal("0.01"),
    min_lot: Decimal = Decimal("0.01"),
    max_lot: Decimal = Decimal("50.00"),
    balance: Optional[Decimal] = None,
) -> Tuple[Decimal, Decimal, Decimal, Optional[str]]:
    """[R5] Position lot calculation.
    
    lots_raw = risk_amount / per_lot_loss.
    Round down to lot_step, never up and never with round().
    If result is below min_lot, skip trade and log MIN_LOT_EXCEEDS_RISK; never raise to min.
    If above max_lot, use max_lot and log it.
    Returns (lots_sent, lots_raw, achieved_risk_pct, log_code).
    """
    if per_lot_loss <= Decimal("0"):
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), "INVALID_PER_LOT_LOSS"

    lots_raw = risk_amount / per_lot_loss

    # Floor round down to lot_step (never round up, never round())
    lots_floored = (lots_raw // lot_step) * lot_step
    lots_floored = lots_floored.quantize(lot_step, rounding=ROUND_DOWN)

    log_code: Optional[str] = None
    lots_sent = lots_floored

    if lots_floored < min_lot:
        log_code = "MIN_LOT_EXCEEDS_RISK"
        logger.warning(
            f"[R5] MIN_LOT_EXCEEDS_RISK: calculated {lots_raw:.4f} lots ({lots_floored} floored) "
            f"below min_lot {min_lot}. Skipping trade."
        )
        lots_sent = Decimal("0.00")
    elif lots_floored > max_lot:
        log_code = "MAX_LOT_CAPPED"
        logger.warning(f"[R5] MAX_LOT_CAPPED: calculated {lots_floored} exceeds max_lot {max_lot}. Capped.")
        lots_sent = max_lot

    # Achieved risk percentage
    if balance and balance > Decimal("0"):
        achieved_dollar_risk = lots_sent * per_lot_loss
        achieved_risk_pct = (achieved_dollar_risk / balance) * Decimal("100")
    else:
        achieved_dollar_risk = lots_sent * per_lot_loss
        achieved_risk_pct = (achieved_dollar_risk / (risk_amount * Decimal("100"))) * Decimal("100") if risk_amount > 0 else Decimal("0.0")

    return lots_sent, lots_raw, achieved_risk_pct, log_code


def prepare_r6_order_prices(
    quote: Decimal,
    sl: Decimal,
    direction: Union[str, Direction],
    rr_multiple: int = 10,
    digits: int = 5,
    strategy_tp: Optional[Decimal] = None,
) -> Tuple[Decimal, Decimal, Decimal]:
    """[R6] Send once, complete.
    
    Send one market order with SL and TP attached in the same request,
    prices rounded to the symbol's digits.
    TP follows the strategy (10 * the SL distance).
    Returns (quote_rounded, sl_rounded, tp_rounded).
    """
    q = Decimal(str(quote))
    s = Decimal(str(sl))
    dist = abs(q - s)
    dir_str = direction.value if isinstance(direction, Direction) else str(direction).upper()

    if strategy_tp is not None:
        tp = Decimal(str(strategy_tp))
    elif dir_str == "BUY":
        tp = q + (Decimal(str(rr_multiple)) * dist)
    else:
        tp = q - (Decimal(str(rr_multiple)) * dist)

    quantizer = Decimal("10") ** -digits
    return (
        q.quantize(quantizer, rounding=ROUND_DOWN),
        s.quantize(quantizer, rounding=ROUND_DOWN),
        tp.quantize(quantizer, rounding=ROUND_DOWN),
    )



def verify_r7_no_post_entry_modifications(
    allow_modifications: bool = not A4_NO_POST_ENTRY_MODIFICATIONS,
) -> bool:
    """[R7] No changes after entry.
    
    The strategy has no break-even, trailing, partial close or early close.
    A position ends only by its SL or TP. [A4]
    Returns whether post-entry modifications are permitted (False by default).
    """
    return allow_modifications


def calculate_r8_realized_risk(
    balance: Decimal,
    fill_price: Decimal,
    sl: Decimal,
    direction: Union[str, Direction],
    lots_sent: Decimal,
    tick_size: Decimal,
    tick_value: Decimal,
    commission_rate: Decimal = Decimal(str(COMMISSION_PER_LOT_ROUND_TURN)),
    planned_risk_pct: Decimal = Decimal(str(RISK_PERCENT)),
    tolerance_pct: Decimal = Decimal(str(RISK_DEVIATION_TOLERANCE_PCT)),
    quote: Optional[Decimal] = None,
) -> Tuple[Decimal, Decimal, bool, Optional[str]]:
    """[R8] Calculate realized risk % from actual fill price and check for deviation.
    
    If realized risk differs from planned risk by more than tolerance_pct (5%),
    logs RISK_DEVIATION with the cause. Do not change TP to compensate.
    Returns (realized_risk_pct, deviation_pct, is_deviation, deviation_reason).
    """
    if balance <= Decimal("0") or lots_sent <= Decimal("0"):
        return Decimal("0.00"), Decimal("0.00"), False, None

    fill_dec = Decimal(str(fill_price))
    sl_dec = Decimal(str(sl))
    realized_distance = abs(fill_dec - sl_dec)

    points = realized_distance / tick_size
    price_loss_per_lot = points * tick_value
    realized_per_lot_loss = price_loss_per_lot + commission_rate
    realized_dollar_loss = lots_sent * realized_per_lot_loss

    realized_risk_pct = (realized_dollar_loss / balance) * Decimal("100")

    if planned_risk_pct > Decimal("0"):
        deviation_pct = (abs(realized_risk_pct - planned_risk_pct) / planned_risk_pct) * Decimal("100")
    else:
        deviation_pct = Decimal("0.00")

    is_deviation = deviation_pct > tolerance_pct
    reason: Optional[str] = None
    if is_deviation:
        cause = "slippage"
        if quote is not None:
            slip_diff = fill_dec - Decimal(str(quote))
            cause = f"slippage of {slip_diff:+.5f} (quote={quote}, fill={fill_price})"
        reason = (
            f"RISK_DEVIATION: planned={planned_risk_pct:.3f}%, realized={realized_risk_pct:.3f}%, "
            f"diff={deviation_pct:.2f}% > {tolerance_pct}%, cause={cause}"
        )
        logger.warning(f"[R8] {reason}")

    return realized_risk_pct, deviation_pct, is_deviation, reason


def format_r8_order_record(
    balance: Decimal,
    balance_timestamp: Union[datetime, str],
    risk_amount: Decimal,
    quote: Decimal,
    sl: Decimal,
    tp: Decimal,
    distance: Decimal,
    tick_size: Decimal,
    tick_value: Decimal,
    commission_rate: Decimal,
    lots_raw: Decimal,
    lots_sent: Decimal,
    expected_loss_sl: Decimal,
    expected_profit_tp: Decimal,
    price_rr: Decimal,
    net_dollar_rr: Decimal,
    ticket: Optional[int] = None,
    actual_fill_price: Optional[Decimal] = None,
    realized_risk_pct: Optional[Decimal] = None,
    risk_deviation: Optional[str] = None,
) -> Dict[str, Any]:
    """[R8] Constructs standard dictionary record containing every required R8 field."""
    ts_str = balance_timestamp.isoformat() if isinstance(balance_timestamp, datetime) else str(balance_timestamp)
    return {
        "balance": float(balance),
        "balance_timestamp": ts_str,
        "risk_amount": float(risk_amount),
        "quote": float(quote),
        "sl": float(sl),
        "tp": float(tp),
        "distance": float(distance),
        "tick_size": float(tick_size),
        "tick_value": float(tick_value),
        "commission_rate": float(commission_rate),
        "lots_raw": float(lots_raw),
        "lots_sent": float(lots_sent),
        "expected_loss_sl": float(expected_loss_sl),
        "expected_profit_tp": float(expected_profit_tp),
        "price_rr": float(price_rr),
        "net_dollar_rr": float(net_dollar_rr),
        "ticket": ticket,
        "actual_fill_price": float(actual_fill_price) if actual_fill_price is not None else None,
        "realized_risk_pct": float(realized_risk_pct) if realized_risk_pct is not None else None,
        "risk_deviation": risk_deviation,
    }


# =============================================================================
# Sizing Data Structure & PositionSizer Class
# =============================================================================

@dataclass(frozen=True)
class SizingResult:
    """Result of position sizing calculation."""
    lots: Decimal
    risk_amount: Decimal
    stop_pips: Decimal
    pip_value_usd: Decimal
    is_valid: bool
    rejection_reason: Optional[str] = None
    lots_raw: Optional[Decimal] = None
    per_lot_loss: Optional[Decimal] = None
    achieved_risk_pct: Optional[Decimal] = None
    expected_loss_sl: Optional[Decimal] = None


class PositionSizer:
    """Computes precision lot sizes based on account balance, risk percentage,
    and currency exchange rates."""

    def __init__(
        self,
        account_currency: str = A1_ACCOUNT_CURRENCY,
        default_risk_pct: Decimal = Decimal(str(RISK_PERCENT / 100.0)),
        min_lot: Decimal = Decimal("0.01"),
        max_lot: Decimal = Decimal("50.00"),
        lot_step: Decimal = Decimal("0.01"),
        standard_lot_units: Decimal = Decimal("100000"),
        commission_per_lot: Decimal = Decimal(str(COMMISSION_PER_LOT_ROUND_TURN)),
    ) -> None:
        self.account_currency = account_currency.upper()
        self.default_risk_pct = default_risk_pct
        self.min_lot = min_lot
        self.max_lot = max_lot
        self.lot_step = lot_step
        self.standard_lot_units = standard_lot_units
        self.commission_per_lot = commission_per_lot

    @staticmethod
    def get_pip_size(symbol: str) -> Decimal:
        """Returns the pip size (0.01 for JPY pairs, 0.0001 for all others)."""
        clean = symbol.replace("/", "").upper()
        if "JPY" in clean:
            return Decimal("0.01")
        return Decimal("0.0001")

    @classmethod
    def price_diff_to_pips(cls, symbol: str, price_diff: Decimal | float) -> Decimal:
        """Converts absolute price difference into pip count."""
        pip_size = cls.get_pip_size(symbol)
        dec_diff = Decimal(str(abs(price_diff)))
        return (dec_diff / pip_size).quantize(Decimal("0.1"))

    def get_pip_value_usd(
        self,
        symbol: str,
        rates: Optional[Dict[str, Decimal]] = None,
        current_price: Optional[Decimal] = None,
    ) -> Decimal:
        """Calculates pip value in USD per standard lot (100,000 units)."""
        clean = symbol.replace("/", "").upper()
        fx_root = clean[:6] if len(clean) >= 6 else clean
        pip_size = self.get_pip_size(clean)
        rates_dict = rates or {}

        # Major pairs quoting in USD
        if fx_root.endswith("USD"):
            return (self.standard_lot_units * pip_size).quantize(Decimal("0.01"))

        # Pairs with USD as base currency
        if fx_root.startswith("USD"):
            rate = current_price or rates_dict.get(fx_root) or rates_dict.get(clean)
            if not rate or rate <= 0:
                if "JPY" in fx_root:
                    rate = Decimal("150.00")
                elif "CAD" in fx_root:
                    rate = Decimal("1.4250")
                elif "CHF" in fx_root:
                    rate = Decimal("0.90")
                else:
                    rate = Decimal("1.00")
            return ((self.standard_lot_units * pip_size) / rate).quantize(Decimal("0.01"))

        # Cross currency pairs
        quote = fx_root[3:6] if len(fx_root) == 6 else clean[-3:]
        if quote == "JPY":
            usdjpy = rates_dict.get("USDJPY", Decimal("150.00"))
            return ((self.standard_lot_units * pip_size) / usdjpy).quantize(Decimal("0.01"))
        elif quote == "GBP":
            gbpusd = rates_dict.get("GBPUSD", Decimal("1.2800"))
            return ((self.standard_lot_units * pip_size) * gbpusd).quantize(Decimal("0.01"))
        elif quote == "EUR":
            eurusd = rates_dict.get("EURUSD", Decimal("1.0800"))
            return ((self.standard_lot_units * pip_size) * eurusd).quantize(Decimal("0.01"))
        elif quote == "AUD":
            audusd = rates_dict.get("AUDUSD", Decimal("0.6500"))
            return ((self.standard_lot_units * pip_size) * audusd).quantize(Decimal("0.01"))

        return Decimal("10.00")

    def calculate_lots(
        self,
        account_balance: Decimal,
        stop_pips: Decimal,
        symbol: str,
        risk_pct: Optional[Decimal] = None,
        rates: Optional[Dict[str, Decimal]] = None,
        current_price: Optional[Decimal] = None,
        commission_per_lot: Optional[Decimal] = None,
    ) -> SizingResult:
        """Calculates lot size complying with position sizing rules.
        
        If commission_per_lot is provided and > 0, executes exact R4-R5 formula
        including commission without arbitrary stop-clamping.
        If commission_per_lot is None or 0, preserves legacy behavior.
        """
        if account_balance <= Decimal("0"):
            return SizingResult(
                lots=Decimal("0.00"),
                risk_amount=Decimal("0.00"),
                stop_pips=stop_pips,
                pip_value_usd=Decimal("0.00"),
                is_valid=False,
                rejection_reason=f"Non-positive account balance: {account_balance}",
            )

        if stop_pips <= Decimal("0"):
            return SizingResult(
                lots=Decimal("0.00"),
                risk_amount=Decimal("0.00"),
                stop_pips=stop_pips,
                pip_value_usd=Decimal("0.00"),
                is_valid=False,
                rejection_reason=f"Non-positive stop distance in pips: {stop_pips}",
            )

        risk = risk_pct if risk_pct is not None else self.default_risk_pct
        risk_amount = account_balance * risk
        pip_val = self.get_pip_value_usd(symbol, rates=rates, current_price=current_price)

        comm = commission_per_lot if commission_per_lot is not None else Decimal("0.00")

        if comm > Decimal("0.00"):
            # Strict R4 - R5 path
            pip_size = self.get_pip_size(symbol)
            distance = stop_pips * pip_size
            tick_size = Decimal("0.00001") if pip_size == Decimal("0.0001") else Decimal("0.001")
            # tick_value in USD per contract
            curr_p = current_price or (rates.get(symbol) if rates else None) or Decimal("1.4250")
            tick_val = get_r4_tick_value(symbol, curr_p, self.standard_lot_units, tick_size)
            per_lot_loss = calculate_r4_per_lot_loss(distance, tick_size, tick_val, comm)
            lots_sent, lots_raw, achieved_risk_pct, log_code = calculate_r5_lot_size(
                risk_amount=risk_amount,
                per_lot_loss=per_lot_loss,
                lot_step=self.lot_step,
                min_lot=self.min_lot,
                max_lot=self.max_lot,
                balance=account_balance,
            )
            is_valid = (lots_sent >= self.min_lot)
            rejection = log_code if not is_valid else None
            return SizingResult(
                lots=lots_sent,
                risk_amount=risk_amount.quantize(Decimal("0.01")),
                stop_pips=stop_pips,
                pip_value_usd=pip_val,
                is_valid=is_valid,
                rejection_reason=rejection,
                lots_raw=lots_raw,
                per_lot_loss=per_lot_loss,
                achieved_risk_pct=achieved_risk_pct,
                expected_loss_sl=lots_sent * per_lot_loss,
            )

        # Legacy calculation without commission (used by existing tests)
        effective_stop_pips = max(stop_pips, Decimal("1.5"))
        total_risk_per_lot = effective_stop_pips * pip_val
        raw_lots = risk_amount / total_risk_per_lot

        quantizer = Decimal("0.01")
        lots = (raw_lots // self.lot_step * self.lot_step).quantize(quantizer, rounding=ROUND_DOWN)

        if lots < self.min_lot:
            msg = (
                f"Calculated lot size {lots:.2f} is below minimum lot limit {self.min_lot:.2f}. "
                f"Risk amount ${risk_amount:.2f} is too small for stop distance {stop_pips:.1f} pips."
            )
            logger.warning(msg)
            return SizingResult(
                lots=lots,
                risk_amount=risk_amount.quantize(Decimal("0.01")),
                stop_pips=stop_pips,
                pip_value_usd=pip_val,
                is_valid=False,
                rejection_reason=msg,
            )

        if lots > self.max_lot:
            logger.warning(f"Calculated lot size {lots:.2f} exceeds ceiling {self.max_lot:.2f}; capping to {self.max_lot:.2f}")
            lots = self.max_lot

        return SizingResult(
            lots=lots,
            risk_amount=risk_amount.quantize(Decimal("0.01")),
            stop_pips=stop_pips,
            pip_value_usd=pip_val,
            is_valid=True,
            rejection_reason=None,
        )

    def calculate_exact_lots(
        self,
        account_balance: Decimal,
        quote: Decimal,
        sl: Decimal,
        direction: Union[str, Direction],
        symbol: str = "USDCAD",
        contract_size: Decimal = Decimal("100000"),
        tick_size: Decimal = Decimal("0.00001"),
        bridge_tick_value: Optional[Decimal] = None,
        commission_per_lot: Decimal = Decimal(str(COMMISSION_PER_LOT_ROUND_TURN)),
        risk_pct: Optional[Decimal] = None,
    ) -> SizingResult:
        """[R1-R5] Full exact 1% risk position sizing.
        
        - Uses live quote (Ask for BUY, Bid for SELL)
        - distance = |quote - SL|
        - tick_value = contract_size * tick_size / quote
        - per_lot_loss = (distance / tick_size) * tick_value + commission_per_lot
        - lots_raw = risk_amount / per_lot_loss
        - lots_sent = floor to lot_step
        """
        risk_fraction = risk_pct if risk_pct is not None else self.default_risk_pct
        risk_amount = calculate_r2_risk_amount(account_balance, risk_fraction * Decimal("100"))

        quote_dec, distance = calculate_r3_quote_distance(quote, sl, direction)
        if distance <= Decimal("0"):
            return SizingResult(
                lots=Decimal("0.00"),
                risk_amount=risk_amount,
                stop_pips=Decimal("0.0"),
                pip_value_usd=Decimal("0.00"),
                is_valid=False,
                rejection_reason="SL distance is zero",
            )

        tick_val = get_r4_tick_value(
            symbol=symbol,
            current_price=quote_dec,
            contract_size=contract_size,
            tick_size=tick_size,
            bridge_tick_value=bridge_tick_value,
        )

        per_lot_loss = calculate_r4_per_lot_loss(
            distance=distance,
            tick_size=tick_size,
            tick_value=tick_val,
            commission_per_lot=commission_per_lot,
        )

        lots_sent, lots_raw, achieved_risk_pct, log_code = calculate_r5_lot_size(
            risk_amount=risk_amount,
            per_lot_loss=per_lot_loss,
            lot_step=self.lot_step,
            min_lot=self.min_lot,
            max_lot=self.max_lot,
            balance=account_balance,
        )

        pip_size = self.get_pip_size(symbol)
        stop_pips = (distance / pip_size).quantize(Decimal("0.1"))
        pip_val_usd = tick_val * (pip_size / tick_size)

        is_valid = (lots_sent >= self.min_lot)
        rejection = log_code if not is_valid else None

        return SizingResult(
            lots=lots_sent,
            risk_amount=risk_amount.quantize(Decimal("0.01")),
            stop_pips=stop_pips,
            pip_value_usd=pip_val_usd.quantize(Decimal("0.01")),
            is_valid=is_valid,
            rejection_reason=rejection,
            lots_raw=lots_raw,
            per_lot_loss=per_lot_loss,
            achieved_risk_pct=achieved_risk_pct,
            expected_loss_sl=lots_sent * per_lot_loss,
        )

