"""Anomaly-detection evaluation against injected ground truth.

Because the dataset generator *injects* the anomalies itself, every flagged
transaction can be checked against a known answer. This module turns that into
a measurement instead of a claim:

* precision / recall / F1 / false-positive rate at the operating point chosen
  on validation;
* average precision and precision@50, which do not depend on the threshold;
* recall per injected pattern, so a blind spot (``unusual_merchant``) is
  visible rather than averaged away;
* two naive threshold rules the detector has to beat, so "Isolation Forest
  F1 = 0.58" means something.

Ground truth is never used to fit the detector. The transaction-time feature
frame is built **once** and sliced per window, because building it costs a
full pass over the ledger and building it six times costs a minute.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.evaluation.metrics import classification_metrics, precision_at_k, SEED

NAIVE_RULES = (
    "amount_outlier",
    "category_zscore",
    "both_rules",
)


# ---------------------------------------------------------------------------
# Naive rules -- thresholds on transaction-time features, no model, no fit
# ---------------------------------------------------------------------------

def _rule_flags(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    amount = frame["amount_vs_user_p90"].to_numpy(dtype=float) >= 3.0
    zscore = np.abs(frame["category_amount_zscore"].to_numpy(dtype=float)) >= 3.0
    recurring = frame["is_recurring"].to_numpy(dtype=int) == 0
    return {
        "amount_outlier": amount & recurring,
        "category_zscore": zscore & recurring,
        "both_rules": amount & zscore & recurring,
    }


def _rule_score(frame: pd.DataFrame, name: str) -> np.ndarray:
    """Continuous score behind a rule, so average precision is comparable."""
    if name == "amount_outlier":
        return frame["amount_vs_user_p90"].to_numpy(dtype=float)
    if name == "category_zscore":
        return np.abs(frame["category_amount_zscore"].to_numpy(dtype=float))
    return (
        frame["amount_vs_user_p90"].to_numpy(dtype=float)
        * np.abs(frame["category_amount_zscore"].to_numpy(dtype=float))
    )


def score_rules(frame: pd.DataFrame, y_true: np.ndarray) -> dict[str, dict]:
    """Precision / recall / F1 / AP / precision@50 for each naive rule."""
    from sklearn.metrics import average_precision_score

    out: dict[str, dict] = {}
    for name, flags in _rule_flags(frame).items():
        metrics = classification_metrics(y_true, flags.astype(int))
        if 0 < int(y_true.sum()) < len(y_true):
            score = _rule_score(frame, name)
            metrics["average_precision"] = float(average_precision_score(y_true, score))
            metrics["precision_at_k"] = precision_at_k(y_true, score, k=50)
        out[name] = metrics
    return out


def random_flag_baseline(y_true: np.ndarray, rate: float) -> dict[str, float]:
    """A detector that flags ``rate`` of rows uniformly at random.

    Expected precision, recall and F1 all equal ``rate`` (the flag is
    independent of the truth), so the analytic expectation is reported
    alongside one seeded realisation -- a single draw can easily be 0.0 when
    the positive class is sparse, which would read as "random is useless"
    rather than "random is uninformative".
    """
    y_true = np.asarray(y_true).astype(int)
    n = len(y_true)
    if n == 0:
        return {}
    rng = np.random.default_rng(SEED)
    predicted = (rng.random(n) < rate).astype(int)
    out = classification_metrics(y_true, predicted)
    out["expected_precision_equals_rate"] = float(rate)
    out["expected_recall_equals_rate"] = float(rate)
    out["expected_f1_equals_rate"] = float(rate)
    return out


# ---------------------------------------------------------------------------
# Window scoring
# ---------------------------------------------------------------------------

def _score_frame(frame: pd.DataFrame, window: str, periods: list[str]) -> dict:
    """Everything measurable from one already-scored window."""
    y_true = frame["is_anomaly"].to_numpy().astype(int)
    y_pred = frame["is_flagged"].to_numpy().astype(int)
    score = frame["anomaly_score"].to_numpy(dtype=float)
    metrics = classification_metrics(y_true, y_pred, score)
    metrics["precision_at_k"] = precision_at_k(y_true, score, k=50)
    metrics["random_flag_baseline"] = random_flag_baseline(y_true, float(frame["is_anomaly"].mean()))

    by_pattern: dict[str, dict] = {}
    for kind, group in frame.groupby("pattern_type", observed=True):
        if not isinstance(kind, str) or not kind:
            continue
        injected = int(len(group))
        detected = int(group["is_flagged"].sum())
        by_pattern[kind] = {
            "injected": injected,
            "detected": detected,
            "recall": round(detected / injected, 4) if injected else None,
        }

    rules = score_rules(frame, y_true)
    rule_f1 = {name: entry["f1"] for name, entry in rules.items()}
    best_rule = max(rule_f1, key=rule_f1.get) if rule_f1 else None

    return {
        "window": window,
        "periods": periods,
        "n_scored_transactions": int(len(frame)),
        "n_injected_anomalies": int(y_true.sum()),
        "injected_rate": round(float(y_true.mean()), 5),
        "model": metrics,
        "by_pattern": by_pattern,
        "naive_rules": rules,
        "headline": {
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "false_positive_rate": metrics["false_positive_rate"],
            "average_precision": metrics["average_precision"],
            "precision_at_50": metrics["precision_at_k"],
            "best_naive_rule": best_rule,
            "best_naive_rule_f1": rule_f1.get(best_rule) if best_rule else None,
            "f1_improvement_over_best_rule_percent": (
                round(
                    100.0 * (metrics["f1"] - rule_f1[best_rule]) / max(rule_f1[best_rule], 1e-9),
                    2,
                )
                if best_rule and rule_f1[best_rule] > 0
                else None
            ),
            "random_flag_f1_expected": metrics["random_flag_baseline"].get("expected_f1_equals_rate"),
            "random_flag_f1_draw": metrics["random_flag_baseline"].get("f1"),
        },
        "examples": _examples(frame),
    }


def _examples(frame: pd.DataFrame, limit: int = 3) -> list[dict]:
    """Highest-scoring true positives, for the evidence dashboard and demo."""
    true_positive = frame[frame["is_flagged"] & frame["is_anomaly"]]
    if true_positive.empty:
        return []
    top = true_positive.sort_values("anomaly_score", ascending=False).head(limit)
    out: list[dict] = []
    for _, row in top.iterrows():
        ratio = float(row["amount_vs_user_median"])
        median = float(row["amount"] / ratio) if ratio else 0.0
        out.append(
            {
                "transaction_id": str(row["transaction_id"]),
                "user_id": str(row["user_id"]),
                "amount": round(float(row["amount"]), 2),
                "category": str(row["category"]),
                "pattern_type": str(row["pattern_type"]),
                "anomaly_score": round(float(row["anomaly_score"]), 4),
                "typical_amount_for_user": round(median, 2),
                "times_user_median": round(ratio, 2),
                "category_zscore": round(float(row["category_amount_zscore"]), 2),
                "hour_of_day": int(row["hour_of_day"]),
                "reasons": _reasons(row),
            }
        )
    return out


def _reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    ratio = float(row["amount_vs_user_median"])
    if ratio >= 3:
        reasons.append(f"{ratio:.1f}x the customer's typical transaction size")
    zscore = float(row["category_amount_zscore"])
    if abs(zscore) >= 3:
        reasons.append(
            f"z-score {zscore:+.1f} against their own '{row['category']}' spending"
        )
    if float(row["amount_vs_user_p90"]) >= 3:
        reasons.append(
            f"{float(row['amount_vs_user_p90']):.1f}x their trailing 90th-percentile amount"
        )
    if int(row["hour_of_day"]) < 5:
        reasons.append("at an hour the customer never transacts at")
    if not reasons:
        reasons.append("deviation from the customer's rolling behaviour")
    return reasons


# ---------------------------------------------------------------------------
# Full evaluation
# ---------------------------------------------------------------------------

def run_anomaly_evaluation(
    transactions: pd.DataFrame,
    splits,
    seed: int = SEED,
    verbose: bool = False,
    dataset=None,
) -> dict:
    """Tune on validation, fit on train, score validation and untouched test.

    Pass ``dataset`` to have the scored transaction frame cached on it as
    ``features["anomaly_scored"]``, which is what the customer-impact block
    reads to report detection value in taka. It is a frame, not report JSON --
    keep it out of the report.
    """
    from app.ml.anomaly import build_transaction_features, train_anomaly_model, tune_contamination

    train_periods = set(splits["train"].periods)
    validation_periods = set(splits["validation"].periods)
    test_periods = set(splits["test"].periods)

    if verbose:
        print("  tuning contamination on validation ...")
    selection = tune_contamination(transactions, train_periods, validation_periods, seed=seed)
    if verbose:
        print(f"    selected contamination={selection['contamination']}")

    bundle = train_anomaly_model(
        transactions, train_periods, contamination=selection["contamination"], seed=seed
    )

    if verbose:
        print("  building transaction-time features once ...")
    features = build_transaction_features(transactions)
    features["period"] = features["timestamp"].dt.strftime("%Y-%m")
    features = features[features["direction"] == "outflow"].copy()
    features["anomaly_score"] = -bundle["model"].score_samples(features[bundle["features"]])
    features["is_flagged"] = (
        (bundle["model"].predict(features[bundle["features"]]) == -1)
        & (features["is_recurring"] == 0)
    )
    if dataset is not None:
        dataset.features["anomaly_scored"] = features

    windows: dict[str, dict] = {}
    for name, periods in (
        ("validation", sorted(validation_periods)),
        ("test", sorted(test_periods)),
    ):
        window = _score_frame(features[features["period"].isin(periods)], name, periods)
        windows[name] = window
        if verbose:
            h = window["headline"]
            print(
                f"  {name}: P={h['precision']:.3f} R={h['recall']:.3f} F1={h['f1']:.3f} "
                f"AP={h['average_precision']:.3f} P@50={h['precision_at_50']:.3f} "
                f"FPR={h['false_positive_rate']:.4f} n={window['n_scored_transactions']}"
            )
            print(
                f"    best naive rule: {h['best_naive_rule']} F1={h['best_naive_rule_f1']} "
                f"-> detector {h['f1_improvement_over_best_rule_percent']:+.1f}%"
            )

    test = windows["test"]["headline"]
    return {
        "task": "unsupervised ranking of unusual transactions",
        "detector": "IsolationForest",
        "fit_window": f"{min(train_periods)}..{max(train_periods)}",
        "operating_point": {
            "chosen_on": f"validation ({min(validation_periods)}..{max(validation_periods)})",
            "contamination": selection["contamination"],
            "grid": selection["grid"],
        },
        "features": bundle["features"],
        "ground_truth": "injected_patterns.csv (generator ground truth, scoring only)",
        "prior_anomaly_rate": bundle["prior_anomaly_rate"],
        "windows": windows,
        "headline": test,
        "seed": seed,
    }
