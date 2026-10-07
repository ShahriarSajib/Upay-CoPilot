"""Financial-health scoring model.

What this model is for
----------------------
``app.engines.health`` already produces a *deterministic, fully auditable*
health score from ladders. That stays the customer-facing number. This module
trains a **calibration layer on top of it**: it predicts the ground-truth
financial profile of a customer from behavioural features only, so that the
product can (a) estimate a customer's profile when history is thin, and
(b) state its own accuracy rather than implying certainty it does not have.

Predicted targets (``data/dev/splits/*/labels/financial_profiles.csv``)
--------------------------------------------------------------------
``savings_rate``             how much of income is kept, in [-1, 1]
``emergency_fund_months``    ending balance in months of average spend
``cash_dependency``          share of spend funded from cash
``income_stability``         1 / (1 + income coefficient of variation)

Behavioural classifiers (``.../labels/behavior_labels.csv``)
----------------------------------------------------------
Six per-period flags, aggregated to one label per customer:
``end_month_shortage``, ``high_cash_dependency``, ``irregular_income``,
``overspending``, ``financial_pressure``, ``goal_progress``.

Fairness: age group, occupation and location type are **dropped** from the
design matrix. They are kept in ``build_features`` for display and for the
fairness report, never as predictors, so the score cannot drift into a proxy
for who the customer is rather than what they do.

Explainability
--------------
LightGBM's ``predict(..., pred_contrib=True)`` returns exact TreeSHAP values,
computed by the model's own C++ code -- mathematically identical to
``shap.TreeExplainer`` without needing the package installed. That is what
:func:`explain` uses, and every served number can quote its own attributions.
``shap`` remains an optional dependency for plot rendering only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.artifacts import json_safe

SEED = 42

# Ground-truth columns are prefixed on merge. Three of the four profile
# targets (``savings_rate``, ``cash_dependency``, ``income_stability``) have
# names that already exist as *features*, so an unprefixed merge silently
# produces ``savings_rate_x`` / ``savings_rate_y``, the label disappears, and
# the trainer quietly skips three of its four targets. The prefix makes the
# distinction impossible to lose.
TARGET_PREFIX = "label_"

# Attributes that must never be used as predictors.
PROTECTED_COLUMNS = ("age_group", "occupation", "location_type", "top_category")

ID_COLUMN = "user_id"

REGRESSION_TARGETS: tuple[str, ...] = (
    "savings_rate",
    "emergency_fund_months",
    "cash_dependency",
    "income_stability",
)


def target_column(name: str) -> str:
    """Where a ground-truth target lives inside the supervised frame."""
    return f"{TARGET_PREFIX}{name}"


# Columns that must never be predictors. Two kinds:
#   * ``label_*`` -- the ground-truth targets themselves, renamed on merge.
#     They are numeric, so a naive "keep the numeric columns" rule picks them
#     up and the model reads the answer straight off the design matrix (this
#     produced R2 ~0.95 and F1 = 1.0 before it was caught).
#   * whole-window aggregates that are derived from the same ledger the labels
#     are derived from, so they restate the answer rather than predict it.
NON_FEATURE_COLUMNS: tuple[str, ...] = (
    "periods_observed",
    "months_observed",
    "monthly_income_avg",
    "monthly_expense_avg",
    "average_monthly_savings",
    "anomaly_count",
    # Derived from the generator's ``is_anomaly`` ground truth, so it is only
    # knowable after the answer is already assigned. Never a predictor.
    "anomaly_events",
)


def is_feature_column(column: str) -> bool:
    """True when a column may enter the design matrix."""
    if column == ID_COLUMN or column in PROTECTED_COLUMNS:
        return False
    if column.startswith(TARGET_PREFIX):
        return False
    if column in NON_FEATURE_COLUMNS:
        return False
    return True


# Label flag -> behaviour labels column name.
CLASSIFICATION_TARGETS: dict[str, str] = {
    "end_month_shortage": "end_month_shortage_label",
    "high_cash_dependency": "high_cash_dependency_label",
    "irregular_income": "irregular_income_label",
    "overspending": "overspending_label",
    "financial_pressure": "financial_pressure_label",
    "goal_progress": "goal_progress_label",
}

# Minimum rows before a classifier is trained at all. Below this the
# minority class has too few examples for a fitted model to beat "always
# predict the majority", and we say so instead of shipping a coin flip.
MIN_CLASSIFIER_ROWS = 40
MIN_POSITIVE_ROWS = 5


def feature_columns(user_frame: pd.DataFrame) -> list[str]:
    """Numeric behavioural columns with targets and protected attrs removed.

    Excluding ``label_*`` here is the single most important leakage control in
    this module: :func:`supervised_frame` merges the ground truth into the same
    frame the features come from, so anything that reads "all numeric columns"
    would hand the model its own answers.
    """
    return [
        column
        for column in user_frame.columns
        if is_feature_column(column) and pd.api.types.is_numeric_dtype(user_frame[column])
    ]


def design_matrix(user_frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    matrix = user_frame[[ID_COLUMN, *columns]].copy()
    matrix[columns] = matrix[columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return matrix


# ---------------------------------------------------------------------------
# Label assembly
# ---------------------------------------------------------------------------

def profile_labels(profile_frame: pd.DataFrame) -> pd.DataFrame:
    """Ground-truth financial profile, one row per user."""
    if profile_frame.empty:
        return pd.DataFrame(columns=["user_id", *REGRESSION_TARGETS])
    out = profile_frame.copy()
    for column in REGRESSION_TARGETS:
        if column not in out.columns:
            out[column] = np.nan
    return out[[ID_COLUMN, *REGRESSION_TARGETS]].drop_duplicates(ID_COLUMN)


def behaviour_targets(labels_frame: pd.DataFrame) -> pd.DataFrame:
    """Per-period behaviour flags collapsed to one row per user.

    A flag fires if it fired in *any* observed period, except
    ``goal_progress`` which is the *share* of periods funded -- "this customer
    funds a goal some months" is a different claim from "this customer ever
    funded a goal", and collapsing the first to the second would overstate it.
    """
    if labels_frame.empty:
        return pd.DataFrame(columns=["user_id", *CLASSIFICATION_TARGETS])
    out = pd.DataFrame({ID_COLUMN: sorted(labels_frame[ID_COLUMN].unique())})
    periods_per_user = labels_frame.groupby(ID_COLUMN, observed=True)["period"].nunique()
    for target, column in CLASSIFICATION_TARGETS.items():
        if column not in labels_frame.columns:
            out[target] = 0
            continue
        if target == "goal_progress":
            out[target] = (
                labels_frame.groupby(ID_COLUMN, observed=True)[column].mean().astype(int).values
            )
        else:
            out[target] = (
                labels_frame.groupby(ID_COLUMN, observed=True)[column].max().astype(int).values
            )
    out["periods_observed"] = periods_per_user.reindex(out[ID_COLUMN]).to_numpy()
    return out


def supervised_frame(
    user_features: pd.DataFrame,
    profile_frame: pd.DataFrame,
    labels_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Feature rows joined to every available ground-truth label.

    Both label frames arrive unprefixed and leave prefixed; see
    :data:`TARGET_PREFIX` for why.
    """
    frame = user_features.copy()
    for label_frame in (profile_labels(profile_frame), behaviour_targets(labels_frame)):
        if label_frame.empty:
            continue
        labelled = label_frame.rename(
            columns={
                column: target_column(column)
                for column in label_frame.columns
                if column != ID_COLUMN
            }
        )
        frame = frame.merge(labelled, on=ID_COLUMN, how="inner")
    return frame


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    n = len(y_true)
    if n == 0:
        return {"n": 0}
    error = y_pred - y_true
    ss_res = float(np.sum(error**2))
    ss_tot = float(np.sum((y_true - float(np.mean(y_true))) ** 2))
    nonzero = np.abs(y_true) > 1e-6
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mape_percent": float(np.mean(np.abs(error[nonzero] / y_true[nonzero])) * 100)
        if nonzero.any()
        else float("nan"),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "bias": float(np.mean(error)),
        "n": int(n),
    }


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, score: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, roc_auc_score

    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    score = np.asarray(score, dtype=float)
    positives = int(y_true.sum())
    negatives = int(len(y_true) - positives)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    out: dict[str, float] = {
        "accuracy": float((tp + tn) / len(y_true)) if len(y_true) else float("nan"),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "specificity": float(tn / (tn + fp)) if (tn + fp) else float("nan"),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "positives": positives,
        "negatives": negatives,
        "n": int(len(y_true)),
    }
    if 0 < positives < len(y_true):
        out["roc_auc"] = float(roc_auc_score(y_true, score))
        out["average_precision"] = float(average_precision_score(y_true, score))
        out["lift_over_base_rate"] = float(
            out["recall"] / (positives / len(y_true)) if positives else float("nan")
        )
    return out


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def _regressor(seed: int = SEED):
    from lightgbm import LGBMRegressor

    return LGBMRegressor(
        objective="regression",
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=7,
        min_child_samples=5,
        subsample=0.9,
        subsample_freq=1,
        colsample_bytree=0.7,
        reg_lambda=30.0,
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )


def _classifier(seed: int = SEED):
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        objective="binary",
        n_estimators=120,
        learning_rate=0.05,
        num_leaves=7,
        min_child_samples=5,
        subsample=0.9,
        subsample_freq=1,
        colsample_bytree=0.7,
        reg_lambda=30.0,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )


def null_control(
    fold_train: pd.DataFrame, fold_eval: pd.DataFrame, seed: int = SEED
) -> dict:
    """Fit on **shuffled** labels and score on the real ones. Must be chance.

    This is the check that the whole supervised path is sound. If a model
    trained on permuted labels still scores well on the held-out fold, the
    merge or the fold construction is leaking, and no amount of R2 on the real
    model can be believed.

    Also reported: the direct feature baseline -- the engine feature the target
    is defined from, copied across with no model at all. On this dataset that
    baseline is strong by construction (see
    :func:`leakage_by_construction_note`), and a model that cannot beat it is
    not adding information, only fitting arithmetic.
    """
    columns = feature_columns(fold_train)
    rng = np.random.default_rng(seed)
    out: dict[str, dict] = {"regression": {}, "classification": {}}

    for target in REGRESSION_TARGETS:
        column = target_column(target)
        if column not in fold_train.columns or column not in fold_eval.columns:
            continue
        values = fold_train[column].dropna()
        if len(values) < 12:
            continue
        shuffled = pd.Series(
            rng.permutation(values.to_numpy(dtype=float)), index=values.index
        )
        model = _regressor(seed)
        model.fit(
            design_matrix(fold_train, columns).loc[shuffled.index, columns],
            shuffled.to_numpy(dtype=float),
        )
        mask = fold_eval[column].notna().to_numpy()
        y_true = fold_eval.loc[mask, column].to_numpy(dtype=float)
        if len(y_true) == 0:
            continue
        entry = regression_metrics(y_true, model.predict(
            design_matrix(fold_eval, columns).loc[mask, columns]
        ))
        entry["train_mean_baseline"] = regression_metrics(
            y_true, np.full(len(y_true), float(values.mean()))
        )
        out["regression"][target] = entry

    for target in CLASSIFICATION_TARGETS:
        column = target_column(target)
        if column not in fold_train.columns or column not in fold_eval.columns:
            continue
        values = fold_train[column].dropna().astype(int)
        if len(values) < MIN_CLASSIFIER_ROWS or int(values.sum()) < MIN_POSITIVE_ROWS:
            continue
        shuffled = pd.Series(
            rng.permutation(values.to_numpy()), index=values.index
        )
        model = _classifier(seed)
        model.fit(
            design_matrix(fold_train, columns).loc[shuffled.index, columns],
            shuffled.to_numpy(),
        )
        mask = fold_eval[column].notna().to_numpy()
        y_true = fold_eval.loc[mask, column].astype(int).to_numpy()
        if len(y_true) == 0 or 0 < int(y_true.sum()) < len(y_true):
            score = model.predict_proba(design_matrix(fold_eval, columns).loc[mask, columns])[:, 1]
            out["classification"][target] = classification_metrics(
                y_true, (score >= 0.5).astype(int), score
            )
        else:
            out["classification"][target] = {"available": False, "reason": "single-class fold"}

    return out


def leakage_by_construction_note() -> str:
    """The single most important caveat on every number this module produces."""
    return (
        "LEAKAGE BY CONSTRUCTION. The dataset generator derives both "
        "financial_profiles and behavior_labels by aggregating the same "
        "transactions these features are built from: label_savings_rate is "
        "close to the savings_rate feature, and the behaviour flags are "
        "thresholded versions of late_month_share, cash_dependency, "
        "expense_income_ratio and emergency_buffer_months. A model can "
        "therefore reach a very high R2 / F1 while learning nothing a rule "
        "could not, because it is re-deriving a statistic it was handed. Read "
        "the null_control and direct_feature_baseline rows beside every score: "
        "the honest claim is that the pipeline reproduces the ground truth "
        "reliably on unseen customers and unseen months, NOT that it predicts "
        "future financial behaviour. Proving the latter needs held-out "
        "real-customer data, which does not exist for this challenge."
    )


def direct_feature_baseline(fold_eval: pd.DataFrame) -> dict:
    """What you get by copying the corresponding engine feature. No model."""
    pairs = {
        "savings_rate": "savings_rate",
        "emergency_fund_months": "emergency_buffer_months",
        "cash_dependency": "cash_dependency",
        "income_stability": "income_stability",
    }
    out: dict[str, dict] = {}
    for target, feature in pairs.items():
        column, source = target_column(target), feature
        if column not in fold_eval.columns or source not in fold_eval.columns:
            continue
        mask = fold_eval[column].notna().to_numpy()
        y_true = fold_eval.loc[mask, column].to_numpy(dtype=float)
        if len(y_true) == 0:
            continue
        out[target] = regression_metrics(
            y_true, fold_eval.loc[mask, source].to_numpy(dtype=float)
        )
    return out


def honest_verdict(
    fold_test: dict,
    direct_baseline: dict,
    null: dict,
) -> list[dict]:
    """Per target: did the model actually beat the trivial baselines?

    Published alongside the headline scores so a reader is never left
    assuming a good R2 / F1 means the model earned it. Verdicts:

    ``beats_trivial``      lower MAE than both the train-mean and the
                           direct-feature baselines -- the model adds something.
    ``no_gain_over_rule``  a plain copy of the engine feature is at least as
                           good, so the honest description is "this target is a
                           restatement of an aggregate the engine already
                           computes" rather than a learned prediction.
    ``null_control_failed`` the shuffled-label control scored as well as the
                           real model, which means the pipeline is leaking and
                           none of the numbers can be believed.
    ``single_class``       the held-out fold contains one class only, so the
                           metric is undefined.

    Regression targets are checked against the shuffled-label **R2**, and
    classification targets against the shuffled-label **ROC-AUC**; the previous
    version looked up a classification key for a regression target, so the
    control check silently never fired.
    """
    out: list[dict] = []

    def _null_entry(target: str) -> dict:
        regression = null.get("regression", {}).get(target)
        if regression is not None:
            return regression
        return null.get("classification", {}).get(target, {})

    for target, entry in fold_test.get("regression", {}).items():
        mae = float(entry.get("mae", float("nan")))
        mean_baseline = entry.get("train_mean_baseline", {}).get("mae")
        direct = direct_baseline.get(target, {}).get("mae")
        control = _null_entry(target)
        control_r2 = control.get("r2")
        verdict = "beats_trivial"
        if direct is not None and mae >= float(direct):
            verdict = "no_gain_over_rule"
        elif mean_baseline is not None and mae >= float(mean_baseline):
            verdict = "no_gain_over_rule"
        if control_r2 is not None and not np.isnan(float(control_r2)) and float(control_r2) > 0.30:
            verdict = "null_control_failed"
        out.append(
            {
                "target": target,
                "task": "regression",
                "model_mae": mae,
                "model_r2": entry.get("r2"),
                "train_mean_baseline_mae": mean_baseline,
                "direct_feature_baseline_mae": direct,
                "null_control_r2": control_r2,
                "verdict": verdict,
            }
        )

    for target, entry in fold_test.get("classification", {}).items():
        positives = int(entry.get("positives", 0))
        negatives = int(entry.get("negatives", 0))
        control = _null_entry(target)
        control_auc = control.get("roc_auc")
        baseline_f1 = entry.get("majority_baseline_f1")
        f1 = float(entry.get("f1", float("nan")))
        if positives == 0 or negatives == 0:
            verdict = "single_class"
        elif control_auc is not None and float(control_auc) > 0.65:
            verdict = "null_control_failed"
        elif baseline_f1 is not None and f1 <= float(baseline_f1):
            verdict = "no_gain_over_rule"
        else:
            verdict = "beats_trivial"
        out.append(
            {
                "target": target,
                "task": "classification",
                "model_f1": f1,
                "model_roc_auc": entry.get("roc_auc"),
                "majority_baseline_f1": baseline_f1,
                "null_control_roc_auc": control_auc,
                "positives": positives,
                "negatives": negatives,
                "verdict": verdict,
            }
        )
    return out


def train_health_models(fold_train: pd.DataFrame, seed: int = SEED) -> dict:
    """Fit one regressor per profile target plus the behaviour classifiers.

    ``fold_train`` is the supervised frame built from the *training* cut point
    only. Anything with too few rows is skipped and recorded in ``skipped``
    rather than fitted on noise.
    """
    columns = feature_columns(fold_train)
    matrix = design_matrix(fold_train, columns)
    regressors: dict[str, object] = {}
    classifier_models: dict[str, object] = {}
    skipped: dict[str, str] = {}

    for target in REGRESSION_TARGETS:
        column = target_column(target)
        if column not in fold_train.columns:
            skipped[target] = f"label '{target}' absent from financial_profiles.csv"
            continue
        subset = matrix.loc[fold_train[column].notna().to_numpy()]
        if len(subset) < 10:
            skipped[target] = f"only {len(subset)} labelled rows (need 10)"
            continue
        model = _regressor(seed)
        model.fit(subset[columns], fold_train.loc[subset.index, column].to_numpy(dtype=float))
        regressors[target] = model

    for target in CLASSIFICATION_TARGETS:
        column = target_column(target)
        if column not in fold_train.columns:
            skipped[target] = f"behaviour label '{target}' absent"
            continue
        subset = matrix.loc[fold_train[column].notna().to_numpy()]
        positives = int(fold_train.loc[subset.index, column].sum())
        if len(subset) < MIN_CLASSIFIER_ROWS or positives < MIN_POSITIVE_ROWS:
            skipped[target] = (
                f"{len(subset)} rows / {positives} positives "
                f"(need {MIN_CLASSIFIER_ROWS}/{MIN_POSITIVE_ROWS})"
            )
            continue
        model = _classifier(seed)
        model.fit(subset[columns], fold_train.loc[subset.index, column].astype(int).to_numpy())
        classifier_models[target] = model

    return {
        "features": columns,
        "regressors": regressors,
        "classifiers": classifier_models,
        "skipped": skipped,
        "seed": seed,
    }


def evaluate(
    bundle: dict,
    fold_eval: pd.DataFrame,
    fold_train: pd.DataFrame,
) -> dict:
    """Score a bundle on one held-out fold against two honest baselines.

    Baseline 1 (``mean_baseline``) predicts the training-fold mean of the
    target. Baseline 2 (``feature_baseline``) uses the same behavioural feature
    the target is closest to, computed from training-fold statistics. If the ML
    model cannot beat the plain training mean, the card says so.
    """
    columns = bundle["features"]
    matrix = design_matrix(fold_eval, columns)
    report: dict[str, dict] = {"regression": {}, "classification": {}, "baselines": {}}

    train_means = (
        fold_train[[target_column(t) for t in REGRESSION_TARGETS if target_column(t) in fold_train]]
        .mean()
        .to_dict()
    )
    baseline_pairs: dict[str, tuple[str, ...]] = {
        "savings_rate": ("savings_rate",),
        "emergency_fund_months": ("ending_balance", "monthly_expense"),
        "cash_dependency": ("cash_dependency",),
        "income_stability": ("income_stability",),
    }

    for target, model in bundle["regressors"].items():
        column = target_column(target)
        if column not in fold_eval.columns:
            continue
        mask = fold_eval[column].notna().to_numpy()
        y_true = fold_eval.loc[mask, column].to_numpy(dtype=float)
        if len(y_true) == 0:
            continue
        y_pred = np.asarray(model.predict(matrix.loc[mask, columns]), dtype=float)

        entry = regression_metrics(y_true, y_pred)
        entry["train_mean_baseline"] = regression_metrics(
            y_true, np.full(len(y_true), train_means.get(column, float(np.mean(y_true))))
        )

        # Second baseline: the engine feature most correlated with the target.
        drivers = [
            c
            for c in baseline_pairs.get(target, ())
            if c in fold_eval.columns and c in fold_train.columns
        ]
        drivers = [c for c in drivers if c != column] or [
            c for c in columns if c in fold_eval.columns
        ][:1]
        if drivers and "monthly_expense" in fold_eval.columns:
            driver = drivers[0]
            scale = fold_train["monthly_expense"].clip(lower=1.0)
            ratio_source = fold_train[driver] / scale
            train_median = float(np.nanmedian(ratio_source.to_numpy(dtype=float)))
            observed = matrix.loc[mask, driver] / fold_eval.loc[mask, "monthly_expense"].clip(
                lower=1.0
            )
            usable = observed.notna().to_numpy()
            if usable.any():
                naive = np.full(len(y_true), train_median)
                naive[usable] = observed[usable].to_numpy(dtype=float)[usable]
                entry["feature_baseline"] = regression_metrics(y_true, naive)
                entry["feature_baseline_driver"] = driver

        report["regression"][target] = entry

    for target, model in bundle["classifiers"].items():
        column = target_column(target)
        if column not in fold_eval.columns:
            continue
        mask = fold_eval[column].notna().to_numpy()
        y_true = fold_eval.loc[mask, column].astype(int).to_numpy()
        if len(y_true) == 0:
            continue
        score = model.predict_proba(matrix.loc[mask, columns])[:, 1]
        entry = classification_metrics(y_true, (score >= 0.5).astype(int), score)
        # Majority-class baseline, so a low F1 can be read in context.
        majority = int(fold_train[column].mean() >= 0.5)
        majority_pred = np.full(len(y_true), majority, dtype=int)
        entry["majority_baseline_accuracy"] = float(
            max((y_true == 1).mean(), (y_true == 0).mean())
        )
        entry["majority_baseline_f1"] = classification_metrics(
            y_true, majority_pred, np.full(len(y_true), float(majority))
        )["f1"]
        entry["majority_class"] = majority
        report["classification"][target] = entry

    return report


# ---------------------------------------------------------------------------
# Inference + explanation
# ---------------------------------------------------------------------------

def predict(bundle: dict, user_row: pd.DataFrame) -> dict:
    """Predicted profile + behaviour probabilities for one customer.

    Returns ``None`` values for any target the bundle did not train, so the
    caller can fall back to the deterministic engine rather than invent a
    number.
    """
    columns = bundle["features"]
    matrix = design_matrix(user_row, columns)
    out: dict[str, dict] = {"profile": {}, "behaviours": {}}
    for target, model in bundle.get("regressors", {}).items():
        out["profile"][target] = float(model.predict(matrix[columns])[0])
    for target, model in bundle.get("classifiers", {}).items():
        out["behaviours"][target] = float(model.predict_proba(matrix[columns])[0])
    # Levels the score ladders need but the models do not predict: they are
    # directly observed in the customer's own feature row, so they are carried
    # through rather than estimated.
    row = matrix.iloc[0] if len(matrix) else user_row
    for level in ("monthly_income", "monthly_expense", "ending_balance"):
        if level in row.index:
            out["profile"][level] = float(row[level])
    return out


def explain(bundle: dict, target: str, user_row: pd.DataFrame, top: int = 6) -> list[dict]:
    """Exact TreeSHAP attributions for one regressed target.

    LightGBM's ``pred_contrib`` returns one value per feature plus a bias term,
    in the same units as the prediction, computed by the tree traversal itself.
    No sampling, no approximation, no extra dependency.
    """
    if target not in bundle.get("regressors", {}):
        return []
    columns = bundle["features"]
    matrix = design_matrix(user_row, columns)
    model = bundle["regressors"][target]
    values = np.asarray(model.predict(matrix[columns], pred_contrib=True), dtype=float)[0]
    contributions = values[: len(columns)]
    bias = float(values[-1]) if len(values) > len(columns) else 0.0
    order = np.argsort(np.abs(contributions))[::-1][:top]
    observed = matrix.iloc[0]
    return json_safe(
        {
            "target": target,
            "base_value": bias,
            "contributions": [
                {
                    "feature": columns[int(i)],
                    "value": float(observed[columns[int(i)]]),
                    "shap": float(contributions[int(i)]),
                    "direction": "raises" if contributions[int(i)] > 0 else "lowers",
                }
                for i in order
            ],
        }
    )


def global_importance(bundle: dict, top: int = 12) -> dict[str, list[dict]]:
    """Mean |SHAP| across the training rows -- the model-level story."""
    from app.ml.artifacts import load_bundle  # noqa: F401  (kept for symmetry)

    out: dict[str, list[dict]] = {}
    matrix = bundle.get("train_matrix")
    if matrix is None:
        return out
    columns = bundle["features"]
    for target, model in bundle.get("regressors", {}).items():
        values = np.asarray(model.predict(matrix[columns], pred_contrib=True), dtype=float)
        mean_abs = np.abs(values[:, : len(columns)]).mean(axis=0)
        order = np.argsort(mean_abs)[::-1][:top]
        out[target] = [
            {"feature": columns[int(i)], "mean_abs_shap": float(mean_abs[int(i)])} for i in order
        ]
    return out


def health_score_from_profile(profile: dict[str, float | None]) -> dict:
    """Turn predicted profile values into one explainable 0-100 score.

    The ladders are fixed here, in one place, so the mapping can be argued
    about and changed as a unit. Every component is returned with its own
    contribution, and a component with no predicted value is held at the
    midpoint and flagged rather than silently scored zero.
    """
    from app.engines.health import ramp

    components: dict[str, dict] = {}
    weights = {
        "savings_rate": 0.28,
        "expense_ratio": 0.22,
        "income_stability": 0.18,
        "emergency_buffer_months": 0.20,
        "cash_dependency": 0.12,
    }
    ladders = {
        "savings_rate": ((-0.05, 0.0), (0.0, 20.0), (0.05, 38.0), (0.10, 55.0),
                         (0.20, 78.0), (0.30, 100.0)),
        "expense_ratio": ((0.50, 100.0), (0.70, 88.0), (0.85, 70.0), (1.00, 48.0),
                          (1.15, 24.0), (1.30, 0.0)),
        "income_stability": ((0.30, 0.0), (0.60, 35.0), (0.75, 58.0), (0.88, 80.0),
                             (0.95, 92.0), (0.99, 100.0)),
        "emergency_buffer_months": ((0.0, 0.0), (0.5, 18.0), (1.0, 36.0), (3.0, 68.0),
                                    (6.0, 88.0), (12.0, 100.0)),
        "cash_dependency": ((0.0, 100.0), (0.10, 88.0), (0.25, 66.0), (0.40, 42.0),
                            (0.60, 18.0), (0.80, 0.0)),
    }
    labels = {
        "savings_rate": "savings behaviour",
        "expense_ratio": "expense control",
        "income_stability": "income stability",
        "emergency_buffer_months": "liquidity buffer",
        "cash_dependency": "cash dependency",
    }

    income = profile.get("monthly_income")
    expense = profile.get("monthly_expense")
    expense_ratio = None
    if income is not None and expense is not None and income > 0:
        expense_ratio = expense / income
    profile = {**profile, "expense_ratio": expense_ratio}

    total = 0.0
    total_weight = 0.0
    for key, weight in weights.items():
        value = profile.get(key)
        if value is None or value != value:
            components[key] = {
                "label": labels[key],
                "score": 50.0,
                "weight": weight,
                "held_neutral": True,
                "reason": "no prediction available for this component",
            }
            continue
        score = float(ramp(float(value), ladders[key]))
        components[key] = {
            "label": labels[key],
            "score": round(score, 2),
            "weight": weight,
            "observed_value": round(float(value), 4),
            "held_neutral": False,
        }
        total += score * weight
        total_weight += weight

    normalised = total / total_weight if total_weight > 0 else 50.0
    return json_safe(
        {
            "score": round(float(np.clip(normalised, 0.0, 100.0)), 2),
            "components": components,
            "held_components": [k for k, v in components.items() if v.get("held_neutral")],
        }
    )


assert np is not None