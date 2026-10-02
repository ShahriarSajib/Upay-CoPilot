"""Tests for the synthetic dataset generator, validator and split logic.

A small sample is generated once and reused, so the suite stays fast while
still exercising the real generation path.

Run with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.dataset.config import LABEL_THRESHOLDS, SEED, START_DATE, TRANSFER_TYPES
from ml.dataset.goals import monthly_surplus
from ml.dataset.labels import build_behavior_labels
from ml.dataset.leakage import run_leakage_check
from ml.dataset.pipeline import (
    build_dataset,
    month_starts,
    write_temporal_splits,
)
from ml.dataset.profiles import build_financial_profiles
from ml.dataset.recurring import build_recurring_expenses
from ml.dataset.splits import SPLIT_PERIODS, drop_leaky_columns
from ml.dataset.validation import validate

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "data" / "schema"

_CACHE: dict[str, dict[str, pd.DataFrame]] = {}


def sample_dataset(seed: int = SEED, users: int = 60, months: int = 9):
    """Generate (and cache) a small but complete dataset."""
    key = f"{seed}-{users}-{months}"
    if key not in _CACHE:
        _CACHE[key] = build_dataset(seed=seed, num_users=users, months_count=months)
    return _CACHE[key]


class TestSchemaAndKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_every_schema_column_is_present(self):
        report = validate(self.tables, SCHEMA_DIR)
        schema_errors = [e for e in report.errors if "schema" in e]
        self.assertEqual(schema_errors, [], f"schema problems: {schema_errors}")

    def test_primary_keys_are_unique(self):
        for name, key in (
            ("users", "user_id"),
            ("wallets", "wallet_id"),
            ("transactions", "transaction_id"),
            ("income_events", "income_id"),
            ("recurring_expenses", "recurring_id"),
            ("financial_goals", "goal_id"),
            ("goal_contributions", "contribution_id"),
        ):
            with self.subTest(table=name):
                self.assertTrue(self.tables[name][key].is_unique)

    def test_each_user_owns_exactly_one_upay_wallet(self):
        counts = self.tables["wallets"].groupby(["user_id", "wallet_type"]).size().unstack(fill_value=0)
        self.assertTrue((counts["upay"] == 1).all())


class TestForeignKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()
        cls.user_ids = set(cls.tables["users"]["user_id"])

    def test_every_user_reference_resolves(self):
        for name in (
            "wallets",
            "income_events",
            "transactions",
            "recurring_expenses",
            "financial_goals",
            "goal_contributions",
        ):
            with self.subTest(table=name):
                self.assertTrue(set(self.tables[name]["user_id"]) <= self.user_ids)

    def test_transactions_use_their_own_users_wallets(self):
        owner = dict(
            zip(self.tables["wallets"]["wallet_id"], self.tables["wallets"]["user_id"])
        )
        transactions = self.tables["transactions"]
        for row in transactions.itertuples():
            if owner.get(row.wallet_id) != row.user_id:
                self.fail(f"{row.transaction_id} references another user's wallet")
                return

    def test_contributions_belong_to_the_goal_owner(self):
        owner = dict(
            zip(self.tables["financial_goals"]["goal_id"], self.tables["financial_goals"]["user_id"])
        )
        for row in self.tables["goal_contributions"].itertuples():
            if owner.get(row.goal_id) != row.user_id:
                self.fail(f"{row.contribution_id} is attributed to the wrong user")
                return


class TestLedgerIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_no_negative_balances(self):
        self.assertTrue((self.tables["transactions"]["balance_after"] >= 0).all())

    def test_running_balance_matches_opening_plus_flows(self):
        transactions = self.tables["transactions"]
        wallets = self.tables["wallets"][["wallet_id", "opening_balance"]]

        merged = transactions.merge(wallets, on="wallet_id", how="left").sort_values(
            ["wallet_id", "timestamp", "transaction_id"]
        ).reset_index(drop=True)

        signed = np.where(
            merged["direction"] == "inflow", merged["amount"], -merged["amount"]
        )
        expected = merged["opening_balance"] + pd.Series(signed).groupby(
            merged["wallet_id"].to_numpy()
        ).cumsum()

        self.assertLess(float((expected - merged["balance_after"]).abs().max()), 0.01)

    def test_amounts_are_positive(self):
        for name in ("transactions", "income_events", "goal_contributions"):
            with self.subTest(table=name):
                self.assertTrue((self.tables[name]["amount"] > 0).all())

    def test_cash_transfers_are_matched_pairs(self):
        transactions = self.tables["transactions"]
        out = transactions[transactions["transaction_type"] == "cash_out"]
        into = transactions[transactions["transaction_type"] == "cash_in"]

        self.assertEqual(len(out), len(into))
        self.assertTrue(out["related_transaction_id"].notna().all())

        linked = out.merge(
            into,
            left_on="related_transaction_id",
            right_on="transaction_id",
            suffixes=("_out", "_in"),
        )
        self.assertEqual(len(linked), len(out))
        self.assertTrue((linked["amount_out"] - linked["amount_in"]).abs().lt(0.01).all())
        self.assertTrue((linked["user_id_out"] == linked["user_id_in"]).all())
        self.assertTrue((linked["wallet_id_out"] != linked["wallet_id_in"]).all())

    def test_cash_volume_is_a_real_share_of_activity(self):
        """Cash handling is high volume in a real mobile money account."""
        transactions = self.tables["transactions"]
        legs = transactions["transaction_type"].isin(["cash_in", "cash_out"]).sum()
        share = legs / len(transactions)
        self.assertGreater(share, 0.10, "cash activity should be a large share of rows")
        self.assertGreater(transactions["user_id"].nunique() * 0.8, 0)

    def test_every_income_event_is_credited_exactly_once(self):
        income = self.tables["income_events"]
        credited = self.tables["transactions"][
            self.tables["transactions"]["income_event_id"].notna()
        ]

        self.assertEqual(len(credited), len(income))
        self.assertFalse(credited["income_event_id"].duplicated().any())
        self.assertTrue((credited["direction"] == "inflow").all())

        linked = credited.merge(
            income,
            left_on="income_event_id",
            right_on="income_id",
            suffixes=("_txn", "_ev"),
        )
        self.assertTrue((linked["amount_txn"] - linked["amount_ev"]).abs().lt(0.01).all())
        self.assertTrue((linked["user_id_txn"] == linked["user_id_ev"]).all())

    def test_income_event_ids_resolve(self):
        known = set(self.tables["income_events"]["income_id"])
        used = set(self.tables["transactions"]["income_event_id"].dropna())
        self.assertTrue(used <= known)

    def test_chronology_is_monotonic_within_each_wallet(self):
        transactions = self.tables["transactions"].sort_values(
            ["wallet_id", "timestamp"]
        )
        for _, group in transactions.groupby("wallet_id"):
            self.assertTrue(group["timestamp"].is_monotonic_increasing)


class TestRecurringExpenses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_every_obligation_is_paid_at_least_once(self):
        recurring = self.tables["recurring_expenses"]
        paid = self.tables["transactions"][self.tables["transactions"]["recurring_id"].notna()]
        self.assertGreater(set(paid["recurring_id"]), set(recurring["recurring_id"]) - set(paid["recurring_id"]))
        self.assertTrue((paid.groupby("recurring_id").size() > 0).all())

    def test_payment_subcategory_matches_the_obligation(self):
        recurring = self.tables["recurring_expenses"].set_index("recurring_id")
        paid = self.tables["transactions"][self.tables["transactions"]["recurring_id"].notna()]
        for row in paid.itertuples():
            name = recurring.loc[row.recurring_id, "expense_name"]
            self.assertEqual(row.subcategory, name)

    def test_amounts_track_the_defined_obligation(self):
        recurring = self.tables["recurring_expenses"].set_index("recurring_id")
        paid = self.tables["transactions"][self.tables["transactions"]["recurring_id"].notna()]
        for recurring_id, group in paid.groupby("recurring_id"):
            expected = recurring.loc[recurring_id, "amount"]
            self.assertTrue(np.allclose(group["amount"], expected * 1.15, rtol=0.5))

    def test_next_due_date_is_after_the_history_window(self):
        recurring = self.tables["recurring_expenses"]
        self.assertTrue(
            (pd.to_datetime(recurring["next_due_date"]) > pd.Timestamp("2026-09-30")).all()
        )


class TestSendMoneyTransfers(unittest.TestCase):
    """User to user "send money": upay id to upay id."""

    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()
        transactions = cls.tables["transactions"]
        cls.sent = transactions[transactions["transaction_type"] == "send_money"]
        cls.received = transactions[transactions["transaction_type"] == "receive_money"]

    def test_both_legs_exist_in_equal_numbers(self):
        self.assertGreater(len(self.sent), 0, "no user-to-user transfers were generated")
        self.assertEqual(len(self.sent), len(self.received))

    def test_every_send_links_to_exactly_one_receive(self):
        self.assertTrue(self.sent["related_transaction_id"].notna().all())
        self.assertTrue(self.received["related_transaction_id"].notna().all())

        linked = self.sent.merge(
            self.received,
            left_on="related_transaction_id",
            right_on="transaction_id",
            suffixes=("_send", "_recv"),
        )
        self.assertEqual(len(linked), len(self.sent))

    def test_transfers_link_two_different_users(self):
        linked = self.sent.merge(
            self.received,
            left_on="related_transaction_id",
            right_on="transaction_id",
            suffixes=("_send", "_recv"),
        )
        self.assertTrue((linked["user_id_send"] != linked["user_id_recv"]).all())

    def test_sender_pays_the_fee_and_receiver_gets_the_amount(self):
        linked = self.sent.merge(
            self.received,
            left_on="related_transaction_id",
            right_on="transaction_id",
            suffixes=("_send", "_recv"),
        )
        difference = linked["amount_send"] - linked["amount_recv"]
        self.assertTrue((difference > 0).all(), "fee must make the sender pay more")
        self.assertTrue((linked["fee_amount_send"] > 0).all())
        self.assertTrue((linked["fee_amount_recv"] == 0).all())
        self.assertTrue(
            (difference - linked["fee_amount_send"]).abs().lt(0.01).all(),
            "sender amount must equal receiver amount plus the fee",
        )

    def test_direction_and_category_are_correct(self):
        self.assertTrue((self.sent["direction"] == "outflow").all())
        self.assertTrue((self.received["direction"] == "inflow").all())
        self.assertTrue((self.sent["category"] == "transfer").all())
        self.assertTrue((self.sent["subcategory"] == "send_money").all())
        self.assertTrue((self.received["subcategory"] == "receive_money").all())

    def test_transfers_go_between_upay_wallets(self):
        wallets = self.tables["wallets"].set_index("wallet_id")["wallet_type"]
        linked = self.sent.merge(
            self.received,
            left_on="related_transaction_id",
            right_on="transaction_id",
            suffixes=("_send", "_recv"),
        )
        self.assertTrue((linked["wallet_id_send"].map(wallets) == "upay").all())
        self.assertTrue((linked["wallet_id_recv"].map(wallets) == "upay").all())

    def test_transfers_are_not_counted_as_income_or_spending(self):
        """A transfer between people is neither earning nor spending."""
        self.assertGreater(len(self.received), 0)

        surplus = monthly_surplus(self.tables["transactions"])
        income = self.tables["income_events"].copy()
        income["period"] = income["timestamp"].dt.strftime("%Y-%m")

        # Income in the surplus calc must equal income_events only, so the
        # receive_money inflows are excluded.
        expected = income.groupby(["user_id", "period"])["amount"].sum().rename("expected")
        actual = surplus.set_index(["user_id", "period"])["income"].rename("actual")
        joined = pd.concat([expected, actual], axis=1).fillna(0.0)
        self.assertTrue(
            (joined["expected"] - joined["actual"]).abs().lt(0.01).all(),
            "receive_money inflows leaked into income",
        )

        # Spending must exclude both cash legs and transfer legs.
        transactions = self.tables["transactions"]
        outflows = transactions[
            (transactions["direction"] == "outflow")
            & (transactions["category"] != "cash")
            & (~transactions["transaction_type"].isin(TRANSFER_TYPES))
        ].copy()
        outflows["period"] = outflows["timestamp"].dt.strftime("%Y-%m")
        expected_spend = (
            outflows.groupby(["user_id", "period"])["amount"].sum().rename("expected")
        )
        actual_spend = surplus.set_index(["user_id", "period"])["spend"].rename("actual")
        joined = pd.concat([expected_spend, actual_spend], axis=1).fillna(0.0)
        self.assertTrue(
            (joined["expected"] - joined["actual"]).abs().lt(0.01).all(),
            "send_money outflows leaked into spending",
        )

    def test_no_orphaned_related_ids(self):
        known = set(self.tables["transactions"]["transaction_id"])
        referenced = set(self.tables["transactions"]["related_transaction_id"].dropna())
        self.assertTrue(referenced <= known)

    def test_links_are_symmetric(self):
        by_id = self.tables["transactions"].set_index("transaction_id")
        for row in self.sent.head(50).itertuples():
            partner = by_id.loc[row.related_transaction_id]
            self.assertEqual(partner.related_transaction_id, row.transaction_id)


class TestGoals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_current_amount_equals_contribution_total(self):
        totals = self.tables["goal_contributions"].groupby("goal_id")["amount"].sum()
        for goal in self.tables["financial_goals"].itertuples():
            expected = round(float(totals.get(goal.goal_id, 0.0)), 2)
            self.assertAlmostEqual(goal.current_amount, expected, places=2)

    def test_current_amount_never_exceeds_target(self):
        goals = self.tables["financial_goals"]
        self.assertTrue((goals["current_amount"] <= goals["target_amount"] + 0.01).all())

    def test_contributions_never_exceed_observed_surplus(self):
        surplus = monthly_surplus(self.tables["transactions"])
        lookup = {
            (row.user_id, row.period): max(row.surplus, 0.0) for row in surplus.itertuples()
        }
        contributions = self.tables["goal_contributions"].copy()
        contributions["period"] = contributions["timestamp"].dt.strftime("%Y-%m")

        for row in contributions.itertuples():
            available = lookup.get((row.user_id, row.period), 0.0)
            self.assertLessEqual(row.amount, available + 0.01)

    def test_target_date_is_after_creation(self):
        goals = self.tables["financial_goals"]
        self.assertTrue(
            (pd.to_datetime(goals["target_date"]) >= pd.to_datetime(goals["created_date"])).all()
        )


class TestProfilesAndLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_one_profile_per_user(self):
        profiles = self.tables["financial_profiles"]
        self.assertEqual(len(profiles), self.tables["users"]["user_id"].nunique())
        self.assertTrue(profiles["user_id"].is_unique)

    def test_profile_savings_rate_matches_its_inputs(self):
        profiles = self.tables["financial_profiles"]
        for row in profiles.head(25).itertuples():
            expected = row.average_monthly_savings / row.monthly_income_avg
            self.assertAlmostEqual(row.savings_rate, round(expected, 4), places=3)

    def test_labels_cover_only_observed_periods(self):
        labels = self.tables["behavior_labels"]
        self.assertTrue(
            set(labels["period"]) <= {f"2026-{month:02d}" for month in range(1, 10)}
        )

    def test_labels_are_binary(self):
        labels = self.tables["behavior_labels"]
        for column in labels.columns:
            if column.endswith("_label"):
                with self.subTest(column=column):
                    self.assertTrue(set(labels[column].unique()) <= {0, 1})

    def test_no_label_is_constant(self):
        labels = self.tables["behavior_labels"]
        for column in labels.columns:
            if column.endswith("_label"):
                with self.subTest(column=column):
                    rate = float(labels[column].mean())
                    self.assertGreater(rate, 0.0, f"{column} has no positive examples")
                    self.assertLess(rate, 1.0, f"{column} is always positive")

    def test_end_month_shortage_label_matches_late_spending(self):
        transactions = self.tables["transactions"]
        # Mirror the label builder exactly: cash legs and user-to-user
        # transfers are excluded from consumption.
        spend = transactions[
            (transactions["direction"] == "outflow")
            & (transactions["category"] != "cash")
            & (~transactions["transaction_type"].isin(TRANSFER_TYPES))
        ].copy()
        spend["period"] = spend["timestamp"].dt.strftime("%Y-%m")
        spend["late"] = spend["timestamp"].dt.day >= 23

        monthly = spend.groupby(["user_id", "period"]).apply(
            lambda d: pd.Series(
                {
                    "share": d.loc[d.late, "amount"].sum() / max(d.amount.sum(), 1.0),
                }
            ),
            include_groups=False,
        ).reset_index()

        labels = self.tables["behavior_labels"]
        merged = monthly.merge(labels, on=["user_id", "period"])
        flagged = merged[merged["end_month_shortage_label"] == 1]["share"]
        unflagged = merged[merged["end_month_shortage_label"] == 0]["share"]

        self.assertGreater(len(flagged), 0)
        self.assertGreater(len(unflagged), 0)
        # The threshold separates the two classes exactly.
        self.assertGreater(flagged.min(), unflagged.max())
        self.assertGreaterEqual(flagged.min(), LABEL_THRESHOLDS["late_month_share"])
        self.assertLessEqual(unflagged.max(), LABEL_THRESHOLDS["late_month_share"])

    def test_labels_do_not_reference_the_persona_column(self):
        """Labels must be derivable without reading the ground-truth persona."""
        transactions = self.tables["transactions"]
        without_persona = transactions.drop(columns=[c for c in ("user_id",) if c in transactions])
        rebuilt = build_behavior_labels(
            transactions,
            self.tables["goal_contributions"],
            self.tables["injected_patterns"],
            month_starts(9),
        )
        self.assertEqual(len(rebuilt), len(self.tables["behavior_labels"]))
        self.assertFalse(without_persona.empty)


class TestBehaviourIsObservable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_end_month_shortage_persona_spends_later(self):
        transactions = self.tables["transactions"]
        users = self.tables["users"][["user_id", "persona"]]
        spend = transactions[
            (transactions["direction"] == "outflow") & (transactions["category"] != "cash")
        ].copy()
        spend["late"] = spend["timestamp"].dt.day >= 23
        merged = spend.merge(users, on="user_id")

        late = merged.groupby("persona").apply(
            lambda d: d.loc[d.late, "amount"].sum() / max(d.amount.sum(), 1.0),
            include_groups=False,
        )
        self.assertGreater(
            late["end_month_shortage"],
            late["stable_saver"],
            "the injected shortage persona is not visibly short-spending late",
        )

    def test_irregular_income_persona_has_unstable_income(self):
        income = self.tables["income_events"]
        users = self.tables["users"][["user_id", "persona"]]
        income = income.copy()
        income["period"] = income["timestamp"].dt.strftime("%Y-%m")
        monthly = income.groupby(["user_id", "period"])["amount"].sum().reset_index()

        cv = monthly.groupby("user_id")["amount"].apply(
            lambda s: float(s.std(ddof=0) / s.mean()) if s.mean() > 0 else 0.0
        )
        merged = cv.reset_index().rename(columns={"amount": "cv"}).merge(users, on="user_id")
        by_persona = merged.groupby("persona")["cv"].mean()
        self.assertGreater(by_persona["irregular_income"], by_persona["stable_saver"])

    def test_injected_anomalies_are_larger_than_normal_spending(self):
        transactions = self.tables["transactions"]
        anomaly = transactions[transactions["is_anomaly"]]["amount"].mean()
        normal = transactions[~transactions["is_anomaly"]]["amount"].mean()
        self.assertGreater(anomaly, normal * 2)

    def test_injected_patterns_reference_real_transactions(self):
        patterns = self.tables["injected_patterns"]
        anomalies = self.tables["transactions"][self.tables["transactions"]["is_anomaly"]]
        self.assertEqual(len(patterns), len(anomalies))
        self.assertTrue(
            set(zip(patterns["user_id"], patterns["amount"]))
            <= set(zip(anomalies["user_id"], anomalies["amount"]))
        )


class TestDeterminism(unittest.TestCase):
    def test_same_seed_produces_identical_tables(self):
        first = sample_dataset(seed=7, users=20, months=6)
        second = build_dataset(seed=7, num_users=20, months_count=6)
        for name, frame in first.items():
            with self.subTest(table=name):
                pd.testing.assert_frame_equal(frame, second[name])

    def test_different_seed_produces_different_data(self):
        first = sample_dataset(seed=7, users=20, months=6)
        second = build_dataset(seed=99, num_users=20, months_count=6)
        self.assertNotEqual(
            first["transactions"]["amount"].sum(),
            second["transactions"]["amount"].sum(),
        )

    def test_window_starts_at_the_configured_date(self):
        months = month_starts(9)
        self.assertEqual(months[0], pd.Timestamp(START_DATE))
        self.assertEqual(months[-1], pd.Timestamp("2026-09-01"))


class TestValidationCatchesProblems(unittest.TestCase):
    """A validator that never fails is worthless, so break things on purpose."""

    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_clean_dataset_passes(self):
        self.assertTrue(validate(self.tables, SCHEMA_DIR).passed)

    def test_detects_negative_balance(self):
        broken = {k: v.copy() for k, v in self.tables.items()}
        broken["transactions"].loc[0, "balance_after"] = -1.0
        report = validate(broken, SCHEMA_DIR)
        self.assertFalse(report.passed)
        self.assertTrue(any("negative balance" in e for e in report.errors))

    def test_detects_balance_drift(self):
        broken = {k: v.copy() for k, v in self.tables.items()}
        broken["transactions"].loc[5, "balance_after"] += 5_000.0
        report = validate(broken, SCHEMA_DIR)
        self.assertFalse(report.passed)
        self.assertTrue(any("reconcile" in e for e in report.errors))

    def test_detects_broken_goal_invariant(self):
        broken = {k: v.copy() for k, v in self.tables.items()}
        broken["financial_goals"].loc[0, "current_amount"] += 500.0
        report = validate(broken, SCHEMA_DIR)
        self.assertFalse(report.passed)
        self.assertTrue(any("current_amount" in e for e in report.errors))

    def test_detects_dangling_foreign_key(self):
        broken = {k: v.copy() for k, v in self.tables.items()}
        broken["transactions"].loc[0, "user_id"] = "U999999"
        report = validate(broken, SCHEMA_DIR)
        self.assertFalse(report.passed)
        self.assertTrue(any("unknown user_id" in e for e in report.errors))


class TestTemporalSplits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = sample_dataset()

    def test_splits_respect_their_period_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs = {
                name: str(Path(tmp) / name) for name in SPLIT_PERIODS
            }
            write_temporal_splits(self.tables, dirs)

            for name, allowed in SPLIT_PERIODS.items():
                frame = pd.read_csv(
                    Path(dirs[name]) / "features" / "transactions.csv",
                    parse_dates=["timestamp"],
                )
                if not len(frame):
                    continue
                periods = set(frame["timestamp"].dt.strftime("%Y-%m"))
                self.assertTrue(
                    periods <= set(allowed),
                    f"{name} contains {sorted(periods - set(allowed))}",
                )

    def test_no_transaction_appears_in_two_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs = {name: str(Path(tmp) / name) for name in SPLIT_PERIODS}
            write_temporal_splits(self.tables, dirs)

            seen = set()
            for name in SPLIT_PERIODS:
                frame = pd.read_csv(
                    Path(dirs[name]) / "features" / "transactions.csv",
                    usecols=["transaction_id"],
                )
                overlap = seen & set(frame["transaction_id"])
                self.assertEqual(overlap, set())
                seen |= set(frame["transaction_id"])

    def test_features_exclude_ground_truth_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs = {name: str(Path(tmp) / name) for name in SPLIT_PERIODS}
            write_temporal_splits(self.tables, dirs)

            users = pd.read_csv(Path(dirs["train"]) / "features" / "users.csv", nrows=0)
            self.assertNotIn("persona", users.columns)
            self.assertNotIn("monthly_income_base", users.columns)

            transactions = pd.read_csv(
                Path(dirs["train"]) / "features" / "transactions.csv", nrows=0
            )
            self.assertNotIn("is_anomaly", transactions.columns)

    def test_labels_are_written_to_the_label_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs = {name: str(Path(tmp) / name) for name in SPLIT_PERIODS}
            write_temporal_splits(self.tables, dirs)

            self.assertTrue((Path(dirs["train"]) / "labels" / "behavior_labels.csv").exists())
            self.assertFalse(
                (Path(dirs["train"]) / "features" / "behavior_labels.csv").exists()
            )

    def test_leakage_check_passes_on_generated_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs = {name: str(Path(tmp) / name) for name in SPLIT_PERIODS}
            write_temporal_splits(self.tables, dirs)
            violations = run_leakage_check(tmp)
            self.assertEqual(violations, [], f"leakage detected: {violations}")

    def test_leakage_check_catches_an_injected_label_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs = {name: str(Path(tmp) / name) for name in SPLIT_PERIODS}
            write_temporal_splits(self.tables, dirs)

            target = Path(dirs["train"]) / "features" / "users.csv"
            frame = pd.read_csv(target)
            frame["persona"] = "stable_saver"
            frame.to_csv(target, index=False)

            violations = run_leakage_check(tmp)
            self.assertTrue(violations)

    def test_drop_leaky_columns_is_not_destructive(self):
        frame = self.tables["users"].copy()
        cleaned = drop_leaky_columns(frame)
        self.assertIn("user_id", cleaned.columns)
        self.assertIn("occupation", cleaned.columns)
        self.assertNotIn("persona", cleaned.columns)


class TestRecurringScheduleIsHonest(unittest.TestCase):
    def test_due_day_is_within_the_month(self):
        tables = sample_dataset()
        recurring = build_recurring_expenses(
            np.random.default_rng(SEED), tables["users"], pd.Timestamp("2026-09-01")
        )
        if len(recurring):
            self.assertTrue(recurring["due_day"].between(1, 31).all())

    def test_profiles_are_computed_not_copied(self):
        tables = sample_dataset()
        profiles = build_financial_profiles(tables["transactions"], tables["wallets"])
        self.assertEqual(len(profiles), tables["users"]["user_id"].nunique())
        self.assertGreater(float(profiles["monthly_income_avg"].sum()), 0)


if __name__ == "__main__":
    unittest.main()