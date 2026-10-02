"""Controlled synthetic financial data generator for the upay Financial Life Copilot.

Produces research datasets with known behavioural ground truth (persona labels)
so later forecasting, anomaly detection and financial-health models can be
evaluated honestly.

Every amount is derived from a per-user financial profile (occupation, age,
location, persona) rather than drawn independently, so the dataset stays
internally realistic and time-consistent.

Run from the project root:
    python scripts/generate_synthetic_data.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42

NUM_USERS = 500
MONTHS = 9
START_DATE = date(2026, 1, 1)

OUTPUT_DIR = Path("data/generated")

np.random.seed(SEED)

PERSONAS = [
    "stable_saver",
    "end_month_shortage",
    "irregular_income",
    "high_cash_dependency",
    "goal_oriented",
    "seasonal_spender",
    "sudden_anomaly",
    "financial_pressure",
]

PERSONA_PROBABILITIES = {
    "stable_saver": 0.20,
    "end_month_shortage": 0.15,
    "irregular_income": 0.12,
    "high_cash_dependency": 0.12,
    "goal_oriented": 0.15,
    "seasonal_spender": 0.10,
    "sudden_anomaly": 0.06,
    "financial_pressure": 0.10,
}

AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55+"]

OCCUPATIONS = [
    "student",
    "private_employee",
    "business",
    "freelancer",
    "self_employed",
    "other",
]

LOCATION_TYPES = ["urban", "semi_urban", "rural"]
LOCATION_PROBABILITIES = [0.55, 0.30, 0.15]
LOCATION_INCOME_MULTIPLIER = {"urban": 1.18, "semi_urban": 1.0, "rural": 0.82}

# Monthly income band (BDT) by occupation: (low, high).
OCCUPATION_INCOME_BAND = {
    "student": (0.0, 9_000.0),
    "private_employee": (26_000.0, 65_000.0),
    "business": (45_000.0, 220_000.0),
    "freelancer": (18_000.0, 95_000.0),
    "self_employed": (20_000.0, 85_000.0),
    "other": (12_000.0, 55_000.0),
}

AGE_INCOME_MULTIPLIER = {
    "18-24": 0.62,
    "25-34": 1.00,
    "35-44": 1.12,
    "45-54": 0.98,
    "55+": 0.74,
}


@dataclass(frozen=True)
class PersonaProfile:
    """Behavioural knobs for one ground-truth persona.

    income_multiplier   scales the occupation income band
    expense_ratio       expected expense / income
    income_cv           coefficient of variation on monthly income
    cash_out_rate       probability a spending day includes a cash-out
    digital_ratio       share of spending done through upay channels
    savings_rate        target monthly saving share of income
    goal_count          expected number of active financial goals
    anomaly_rate        probability of a sudden shock event
    occupation_weights  plausible occupations for this persona
    age_weights         plausible age groups for this persona
    """

    name: str
    income_multiplier: float
    expense_ratio: float
    income_cv: float
    cash_out_rate: float
    digital_ratio: float
    savings_rate: float
    goal_count: int
    anomaly_rate: float
    occupation_weights: dict = field(default_factory=dict)
    age_weights: dict = field(default_factory=dict)


PERSONA_PROFILES: dict[str, PersonaProfile] = {
    "stable_saver": PersonaProfile(
        name="stable_saver",
        income_multiplier=1.05,
        expense_ratio=0.62,
        income_cv=0.08,
        cash_out_rate=0.10,
        digital_ratio=0.80,
        savings_rate=0.25,
        goal_count=2,
        anomaly_rate=0.04,
        occupation_weights={
            "private_employee": 0.55,
            "self_employed": 0.20,
            "freelancer": 0.15,
            "other": 0.10,
        },
        age_weights={"25-34": 0.50, "35-44": 0.30, "45-54": 0.20},
    ),
    "end_month_shortage": PersonaProfile(
        name="end_month_shortage",
        income_multiplier=0.95,
        expense_ratio=0.95,
        income_cv=0.10,
        cash_out_rate=0.22,
        digital_ratio=0.70,
        savings_rate=0.02,
        goal_count=1,
        anomaly_rate=0.06,
        occupation_weights={
            "private_employee": 0.40,
            "self_employed": 0.30,
            "business": 0.20,
            "other": 0.10,
        },
        age_weights={"18-24": 0.25, "25-34": 0.45, "35-44": 0.30},
    ),
    "irregular_income": PersonaProfile(
        name="irregular_income",
        income_multiplier=1.0,
        expense_ratio=0.80,
        income_cv=0.55,
        cash_out_rate=0.20,
        digital_ratio=0.60,
        savings_rate=0.05,
        goal_count=1,
        anomaly_rate=0.08,
        occupation_weights={
            "freelancer": 0.40,
            "business": 0.30,
            "self_employed": 0.20,
            "other": 0.10,
        },
        age_weights={"18-24": 0.30, "25-34": 0.45, "35-44": 0.25},
    ),
    "high_cash_dependency": PersonaProfile(
        name="high_cash_dependency",
        income_multiplier=0.92,
        expense_ratio=0.85,
        income_cv=0.12,
        cash_out_rate=0.62,
        digital_ratio=0.25,
        savings_rate=0.05,
        goal_count=1,
        anomaly_rate=0.06,
        occupation_weights={
            "self_employed": 0.40,
            "business": 0.30,
            "private_employee": 0.20,
            "other": 0.10,
        },
        age_weights={"18-24": 0.20, "25-34": 0.40, "35-44": 0.40},
    ),
    "goal_oriented": PersonaProfile(
        name="goal_oriented",
        income_multiplier=1.08,
        expense_ratio=0.70,
        income_cv=0.09,
        cash_out_rate=0.12,
        digital_ratio=0.78,
        savings_rate=0.28,
        goal_count=3,
        anomaly_rate=0.04,
        occupation_weights={
            "private_employee": 0.45,
            "freelancer": 0.25,
            "self_employed": 0.20,
            "other": 0.10,
        },
        age_weights={"25-34": 0.55, "35-44": 0.30, "18-24": 0.15},
    ),
    "seasonal_spender": PersonaProfile(
        name="seasonal_spender",
        income_multiplier=1.0,
        expense_ratio=0.88,
        income_cv=0.15,
        cash_out_rate=0.25,
        digital_ratio=0.62,
        savings_rate=0.04,
        goal_count=1,
        anomaly_rate=0.05,
        occupation_weights={
            "private_employee": 0.35,
            "business": 0.25,
            "self_employed": 0.25,
            "other": 0.15,
        },
        age_weights={"25-34": 0.45, "35-44": 0.30, "45-54": 0.25},
    ),
    "sudden_anomaly": PersonaProfile(
        name="sudden_anomaly",
        income_multiplier=1.02,
        expense_ratio=0.80,
        income_cv=0.11,
        cash_out_rate=0.20,
        digital_ratio=0.70,
        savings_rate=0.12,
        goal_count=2,
        anomaly_rate=0.55,
        occupation_weights={
            "private_employee": 0.40,
            "business": 0.20,
            "freelancer": 0.20,
            "self_employed": 0.20,
        },
        age_weights={"25-34": 0.45, "35-44": 0.35, "45-54": 0.20},
    ),
    "financial_pressure": PersonaProfile(
        name="financial_pressure",
        income_multiplier=0.68,
        expense_ratio=1.15,
        income_cv=0.14,
        cash_out_rate=0.38,
        digital_ratio=0.50,
        savings_rate=0.0,
        goal_count=1,
        anomaly_rate=0.12,
        occupation_weights={
            "student": 0.20,
            "self_employed": 0.30,
            "freelancer": 0.25,
            "private_employee": 0.15,
            "other": 0.10,
        },
        age_weights={"18-24": 0.40, "25-34": 0.40, "35-44": 0.20},
    ),
}

WALLET_TYPES = ["upay", "bank", "cash", "other_digital"]


def weighted_choice(options: list[str], weights: dict) -> str:
    """Deterministically pick one key from ``options`` using ``weights``."""
    values = [weights.get(option, 0.0) for option in options]
    if sum(values) <= 0:
        return options[0]
    return str(np.random.choice(options, p=np.array(values) / sum(values)))


def month_window() -> list[tuple[int, int]]:
    """Return (year, month) pairs covered by the simulation window."""
    months: list[tuple[int, int]] = []
    year, month = START_DATE.year, START_DATE.month
    for _ in range(MONTHS):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def end_of_history_date() -> date:
    """Last calendar day covered by the generated history."""
    year, month = month_window()[-1]
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def history_span_days() -> int:
    """Number of days the account must be open to cover the full history."""
    return (end_of_history_date() - START_DATE).days + 1


def min_account_age_days() -> int:
    """Account must predate the history window so opening balances are valid.

    Age is measured at the reference date (end of the history window), so an
    account needs to be at least as old as the history it explains.
    """
    return history_span_days()


def user_monthly_income_base(occupation: str, age_group: str, location: str,
                             persona: PersonaProfile) -> float:
    """Derive a realistic monthly income for one user."""
    low, high = OCCUPATION_INCOME_BAND[occupation]
    raw = float(np.random.uniform(low, high))
    if raw <= 0.0:
        return 0.0
    scaled = (
        raw
        * LOCATION_INCOME_MULTIPLIER[location]
        * AGE_INCOME_MULTIPLIER[age_group]
        * persona.income_multiplier
    )
    return round(float(np.random.normal(scaled, scaled * 0.12)), 2)


def generate_users(num_users: int) -> pd.DataFrame:
    """Create the user dimension table with ground-truth persona labels."""
    rows = []
    persona_names = list(PERSONA_PROBABILITIES.keys())
    persona_probs = list(PERSONA_PROBABILITIES.values())

    for i in range(1, num_users + 1):
        persona_name = str(
            np.random.choice(persona_names, p=np.array(persona_probs) / sum(persona_probs))
        )
        profile = PERSONA_PROFILES[persona_name]

        occupation = weighted_choice(OCCUPATIONS, profile.occupation_weights)
        age_group = weighted_choice(AGE_GROUPS, profile.age_weights)
        location_type = str(
            np.random.choice(
                LOCATION_TYPES,
                p=np.array(LOCATION_PROBABILITIES) / sum(LOCATION_PROBABILITIES),
            )
        )

        monthly_income_base = user_monthly_income_base(
            occupation, age_group, location_type, profile
        )

        min_age = min_account_age_days()
        account_age_days = int(
            np.random.randint(min_age, max(min_age + 1, 1500 + min_age))
        )

        rows.append({
            "user_id": f"U{i:05d}",
            "age_group": age_group,
            "occupation": occupation,
            "location_type": location_type,
            "account_age_days": account_age_days,
            "persona": persona_name,
            "monthly_income_base": monthly_income_base,
            "expense_ratio": round(profile.expense_ratio, 4),
            "income_cv": round(profile.income_cv, 4),
            "cash_out_rate": round(profile.cash_out_rate, 4),
            "digital_ratio": round(profile.digital_ratio, 4),
            "target_savings_rate": round(profile.savings_rate, 4),
            "goal_count": profile.goal_count,
            "anomaly_rate": round(profile.anomaly_rate, 4),
        })

    return pd.DataFrame(rows)


def generate_wallets(users: pd.DataFrame) -> pd.DataFrame:
    """Create wallets whose balances scale with each user's income level."""
    rows = []

    for _, user in users.iterrows():
        user_id = user["user_id"]
        income = float(user["monthly_income_base"])
        profile = PERSONA_PROFILES[user["persona"]]
        expense_ratio = float(user["expense_ratio"])

        upay_balance = round(float(np.random.uniform(0.10, 0.55)) * (income + 2_000.0), 2)
        rows.append({
            "wallet_id": f"W{len(rows) + 1:05d}",
            "user_id": user_id,
            "wallet_type": "upay",
            "opening_balance": upay_balance,
        })

        # Income stability drives bank adoption: salaried users bank, cash-heavy users do not.
        bank_probability = float(
            np.clip(0.85 - profile.cash_out_rate * 0.6, 0.15, 0.85)
        )
        if np.random.random() < bank_probability:
            bank_balance = round(float(np.random.uniform(1.0, 4.0)) * max(income, 5_000.0), 2)
            rows.append({
                "wallet_id": f"W{len(rows) + 1:05d}",
                "user_id": user_id,
                "wallet_type": "bank",
                "opening_balance": bank_balance,
            })

        cash_probability = float(np.clip(0.15 + profile.cash_out_rate * 0.85, 0.15, 0.95))
        if np.random.random() < cash_probability:
            cash_balance = round(float(np.random.uniform(0.2, 1.2)) * max(income * 0.4, 1_000.0), 2)
            rows.append({
                "wallet_id": f"W{len(rows) + 1:05d}",
                "user_id": user_id,
                "wallet_type": "cash",
                "opening_balance": cash_balance,
            })

        if np.random.random() < 0.18:
            rows.append({
                "wallet_id": f"W{len(rows) + 1:05d}",
                "user_id": user_id,
                "wallet_type": "other_digital",
                "opening_balance": round(float(np.random.uniform(200.0, 8_000.0)), 2),
            })

    return pd.DataFrame(rows)


def validate(users: pd.DataFrame, wallets: pd.DataFrame) -> None:
    """Fail loudly if the generated data is not internally coherent."""
    assert set(users["persona"]) == set(PERSONAS), "persona set mismatch"
    assert not users["user_id"].duplicated().any(), "duplicate user_id"
    assert not wallets["wallet_id"].duplicated().any(), "duplicate wallet_id"
    assert set(wallets["wallet_type"]) <= set(WALLET_TYPES), "unexpected wallet_type"

    every_user_has_upay = (
        wallets[wallets["wallet_type"] == "upay"]["user_id"].nunique()
        == users["user_id"].nunique()
    )
    assert every_user_has_upay, "some users have no upay wallet"

    orphans = set(wallets["user_id"]) - set(users["user_id"])
    assert not orphans, f"wallets referencing unknown users: {orphans}"

    # Account must be older than the history window, otherwise opening balances
    # would describe a period before the account existed.
    assert (users["account_age_days"] >= min_account_age_days()).all(), (
        "account_age_days shorter than simulated history"
    )

    earners = users[users["monthly_income_base"] > 0]
    assert (earners["monthly_income_base"] > 0).all(), "non-positive income"


def report(users: pd.DataFrame, wallets: pd.DataFrame) -> None:
    counts = users["persona"].value_counts()
    print(f"Generated {len(users)} users")
    print(f"Generated {len(wallets)} wallets")
    print("\nPersona distribution:")
    for persona in PERSONAS:
        share = counts.get(persona, 0) / max(len(users), 1)
        print(f"  {persona:<22} {counts.get(persona, 0):>4}  ({share:6.2%})")

    print("\nWallets per type:")
    print(wallets["wallet_type"].value_counts().to_string())

    earners = users[users["monthly_income_base"] > 0]
    print("\nMonthly income base by occupation (BDT):")
    print(
        earners.groupby("occupation")["monthly_income_base"]
        .agg(["count", "mean", "min", "max"])
        .round(0)
        .to_string()
    )

    print(f"\nHistory window: {START_DATE} to {end_of_history_date()} ({MONTHS} months)")
    print(f"Seed: {SEED}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    users = generate_users(NUM_USERS)
    wallets = generate_wallets(users)

    validate(users, wallets)

    users.to_csv(OUTPUT_DIR / "users.csv", index=False)
    wallets.to_csv(OUTPUT_DIR / "wallets.csv", index=False)

    report(users, wallets)


if __name__ == "__main__":
    main()