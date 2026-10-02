"""Transaction ledger generation (Steps 5 and 8).

The ledger is double-entry per wallet: income credits the upay wallet, cash-outs
move money from upay into the cash wallet, and spending debits whichever wallet
funded it. ``balance_after`` is a true running balance and never goes negative,
because Step 5 forbids an overdraft.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    ANOMALY_KINDS,
    CATEGORY_TICKET_FRACTION,
    PERSONA_TRANSACTION_COUNT,
    TRANSACTION_CATEGORIES,
)
from .recurring import monthly_payment_plan

DISCRETE_CATEGORIES = [
    c for c in TRANSACTION_CATEGORIES if c not in ("housing", "cash", "transfer", "other")
]


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


def sample_day(rng: np.random.Generator, persona: str, dim: int) -> int:
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

    return int(rng.choice(days, p=weights / weights.sum()))


def generate_transactions(
    rng: np.random.Generator,
    users: pd.DataFrame,
    wallets: pd.DataFrame,
    income: pd.DataFrame,
    recurring: pd.DataFrame,
    months: list[pd.Timestamp],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate the transaction log and the injected-pattern ground truth.

    Returns ``(transactions, patterns)`` where ``patterns`` records exactly
    what was deliberately injected, per user and month.
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
             pair_id=None, recurring_id=None, is_anomaly=False, pattern_kind=None):
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
            "recurring_id": recurring_id,
            "is_anomaly": is_anomaly,
            "pattern_kind": pattern_kind,
            "_order": order,
            "_pair_id": pair_id,
        })

    income_groups = {uid: grp for uid, grp in income.groupby("user_id")}
    recurring_groups = (
        {uid: grp for uid, grp in recurring.groupby("user_id")} if len(recurring) else {}
    )

    for user in users.itertuples():
        user_id = user.user_id
        persona = user.persona
        primary_wallet = wallet_map[user_id]
        cash_wallet = cash_map.get(user_id)
        income_base = float(user.monthly_income_base)
        expense_ratio = float(user.expense_ratio)
        cash_out_rate = float(user.cash_out_rate)
        anomaly_rate = float(user.anomaly_rate)
        digital_ratio = float(user.digital_ratio)

        obligations = recurring_groups.get(user_id)
        obligations = (
            obligations if obligations is not None and len(obligations)
            else recurring.iloc[0:0]
        )

        category_weights = persona_category_weights(persona)
        category_probs = np.array(
            [category_weights[c] for c in DISCRETE_CATEGORIES], dtype=float
        )
        category_probs = category_probs / category_probs.sum()
        low_count, high_count = PERSONA_TRANSACTION_COUNT[persona]

        cash_available = opening_by_wallet.get(cash_wallet, 0.0) if cash_wallet else 0.0

        for month in months:
            month_end = month + pd.offsets.MonthBegin(1)
            dim = month.days_in_month

            group = income_groups.get(user_id)
            if group is not None and len(group):
                month_events = group[
                    (group["timestamp"] >= month) & (group["timestamp"] < month_end)
                ].sort_values("timestamp")
            else:
                month_events = income.iloc[0:0]

            month_income = float(month_events["amount"].sum()) if len(month_events) else 0.0

            bills = monthly_payment_plan(rng, user, obligations, month)
            fixed_total = float(sum(bill["amount"] for bill in bills))

            pool_multiplier = float(rng.uniform(0.92, 1.08))
            discretionary_budget = max(
                (month_income * expense_ratio - fixed_total) * pool_multiplier,
                month_income * 0.15,
                500.0,
            )
            count = int(rng.integers(low_count, high_count + 1))

            draft = []
            for _ in range(count):
                category = str(rng.choice(DISCRETE_CATEGORIES, p=category_probs))
                ticket = max(
                    CATEGORY_TICKET_FRACTION[category] * max(income_base, 6_000.0), 25.0
                )
                amount = float(rng.lognormal(mean=np.log(ticket), sigma=0.55))
                draft.append((category, amount, sample_day(rng, persona, dim)))

            drawn_total = float(sum(item[1] for item in draft))
            scale = (discretionary_budget / drawn_total) if drawn_total > 0 else 1.0

            planned: list[dict] = []

            for bill in bills:
                planned.append({
                    "timestamp": month + pd.Timedelta(
                        days=bill["day"] - 1,
                        hours=int(rng.integers(8, 21)),
                        minutes=int(rng.integers(0, 60)),
                    ),
                    "category": bill["category"],
                    "amount": bill["amount"],
                    "type": "bill_payment"
                    if bill["category"] in ("utilities", "communication") else "payment",
                    "subcategory": bill["subcategory"],
                    "recurring_id": bill["recurring_id"],
                    "is_anomaly": False,
                })

            for category, amount, day in draft:
                planned.append({
                    "timestamp": month + pd.Timedelta(
                        days=day - 1,
                        hours=int(rng.integers(6, 23)),
                        minutes=int(rng.integers(0, 60)),
                    ),
                    "category": category,
                    "amount": round(max(amount * scale, 20.0), 2),
                    "type": "payment",
                    "subcategory": None,
                    "recurring_id": None,
                    "is_anomaly": False,
                })

            # Injected anomalies (Step 8): rare, large, and explicitly labelled.
            if rng.random() < anomaly_rate:
                n_shocks = int(rng.integers(1, 4))
                for _ in range(n_shocks):
                    kind = str(rng.choice(ANOMALY_KINDS))
                    if kind == "duplicate_charge":
                        category = str(rng.choice(["shopping", "food", "entertainment"]))
                        amount = round(float(rng.uniform(0.15, 0.45)) * max(month_income, 4_000.0), 2)
                    elif kind == "unusual_merchant":
                        category = "other"
                        amount = round(float(rng.uniform(0.10, 0.35)) * max(month_income, 4_000.0), 2)
                    elif kind == "round_number_spike":
                        category = str(rng.choice(["shopping", "other"]))
                        amount = round(float(rng.uniform(0.20, 0.60)) * max(month_income, 5_000.0), 2)
                    else:
                        category = str(rng.choice(["health", "family", "other"], p=[0.45, 0.40, 0.15]))
                        amount = round(
                            float(rng.uniform(0.25, 0.85)) * max(month_income, 5_000.0), 2
                        )

                    planned.append({
                        "timestamp": month + pd.Timedelta(
                            days=int(rng.integers(1, dim + 1)) - 1,
                            hours=int(rng.integers(9, 22)),
                            minutes=int(rng.integers(0, 60)),
                        ),
                        "category": category,
                        "amount": amount,
                        "type": "payment",
                        "subcategory": str(rng.choice(TRANSACTION_CATEGORIES[category])),
                        "recurring_id": None,
                        "is_anomaly": True,
                        "pattern_kind": kind,
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
                    "recurring_id": None,
                    "is_anomaly": False,
                    "is_income": True,
                })
            for item in planned:
                timeline.append({**item, "is_income": False})
            timeline.sort(key=lambda item: item["timestamp"])

            n_cashouts = int(rng.binomial(6, cash_out_rate)) if cash_wallet else 0
            cash_schedule: dict[int, float] = {}
            if n_cashouts:
                share = float(rng.uniform(0.20, 0.55))
                per_cashout = round(discretionary_budget * share / n_cashouts, 2)
                for _ in range(n_cashouts):
                    day = int(rng.integers(1, dim + 1))
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
                         amount, "transfer", item["subcategory"], "person", "bank",
                         False, 0)
                    continue

                subcategory = item["subcategory"] or str(
                    rng.choice(TRANSACTION_CATEGORIES[category])
                )
                funded_by_cash = (
                    cash_wallet is not None
                    and cash_available >= amount
                    and rng.random() < (1.0 - digital_ratio)
                )
                wallet_id = cash_wallet if funded_by_cash else primary_wallet

                if funded_by_cash:
                    channel, merchant_type = "agent", "agent"
                elif item["recurring_id"] is not None or category in ("utilities", "communication"):
                    channel, merchant_type = "upay", "utility"
                elif category == "shopping":
                    channel = "online" if rng.random() < 0.35 else "upay"
                    merchant_type = "ecommerce" if channel == "online" else "merchant"
                else:
                    channel, merchant_type = "upay", "merchant"

                if funded_by_cash:
                    cash_available -= amount

                emit(user_id, wallet_id, timestamp, item["type"], "outflow",
                     amount, category, subcategory, merchant_type, channel,
                     funded_by_cash, 0,
                     recurring_id=item["recurring_id"],
                     is_anomaly=item["is_anomaly"],
                     pattern_kind=item.get("pattern_kind"))

    transactions = replay_ledger(events, opening_by_wallet)

    # Derive ground truth from the rows that actually survived the ledger
    # replay, so injected_patterns can never reference a dropped transaction.
    pattern_columns = [
        "user_id", "period", "pattern_type", "amount", "category", "timestamp",
    ]
    anomalies = transactions[transactions["is_anomaly"]]
    if len(anomalies):
        pattern_frame = anomalies[["user_id", "timestamp", "category", "amount"]].copy()
        pattern_frame["period"] = pattern_frame["timestamp"].dt.strftime("%Y-%m")
        pattern_frame["pattern_type"] = [
            kind or "large_unplanned_charge" for kind in anomalies["pattern_type"]
        ]
        pattern_frame = pattern_frame[pattern_columns].reset_index(drop=True)
    else:
        pattern_frame = pd.DataFrame(columns=pattern_columns)

    return transactions, pattern_frame


def replay_ledger(events: list[dict], opening_by_wallet: dict[str, float]) -> pd.DataFrame:
    """Replay events chronologically and compute exact running balances.

    A purchase that cannot be funded is dropped rather than allowed to push the
    wallet negative, because Step 5 requires ``balance_after >= 0``.
    """
    events.sort(key=lambda e: (e["user_id"], e["timestamp"], e["_order"], e["amount"]))

    balances = dict(opening_by_wallet)
    rows: list[dict] = []
    row_index: dict[str, int] = {}
    skipped = 0

    for event in events:
        wallet_id = event["wallet_id"]
        amount = event["amount"]
        direction = event["direction"]
        balance = balances[wallet_id]
        signed = amount if direction == "inflow" else -amount

        if direction == "outflow" and balance - amount < 0:
            skipped += 1
            continue

        pair_id = event["_pair_id"]
        if pair_id is not None and direction == "inflow" and pair_id not in row_index:
            # Its matching withdrawal was dropped for lack of funds.
            skipped += 1
            continue

        new_balance = round(balance + signed, 2)
        balances[wallet_id] = new_balance

        position = len(rows)
        rows.append({
            "transaction_id": f"T{position + 1:08d}",
            "user_id": event["user_id"],
            "wallet_id": wallet_id,
            "timestamp": event["timestamp"],
            "transaction_type": event["transaction_type"],
            "direction": direction,
            "amount": amount,
            "category": event["category"],
            "subcategory": event["subcategory"],
            "merchant_type": event["merchant_type"],
            "channel": event["channel"],
            "cash_out": event["cash_out"],
            "balance_after": new_balance,
            "recurring_id": event["recurring_id"],
            "is_anomaly": event["is_anomaly"],
            "pattern_type": event["pattern_kind"] or "",
        })
        if pair_id is not None:
            row_index[pair_id] = position

    print(f"  unaffordable purchases skipped (wallet would go negative): {skipped}")

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["cash_out"] = frame["cash_out"].astype(bool)
        frame["is_anomaly"] = frame["is_anomaly"].astype(bool)
        return frame

    return pd.DataFrame(
        columns=[
            "transaction_id", "user_id", "wallet_id", "timestamp", "transaction_type",
            "direction", "amount", "category", "subcategory", "merchant_type",
            "channel", "cash_out", "balance_after", "recurring_id", "is_anomaly",
            "pattern_type",
        ]
    )