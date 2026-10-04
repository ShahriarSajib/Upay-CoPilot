"""Period helpers shared by features, models and the API.

The synthetic history ends on the last day of the final month. Everything in
the product is expressed "as of" that date so the demo, the models and the
tests all agree on what "now" means.
"""

from __future__ import annotations

import pandas as pd

PERIOD_FMT = "%Y-%m"


def period_of(timestamp: pd.Series) -> pd.Series:
    return timestamp.dt.strftime(PERIOD_FMT)


def month_start(period: str) -> pd.Timestamp:
    return pd.Period(period, freq="M").start_time


def month_end(period: str) -> pd.Timestamp:
    return pd.Period(period, freq="M").end_time.normalize()


def shift_month(period: str, months: int) -> str:
    return str((pd.Period(period, freq="M") + months).strftime(PERIOD_FMT))


def months_between(start_period: str, end_period: str) -> int:
    """Whole months from start to end, at least 1."""
    delta = pd.Period(end_period, freq="M") - pd.Period(start_period, freq="M")
    return max(int(delta.n), 1)


def month_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    p = pd.Period(period, freq="M")
    return p.start_time, p.end_time.normalize()


def day_of_month_windows(period: str, windows: list[tuple[int, int]]) -> dict[str, str]:
    """Map ``(from_day, to_day)`` inclusive ranges to readable labels."""
    return {f"d{lo}_{hi}": f"Days {lo}-{hi}" for lo, hi in windows}


def describe_window(lo: int, hi: int) -> str:
    return f"Days {lo}-{hi}"


WINDOWS: list[tuple[int, int]] = [(1, 10), (11, 20), (21, 28), (29, 31)]
