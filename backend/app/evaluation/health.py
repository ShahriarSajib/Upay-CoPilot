"""Financial-health model evaluation, plus a genuinely temporal task.

Two evaluations, deliberately side by side
------------------------------------------
**A. Profile calibration.** Predict the generator's ``financial_profiles`` and
``behavior_labels`` from behavioural features. This is the honest, weak result
and it is reported as such: three of the four regression targets are *defined*
from the same aggregates the features are built from, so a plain copy of the
engine feature is already near-perfect. The verdict ``no_gain_over_rule`` is the
correct reading, not a failure to be hidden -- see
:func:`app.ml.health.leakage_by_construction_note`.

**B. Early warning.** The task that *is* a real prediction. Given the ledger up
to month *t*, will the customer end month *t+1* in shortage? The label is a
strictly future period, the features are strictly past, and the answer cannot
be copied off any feature because the feature for month *t+1* does not exist
yet. Four estimators compete:

``persistence``      "short last month -> short next month"
``majority``         base rate from the training window
``logistic``         regularised logistic regression on trailing aggregates
``lightgbm``         LightGBM on the identical frame

The operating threshold for both learned models is chosen on the validation
window; test is scored once, untouched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.evaluation.datasets import Dataset
from app.evaluation.metrics import SEED, classification_metrics

# Ground-truth-derived columns that must not become features.
FORBIDDEN_FEATURES = ("anomaly_events", "anomaly_count")

# Behaviour flags that are genuinely period-scoped outcomes.
EARLY_WARNING_TARGETS = (
    "end_month_shortage",
    "high_cash_dependency",
    "irregular_income",
    "overspending",
    "financial_pressure",
)

MIN_HISTORY_MONTHS = 2

TRAILING_WINDOWS = (1, 3)


# ---------------------------------------------------------------------------
# Early-warning frame
# ---------------------------------------------------------------------------

def _monthly(dataset: Dataset) -> pd.DataFrame:
    def build() -> pd.DataFrame:
        from app.features.build import _reindex_calendar, daily_features, monthly_features

        daily = _reindex_calendar(daily_features(dataset.transactions, dataset.wallets))
        return monthly_features(daily, dataset.contributions, dataset.goals)

    if dataset.monthly is None:
        dataset.monthly = build()
    return dataset.monthly


def early_warning_frame(dataset: Dataset) -> tuple[pd.DataFrame, list[str]]:
    """(user, as_of) rows -> next-period behaviour labels.

    Features are the trailing aggregates of months ``<= as_of``. The target is
    the behaviour flag of the month *after* ``as_of``. No feature is computed
    from the target month.
    """
    monthly = _monthly(dataset).copy()
    for column in FORBIDDEN_FEATURES:
        monthly = monthly.drop(columns=[column], errors="ignore")

    labels = dataset.behaviour_labels.copy()
    flags = labels.set_index(["user_id", "period"])

    base = [
        "savings_rate",
        "late_share",
        "cash_share",
        "expense_income_ratio",
        "recurring_share",
        "small_share",
        "days_below_buffer",
        "income",
        "spend",
        "net",
        "ending_balance",
        "min_balance",
        "txn_count",
        "goal_contribution",
    ]
    base = [c for c in base if c in monthly.columns]

    rows: list[dict] = []
    for user_id, group in monthly.groupby("user_id", observed=True, sort=False):
        group = group.sort_values("period").reset_index(drop=True)
        if len(group) < MIN_HISTORY_MONTHS + 1:
            continue
        values = {column: group[column].to_numpy(dtype=float) for column in base}
        periods = group["period"].tolist()

        for index in range(MIN_HISTORY_MONTHS - 1, len(group) - 1):
            as_of = periods[index]
            target_period = periods[index + 1]
            row: dict = {"user_id": user_id, "as_of": as_of, "target_period": target_period}

            # Trailing levels and means strictly up to and including as_of.
            for column in base:
                series = values[column]
                row[f"{column}_last"] = series[index]
                for window in TRAILING_WINDOWS:
                    start = max(0, index - window + 1)
                    row[f"{column}_mean{window}"] = float(np.mean(series[start : index + 1]))
            spend = values["spend"]
            income = values["income"]
            trailing_spend = float(np.mean(spend[max(0, index - 2) : index + 1]))
            trailing_income = float(np.mean(income[max(0, index - 2) : index + 1]))
            row["buffer_months"] = (
                float(values["ending_balance"][index]) / max(trailing_spend, 1.0)
            )
            row["spend_trend"] = float(spend[index] - np.mean(spend[max(0, index - 2) : index]))
            row["income_cv_3"] = float(
                np.std(income[max(0, index - 2) : index + 1], ddof=0)
                / max(trailing_income, 1.0)
            )
            row["expense_ratio_trailing"] = trailing_spend / max(trailing_income, 1.0)
            row["min_balance_to_spend"] = float(values["min_balance"][index]) / max(
                trailing_spend, 1.0
            )

            for target in EARLY_WARNING_TARGETS:
                column = f"{target}_label"
                if (user_id, target_period) in flags.index and column in flags.columns:
                    row[target] = int(flags.loc[(user_id, target_period), column])
                else:
                    row[target] = np.nan

            rows.append(row)

    frame = pd.DataFrame(rows)
    feature_columns = [c for c in frame.columns if c not in {"user_id", "as_of", "target_period", *EARLY_WARNING_TARGETS}]
    return frame, feature_columns


def split_early_warning(frame: pd.DataFrame, dataset: Dataset) -> dict[str, pd.DataFrame]:
    """Assign each row to a window by its *target* month, not its as-of month."""
    return {
        name: frame[frame["target_period"].isin(dataset.periods_of(name))].copy()
        for name in ("train", "validation", "test")
    }


# ---------------------------------------------------------------------------
# Estimators
# ---------------------------------------------------------------------------

def _fit_logistic(train: pd.DataFrame, features: list[str], target: str, seed: int = SEED):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    y = train[target].astype(int).to_numpy()
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced", random_state=seed),
    )
    model.fit(train[features].replace([np.inf, -np.inf], np.nan).fillna(0.0), y)
    return model


def _fit_lgbm(train: pd.DataFrame, features: list[str], target: str, seed: int = SEED):
    from lightgbm import LGBMClassifier

    y = train[target].astype(int).to_numpy()
    model = LGBMClassifier(
        objective="binary",
        n_estimators=200,
        learning_rate=0.04,
        num_leaves=7,
        min_child_samples=20,
        subsample=0.9,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=30.0,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(train[features].replace([np.inf, -np.inf], np.nan).fillna(0.0), y)
    return model


def _scores(model, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    matrix = frame[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if hasattr(model, "predict_proba"):
        return model.predict_proba(matrix)[:, 1]
    return np.asarray(model.decision_function(matrix), dtype=float)


def _best_threshold(y_true: np.ndarray, score: np.ndarray) -> float:
    """Threshold on validation maximising F1, searched on a fixed grid."""
    grid = np.arange(0.05, 0.951, 0.05)
    best = (0.5, -1.0)
    for threshold in grid:
        f1 = classification_metrics(y_true, (score >= threshold).astype(int))["f1"]
        if f1 > best[1]:
            best = (float(threshold), float(f1))
    return best[0]


# ---------------------------------------------------------------------------
# Evaluation A: profile calibration
# ---------------------------------------------------------------------------

def run_profile_calibration(dataset: Dataset, verbose: bool = False) -> dict:
    from app.ml import health as ml_health

    profile = dataset.splits["train"].label("financial_profiles")
    behaviour = dataset.splits["train"].label("behavior_labels")
    if profile.empty:
        return {"fitted": False, "reason": "financial_profiles.csv is empty"}

    folds: dict[str, pd.DataFrame] = {}
    for cut in ("train", "validation", "test"):
        features = dataset.build_frame(f"features_{cut}", lambda c=cut: _features_for(dataset, c))
        folds[cut] = ml_health.supervised_frame(features, profile, behaviour)

    bundle = ml_health.train_health_models(folds["train"])
    bundle["train_matrix"] = ml_health.design_matrix(folds["train"], bundle["features"])

    evaluation: dict = {
        "skipped": bundle["skipped"],
        "folds": {
            cut: ml_health.evaluate(bundle, folds[cut], folds["train"])
            for cut in ("validation", "test")
        },
        "direct_feature_baseline": ml_health.direct_feature_baseline(folds["test"]),
        "null_control": ml_health.null_control(folds["train"], folds["test"]),
        "caveat": ml_health.leakage_by_construction_note(),
    }
    evaluation["honest_verdict"] = ml_health.honest_verdict(
        evaluation["folds"]["test"],
        evaluation["direct_feature_baseline"],
        evaluation["null_control"],
    )

    verdicts = evaluation["honest_verdict"]
    counts: dict[str, int] = {}
    for row in verdicts:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    if verbose:
        for row in verdicts:
            if row.get("task") == "regression":
                print(
                    f"  {row['target']:24s} {row['verdict']:26s} "
                    f"MAE={row['model_mae']:.4f} direct={row['direct_feature_baseline_mae']}"
                )
            else:
                print(
                    f"  {row['target']:24s} {row['verdict']:26s} "
                    f"F1={row['model_f1']:.3f} majority={row['majority_baseline_f1']}"
                )

    return {
        "fitted": True,
        "task": "recover the generator's ground-truth financial profile from behaviour",
        "design": "expanding windows: validation cut = 2026-01..07, test cut = 2026-01..09",
        "protected_attributes_excluded": list(ml_health.PROTECTED_COLUMNS),
        "features": bundle["features"],
        "evaluation": evaluation,
        "verdict_counts": counts,
        "_bundle": bundle,
        "_folds": folds,
    }


def _features_for(dataset: Dataset, cut: str) -> pd.DataFrame:
    """The same expanding-window user frame the trainer uses.

    :func:`app.data.splits.build_features` rebuilds the whole feature pipeline
    from every month up to the cut, which is what makes the validation and test
    folds honest for a full-horizon label. Reading the shipped
    ``features/users.csv`` would be cheaper but is a different construction, so
    the trainer's path is used here to keep the two reports comparable.
    """
    from app.data.splits import build_features

    return build_features(cut).user


# ---------------------------------------------------------------------------
# Evaluation B: early warning
# ---------------------------------------------------------------------------

def run_early_warning(dataset: Dataset, verbose: bool = False) -> dict:
    """Predict next-period behaviour flags from strictly trailing history."""
    frame, features = early_warning_frame(dataset)
    if frame.empty:
        return {"fitted": False, "reason": "no usable (user, as_of) rows"}

    splits = split_early_warning(frame, dataset)
    if verbose:
        print(
            "  rows: "
            + ", ".join(f"{name}={len(value)}" for name, value in splits.items())
        )

    train = splits["train"]
    validation = splits["validation"]
    test = splits["test"]
    if train.empty or validation.empty or test.empty:
        return {
            "fitted": False,
            "reason": "a window is empty",
            "row_counts": {k: int(len(v)) for k, v in splits.items()},
        }

    results: dict[str, dict] = {}
    for target in EARLY_WARNING_TARGETS:
        if target not in train.columns:
            continue
        usable_train = train[train[target].notna()]
        usable_validation = validation[validation[target].notna()]
        usable_test = test[test[target].notna()]
        if usable_train[target].sum() == 0 or usable_validation[target].sum() == 0:
            results[target] = {"available": False, "reason": "no positives in train/validation"}
            continue

        y_val = usable_validation[target].astype(int).to_numpy()
        y_test = usable_test[target].astype(int).to_numpy()
        prevalence = float(usable_train[target].mean())

        logistic = _fit_logistic(usable_train, features, target)
        lgbm = _fit_lgbm(usable_train, features, target)

        thresholds = {
            "logistic": _best_threshold(y_val, _scores(logistic, usable_validation, features)),
            "lightgbm": _best_threshold(y_val, _scores(lgbm, usable_validation, features)),
        }

        models: dict[str, dict] = {}
        # Persistence: last month's flag, straight off the behaviour table.
        models["persistence"] = _score_persistence(dataset, usable_test, target)
        models["constant"] = _score_constant(usable_validation, usable_test, target, prevalence)

        for name, model, threshold in (
            ("logistic", logistic, thresholds["logistic"]),
            ("lightgbm", lgbm, thresholds["lightgbm"]),
        ):
            score = _scores(model, usable_test, features)
            entry = classification_metrics(y_test, (score >= threshold).astype(int), score)
            entry["threshold"] = round(threshold, 3)
            entry["chosen_on"] = "validation (maximise F1)"
            models[name] = entry

        base = models["constant"]["f1"]
        best_model = max(
            (n for n in models if n in ("logistic", "lightgbm")),
            key=lambda n: models[n]["f1"],
        )
        results[target] = {
            "positive_rate_test": round(float(y_test.mean()), 4),
            "n_train": int(len(usable_train)),
            "n_validation": int(len(usable_validation)),
            "n_test": int(len(usable_test)),
            "models": models,
            "best_model": best_model,
            "best_model_f1": models[best_model]["f1"],
            "improvement_over_constant_percent": (
                round(100.0 * (models[best_model]["f1"] - base) / max(base, 1e-9), 2)
                if base > 0
                else None
            ),
            "improvement_over_persistence_percent": (
                round(
                    100.0
                    * (models[best_model]["f1"] - models["persistence"]["f1"])
                    / max(models["persistence"]["f1"], 1e-9),
                    2,
                )
                if models["persistence"].get("f1", 0) > 0
                else None
            ),
        }
        if verbose:
            print(
                f"  {target:22s} constant={models['constant']['f1']:.3f} "
                f"persistence={models['persistence'].get('f1', float('nan')):.3f} "
                f"logistic={models['logistic']['f1']:.3f} "
                f"lgbm={models['lightgbm']['f1']:.3f}  "
                f"(base rate {results[target]['positive_rate_test']:.2f})"
            )

    return {
        "fitted": True,
        "task": (
            "predict whether the customer will hit a behaviour flag NEXT month "
            "from the ledger strictly up to this month"
        ),
        "protocol": (
            "Windows are assigned by the target month: train targets 2026-03..05, "
            "validation targets 2026-06..07, test targets 2026-08..09. Features "
            "are trailing aggregates of months strictly before the target month, "
            "so nothing in the design matrix can contain the answer. Learned "
            "thresholds are chosen on validation; test is scored once."
        ),
        "features": features,
        "n_rows": int(len(frame)),
        "row_counts": {name: int(len(value)) for name, value in splits.items()},
        "label_quality": label_quality(dataset),
        "targets": results,
        "seed": SEED,
    }


def label_quality(dataset: Dataset) -> dict:
    """Duplicate / constant / class-balance check on the behaviour labels.

    Run because two of the six flags were found to be *byte-identical* in the
    shipped generator output, which means any "two independent models agree"
    claim built on them would be circular. Detection is automatic rather than
    a hard-coded note, so a regenerated dataset that fixes the duplication is
    reported correctly.
    """
    import itertools

    labels = dataset.behaviour_labels
    columns = [c for c in labels.columns if c.endswith("_label")]
    duplicates: list[dict] = []
    for left, right in itertools.combinations(columns, 2):
        differing = int((labels[left] != labels[right]).sum())
        if differing == 0:
            duplicates.append({"first": left, "second": right, "differing_rows": 0})
        elif differing <= max(3, int(0.001 * len(labels))):
            duplicates.append(
                {"first": left, "second": right, "differing_rows": differing}
            )

    balance = {
        column: {
            "positives": int(labels[column].sum()),
            "rate": round(float(labels[column].mean()), 4),
            "n_rows": int(len(labels)),
        }
        for column in columns
    }
    constants = [c for c, v in balance.items() if v["positives"] in (0, v["n_rows"])]
    return {
        "n_label_rows": int(len(labels)),
        "n_distinct_periods": int(labels["period"].nunique()),
        "balance": balance,
        "duplicate_flags": duplicates,
        "constant_flags": constants,
        "note": (
            "Flags listed under duplicate_flags carry the same information. "
            "Report any pair as one finding, not two confirmations."
        ),
    }


def _score_persistence(dataset: Dataset, frame: pd.DataFrame, target: str) -> dict:
    """Baseline: the flag from the month the features end (as_of), if known."""
    flags = dataset.behaviour_labels.set_index(["user_id", "period"])
    column = f"{target}_label"
    y_true = frame[target].astype(int).to_numpy()
    predicted: list[int] = []
    keep: list[int] = []
    for position, (_, row) in enumerate(frame.iterrows()):
        key = (row["user_id"], row["as_of"])
        if key in flags.index and column in flags.columns:
            predicted.append(int(flags.loc[key, column]))
            keep.append(position)
    if not keep:
        return {"available": False, "reason": "no as_of flag available for persistence"}
    y_true = y_true[keep]
    out = classification_metrics(y_true, np.asarray(predicted, dtype=int))
    out["available"] = True
    out["definition"] = "carry forward last month's observed flag"
    return out


def _score_constant(
    validation: pd.DataFrame, test: pd.DataFrame, target: str, rate: float
) -> dict:
    """Best constant prediction, chosen on validation and scored on test.

    Predicting "never" scores F1 = 0 whenever the flag is rare, which makes the
    baseline look trivially weak. The honest constant is whichever of
    "always" / "never" maximises F1 on the *validation* window -- the same
    information a model gets from its threshold.
    """
    y_val = validation[target].astype(int).to_numpy()
    y_test = test[target].astype(int).to_numpy()

    candidates = {
        "never": np.zeros(len(y_val), dtype=int),
        "always": np.ones(len(y_val), dtype=int),
        "base_rate": (np.full(len(y_val), rate) >= 0.5).astype(int),
    }
    scores = {
        name: classification_metrics(y_val, prediction)["f1"]
        for name, prediction in candidates.items()
    }
    chosen = max(scores, key=scores.get)
    prediction = {
        "never": np.zeros(len(y_test), dtype=int),
        "always": np.ones(len(y_test), dtype=int),
        "base_rate": (np.full(len(y_test), rate) >= 0.5).astype(int),
    }[chosen]

    out = classification_metrics(y_test, prediction)
    out["available"] = True
    out["chosen_constant"] = chosen
    out["validation_f1_by_constant"] = {k: round(v, 4) for k, v in scores.items()}
    out["base_rate_train"] = round(float(rate), 4)
    out["definition"] = (
        "constant predictor whose choice between 'never' and 'always' was made "
        "on the validation window"
    )
    return out
