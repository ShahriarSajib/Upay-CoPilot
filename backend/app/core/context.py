"""Per-user financial context.

Every engine needs the same thing: this customer's daily and monthly feature
history, their ledger, their obligations and their goals, all aligned to the
dataset's as-of date. Rebuilding that per request would be wasteful and would
let two engines disagree, so it is assembled once and cached.

Nothing here interprets or judges. It only gathers and aligns facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from app.db.store import FinancialStore, cached_store, consumption_mask, month_windows
from app.features.build import (
    _reindex_calendar,
    daily_features,
    monthly_features,
    user_features,
)
from app.ml.forecast import day_of_month_profile, income_day_profile


def _require_user(store: FinancialStore, user_id: str) -> pd.Series:
    users = store.users()
    match = users[users["user_id"] == user_id]
    if match.empty:
        raise KeyError(f"Unknown user_id {user_id!r}")
    return match.iloc[0]


@dataclass
class UserContext:
    """Everything known about one customer, aligned to one as-of date."""

    store: FinancialStore
    user_id: str
    profile: pd.Series
    as_of: pd.Timestamp
    current_period: str
    periods: list[str]
    daily: pd.DataFrame
    monthly: pd.DataFrame
    transactions: pd.DataFrame
    wallets: pd.DataFrame
    income_events: pd.DataFrame
    recurring: pd.DataFrame
    goals: pd.DataFrame
    contributions: pd.DataFrame
    month_windows: pd.DataFrame
    features: pd.DataFrame = field(default_factory=pd.DataFrame)

    # -- convenience accessors -----------------------------------------
    @property
    def display_name(self) -> str:
        """Prefer the synthetic full name, falling back to the opaque id."""
        if "full_name" in self.profile.index and isinstance(self.profile["full_name"], str):
            return self.profile["full_name"]
        return self.user_id

    @property
    def name_bn(self) -> str:
        if "name_bn" in self.profile.index and isinstance(self.profile["name_bn"], str):
            return self.profile["name_bn"]
        return self.display_name

    @property
    def persona(self) -> str:
        return str(self.profile.get("persona", "unknown"))

    def month_row(self, period: str) -> pd.Series | None:
        """One month's aggregate row, or None if the period predates history.

        Named ``month_row`` rather than ``monthly`` on purpose: a method sharing
        a name with a dataclass field is silently adopted by ``dataclasses`` as
        that field's default value.
        """
        match = self.monthly[self.monthly["period"] == period]
        return None if match.empty else match.iloc[0]

    def history(self, periods: int) -> pd.DataFrame:
        """Most recent ``periods`` months, oldest first."""
        return self.monthly.tail(periods)

    def period_flow(self) -> pd.Series:
        """Income/spend/balance for the current (partial or complete) period."""
        row = self.month_row(self.current_period)
        if row is not None:
            return row
        if self.monthly.empty:
            raise ValueError(f"No monthly history for {self.user_id}")
        return self.monthly.iloc[-1]

    def consumption(self) -> pd.DataFrame:
        """Outflow rows that count as real spending (excludes transfers)."""
        return self.transactions[consumption_mask(self.transactions)]

    def spend_profile_by_day(self) -> pd.Series:
        """Share of this user's spending by day-of-month, length 31."""
        return pd.Series(day_of_month_profile(self.daily, self.user_id, "spend"))

    def income_profile_by_day(self) -> pd.Series:
        return pd.Series(income_day_profile(self.income_events, self.user_id))

    def feature(self, key: str, default: float | None = None) -> float | None:
        if self.features.empty or key not in self.features.columns:
            return default
        value = self.features.iloc[-1][key]
        if pd.isna(value):
            return default
        return float(value)

    def summary(self) -> dict:
        """Small header block shared by API responses and the assistant."""
        return {
            "user_id": self.user_id,
            "name": self.display_name,
            "name_bn": self.name_bn,
            "persona": self.persona,
            "occupation": str(self.profile.get("occupation", "")),
            "age_group": str(self.profile.get("age_group", "")),
            "location_type": str(self.profile.get("location_type", "")),
            "as_of": self.as_of.date().isoformat(),
            "current_period": self.current_period,
        }


@lru_cache(maxsize=1)
def _shared_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Daily/monthly/user feature frames, computed once per process."""
    store = cached_store()
    daily = _reindex_calendar(daily_features(store.transactions(), store.wallets()))
    monthly = monthly_features(daily, store.contributions(), store.goals())
    users = user_features(
        daily,
        monthly,
        store.users(),
        store.wallets(),
        store.recurring(),
        store.goals(),
        store.contributions(),
    )
    return daily, monthly, users


def build_context(user_id: str, store: FinancialStore | None = None) -> UserContext:
    store = store or cached_store()
    daily, monthly, users = _shared_frames()
    profile = _require_user(store, user_id)
    as_of = store.as_of_date()
    periods = store.periods()

    transactions = store.transactions()
    return UserContext(
        store=store,
        user_id=user_id,
        profile=profile,
        as_of=as_of,
        current_period=periods[-1],
        periods=periods,
        daily=daily[daily["user_id"] == user_id].copy(),
        monthly=monthly[monthly["user_id"] == user_id].sort_values("period").reset_index(drop=True),
        transactions=transactions[transactions["user_id"] == user_id].copy(),
        wallets=store.wallets()[store.wallets()["user_id"] == user_id].copy(),
        income_events=store.income_events()[store.income_events()["user_id"] == user_id].copy(),
        recurring=store.recurring()[store.recurring()["user_id"] == user_id].copy(),
        goals=store.goals()[store.goals()["user_id"] == user_id].copy(),
        contributions=store.contributions()[store.contributions()["user_id"] == user_id].copy(),
        month_windows=month_windows(transactions[transactions["user_id"] == user_id]),
        features=users[users["user_id"] == user_id].copy(),
    )


@lru_cache(maxsize=128)
def get_context(user_id: str) -> UserContext:
    return build_context(user_id)


def list_users() -> pd.DataFrame:
    """Directory used by the user switcher in the UI."""
    store = cached_store()
    users = store.users().copy()
    columns = ["user_id", "persona", "occupation", "age_group", "location_type"]
    if "full_name" in users.columns:
        columns.insert(1, "full_name")
    if "name_bn" in users.columns:
        columns.insert(2, "name_bn")
    return users[[c for c in columns if c in users.columns]]


def clear_context_cache() -> None:
    get_context.cache_clear()
    _shared_frames.cache_clear()