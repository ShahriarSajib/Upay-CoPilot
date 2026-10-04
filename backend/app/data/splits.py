"""Leak-safe loader for ``data/dev/splits``.

Why this module exists
----------------------
``data/dev/splits`` is not one flat CSV. It is three *temporal* windows::

    data/dev/splits/
      train/      features/{users,wallets,transactions,income_events,
                           recurring_expenses,financial_goals,goal_contributions}.csv
                 labels/{behavior_labels,financial_profiles,injected_patterns}.csv
      validation/ ...same layout...
      test/       ...same layout...

The split boundary is **time**, not user:

===============  ====================  ==========================
split            periods               transaction rows
===============  ====================  ==========================
train            2026-01 .. 2026-05   4061
validation       2026-06 .. 2026-07   1802
test             2026-08 .. 2026-09   1746
===============  ====================  ==========================

Every period is read back from the rows themselves (see :func:`split_periods`)
rather than hard-coded, so re-running the generator with a different horizon
does not silently train on the wrong window.

Two invariants this loader is responsible for
---------------------------------------------
1. **Features never carry ground truth.** ``train/features/transactions.csv``
   has no ``is_anomaly`` / ``pattern_type`` column; ``financial_goals.csv`` has
   no ``current_amount`` / ``is_achieved`` / ``progress_ratio``. The loader
   re-attaches those *only* under ``labels/`` keys so training code has to ask
   for them by name, and :func:`assert_no_label_leakage` fails loudly if a label
   column is found on a feature frame.
2. **User roster != user activity.** ``features/users.csv`` lists 500 users but
   only 50 of them have transactions in this development dataset. Every consumer
   must therefore inner-join activity onto the roster; :func:`active_users`
   returns the users that actually moved money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings

SPLIT_NAMES = ("train", "validation", "test")

FEATURE_TABLES: tuple[str, ...] = (
    "users",
    "wallets",
    "transactions",
    "income_events",
    "recurring_expenses",
    "financial_goals",
    "goal_contributions",
)

LABEL_TABLES: tuple[str, ...] = (
    "behavior_labels",
    "financial_profiles",
    "injected_patterns",
)

DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "transactions": ("timestamp",),
    "income_events": ("timestamp",),
    "goal_contributions": ("timestamp",),
    "injected_patterns": ("timestamp",),
    "recurring_expenses": ("next_due_date",),
    "financial_goals": ("target_date", "created_date"),
}

# Ground-truth columns that must never appear on a *feature* frame.
LABEL_ONLY_COLUMNS: dict[str, tuple[str, ...]] = {
    "transactions": ("is_anomaly", "pattern_type"),
    "financial_goals": ("current_amount", "is_achieved", "progress_ratio"),
    "users": ("persona", "monthly_income_base", "expense_ratio", "income_cv",
              "cash_out_rate", "digital_ratio", "target_savings_rate",
              "goal_count", "anomaly_rate", "full_name", "name_bn"),
}


class SplitError(RuntimeError):
    pass


def splits_root(root: Path | str | None = None) -> Path:
    if root is not None:
        path = Path(root)
    else:
        path = settings.split_path
    # Hard guard: the generated population is never a training source. This is
    # checked here, at the single point every reader goes through, rather than
    # trusted to each caller.
    resolved = path.resolve()
    if "generated" in resolved.parts:
        raise SplitError(
            f"Refusing to read splits from {resolved}: the generated dataset is "
            "out of bounds. Use data/dev/splits."
        )
    if not path.exists():
        raise SplitError(
            f"Split directory not found: {path}. "
            "Run `python scripts/generate_dev_dataset.py` to build it."
        )
    return path


def split_dir(name: str, root: Path | str | None = None) -> Path:
    if name not in SPLIT_NAMES:
        raise SplitError(f"Unknown split '{name}'. Known: {', '.join(SPLIT_NAMES)}")
    return splits_root(root) / name


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read_csv(path: Path, table: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, parse_dates=list(DATE_COLUMNS.get(table, ())))
    if "cash_out" in frame.columns:
        frame["cash_out"] = (
            frame["cash_out"].astype(str).str.strip().str.lower().isin({"true", "1", "t"})
        )
    if "mandatory" in frame.columns:
        frame["mandatory"] = (
            frame["mandatory"].astype(str).str.strip().str.lower().isin({"true", "1", "t"})
        )
    return frame


@dataclass
class Split:
    """One temporal window: activity features plus (optionally) its labels."""

    name: str
    features: dict[str, pd.DataFrame]
    labels: dict[str, pd.DataFrame]
    path: Path

    def feature(self, table: str) -> pd.DataFrame:
        try:
            return self.features[table]
        except KeyError as exc:  # pragma: no cover - programming error
            raise SplitError(f"Split '{self.name}' has no feature table '{table}'") from exc

    def label(self, table: str) -> pd.DataFrame:
        frame = self.labels.get(table)
        if frame is None or frame.empty:
            return pd.DataFrame()
        return frame

    # -- convenience --------------------------------------------------
    @property
    def transactions(self) -> pd.DataFrame:
        """Transactions with ground-truth anomaly labels attached.

        Safe to pass straight to :func:`app.features.build.daily_features`
        (which only reads behaviour columns) or to the anomaly trainer (which
        reads ``is_anomaly`` for *scoring*, never for fitting).
        """
        transactions = self.feature("transactions")
        injected = self.labels.get("injected_patterns")
        if transactions.empty:
            return transactions
        if injected is None or injected.empty:
            out = transactions.copy()
            out["is_anomaly"] = False
            out["pattern_type"] = pd.NA
            return out
        pattern = injected[["transaction_id", "pattern_type"]].drop_duplicates("transaction_id")
        out = transactions.merge(pattern, on="transaction_id", how="left")
        out["is_anomaly"] = out["transaction_id"].isin(set(injected["transaction_id"]))
        return out

    @property
    def goals(self) -> pd.DataFrame:
        """Goals with the label columns restored, for scoring/evaluation only."""
        goals = self.feature("financial_goals")
        if goals.empty:
            return goals

        out = goals.copy()
        # Recompute progress from contributions that fall inside *this* window.
        contributions = self.feature("goal_contributions")
        if not contributions.empty:
            saved = contributions.groupby("goal_id")["amount"].sum().rename("current_amount")
            out = out.merge(saved, on="goal_id", how="left").fillna({"current_amount": 0.0})
        else:
            out["current_amount"] = 0.0
        out["progress_ratio"] = (
            out["current_amount"] / out["target_amount"].clip(lower=1.0)
        )
        out["is_achieved"] = out["current_amount"] >= out["target_amount"]
        return out

    @property
    def periods(self) -> list[str]:
        return split_periods(self.transactions)

    def describe(self) -> dict[str, Any]:
        transactions = self.transactions
        periods = self.periods
        return {
            "split": self.name,
            "periods": periods,
            "period_range": f"{periods[0]}..{periods[-1]}" if periods else "",
            "roster_users": int(self.feature("users")["user_id"].nunique())
            if not self.feature("users").empty
            else 0,
            "active_users": int(transactions["user_id"].nunique()) if not transactions.empty else 0,
            "transactions": int(len(transactions)),
            "transaction_window": (
                f"{transactions['timestamp'].min()}..{transactions['timestamp'].max()}"
                if not transactions.empty
                else ""
            ),
            "injected_anomalies": int(
                len(self.label("injected_patterns"))
            ),
            "behavior_label_rows": int(len(self.label("behavior_labels"))),
            "financial_profile_rows": int(len(self.label("financial_profiles"))),
        }


def load_split(name: str, root: Path | str | None = None) -> Split:
    """Read one split folder into a :class:`Split`."""
    path = split_dir(name, root)
    features = {
        table: _read_csv(path / "features" / f"{table}.csv", table) for table in FEATURE_TABLES
    }
    labels = {
        table: _read_csv(path / "labels" / f"{table}.csv", table) for table in LABEL_TABLES
    }
    labels = {key: value for key, value in labels.items() if not value.empty}
    split = Split(name=name, features=features, labels=labels, path=path)
    assert_no_label_leakage(split)
    return split


@lru_cache(maxsize=1)
def load_all_splits(root: Path | str | None = None) -> dict[str, Split]:
    """All three splits, cached. ``root`` must be hashable (str or None)."""
    return {name: load_split(name, root) for name in SPLIT_NAMES}


def reset_cache() -> None:
    load_all_splits.cache_clear()


# ---------------------------------------------------------------------------
# Leakage assertions
# ---------------------------------------------------------------------------

def assert_no_label_leakage(split: Split) -> None:
    """Fail if a ground-truth column survived onto a feature frame."""
    problems: list[str] = []
    for table, forbidden in LABEL_ONLY_COLUMNS.items():
        frame = split.features.get(table)
        if frame is None or frame.empty:
            continue
        present = sorted(set(frame.columns) & set(forbidden))
        if present:
            problems.append(f"{split.name}/features/{table}.csv has label columns {present}")
    if problems:
        raise SplitError(
            "Label leakage detected in the split folder:\n  - " + "\n  - ".join(problems)
        )


def split_periods(transactions: pd.DataFrame) -> list[str]:
    """Sorted ``YYYY-MM`` periods actually present in a transaction frame."""
    if transactions.empty:
        return []
    stamps = pd.to_datetime(transactions["timestamp"])
    return sorted(stamps.dt.strftime("%Y-%m").unique().tolist())


def split_windows() -> dict[str, set[str]]:
    """Period sets per split, read from the data."""
    return {name: set(split.periods) for name, split in load_all_splits().items()}


def active_users(transactions: pd.DataFrame) -> list[str]:
    """Users that actually moved money (the roster is 500, activity is 50)."""
    if transactions.empty:
        return []
    return sorted(transactions["user_id"].unique().tolist())


def assert_disjoint_periods() -> dict[str, list[str]]:
    """Verify the three windows do not overlap in time."""
    windows = split_windows()
    overlaps: list[str] = []
    for left, right in (("train", "validation"), ("validation", "test"), ("train", "test")):
        shared = windows[left] & windows[right]
        if shared:
            overlaps.append(f"{left}&{right} share {sorted(shared)}")
    if overlaps:
        raise SplitError("Split windows overlap in time: " + "; ".join(overlaps))
    return {name: sorted(periods) for name, periods in windows.items()}


# ---------------------------------------------------------------------------
# Composition helpers (expanding windows, still time-ordered)
# ---------------------------------------------------------------------------

def expanding_transactions(through: str) -> pd.DataFrame:
    """Transactions from *all* splits up to and including ``through``.

    Used for the health/resilience models, where the label is a full-horizon
    property of a customer: the feature vector must be built from the history
    available at the split boundary, never from the horizon it is predicting.
    """
    order = {"train": 0, "validation": 1, "test": 2}
    limit = next((i for name, i in order.items() if name == through), None)
    if limit is None:
        raise SplitError(f"Unknown cut point '{through}'. Use one of: train, validation, test")
    frames = []
    for name in SPLIT_NAMES[: limit + 1]:
        frames.append(load_all_splits()[name].transactions)
    combined = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if not combined.empty:
        combined = combined.sort_values(["user_id", "timestamp"]).reset_index(drop=True)
    return combined


def expanding_wallets(through: str) -> pd.DataFrame:
    order = {"train": 0, "validation": 1, "test": 2}
    limit = order[through]
    frames = []
    for name in SPLIT_NAMES[: limit + 1]:
        frame = load_all_splits()[name].feature("wallets")
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["wallet_id"])


def expanding_recurring(through: str) -> pd.DataFrame:
    order = {"train": 0, "validation": 1, "test": 2}
    limit = order[through]
    frames = []
    for name in SPLIT_NAMES[: limit + 1]:
        frame = load_all_splits()[name].feature("recurring_expenses")
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["recurring_id"])


def expanding_goals(through: str) -> pd.DataFrame:
    order = {"train": 0, "validation": 1, "test": 2}
    limit = order[through]
    frames = []
    for name in SPLIT_NAMES[: limit + 1]:
        frame = load_all_splits()[name].goals
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["goal_id"])


def expanding_contributions(through: str) -> pd.DataFrame:
    order = {"train": 0, "validation": 1, "test": 2}
    limit = order[through]
    frames = []
    for name in SPLIT_NAMES[: limit + 1]:
        frame = load_all_splits()[name].feature("goal_contributions")
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def expanding_users(through: str) -> pd.DataFrame:
    return load_all_splits()[through].feature("users")


@dataclass
class FeatureBundle:
    """Feature frames for one temporal cut point, ready for the ML scripts."""

    cut: str
    daily: pd.DataFrame
    monthly: pd.DataFrame
    user: pd.DataFrame
    periods: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "cut": self.cut,
            "periods": self.periods,
            "daily_rows": int(len(self.daily)),
            "monthly_rows": int(len(self.monthly)),
            "user_rows": int(len(self.user)),
        }


def build_features(through: str) -> FeatureBundle:
    """Run the shared feature pipeline over history up to ``through``.

    ``through='train'``    -> 2026-01..2026-05
    ``through='validation'`` -> 2026-01..2026-07
    ``through='test'``     -> 2026-01..2026-09
    """
    from app.features.build import (
        _reindex_calendar,
        daily_features,
        monthly_features,
        user_features,
    )

    transactions = expanding_transactions(through)
    wallets = expanding_wallets(through)
    recurring = expanding_recurring(through)
    goals = expanding_goals(through)
    contributions = expanding_contributions(through)
    users = expanding_users(through)

    daily = _reindex_calendar(daily_features(transactions, wallets))
    monthly = monthly_features(daily, contributions, goals)
    roster = users[users["user_id"].isin(set(transactions["user_id"]))] if not users.empty else users
    user = user_features(daily, monthly, roster, wallets, recurring, goals, contributions)
    return FeatureBundle(
        cut=through,
        daily=daily,
        monthly=monthly,
        user=user,
        periods=split_periods(transactions),
    )


def describe_all() -> list[dict[str, Any]]:
    """One row per split -- what the training report prints."""
    return [load_all_splits()[name].describe() for name in SPLIT_NAMES]