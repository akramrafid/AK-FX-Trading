"""
Mission Impossible 3-run detector (Mission_Impossible_Pine_Script.docx; BUY_STRATEGY_PROMPT.md §4.3).

Closed 1m candles are grouped into runs of one colour. A run is eligible when its first candle
(a doji or a real candle) reaches the previous run's extreme: low <= prior low for a bullish run,
high >= prior high for a bearish one (equal or sweep, exact price unless a tolerance is set).
An eligible run signals once, on the bar where its count reaches 3.

Dojis are neutral and placed by the doc's rules:
(a) a doji that brings count + pending dojis to 3 completes the current run;
(b) a third doji in a row drops the pending dojis and itself;
(c) any other doji waits as pending;
(d) a real candle of the run's colour adds 1; pending dojis join the run's range but not its
    count (DOJI_COUNTING = doc_exact) or count too (every_doji_counts);
(e) a real candle of the other colour starts a new run whose first candles are the pending dojis;
    eligibility is tested on the first of them, on its own low/high (the doc's prose).
The detector is pure: it knows nothing about setups, sessions or orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .sell_scenarios import CandleKind, PointCandle

RUN_LENGTH = 3
DOJI_COUNTINGS = ("doc_exact", "every_doji_counts")


@dataclass(frozen=True)
class RunMember:
    candle: PointCandle
    kind: CandleKind


@dataclass(frozen=True)
class RunSignal:
    """An eligible run that reached RUN_LENGTH counted candles on its last member."""
    direction: CandleKind  # BULL or BEAR
    members: Tuple[RunMember, ...]  # every candle of the run, merged dojis included
    low: int
    high: int
    prior_members: Tuple[RunMember, ...]
    prior_low: int
    prior_high: int

    @property
    def first(self) -> PointCandle:
        return self.members[0].candle

    @property
    def signal(self) -> PointCandle:
        return self.members[-1].candle

    @property
    def doji_positions(self) -> Tuple[int, ...]:
        return tuple(i for i, m in enumerate(self.members, start=1) if m.kind is CandleKind.DOJI)


@dataclass
class _Run:
    direction: CandleKind
    members: List[RunMember]
    count: int
    eligible: bool
    fired: bool = False

    @property
    def low(self) -> int:
        return min(m.candle.low for m in self.members)

    @property
    def high(self) -> int:
        return max(m.candle.high for m in self.members)


class ThreeRunDetector:
    """Feed every closed 1m candle with its kind; push() returns a RunSignal when an eligible run fires."""

    def __init__(self, doji_counting: str = "doc_exact", eq_tol_pts: int = 0) -> None:
        if doji_counting not in DOJI_COUNTINGS:
            raise ValueError(f"doji_counting must be one of {DOJI_COUNTINGS} (got {doji_counting!r})")
        if eq_tol_pts < 0:
            raise ValueError("eq_tol_pts cannot be negative")
        self.doji_counting = doji_counting
        self.eq_tol_pts = eq_tol_pts
        self.reset()

    def reset(self) -> None:
        """Forget every run and pending doji (used after a feed outage)."""
        self._run: Optional[_Run] = None
        self._prior: Optional[_Run] = None
        self._pending: List[RunMember] = []

    def push(self, candle: PointCandle, kind: CandleKind) -> Optional[RunSignal]:
        member = RunMember(candle, kind)
        run = self._run
        if kind is CandleKind.DOJI:
            if run is not None and run.count + len(self._pending) + 1 == RUN_LENGTH:  # (a)
                run.members += self._pending + [member]
                run.count = RUN_LENGTH
                self._pending = []
                return self._fire(run)
            if len(self._pending) == 2:  # (b)
                self._pending = []
            else:  # (c)
                self._pending.append(member)
            return None

        if run is not None and kind is run.direction:  # (d)
            before = run.count
            run.count += 1 + (len(self._pending) if self.doji_counting == "every_doji_counts" else 0)
            run.members += self._pending + [member]
            self._pending = []
            return self._fire(run) if before < RUN_LENGTH <= run.count else None

        members = self._pending + [member]  # (e)
        new = _Run(direction=kind, members=members, count=len(members),
                   eligible=self._eligible(kind, members[0].candle, run))
        self._prior, self._run, self._pending = run, new, []
        return self._fire(new) if new.count >= RUN_LENGTH else None

    def _eligible(self, kind: CandleKind, first: PointCandle, prior: Optional[_Run]) -> bool:
        if prior is None:
            return False
        if kind is CandleKind.BULL:
            return first.low <= prior.low + self.eq_tol_pts
        return first.high >= prior.high - self.eq_tol_pts

    def _fire(self, run: _Run) -> Optional[RunSignal]:
        if not run.eligible or run.fired or self._prior is None:
            return None
        run.fired = True
        prior = self._prior
        return RunSignal(
            direction=run.direction,
            members=tuple(run.members),
            low=run.low,
            high=run.high,
            prior_members=tuple(prior.members),
            prior_low=prior.low,
            prior_high=prior.high,
        )
