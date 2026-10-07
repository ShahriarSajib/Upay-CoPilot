"""Temporal train/validation/test split (Step 14).

Splitting by time, never at random, so a model can never learn from the future
when predicting the past.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Period-level split, aligned to the 9 simulated months (2026-01 .. 2026-09).
SPLIT_PERIODS = {
    "train": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
    "validation": ["2026-06", "2026-07"],
    "test": ["2026-08", "2026-09"],
}

# Columns that must never reach a model as a feature, because they are the
# ground truth of the behaviour we are trying to predict, or a generator knob
# that determines the answer by construction.
GROUND_TRUTH_COLUMNS = {
    "persona",
    "monthly_income_base",
    "expense_ratio",
    "income_cv",
    "cash_out_rate",
    "digital_ratio",
    "target_savings_rate",
    "goal_count",
    "anomaly_rate",
    "is_anomaly",
    "pattern_type",
    "end_month_shortage_label",
    "high_cash_dependency_label",
    "irregular_income_label",
    "overspending_label",
    "goal_progress_label",
    "financial_pressure_label",
    "anomaly_count",
}

# Columns that are correct in data/generated/ but cannot be used as features
# for earlier periods, because they are aggregated over the whole window and
# therefore encode the future.
TIME_AGGREGATE_COLUMNS = {
    "current_amount",
    "progress_ratio",
    "is_achieved",
    "monthly_income_avg",
    "monthly_expense_avg",
    "average_monthly_savings",
    "savings_rate",
    "income_stability",
    "cash_dependency",
    "emergency_fund_months",
}

FORBIDDEN_FEATURE_COLUMNS = GROUND_TRUTH_COLUMNS | TIME_AGGREGATE_COLUMNS

# Tables that carry the answer, so they belong on the label side only.
LABEL_SIDE_TABLES = {"behavior_labels", "injected_patterns"}

# Tables that are valid research artifacts but are whole-window aggregates, so
# they are excluded from the feature side of every split.
RESEARCH_SIDE_TABLES = LABEL_SIDE_TABLES | {"financial_profiles"}


def _period_of(frame: pd.DataFrame) -> pd.Series:
    return frame["timestamp"].dt.strftime("%Y-%m")


def split_frames(
    tables: dict[str, pd.DataFrame],
) -> dict[str, dict[str, pd.DataFrame]]:
    """Partition every time-indexed table into train/validation/test."""
    splits: dict[str, dict[str, pd.DataFrame]] = {name: {} for name in SPLIT_PERIODS}

    for name, frame in tables.items():
        if "timestamp" not in frame.columns or frame.empty:
            for split in SPLIT_PERIODS:
                splits[split][name] = frame.copy()
            continue

        periods = _period_of(frame)
        for split, allowed in SPLIT_PERIODS.items():
            splits[split][name] = frame[periods.isin(allowed)].copy().reset_index(drop=True)

    return splits


def write_splits(
    splits: dict[str, dict[str, pd.DataFrame]],
    directories: dict[str, str],
    generated_dir: str = "data/generated",
) -> None:
    """Write split tables, keeping research-only tables out of the feature side."""
    generated = Path(generated_dir)

    for split, tables in splits.items():
        target = Path(directories[split])
        feature_dir = target / "features"
        label_dir = target / "labels"
        feature_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)

        # Clear stale files so a split directory only ever describes its own run.
        for directory in (feature_dir, label_dir):
            for stale in directory.glob("*.csv"):
                stale.unlink()

        for name, frame in tables.items():
            if name in RESEARCH_SIDE_TABLES:
                frame.to_csv(label_dir / f"{name}.csv", index=False)
                continue

            frame = drop_leaky_columns(frame)
            frame.to_csv(feature_dir / f"{name}.csv", index=False)

        # User and wallet dimension tables are shared, not period-scoped.
        for shared in ("users", "wallets"):
            if shared in tables:
                continue
            source = generated / f"{shared}.csv"
            if source.exists():
                frame = drop_leaky_columns(pd.read_csv(source))
                frame.to_csv(feature_dir / f"{shared}.csv", index=False)


def drop_leaky_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove ground-truth and whole-window aggregate columns."""
    leaky = FORBIDDEN_FEATURE_COLUMNS & set(frame.columns)
    if not leaky:
        return frame
    return frame.drop(columns=sorted(leaky))


def split_summary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Row counts per table per split, for the dataset split document."""
    rows = []
    for name, frame in tables.items():
        row = {"table": name, "total": len(frame)}
        if "timestamp" in frame.columns and len(frame):
            periods = _period_of(frame)
            for split, allowed in SPLIT_PERIODS.items():
                row[split] = int(periods.isin(allowed).sum())
        else:
            for split in SPLIT_PERIODS:
                row[split] = len(frame)
        rows.append(row)
    return pd.DataFrame(rows)