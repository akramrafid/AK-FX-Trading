"""
Sell and buy scenarios together on one symbol (STRATEGY_MODE=ak_scenarios; trader decisions of 2026-10-26).

Both engines see every closed candle. On top of them:
- No hedging: while one side has an open position, the other side's signals are skipped and
  journaled as POSITION_OPEN. Within one side the engine's own limit applies (MAX_OPEN_TRADES).
- A sell and a buy on the same 1m bar cancel each other: neither is sent and the pair is journaled
  as SAME_BAR_CONFLICT. With the default rules this cannot happen: a bullish 3-run always has a
  bullish candle among its last three bars, and a sell's B1-B3 never hold one.
Neither engine is modified: the hedge block reaches each one through its own position limit.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar, Union

import config
from .buy_scenarios import BuyDecision, BuyScenarioEngine, BuyScenarioParams
from .models import Candle, TradeSignal
from .sell_scenarios import SellDecision, SellScenarioEngine, SellScenarioParams, time_fields

logger = logging.getLogger("ak_scenarios")

HEDGE_BLOCK = 10**9  # an open-position count above any real limit: the engine skips with POSITION_OPEN
SAME_BAR_CONFLICT = "SAME_BAR_CONFLICT"

Decision = Union[SellDecision, BuyDecision]
OpenPositions = Tuple[int, int]  # (open buys, open sells) on the symbol
ScenarioParams = TypeVar("ScenarioParams", SellScenarioParams, BuyScenarioParams)


def no_hedging_params(params: ScenarioParams) -> ScenarioParams:
    """Engine parameters for AkScenariosEngine: no limit becomes HEDGE_BLOCK, so the hedge block can skip."""
    return params if params.max_open_positions is not None else replace(params, max_open_positions=HEDGE_BLOCK)


def decision_side(decision: Decision) -> str:
    return "BUY" if isinstance(decision, BuyDecision) else "SELL"


class AkScenariosEngine:
    """
    Feed HTF closes to on_htf_candle() and 1m closes to on_m1_candle() in close-time order, as for
    either engine. The backtest passes the open positions by side; live, the BridgeExecutor running
    the engine installs its position_counter. Without a counter, or while it returns None, neither
    side trades.
    """

    tp_from_fill = True  # read by bridge/executor.py: both engines price the TP from the live quote

    def __init__(
        self,
        sell: Optional[SellScenarioEngine] = None,
        buy: Optional[BuyScenarioEngine] = None,
        no_hedging: bool = config.AK_SCENARIOS_NO_HEDGING,
        position_counter: Optional[Callable[[], Optional[OpenPositions]]] = None,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        engines = [e for e in (sell, buy) if e is not None]
        if not engines:
            raise ValueError("AkScenariosEngine needs a sell engine, a buy engine or both")
        if len({e.params.rr for e in engines}) > 1:
            raise ValueError("Sell and buy must share one reward:risk ratio: the bridge prices one TP rule")
        if len({e.params.point_size for e in engines}) > 1:
            raise ValueError("Sell and buy must trade the same symbol")
        if no_hedging and len(engines) == 2 and any(e.params.max_open_positions is None for e in engines):
            raise ValueError("No hedging needs a position limit on both engines: build their params with no_hedging_params()")
        self.sell = sell
        self.buy = buy
        self.no_hedging = no_hedging
        self.position_counter = position_counter
        self.event_sink = event_sink
        self.reward_risk_ratio = engines[0].params.rr
        # bridge/executor.py sets or reads these on every rule engine; they do not affect this strategy.
        self.spread_pips = 0.0
        self._m1_body_sum = 0.0
        self._m1_body_count = 0
        self._engines: Tuple[Any, ...] = tuple(engines)
        self.conflicts: List[Tuple[SellDecision, BuyDecision]] = []
        self.last_decision: Optional[Decision] = None
        self._warned_no_m1 = False

    @property
    def decisions(self) -> List[Decision]:
        """Both engines' decisions in signal-time order (sells first at the same time)."""
        return sorted((d for e in self._engines for d in e.decisions), key=lambda d: d.signal_time)

    @property
    def armed_setups(self) -> Tuple[Any, ...]:
        return tuple(s for e in self._engines for s in e.armed_setups)

    def reset(self) -> None:
        for engine in self._engines:
            engine.reset()
        self.conflicts = []
        self.last_decision = None

    def on_htf_candle(self, raw_candle: Union[Candle, Dict[str, Any]], timeframe: str = "M5") -> None:
        for engine in self._engines:
            engine.on_htf_candle(raw_candle, timeframe)

    def on_m1_candle(
        self, raw_candle: Union[Candle, Dict[str, Any]], open_positions: Optional[OpenPositions] = None
    ) -> Optional[TradeSignal]:
        """One closed 1m candle through both engines; open_positions = (buys, sells), None asks position_counter."""
        sell_open, buy_open = self._position_limits(open_positions if open_positions is not None else self._count())
        self.last_decision = None
        sell_signal = self.sell.on_m1_candle(raw_candle, sell_open) if self.sell is not None else None
        buy_signal = self.buy.on_m1_candle(raw_candle, buy_open) if self.buy is not None else None
        if sell_signal is not None and buy_signal is not None:
            self._conflict(self.sell.decisions[-1], self.buy.decisions[-1])
            return None
        if sell_signal is not None:
            self.last_decision = self.sell.decisions[-1]
            return sell_signal
        if buy_signal is not None:
            self.last_decision = self.buy.decisions[-1]
        return buy_signal

    def evaluate_completed_candle(self, raw_candles: Sequence[Any]) -> None:
        """The bridge's single-timeframe path cannot run this strategy: it needs the M1 bar export."""
        if not self._warned_no_m1:
            logger.warning("AK scenarios need the MT4 M1 bar export; no M1 file found, so no signals.")
            self._warned_no_m1 = True
        return None

    def _count(self) -> Optional[OpenPositions]:
        """The live open positions; None (unknown) without a counter or when it fails."""
        if self.position_counter is None:
            return None
        try:
            return self.position_counter()
        except Exception as exc:
            logger.error(f"Open-position count failed: {exc}")
            return None

    def _position_limits(self, positions: Optional[OpenPositions]) -> Tuple[int, int]:
        """The open-position count each engine sees: HEDGE_BLOCK while the other side is open, or unknown."""
        if positions is None:
            logger.warning("Open positions unknown: no sell or buy is sent on this bar.")
            return HEDGE_BLOCK, HEDGE_BLOCK
        buys, sells = positions
        sell_open = HEDGE_BLOCK if self.no_hedging and buys > 0 else sells
        buy_open = HEDGE_BLOCK if self.no_hedging and sells > 0 else buys
        return sell_open, buy_open

    def _conflict(self, sell: SellDecision, buy: BuyDecision) -> None:
        self.conflicts.append((sell, buy))
        logger.warning(f"Sell and buy on the same bar ({sell.signal_time:%Y-%m-%d %H:%M} UTC): neither is sent.")
        if self.event_sink is None:
            return
        record: Dict[str, Any] = {
            "event": SAME_BAR_CONFLICT,
            "sell_scenario": sell.scenario,
            "sell_setup_id": sell.setup.setup_id,
            "buy_scenario": buy.scenario,
            "buy_setup_id": buy.setup.setup_id,
            **time_fields("signal_time", sell.signal_time),
        }
        try:
            self.event_sink(record)
        except Exception as exc:  # journaling must never block a trade
            logger.error(f"AK scenarios journal write failed: {exc}")
