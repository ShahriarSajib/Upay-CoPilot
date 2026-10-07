"""Metric functions shared by every evaluation module.

One implementation per metric family, so "F1" means the same thing in the
anomaly report, the health report and the LLM report.
"""

from __future__ import annotations

import numpy as np

SEED = 42


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------

def regression_metrics(y_true, y_pred) -> dict[str, float]:
    """MAE / RMSE / MAPE / R2 / bias.

    MAPE is computed over rows whose actual value is meaningfully non-zero
    (``|y| > 1e-6``) so a near-zero month does not produce an infinite error
    and silently dominate the average.
    """
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
        "mape_percent": (
            float(np.mean(np.abs(error[nonzero] / y_true[nonzero])) * 100)
            if nonzero.any()
            else float("nan")
        ),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "bias": float(np.mean(error)),
        "n": int(n),
    }


def mae_improvement_percent(baseline_mae: float, model_mae: float) -> float:
    """Relative MAE reduction of ``model`` against ``baseline``."""
    if baseline_mae <= 0:
        return 0.0
    return round(100.0 * (baseline_mae - model_mae) / baseline_mae, 2)


# ---------------------------------------------------------------------------
# Classification / detection
# ---------------------------------------------------------------------------

def classification_metrics(y_true, y_pred, score=None) -> dict[str, float]:
    """Precision / recall / F1 / specificity / FPR plus threshold-free ranks."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
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
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else float("nan"),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "positives": positives,
        "negatives": negatives,
        "n": int(len(y_true)),
    }
    if 0 < positives < len(y_true):
        out["roc_auc"] = float(roc_auc_score(y_true, y_pred))
        if score is not None:
            score = np.asarray(score, dtype=float)
            out["average_precision"] = float(average_precision_score(y_true, score))
            out["roc_auc_score"] = float(roc_auc_score(y_true, score))
            out["lift_over_base_rate"] = float(
                recall / (positives / len(y_true)) if positives else float("nan")
            )
    else:
        out["roc_auc"] = float("nan")
    return out


def precision_at_k(y_true, ranking_score, k: int = 50) -> float:
    """Precision of the top-``k`` ranked rows -- what a reviewer actually sees."""
    y_true = np.asarray(y_true).astype(int)
    order = np.argsort(-np.asarray(ranking_score, dtype=float))[:k]
    return float(y_true[order].mean()) if len(order) else 0.0


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def clustering_metrics(matrix: np.ndarray, labels) -> dict[str, float]:
    """Silhouette, Davies-Bouldin and Calinski-Harabasz for one clustering."""
    from sklearn.metrics import (
        calinski_harabasz_score,
        davies_bouldin_score,
        silhouette_score,
    )

    labels = np.asarray(labels)
    n_clusters = int(len(np.unique(labels)))
    n_samples = len(labels)
    if n_clusters < 2 or n_samples <= n_clusters:
        return {"n_clusters": n_clusters, "n": int(n_samples)}
    return {
        "silhouette": float(silhouette_score(matrix, labels)),
        "davies_bouldin": float(davies_bouldin_score(matrix, labels)),
        "calinski_harabasz": float(calinski_harabasz_score(matrix, labels)),
        "n_clusters": n_clusters,
        "n": int(n_samples),
    }


def agreement_metrics(reference, predicted) -> dict[str, float]:
    """External clustering scores against a ground-truth partition."""
    from sklearn.metrics import (
        adjusted_mutual_info_score,
        adjusted_rand_score,
        normalized_mutual_info_score,
    )

    reference = np.asarray(reference)
    predicted = np.asarray(predicted)
    if len(reference) != len(predicted) or len(reference) == 0:
        return {"available": False}
    return {
        "available": True,
        "adjusted_rand_index": float(adjusted_rand_score(reference, predicted)),
        "normalized_mutual_information": float(
            normalized_mutual_info_score(reference, predicted)
        ),
        "adjusted_mutual_information": float(
            adjusted_mutual_info_score(reference, predicted)
        ),
        "n": int(len(reference)),
    }
