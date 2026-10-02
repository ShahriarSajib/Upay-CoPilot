"""End-to-end dataset generation pipeline.

Order matters: recurring obligations are defined before the ledger is built,
because the ledger's monthly bills come from those obligations. Goals are
funded only after the ledger exists, so contributions can never exceed real
surplus. Labels and profiles come last, because they are derived from the
finished ledger.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import MONTHS, NUM_USERS, OUTPUT_DIR, SEED, SPLIT_DIRS, START_DATE
from .goals import (
    apply_contributions,
    generate_goal_contributions,
    generate_goals,
    monthly_surplus,
)
from .labels import build_behavior_labels
from .profiles import build_financial_profiles
from .recurring import build_recurring_expenses
from .splits import split_frames, split_summary, write_splits
from .transactions import generate_transactions
from .users import generate_all_income, generate_users, generate_wallets

# Tables written to data/generated, in dependency order.
TABLE_ORDER = [
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
]


def month_starts(count: int = MONTHS, start: pd.Timestamp | None = None) -> list[pd.Timestamp]:
    first = pd.Timestamp(start) if start is not None else pd.Timestamp(START_DATE)
    return [first + pd.offsets.MonthBegin(i) for i in range(count)]


def build_dataset(
    seed: int = SEED, num_users: int = NUM_USERS, months_count: int = MONTHS
) -> dict[str, pd.DataFrame]:
    """Generate every table, with independent RNG streams per stage."""
    months = month_starts(months_count)

    users = generate_users(np.random.default_rng(seed), num_users, months_count)
    wallets = generate_wallets(np.random.default_rng(seed + 10), users, months_count)
    print(f"  users={len(users)} wallets={len(wallets)}")

    income = generate_all_income(np.random.default_rng(seed + 1), users, months)
    print(f"  income_events={len(income)}")

    recurring = build_recurring_expenses(
        np.random.default_rng(seed + 2), users, months[-1]
    )
    print(f"  recurring_expenses={len(recurring)}")

    transactions, patterns, wallets = generate_transactions(
        np.random.default_rng(seed + 3), users, wallets, income, recurring, months
    )
    print(f"  transactions={len(transactions)}")

    surplus = monthly_surplus(transactions)
    goals = generate_goals(np.random.default_rng(seed + 4), users, surplus, months)
    contributions = generate_goal_contributions(
        np.random.default_rng(seed + 5), goals, users, surplus, months
    )
    goals = apply_contributions(goals, contributions)
    print(f"  goals={len(goals)} contributions={len(contributions)}")

    profiles = build_financial_profiles(transactions, wallets)
    labels = build_behavior_labels(transactions, contributions, patterns, months)
    print(f"  profiles={len(profiles)} labels={len(labels)}")

    return {
        "users": users,
        "wallets": wallets,
        "income_events": income,
        "recurring_expenses": recurring,
        "transactions": transactions,
        "financial_goals": goals,
        "goal_contributions": contributions,
        "financial_profiles": profiles,
        "behavior_labels": labels,
        "injected_patterns": patterns,
    }


def _serialise(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert date/timestamp columns for stable CSV round-trips."""
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif pd.api.types.is_object_dtype(out[column]):
            out[column] = out[column].map(
                lambda value: value.isoformat() if hasattr(value, "isoformat") else value
            )
    return out


def write_dataset(tables: dict[str, pd.DataFrame], output_dir: str = OUTPUT_DIR) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    for name in TABLE_ORDER:
        frame = tables.get(name)
        if frame is None:
            continue
        path = target / f"{name}.csv"
        _serialise(frame).to_csv(path, index=False)
        written[name] = path

    return written


def write_temporal_splits(
    tables: dict[str, pd.DataFrame], directories: dict[str, str] = SPLIT_DIRS
) -> dict[str, pd.DataFrame]:
    """Materialise time-based train/validation/test splits."""
    time_scoped = {
        name: frame
        for name, frame in tables.items()
        if name not in ("users", "wallets")
    }
    splits = split_frames(time_scoped)
    write_splits(splits, directories)
    return splits


def generate_all(
    seed: int = SEED,
    num_users: int = NUM_USERS,
    months_count: int = MONTHS,
    output_dir: str = OUTPUT_DIR,
    split_dirs: dict[str, str] = SPLIT_DIRS,
) -> dict[str, pd.DataFrame]:
    """Generate, persist and split the dataset in one call."""
    print(f"Generating synthetic dataset (seed={seed}, users={num_users}, months={months_count})")
    tables = build_dataset(seed=seed, num_users=num_users, months_count=months_count)

    written = write_dataset(tables, output_dir)
    print(f"\nWrote {len(written)} tables to {output_dir}/")

    write_temporal_splits(tables, split_dirs)
    print("\nTemporal split (row counts):")
    print(split_summary(tables).to_string(index=False))

    return tables