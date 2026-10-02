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

TRANSACTION_CATEGORIES = {
    "food": ["restaurant", "grocery", "snacks"],
    "transport": ["bus", "ride", "fuel"],
    "shopping": ["clothing", "electronics", "general"],
    "education": ["tuition", "books", "course"],
    "health": ["medicine", "doctor", "pharmacy"],
    "utilities": ["electricity", "internet", "water"],
    "communication": ["mobile_recharge", "internet"],
    "entertainment": ["movies", "games", "events"],
    "family": ["family_support", "gift"],
    "housing": ["rent", "maintenance"],
    "cash": ["cash_out"],
    "transfer": ["salary_credit", "self_transfer", "p2p"],
    "other": ["misc"],
}

TRANSACTION_TYPES = [
    "payment",
    "cash_out",
    "cash_in",
    "transfer",
    "bill_payment",
    "mobile_recharge",
    "bank_transfer",
]

DIRECTIONS = ["inflow", "outflow"]

CHANNELS = ["upay", "agent", "merchant", "bank", "online"]

MERCHANT_TYPES = ["merchant", "agent", "ecommerce", "utility", "person"]

# Income type / source / regularity implied by occupation.
OCCUPATION_INCOME_PROFILE = {
    "student": ("allowance", "family", "irregular"),
    "private_employee": ("salary", "employer", "regular"),
    "business": ("business", "own_business", "seasonal"),
    "freelancer": ("freelance", "freelance_client", "irregular"),
    "self_employed": ("business", "own_business", "irregular"),
    "other": ("salary", "employer", "regular"),
}

# Monthly discretionary (non-bill) transaction counts by persona.
PERSONA_TRANSACTION_COUNT = {
    "stable_saver": (14, 30),
    "end_month_shortage": (22, 44),
    "irregular_income": (18, 36),
    "high_cash_dependency": (30, 55),
    "goal_oriented": (14, 30),
    "seasonal_spender": (20, 38),
    "sudden_anomaly": (18, 34),
    "financial_pressure": (26, 48),
}

# Share of monthly income a persona earns, and how volatile it is.
PERSONA_INCOME_FACTOR = {
    "stable_saver": (0.97, 1.05),
    "end_month_shortage": (0.95, 1.06),
    "irregular_income": (0.35, 1.90),
    "high_cash_dependency": (0.94, 1.07),
    "goal_oriented": (0.97, 1.06),
    "seasonal_spender": (0.90, 1.15),
    "sudden_anomaly": (0.95, 1.08),
    "financial_pressure": (0.85, 1.05),
}

# Typical single-transaction size as a fraction of monthly income, so ticket
# sizes scale with what the user can actually afford. Everyday purchases are
# small; rent and large transfers are large.
CATEGORY_TICKET_FRACTION = {
    "food": 0.0045,
    "transport": 0.0022,
    "shopping": 0.0180,
    "education": 0.0550,
    "health": 0.0140,
    "utilities": 0.0280,
    "communication": 0.0048,
    "entertainment": 0.0090,
    "family": 0.0200,
    "housing": 0.2200,
    "cash": 0.0600,
    "transfer": 0.0400,
    "other": 0.0080,
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

        upay_balance = round(float(np.random.uniform(0.35, 1.10)) * (income + 3_000.0), 2)
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



def month_starts() -> list[pd.Timestamp]:
    """First day of each month in the simulation window."""
    return list(pd.date_range(START_DATE, periods=MONTHS, freq="MS"))


def days_in_month(month: pd.Timestamp) -> int:
    return int(month.days_in_month)


def generate_income_for_user(user: pd.Series, months: list[pd.Timestamp]) -> list[dict]:
    """Generate one user's income events, anchored to their stored income base.

    Amounts scale with ``monthly_income_base`` from ``users.csv`` so the two
    tables never disagree about how much this user earns.
    """
    rows: list[dict] = []

    user_id = user["user_id"]
    persona = user["persona"]
    occupation = user["occupation"]
    base_income = float(user["monthly_income_base"])

    income_type, source, default_regularity = OCCUPATION_INCOME_PROFILE[occupation]
    low, high = PERSONA_INCOME_FACTOR[persona]

    payday = int(np.random.randint(1, 6))
    has_variable_timing = persona == "irregular_income" or occupation in (
        "freelancer", "business", "self_employed",
    )

    if base_income <= 0.0:
        # No recorded earnings: emit small, scattered irregular amounts so the
        # user still has a plausible history.
        for month in months:
            day = int(np.random.randint(1, days_in_month(month) + 1))
            timestamp = month + pd.Timedelta(
                days=day - 1,
                hours=int(np.random.randint(8, 20)),
                minutes=int(np.random.randint(0, 60)),
            )
            rows.append({
                "income_id": "PENDING",
                "user_id": user_id,
                "timestamp": timestamp,
                "income_type": income_type,
                "amount": round(float(np.random.uniform(0.0, 4_000.0)), 2),
                "regularity": "irregular",
                "source": source,
            })
        return rows

    for month in months:
        if persona == "irregular_income" and np.random.random() < 0.12:
            # Occasional zero-income month: this is what makes the persona's
            # cash flow hard to forecast.
            continue
        month_income = base_income * float(np.random.uniform(low, high))

        if has_variable_timing:
            n_events = int(np.random.randint(1, 4))
        elif income_type == "business":
            n_events = int(np.random.randint(1, 3))
        else:
            n_events = 1

        splits = np.random.dirichlet(np.ones(n_events) * 4.0)
        for split in splits:
            if has_variable_timing:
                day = int(np.random.randint(1, days_in_month(month) + 1))
            else:
                day = min(payday, days_in_month(month))

            timestamp = month + pd.Timedelta(
                days=day - 1,
                hours=int(np.random.randint(8, 19)),
                minutes=int(np.random.randint(0, 60)),
            )

            regularity = default_regularity
            if persona == "irregular_income":
                regularity = "irregular"
            elif persona == "seasonal_spender" or income_type == "business":
                regularity = "seasonal"

            rows.append({
                "income_id": "PENDING",
                "user_id": user_id,
                "timestamp": timestamp,
                "income_type": income_type,
                "amount": round(float(month_income * split), 2),
                "regularity": regularity,
                "source": source,
            })

    return rows


def generate_all_income(users: pd.DataFrame, months: list[pd.Timestamp]) -> pd.DataFrame:
    """Generate income events for every user, keeping ids globally unique."""
    rows: list[dict] = []
    counter = 0

    for _, user in users.iterrows():
        for row in generate_income_for_user(user, months):
            counter += 1
            row["income_id"] = f"I{counter:07d}"
            rows.append(row)

    return pd.DataFrame(rows)


def persona_category_weights(persona: str) -> dict[str, float]:
    """Relative propensity to spend on each category."""
    weights = {category: 1.0 for category in TRANSACTION_CATEGORIES}

    if persona == "financial_pressure":
        weights["food"] *= 1.4
        weights["family"] *= 1.5
        weights["health"] *= 1.2
        weights["shopping"] *= 0.6
    elif persona == "goal_oriented":
        weights["shopping"] *= 0.6
        weights["entertainment"] *= 0.6
        weights["education"] *= 1.4
    elif persona == "high_cash_dependency":
        weights["food"] *= 1.3
        weights["transport"] *= 1.2
        weights["entertainment"] *= 1.2
    elif persona == "seasonal_spender":
        weights["shopping"] *= 1.5
        weights["family"] *= 1.3
        weights["entertainment"] *= 1.3
    elif persona == "sudden_anomaly":
        weights["health"] *= 1.4
        weights["other"] *= 1.3
    elif persona == "stable_saver":
        weights["shopping"] *= 0.7
        weights["entertainment"] *= 0.7

    return weights


def sample_day(persona: str, dim: int) -> int:
    """Sample a day of the month with persona-specific timing behaviour."""
    days = np.arange(1, dim + 1)

    if persona == "end_month_shortage":
        weights = np.where(days >= 23, 3.2, 1.0)
    elif persona == "seasonal_spender":
        weights = np.where(days >= 20, 2.8, 1.0)
    elif persona == "stable_saver":
        weights = np.where(days >= 25, 0.35, 1.0)
    elif persona == "goal_oriented":
        weights = np.where(np.isin(days, [2, 3, 4, 28]), 2.2, 0.9)
    elif persona == "financial_pressure":
        weights = np.where(days >= 24, 2.0, 1.0)
    else:
        weights = np.ones(len(days), dtype=float)

    return int(np.random.choice(days, p=weights / weights.sum()))


def monthly_bills_for_user(user: pd.Series) -> list[dict]:
    """Recurring monthly obligations for one user, scaled to their income."""
    income = float(user["monthly_income_base"])
    persona = user["persona"]
    occupation = user["occupation"]
    bills: list[dict] = []

    if occupation == "student":
        bills.append({
            "name": "family_support", "category": "family",
            "amount": round(float(np.random.uniform(1_500.0, 5_000.0)), 2),
            "day": int(np.random.randint(5, 12)), "type": "payment", "channel": "upay",
        })
    else:
        bills.append({
            "name": "rent", "category": "housing",
            "amount": round(float(np.random.uniform(0.18, 0.34)) * max(income, 10_000.0), 2),
            "day": int(np.random.randint(1, 6)), "type": "payment", "channel": "upay",
        })

    bills.append({
        "name": "electricity", "category": "utilities",
        "amount": round(float(np.random.uniform(400.0, 2_800.0)), 2),
        "day": int(np.random.randint(6, 14)), "type": "bill_payment", "channel": "upay",
    })
    bills.append({
        "name": "internet", "category": "communication",
        "amount": round(float(np.random.uniform(500.0, 2_000.0)), 2),
        "day": int(np.random.randint(3, 10)), "type": "bill_payment", "channel": "upay",
    })
    bills.append({
        "name": "mobile_recharge", "category": "communication",
        "amount": round(float(np.random.uniform(100.0, 900.0)), 2),
        "day": int(np.random.randint(2, 27)), "type": "mobile_recharge", "channel": "upay",
    })

    if persona == "goal_oriented" or occupation == "student":
        bills.append({
            "name": "education", "category": "education",
            "amount": round(float(np.random.uniform(1_200.0, 9_000.0)), 2),
            "day": int(np.random.randint(5, 20)), "type": "payment", "channel": "upay",
        })

    if persona in ("financial_pressure", "sudden_anomaly"):
        bills.append({
            "name": "medicine", "category": "health",
            "amount": round(float(np.random.uniform(500.0, 4_500.0)), 2),
            "day": int(np.random.randint(8, 26)), "type": "payment", "channel": "upay",
        })

    return bills


def generate_transactions(
    users: pd.DataFrame,
    wallets: pd.DataFrame,
    income: pd.DataFrame,
    months: list[pd.Timestamp],
) -> pd.DataFrame:
    """Generate a chronologically ordered, balance-consistent transaction log.

    Events are collected per user, then replayed in timestamp order so that
    ``balance_after`` is a true running balance and every amount is funded by
    the wallet it actually debits.
    """
    wallet_map = (
        wallets[wallets["wallet_type"] == "upay"].set_index("user_id")["wallet_id"].to_dict()
    )
    cash_map = (
        wallets[wallets["wallet_type"] == "cash"].set_index("user_id")["wallet_id"].to_dict()
    )
    opening_by_wallet = {
        row.wallet_id: float(row.opening_balance) for row in wallets.itertuples()
    }

    events: list[dict] = []
    cash_pair_counter = 0

    def emit(user_id, wallet_id, timestamp, transaction_type, direction, amount,
             category, subcategory, merchant_type, channel, cash_out_flag, order,
             pair_id=None):
        events.append({
            "user_id": user_id,
            "wallet_id": wallet_id,
            "timestamp": timestamp,
            "transaction_type": transaction_type,
            "direction": direction,
            "amount": round(abs(amount), 2),
            "category": category,
            "subcategory": subcategory,
            "merchant_type": merchant_type,
            "channel": channel,
            "cash_out": cash_out_flag,
            "_order": order,
            "pair_id": pair_id,
        })

    income_groups = {uid: grp for uid, grp in income.groupby("user_id")}
    discrete_categories = [
        c for c in TRANSACTION_CATEGORIES if c not in ("housing", "cash", "transfer", "other")
    ]

    for _, user in users.iterrows():
        user_id = user["user_id"]
        persona = user["persona"]
        primary_wallet = wallet_map[user_id]
        cash_wallet = cash_map.get(user_id)
        income_base = float(user["monthly_income_base"])
        expense_ratio = float(user["expense_ratio"])
        cash_out_rate = float(user["cash_out_rate"])
        anomaly_rate = float(user["anomaly_rate"])
        digital_ratio = float(user["digital_ratio"])

        bills = monthly_bills_for_user(user)
        category_weights = persona_category_weights(persona)
        category_probs = np.array([category_weights[c] for c in discrete_categories], dtype=float)
        category_probs = category_probs / category_probs.sum()
        low_count, high_count = PERSONA_TRANSACTION_COUNT[persona]

        cash_available = opening_by_wallet.get(cash_wallet, 0.0) if cash_wallet else 0.0

        for month in months:
            month_end = month + pd.offsets.MonthBegin(1)
            dim = days_in_month(month)

            group = income_groups.get(user_id)
            if group is not None and len(group):
                month_events = group[
                    (group["timestamp"] >= month) & (group["timestamp"] < month_end)
                ].sort_values("timestamp")
            else:
                month_events = income.iloc[0:0]

            month_income = float(month_events["amount"].sum()) if len(month_events) else 0.0

            fixed_total = float(sum(bill["amount"] for bill in bills))
            pool_multiplier = float(np.random.uniform(0.92, 1.08))
            discretionary_budget = max(
                (month_income * expense_ratio - fixed_total) * pool_multiplier,
                month_income * 0.15,
                500.0,
            )
            count = int(np.random.randint(low_count, high_count + 1))

            draft: list[tuple[str, float, int]] = []
            for _ in range(count):
                category = str(np.random.choice(discrete_categories, p=category_probs))
                ticket = max(
                    CATEGORY_TICKET_FRACTION[category] * max(income_base, 6_000.0), 25.0
                )
                amount = float(np.random.lognormal(mean=np.log(ticket), sigma=0.55))
                draft.append((category, amount, sample_day(persona, dim)))

            drawn_total = float(sum(item[1] for item in draft))
            scale = (discretionary_budget / drawn_total) if drawn_total > 0 else 1.0

            planned: list[dict] = []

            for bill in bills:
                day = min(bill["day"], dim)
                planned.append({
                    "timestamp": month + pd.Timedelta(
                        days=day - 1,
                        hours=int(np.random.randint(8, 21)),
                        minutes=int(np.random.randint(0, 60)),
                    ),
                    "category": bill["category"],
                    "amount": float(bill["amount"]),
                    "type": bill["type"],
                    "subcategory": None,
                })

            for category, amount, day in draft:
                planned.append({
                    "timestamp": month + pd.Timedelta(
                        days=day - 1,
                        hours=int(np.random.randint(6, 23)),
                        minutes=int(np.random.randint(0, 60)),
                    ),
                    "category": category,
                    "amount": round(max(amount * scale, 20.0), 2),
                    "type": "payment",
                    "subcategory": None,
                })

            if np.random.random() < anomaly_rate:
                for _ in range(int(np.random.randint(1, 4))):
                    category = str(
                        np.random.choice(["health", "family", "other"], p=[0.45, 0.40, 0.15])
                    )
                    planned.append({
                        "timestamp": month + pd.Timedelta(
                            days=int(np.random.randint(1, dim + 1)) - 1,
                            hours=int(np.random.randint(9, 22)),
                            minutes=int(np.random.randint(0, 60)),
                        ),
                        "category": category,
                        "amount": round(
                            float(np.random.uniform(0.25, 0.85)) * max(month_income, 5_000.0), 2
                        ),
                        "type": "payment",
                        "subcategory": str(np.random.choice(TRANSACTION_CATEGORIES[category])),
                    })

            timeline: list[dict] = []
            for event in month_events.itertuples():
                sub = "salary_credit" if event.income_type == "salary" else "p2p"
                timeline.append({
                    "timestamp": event.timestamp,
                    "category": "transfer",
                    "amount": float(event.amount),
                    "type": "transfer",
                    "subcategory": sub,
                    "is_income": True,
                })
            for item in planned:
                timeline.append({**item, "is_income": False})
            timeline.sort(key=lambda item: item["timestamp"])

            n_cashouts = int(np.random.binomial(6, cash_out_rate)) if cash_wallet else 0
            cash_schedule: dict[int, float] = {}
            if n_cashouts:
                share = float(np.random.uniform(0.20, 0.55))
                per_cashout = round(discretionary_budget * share / n_cashouts, 2)
                for _ in range(n_cashouts):
                    day = int(np.random.randint(1, dim + 1))
                    cash_schedule[day] = cash_schedule.get(day, 0.0) + per_cashout

            for item in timeline:
                timestamp = item["timestamp"]
                day = timestamp.day
                category = item["category"]
                amount = float(item["amount"])

                if day in cash_schedule:
                    withdraw = cash_schedule[day]
                    cash_ts = timestamp - pd.Timedelta(hours=2)
                    cash_pair_counter += 1
                    pair_id = f"C{cash_pair_counter:08d}"
                    emit(user_id, primary_wallet, cash_ts, "cash_out", "outflow",
                         withdraw, "cash", "cash_out", "agent", "agent", True, 0, pair_id)
                    emit(user_id, cash_wallet, cash_ts, "cash_in", "inflow",
                         withdraw, "cash", "cash_out", "agent", "agent", True, 1, pair_id)
                    cash_available += withdraw

                if item["is_income"]:
                    emit(user_id, primary_wallet, timestamp, "transfer", "inflow",
                         amount, "transfer", item["subcategory"], "person", "bank", False, 0)
                    continue

                subcategory = item["subcategory"] or str(
                    np.random.choice(TRANSACTION_CATEGORIES[category])
                )

                funded_by_cash = (
                    cash_wallet is not None
                    and cash_available >= amount
                    and np.random.random() < (1.0 - digital_ratio)
                )
                wallet_id = cash_wallet if funded_by_cash else primary_wallet

                if funded_by_cash:
                    channel, merchant_type = "agent", "agent"
                elif category in ("utilities", "communication"):
                    channel, merchant_type = "upay", "utility"
                elif category == "shopping":
                    channel = "online" if np.random.random() < 0.35 else "upay"
                    merchant_type = "ecommerce" if channel == "online" else "merchant"
                else:
                    channel, merchant_type = "upay", "merchant"

                if funded_by_cash:
                    cash_available -= amount

                emit(user_id, wallet_id, timestamp, item["type"], "outflow",
                     amount, category, subcategory, merchant_type, channel, funded_by_cash, 0)

    # Replay every event chronologically to produce true running balances.
    events.sort(key=lambda e: (e["user_id"], e["timestamp"], e["_order"], e["amount"]))

    balances = dict(opening_by_wallet)
    overdraft_limit = {
        wallet_id: round(amount * 0.6, 2) for wallet_id, amount in opening_by_wallet.items()
    }

    rows: list[dict] = []
    row_index: dict[str, int] = {}
    overdraft_events = 0
    pending_cash_cap: dict[str, float] = {}

    for event in events:
        wallet_id = event["wallet_id"]
        signed = event["amount"] if event["direction"] == "inflow" else -event["amount"]
        balance = balances[wallet_id]
        new_balance = round(balance + signed, 2)

        pair_id = event.get("pair_id")

        # The deposit leg of a cash transfer must match the withdrawal leg,
        # even when the withdrawal gets capped by the overdraft limit.
        if pair_id is not None and event["direction"] == "inflow":
            capped = pending_cash_cap.get(pair_id)
            if capped is not None and capped <= 0.0:
                # The matching withdrawal was dropped for lack of funds.
                continue
            if capped is not None and capped < event["amount"]:
                event["amount"] = capped
                signed = capped
                new_balance = round(balance + signed, 2)
                partner = row_index.get(pair_id)
                if partner is not None:
                    rows[partner]["amount"] = capped

        if new_balance < -overdraft_limit[wallet_id]:
            # Cannot spend past the limit: reduce to what is actually available.
            allowed = round(max(balance + overdraft_limit[wallet_id], 0.0), 2)
            if allowed <= 0.0:
                # Nothing available: the purchase simply never happens. Record
                # it so the paired leg of a cash transfer is dropped too.
                if pair_id is not None:
                    pending_cash_cap[pair_id] = 0.0
                continue
            event["amount"] = allowed
            signed = allowed if event["direction"] == "inflow" else -allowed
            new_balance = round(balance + signed, 2)
            if pair_id is not None and event["direction"] == "outflow":
                pending_cash_cap[pair_id] = allowed

        if event["direction"] == "outflow" and new_balance < 0:
            overdraft_events += 1

        balances[wallet_id] = new_balance
        position = len(rows)
        rows.append({
            "transaction_id": f"T{position + 1:08d}",
            "user_id": event["user_id"],
            "wallet_id": wallet_id,
            "timestamp": event["timestamp"],
            "transaction_type": event["transaction_type"],
            "direction": event["direction"],
            "amount": event["amount"],
            "category": event["category"],
            "subcategory": event["subcategory"],
            "merchant_type": event["merchant_type"],
            "channel": event["channel"],
            "cash_out": event["cash_out"],
            "balance_after": new_balance,
        })
        if pair_id is not None:
            row_index[pair_id] = position

    print(f"  transactions with an overdraft balance: {overdraft_events}")
    return pd.DataFrame(rows)


def validate(
    users: pd.DataFrame,
    wallets: pd.DataFrame,
    income: pd.DataFrame,
    transactions: pd.DataFrame,
) -> None:
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
    assert not set(wallets["user_id"]) - set(users["user_id"]), "wallets reference unknown users"

    assert (users["account_age_days"] >= min_account_age_days()).all(), (
        "account_age_days shorter than simulated history"
    )
    earners = users[users["monthly_income_base"] > 0]
    assert (earners["monthly_income_base"] > 0).all(), "non-positive income"

    # Referential integrity across all four tables.
    assert not set(income["user_id"]) - set(users["user_id"]), "income references unknown users"
    assert not set(transactions["user_id"]) - set(users["user_id"]), (
        "transactions reference unknown users"
    )
    assert not set(transactions["wallet_id"]) - set(wallets["wallet_id"]), (
        "transactions reference unknown wallets"
    )
    assert not income["income_id"].duplicated().any(), "duplicate income_id"
    assert not transactions["transaction_id"].duplicated().any(), "duplicate transaction_id"

    owner = wallets.set_index("wallet_id")["user_id"].to_dict()
    mismatched = [
        row.transaction_id
        for row in transactions.itertuples()
        if owner[row.wallet_id] != row.user_id
    ]
    assert not mismatched, f"transaction wallet does not belong to its user: {mismatched[:3]}"

    # Controlled vocabularies.
    assert set(transactions["transaction_type"]) <= set(TRANSACTION_TYPES), "bad transaction_type"
    assert set(transactions["direction"]) <= set(DIRECTIONS), "bad direction"
    assert set(transactions["channel"]) <= set(CHANNELS), "bad channel"
    assert set(transactions["category"]) <= set(TRANSACTION_CATEGORIES), "bad category"
    assert set(transactions["merchant_type"]) <= set(MERCHANT_TYPES), "bad merchant_type"

    valid_subcategories = {
        category: set(subs) for category, subs in TRANSACTION_CATEGORIES.items()
    }
    bad = [
        (row.category, row.subcategory)
        for row in transactions.itertuples()
        if row.subcategory not in valid_subcategories.get(row.category, set())
    ]
    assert not bad, f"subcategory does not belong to its category: {bad[:3]}"

    # Time coherence.
    first = pd.Timestamp(START_DATE)
    last = pd.Timestamp(end_of_history_date()) + pd.Timedelta(days=1)
    for frame, label in ((transactions, "transaction"), (income, "income")):
        assert (frame["timestamp"] >= first).all(), f"{label} before history start"
        assert (frame["timestamp"] < last).all(), f"{label} after history end"

    # Every user must have at least some activity in the window.
    assert len(transactions) > 0, "no transactions generated"
    assert set(transactions["user_id"]) == set(users["user_id"]), (
        "some users have no transactions"
    )
    assert (transactions["amount"] > 0).all(), "non-positive transaction amount"
    assert (income["amount"] >= 0).all(), "negative income"

    # Accounting coherence: balance_after must be a true running balance.
    opening = wallets.set_index("wallet_id")["opening_balance"].to_dict()
    ordered = transactions.sort_values(["wallet_id", "timestamp", "transaction_id"])
    running: dict[str, float] = {}
    drift = 0.0
    for row in ordered.itertuples():
        expected = running.get(row.wallet_id, float(opening[row.wallet_id]))
        signed = row.amount if row.direction == "inflow" else -row.amount
        expected = round(expected + signed, 2)
        drift = max(drift, abs(expected - row.balance_after))
        running[row.wallet_id] = row.balance_after
    assert drift < 0.05, f"balance_after is not a true running balance (drift {drift})"

    # Income must be credited to a wallet exactly once, with the same amount.
    credited = transactions[
        (transactions["direction"] == "inflow") & (transactions["category"] == "transfer")
    ]
    credited_total = float(credited["amount"].sum())
    income_total = float(income["amount"].sum())
    assert abs(credited_total - income_total) < 1.0, (
        f"credited income {credited_total} != income events {income_total}"
    )

    # Cash-outs move money between wallets, so both legs must reconcile.
    cash_rows = transactions[transactions["category"] == "cash"]
    legs = cash_rows.groupby("direction")["amount"].sum()
    assert abs(float(legs.get("outflow", 0.0)) - float(legs.get("inflow", 0.0))) < 1.0, (
        "cash withdrawal and deposit legs do not reconcile"
    )


def report(
    users: pd.DataFrame,
    wallets: pd.DataFrame,
    income: pd.DataFrame,
    transactions: pd.DataFrame,
) -> None:
    counts = users["persona"].value_counts()
    print(f"Generated {len(users)} users")
    print(f"Generated {len(wallets)} wallets")
    print(f"Generated {len(income)} income events")
    print(f"Generated {len(transactions)} transactions")

    print("\nPersona distribution:")
    for persona in PERSONAS:
        share = counts.get(persona, 0) / max(len(users), 1)
        print(f"  {persona:<22} {counts.get(persona, 0):>4}  ({share:6.2%})")

    print("\nWallets per type:")
    print(wallets["wallet_type"].value_counts().to_string())

    frame = transactions.merge(users[["user_id", "persona"]], on="user_id")

    # A cash-out is an internal transfer (upay wallet -> cash wallet), not
    # consumption. The spending it funds is already recorded against the cash
    # wallet, so counting both would double-count the same money.
    transfers = frame["category"] == "cash"
    outflows = frame[(frame["direction"] == "outflow") & ~transfers]
    inflows = frame[frame["direction"] == "inflow"]

    summary = outflows.groupby("persona").agg(
        txns=("amount", "size"),
        spend=("amount", "sum"),
        cash_share=("cash_out", "mean"),
    )
    summary["spend_per_txn"] = (summary["spend"] / summary["txns"]).round(0)
    income_by_persona = inflows.groupby("persona")["amount"].sum()
    summary["income"] = income_by_persona.reindex(summary.index).fillna(0).round(0)
    summary["spend_per_income"] = (summary["spend"] / summary["income"]).round(2)

    print("\nBehaviour by persona (BDT):")
    print(
        summary[["txns", "spend", "spend_per_txn", "income", "spend_per_income", "cash_share"]]
        .to_string()
    )

    late = outflows.assign(late=outflows["timestamp"].dt.day >= 23)
    print("\nLate-month share of spending (day >= 23):")
    print(late.groupby("persona")["late"].mean().round(3).sort_values(ascending=False).to_string())

    print("\nCategory mix (top 8):")
    print(outflows["category"].value_counts().head(8).to_string())

    print(f"\nHistory window: {START_DATE} to {end_of_history_date()} ({MONTHS} months)")
    print(f"Seed: {SEED}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    months = month_starts()

    users = generate_users(NUM_USERS)
    wallets = generate_wallets(users)
    income = generate_all_income(users, months)
    transactions = generate_transactions(users, wallets, income, months)

    validate(users, wallets, income, transactions)

    users.to_csv(OUTPUT_DIR / "users.csv", index=False)
    wallets.to_csv(OUTPUT_DIR / "wallets.csv", index=False)
    income.to_csv(OUTPUT_DIR / "income_events.csv", index=False)
    transactions.to_csv(OUTPUT_DIR / "transactions.csv", index=False)

    report(users, wallets, income, transactions)


if __name__ == "__main__":
    main()