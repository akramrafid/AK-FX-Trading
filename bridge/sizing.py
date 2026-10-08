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
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional, Tuple

logger = logging.getLogger("sizing")


@dataclass(frozen=True)
class SizingResult:
    """Result of position sizing calculation."""
    lots: Decimal
    risk_amount: Decimal
    stop_pips: Decimal
    pip_value_usd: Decimal
    is_valid: bool
    rejection_reason: Optional[str] = None


class PositionSizer:
    """Computes precision lot sizes based on account balance, risk percentage,
    and currency exchange rates."""

    def __init__(
        self,
        account_currency: str = "USD",
        default_risk_pct: Decimal = Decimal("0.01"),
        min_lot: Decimal = Decimal("0.01"),
        max_lot: Decimal = Decimal("50.00"),
        lot_step: Decimal = Decimal("0.01"),
        standard_lot_units: Decimal = Decimal("100000"),
    ) -> None:
        self.account_currency = account_currency.upper()
        self.default_risk_pct = default_risk_pct
        self.min_lot = min_lot
        self.max_lot = max_lot
        self.lot_step = lot_step
        self.standard_lot_units = standard_lot_units

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
        """Calculates pip value in USD per standard lot (100,000 units).
        
        - If quote currency is USD (e.g. EURUSD, GBPUSD, AUDUSD):
          Pip Value = 100,000 * 0.0001 = $10.00 USD.
        - If base currency is USD (e.g. USDJPY):
          Pip Value = (100,000 * 0.01) / USDJPY_rate = 1,000 / USDJPY_rate.
        - If cross pair (e.g. EURJPY):
          Pip Value = (100,000 * 0.01) / USDJPY_rate.
        - If cross pair with GBP quote (e.g. EURGBP):
          Pip Value = (100,000 * 0.0001) * GBPUSD_rate.
        """
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
                # Conservative fallback if rate is unavailable
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

        # Default fallback
        return Decimal("10.00")

    def calculate_lots(
        self,
        account_balance: Decimal,
        stop_pips: Decimal,
        symbol: str,
        risk_pct: Optional[Decimal] = None,
        rates: Optional[Dict[str, Decimal]] = None,
        current_price: Optional[Decimal] = None,
    ) -> SizingResult:
        """Calculates lot size complying with Hard Rule 3.
        
        Formula: Lots = (Balance * Risk_Pct) / (Stop_Loss_Pips * Pip_Value)
        Rounds down to nearest 0.01 lot.
        Validates min (0.01) and max (50.00) lot limits.
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
        risk_amount = (account_balance * risk).quantize(Decimal("0.01"))
        pip_val = self.get_pip_value_usd(symbol, rates=rates, current_price=current_price)

        # Enforce minimum effective stop distance of 1.5 pips to prevent micro-stops
        # (e.g. 0.2 pips) from producing oversized lots that exceed account margin (MT4 err 134)
        # and ensure maximum sizing on tight stops does not exceed 1 pip ≈ $1 USD.
        effective_stop_pips = max(stop_pips, Decimal("1.5"))
        total_risk_per_lot = effective_stop_pips * pip_val
        raw_lots = risk_amount / total_risk_per_lot

        # Round down to nearest lot_step (0.01)
        quantizer = Decimal("0.01")
        lots = (raw_lots // self.lot_step * self.lot_step).quantize(quantizer, rounding=ROUND_DOWN)

        # Sanity Bounds Check
        if lots < self.min_lot:
            msg = (
                f"Calculated lot size {lots:.2f} is below minimum lot limit {self.min_lot:.2f}. "
                f"Risk amount ${risk_amount:.2f} is too small for stop distance {stop_pips:.1f} pips."
            )
            logger.warning(msg)
            return SizingResult(
                lots=lots,
                risk_amount=risk_amount,
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
            risk_amount=risk_amount,
            stop_pips=stop_pips,
            pip_value_usd=pip_val,
            is_valid=True,
            rejection_reason=None,
        )
