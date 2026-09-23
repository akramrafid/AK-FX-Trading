"""
Historical OHLCV Data Ingestion Pipeline.

Supports Dukascopy, MetaTrader 4 (MT4), and standard CSV formats.
Normalizes data into immutable, validated Candle model instances.
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

from engine.models import Candle


DATETIME_FORMATS = [
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y%m%d %H:%M:%S",
    "%Y%m%d %H:%M",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
]


def parse_timestamp(date_str: str, time_str: Optional[str] = None) -> datetime:
    """Parse date/time string(s) into a UTC-aware datetime object."""
    combined = f"{date_str.strip()} {time_str.strip()}" if time_str else date_str.strip()
    # Strip sub-second milliseconds if present (e.g. .000)
    if "." in combined:
        parts = combined.split(" ")
        time_part = parts[-1]
        if "." in time_part:
            time_clean = time_part.split(".")[0]
            parts[-1] = time_clean
            combined = " ".join(parts)

    for fmt in DATETIME_FORMATS:
        try:
            dt = datetime.strptime(combined, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        # Fallback to ISO format parsing
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as exc:
        raise ValueError(f"Unable to parse timestamp: '{date_str}' (time: '{time_str}')") from exc


def parse_candle_row(
    timestamp: datetime,
    open_val: Union[str, float],
    high_val: Union[str, float],
    low_val: Union[str, float],
    close_val: Union[str, float],
    volume_val: Union[str, float] = 0.0,
) -> Candle:
    """Create a validated Candle instance with float conversion and invariant checks."""
    o = float(open_val)
    h = float(high_val)
    l = float(low_val)
    c = float(close_val)
    v = float(volume_val) if volume_val else 0.0
    return Candle(timestamp=timestamp, open=o, high=h, low=l, close=c, volume=v)


def load_candles_from_csv(
    filepath: Union[str, Path],
    delimiter: str = ",",
    skip_invalid: bool = False,
) -> List[Candle]:
    """
    Load OHLCV candles from a CSV file.
    
    Supports:
    1. Headered standard: timestamp,open,high,low,close,volume
    2. Dukascopy format: Gmt time,Open,High,Low,Close,Volume
    3. MT4 History Export: Date,Time,Open,High,Low,Close,Volume (with or without headers)
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"Historical data file not found: {path}")

    candles: List[Candle] = []

    with open(path, mode="r", encoding="utf-8", errors="replace") as f:
        # Peek first lines to inspect headers
        sample = [f.readline() for _ in range(5)]
        f.seek(0)

        # Detect delimiter if not strictly comma
        first_line = sample[0] if sample else ""
        if "\t" in first_line:
            delimiter = "\t"
        elif ";" in first_line:
            delimiter = ";"

        reader = csv.reader(f, delimiter=delimiter)
        raw_header = next(reader, None)
        if not raw_header:
            return []

        # Analyze header
        cleaned_header = [h.strip().lower().replace("<", "").replace(">", "") for h in raw_header]
        has_named_header = any(h in cleaned_header for h in ("open", "close", "time", "date"))

        # Map column indexes
        if has_named_header:
            col_map = {col: idx for idx, col in enumerate(cleaned_header)}
            date_col = col_map.get("date", col_map.get("gmt time", col_map.get("time", col_map.get("timestamp", 0))))
            time_col = col_map.get("time") if "date" in col_map and "time" in col_map and col_map["date"] != col_map["time"] else None
            open_col = col_map.get("open", 1)
            high_col = col_map.get("high", 2)
            low_col = col_map.get("low", 3)
            close_col = col_map.get("close", 4)
            vol_col = col_map.get("volume", col_map.get("vol", col_map.get("tickvol", None)))
        else:
            # No header: Assume MT4 format: Date, Time, Open, High, Low, Close, Volume
            # or: Timestamp, Open, High, Low, Close, Volume
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            first_row = next(reader)
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            if len(first_row) >= 7:
                date_col, time_col, open_col, high_col, low_col, close_col = 0, 1, 2, 3, 4, 5
                vol_col = 6
            else:
                date_col, time_col, open_col, high_col, low_col, close_col = 0, None, 1, 2, 3, 4
                vol_col = 5 if len(first_row) > 5 else None

        row_idx = 0
        for row in reader:
            row_idx += 1
            if not row or len(row) <= max(open_col, high_col, low_col, close_col):
                continue

            try:
                d_val = row[date_col]
                t_val = row[time_col] if time_col is not None and time_col < len(row) else None
                ts = parse_timestamp(d_val, t_val)
                o = row[open_col]
                h = row[high_col]
                l = row[low_col]
                c = row[close_col]
                v = row[vol_col] if vol_col is not None and vol_col < len(row) else 0.0

                candle = parse_candle_row(ts, o, h, l, c, v)
                candles.append(candle)
            except Exception as exc:
                if skip_invalid:
                    continue
                raise ValueError(f"Error parsing row {row_idx}: {row} -> {exc}") from exc

    # Ensure chronological ascending sort
    candles.sort(key=lambda c: c.timestamp)
    return candles


def save_candles_to_csv(candles: Iterable[Candle], filepath: Union[str, Path]) -> None:
    """Save Candle sequence to standard CSV format."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow([
                c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                f"{c.open:.5f}",
                f"{c.high:.5f}",
                f"{c.low:.5f}",
                f"{c.close:.5f}",
                f"{c.volume:.1f}",
            ])


def find_data_gaps(candles: List[Candle], expected_interval_minutes: int = 5) -> List[Tuple[datetime, datetime]]:
    """Identify missing candle intervals exceeding the expected bar duration (excluding weekends)."""
    gaps: List[Tuple[datetime, datetime]] = []
    if len(candles) < 2:
        return gaps

    expected_seconds = expected_interval_minutes * 60
    for i in range(len(candles) - 1):
        c_curr = candles[i]
        c_next = candles[i + 1]
        diff_seconds = (c_next.timestamp - c_curr.timestamp).total_seconds()

        # If gap is larger than 1.5x expected interval
        if diff_seconds > expected_seconds * 1.5:
            # Check if gap is over weekend (Friday close to Sunday open)
            if c_curr.timestamp.weekday() == 4 and c_next.timestamp.weekday() == 6:
                continue
            gaps.append((c_curr.timestamp, c_next.timestamp))

    return gaps
