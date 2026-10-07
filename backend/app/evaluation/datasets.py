"""One shared, memoised view of the data for an entire evaluation run.

Everything downstream -- forecasting baselines, the anomaly window, the health
folds, the SHAP pass, the impact simulation -- reads from here so that:

* the ledger and the derived feature frames are built **once** per run rather
  than once per module;
* every module reports the same row counts, periods and seed, so two numbers
  in the same report are always about the same data;
* the test window can be labelled (and then refused) explicitly rather than
  by convention.

:func:`load` is the only supported entry point. It is idempotent: calling it
any number of times returns the same frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.data.splits import (
    SPLIT_NAMES,
    assert_disjoint_periods,
    build_features,
    load_all_splits,
)
from app.evaluation.metrics import SEED


@dataclass
class Dataset:
    """The frames every evaluation module needs."""

    splits: dict[str, Any]
    transactions: pd.DataFrame
    wallets: pd.DataFrame
    contributions: pd.DataFrame
    goals: pd.DataFrame
    behaviour_labels: pd.DataFrame
    profile_labels: pd.DataFrame
    periods: dict[str, list[str]] = field(default_factory=dict)
    windows: dict[str, set[str]] = field(default_factory=dict)
    daily: pd.DataFrame | None = None
    monthly: pd.DataFrame | None = None
    features: dict[str, Any] = field(default_factory=dict)
    seed: int = SEED

    # -- helpers ---------------------------------------------------------

    @property
    def train_periods(self) -> set[str]:
        return self.windows["train"]

    @property
    def validation_periods(self) -> set[str]:
        return self.windows["validation"]

    @property
    def test_periods(self) -> set[str]:
        return self.windows["test"]

    def periods_of(self, name: str) -> set[str]:
        return self.windows[name]

    def description(self) -> dict:
        return {
            "splits": [split.describe() for split in self.splits.values()],
            "periods": self.periods,
            "disjoint": self.periods.get("_disjoint"),
            "n_transactions": int(len(self.transactions)),
            "n_customers": int(self.transactions["user_id"].nunique()),
            "n_behaviour_label_rows": int(len(self.behaviour_labels)),
            "n_profile_label_rows": int(len(self.profile_labels)),
            "seed": self.seed,
        }

    def build_frame(self, name: str, builder) -> Any:
        """Build and cache an expensive derived frame on first use."""
        if name not in self.features:
            self.features[name] = builder()
        return self.features[name]


_CACHE: Dataset | None = None


def load(force: bool = False) -> Dataset:
    """Load (or return the cached) evaluation dataset."""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    splits = load_all_splits()
    transactions = pd.concat(
        [splits[name].transactions for name in SPLIT_NAMES], ignore_index=True
    )
    wallets = (
        pd.concat([splits[name].feature("wallets") for name in SPLIT_NAMES], ignore_index=True)
        .drop_duplicates(subset=["wallet_id"])
    )
    contributions = pd.concat(
        [splits[name].feature("goal_contributions") for name in SPLIT_NAMES], ignore_index=True
    )
    goals = pd.concat([splits[name].goals for name in SPLIT_NAMES], ignore_index=True)
    behaviour = (
        pd.concat([splits[name].label("behavior_labels") for name in SPLIT_NAMES], ignore_index=True)
        .drop_duplicates(subset=["user_id", "period"])
    )
    profile = (
        pd.concat(
            [splits[name].label("financial_profiles") for name in SPLIT_NAMES], ignore_index=True
        )
        .drop_duplicates(subset=["user_id"])
    )

    periods = {name: list(split.periods) for name, split in splits.items()}
    periods["_disjoint"] = _flatten(assert_disjoint_periods())

    _CACHE = Dataset(
        splits=splits,
        transactions=transactions,
        wallets=wallets,
        contributions=contributions,
        goals=goals,
        behaviour_labels=behaviour,
        profile_labels=profile,
        periods=periods,
        windows={name: set(splits[name].periods) for name in SPLIT_NAMES},
        seed=SEED,
    )
    return _CACHE


def _flatten(window_report: dict) -> list[str]:
    return [f"{name}: {','.join(value)}" for name, value in window_report.items()]


def reset() -> None:
    """Drop the cache (used by tests and by a second, different run)."""
    global _CACHE
    _CACHE = None
