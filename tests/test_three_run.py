"""
Tests for the Mission Impossible 3-run detector (engine/three_run.py).

BUY_STRATEGY_PROMPT.md §4.3-§4.5 and Mission_Impossible_Pine_Script.docx:
- the eight bullish doji cases of §4.4 and the bar each one signals on;
- the position-2 quirk, short prior runs absorbing dojis, eligibility tested on a first doji
  (the doc's prose), a third doji dropping the pending ones;
- the every_doji_counts alternative, the bearish mirror, the tolerance and a feed reset.
"""

import unittest
from datetime import datetime, timedelta, timezone

from engine.buy_scenarios import candle_kind_pct
from engine.models import Candle
from engine.sell_scenarios import CandleKind, PointCandle
from engine.three_run import ThreeRunDetector

T0 = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
M1 = timedelta(minutes=1)

# BUY_STRATEGY_PROMPT.md §12 1m fixtures: open, high, low, close
FIX = {
    "P1": (1.40110, 1.40112, 1.40085, 1.40090),
    "P2": (1.40090, 1.40093, 1.40060, 1.40065),
    "P": (1.40070, 1.40072, 1.40040, 1.40045),
    "R1_eq": (1.40045, 1.40060, 1.40040, 1.40055),
    "R1_sw": (1.40045, 1.40060, 1.40033, 1.40055),
    "R1_miss": (1.40045, 1.40060, 1.40041, 1.40055),
    "D1": (1.40048, 1.40060, 1.40040, 1.40048),
    "D1_hi": (1.40050, 1.40056, 1.40045, 1.40050),
    "R2": (1.40055, 1.40070, 1.40050, 1.40065),
    "Dm": (1.40055, 1.40062, 1.40050, 1.40055),
    "Dx": (1.40050, 1.40056, 1.40044, 1.40050),
    "R3": (1.40065, 1.40080, 1.40060, 1.40075),
    "D3": (1.40065, 1.40072, 1.40058, 1.40065),
    # a bullish prior run and a bearish run whose first candle equals its high (the mirror)
    "U1": (1.40000, 1.40030, 1.39995, 1.40025),
    "U2": (1.40025, 1.40050, 1.40020, 1.40045),
    "S1": (1.40045, 1.40050, 1.40030, 1.40035),
    "S2": (1.40035, 1.40040, 1.40020, 1.40025),
    "S3": (1.40025, 1.40030, 1.40010, 1.40015),
}
PRIOR = ["P1", "P2", "P"]  # the doc's 3-candle bearish prior run, lowest low 1.40040


def candle(i: int, ohlc: tuple) -> PointCandle:
    return PointCandle.of(Candle(T0 + i * M1, *ohlc), 0.00001)


def fire_bars(names, counting="doc_exact", tol=0, detector=None):
    """(index, signal) for every bar where a run fired."""
    detector = detector or ThreeRunDetector(counting, tol)
    fired = []
    for i, name in enumerate(names):
        c = candle(i, FIX[name])
        signal = detector.push(c, candle_kind_pct(c, 5.0))
        if signal is not None:
            fired.append((i, signal))
    return fired


def bull_fires(names, **kwargs):
    return [(i, s) for i, s in fire_bars(names, **kwargs) if s.direction is CandleKind.BULL]


def bull_bars(names, **kwargs):
    return [i for i, _ in bull_fires(names, **kwargs)]


class TestCandleKind(unittest.TestCase):
    def test_body_at_five_percent_of_range_is_a_doji(self):
        self.assertIs(candle_kind_pct(candle(0, (1.40055, 1.40065, 1.40045, 1.40056)), 5.0), CandleKind.DOJI)
        self.assertIs(candle_kind_pct(candle(0, (1.40055, 1.40065, 1.40045, 1.40057)), 5.0), CandleKind.BULL)

    def test_zero_range_candle_is_a_doji(self):
        self.assertIs(candle_kind_pct(candle(0, (1.40050, 1.40050, 1.40050, 1.40050)), 5.0), CandleKind.DOJI)


class TestDojiTable(unittest.TestCase):
    """§4.4: the new run after a 3-candle bearish prior run, and the bar it signals on."""

    def test_bull_bull_bull_fires_on_the_third(self):
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "R2", "R3"]), [5])

    def test_doji_bull_bull_fires_on_the_third(self):
        self.assertEqual(bull_bars(PRIOR + ["D1", "R2", "R3"]), [5])

    def test_single_doji_in_position_2_moves_the_signal_to_bar_4(self):
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "Dm", "R2", "R3"]), [6])

    def test_bull_bull_doji_fires_on_the_doji(self):
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "R2", "D3"]), [5])

    def test_doji_bull_doji_fires_on_the_second_doji(self):
        self.assertEqual(bull_bars(PRIOR + ["D1", "R2", "D3"]), [5])

    def test_doji_doji_bull_fires_on_the_bull(self):
        self.assertEqual(bull_bars(PRIOR + ["D1", "Dm", "R3"]), [5])

    def test_bull_doji_doji_fires_on_the_second_doji(self):
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "Dm", "D3"]), [5])

    def test_third_doji_drops_the_pending_dojis(self):
        ((i, signal),) = bull_fires(PRIOR + ["D1", "Dm", "Dx", "R1_eq", "R2", "R3"])
        self.assertEqual(i, 8)
        self.assertEqual(signal.doji_positions, ())
        self.assertEqual(signal.first.timestamp, T0 + 6 * M1)


class TestDerivedBehaviours(unittest.TestCase):
    """§4.5 items 1-4."""

    def test_two_dojis_after_one_bull_count(self):
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "Dm", "D3"]), [5])
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "Dm", "R2"]), [])

    def test_short_prior_run_absorbs_two_dojis(self):
        self.assertEqual(bull_bars(["P", "D1", "Dm", "R3"]), [])
        self.assertEqual(bull_bars(["P", "D1", "R2", "R3"]), [3])

    def test_eligibility_uses_the_first_dojis_own_low(self):
        self.assertEqual(bull_bars(["P", "D1_hi", "R1_sw", "R2"]), [])

    def test_one_tick_miss_is_rejected_unless_tolerated(self):
        self.assertEqual(bull_bars(["P", "R1_miss", "R2", "R3"]), [])
        self.assertEqual(bull_bars(["P", "R1_miss", "R2", "R3"], tol=1), [3])

    def test_every_doji_counts_alternative(self):
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "Dm", "R2"], counting="every_doji_counts"), [5])

    def test_run_fires_only_once(self):
        self.assertEqual(bull_bars(PRIOR + ["R1_eq", "R2", "R3", "R3"]), [5])


class TestSignalDetail(unittest.TestCase):
    def test_signal_carries_first_candle_members_and_prior_run(self):
        ((i, signal),) = bull_fires(PRIOR + ["D1", "Dm", "R3"])
        self.assertEqual(i, 5)
        self.assertEqual(signal.first.timestamp, T0 + 3 * M1)
        self.assertEqual(signal.signal.timestamp, T0 + 5 * M1)
        self.assertEqual(signal.doji_positions, (1, 2))
        self.assertEqual(signal.low, 140040)
        self.assertEqual(signal.prior_low, 140040)
        self.assertEqual([m.candle.timestamp for m in signal.prior_members], [T0, T0 + M1, T0 + 2 * M1])

    def test_bearish_mirror(self):
        ((i, signal),) = fire_bars(["U1", "U2", "S1", "S2", "S3"])
        self.assertEqual(i, 4)
        self.assertIs(signal.direction, CandleKind.BEAR)
        self.assertEqual(signal.prior_high, 140050)

    def test_reset_forgets_the_prior_run(self):
        detector = ThreeRunDetector()
        fire_bars(["P"], detector=detector)
        detector.reset()
        self.assertEqual(fire_bars(["R1_eq", "R2", "R3"], detector=detector), [])

    def test_invalid_options_are_rejected(self):
        with self.assertRaises(ValueError):
            ThreeRunDetector("count_some")
        with self.assertRaises(ValueError):
            ThreeRunDetector(eq_tol_pts=-1)


if __name__ == "__main__":
    unittest.main()
