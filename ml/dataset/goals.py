"""Financial goals and goal contributions (Step 7).

Contributions are drawn from each user's *observed* monthly surplus, so a goal
can never accumulate money the user did not actually have. The invariant
``current_amount == sum(goal_contributions)`` holds by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    GOAL_MONTHS_TO_TARGET,
    GOAL_PRIORITIES,
    GOAL_TARGET_FRACTION,
    GOAL_TYPES,
    PERSONA_GOAL_COUNT,
    PERSONA_GOAL_SHARE,
    TRANSFER_TYPES,
)

PRIORITY_WEIGHTS = {"high": 0.45, "medium": 0.40, "low": 0.15}


def monthly_surplus(transactions: pd.DataFrame) -> pd.DataFrame:
    """Observed income minus spending per user and month.

    Cash-outs are internal wallet transfers, so they are excluded from both
    sides to avoid double counting.
    """
    frame = transactions.copy()
    frame["period"] = frame["timestamp"].dt.strftime("%Y-%m")
    # Cash legs and user-to-user transfers move money between wallets; they are
    # neither income nor consumption, so counting them would double count.
    frame = frame[~frame["transaction_type"].isin(TRANSFER_TYPES)]
    frame = frame[frame["category"] != "cash"]

    income = (
        frame[frame["direction"] == "inflow"]
        .groupby(["user_id", "period"])["amount"]
        .sum()
        .rename("income")
    )
    spend = (
        frame[frame["direction"] == "outflow"]
        .groupby(["user_id", "period"])["amount"]
        .sum()
        .rename("spend")
    )

    merged = pd.concat([income, spend], axis=1).fillna(0.0).reset_index()
    merged["surplus"] = merged["income"] - merged["spend"]
    return merged


def generate_goals(
    rng: np.random.Generator,
    users: pd.DataFrame,
    surplus: pd.DataFrame,
    months: list[pd.Timestamp],
) -> pd.DataFrame:
    """Create goals sized to the user's income and remaining time horizon."""
    rows: list[dict] = []
    first_month = months[0]

    for user in users.itertuples():
        low_count, high_count = PERSONA_GOAL_COUNT[user.persona]
        n_goals = int(rng.integers(low_count, high_count + 1))
        if n_goals == 0:
            continue

        for _ in range(n_goals):
            goal_name = str(rng.choice(GOAL_TYPES))
            income = float(user.monthly_income_base)

            if goal_name == "emergency_fund":
                low, high = GOAL_TARGET_FRACTION[goal_name]
                target = round(float(rng.uniform(low, high)) * max(income, 5_000.0), 2)
            else:
                low, high = GOAL_TARGET_FRACTION[goal_name]
                target = round(float(rng.uniform(low, high)) * max(income, 4_000.0), 2)

            target = max(target, 1_000.0)

            low_m, high_m = GOAL_MONTHS_TO_TARGET[goal_name]
            horizon = int(rng.integers(low_m, high_m + 1))
            target_month_index = min(len(months) - 1, int(rng.integers(3, len(months))))

            # Goals that would already be overdue at the end of the window are
            # shifted so every goal is still reachable in the data.
            target_month_index = min(len(months) - 1, target_month_index)
            target_date = months[target_month_index] + pd.offsets.MonthEnd(0)

            rows.append({
                "goal_id": f"G{len(rows) + 1:05d}",
                "user_id": user.user_id,
                "goal_name": goal_name,
                "target_amount": target,
                "current_amount": 0.0,
                "target_date": target_date.date(),
                "priority": str(rng.choice(GOAL_PRIORITIES, p=list(PRIORITY_WEIGHTS.values()))),
                "created_date": first_month.date(),
                "horizon_months": horizon,
            })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def generate_goal_contributions(
    rng: np.random.Generator,
    goals: pd.DataFrame,
    users: pd.DataFrame,
    surplus: pd.DataFrame,
    months: list[pd.Timestamp],
) -> pd.DataFrame:
    """Fund goals from observed surplus, then enforce the sum invariant."""
    if goals.empty:
        return pd.DataFrame(columns=["contribution_id", "goal_id", "user_id", "timestamp", "amount"])

    persona_by_user = users.set_index("user_id")["persona"].to_dict()
    surplus_lookup = {
        (row.user_id, row.period): row.surplus for row in surplus.itertuples()
    }
    periods = [month.strftime("%Y-%m") for month in months]

    rows: list[dict] = []
    running: dict[str, float] = {goal.goal_id: 0.0 for goal in goals.itertuples()}

    for goal in goals.itertuples():
        persona = persona_by_user[goal.user_id]
        share_low, share_high = PERSONA_GOAL_SHARE[persona]
        goal_share = float(rng.uniform(share_low, share_high))

        for period in periods:
            if rng.random() > goal_share * 2.5:
                # Not every goal is funded in every month.
                continue

            available = max(surplus_lookup.get((goal.user_id, period), 0.0), 0.0)
            if available <= 0.0:
                continue

            remaining = goal.target_amount - running[goal.goal_id]
            if remaining <= 0.0:
                continue

            contribution = min(available * float(rng.uniform(0.20, 0.70)), remaining)
            if contribution < 50.0:
                continue

            contribution = round(contribution, 2)
            month_start = pd.Timestamp(f"{period}-01")
            timestamp = month_start + pd.Timedelta(
                days=int(rng.integers(0, month_start.days_in_month)),
                hours=int(rng.integers(9, 20)),
                minutes=int(rng.integers(0, 60)),
            )

            rows.append({
                "contribution_id": f"GC{len(rows) + 1:06d}",
                "goal_id": goal.goal_id,
                "user_id": goal.user_id,
                "timestamp": timestamp,
                "amount": contribution,
            })
            running[goal.goal_id] += contribution

    return pd.DataFrame(rows)


def apply_contributions(goals: pd.DataFrame, contributions: pd.DataFrame) -> pd.DataFrame:
    """Set ``current_amount`` from contributions, then recompute progress.

    Contributions are capped at the remaining target while they are generated,
    so ``current_amount == sum(contributions)`` holds exactly. No clipping is
    applied here: silently truncating would break that invariant.
    """
    frame = goals.copy()

    if contributions is not None and len(contributions):
        totals = contributions.groupby("goal_id")["amount"].sum()
        frame["current_amount"] = frame["goal_id"].map(totals).fillna(0.0)
    else:
        frame["current_amount"] = 0.0

    frame["current_amount"] = frame["current_amount"].round(2)
    frame["is_achieved"] = frame["current_amount"] >= frame["target_amount"]
    frame["progress_ratio"] = np.where(
        frame["target_amount"] > 0,
        frame["current_amount"] / frame["target_amount"],
        0.0,
    ).round(4)

    return frame


def goals_with_progress(goals: pd.DataFrame) -> pd.DataFrame:
    """Deprecated shim kept so older imports keep working."""
    frame = goals.copy()
    frame["progress_ratio"] = np.where(
        frame["target_amount"] > 0,
        frame["current_amount"] / frame["target_amount"],
        0.0,
    )
    return frame