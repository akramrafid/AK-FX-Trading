"""scripts/generate_3yr_dataset.py
Generates 3+ years of realistic EUR/USD 1-minute historical data (2021-01-04 to 2024-01-05)
incorporating real Forex market mechanics:
- London/NY liquidity sweeps
- Session-based volatility clustering (Asian range, London expansion, NY reversal)
- Realistic spread & pip scaling
Zero third-party dependencies.
"""

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def generate_3yr_forex_m1(output_csv: str = "data/EURUSD_M1_3Y.csv") -> int:
    path = Path(output_csv)
    path.parent.mkdir(parents=True, exist_ok=True)

    start_date = datetime(2021, 1, 4, 0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2024, 1, 5, 23, 59, 0, tzinfo=timezone.utc)

    # Seed for determinism and reproducibility
    random.seed(42)

    current_price = 1.2250
    current_time = start_date
    candle_count = 0

    print(f"Generating 3+ years of M1 Forex data from {start_date.date()} to {end_date.date()}...")

    with open(path, "w", encoding="utf-8") as f:
        f.write("timestamp,open,high,low,close,volume\n")

        while current_time <= end_date:
            # Skip weekends (Forex market closes Friday 22:00 UTC, opens Sunday 22:00 UTC)
            weekday = current_time.weekday()
            hour = current_time.hour
            minute = current_time.minute

            if weekday == 4 and hour >= 22:
                # Friday after 22:00 UTC -> advance to Sunday 22:00 UTC
                current_time += timedelta(days=2)
                continue
            if weekday == 5:
                # Saturday
                current_time += timedelta(days=1)
                continue
            if weekday == 6 and hour < 22:
                # Sunday before 22:00 UTC
                current_time += timedelta(hours=1)
                continue

            # Determine session volatility multiplier
            if 0 <= hour < 7:
                # Asian session (quiet consolidation)
                vol_base = 0.00015
                drift = random.gauss(0, 0.00003)
            elif 7 <= hour < 12:
                # London open & morning (breakouts, liquidity sweeps)
                vol_base = 0.00040
                drift = random.gauss(0, 0.00008)
            elif 12 <= hour < 17:
                # London / New York overlap (peak volatility & reversals)
                vol_base = 0.00045
                drift = random.gauss(0, 0.00009)
            elif 17 <= hour < 21:
                # Late NY session
                vol_base = 0.00025
                drift = random.gauss(0, 0.00004)
            else:
                # Rollover / Asian lead-in
                vol_base = 0.00018
                drift = random.gauss(0, 0.00003)

            # Bar open
            open_p = current_price
            delta = drift + random.gauss(0, vol_base * 0.4)
            close_p = open_p + delta

            # Wicks: occasionally create deep liquidity sweep wicks
            is_sweep_wick = random.random() < 0.03
            if is_sweep_wick:
                wick_mult = random.uniform(2.5, 4.5)
            else:
                wick_mult = random.uniform(1.1, 1.8)

            high_wick = abs(random.gauss(0, vol_base * 0.3 * wick_mult))
            low_wick = abs(random.gauss(0, vol_base * 0.3 * wick_mult))

            high_p = max(open_p, close_p) + high_wick
            low_p = min(open_p, close_p) - low_wick

            # Precision rounding to 5 decimal places (typical EUR/USD)
            open_p = round(open_p, 5)
            high_p = round(high_p, 5)
            low_p = round(low_p, 5)
            close_p = round(close_p, 5)

            # Invariant safety check
            if high_p < max(open_p, close_p):
                high_p = max(open_p, close_p)
            if low_p > min(open_p, close_p):
                low_p = min(open_p, close_p)

            volume = round(random.uniform(50, 400), 1)

            time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{time_str},{open_p:.5f},{high_p:.5f},{low_p:.5f},{close_p:.5f},{volume}\n")

            current_price = close_p
            # Keep price within realistic historical EUR/USD macro band [0.95, 1.25]
            if current_price < 0.9600:
                current_price += 0.0010
            elif current_price > 1.2400:
                current_price -= 0.0010

            current_time += timedelta(minutes=1)
            candle_count += 1

            if candle_count % 200000 == 0:
                print(f"Generated {candle_count:,} M1 candles (up to {time_str})...")

    print(f"Complete! Generated {candle_count:,} candles saved to {output_csv}.")
    return candle_count


if __name__ == "__main__":
    generate_3yr_forex_m1()
