"""Ground-truth behaviour labels (Step 9).

Labels are produced by fixed rules over information available up to and
including each period. They never read the persona assignment, so they can be
used as honest supervision and evaluated against the injected persona.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import LABEL_THRESHOLDS, TRANSFER_TYPES

LABEL_COLUMNS = [
    "user_id",
    "period",
    "end_month_shortage_label",
    "high_cash_dependency_label",
    "irregular_income_label",
    "overspending_label",
    "goal_progress_label",
    "financial_pressure_label",
    "anomaly_count",
]


def _income_stability(monthly_income: pd.Series) -> float:
    """Coefficient of variation of monthly income (0 means perfectly stable)."""
    if len(monthly_income) < LABEL_THRESHOLDS["min_months_active"]:
        return 0.0
    mean = monthly_income.mean()
    if mean <= 0:
        return 0.0
    return float(monthly_income.std(ddof=0) / mean)


def build_behavior_labels(
    transactions: pd.DataFrame,
    contributions: pd.DataFrame,
    patterns: pd.DataFrame,
    months: list[pd.Timestamp],
) -> pd.DataFrame:
    """Derive per-user, per-month behavioural ground truth from observed data."""
    frame = transactions.copy()
    frame["period"] = frame["timestamp"].dt.strftime("%Y-%m")
    # Cash legs and user-to-user transfers are movements, not income or
    # consumption. Excluding both directions prevents double counting.
    frame = frame[~frame["transaction_type"].isin(TRANSFER_TYPES)]
    frame["is_transfer"] = frame["category"] == "cash"

    # Consumption excludes internal cash transfers in both directions.
    spend = frame[(frame["direction"] == "outflow") & (~frame["is_transfer"])].copy()
    income = frame[frame["direction"] == "inflow"]

    monthly_spend = spend.groupby(["user_id", "period"])["amount"].sum().rename("spend")
    monthly_income = income.groupby(["user_id", "period"])["amount"].sum().rename("income")

    late = spend[spend["timestamp"].dt.day >= 23]
    monthly_late = late.groupby(["user_id", "period"])["amount"].sum().rename("late_spend")

    cash_wallets = set(
        transactions.loc[transactions["transaction_type"] == "cash_in", "wallet_id"]
    )
    cash_spend = spend[spend["wallet_id"].isin(cash_wallets)]
    monthly_cash = cash_spend.groupby(["user_id", "period"])["amount"].sum().rename("cash_spend")

    base = pd.concat(
        [monthly_spend, monthly_income, monthly_late, monthly_cash], axis=1
    ).fillna(0.0)

    contribution_by_period = (
        contributions.assign(period=contributions["timestamp"].dt.strftime("%Y-%m"))
        .groupby(["user_id", "period"])["amount"]
        .sum()
        .rename("contribution")
        if len(contributions)
        else pd.Series(dtype=float, name="contribution")
    )
    base["contribution"] = contribution_by_period.reindex(base.index).fillna(0.0)

    anomaly_by_period = (
        patterns.groupby(["user_id", "period"]).size().rename("anomaly_count")
        if len(patterns)
        else pd.Series(dtype=float, name="anomaly_count")
    )
    base["anomaly_count"] = anomaly_by_period.reindex(base.index).fillna(0)

    income_cv = (
        monthly_income.groupby("user_id").apply(_income_stability).rename("income_cv")
    )
    base = base.reset_index()
    base["income_cv"] = base["user_id"].map(income_cv).fillna(0.0)

    active = base[base["spend"] > 0].copy()

    active["late_share"] = np.where(
        active["spend"] > 0, active["late_spend"] / active["spend"], 0.0
    )
    active["cash_share"] = np.where(
        active["spend"] > 0, active["cash_spend"] / active["spend"], 0.0
    )
    active["savings_rate"] = np.where(
        active["income"] > 0,
        (active["income"] - active["spend"]) / active["income"],
        0.0,
    )
    active["expense_income_ratio"] = np.where(
        active["income"] > 0, active["spend"] / active["income"], np.inf
    )

    thresholds = LABEL_THRESHOLDS
    active["end_month_shortage_label"] = (
        active["late_share"] > thresholds["late_month_share"]
    ).astype(int)
    active["high_cash_dependency_label"] = (
        active["cash_share"] > thresholds["cash_dependency_share"]
    ).astype(int)
    active["irregular_income_label"] = (
        active["income_cv"] > thresholds["income_cv"]
    ).astype(int)
    active["overspending_label"] = (
        active["expense_income_ratio"] > thresholds["expense_income_ratio"]
    ).astype(int)
    active["goal_progress_label"] = (
        active["contribution"] >= thresholds["goal_contribution_min"]
    ).astype(int)
    active["financial_pressure_label"] = (
        (active["expense_income_ratio"] > thresholds["expense_income_ratio"])
        & (active["savings_rate"] < thresholds["savings_rate"])
    ).astype(int)
    active["anomaly_count"] = active["anomaly_count"].astype(int)

    return active[LABEL_COLUMNS].sort_values(["user_id", "period"]).reset_index(drop=True)