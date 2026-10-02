"""Configuration and ground-truth definitions for synthetic data generation.

All tunable knobs live here so the generator, the validators and the tests
agree on one definition of the simulated world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SEED = 42

NUM_USERS = 500
MONTHS = 9
START_DATE = date(2026, 1, 1)

OUTPUT_DIR = "data/generated"
SPLIT_DIRS = {
    "train": "data/train",
    "validation": "data/validation",
    "test": "data/test",
}

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
    "health": ["medicine", "doctor", "pharmacy", "insurance"],
    "utilities": ["electricity", "internet", "water"],
    "communication": ["mobile_recharge", "internet"],
    "entertainment": ["movies", "games", "events", "subscription"],
    "family": ["family_support", "gift"],
    "housing": ["rent", "maintenance"],
    "cash": ["cash_out"],
    "transfer": ["salary", "business", "freelance", "allowance", "send_money", "receive_money"],
    "other": ["misc"],
}

TRANSACTION_TYPES = [
    "payment",
    "cash_out",
    "cash_in",
    "send_money",
    "receive_money",
    "transfer",
    "bill_payment",
    "mobile_recharge",
    "bank_transfer",
]

DIRECTIONS = ["inflow", "outflow"]

CHANNELS = ["upay", "agent", "merchant", "bank", "online"]

MERCHANT_TYPES = ["merchant", "agent", "ecommerce", "utility", "person"]

WALLET_TYPES = ["upay", "bank", "cash", "other_digital"]

OCCUPATION_INCOME_PROFILE = {
    "student": ("allowance", "family", "irregular"),
    "private_employee": ("salary", "employer", "regular"),
    "business": ("business", "own_business", "seasonal"),
    "freelancer": ("freelance", "freelance_client", "irregular"),
    "self_employed": ("business", "own_business", "irregular"),
    "other": ("salary", "employer", "regular"),
}

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

# ---------------------------------------------------------------------------
# Recurring expenses (Step 6)
# ---------------------------------------------------------------------------

RECURRING_CATALOG = {
    "rent": {"category": "housing", "fraction_of_income": (0.18, 0.34), "mandatory": True},
    "electricity": {"category": "utilities", "absolute": (400.0, 2_800.0), "mandatory": True},
    "internet": {"category": "communication", "absolute": (500.0, 2_000.0), "mandatory": True},
    "mobile_recharge": {
        "category": "communication", "absolute": (100.0, 900.0), "mandatory": True,
    },
    "tuition": {"category": "education", "absolute": (1_200.0, 9_000.0), "mandatory": True},
    "medicine": {"category": "health", "absolute": (500.0, 4_500.0), "mandatory": True},
    "family_support": {
        "category": "family", "absolute": (1_500.0, 5_000.0), "mandatory": True,
    },
    "subscription": {
        "category": "entertainment", "absolute": (300.0, 1_500.0), "mandatory": False,
    },
    "insurance": {"category": "health", "absolute": (800.0, 4_000.0), "mandatory": True},
}

# Which recurring obligations each persona carries, in priority order.
PERSONA_RECURRING = {
    "stable_saver": ["rent", "electricity", "internet", "mobile_recharge", "insurance"],
    "end_month_shortage": ["rent", "electricity", "internet", "mobile_recharge", "subscription"],
    "irregular_income": ["rent", "electricity", "mobile_recharge", "subscription"],
    "high_cash_dependency": ["rent", "electricity", "mobile_recharge", "medicine"],
    "goal_oriented": ["rent", "electricity", "internet", "mobile_recharge", "tuition"],
    "seasonal_spender": ["rent", "electricity", "internet", "mobile_recharge", "subscription"],
    "sudden_anomaly": ["rent", "electricity", "internet", "mobile_recharge", "medicine"],
    "financial_pressure": ["rent", "electricity", "mobile_recharge", "medicine"],
}

# Payment jitter and missed-payment behaviour per persona.
RECURRING_RELIABILITY = {
    "stable_saver": (0.02, 0.99),
    "end_month_shortage": (0.10, 0.95),
    "irregular_income": (0.14, 0.94),
    "high_cash_dependency": (0.06, 0.97),
    "goal_oriented": (0.03, 0.99),
    "seasonal_spender": (0.07, 0.96),
    "sudden_anomaly": (0.09, 0.96),
    "financial_pressure": (0.18, 0.90),
}

# ---------------------------------------------------------------------------
# Goals (Step 7)
# ---------------------------------------------------------------------------

GOAL_TYPES = ["emergency_fund", "education", "laptop", "phone", "travel", "family", "other"]

GOAL_PRIORITIES = ["high", "medium", "low"]

PERSONA_GOAL_COUNT = {
    "stable_saver": (1, 2),
    "end_month_shortage": (0, 1),
    "irregular_income": (0, 1),
    "high_cash_dependency": (0, 1),
    "goal_oriented": (2, 3),
    "seasonal_spender": (0, 1),
    "sudden_anomaly": (1, 2),
    "financial_pressure": (0, 1),
}

# Share of the monthly surplus a persona diverts into goals.
PERSONA_GOAL_SHARE = {
    "stable_saver": (0.15, 0.35),
    "end_month_shortage": (0.0, 0.08),
    "irregular_income": (0.0, 0.10),
    "high_cash_dependency": (0.0, 0.08),
    "goal_oriented": (0.35, 0.60),
    "seasonal_spender": (0.0, 0.08),
    "sudden_anomaly": (0.10, 0.25),
    "financial_pressure": (0.0, 0.03),
}

GOAL_TARGET_FRACTION = {
    "emergency_fund": (2.0, 4.0),
    "education": (2.0, 6.0),
    "laptop": (0.8, 2.0),
    "phone": (0.4, 1.2),
    "travel": (1.0, 2.5),
    "family": (1.5, 4.0),
    "other": (0.5, 2.0),
}

GOAL_MONTHS_TO_TARGET = {
    "emergency_fund": (6, 14),
    "education": (6, 18),
    "laptop": (3, 9),
    "phone": (2, 6),
    "travel": (4, 12),
    "family": (4, 12),
    "other": (2, 8),
}

# ---------------------------------------------------------------------------
# Cash-in / cash-out behaviour (mobile financial services)
#
# Cash handling is one of the most frequent things a user does: salary comes
# into the upay wallet, then most of it is cashed out and spent physically.
# The persona rate is the per-month probability of each cash-out event, so
# cash-heavy personas produce many more pairs.
# ---------------------------------------------------------------------------

CASH_OUT_EVENTS_PER_MONTH = {
    "stable_saver": (1, 3),
    "end_month_shortage": (2, 5),
    "irregular_income": (2, 6),
    "high_cash_dependency": (6, 14),
    "goal_oriented": (1, 4),
    "seasonal_spender": (2, 5),
    "sudden_anomaly": (2, 5),
    "financial_pressure": (3, 7),
}

# Share of the month's spending budget moved into physical cash.
CASH_OUT_SHARE = (0.30, 0.75)

# How often the leftover cash is brought back into the digital wallet.
CASH_IN_PERIODS = ("month_start", "payday", "random")

# ---------------------------------------------------------------------------
# User to user transfers ("send money", upay id to upay id)
#
# Every send produces two linked ledger rows: a send_money outflow on the
# sender's upay wallet and a receive_money inflow on the receiver's upay
# wallet. These are excluded from income and consumption aggregates because
# moving money between people is neither earning nor spending.
# ---------------------------------------------------------------------------

# Expected user-to-user sends per user per month, before the persona multiplier.
P2P_SENDS_PER_USER_MONTH = (0.3, 2.2)

# A sender cannot send to themselves, so this is the fraction of the population
# that takes part in transfers at all.
P2P_ACTIVE_SHARE = (0.35, 0.75)

# Transfer size as a fraction of the sender's monthly income.
P2P_AMOUNT_FRACTION = (0.01, 0.18)

# upay charges a fee on send money: a small flat fee plus a percentage.
P2P_FEE_FLAT = (2.0, 15.0)
P2P_FEE_PERCENT = (0.001, 0.006)

# Sending is more common for some personas than others.
PERSONA_P2P_RATE = {
    "stable_saver": 1.00,
    "end_month_shortage": 1.15,
    "irregular_income": 1.05,
    "high_cash_dependency": 1.30,
    "goal_oriented": 1.20,
    "seasonal_spender": 1.35,
    "sudden_anomaly": 0.95,
    "financial_pressure": 1.40,
}

# Transaction types that move money without being income or consumption.
TRANSFER_TYPES = {"send_money", "receive_money"}

# ---------------------------------------------------------------------------
# Seasonality and anomalies (Step 8)
# ---------------------------------------------------------------------------

# Plausible seasonal spending pressure by calendar month (1-12).
# Documented as a modelling assumption, not a verified calendar.
SEASONALITY = {
    1: 1.05,   # year-end / winter
    2: 0.95,
    3: 1.35,   # Eid al-Fitr spending
    4: 1.05,
    5: 0.95,
    6: 1.00,
    7: 1.05,
    8: 1.00,
    9: 0.95,
    10: 1.00,
    11: 0.95,
    12: 1.15,
}

ANOMALY_KINDS = [
    "large_unplanned_charge",
    "unusual_merchant",
    "duplicate_charge",
    "round_number_spike",
]


@dataclass(frozen=True)
class PersonaProfile:
    """Behavioural knobs for one ground-truth persona."""

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

# ---------------------------------------------------------------------------
# Behaviour label thresholds (Step 9)
# These produce the ground-truth labels in behavior_labels.csv.
# They are rule-based and derived only from information available up to the
# end of each period, so the labels can never encode the future.
# ---------------------------------------------------------------------------

LABEL_THRESHOLDS = {
    "late_month_share": 0.40,
    "cash_dependency_share": 0.40,
    "income_cv": 0.35,
    "savings_rate": 0.05,
    "expense_income_ratio": 1.0,
    "goal_contribution_min": 1.0,
    "anomaly_zscore": 3.0,
    "min_months_active": 3,
}