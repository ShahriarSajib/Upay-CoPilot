"""Transaction ledger generation (Steps 5 and 8).

The ledger is double entry. Every movement is recorded on exactly one wallet, so
``opening_balance + inflows - outflows = balance_after`` holds per wallet with
no negative balance, because Step 5 forbids overdrafting and there is no credit
facility.

Three kinds of movement move money *between* wallets and are recorded as two
linked rows sharing a ``related_transaction_id``:

- cash out / cash in (same user, upay wallet to cash wallet)
- send money / receive money (different users, upay wallet to upay wallet)

Everything else is a single row against one wallet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    ANOMALY_KINDS,
    CASH_OUT_EVENTS_PER_MONTH,
    CASH_OUT_SHARE,
    CATEGORY_TICKET_FRACTION,
    P2P_ACTIVE_SHARE,
    P2P_AMOUNT_FRACTION,
    P2P_FEE_FLAT,
    P2P_FEE_PERCENT,
    P2P_SENDS_PER_USER_MONTH,
    PERSONA_P2P_RATE,
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


def _random_timestamp(rng: np.random.Generator, month: pd.Timestamp) -> pd.Timestamp:
    return month + pd.Timedelta(
        days=int(rng.integers(0, month.days_in_month)),
        hours=int(rng.integers(6, 23)),
        minutes=int(rng.integers(0, 60)),
    )


def generate_transactions(
    rng: np.random.Generator,
    users: pd.DataFrame,
    wallets: pd.DataFrame,
    income: pd.DataFrame,
    recurring: pd.DataFrame,
    months: list[pd.Timestamp],
    volume_scale: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate the transaction log and the injected-pattern ground truth.

    Returns ``(transactions, patterns, wallets)``. The wallet frame is returned
    because cash wallets are added here for any user who lacked one, since a
    user with no cash wallet could not have any cash activity.
    """
    upay_wallet = (
        wallets[wallets["wallet_type"] == "upay"].set_index("user_id")["wallet_id"].to_dict()
    )
    cash_wallet_of = (
        wallets[wallets["wallet_type"] == "cash"].set_index("user_id")["wallet_id"].to_dict()
    )

    events: list[dict] = []
    pair_counter = 0
    cash_available: dict[str, float] = {}

    def next_pair_id(prefix: str) -> str:
        nonlocal pair_counter
        pair_counter += 1
        return f"{prefix}{pair_counter:08d}"

    def emit(
        user_id,
        wallet_id,
        timestamp,
        transaction_type,
        direction,
        amount,
        category,
        subcategory,
        merchant_type,
        channel,
        cash_out_flag,
        order,
        pair_id=None,
        pair_role=None,
        cross_user=False,
        recurring_id=None,
        income_event_id=None,
        is_anomaly=False,
        pattern_kind=None,
        fee_amount=0.0,
    ):
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
            "income_event_id": income_event_id,
            "is_anomaly": is_anomaly,
            "pattern_kind": pattern_kind,
            "fee_amount": round(float(fee_amount), 2),
            "pair_id": pair_id,
            "pair_role": pair_role,
            "cross_user": cross_user,
            "_order": order,
        })

    income_groups = {uid: grp for uid, grp in income.groupby("user_id")}
    recurring_groups = (
        {uid: grp for uid, grp in recurring.groupby("user_id")} if len(recurring) else {}
    )
    opening_by_wallet = {
        row.wallet_id: float(row.opening_balance) for row in wallets.itertuples()
    }

    # Cash is the everyday medium for a large share of spending, so virtually
    # every user needs a cash wallet. Without one they could have no cash
    # activity at all.
    added_wallets: list[dict] = []
    for user in users.itertuples():
        if user.user_id in cash_wallet_of:
            continue
        opening = round(
            opening_by_wallet[upay_wallet[user.user_id]] * float(rng.uniform(0.05, 0.25)), 2
        )
        cash_id = f"CW{user.user_id[1:]}"
        added_wallets.append({
            "wallet_id": cash_id,
            "user_id": user.user_id,
            "wallet_type": "cash",
            "opening_balance": opening,
        })
        opening_by_wallet[cash_id] = opening
        cash_wallet_of[user.user_id] = cash_id

    if added_wallets:
        wallets = pd.concat([wallets, pd.DataFrame(added_wallets)], ignore_index=True)

    for user in users.itertuples():
        cash_wallet = cash_wallet_of.get(user.user_id)
        cash_available[user.user_id] = opening_by_wallet.get(cash_wallet, 0.0)

    # ------------------------------------------------------------------
    # Per user, per month: income, bills, discretionary spend, anomalies
    # ------------------------------------------------------------------
    for user in users.itertuples():
        user_id = user.user_id
        persona = user.persona
        primary_wallet = upay_wallet[user_id]
        cash_wallet = cash_wallet_of.get(user_id)
        income_base = float(user.monthly_income_base)
        expense_ratio = float(user.expense_ratio)
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
        if volume_scale != 1.0:
            # Scaling the persona band keeps the persona ordering intact while
            # letting a small population stay inside a row budget. At least two
            # transactions per month is the floor below which recurring bills
            # and payday cash-outs stop being representable.
            low_count = max(2, round(low_count * volume_scale))
            high_count = max(low_count + 1, round(high_count * volume_scale))

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
                for _ in range(int(rng.integers(1, 4))):
                    kind = str(rng.choice(ANOMALY_KINDS))
                    if kind == "duplicate_charge":
                        category = str(rng.choice(["shopping", "food", "entertainment"]))
                        amount = round(
                            float(rng.uniform(0.15, 0.45)) * max(month_income, 4_000.0), 2
                        )
                    elif kind == "unusual_merchant":
                        category = "other"
                        amount = round(
                            float(rng.uniform(0.10, 0.35)) * max(month_income, 4_000.0), 2
                        )
                    elif kind == "round_number_spike":
                        category = str(rng.choice(["shopping", "other"]))
                        amount = round(
                            float(rng.uniform(0.20, 0.60)) * max(month_income, 5_000.0), 2
                        )
                    else:
                        category = str(
                            rng.choice(["health", "family", "other"], p=[0.45, 0.40, 0.15])
                        )
                        amount = round(
                            float(rng.uniform(0.25, 0.85)) * max(month_income, 5_000.0), 2
                        )

                    planned.append({
                        "timestamp": _random_timestamp(rng, month),
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
                timeline.append({
                    "timestamp": event.timestamp,
                    "category": "transfer",
                    "amount": float(event.amount),
                    "type": "transfer",
                    "subcategory": event.income_type,
                    "recurring_id": None,
                    "income_event_id": event.income_id,
                    "is_anomaly": False,
                    "is_income": True,
                })
            for item in planned:
                timeline.append({**item, "is_income": False})
            timeline.sort(key=lambda item: item["timestamp"])

            # Cash-outs: salary arrives in the upay wallet, then most of it is
            # drawn out and spent physically. This is one of the highest volume
            # behaviours in a real mobile money account.
            cash_plan: dict[int, float] = {}
            if cash_wallet:
                lo, hi = CASH_OUT_EVENTS_PER_MONTH[persona]
                n_cashouts = int(rng.integers(lo, hi + 1))

                cash_cap = max(discretionary_budget, 500.0) * 1.2
                headroom = max(cash_cap - cash_available[user_id], 0.0)
                desired = discretionary_budget * float(rng.uniform(*CASH_OUT_SHARE))
                total = min(desired, headroom)

                if n_cashouts > 0 and total >= 50.0:
                    weights = rng.dirichlet(np.ones(n_cashouts) * 2.0)
                    chosen_days = rng.choice(np.arange(1, dim + 1), size=n_cashouts, replace=False)
                    for day, weight in zip(chosen_days, weights):
                        amount = round(float(total * weight), 2)
                        if amount >= 30.0:
                            cash_plan[int(day)] = amount

            for item in timeline:
                timestamp = item["timestamp"]
                day = timestamp.day
                category = item["category"]
                amount = float(item["amount"])

                if day in cash_plan:
                    withdraw = cash_plan[day]
                    pair_id = next_pair_id("C")
                    cash_ts = timestamp - pd.Timedelta(hours=2)
                    emit(
                        user_id, primary_wallet, cash_ts, "cash_out", "outflow",
                        withdraw, "cash", "cash_out", "agent", "agent", True,
                        0, pair_id=pair_id, pair_role="out",
                    )
                    emit(
                        user_id, cash_wallet, cash_ts, "cash_in", "inflow",
                        withdraw, "cash", "cash_out", "agent", "agent", True,
                        1, pair_id=pair_id, pair_role="in",
                    )
                    cash_available[user_id] += withdraw

                if item["is_income"]:
                    emit(
                        user_id, primary_wallet, timestamp, "transfer", "inflow",
                        amount, "transfer", item["subcategory"], "person", "bank",
                        False, 0, income_event_id=item["income_event_id"],
                    )
                    continue

                subcategory = item["subcategory"] or str(
                    rng.choice(TRANSACTION_CATEGORIES[category])
                )
                funded_by_cash = (
                    cash_wallet is not None
                    and cash_available[user_id] >= amount
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
                    cash_available[user_id] -= amount

                emit(
                    user_id, wallet_id, timestamp, item["type"], "outflow",
                    amount, category, subcategory, merchant_type, channel,
                    funded_by_cash, 0,
                    recurring_id=item["recurring_id"],
                    is_anomaly=item["is_anomaly"],
                    pattern_kind=item.get("pattern_kind"),
                )

    # ------------------------------------------------------------------
    # User to user transfers: "send money", upay id to upay id
    # ------------------------------------------------------------------
    user_ids = list(users["user_id"])
    income_base = dict(zip(users["user_id"], users["monthly_income_base"]))
    persona_of = dict(zip(users["user_id"], users["persona"]))

    # Sends scale with the population, not with the number of months.
    lo, hi = P2P_SENDS_PER_USER_MONTH
    population = len(user_ids)

    for month in months:
        expected = population * float(rng.uniform(lo, hi))
        for _ in range(int(rng.poisson(expected))):
            sender, receiver = rng.choice(user_ids, size=2, replace=False)
            if rng.random() > PERSONA_P2P_RATE[persona_of[sender]]:
                continue
            if rng.random() > float(rng.uniform(*P2P_ACTIVE_SHARE)):
                continue

            fraction = float(rng.uniform(*P2P_AMOUNT_FRACTION))
            sender_income = float(income_base[sender])
            amount = round(fraction * max(sender_income, 3_000.0), 2)
            if amount < 50.0 or amount > sender_income * 0.9:
                continue

            fee = round(
                amount * float(rng.uniform(*P2P_FEE_PERCENT))
                + float(rng.uniform(*P2P_FEE_FLAT)),
                2,
            )
            pair_id = next_pair_id("P")
            timestamp = _random_timestamp(rng, month)

            # Sender is debited the amount plus the transfer fee; the receiver
            # only ever gets the amount, so the fee leaves the system.
            emit(
                sender, upay_wallet[sender], timestamp, "send_money", "outflow",
                amount + fee, "transfer", "send_money", "person", "upay",
                False, 0, pair_id=pair_id, pair_role="out", cross_user=True,
                fee_amount=fee,
            )
            emit(
                receiver, upay_wallet[receiver], timestamp, "receive_money", "inflow",
                amount, "transfer", "receive_money", "person", "upay",
                False, 1, pair_id=pair_id, pair_role="in", cross_user=True,
            )

    transactions = replay_ledger(events, opening_by_wallet)
    return transactions, _derive_patterns(transactions), wallets


def _derive_patterns(transactions: pd.DataFrame) -> pd.DataFrame:
    """Ground truth read back from the rows that survived the ledger replay."""
    columns = ["user_id", "period", "pattern_type", "amount", "category", "timestamp",
               "transaction_id"]
    anomalies = transactions[transactions["is_anomaly"]]

    if not len(anomalies):
        return pd.DataFrame(columns=columns)

    frame = anomalies[["user_id", "timestamp", "category", "amount", "transaction_id"]].copy()
    frame["period"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame["pattern_type"] = [
        kind or "large_unplanned_charge" for kind in anomalies["pattern_type"]
    ]
    return frame[columns].reset_index(drop=True)


def _replay_user(
    events: list[tuple[int, dict]],
    balances: dict[str, float],
    blocked: set[int] | None = None,
):
    """Replay one user's events, returning balance_after per event index.

    An outflow that the wallet cannot fund is dropped, because Step 5 requires
    ``balance_after >= 0``. Cash pairs are atomic: if the withdrawal fails, the
    matching deposit is dropped with it. Indices in ``blocked`` are permanently
    dropped, which is how a cross-user transfer whose sender could not afford it
    is removed from the receiver's ledger too.
    """
    working = dict(balances)
    kept: dict[int, float] = {}
    pair_ok: dict[str, bool] = {}

    for index, event in events:
        if blocked and index in blocked:
            kept[index] = None
            continue

        pair_id = event["pair_id"]

        if event["pair_role"] == "in" and pair_id is not None and pair_ok.get(pair_id) is False:
            kept[index] = None
            continue

        amount = event["amount"]
        if event["direction"] == "outflow" and working[event["wallet_id"]] - amount < -1e-9:
            kept[index] = None
            if pair_id is not None:
                pair_ok[pair_id] = False
            continue

        signed = amount if event["direction"] == "inflow" else -amount
        working[event["wallet_id"]] = round(working[event["wallet_id"]] + signed, 2)
        kept[index] = working[event["wallet_id"]]

        if pair_id is not None:
            pair_ok[pair_id] = True

    return kept


def replay_ledger(events: list[dict], opening_by_wallet: dict[str, float]) -> pd.DataFrame:
    """Replay all events chronologically and compute exact running balances."""
    events.sort(key=lambda e: (e["user_id"], e["timestamp"], e["_order"], e["amount"]))

    by_user: dict[str, list[tuple[int, dict]]] = {}
    for index, event in enumerate(events):
        by_user.setdefault(event["user_id"], []).append((index, event))

    surviving: dict[int, float] = {}
    dropped = 0

    for user_events in by_user.values():
        balances = {
            event["wallet_id"]: opening_by_wallet[event["wallet_id"]]
            for _, event in user_events
        }
        surviving.update(_replay_user(user_events, balances))

    # A cross-user pair is atomic across users: if the sender could not afford
    # the transfer, the receiver must not receive it either.
    cross_pairs: dict[str, dict[str, int]] = {}
    for index, event in enumerate(events):
        if event["cross_user"] and event["pair_id"] is not None:
            role = "out" if event["pair_role"] == "out" else "in"
            cross_pairs.setdefault(event["pair_id"], {})[role] = index

    blocked: set[int] = set()
    for pair in cross_pairs.values():
        out_index, in_index = pair.get("out"), pair.get("in")
        if out_index is None or in_index is None:
            continue
        if surviving.get(out_index) is None and surviving.get(in_index) is not None:
            blocked.add(in_index)

    # Recompute balances for the receivers who lost an inflow. The blocked index
    # must stay blocked, otherwise the replay would simply recreate it.
    for user_id in {events[index]["user_id"] for index in blocked}:
        user_events = by_user[user_id]
        balances = {
            event["wallet_id"]: opening_by_wallet[event["wallet_id"]]
            for _, event in user_events
        }
        surviving.update(_replay_user(user_events, balances, blocked))

    dropped = sum(1 for value in surviving.values() if value is None)
    print(f"  unaffordable movements skipped (wallet would go negative): {dropped}")

    rows: list[dict] = []
    key_to_id: dict[int, str] = {}
    pair_to_ids: dict[str, list[str]] = {}
    position = 0

    for index, event in enumerate(events):
        balance = surviving.get(index)
        if balance is None:
            continue

        position += 1
        transaction_id = f"T{position:08d}"
        key_to_id[index] = transaction_id
        if event["pair_id"] is not None:
            pair_to_ids.setdefault(event["pair_id"], []).append(transaction_id)

        rows.append({
            "transaction_id": transaction_id,
            "user_id": event["user_id"],
            "wallet_id": event["wallet_id"],
            "timestamp": event["timestamp"],
            "transaction_type": event["transaction_type"],
            "direction": event["direction"],
            "amount": event["amount"],
            "category": event["category"],
            "subcategory": event["subcategory"],
            "merchant_type": event["merchant_type"],
            "channel": event["channel"],
            "cash_out": event["cash_out"],
            "balance_after": balance,
            "related_transaction_id": None,
            "income_event_id": event["income_event_id"],
            "recurring_id": event["recurring_id"],
            "fee_amount": event["fee_amount"],
            "is_anomaly": event["is_anomaly"],
            "pattern_type": event["pattern_kind"] or "",
            "_pair_id": event["pair_id"],
        })

    # Both cash pairs and send-money pairs are linked in both directions.
    for row in rows:
        ids = pair_to_ids.get(row["_pair_id"], [])
        if len(ids) != 2:
            continue
        row["related_transaction_id"] = ids[0] if row["transaction_id"] == ids[1] else ids[1]

    frame = pd.DataFrame(rows).drop(columns=["_pair_id"])
    if not frame.empty:
        frame["cash_out"] = frame["cash_out"].astype(bool)
        frame["is_anomaly"] = frame["is_anomaly"].astype(bool)
    return frame