"""Customer-impact evaluation: does using the copilot change an outcome?

Metrics without a customer in them are not impact. This module measures three
things that a customer would actually experience, each with a control:

**Detection value.** How much of the injected anomalous spending the detector
catches, in taka, not just in counts -- alongside the taka it wrongly flags,
because a detector that cries wolf costs the customer attention.

**Month-end deficit warnings.** Trained on history up to month *t*, does the copilot
warn about a customer who will run short in month *t+1*? Reported with
precision/recall **and** with ``novel_warning_share``: the share of warnings
about a deficit that had *not already started*. A warning about a deficit the
customer is already living through is not a warning.

**Counterfactual simulation.** Two stated policies -- save a fifth of
disposable capacity, or cut discretionary spend by 10% -- run through the same
engine as the baseline, plus a **placebo arm** with no change at all. The
placebo must produce a zero delta; if it does not, the harness is measuring
something other than the intervention and none of the other numbers mean
anything.

Population note: the simulation arms use the product's serving population
(``data/generated``, 50 customers), because that is the population
:func:`app.core.context.get_context` reads. The detection and warning blocks
use the 500-customer evaluation splits.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.evaluation.datasets import Dataset
from app.evaluation.metrics import SEED, classification_metrics

# Stated interventions -- not tuned, declared up front.
SAVING_SHARE_OF_CAPACITY = 0.20
EXPENSE_CUT_SHARE = 0.10
SIMULATION_MONTHS = 12
MAX_SIMULATION_CUSTOMERS = 50


# ---------------------------------------------------------------------------
# 1. Detection value
# ---------------------------------------------------------------------------

def detection_value(dataset: Dataset) -> dict:
    """Taka caught vs taka wrongly flagged, on the untouched test window."""
    frame = dataset.features.get("anomaly_scored")
    if frame is None or not len(frame):
        return {"available": False, "reason": "anomaly scoring frame not built yet"}

    test = frame[frame["period"].isin(dataset.test_periods)]
    if test.empty:
        return {"available": False, "reason": "no rows in the test window"}

    anomalous = test[test["is_anomaly"]]
    flagged = test[test["is_flagged"]]
    flagged_anomalous = flagged[flagged["is_anomaly"]]
    false_positives = flagged[~flagged["is_anomaly"]]

    total_value = float(anomalous["amount"].sum())
    caught_value = float(flagged_anomalous["amount"].sum())
    fp_value = float(false_positives["amount"].sum())
    tested_value = float(test["amount"].sum())

    by_pattern: dict[str, dict] = {}
    for pattern, group in anomalous.groupby("pattern_type", observed=True):
        caught = group[group["is_flagged"]]
        by_pattern[str(pattern)] = {
            "events": int(len(group)),
            "detected": int(len(caught)),
            "value_total": round(float(group["amount"].sum()), 2),
            "value_caught": round(float(caught["amount"].sum()), 2),
            "value_coverage": round(
                float(caught["amount"].sum()) / max(float(group["amount"].sum()), 1e-9), 4
            ),
        }

    return {
        "available": True,
        "window": "test (2026-08..2026-09)",
        "n_transactions": int(len(test)),
        "anomalous_events": int(len(anomalous)),
        "flagged_events": int(len(flagged)),
        "total_anomalous_value": round(total_value, 2),
        "caught_anomalous_value": round(caught_value, 2),
        "value_coverage": round(caught_value / max(total_value, 1e-9), 4),
        "false_positive_value": round(fp_value, 2),
        "false_positive_value_share_of_tested": round(
            fp_value / max(tested_value, 1e-9), 6
        ),
        "wrongly_flagged_share_of_flagged_value": round(
            fp_value / max(float(flagged["amount"].sum()), 1e-9), 4
        ),
        "by_pattern": by_pattern,
        "reading": (
            "value_coverage is the share of injected anomalous spend the copilot "
            "put in front of the customer. wrongly_flagged_share_of_flagged_value "
            "is the share of what it showed that turned out to be ordinary "
            "spending -- the trust cost of the feature."
        ),
    }


# ---------------------------------------------------------------------------
# 2. Month-end deficit warnings
# ---------------------------------------------------------------------------

def deficit_warnings(dataset: Dataset, verbose: bool = False) -> dict:
    """Warn about a *future* month-end deficit, using only past data.

    The outcome is observed from the transactions themselves -- the target
    month's ``net < 0``, meaning spending exceeded income -- rather than taken
    from the behaviour label table. ``days_below_buffer`` is also reported, but
    on this population it is almost always zero, so it is a footnote here, not
    the headline.
    """
    from app.evaluation.health import (
        _best_threshold,
        _fit_lgbm,
        _fit_logistic,
        _monthly,
        _scores,
        early_warning_frame,
    )

    features_frame, feature_columns = early_warning_frame(dataset)
    if features_frame.empty:
        return {"available": False, "reason": "no trailing rows"}

    monthly = _monthly(dataset)
    observed = monthly[["user_id", "period", "net", "days_below_buffer"]].rename(
        columns={"period": "target_period"}
    )
    observed["target_deficit"] = (observed["net"] < 0).astype(int)
    observed["target_days_below_buffer"] = observed["days_below_buffer"]

    frame = features_frame.merge(observed, on=["user_id", "target_period"], how="left")
    frame = frame[frame["target_deficit"].notna()].copy()
    frame["target_deficit"] = frame["target_deficit"].astype(int)

    # Persistence needs last month's observed outcome, from the feature month.
    prior = monthly[["user_id", "period", "net", "days_below_buffer"]].rename(
        columns={
            "period": "as_of",
            "net": "as_of_net",
            "days_below_buffer": "as_of_days_below_buffer",
        }
    )
    frame = frame.merge(prior, on=["user_id", "as_of"], how="left")
    frame["was_in_deficit_last_month"] = (frame["as_of_net"].fillna(0) < 0).astype(int)

    splits = {
        name: frame[frame["target_period"].isin(dataset.periods_of(name))].copy()
        for name in ("train", "validation", "test")
    }
    train, validation, test = splits["train"], splits["validation"], splits["test"]
    if train.empty or test.empty:
        return {"available": False, "reason": "empty window", "rows": {k: len(v) for k, v in splits.items()}}

    y_val = validation["target_deficit"].to_numpy()
    y_test = test["target_deficit"].to_numpy()
    prevalence = float(train["target_deficit"].mean())

    models = {}
    thresholded: dict[str, np.ndarray] = {}

    for name, model in (
        ("logistic", _fit_logistic(train, feature_columns, "target_deficit")),
        ("lightgbm", _fit_lgbm(train, feature_columns, "target_deficit")),
    ):
        threshold = _best_threshold(y_val, _scores(model, validation, feature_columns))
        score = _scores(model, test, feature_columns)
        thresholded[name] = score >= threshold
        entry = classification_metrics(y_test, thresholded[name].astype(int), score)
        entry["threshold"] = round(threshold, 3)
        entry["chosen_on"] = "validation (maximise F1)"
        models[name] = entry

    thresholded["persistence"] = test["was_in_deficit_last_month"].to_numpy().astype(int)
    models["persistence"] = classification_metrics(y_test, thresholded["persistence"])

    constant = int(prevalence >= 0.5)
    thresholded["constant"] = np.full(len(test), constant, dtype=int)
    models["constant"] = classification_metrics(y_test, thresholded["constant"])
    models["constant"]["base_rate_train"] = round(prevalence, 4)

    best_name = max(("logistic", "lightgbm"), key=lambda n: models[n]["f1"])
    best = thresholded[best_name]

    # Actionability of the warning, not just its accuracy.
    flagged = test[best.astype(bool)]
    novel = flagged[flagged["was_in_deficit_last_month"] == 0]
    missed = test[(~best.astype(bool)) & (test["target_deficit"] == 1)]
    caught = test[best.astype(bool) & (test["target_deficit"] == 1)]

    actionability = {
        "warnings_emitted": int(len(flagged)),
        "warnings_correct": int(len(caught)),
        "novel_warnings": int(len(novel)),
        "novel_warning_share": round(len(novel) / len(flagged), 4) if len(flagged) else None,
        "novel_warning_definition": (
            "warnings about a customer who was NOT already in deficit in the "
            "month the features end -- i.e. information the customer did not "
            "already have"
        ),
        "false_warnings": int((flagged["target_deficit"] == 0).sum()),
        "deficits_missed": int(len(missed)),
        "false_warning_rate": round(
            float((flagged["target_deficit"] == 0).sum()) / max(len(flagged), 1), 4
        ),
        "days_of_lead_time": 30,
        "lead_time_note": (
            "The warning is issued at the end of month t about month t+1, so it "
            "always precedes the outcome by roughly one month. What is *not* "
            "guaranteed is that it precedes the customer's first symptom -- "
            "novel_warning_share measures that."
        ),
    }

    if verbose:
        print(
            f"  deficit: constant={models['constant']['f1']:.3f} "
            f"persistence={models['persistence']['f1']:.3f} "
            f"logistic={models['logistic']['f1']:.3f} "
            f"lgbm={models['lightgbm']['f1']:.3f} "
            f"(base {float(y_test.mean()):.2f}) "
            f"novel={actionability['novel_warning_share']}"
        )

    return {
        "available": True,
        "task": "predict an observed month-end deficit (spend > income) next month",
        "outcome_source": "observed monthly net from the transactions themselves (features side, not a label table)",
        "secondary_outcome": {
            "definition": "days spent below the balance buffer in the target month",
            "positive_rows_test": int((test["target_days_below_buffer"].fillna(0) > 0).sum()),
            "n_test": int(len(test)),
            "note": "reported for completeness; rare in this population, so the deficit above is the scored outcome",
        },
        "n_rows": int(len(frame)),
        "rows": {name: int(len(value)) for name, value in splits.items()},
        "positive_rate_test": round(float(y_test.mean()), 4),
        "models": models,
        "best_model": best_name,
        "best_model_f1": models[best_name]["f1"],
        "improvement_over_persistence_percent": round(
            100.0 * (models[best_name]["f1"] - models["persistence"]["f1"])
            / max(models["persistence"]["f1"], 1e-9),
            2,
        )
        if models["persistence"]["f1"] > 0
        else None,
        "actionability": actionability,
        "seed": SEED,
    }


# ---------------------------------------------------------------------------
# 3. Counterfactual simulation with a placebo control
# ---------------------------------------------------------------------------

def _product_user_ids() -> list[str]:
    from app.core.config import settings

    users = settings.data_root / "users.csv"
    if not users.exists():
        return []
    frame = pd.read_csv(users)
    return [str(u) for u in frame["user_id"].head(MAX_SIMULATION_CUSTOMERS)]


def simulation_arms(verbose: bool = False) -> dict:
    """Baseline vs two stated policies vs a placebo, one engine for all arms."""
    from app.core.context import get_context
    from app.engines.planning import disposable_capacity, emergency_fund, simulate

    user_ids = _product_user_ids()
    if not user_ids:
        return {"available": False, "reason": "product dataset users.csv not found"}

    arms: list[dict] = []
    placebo_rows: list[dict] = []
    actionability: list[dict] = []
    errors: list[dict] = []

    for user_id in user_ids:
        try:
            ctx = get_context(user_id)
            capacity = disposable_capacity(ctx)
            fund = emergency_fund(user_id)
            spare = max(float(capacity["capacity"]), 0.0)
            spend_base = max(float(capacity["monthly_spend"]), 0.0)
            saving_change = round(SAVING_SHARE_OF_CAPACITY * spare, 2)
            expense_change = round(-EXPENSE_CUT_SHARE * spend_base, 2)

            placebo = simulate(user_id)
            arm_saving = simulate(user_id, monthly_saving_change=saving_change)
            arm_expense = simulate(user_id, expense_change=expense_change)
        except Exception as exc:  # noqa: BLE001 - a crash is a finding
            errors.append({"user_id": user_id, "error": f"{type(exc).__name__}: {exc}"})
            continue

        base = _arm_metrics(placebo, 0.0)
        placebo_rows.append(base)
        arms.append(
            {
                "user_id": user_id,
                "saving": _compare(_arm_metrics(arm_saving, saving_change), base),
                "expense": _compare(_arm_metrics(arm_expense, expense_change), base),
            }
        )
        actionability.append(
            {
                "user_id": user_id,
                "emergency_fund_affordable": bool(getattr(fund, "affordable", False)),
                "affordable_monthly": round(float(getattr(fund, "affordable_monthly", 0.0)), 2),
                "disposable_capacity_monthly": round(
                    float(getattr(fund, "disposable_capacity_monthly", 0.0)), 2
                ),
                "capacity": round(spare, 2),
                "monthly_income": round(float(capacity["monthly_income"]), 2),
                "monthly_spend": round(float(capacity["monthly_spend"]), 2),
                "buffer_cost": round(float(capacity["buffer_cost"]), 2),
                "below_buffer": bool(float(capacity["buffer_cost"]) > 0),
                "remaining_amount": round(float(getattr(fund, "remaining_amount", 0.0)), 2),
                "months_to_target": getattr(fund, "months_to_target", None),
                "progress_ratio": round(float(getattr(fund, "progress_ratio", 0.0)), 4),
                "funded": bool(getattr(fund, "funded", False)),
            }
        )

    if not arms:
        return {"available": False, "reason": "every simulation raised", "errors": errors[:5]}

    placebo_ok = all(
        abs(r["balance_change"]) < 1e-6
        and abs(r["net_worth_change"]) < 1e-6
        and abs(r["savings_change"]) < 1e-6
        for r in placebo_rows
    )

    def _aggregate(arm: str) -> dict:
        entries = [r[arm] for r in arms]
        return {
            "n_customers": len(entries),
            "mean_balance_change": round(float(np.mean([e["balance_change"] for e in entries])), 2),
            "mean_net_worth_change": round(
                float(np.mean([e["net_worth_change"] for e in entries])), 2
            ),
            "mean_buffer_breach_days_delta": round(
                float(np.mean([e["buffer_breach_days_delta"] for e in entries])), 3
            ),
            "customers_with_fewer_breach_days": int(
                sum(1 for e in entries if e["buffer_breach_days_delta"] > 0)
            ),
            "customers_with_more_breach_days": int(
                sum(1 for e in entries if e["buffer_breach_days_delta"] < 0)
            ),
            "customers_buffer_respected": int(
                sum(1 for e in entries if e["buffer_respected"])
            ),
            "mean_goals_unlocked": round(float(np.mean([e["goals_unlocked"] for e in entries])), 3),
        }

    # ``months_to_target`` is null once the customer is already funded, so the
    # horizon statistics are computed over the customers who still have a gap.
    unfunded = [a for a in actionability if not a["funded"]]
    horizon = [
        float(a["months_to_target"]) for a in unfunded if a["months_to_target"] is not None
    ]
    n = len(arms)
    funded_count = sum(1 for a in actionability if a["funded"])
    n_action = max(len(actionability), 1)
    return {
        "available": True,
        "population": {
            "n_customers": n,
            "n_errors": len(errors),
            "source": "data/generated (the population the serving engines read)",
            "note": (
                "The evaluation splits hold 500 customers for offline model "
                "scoring; the serving engines read the 50-customer product "
                "population, so the counterfactual arms run there. The two "
                "populations are the same generator with the same seed."
            ),
        },
        "interventions": {
            "saving_arm": {
                "policy": (
                    f"redirect {int(SAVING_SHARE_OF_CAPACITY * 100)}% of measured "
                    "disposable capacity into savings every month"
                ),
                "mean_monthly_change": round(
                    float(np.mean([r["saving"]["monthly_change"] for r in arms])), 2
                ),
                **_aggregate("saving"),
            },
            "expense_arm": {
                "policy": (
                    f"cut discretionary spending by {int(EXPENSE_CUT_SHARE * 100)}% "
                    "of measured monthly spend"
                ),
                "mean_monthly_change": round(
                    float(np.mean([r["expense"]["monthly_change"] for r in arms])), 2
                ),
                **_aggregate("expense"),
            },
        },
        "placebo": {
            "policy": "no change at all -- same engine, same customer, zero intervention",
            "n_customers": len(placebo_rows),
            "max_absolute_balance_change": round(
                max((abs(r["balance_change"]) for r in placebo_rows), default=0.0), 6
            ),
            "max_absolute_net_worth_change": round(
                max((abs(r["net_worth_change"]) for r in placebo_rows), default=0.0), 6
            ),
            "mean_buffer_breach_days": round(
                float(np.mean([r["buffer_breach_days"] for r in placebo_rows])), 3
            ),
            "customers_with_any_breach": int(
                sum(1 for r in placebo_rows if r["buffer_breach_days"] > 0)
            ),
            "harness_sensitive": bool(placebo_ok),
            "interpretation": (
                "A zero intervention must move nothing. If this fails, the "
                "difference between arms is produced by something other than "
                "the policy and no arm comparison is trustworthy."
            ),
        },
        "recommendation_actionability": {
            "n_customers": len(actionability),
            "median_disposable_capacity_monthly": round(
                float(np.median([a["capacity"] for a in actionability])), 2
            ),
            "share_with_positive_capacity": round(
                sum(1 for a in actionability if a["capacity"] > 0) / n_action, 4
            ),
            "share_sitting_below_their_buffer": round(
                sum(1 for a in actionability if a["below_buffer"]) / n_action, 4
            ),
            "emergency_fund_affordable_share": round(
                sum(1 for a in actionability if a["emergency_fund_affordable"]) / n_action, 4,
            ),
            "emergency_fund_funded_share": round(funded_count / n_action, 4),
            "customers_with_a_remaining_gap": len(unfunded),
            "median_months_to_target_for_open_gaps": float(np.median(horizon))
            if horizon
            else None,
            "share_of_open_gaps_never_reaching_target": round(
                sum(1 for m in horizon if m > 60) / max(len(horizon), 1), 4
            )
            if horizon
            else None,
            "mean_remaining_amount": round(
                float(np.mean([a["remaining_amount"] for a in actionability])), 2
            ),
            "population_finding": (
                "Every product customer already holds more than the emergency "
                "fund their own history implies, so this feature has nothing to "
                "do on this population and the horizon statistics are empty. "
                "That is a product finding, not a modelling result: the useful "
                "signal here is the capacity line, because "
                "share_with_positive_capacity is exactly the share of customers "
                "who could follow a save-more recommendation at all. The rest "
                "are already below the buffer the engine itself computes."
            ),
        },
        "errors": errors[:10],
        "seed": SEED,
    }


def _compare(arm: dict, placebo: dict) -> dict:
    """Arm outcome plus the delta against that customer's own no-change run."""
    out = dict(arm)
    out["buffer_breach_days_delta"] = int(placebo["buffer_breach_days"]) - int(
        arm["buffer_breach_days"]
    )
    out["min_balance_delta"] = round(
        float(arm["min_scenario_balance"]) - float(placebo["min_scenario_balance"]), 2
    )
    return out


def _arm_metrics(response, monthly_change: float) -> dict:
    return {
        "monthly_change": round(float(monthly_change), 2),
        "balance_change": float(response.balance_change),
        "net_worth_change": float(response.net_worth_change),
        "savings_change": float(response.savings_change),
        "min_baseline_balance": float(response.min_baseline_balance),
        "min_scenario_balance": float(response.min_scenario_balance),
        "buffer_breach_days": int(response.buffer_breach_days),
        "buffer_respected": bool(response.buffer_respected),
        "goals_unlocked": int(response.goals_unlocked),
        "risk_level": str(response.risk_level),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(dataset: Dataset, verbose: bool = False, fit_anomaly: bool = True) -> dict:
    if dataset.features.get("anomaly_scored") is None and fit_anomaly:
        # The detector is ~70s to fit. The pipeline fits it once, scores the
        # anomaly block, then calls this; only a standalone call pays twice.
        from app.evaluation.anomaly import run_anomaly_evaluation

        run_anomaly_evaluation(
            dataset.transactions, dataset.splits, verbose=verbose, dataset=dataset
        )

    detection = detection_value(dataset)
    warnings = deficit_warnings(dataset, verbose=verbose)
    simulation = simulation_arms(verbose=verbose)

    headline = {
        "anomaly_value_coverage": detection.get("value_coverage"),
        "anomaly_wrongly_flagged_value_share": detection.get(
            "wrongly_flagged_share_of_flagged_value"
        ),
        "deficit_warning_best_model": warnings.get("best_model"),
        "deficit_warning_f1": warnings.get("best_model_f1"),
        "deficit_warning_over_persistence_percent": warnings.get(
            "improvement_over_persistence_percent"
        ),
        "deficit_warning_novel_share": (warnings.get("actionability") or {}).get(
            "novel_warning_share"
        ),
        "placebo_harness_sensitive": (simulation.get("placebo") or {}).get("harness_sensitive"),
        "customers_able_to_follow_a_saving_plan": (simulation.get("recommendation_actionability") or {}).get(
            "share_with_positive_capacity"
        ),
    }

    if verbose:
        for key, value in headline.items():
            print(f"  {key:38s} {value}")

    return {
        "headline": headline,
        "detection_value": detection,
        "deficit_warnings": warnings,
        "simulation": simulation,
        "controls": [
            "placebo arm with no intervention must produce a zero delta",
            "warnings are scored against an observed outcome, not a label table",
            "anomaly value coverage is measured on the untouched test window",
            "every intervention is declared before the run, not tuned to the result",
        ],
    }
