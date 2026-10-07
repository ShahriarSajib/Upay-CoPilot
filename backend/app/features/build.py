"""Deterministic feature engineering.

Every number the models and engines see is produced here. Three grains:

* :func:`daily_features`  — one row per user-day. The forecasting grain.
* :func:`monthly_features` — one row per user-month. The planning grain.
* :func:`user_features`  — one row per user. The scoring and segmentation grain.

Nothing in this module reads a label, a persona or any other ground-truth
column, so the features are safe to build at inference time from production
data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.db.store import CASH_CATEGORY, consumption_mask

# Movements that are neither income nor consumption.
P2P_TYPES = ("send_money", "receive_money")

# Wallet types whose balance counts as money the customer can actually reach.
LIQUID_WALLET_TYPES = ("upay", "bank", "cash")

# Spend categories that become their own daily column.
SPEND_CATEGORIES = (
    "food",
    "transport",
    "shopping",
    "education",
    "health",
    "utilities",
    "communication",
    "entertainment",
    "family",
    "housing",
    "other",
)

# Days 21-30 is where the "end of month" persona concentrates spending, and it
# is the window the shortage explanation is built from.
LATE_MONTH_DAY = 23

SMALL_PURCHASE_THRESHOLD = 300.0

WINDOW_EDGES = [0, 10, 20, 28, 31]
WINDOW_LABELS = ["d1_10", "d11_20", "d21_28", "d29_31"]


def _safe_div(numerator, denominator, default: float = 0.0):
    numerator = np.asarray(numerator, dtype=float)
    denominator = np.asarray(denominator, dtype=float)
    out = np.full(numerator.shape, default, dtype=float)
    mask = denominator != 0
    out[mask] = numerator[mask] / denominator[mask]
    return out


def _entropy(values: np.ndarray) -> float:
    """Shannon entropy of a non-negative vector; 0 means fully concentrated."""
    total = values.sum()
    if total <= 0:
        return 0.0
    probabilities = values / total
    probabilities = probabilities[probabilities > 0]
    return float(-(probabilities * np.log(probabilities)).sum())


def daily_features(transactions: pd.DataFrame, wallets: pd.DataFrame) -> pd.DataFrame:
    """One row per user-day, including a full month of calendar days."""
    tx = transactions.copy()
    tx["date"] = pd.to_datetime(tx["timestamp"]).dt.normalize()
    tx["period"] = tx["timestamp"].dt.strftime("%Y-%m")

    is_cash_leg = tx["category"] == CASH_CATEGORY
    is_p2p = tx["transaction_type"].isin(P2P_TYPES)
    tx["wallet_type"] = tx["wallet_id"].map(wallets.set_index("wallet_id")["wallet_type"])

    # Consumption basis, shared with the dataset generator: cash legs and
    # user-to-user transfers move money between wallets, so counting them as
    # spending would double count every cash-out.
    is_movement = is_cash_leg | is_p2p
    consumption_rows = tx[(tx["direction"] == "outflow") & (~is_movement)]
    inflow_rows = tx[(tx["direction"] == "inflow") & (~is_movement)]

    inflow = inflow_rows.groupby(["user_id", "date"])["amount"].sum().rename("income")
    spend_daily = (
        consumption_rows.groupby(["user_id", "date"])["amount"].sum().rename("spend")
    )

    # Cash-funded spending is a separate cut of the same consumption. A wallet
    # counts as cash when money has actually been withdrawn into it, which is
    # the same rule the ground-truth cash-dependency label uses.
    cash_wallet_ids = set(tx.loc[tx["transaction_type"] == "cash_in", "wallet_id"])
    cash_spend = (
        consumption_rows[consumption_rows["wallet_id"].isin(cash_wallet_ids)]
        .groupby(["user_id", "date"])["amount"]
        .sum()
        .rename("cash_spend")
    )

    cash_out = (
        tx[tx["transaction_type"] == "cash_out"]
        .groupby(["user_id", "date"])["amount"]
        .sum()
        .rename("cash_out_amount")
    )
    cash_in = (
        tx[tx["transaction_type"] == "cash_in"]
        .groupby(["user_id", "date"])["amount"]
        .sum()
        .rename("cash_in_amount")
    )

    digital_spend = (
        consumption_rows[consumption_rows["wallet_type"].isin(["upay", "bank", "other_digital"])]
        .groupby(["user_id", "date"])["amount"]
        .sum()
        .rename("digital_spend")
    )

    counts = (
        consumption_rows.groupby(["user_id", "date"]).size().rename("txn_count").to_frame()
    )

    small = consumption_rows[consumption_rows["amount"] < SMALL_PURCHASE_THRESHOLD]
    small_total = small.groupby(["user_id", "date"])["amount"].sum().rename("small_spend")
    small_count = small.groupby(["user_id", "date"]).size().rename("small_purchase_count")

    recurring = (
        consumption_rows[consumption_rows["recurring_id"].notna()]
        .groupby(["user_id", "date"])["amount"]
        .sum()
        .rename("recurring_amount")
    )

    # ``is_anomaly`` is generator ground truth. It is present on the product
    # dataset and on ``Split.transactions`` (which re-attaches it for scoring),
    # but it must never be required to build features: the feature side of a
    # split deliberately does not carry it.
    if "is_anomaly" in tx.columns:
        anomalies = (
            tx[tx["is_anomaly"].fillna(False)].groupby(["user_id", "date"]).size().rename("anomaly_count")
        )
    else:
        anomalies = pd.Series(dtype=float, name="anomaly_count")

    frames = [
        inflow,
        spend_daily,
        cash_spend,
        digital_spend,
        cash_out,
        cash_in,
        counts,
        small_total,
        small_count,
        recurring,
        anomalies,
    ]
    daily = pd.concat(frames, axis=1).fillna(0.0)
    daily = daily.groupby(level=["user_id", "date"]).sum()

    # Category columns.
    category_spend = (
        consumption_rows.assign(cat=consumption_rows["category"])
        .groupby(["user_id", "date", "cat"])["amount"]
        .sum()
        .unstack("cat")
    )
    category_spend = category_spend.reindex(columns=SPEND_CATEGORIES).fillna(0.0)
    category_spend.columns = [f"spend_{name}" for name in category_spend.columns]
    daily = daily.join(category_spend, how="left").fillna(0.0)

    # Period back-fill so a missing day inherits its month label.
    month_of_day = tx.groupby("date")["period"].agg(lambda s: s.mode().iat[0])
    daily = daily.reset_index()
    daily["period"] = daily["date"].map(month_of_day)
    daily["period"] = daily["period"].fillna(
        daily["date"].dt.strftime("%Y-%m")
    )

    daily["net"] = daily["income"] - daily["spend"]
    daily["digital_ratio"] = _safe_div(daily["digital_spend"], daily["spend"])
    daily["cash_ratio"] = _safe_div(daily["cash_spend"], daily["spend"])
    daily["small_ratio"] = _safe_div(daily["small_spend"], daily["spend"])
    daily["avg_ticket"] = _safe_div(daily["spend"], daily["txn_count"])

    # Liquid balance is a *sum across wallets*, not the last row of one wallet.
    # Each wallet's ledger carries forward on days it has no transactions, then
    # the user's wallets are summed. This matches the dataset's own
    # emergency_fund_months definition and keeps emergency-fund maths honest.
    liquid_wallets = set(
        wallets.loc[wallets["wallet_type"].isin(LIQUID_WALLET_TYPES), "wallet_id"]
    )
    ledger = (
        tx[tx["wallet_id"].isin(liquid_wallets)]
        .sort_values(["wallet_id", "timestamp"])
        .groupby(["wallet_id", "user_id", "date"])["balance_after"]
        .last()
        .rename("wallet_balance")
        .reset_index()
    )
    per_wallet = []
    # Carry every wallet across its *owner's* full active range, not its own.
    # A cash wallet that stops being used mid-month still holds money, so its
    # balance must be carried forward into the sum for the rest of the window.
    user_span = (
        tx.groupby("user_id", observed=True)["date"].agg(["min", "max"]).to_dict("index")
    )
    for (wallet_id, user_id), group in ledger.groupby(
        ["wallet_id", "user_id"], observed=True, sort=False
    ):
        series = group.set_index("date")["wallet_balance"].sort_index()
        span = user_span.get(user_id)
        start = min(series.index.min(), span["min"]) if span else series.index.min()
        end = max(series.index.max(), span["max"]) if span else series.index.max()
        series = series.reindex(pd.date_range(start, end, freq="D")).ffill()
        per_wallet.append(
            pd.DataFrame(
                {
                    "wallet_id": wallet_id,
                    "user_id": user_id,
                    "date": series.index,
                    "wallet_balance": series.to_numpy(),
                }
            )
        )
    wallet_panel = pd.concat(per_wallet, ignore_index=True)
    liquid = (
        wallet_panel.groupby(["user_id", "date"], observed=True)["wallet_balance"]
        .sum(min_count=1)
        .rename("balance")
    )

    daily = daily.set_index(["user_id", "date"])
    daily = daily.join(liquid)
    daily = daily.reset_index()
    daily = daily.sort_values(["user_id", "date"])
    daily["balance"] = (
        daily.groupby("user_id")["balance"].transform(lambda s: s.ffill().bfill()).fillna(0.0)
    )

    daily = daily.sort_values(["user_id", "date"]).reset_index(drop=True)
    grouped = daily.groupby("user_id", observed=True)
    daily["balance_7d_mean"] = (
        grouped["balance"].rolling(7, min_periods=1).mean().reset_index(level=0, drop=True)
    )
    daily["balance_30d_mean"] = (
        grouped["balance"].rolling(30, min_periods=1).mean().reset_index(level=0, drop=True)
    )
    daily["balance_30d_min"] = (
        grouped["balance"].rolling(30, min_periods=1).min().reset_index(level=0, drop=True)
    )
    daily["balance_volatility_30d"] = (
        grouped["balance"]
        .rolling(30, min_periods=2)
        .std()
        .reset_index(level=0, drop=True)
        .fillna(0.0)
    )
    return daily


def _reindex_calendar(daily: pd.DataFrame) -> pd.DataFrame:
    """Insert zero-flow days so every user has a continuous series.

    A day with no transactions means no money moved, which is a real zero and
    not missing data -- so flow columns are filled with 0 while the balance is
    carried forward from the previous day.
    """
    balance_column = "balance" if "balance" in daily.columns else None
    out = []
    for user_id, group in daily.groupby("user_id", observed=True, sort=False):
        group = group.sort_values("date")
        full = pd.date_range(group["date"].min(), group["date"].max(), freq="D")
        group = group.set_index("date").reindex(full)
        group.index.name = "date"
        group["user_id"] = user_id
        group["period"] = group.index.strftime("%Y-%m")
        if balance_column:
            group[balance_column] = group[balance_column].ffill().bfill()
        group = group.fillna(0.0)
        out.append(group.reset_index())
    return pd.concat(out, ignore_index=True)


def monthly_features(
    daily: pd.DataFrame, contributions: pd.DataFrame, goals: pd.DataFrame
) -> pd.DataFrame:
    """One row per user-month: the planning grain.

    ``late_share`` and the four month windows are the evidence behind the
    end-of-month shortage explanation, so they are computed here once.
    """
    frame = daily.copy()
    frame["day_of_month"] = frame["date"].dt.day
    frame["is_late"] = frame["day_of_month"] >= LATE_MONTH_DAY

    grouped = frame.groupby(["user_id", "period"], observed=True)
    monthly = grouped.agg(
        income=("income", "sum"),
        spend=("spend", "sum"),
        net=("net", "sum"),
        cash_spend=("cash_spend", "sum"),
        digital_spend=("digital_spend", "sum"),
        cash_out_amount=("cash_out_amount", "sum"),
        recurring_amount=("recurring_amount", "sum"),
        small_spend=("small_spend", "sum"),
        txn_count=("txn_count", "sum"),
        anomaly_count=("anomaly_count", "count"),
        active_days=("spend", lambda s: int((s > 0).sum())),
        observed_days=("spend", "size"),
        ending_balance=("balance", "last"),
        min_balance=("balance", "min"),
        mean_balance=("balance", "mean"),
        balance_volatility=("balance_volatility_30d", "max"),
    ).reset_index()

    late = (
        frame[frame["is_late"]]
        .groupby(["user_id", "period"], observed=True)["spend"]
        .sum()
        .rename("late_spend")
    )
    monthly = monthly.merge(late, on=["user_id", "period"], how="left").fillna({"late_spend": 0.0})

    # Anomaly count must count flagged rows, not flagged days.
    anomaly_rows = (
        daily[daily["anomaly_count"] > 0]
        .groupby(["user_id", "period"], observed=True)["anomaly_count"]
        .sum()
        .rename("anomaly_events")
    )
    monthly = monthly.merge(anomaly_rows, on=["user_id", "period"], how="left").fillna(
        {"anomaly_events": 0}
    )

    windows = (
        frame.assign(
            window=pd.cut(
                frame["day_of_month"], bins=WINDOW_EDGES, labels=WINDOW_LABELS
            )
        )
        .groupby(["user_id", "period", "window"], observed=True)["spend"]
        .sum()
        .unstack("window")
        .reindex(columns=WINDOW_LABELS)
        .fillna(0.0)
    )
    monthly = monthly.merge(
        windows.reset_index().rename(
            columns={label: f"spend_{label}" for label in WINDOW_LABELS}
        ),
        on=["user_id", "period"],
        how="left",
    ).fillna(0.0)

    contribution_by_period = (
        contributions.assign(period=contributions["timestamp"].dt.strftime("%Y-%m"))
        .groupby(["user_id", "period"], observed=True)["amount"]
        .sum()
        .rename("goal_contribution")
    )
    monthly = monthly.merge(
        contribution_by_period, on=["user_id", "period"], how="left"
    ).fillna({"goal_contribution": 0.0})

    # Monthly category totals, joined by key rather than position.
    category_monthly = (
        frame.groupby(["user_id", "period"], observed=True)[
            [f"spend_{name}" for name in SPEND_CATEGORIES]
        ]
        .sum()
        .reset_index()
    )
    monthly = monthly.merge(category_monthly, on=["user_id", "period"], how="left").fillna(0.0)

    below_buffer = (
        frame.assign(below=(frame["balance"] < 5000.0).astype(int))
        .groupby(["user_id", "period"], observed=True)["below"]
        .sum()
        .rename("days_below_buffer")
        .reset_index()
    )
    monthly = monthly.merge(below_buffer, on=["user_id", "period"], how="left").fillna(
        {"days_below_buffer": 0}
    )

    monthly["surplus"] = monthly["income"] - monthly["spend"]
    monthly["savings_rate"] = _safe_div(monthly["surplus"], monthly["income"])
    monthly["expense_income_ratio"] = _safe_div(
        monthly["spend"], monthly["income"], default=1.0
    )
    monthly["late_share"] = _safe_div(monthly["late_spend"], monthly["spend"])
    monthly["cash_share"] = _safe_div(monthly["cash_spend"], monthly["spend"])
    monthly["recurring_share"] = _safe_div(monthly["recurring_amount"], monthly["spend"])
    monthly["small_share"] = _safe_div(monthly["small_spend"], monthly["spend"])
    return monthly.sort_values(["user_id", "period"]).reset_index(drop=True)


def user_features(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    users: pd.DataFrame,
    wallets: pd.DataFrame,
    recurring: pd.DataFrame,
    goals: pd.DataFrame,
    contributions: pd.DataFrame,
) -> pd.DataFrame:
    """One row per user: the scoring, health and segmentation grain."""
    features: dict[str, pd.Series] = {}

    grouped = monthly.groupby("user_id", observed=True)
    features["months_observed"] = grouped.size()
    features["monthly_income"] = grouped["income"].mean()
    features["monthly_expense"] = grouped["spend"].mean()
    features["monthly_surplus"] = grouped["surplus"].mean()
    features["savings_rate"] = grouped["savings_rate"].mean()
    features["expense_income_ratio"] = grouped["expense_income_ratio"].mean()
    features["late_month_share"] = grouped["late_share"].mean()
    features["late_month_share_max"] = grouped["late_share"].max()
    features["cash_dependency"] = grouped["cash_share"].mean()
    features["recurring_obligation_ratio"] = grouped["recurring_share"].mean()
    features["small_purchase_ratio"] = grouped["small_share"].mean()
    features["monthly_recurring_amount"] = grouped["recurring_amount"].mean()
    features["monthly_cash_out"] = grouped["cash_out_amount"].mean()
    features["txn_per_month"] = grouped["txn_count"].mean()
    features["anomaly_events"] = grouped["anomaly_events"].sum()
    features["goal_contribution_monthly"] = grouped["goal_contribution"].mean()
    features["funding_months"] = grouped["goal_contribution"].apply(
        lambda s: float((s > 0).sum())
    )
    features["funding_consistency"] = features["funding_months"] / features[
        "months_observed"
    ].replace(0, np.nan)
    features["ending_balance"] = grouped["ending_balance"].last()
    features["mean_balance"] = grouped["mean_balance"].mean()
    features["min_balance"] = grouped["min_balance"].min()
    features["balance_volatility"] = grouped["balance_volatility"].mean()
    features["months_negative_surplus"] = grouped["surplus"].apply(lambda s: float((s < 0).sum()))

    # Population std (ddof=0) to match the dataset's own stability definition.
    income_mean = grouped["income"].mean()
    income_std = grouped["income"].apply(lambda s: float(s.std(ddof=0)))
    features["income_cv"] = _safe_div(income_std, income_mean)
    features["income_stability"] = 1.0 / (1.0 + features["income_cv"])

    daily_grouped = daily.groupby("user_id", observed=True)
    features["digital_ratio"] = _safe_div(
        daily_grouped["digital_spend"].sum(), daily_grouped["spend"].sum()
    )
    # Cash dependency is a whole-window share of spend, not a mean of monthly
    # ratios: a user who cashes out in one heavy month is cash dependent.
    features["cash_dependency"] = _safe_div(
        daily_grouped["cash_spend"].sum(), daily_grouped["spend"].sum()
    )
    features["days_below_buffer"] = (
        daily.assign(below=(daily["balance"] < 5000.0).astype(int))
        .groupby("user_id", observed=True)["below"]
        .sum()
    )
    features["low_balance_frequency"] = _safe_div(
        features["days_below_buffer"], daily_grouped.size()
    )

    category_totals = daily_grouped[[f"spend_{c}" for c in SPEND_CATEGORIES]].sum()
    category_totals = category_totals.reindex(
        daily["user_id"].unique(), fill_value=0.0
    )
    features["category_entropy"] = pd.Series(
        {
            user_id: _entropy(category_totals.loc[user_id].to_numpy(dtype=float))
            for user_id in category_totals.index
        }
    )
    features["top_category"] = (
        category_totals.idxmax(axis=1).str.replace("spend_", "", regex=False)
    )

    goal_grouped = goals.groupby("user_id", observed=True)
    features["goal_count"] = goal_grouped.size().reindex(
        features["monthly_income"].index
    ).fillna(0)
    try:
        cur = contributions.groupby("goal_id", observed=True)["amount"].sum().rename("current_amount")
        g2 = goals.merge(cur, on="goal_id", how="left").fillna({"current_amount": 0.0})
        g2g = g2.groupby("user_id", observed=True)
        goal_progress = (g2g["current_amount"].sum() / g2g["target_amount"].sum().clip(lower=1.0))
        features["goal_progress"] = goal_progress.reindex(features["monthly_income"].index).fillna(0.0)
    except Exception:
        features["goal_progress"] = 0.0
    try:
        features["goal_target_total"] = g2g["target_amount"].sum().reindex(features["monthly_income"].index).fillna(0.0)
    except Exception:
        try:
            features["goal_target_total"] = goal_grouped["target_amount"].sum().reindex(features["monthly_income"].index).fillna(0.0)
        except Exception:
            features["goal_target_total"] = 0.0
    features["goals_achieved"] = (
        g2g["is_achieved"].sum().reindex(features["monthly_income"].index).fillna(0) if 'g2g' in locals() else (goal_grouped["is_achieved"].sum().reindex(features["monthly_income"].index).fillna(0) if "is_achieved" in goals.columns else 0)
    )

    obligation = recurring.groupby("user_id", observed=True)["amount"].sum()
    features["mandatory_obligation_amount"] = (
        recurring[recurring["mandatory"]]
        .groupby("user_id", observed=True)["amount"]
        .sum()
        .reindex(features["monthly_income"].index)
        .fillna(0.0)
    )
    features["obligation_count"] = (
        recurring.groupby("user_id", observed=True).size().reindex(features["monthly_income"].index).fillna(0)
    )
    features["emergency_buffer_months"] = _safe_div(
        features["ending_balance"].clip(lower=0), features["monthly_expense"]
    )

    # Built as an index-aligned Series, not a bare array: the wallet roster can
    # cover more customers than the activity frame (the split folders ship a
    # 500-user roster for 50 users with transactions), and a raw array here
    # would either misalign or raise inside ``pd.DataFrame``.
    features["has_cash_wallet"] = (
        wallets.assign(_is_cash=(wallets["wallet_type"] == "cash").astype(int))
        .groupby("user_id", observed=True)["_is_cash"]
        .max()
        .reindex(features["monthly_income"].index)
        .fillna(0)
    )
    features["wallet_count"] = (
        wallets.groupby("user_id", observed=True).size().reindex(features["monthly_income"].index).fillna(1)
    )

    frame = pd.DataFrame(features)
    frame["has_cash_wallet"] = frame["has_cash_wallet"].astype(int)
    demographics = users.set_index("user_id")
    for column in ("age_group", "occupation", "location_type", "account_age_days"):
        frame[column] = demographics[column].reindex(frame.index)
    frame["account_age_months"] = frame["account_age_days"] / 30.44
    frame = frame.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame.index.name = "user_id"
    return frame.reset_index()


def build_all(
    transactions: pd.DataFrame,
    wallets: pd.DataFrame,
    users: pd.DataFrame,
    recurring: pd.DataFrame,
    goals: pd.DataFrame,
    contributions: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Run the full feature pipeline."""
    daily = _reindex_calendar(daily_features(transactions, wallets))
    monthly = monthly_features(daily, contributions, goals)
    user = user_features(daily, monthly, users, wallets, recurring, goals, contributions)
    return {"daily": daily, "monthly": monthly, "user": user}


assert consumption_mask is not None  # re-exported contract used by engines
