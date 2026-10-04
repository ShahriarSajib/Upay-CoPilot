"""User, wallet and income generation."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .config import (
    AGE_GROUPS,
    AGE_INCOME_MULTIPLIER,
    DEV_PERSONAS_BALANCED,
    DEV_USER_NAMES,
    LOCATION_INCOME_MULTIPLIER,
    LOCATION_PROBABILITIES,
    LOCATION_TYPES,
    OCCUPATION_INCOME_BAND,
    OCCUPATION_INCOME_PROFILE,
    OCCUPATIONS,
    PERSONA_INCOME_FACTOR,
    PERSONA_PROBABILITIES,
    PERSONA_PROFILES,
    START_DATE,
)

DISCRETE_CATEGORIES = [
    "food", "transport", "shopping", "education", "health",
    "utilities", "communication", "entertainment", "family",
]


def month_starts(months: int) -> list[pd.Timestamp]:
    """First day of each month in the simulation window."""
    return list(pd.date_range(START_DATE, periods=months, freq="MS"))


def end_of_history_date(months: int) -> date:
    """Last calendar day covered by the generated history."""
    last_day = month_starts(months)[-1] + pd.offsets.MonthBegin(1) - pd.Timedelta(days=1)
    return last_day.date()


def history_span_days(months: int) -> int:
    """Days an account must be open to cover the whole history."""
    return (pd.Timestamp(end_of_history_date(months)) - pd.Timestamp(START_DATE)).days + 1


def min_account_age_days(months: int) -> int:
    """Accounts must predate the history they explain."""
    return history_span_days(months)


def weighted_choice(rng: np.random.Generator, options: list[str], weights: dict) -> str:
    """Deterministically pick one key from ``options`` using ``weights``."""
    values = np.array([weights.get(option, 0.0) for option in options], dtype=float)
    if values.sum() <= 0:
        return options[0]
    return str(rng.choice(options, p=values / values.sum()))


def user_monthly_income_base(
    rng: np.random.Generator, occupation: str, age_group: str, location: str, profile
) -> float:
    """Derive a realistic monthly income for one user."""
    low, high = OCCUPATION_INCOME_BAND[occupation]
    raw = float(rng.uniform(low, high))
    if raw <= 0.0:
        return 0.0
    scaled = (
        raw
        * LOCATION_INCOME_MULTIPLIER[location]
        * AGE_INCOME_MULTIPLIER[age_group]
        * profile.income_multiplier
    )
    return round(float(rng.normal(scaled, scaled * 0.12)), 2)


def generate_users(
    rng: np.random.Generator,
    num_users: int,
    months: int,
    named: bool = False,
) -> pd.DataFrame:
    """Create the user dimension table with ground-truth persona labels.

    With ``named=True`` each user also receives a synthetic ``full_name`` and
    ``name_bn`` (Bangla script) and personas are assigned round-robin from
    ``DEV_PERSONAS_BALANCED`` instead of sampled, so a small population still
    covers every behaviour. Names are assigned in a shuffled order so persona
    and name stay uncorrelated.
    """
    rows = []

    if named:
        names = list(DEV_USER_NAMES)
        if num_users > len(names):
            raise ValueError(
                f"DEV_USER_NAMES has {len(names)} entries but {num_users} users "
                "were requested; add more synthetic names"
            )
        assignment = [DEV_PERSONAS_BALANCED[i % len(DEV_PERSONAS_BALANCED)] for i in range(num_users)]
        rng.shuffle(assignment)
        order = rng.permutation(num_users)
        identity = {
            int(user_index): (DEV_USER_NAMES[int(name_index)][0], DEV_USER_NAMES[int(name_index)][1])
            for user_index, name_index in enumerate(order)
        }
    else:
        persona_names = list(PERSONA_PROBABILITIES.keys())
        persona_probs = np.array(list(PERSONA_PROBABILITIES.values()), dtype=float)
        persona_probs = persona_probs / persona_probs.sum()

    min_age = min_account_age_days(months)

    for index in range(1, num_users + 1):
        if named:
            persona_name = assignment[index - 1]
        else:
            persona_name = str(rng.choice(persona_names, p=persona_probs))
        profile = PERSONA_PROFILES[persona_name]

        occupation = weighted_choice(rng, OCCUPATIONS, profile.occupation_weights)
        age_group = weighted_choice(rng, AGE_GROUPS, profile.age_weights)
        location_type = str(
            rng.choice(LOCATION_TYPES, p=np.array(LOCATION_PROBABILITIES) / sum(LOCATION_PROBABILITIES))
        )

        income_base = user_monthly_income_base(
            rng, occupation, age_group, location_type, profile
        )

        record = {
            "user_id": f"U{index:05d}",
            "age_group": age_group,
            "occupation": occupation,
            "location_type": location_type,
            "account_age_days": int(rng.integers(min_age, min_age + 1500)),
            "persona": persona_name,
            "monthly_income_base": income_base,
            "expense_ratio": round(profile.expense_ratio, 4),
            "income_cv": round(profile.income_cv, 4),
            "cash_out_rate": round(profile.cash_out_rate, 4),
            "digital_ratio": round(profile.digital_ratio, 4),
            "target_savings_rate": round(profile.savings_rate, 4),
            "goal_count": profile.goal_count,
            "anomaly_rate": round(profile.anomaly_rate, 4),
        }
        if named:
            full_name, name_bn = identity[index - 1]
            # Placed after user_id so the identity columns read together.
            record = {"user_id": record["user_id"], "full_name": full_name, "name_bn": name_bn,
                      **{k: v for k, v in record.items() if k != "user_id"}}
        rows.append(record)

    return pd.DataFrame(rows)


def generate_wallets(
    rng: np.random.Generator, users: pd.DataFrame, months: int
) -> pd.DataFrame:
    """Create wallets whose balances scale with each user's income level.

    Opening balances must cover the whole simulated window, because Step 5
    forbids negative balances and there is no credit facility.
    """
    rows = []
    opening_months = history_span_days(months) / 30.44

    for user in users.itertuples():
        income = float(user.monthly_income_base)
        profile = PERSONA_PROFILES[user.persona]
        monthly_expense = max(income * profile.expense_ratio, 1_000.0)

        # Enough runway to live through the window without overdrafting.
        runway_months = opening_months * float(rng.uniform(1.0, 1.4))
        upay_balance = round(monthly_expense * runway_months, 2)

        rows.append({
            "wallet_id": f"W{len(rows) + 1:05d}",
            "user_id": user.user_id,
            "wallet_type": "upay",
            "opening_balance": upay_balance,
        })

        bank_probability = float(np.clip(0.85 - profile.cash_out_rate * 0.6, 0.15, 0.85))
        if rng.random() < bank_probability:
            rows.append({
                "wallet_id": f"W{len(rows) + 1:05d}",
                "user_id": user.user_id,
                "wallet_type": "bank",
                "opening_balance": round(monthly_expense * float(rng.uniform(0.5, 2.5)), 2),
            })

        cash_probability = float(np.clip(0.15 + profile.cash_out_rate * 0.85, 0.15, 0.95))
        if rng.random() < cash_probability:
            rows.append({
                "wallet_id": f"W{len(rows) + 1:05d}",
                "user_id": user.user_id,
                "wallet_type": "cash",
                "opening_balance": round(monthly_expense * float(rng.uniform(0.05, 0.25)), 2),
            })

        if rng.random() < 0.18:
            rows.append({
                "wallet_id": f"W{len(rows) + 1:05d}",
                "user_id": user.user_id,
                "wallet_type": "other_digital",
                "opening_balance": round(float(rng.uniform(200.0, 8_000.0)), 2),
            })

    return pd.DataFrame(rows)


def generate_income_for_user(
    rng: np.random.Generator, user, months: list[pd.Timestamp]
) -> list[dict]:
    """Generate one user's income events, anchored to their stored income base."""
    rows: list[dict] = []

    persona = user.persona
    occupation = user.occupation
    base_income = float(user.monthly_income_base)

    income_type, source, default_regularity = OCCUPATION_INCOME_PROFILE[occupation]
    low, high = PERSONA_INCOME_FACTOR[persona]

    payday = int(rng.integers(1, 6))
    has_variable_timing = persona == "irregular_income" or occupation in (
        "freelancer", "business", "self_employed",
    )

    if base_income <= 0.0:
        for month in months:
            timestamp = month + pd.Timedelta(
                days=int(rng.integers(0, month.days_in_month)),
                hours=int(rng.integers(8, 20)),
                minutes=int(rng.integers(0, 60)),
            )
            rows.append({
                "income_id": "PENDING",
                "user_id": user.user_id,
                "timestamp": timestamp,
                "income_type": income_type,
                "amount": round(float(rng.uniform(0.0, 4_000.0)), 2),
                "regularity": "irregular",
                "source": source,
            })
        return rows

    for month in months:
        if persona == "irregular_income" and rng.random() < 0.12:
            # Occasional zero-income month: this is what makes the persona's
            # cash flow genuinely hard to forecast.
            continue

        month_income = base_income * float(rng.uniform(low, high))

        if has_variable_timing:
            n_events = int(rng.integers(1, 4))
        elif income_type == "business":
            n_events = int(rng.integers(1, 3))
        else:
            n_events = 1

        splits = rng.dirichlet(np.ones(n_events) * 4.0)
        for split in splits:
            day = (
                int(rng.integers(1, month.days_in_month + 1))
                if has_variable_timing
                else min(payday, month.days_in_month)
            )
            timestamp = month + pd.Timedelta(
                days=day - 1,
                hours=int(rng.integers(8, 19)),
                minutes=int(rng.integers(0, 60)),
            )

            regularity = default_regularity
            if persona == "irregular_income":
                regularity = "irregular"
            elif persona == "seasonal_spender" or income_type == "business":
                regularity = "seasonal"

            rows.append({
                "income_id": "PENDING",
                "user_id": user.user_id,
                "timestamp": timestamp,
                "income_type": income_type,
                "amount": round(float(month_income * split), 2),
                "regularity": regularity,
                "source": source,
            })

    return rows


def generate_all_income(
    rng: np.random.Generator, users: pd.DataFrame, months: list[pd.Timestamp]
) -> pd.DataFrame:
    """Generate income events for every user with globally unique ids."""
    rows: list[dict] = []
    counter = 0

    for user in users.itertuples():
        for row in generate_income_for_user(rng, user, months):
            counter += 1
            row["income_id"] = f"I{counter:07d}"
            rows.append(row)

    return pd.DataFrame(rows)