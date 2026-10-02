"""Calculated financial profiles.

These fields are derived from the underlying ledger rather than invented, which
is what the competition guideline asks for and what downstream features need.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PROFILE_COLUMNS = [
    "user_id",
    "monthly_income_avg",
    "monthly_expense_avg",
    "average_monthly_savings",
    "savings_rate",
    "income_stability",
    "cash_dependency",
    "emergency_fund_months",
]


def build_financial_profiles(
    transactions: pd.DataFrame, wallets: pd.DataFrame
) -> pd.DataFrame:
    """Compute one profile row per user from their transaction history."""
    frame = transactions.copy()
    frame["period"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame = frame[frame["category"] != "cash"]

    income = (
        frame[frame["direction"] == "inflow"]
        .groupby(["user_id", "period"])["amount"].sum().rename("income")
    )
    spend = (
        frame[frame["direction"] == "outflow"]
        .groupby(["user_id", "period"])["amount"].sum().rename("spend")
    )

    monthly = pd.concat([income, spend], axis=1).fillna(0.0).reset_index()
    monthly["savings"] = monthly["income"] - monthly["spend"]

    profiles = monthly.groupby("user_id").agg(
        monthly_income_avg=("income", "mean"),
        monthly_expense_avg=("spend", "mean"),
        average_monthly_savings=("savings", "mean"),
        active_months=("period", "nunique"),
    )

    profiles["savings_rate"] = np.where(
        profiles["monthly_income_avg"] > 0,
        profiles["average_monthly_savings"] / profiles["monthly_income_avg"],
        0.0,
    )

    income_cv = monthly.groupby("user_id")["income"].apply(
        lambda s: float(s.std(ddof=0) / s.mean()) if s.mean() > 0 else 0.0
    )
    # Map CV to a 0-1 stability score: 1.0 is perfectly stable income.
    profiles["income_stability"] = 1.0 / (1.0 + income_cv)

    cash_wallets = set(
        transactions.loc[transactions["transaction_type"] == "cash_in", "wallet_id"]
    )
    consumption = frame[frame["direction"] == "outflow"]
    cash_by_user = (
        consumption[consumption["wallet_id"].isin(cash_wallets)]
        .groupby("user_id")["amount"].sum()
    )
    total_by_user = consumption.groupby("user_id")["amount"].sum()
    profiles["cash_dependency"] = np.where(
        total_by_user > 0,
        cash_by_user.reindex(profiles.index).fillna(0.0) / total_by_user,
        0.0,
    )

    # Emergency fund = liquid balance (upay + bank + cash) held at the end of
    # the window, expressed in months of average spending.
    liquid_wallets = set(
        wallets.loc[wallets["wallet_type"].isin(["upay", "bank", "cash"]), "wallet_id"]
    )
    closing = (
        transactions.sort_values(["timestamp", "transaction_id"])
        .groupby("wallet_id")["balance_after"].last()
        .reindex(sorted(liquid_wallets))
        .fillna(0.0)
        .clip(lower=0.0)
    )
    liquid_by_user = (
        wallets.assign(closing=wallets["wallet_id"].map(closing).fillna(0.0))
        .groupby("user_id")["closing"].sum()
    )
    profiles["emergency_fund_months"] = np.where(
        profiles["monthly_expense_avg"] > 0,
        liquid_by_user.reindex(profiles.index).fillna(0.0)
        / profiles["monthly_expense_avg"],
        0.0,
    )

    for column in (
        "monthly_income_avg",
        "monthly_expense_avg",
        "average_monthly_savings",
        "emergency_fund_months",
    ):
        profiles[column] = profiles[column].round(2)

    profiles["savings_rate"] = profiles["savings_rate"].round(4)
    profiles["income_stability"] = profiles["income_stability"].round(4)
    profiles["cash_dependency"] = profiles["cash_dependency"].round(4)

    return profiles.reset_index()[PROFILE_COLUMNS]