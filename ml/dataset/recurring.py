"""Recurring expense definitions (Step 6).

Recurring obligations are defined once per user and are the *source* of the
corresponding monthly transactions, so the
``recurring_expenses -> expected payment -> actual transaction`` chain holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .config import (
    PERSONA_RECURRING,
    RECURRING_CATALOG,
    RECURRING_RELIABILITY,
    SEASONALITY,
)


@dataclass
class RecurringExpense:
    """One standing obligation for a user."""

    recurring_id: str
    user_id: str
    expense_name: str
    category: str
    amount: float
    frequency: str
    next_due_date: date
    mandatory: bool
    due_day: int


def build_recurring_expenses(
    rng: np.random.Generator, users: pd.DataFrame, last_month: pd.Timestamp
) -> pd.DataFrame:
    """Define 1-5 standing obligations per user, scaled to their income."""
    records: list[RecurringExpense] = []
    # next_due_date is the first due date after the simulated window.
    next_month = last_month + pd.offsets.MonthBegin(1)

    for user in users.itertuples():
        income = float(user.monthly_income_base)
        names = PERSONA_RECURRING[user.persona]
        n_obligations = int(rng.integers(1, min(len(names), 5) + 1))
        chosen = list(rng.choice(names, size=n_obligations, replace=False))

        for name in chosen:
            spec = RECURRING_CATALOG[name]

            if name == "rent" and user.occupation == "student":
                continue

            if "fraction_of_income" in spec:
                low, high = spec["fraction_of_income"]
                amount = round(float(rng.uniform(low, high)) * max(income, 10_000.0), 2)
            else:
                low, high = spec["absolute"]
                amount = round(float(rng.uniform(low, high)), 2)

            due_day = int(rng.integers(2, 28))
            next_due = next_month.replace(day=min(due_day, next_month.days_in_month))

            records.append(RecurringExpense(
                recurring_id=f"R{len(records) + 1:05d}",
                user_id=user.user_id,
                expense_name=name,
                category=spec["category"],
                amount=amount,
                frequency="monthly",
                next_due_date=next_due.date(),
                mandatory=bool(spec["mandatory"]),
                due_day=due_day,
            ))

    frame = pd.DataFrame([record.__dict__ for record in records])
    if frame.empty:
        return frame
    return frame.sort_values(["user_id", "due_day"]).reset_index(drop=True)


def monthly_payment_plan(
    rng: np.random.Generator,
    user,
    recurring: pd.DataFrame,
    month: pd.Timestamp,
) -> list[dict]:
    """Decide whether and when each standing obligation is paid this month."""
    reliability = RECURRING_RELIABILITY[user.persona]
    miss_rate, pay_rate = reliability
    seasonal = SEASONALITY.get(month.month, 1.0)

    plan: list[dict] = []
    dim = month.days_in_month

    for obligation in recurring.itertuples():
        if obligation.expense_name == "electricity":
            # Utility bills move with the season.
            amount = obligation.amount * seasonal * float(rng.normal(1.0, 0.06))
        else:
            amount = obligation.amount * float(rng.normal(1.0, 0.03))

        amount = round(max(amount, 20.0), 2)

        paid = bool(rng.random() < pay_rate)
        if not paid:
            # A missed bill may still be paid late within the month.
            paid = bool(rng.random() < (1.0 - miss_rate) * 0.5)

        if not paid:
            continue

        jitter = int(rng.integers(-2, 3))
        day = int(np.clip(obligation.due_day + jitter, 1, dim))

        plan.append({
            "recurring_id": obligation.recurring_id,
            "expense_name": obligation.expense_name,
            "subcategory": obligation.expense_name,
            "category": obligation.category,
            "amount": amount,
            "day": day,
            "due_day": obligation.due_day,
            "mandatory": obligation.mandatory,
        })

    return plan