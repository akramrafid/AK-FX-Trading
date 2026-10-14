"""
Confirmation and Risk-Reward (5:1) Calculator for AK Forex Trading System.

Evaluates the 3 closed candles following a qualifying liquidity sweep:
- Confirms 3 consecutive candles in trade direction (all green for BUY, all red for SELL).
- Entry: Close of candle 3.
- Stop-Loss: Lowest low (BUY) / Highest high + spread (SELL) across confirming candles.
- Take-Profit: Fixed 5x stop-loss distance (5:1 R:R).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
from .models import Candle, Direction, SweepEvent, TradeSignal


def evaluate_3_candles(
    confirming_candles: Sequence[Candle],
    direction: Direction,
    buffer_pips: float = 0.0,
    pip_size: float = 0.0001,
    spread_pips: float = 0.0,
    sweep_type: str = "VARIANT_A",
    sweep_candle_index: int = -1,
    sweep_timeframe: str = "M5",
    confirmation_indices: Tuple[int, int, int] = (0, 1, 2),
    use_c1_only_sl: bool = False,
    reward_risk_ratio: float = 5.0,
    sweep_extreme_price: Optional[float] = None,
    use_sweep_wick_sl: bool = False,
    min_displacement_ratio: float = 0.0,
    avg_candle_body: Optional[float] = None,
    min_risk_pips: float = 0.0,
    partial_bank_r: Optional[float] = None,
    partial_bank_pct: Optional[float] = None,
    breakeven_trigger_r: Optional[float] = None,
) -> Optional[TradeSignal]:
    """
    Evaluates 3 closed candles for directional confirmation and calculates R:R (default 5:1).
    - Long (BUY): All 3 candles must be bullish.
    - Short (SELL): All 3 candles must be bearish.
    - Entry: Close of 3rd candle.
    - Stop-Loss:
      - If use_sweep_wick_sl=True: Placed beyond the sweep extreme wick (High_sweep + spread for short, Low_sweep for long).
      - Else: lowest low / highest high across confirming candles (default).
    - Displacement: If min_displacement_ratio > 0, requires at least one candle body >= ratio * avg_candle_body.
    - Take-Profit: Entry ± (reward_risk_ratio * Stop Distance).
    """
    if len(confirming_candles) != 3:
        return None

    c1, c2, c3 = confirming_candles[0], confirming_candles[1], confirming_candles[2]
    buffer_price = buffer_pips * pip_size
    spread_price = spread_pips * pip_size

    # Check institutional displacement requirement if configured
    if min_displacement_ratio > 0.0 and avg_candle_body is not None and avg_candle_body > 0.0:
        max_body = max(c1.body, c2.body, c3.body)
        if max_body < (min_displacement_ratio * avg_candle_body):
            return None

    if direction == Direction.BUY:
        # All 3 candles must be directional (bullish or neutral doji; none can close bearish)
        if not (c1.close >= c1.open and c2.close >= c2.open and c3.close >= c3.open):
            return None
        entry_price = c3.close
        if use_sweep_wick_sl and sweep_extreme_price is not None:
            lowest_low = min(sweep_extreme_price, c1.low, c2.low, c3.low)
            stop_loss = lowest_low - buffer_price
        else:
            lowest_low = c1.low if use_c1_only_sl else min(c1.low, c2.low, c3.low)
            stop_loss = lowest_low - buffer_price

        risk_distance = entry_price - stop_loss
        if min_risk_pips > 0.0:
            min_dist = min_risk_pips * pip_size
            if risk_distance < min_dist:
                risk_distance = min_dist
                stop_loss = entry_price - risk_distance

        if risk_distance <= 0:
            return None
        reward_distance = reward_risk_ratio * risk_distance
        take_profit = entry_price + reward_distance

        return TradeSignal(
            direction="BUY",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_distance=risk_distance,
            reward_distance=reward_distance,
            reward_risk_ratio=reward_risk_ratio,
            sweep_type=sweep_type,
            sweep_candle_index=sweep_candle_index,
            confirmation_indices=confirmation_indices,
            timestamp=c3.timestamp,
            sweep_timeframe=sweep_timeframe,
            timeframe="M1",
            extreme_price=sweep_extreme_price,
            partial_bank_r=partial_bank_r,
            partial_bank_pct=partial_bank_pct,
            breakeven_trigger_r=breakeven_trigger_r,
        )

    elif direction == Direction.SELL:
        # All 3 candles must be directional (bearish or neutral doji; none can close bullish)
        if not (c1.close <= c1.open and c2.close <= c2.open and c3.close <= c3.open):
            return None
        entry_price = c3.close
        if use_sweep_wick_sl and sweep_extreme_price is not None:
            highest_high = max(sweep_extreme_price, c1.high, c2.high, c3.high)
            stop_loss = highest_high + spread_price + buffer_price
        else:
            highest_high = c1.high if use_c1_only_sl else max(c1.high, c2.high, c3.high)
            stop_loss = highest_high + spread_price + buffer_price

        risk_distance = stop_loss - entry_price
        if min_risk_pips > 0.0:
            min_dist = min_risk_pips * pip_size
            if risk_distance < min_dist:
                risk_distance = min_dist
                stop_loss = entry_price + risk_distance

        if risk_distance <= 0:
            return None
        reward_distance = reward_risk_ratio * risk_distance
        take_profit = entry_price - reward_distance

        return TradeSignal(
            direction="SELL",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_distance=risk_distance,
            reward_distance=reward_distance,
            reward_risk_ratio=reward_risk_ratio,
            sweep_type=sweep_type,
            sweep_candle_index=sweep_candle_index,
            confirmation_indices=confirmation_indices,
            timestamp=c3.timestamp,
            sweep_timeframe=sweep_timeframe,
            timeframe="M1",
            extreme_price=sweep_extreme_price,
            partial_bank_r=partial_bank_r,
            partial_bank_pct=partial_bank_pct,
            breakeven_trigger_r=breakeven_trigger_r,
        )

    return None


def evaluate_confirmation(
    candles: List[Candle],
    sweep_event: SweepEvent,
    buffer_pips: float = 0.0,
    pip_size: float = 0.0001,
    spread_pips: float = 0.0,
    use_c1_only_sl: bool = False,
    reward_risk_ratio: float = 5.0,
    use_sweep_wick_sl: bool = False,
    min_displacement_ratio: float = 0.0,
    avg_candle_body: Optional[float] = None,
    min_risk_pips: float = 0.0,
    partial_bank_r: Optional[float] = None,
    partial_bank_pct: Optional[float] = None,
    breakeven_trigger_r: Optional[float] = None,
) -> Optional[TradeSignal]:
    """
    Evaluate the 3 candles immediately following the sweep candle.

    sweep_event.candle_index: index of the sweep candle (S)
    Confirmation candles must be at:
    - Candle 1: S + 1
    - Candle 2: S + 2
    - Candle 3: S + 3

    Returns TradeSignal if all 3 candles confirm; None if incomplete or broken.
    """
    s_idx = sweep_event.candle_index
    c1_idx = s_idx + 1
    c2_idx = s_idx + 2
    c3_idx = s_idx + 3

    # Check if all 3 confirmation candles are available and closed
    if c3_idx >= len(candles):
        return None

    confirming = [candles[c1_idx], candles[c2_idx], candles[c3_idx]]

    return evaluate_3_candles(
        confirming_candles=confirming,
        direction=sweep_event.direction,
        buffer_pips=buffer_pips,
        pip_size=pip_size,
        spread_pips=spread_pips,
        sweep_type=sweep_event.sweep_type.value,
        sweep_candle_index=s_idx,
        confirmation_indices=(c1_idx, c2_idx, c3_idx),
        use_c1_only_sl=use_c1_only_sl,
        reward_risk_ratio=reward_risk_ratio,
        sweep_extreme_price=sweep_event.extreme_price,
        use_sweep_wick_sl=use_sweep_wick_sl,
        min_displacement_ratio=min_displacement_ratio,
        avg_candle_body=avg_candle_body,
        min_risk_pips=min_risk_pips,
        partial_bank_r=partial_bank_r,
        partial_bank_pct=partial_bank_pct,
        breakeven_trigger_r=breakeven_trigger_r,
    )


# =============================================================================
# Strict AK Forex Strategy Rules (Tagged Implementation: S2-S6, B2-B6)
# =============================================================================

def evaluate_s2_m1_validity(
    c1: Candle,
    l_candle: Candle,
    equal_tolerance: float = 0.0,
) -> Tuple[bool, Dict[str, Any]]:
    """
    [Rule S2] M1 method gate for SELL setups.
    c1 = first bearish M1 candle (c1.close < c1.open).
    L = M1 candle immediately before c1; must be bullish (L.close > L.open). [A6]
    Two methods (one must hold):
      S2-A "Equal top": c1.high == L.high (tolerance EQUAL_TOLERANCE_POINTS = 0). [A2]
      S2-B "Bullish wick swapped": c1.high > L.high.
    If c1.high < L.high, neither holds: no trade.
    """
    c1_bearish = c1.close < c1.open
    l_bullish = l_candle.close > l_candle.open

    method: Optional[str] = None
    passed = False

    if c1_bearish and l_bullish:
        if abs(c1.high - l_candle.high) <= equal_tolerance:
            method = "equal"
            passed = True
        elif c1.high > l_candle.high:
            method = "wick_swap"
            passed = True
        else:
            method = None
            passed = False

    eval_data = {
        "rule_id": "S2",
        "pass": passed,
        "method": method,
        "values": {
            "c1_open": c1.open,
            "c1_close": c1.close,
            "c1_high": c1.high,
            "c1_bearish": c1_bearish,
            "l_open": l_candle.open,
            "l_close": l_candle.close,
            "l_high": l_candle.high,
            "l_bullish": l_bullish,
            "method": method,
            "equal_tolerance": equal_tolerance,
        },
    }
    return passed, eval_data


def evaluate_b2_m1_validity(
    c1: Candle,
    l_candle: Candle,
    equal_tolerance: float = 0.0,
) -> Tuple[bool, Dict[str, Any]]:
    """
    [Rule B2] M1 method gate for BUY setups.
    c1 = first bullish M1 candle (c1.close > c1.open).
    L = M1 candle immediately before c1; must be bearish (L.close < L.open). [A6]
    Two methods (one must hold):
      B2-A "Equal low": c1.low == L.low (tolerance EQUAL_TOLERANCE_POINTS = 0). [A2]
      B2-B "Bearish wick swapped by bullish": c1.low < L.low.
    If c1.low > L.low, neither holds: no trade.
    """
    c1_bullish = c1.close > c1.open
    l_bearish = l_candle.close < l_candle.open

    method: Optional[str] = None
    passed = False

    if c1_bullish and l_bearish:
        if abs(c1.low - l_candle.low) <= equal_tolerance:
            method = "equal"
            passed = True
        elif c1.low < l_candle.low:
            method = "wick_swap"
            passed = True
        else:
            method = None
            passed = False

    eval_data = {
        "rule_id": "B2",
        "pass": passed,
        "method": method,
        "values": {
            "c1_open": c1.open,
            "c1_close": c1.close,
            "c1_low": c1.low,
            "c1_bullish": c1_bullish,
            "l_open": l_candle.open,
            "l_close": l_candle.close,
            "l_low": l_candle.low,
            "l_bearish": l_bearish,
            "method": method,
            "equal_tolerance": equal_tolerance,
        },
    }
    return passed, eval_data


def evaluate_s3_m1_confirmation(
    candles: Sequence[Candle],
) -> Tuple[bool, Dict[str, Any]]:
    """
    [Rule S3] M1 confirmation for SELL setups.
    3 consecutive bearish M1 candles, c1, c2, c3 (c1 from S2).
    Evaluate only on closed M1 candles.
    """
    count_ok = len(candles) == 3
    all_bearish = count_ok and all(c.close < c.open for c in candles)
    passed = bool(count_ok and all_bearish)

    eval_data = {
        "rule_id": "S3",
        "pass": passed,
        "values": {
            "count": len(candles),
            "expected_count": 3,
            "all_bearish": all_bearish,
            "candle_states": [
                {
                    "timestamp": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp),
                    "open": c.open,
                    "close": c.close,
                    "is_bearish": c.close < c.open,
                }
                for c in candles
            ],
        },
    }
    return passed, eval_data


def evaluate_b3_m1_confirmation(
    candles: Sequence[Candle],
) -> Tuple[bool, Dict[str, Any]]:
    """
    [Rule B3] M1 confirmation for BUY setups.
    3 consecutive bullish M1 candles, c1, c2, c3 (c1 from B2).
    Evaluate only on closed M1 candles.
    """
    count_ok = len(candles) == 3
    all_bullish = count_ok and all(c.close > c.open for c in candles)
    passed = bool(count_ok and all_bullish)

    eval_data = {
        "rule_id": "B3",
        "pass": passed,
        "values": {
            "count": len(candles),
            "expected_count": 3,
            "all_bullish": all_bullish,
            "candle_states": [
                {
                    "timestamp": c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp),
                    "open": c.open,
                    "close": c.close,
                    "is_bullish": c.close > c.open,
                }
                for c in candles
            ],
        },
    }
    return passed, eval_data


def calculate_s4_entry(c3: Candle) -> Tuple[float, Dict[str, Any]]:
    """
    [Rule S4] Market SELL immediately when c3 closes.
    No limit orders. Not on a live tick.
    """
    entry_price = float(c3.close)
    eval_data = {
        "rule_id": "S4",
        "pass": True,
        "values": {
            "entry_price": entry_price,
            "order_type": "market",
            "trigger": "c3_close",
        },
    }
    return entry_price, eval_data


def calculate_b4_entry(c3: Candle) -> Tuple[float, Dict[str, Any]]:
    """
    [Rule B4] Market BUY immediately when c3 closes.
    No limit orders. Not on a live tick.
    """
    entry_price = float(c3.close)
    eval_data = {
        "rule_id": "B4",
        "pass": True,
        "values": {
            "entry_price": entry_price,
            "order_type": "market",
            "trigger": "c3_close",
        },
    }
    return entry_price, eval_data


def calculate_s5_stop_loss(
    c1: Candle,
    entry: Optional[float] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    [Rule S5] Stop-loss for SELL setups.
    The top of the wick of c1 (c1.high).
    Stop-loss is always above entry.
    """
    stop_loss = float(c1.high)
    passed = True if entry is None else (stop_loss > entry)
    eval_data = {
        "rule_id": "S5",
        "pass": passed,
        "values": {
            "stop_loss": stop_loss,
            "c1_high": float(c1.high),
            "entry": entry,
            "sl_above_entry": passed,
            "reference": "c1_wick_extreme",
        },
    }
    return stop_loss, eval_data


def calculate_b5_stop_loss(
    c1: Candle,
    entry: Optional[float] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    [Rule B5] Stop-loss for BUY setups.
    The bottom of the wick of c1 (c1.low).
    In method B2-B this is below L.low; in B2-A they are equal. [A3]
    Stop-loss is always below entry.
    """
    stop_loss = float(c1.low)
    passed = True if entry is None else (stop_loss < entry)
    eval_data = {
        "rule_id": "B5",
        "pass": passed,
        "values": {
            "stop_loss": stop_loss,
            "c1_low": float(c1.low),
            "entry": entry,
            "sl_below_entry": passed,
            "reference": "c1_wick_extreme",
        },
    }
    return stop_loss, eval_data


def calculate_s6_take_profit(
    entry: float,
    stop_loss: float,
    rr_multiple: float = 10.0,
) -> Tuple[float, Dict[str, Any]]:
    """
    [Rule S6] Take-profit for SELL setups.
    entry - 10 * (SL - entry). Risk-reward 1:10.
    """
    risk = stop_loss - entry
    take_profit = round(entry - (rr_multiple * risk), 5)
    eval_data = {
        "rule_id": "S6",
        "pass": True,
        "values": {
            "entry": entry,
            "stop_loss": stop_loss,
            "risk": risk,
            "take_profit": take_profit,
            "reward": entry - take_profit,
            "rr_multiple": rr_multiple,
        },
    }
    return take_profit, eval_data


def calculate_b6_take_profit(
    entry: float,
    stop_loss: float,
    rr_multiple: float = 10.0,
) -> Tuple[float, Dict[str, Any]]:
    """
    [Rule B6] Take-profit for BUY setups.
    entry + 10 * (entry - SL). Risk-reward 1:10.
    """
    risk = entry - stop_loss
    take_profit = round(entry + (rr_multiple * risk), 5)
    eval_data = {
        "rule_id": "B6",
        "pass": True,
        "values": {
            "entry": entry,
            "stop_loss": stop_loss,
            "risk": risk,
            "take_profit": take_profit,
            "reward": take_profit - entry,
            "rr_multiple": rr_multiple,
        },
    }
    return take_profit, eval_data


def format_rule_log_record(
    direction: str,
    rules: Optional[List[Dict[str, Any]]] = None,
    setup_passed: bool = False,
    failing_rule: Optional[str] = None,
    timeframe: Optional[str] = None,
    htf_timestamp: Optional[Any] = None,
    details: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
    evaluations: Optional[List[Dict[str, Any]]] = None,
    timestamp: Optional[Any] = None,
    method: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a structured log record listing each rule ID with pass/fail and compared values,
    plus Stage 2 method name ("equal" or "wick_swap") when it passes.
    If a setup is skipped, failing_rule identifies which rule failed.
    """
    effective_rules = rules if rules is not None else (evaluations if evaluations is not None else [])
    effective_ts = htf_timestamp if htf_timestamp is not None else timestamp
    ts_str = effective_ts.isoformat() if hasattr(effective_ts, "isoformat") else str(effective_ts) if effective_ts else None
    effective_status = status if status is not None else ("PASSED" if setup_passed else "SKIPPED")

    # Resolve Stage 2 method name
    stage2_method = method
    if stage2_method is None:
        for r in effective_rules:
            if r.get("rule_id") in ("S2", "B2") and r.get("pass"):
                stage2_method = r.get("method") or r.get("values", {}).get("method")
                break

    merged_details = dict(details or {})
    if stage2_method:
        merged_details["method"] = stage2_method

    return {
        "timestamp": ts_str,
        "timeframe": timeframe,
        "direction": direction,
        "status": effective_status,
        "setup_passed": setup_passed or (effective_status == "PASSED"),
        "method": stage2_method,
        "failing_rule": failing_rule,
        "rules": effective_rules,
        "evaluations": effective_rules,
        "details": merged_details,
    }

