"""Export a curated static JSON snapshot of the synthetic dataset for the frontend.

The frontend ships as a static app with no backend. To keep every number on screen
traceable to a real row of the generated dataset, we export a small, deterministic
slice of `data/generated` into a single columnar JSON document that Vite serves as
a static asset. Nothing here computes financial logic: engines run client side.

Usage:
    python scripts/export_frontend_snapshot.py
    python scripts/export_frontend_snapshot.py --users-per-persona 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "generated"
OUT_PATH = ROOT / "frontend" / "public" / "data" / "snapshot.json"

# Columns that are ground truth for the generator. They are exported so the
# evaluation screen can measure the engines against them. The engines never read
# these fields, mirroring the leakage blocklist in ml/dataset/splits.py.
LABEL_COLUMNS = {
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
}

TABLE_COLUMNS = {
    "users": [
        "user_id",
        "age_group",
        "occupation",
        "location_type",
        "account_age_days",
        "persona",
        "monthly_income_base",
        "target_savings_rate",
    ],
    "wallets": ["wallet_id", "user_id", "wallet_type", "opening_balance"],
    "income_events": [
        "income_id",
        "user_id",
        "timestamp",
        "income_type",
        "amount",
        "regularity",
        "source",
    ],
    "recurring_expenses": [
        "recurring_id",
        "user_id",
        "expense_name",
        "category",
        "amount",
        "frequency",
        "next_due_date",
        "mandatory",
        "due_day",
    ],
    "transactions": [
        "transaction_id",
        "user_id",
        "wallet_id",
        "timestamp",
        "transaction_type",
        "direction",
        "amount",
        "category",
        "subcategory",
        "merchant_type",
        "channel",
        "cash_out",
        "balance_after",
        "fee_amount",
        "is_anomaly",
        "pattern_type",
    ],
    "financial_goals": [
        "goal_id",
        "user_id",
        "goal_name",
        "target_amount",
        "current_amount",
        "target_date",
        "priority",
        "created_date",
        "horizon_months",
    ],
    "goal_contributions": ["contribution_id", "goal_id", "user_id", "timestamp", "amount"],
    "financial_profiles": [
        "user_id",
        "monthly_income_avg",
        "monthly_expense_avg",
        "average_monthly_savings",
        "savings_rate",
        "income_stability",
        "cash_dependency",
        "emergency_fund_months",
    ],
    "behavior_labels": [
        "user_id",
        "period",
        "end_month_shortage_label",
        "high_cash_dependency_label",
        "irregular_income_label",
        "overspending_label",
        "goal_progress_label",
        "financial_pressure_label",
        "anomaly_count",
    ],
    "injected_patterns": [
        "user_id",
        "period",
        "pattern_type",
        "amount",
        "category",
        "timestamp",
        "transaction_id",
    ],
}


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return round(value, 2)
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _columnar(frame: pd.DataFrame, columns: list[str]) -> dict:
    """Encode a frame as {"columns": [...], "rows": [[...]]} to keep the payload small."""
    subset = frame[columns].copy()
    rows = [[_clean(cell) for cell in row] for row in subset.itertuples(index=False, name=None)]
    return {"columns": columns, "rows": rows}


def _pick_users(users: pd.DataFrame, per_persona: int) -> list[str]:
    """Pick a deterministic, demo-friendly cohort: the busiest users of each persona."""
    chosen: list[str] = []
    ordered = users.sort_values(["persona", "user_id"])
    for _, group in ordered.groupby("persona", sort=True):
        chosen.extend(group["user_id"].head(per_persona).tolist())
    return sorted(chosen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users-per-persona", type=int, default=3)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)

    if not args.data_dir.exists():
        print(f"error: {args.data_dir} not found. Run scripts/generate_synthetic_data.py first.")
        return 1

    users = pd.read_csv(args.data_dir / "users.csv")
    cohort = _pick_users(users, args.users_per_persona)
    cohort_set = set(cohort)
    print(f"cohort: {len(cohort)} users across {users['persona'].nunique()} personas")

    payload: dict = {
        "meta": {
            "source": "data/generated (persona-driven synthetic dataset, seed 42)",
            "exported_by": "scripts/export_frontend_snapshot.py",
            "currency": "BDT",
            "note": (
                "Ground-truth columns (persona, is_anomaly, pattern_type, behaviour labels) are "
                "included for evaluation only. The financial engines in src/engines never read them, "
                "mirroring the leakage blocklist in ml/dataset/splits.py."
            ),
        },
        "tables": {},
        "cohort": cohort,
    }

    for name, columns in TABLE_COLUMNS.items():
        frame = pd.read_csv(args.data_dir / f"{name}.csv")
        if "user_id" in frame.columns:
            frame = frame[frame["user_id"].isin(cohort_set)]
        frame = frame.sort_values(list(frame.columns[:2])).reset_index(drop=True)
        payload["tables"][name] = _columnar(frame, columns)
        print(f"  {name:<22} {len(frame):>7} rows")

    timestamps = pd.read_csv(args.data_dir / "transactions.csv", usecols=["timestamp"])
    payload["meta"]["window_start"] = timestamps["timestamp"].min()[:10]
    payload["meta"]["window_end"] = timestamps["timestamp"].max()[:10]
    payload["meta"]["label_columns"] = sorted(LABEL_COLUMNS)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    size_kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out.relative_to(ROOT)} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())