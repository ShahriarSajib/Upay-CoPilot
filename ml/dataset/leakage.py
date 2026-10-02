"""Leakage guardrails (Step 13).

Two failure modes matter here:

1. Column leakage - a ground-truth or whole-window aggregate column reaching the
   feature side of a split.
2. Time leakage - a split containing periods outside its own window, or the same
   row appearing in two splits.

The raw ``data/generated`` tables legitimately contain ground-truth columns, so
the column checks run against the written split folders rather than the raw
dataset.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pandas as pd

from .splits import (
    FORBIDDEN_FEATURE_COLUMNS,
    GROUND_TRUTH_COLUMNS,
    LABEL_SIDE_TABLES,
    RESEARCH_SIDE_TABLES,
    SPLIT_PERIODS,
)


def check_feature_files(split_root: str | Path) -> list[str]:
    """Fail if any feature file holds a ground-truth or future-summary column."""
    problems: list[str] = []

    for split in SPLIT_PERIODS:
        feature_dir = Path(split_root) / split / "features"
        if not feature_dir.exists():
            continue

        for path in sorted(feature_dir.glob("*.csv")):
            if path.stem in RESEARCH_SIDE_TABLES:
                problems.append(
                    f"{split}/features/{path.name}: research-only table on the feature side"
                )

            columns = set(pd.read_csv(path, nrows=0).columns)
            ground_truth = sorted(GROUND_TRUTH_COLUMNS & columns)
            if ground_truth:
                problems.append(
                    f"{split}/features/{path.name}: ground-truth column(s) {ground_truth}"
                )

            aggregates = sorted(FORBIDDEN_FEATURE_COLUMNS - GROUND_TRUTH_COLUMNS & columns)
            if aggregates:
                problems.append(
                    f"{split}/features/{path.name}: whole-window column(s) {aggregates}"
                )

    return problems


def check_label_files(split_root: str | Path) -> list[str]:
    """Fail if a label table is missing from the label side of a split."""
    problems: list[str] = []

    for split in SPLIT_PERIODS:
        label_dir = Path(split_root) / split / "labels"
        for name in sorted(LABEL_SIDE_TABLES):
            if not (label_dir / f"{name}.csv").exists():
                problems.append(f"{split}/labels/{name}.csv: missing label table")

    return problems


def check_temporal_ordering(split_root: str | Path) -> list[str]:
    """Fail if any split contains data outside its own period window."""
    problems: list[str] = []

    for split, allowed in SPLIT_PERIODS.items():
        path = Path(split_root) / split / "features" / "transactions.csv"
        if not path.exists():
            continue

        frame = pd.read_csv(path, parse_dates=["timestamp"])
        if not len(frame):
            continue

        periods = set(frame["timestamp"].dt.strftime("%Y-%m"))
        strays = sorted(periods - set(allowed))
        if strays:
            problems.append(f"{split}: contains out-of-window periods {strays}")

    return problems


def check_overlap(split_root: str | Path) -> list[str]:
    """Fail if any transaction id appears in more than one split."""
    problems: list[str] = []
    seen: dict[str, str] = {}

    for split in SPLIT_PERIODS:
        path = Path(split_root) / split / "features" / "transactions.csv"
        if not path.exists():
            continue

        frame = pd.read_csv(path, usecols=["transaction_id"])
        for transaction_id in frame["transaction_id"].to_numpy():
            if transaction_id in seen:
                problems.append(
                    f"transaction {transaction_id} appears in both "
                    f"{seen[transaction_id]} and {split}"
                )
            seen[transaction_id] = split

    return problems


def check_split_chronology(split_root: str | Path) -> list[str]:
    """Fail if a later split contains data that an earlier split would not know."""
    problems: list[str] = []
    order = ["train", "validation", "test"]

    for earlier, later in pairwise(order):
        for table in ("transactions", "income_events", "goal_contributions"):
            earlier_path = Path(split_root) / earlier / "features" / f"{table}.csv"
            later_path = Path(split_root) / later / "features" / f"{table}.csv"
            if not earlier_path.exists() or not later_path.exists():
                continue

            earlier_max = pd.read_csv(
                earlier_path, parse_dates=["timestamp"], usecols=["timestamp"]
            )["timestamp"].max()
            later_min = pd.read_csv(
                later_path, parse_dates=["timestamp"], usecols=["timestamp"]
            )["timestamp"].min()

            if pd.notna(earlier_max) and pd.notna(later_min) and later_min <= earlier_max:
                problems.append(
                    f"{later} starts at {later_min} but {earlier} already reaches "
                    f"{earlier_max}: splits overlap"
                )

    return problems


def run_leakage_check(
    split_root: str | Path, tables: dict[str, pd.DataFrame] | None = None
) -> list[str]:
    """Run every leakage check and return a list of violations."""
    violations = [
        *check_feature_files(split_root),
        *check_label_files(split_root),
        *check_temporal_ordering(split_root),
        *check_overlap(split_root),
        *check_split_chronology(split_root),
    ]

    if tables:
        for name in tables:
            if name in LABEL_SIDE_TABLES:
                continue
            # A ground-truth table is fine in data/generated; it just must never
            # be treated as a feature table.
            if "label" in name:
                violations.append(
                    f"{name}: label table present in the feature-side table set"
                )

    return violations


def render(violations: list[str]) -> str:
    if not violations:
        return (
            "\nLEAKAGE CHECK: PASSED\n"
            "  - no ground-truth or whole-window columns on the feature side\n"
            "  - labels isolated under labels/\n"
            "  - splits contain only their own periods\n"
            "  - no transaction id in two splits\n"
            "  - splits are strictly chronological\n"
        )

    lines = ["\nLEAKAGE CHECK: FAILED", f"  {len(violations)} violation(s)"]
    lines.extend(f"  - {violation}" for violation in violations)
    return "\n".join(lines)