"""Dataset validation (Steps 11 and 12).

Structural checks confirm the files match their schemas. Ledger checks confirm
the money adds up. Behavioural checks confirm the personas are actually
present in the data rather than only declared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import TRANSACTION_CATEGORIES, TRANSACTION_TYPES


@dataclass
class ValidationReport:
    """Collects pass/fail results for every validation rule."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def check(self, condition: bool, message: str) -> bool:
        if not condition:
            self.errors.append(message)
        return bool(condition)

    def warn(self, condition: bool, message: str) -> bool:
        if not condition:
            self.warnings.append(message)
        return bool(condition)

    def render(self) -> str:
        lines = ["", "=" * 68, "DATASET VALIDATION REPORT", "=" * 68]
        for key, value in self.stats.items():
            lines.append(f"  {key:<46} {value}")

        lines.append("")
        if self.errors:
            lines.append(f"FAILED: {len(self.errors)} error(s)")
            lines.extend(f"  - {error}" for error in self.errors)
        else:
            lines.append("PASSED: all structural, ledger and relationship checks")

        if self.warnings:
            lines.append(f"\n{len(self.warnings)} warning(s):")
            lines.extend(f"  - {warning}" for warning in self.warnings)

        lines.append("=" * 68)
        return "\n".join(lines)


def load_schema(schema_dir: str | Path) -> dict[str, list[str]]:
    """Read the header-only schema files into column lists."""
    schemas: dict[str, list[str]] = {}
    for path in sorted(Path(schema_dir).glob("*.csv")):
        schemas[path.stem] = pd.read_csv(path, nrows=0).columns.tolist()
    return schemas


def check_schema(
    tables: dict[str, pd.DataFrame], schemas: dict[str, list[str]], report: ValidationReport
) -> None:
    for name, expected in schemas.items():
        if name not in tables:
            report.check(False, f"{name}: missing from generated dataset")
            continue

        actual = list(tables[name].columns)
        missing = [column for column in expected if column not in actual]
        if missing:
            report.check(False, f"{name}: missing schema columns {missing}")

    for name in tables:
        if schemas and name not in schemas and not name.startswith("_"):
            report.warn(False, f"{name}: extra table with no schema definition")

    return report


def check_primary_keys(tables: dict[str, pd.DataFrame], report: ValidationReport) -> None:
    keys = {
        "users": "user_id",
        "wallets": "wallet_id",
        "income_events": "income_id",
        "transactions": "transaction_id",
        "recurring_expenses": "recurring_id",
        "financial_goals": "goal_id",
        "goal_contributions": "contribution_id",
        "financial_profiles": "user_id",
    }

    for name, key in keys.items():
        frame = tables.get(name)
        if frame is None or key not in frame.columns:
            continue
        report.check(frame[key].is_unique, f"{name}.{key} is not unique")

    users = tables["users"]
    wallets = tables["wallets"]
    report.check(
        len(users) == users["user_id"].nunique(),
        "users.user_id contains duplicates",
    )
    report.check(
        wallets.groupby("user_id")["wallet_type"].apply(
            lambda s: (s == "upay").sum() == 1
        ).all(),
        "every user must own exactly one upay wallet",
    )


def check_foreign_keys(tables: dict[str, pd.DataFrame], report: ValidationReport) -> None:
    user_ids = set(tables["users"]["user_id"])
    wallet_ids = set(tables["wallets"]["wallet_id"])
    goal_ids = set(tables["financial_goals"]["goal_id"])
    wallet_owner = dict(zip(tables["wallets"]["wallet_id"], tables["wallets"]["user_id"]))

    for name, column in (
        ("wallets", "user_id"),
        ("income_events", "user_id"),
        ("transactions", "user_id"),
        ("recurring_expenses", "user_id"),
        ("financial_goals", "user_id"),
        ("goal_contributions", "user_id"),
        ("financial_profiles", "user_id"),
    ):
        orphans = set(tables[name][column]) - user_ids
        report.check(not orphans, f"{name}.{column} has unknown user_id values {sorted(orphans)[:5]}")

    orphan_wallets = set(tables["transactions"]["wallet_id"]) - wallet_ids
    report.check(
        not orphan_wallets,
        f"transactions.wallet_id has unknown wallets {sorted(orphan_wallets)[:5]}",
    )

    mismatched = tables["transactions"].apply(
        lambda row: wallet_owner.get(row["wallet_id"]) != row["user_id"], axis=1
    )
    report.check(
        not mismatched.any(),
        f"{int(mismatched.sum())} transactions reference another user's wallet",
    )

    orphan_goals = set(tables["goal_contributions"]["goal_id"]) - goal_ids
    report.check(
        not orphan_goals,
        f"goal_contributions.goal_id has unknown goals {sorted(orphan_goals)[:5]}",
    )

    goal_owner = dict(zip(tables["financial_goals"]["goal_id"], tables["financial_goals"]["user_id"]))
    bad_ownership = tables["goal_contributions"].apply(
        lambda row: goal_owner.get(row["goal_id"]) != row["user_id"], axis=1
    )
    report.check(
        not bad_ownership.any(),
        f"{int(bad_ownership.sum())} contributions are attributed to the wrong user",
    )


def check_ledger(tables: dict[str, pd.DataFrame], report: ValidationReport) -> None:
    transactions = tables["transactions"]
    wallets = tables["wallets"]

    report.check(
        (transactions["amount"] > 0).all(),
        "transactions.amount must be strictly positive",
    )

    negatives = int((transactions["balance_after"] < 0).sum())
    report.check(negatives == 0, f"{negatives} transactions end with a negative balance")
    report.stats["negative_balances"] = negatives

    ordered = transactions.merge(
        wallets[["wallet_id", "opening_balance"]], on="wallet_id", how="left"
    )
    ordered = ordered.sort_values(
        ["wallet_id", "timestamp", "transaction_id"]
    ).reset_index(drop=True)
    signed = np.where(
        ordered["direction"] == "inflow", ordered["amount"], -ordered["amount"]
    )
    # The running balance must accumulate within each wallet, not across wallets.
    recomputed = ordered["opening_balance"] + pd.Series(signed).groupby(
        ordered["wallet_id"].to_numpy()
    ).cumsum()
    drift = (recomputed - ordered["balance_after"]).abs().max()
    report.check(
        bool(drift < 0.01),
        f"balance_after does not reconcile with opening balance and flows (max drift {drift})",
    )
    report.stats["max_balance_drift"] = round(float(drift), 6)

    _check_cash_pairs(transactions, report)
    _check_send_money_pairs(transactions, report)
    _check_income_links(tables, report)


def _check_cash_pairs(transactions: pd.DataFrame, report: ValidationReport) -> None:
    """Cash out and cash in must be equal-sized, same-user, cross-wallet pairs."""
    out = transactions[transactions["transaction_type"] == "cash_out"]
    into = transactions[transactions["transaction_type"] == "cash_in"]

    report.check(
        len(out) == len(into),
        f"cash_out rows ({len(out)}) != cash_in rows ({len(into)})",
    )

    if not len(out) or not len(into):
        return

    linked = out.merge(
        into,
        left_on="related_transaction_id",
        right_on="transaction_id",
        suffixes=("_out", "_in"),
    )

    unmatched = len(out) - len(linked)
    report.check(
        unmatched == 0,
        f"{unmatched} cash withdrawals have no linked cash deposit",
    )

    same_amount = (linked["amount_out"] - linked["amount_in"]).abs()
    report.check(
        bool((same_amount < 0.01).all()),
        f"{(same_amount >= 0.01).sum()} cash pairs have mismatched amounts",
    )
    report.check(
        bool((linked["user_id_out"] == linked["user_id_in"]).all()),
        "a cash pair spans two different users",
    )
    report.check(
        bool((linked["wallet_id_out"] != linked["wallet_id_in"]).all()),
        "a cash pair moved money within a single wallet instead of across two",
    )

    report.stats["cash_transfer_pairs"] = len(linked)
    report.stats["cash_transfer_legs"] = int(len(out) + len(into))
    report.stats["cash_out_share_of_rows"] = round(
        2 * len(out) / max(len(transactions), 1), 4
    )
    report.stats["users_with_cash_activity"] = int(out["user_id"].nunique())


def _check_send_money_pairs(transactions: pd.DataFrame, report: ValidationReport) -> None:
    """send_money is user to user: two rows, two users, sender pays the fee."""
    sent = transactions[transactions["transaction_type"] == "send_money"]
    received = transactions[transactions["transaction_type"] == "receive_money"]

    report.check(
        len(sent) == len(received),
        f"send_money rows ({len(sent)}) != receive_money rows ({len(received)})",
    )

    if not len(sent):
        return

    linked = sent.merge(
        received,
        left_on="related_transaction_id",
        right_on="transaction_id",
        suffixes=("_send", "_recv"),
    )

    report.check(
        len(linked) == len(sent),
        f"{len(sent) - len(linked)} sends have no linked receive",
    )

    report.check(
        bool((linked["user_id_send"] != linked["user_id_recv"]).all()),
        "a send_money pair involves the same user on both legs",
    )

    # The sender is debited amount + fee; the receiver gets the amount alone.
    # Only the sender is charged, so the receiver's fee must be zero.
    expected = linked["amount_send"] - linked["fee_amount_send"] - linked["amount_recv"]
    report.check(
        bool((expected.abs() < 0.01).all()),
        f"{(expected.abs() >= 0.01).sum()} transfers where sender amount != receiver amount + fee",
    )
    report.check(
        bool((linked["fee_amount_send"] > 0).all()),
        "a send_money row has no fee",
    )
    report.check(
        bool((sent["direction"] == "outflow").all()),
        "send_money rows must be outflows",
    )
    report.check(
        bool((received["direction"] == "inflow").all()),
        "receive_money rows must be inflows",
    )
    report.check(
        bool((received["fee_amount"] == 0).all()),
        "a receive_money row was charged a fee; only the sender pays it",
    )

    report.stats["send_money_pairs"] = len(linked)
    report.stats["send_money_total"] = round(float(linked["amount_send"].sum()), 2)
    report.stats["send_money_fees"] = round(float(linked["fee_amount_send"].sum()), 2)
    report.stats["unique_senders"] = int(sent["user_id"].nunique())
    report.stats["unique_receivers"] = int(received["user_id"].nunique())


def _check_income_links(tables: dict[str, pd.DataFrame], report: ValidationReport) -> None:
    """Every income event must be credited exactly once, via income_event_id."""
    income = tables["income_events"]
    transactions = tables["transactions"]

    credited = transactions[transactions["income_event_id"].notna()]
    report.check(
        bool((credited["direction"] == "inflow").all()),
        "a transaction with an income_event_id is not an inflow",
    )

    linked = credited.merge(
        income, left_on="income_event_id", right_on="income_id", suffixes=("_txn", "_ev")
    )
    report.check(
        len(linked) == len(income),
        f"{len(income) - len(linked)} income events are not credited in the ledger",
    )
    report.check(
        bool((linked["amount_txn"] - linked["amount_ev"]).abs().lt(0.01).all()),
        "a credited amount does not match its income event",
    )
    report.check(
        bool((linked["user_id_txn"] == linked["user_id_ev"]).all()),
        "an income event was credited to a different user",
    )

    duplicate = credited["income_event_id"].duplicated().sum()
    report.check(duplicate == 0, f"{duplicate} income events are credited more than once")

    income_total = round(float(income["amount"].sum()), 2)
    credited_total = round(float(credited["amount"].sum()), 2)
    report.check(
        abs(income_total - credited_total) < 0.01,
        f"credited income {credited_total} != income_events total {income_total}",
    )
    report.stats["income_event_total"] = income_total
    report.stats["credited_income_total"] = credited_total
    report.stats["income_events_linked"] = f"{len(linked)}/{len(income)}"


def check_vocabulary(tables: dict[str, pd.DataFrame], schemas, report: ValidationReport) -> None:
    transactions = tables["transactions"]

    unknown = set(transactions["category"]) - set(TRANSACTION_CATEGORIES)
    report.check(
        not unknown,
        f"unknown transaction categories {sorted(unknown)}",
    )

    unknown_types = set(transactions["transaction_type"]) - set(TRANSACTION_TYPES)
    report.check(
        not unknown_types,
        f"unknown transaction types {sorted(unknown_types)}",
    )
    report.check(
        set(transactions["direction"]) <= {"inflow", "outflow"},
        "direction must be inflow or outflow",
    )

    # A user cannot send money to themselves.
    self_transfer = transactions[transactions["transaction_type"] == "send_money"].merge(
        transactions[transactions["transaction_type"] == "receive_money"],
        left_on="related_transaction_id",
        right_on="transaction_id",
        suffixes=("_send", "_recv"),
    )
    report.check(
        bool((self_transfer["user_id_send"] != self_transfer["user_id_recv"]).all()),
        "a user sent money to themselves",
    )

    # related_transaction_id must always point at a real, different row.
    known = set(transactions["transaction_id"])
    dangling = set(transactions["related_transaction_id"].dropna()) - known
    report.check(
        not dangling,
        f"related_transaction_id points at missing transactions {sorted(dangling)[:5]}",
    )

    self_reference = transactions[
        transactions["related_transaction_id"] == transactions["transaction_id"]
    ]
    report.check(self_reference.empty, "a transaction is linked to itself")

    paired = transactions[transactions["related_transaction_id"].notna()]
    report.check(
        bool((paired["related_transaction_id"].notna()).all()),
        "a linked row has no partner",
    )

    bad_subcategory = [
        (row.category, row.subcategory)
        for row in transactions.itertuples()
        if row.subcategory not in TRANSACTION_CATEGORIES.get(row.category, [])
    ]
    report.check(
        not bad_subcategory,
        f"{len(bad_subcategory)} subcategory values are invalid for their category, "
        f"e.g. {bad_subcategory[:3]}",
    )

    wallets = tables["wallets"]
    report.check(
        set(wallets["wallet_type"]) <= {"upay", "bank", "cash", "other_digital"},
        "wallets.wallet_type has unknown values",
    )


def check_relationships(tables: dict[str, pd.DataFrame], report: ValidationReport) -> None:
    goals = tables["financial_goals"]
    contributions = tables["goal_contributions"]

    totals = contributions.groupby("goal_id")["amount"].sum()
    expected = goals.set_index("goal_id")["current_amount"].reindex(totals.index)
    mismatched = (~np.isclose(totals.values, expected.values, atol=0.01)).sum()
    report.check(
        mismatched == 0,
        f"current_amount != sum(contributions) for {mismatched} goals",
    )
    report.stats["goals"] = len(goals)
    report.stats["goals_contributed_to"] = int(totals.index.nunique())
    report.stats["goal_contribution_total"] = round(float(totals.sum()), 2)
    report.stats["goal_current_amount_exact"] = mismatched == 0

    report.check(
        (goals["current_amount"] <= goals["target_amount"] + 0.01).all(),
        "a goal's current_amount exceeds its target_amount",
    )

    # Recurring obligations must actually be paid most months.
    recurring = tables["recurring_expenses"]
    transactions = tables["transactions"]
    paid = (
        transactions[transactions["recurring_id"].notna()]
        .groupby("recurring_id")["timestamp"]
        .count()
    )
    coverage = float(paid.reindex(recurring["recurring_id"]).fillna(0).gt(0).mean())
    report.check(
        coverage > 0.85,
        f"only {coverage:.1%} of recurring obligations have any linked payment",
    )
    report.stats["recurring_expenses"] = len(recurring)
    report.stats["recurring_with_payments"] = f"{coverage:.1%}"

    orphans = set(transactions["recurring_id"].dropna()) - set(recurring["recurring_id"])
    report.check(not orphans, f"transactions link to unknown recurring ids {sorted(orphans)[:5]}")


def check_dates(tables: dict[str, pd.DataFrame], report: ValidationReport) -> None:
    for name in ("transactions", "income_events", "goal_contributions"):
        frame = tables[name]
        if "timestamp" not in frame.columns or not len(frame):
            continue
        report.check(
            frame["timestamp"].notna().all(),
            f"{name} contains missing timestamps",
        )

    goals = tables["financial_goals"]
    report.check(
        (pd.to_datetime(goals["target_date"]) >= pd.to_datetime(goals["created_date"])).all(),
        "financial_goals.target_date precedes created_date",
    )

    contributions = tables["goal_contributions"]
    if len(contributions):
        created = dict(
            zip(tables["financial_goals"]["goal_id"], pd.to_datetime(tables["financial_goals"]["created_date"]))
        )
        earliest = contributions.groupby("goal_id")["timestamp"].min()
        violations = [
            goal_id
            for goal_id, timestamp in earliest.items()
            if goal_id in created and pd.Timestamp(timestamp) < created[goal_id]
        ]
        report.check(not violations, f"{len(violations)} contributions predate goal creation")


def check_behaviour(tables: dict[str, pd.DataFrame], report: ValidationReport) -> None:
    """Confirm the injected personas are actually observable (Step 12)."""
    transactions = tables["transactions"]
    users = tables["users"]
    labels = tables.get("behavior_labels")

    consumption = transactions[
        (transactions["direction"] == "outflow") & (transactions["category"] != "cash")
    ].copy()
    consumption["period"] = consumption["timestamp"].dt.strftime("%Y-%m")
    consumption["late"] = consumption["timestamp"].dt.day >= 23

    monthly = (
        consumption.groupby(["user_id", "period"])["amount"].sum().rename("spend").reset_index()
    )
    late_totals = (
        consumption[consumption["late"]]
        .groupby(["user_id", "period"])["amount"]
        .sum()
        .rename("late_spend")
    )
    monthly = monthly.merge(
        late_totals, on=["user_id", "period"], how="left"
    )
    monthly["late_spend"] = monthly["late_spend"].fillna(0.0)
    monthly["late_share"] = monthly["late_spend"] / monthly["spend"].clip(lower=1)

    by_persona = monthly.merge(users[["user_id", "persona"]], on="user_id")
    late_by_persona = by_persona.groupby("persona")["late_share"].mean()
    spend_by_persona = consumption.merge(
        users[["user_id", "persona"]], on="user_id"
    ).groupby("persona")["amount"].mean()

    report.stats["late_month_share_by_persona"] = {
        k: round(float(v), 3) for k, v in late_by_persona.items()
    }
    report.stats["mean_transaction_by_persona"] = {
        k: round(float(v), 0) for k, v in spend_by_persona.items()
    }

    shortage = late_by_persona.get("end_month_shortage", 0.0)
    saver = late_by_persona.get("stable_saver", 0.0)
    report.check(
        shortage > saver,
        f"end_month_shortage ({shortage:.3f}) does not exceed stable_saver ({saver:.3f})",
    )

    anomalies = transactions[transactions["is_anomaly"]]
    avg_anomaly = float(anomalies["amount"].mean()) if len(anomalies) else 0.0
    avg_normal = float(
        transactions[~transactions["is_anomaly"]]["amount"].mean()
    )
    report.check(
        avg_anomaly > avg_normal,
        f"injected anomalies (avg {avg_anomaly:.0f}) are not larger than normal spending ({avg_normal:.0f})",
    )
    report.stats["anomaly_transactions"] = len(anomalies)
    report.stats["anomaly_avg_ticket"] = round(avg_anomaly, 2)
    report.stats["normal_avg_ticket"] = round(avg_normal, 2)

    cash_wallets = set(transactions.loc[transactions["transaction_type"] == "cash_in", "wallet_id"])
    cash_spend = consumption[consumption["wallet_id"].isin(cash_wallets)]
    report.stats["observed_cash_spend_share"] = round(
        float(cash_spend["amount"].sum() / max(consumption["amount"].sum(), 1.0)), 3
    )

    if labels is not None and len(labels):
        positives = {
            column: round(float(labels[column].mean()), 3)
            for column in labels.columns
            if column.endswith("_label")
        }
        report.stats["label_positive_rate"] = positives
        report.check(
            all(0.0 < rate < 1.0 for rate in positives.values()),
            f"a label is constant across the dataset: {positives}",
        )
        report.check(
            set(labels["period"]) <= set(pd.period_range("2026-01", "2026-09", freq="M").strftime("%Y-%m")),
            "behavior_labels contains periods outside the simulated window",
        )


def validate(tables: dict[str, pd.DataFrame], schema_dir: str | Path) -> ValidationReport:
    """Run every validation layer and return a single report."""
    schemas = load_schema(schema_dir)
    report = ValidationReport()

    for name, frame in tables.items():
        report.stats[f"{name}_rows"] = len(frame)

    check_schema(tables, schemas, report)
    check_primary_keys(tables, report)
    check_foreign_keys(tables, report)
    check_vocabulary(tables, schemas, report)
    check_ledger(tables, report)
    check_relationships(tables, report)
    check_dates(tables, report)
    check_behaviour(tables, report)

    return report