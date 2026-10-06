"""Read layer for the Copilot.

The engines never touch storage directly. They ask a :class:`FinancialStore`
for small, well-defined frames (daily per-user series, monthly aggregates,
goals, obligations) and everything downstream — features, models, planning —
is identical no matter where the rows came from.

Two implementations ship:

* :class:`EmbeddedStore`  — reads the generated product dataset
  (``data/generated``) into a cached pandas store.
* :class:`PostgresStore`  — runs the same rollups in SQL against the schema in
  ``app/db/schema.sql``.

Accounting rules are identical in both and match the dataset generator:
user-to-user transfers and cash legs move money *between* wallets, so they are
excluded from income and consumption on both sides.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from app.core.config import settings

# Movements that are neither income nor consumption.
TRANSFER_TYPES = ("send_money", "receive_money")
CASH_CATEGORY = "cash"

DATETIME_COLUMNS: dict[str, tuple[str, ...]] = {
    "transactions": ("timestamp",),
    "income_events": ("timestamp",),
    "goal_contributions": ("timestamp",),
    "injected_patterns": ("timestamp",),
    "recurring_expenses": ("next_due_date",),
    "financial_goals": ("target_date", "created_date"),
}

BOOL_COLUMNS: dict[str, tuple[str, ...]] = {
    "transactions": ("cash_out", "is_anomaly"),
    "recurring_expenses": ("mandatory",),
    "financial_goals": ("is_achieved",),
}

TABLES = (
    "users",
    "wallets",
    "income_events",
    "recurring_expenses",
    "transactions",
    "financial_goals",
    "goal_contributions",
    "financial_profiles",
    "behavior_labels",
    "injected_patterns",
)


class StoreError(RuntimeError):
    pass


class FinancialStore(Protocol):
    """The surface every engine is allowed to depend on."""

    def table(self, name: str) -> pd.DataFrame: ...
    def users(self) -> pd.DataFrame: ...
    def wallets(self) -> pd.DataFrame: ...
    def transactions(self) -> pd.DataFrame: ...
    def income_events(self) -> pd.DataFrame: ...
    def recurring(self) -> pd.DataFrame: ...
    def goals(self) -> pd.DataFrame: ...
    def contributions(self) -> pd.DataFrame: ...
    def profiles(self) -> pd.DataFrame: ...
    def behavior_labels(self) -> pd.DataFrame: ...
    def injected_patterns(self) -> pd.DataFrame: ...
    def as_of_date(self) -> pd.Timestamp: ...
    def periods(self) -> list[str]: ...


def consumption_mask(transactions: pd.DataFrame) -> pd.Series:
    """Rows that represent real consumption or real inflow (not a wallet move)."""
    return ~transactions["transaction_type"].isin(TRANSFER_TYPES) & (
        transactions["category"] != CASH_CATEGORY
    )


def signed_amount(transactions: pd.DataFrame) -> pd.Series:
    is_inflow = transactions["direction"] == "inflow"
    return np.where(is_inflow, transactions["amount"], -transactions["amount"])


def add_period(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["period"] = out["timestamp"].dt.strftime("%Y-%m")
    return out


def daily_flow(transactions: pd.DataFrame) -> pd.DataFrame:
    """Per user-day income and spending on the shared accounting basis."""
    frame = add_period(transactions)
    # The generated CSVs carry only ``timestamp``, so the calendar day is derived
    # here rather than assumed to be a stored column.
    frame["date"] = frame["timestamp"].dt.normalize()
    frame = frame[consumption_mask(frame)]
    frame = frame.assign(
        income=np.where(frame["direction"] == "inflow", frame["amount"], 0.0),
        spend=np.where(frame["direction"] == "outflow", frame["amount"], 0.0),
    )
    daily = (
        frame.groupby(["user_id", "date", "period"], observed=True)[["income", "spend"]]
        .sum()
        .reset_index()
    )
    daily["net"] = daily["income"] - daily["spend"]
    daily["date"] = pd.to_datetime(daily["date"])
    return daily


def monthly_flow(transactions: pd.DataFrame) -> pd.DataFrame:
    frame = add_period(transactions)
    frame = frame[consumption_mask(frame)]
    frame = frame.assign(
        income=np.where(frame["direction"] == "inflow", frame["amount"], 0.0),
        spend=np.where(frame["direction"] == "outflow", frame["amount"], 0.0),
    )
    monthly = (
        frame.groupby(["user_id", "period"], observed=True)[["income", "spend"]]
        .sum()
        .reset_index()
    )
    monthly["surplus"] = monthly["income"] - monthly["spend"]
    monthly["savings_rate"] = np.where(
        monthly["income"] > 0, monthly["surplus"] / monthly["income"], 0.0
    )
    return monthly


def month_windows(transactions: pd.DataFrame) -> pd.DataFrame:
    """Spending per user-period split into the four thirds of a month.

    This is the quantitative backbone of the "why do I run short before
    month-end" answer: the last third of the month is where pressure builds.
    """
    frame = add_period(transactions)
    frame = frame[(frame["direction"] == "outflow") & consumption_mask(frame)]
    if frame.empty:
        return pd.DataFrame(
            columns=["user_id", "period", "window", "day_of_month", "spend"]
        )
    frame = frame.assign(day_of_month=frame["timestamp"].dt.day)
    frame = frame.assign(
        window=pd.cut(
            frame["day_of_month"],
            bins=[0, 10, 20, 28, 31],
            labels=["d1_10", "d11_20", "d21_28", "d29_31"],
        )
    )
    return (
        frame.groupby(["user_id", "period", "window"], observed=True)["amount"]
        .sum()
        .rename("spend")
        .reset_index()
    )


class EmbeddedStore:
    """CSV-backed store. Loaded once per process, then served from memory."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else settings.data_root
        if not self.root.exists():
            raise StoreError(
                f"Dataset directory not found: {self.root}. "
                "Run `python scripts/generate_dev_dataset.py` first."
            )
        self._tables: dict[str, pd.DataFrame] = {}
        self._lock = threading.Lock()
        self._as_of: pd.Timestamp | None = None
        self._periods: list[str] | None = None

    # -- loading ------------------------------------------------------
    def _load(self, name: str) -> pd.DataFrame:
        path = self.root / f"{name}.csv"
        if not path.exists():
            raise StoreError(f"Missing table: {path}")
        frame = pd.read_csv(
            path,
            parse_dates=list(DATETIME_COLUMNS.get(name, ())),
            keep_default_na=True,
        )
        for column in BOOL_COLUMNS.get(name, ()):
            if column in frame.columns:
                frame[column] = (
                    frame[column].astype(str).str.strip().str.lower().isin({"true", "1", "t"})
                )
        return frame

    def table(self, name: str) -> pd.DataFrame:
        if name not in TABLES:
            raise StoreError(f"Unknown table '{name}'. Known: {', '.join(TABLES)}")
        with self._lock:
            if name not in self._tables:
                self._tables[name] = self._load(name)
            return self._tables[name]

    # -- accessors ----------------------------------------------------
    def users(self) -> pd.DataFrame:
        return self.table("users")

    def wallets(self) -> pd.DataFrame:
        return self.table("wallets")

    def transactions(self) -> pd.DataFrame:
        return self.table("transactions")

    def income_events(self) -> pd.DataFrame:
        return self.table("income_events")

    def recurring(self) -> pd.DataFrame:
        return self.table("recurring_expenses")

    def goals(self) -> pd.DataFrame:
        return self.table("financial_goals")

    def contributions(self) -> pd.DataFrame:
        return self.table("goal_contributions")

    def profiles(self) -> pd.DataFrame:
        return self.table("financial_profiles")

    def behavior_labels(self) -> pd.DataFrame:
        return self.table("behavior_labels")

    def injected_patterns(self) -> pd.DataFrame:
        return self.table("injected_patterns")

    # -- calendar -----------------------------------------------------
    def as_of_date(self) -> pd.Timestamp:
        if self._as_of is None:
            self._as_of = pd.Timestamp(self.transactions()["timestamp"].max()).normalize()
        return self._as_of

    def periods(self) -> list[str]:
        if self._periods is None:
            monthly = monthly_flow(self.transactions())
            if monthly.empty:
                self._periods = []
            else:
                self._periods = sorted(monthly["period"].unique().tolist())
        return self._periods

    # -- precomputed shared views -------------------------------------
    def daily_flow(self) -> pd.DataFrame:
        return daily_flow(self.transactions())

    def monthly_flow(self) -> pd.DataFrame:
        return monthly_flow(self.transactions())

    def month_windows(self) -> pd.DataFrame:
        return month_windows(self.transactions())


def get_store() -> FinancialStore:
    """Build the configured store; embedded mode is an explicit no-DB fallback."""
    url = settings.database_url
    if settings.use_postgres and url.startswith("postgres"):
        from app.db.postgres_store import PostgresStore
        return PostgresStore(url)
    return EmbeddedStore()


@lru_cache(maxsize=1)
def cached_store() -> FinancialStore:
    return get_store()


def reset_store_cache() -> None:
    cached_store.cache_clear()
