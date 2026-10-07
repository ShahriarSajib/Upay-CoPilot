"""Explainability evaluation -- are the explanations real?

The product shows customers *why* a number moved. If the attributions are
wrong, the interface is confidently lying. This module treats explanations as
measurements and checks four properties:

**Fidelity**       For a tree model, SHAP is exact: ``base + sum(contributions)
                   == prediction``. Any deviation is a bug, and it is
                   reported as a maximum absolute error rather than assumed.
**Faithfulness**   Removing a feature the attribution says *raises* the
                   prediction must lower it. Reported as the share of
                   (feature, row) pairs where the sign agrees.
**Stability**      The same model scoring two different windows should name the
                   same drivers. Reported as the Spearman rank correlation of
                   mean |SHAP| between windows.
**Sanity**         Shuffling a feature's values must collapse its attribution.
                   An attribution that survives shuffling is keyed to the
                   column, not to the customer's data.

The ``shap`` package is used when it is importable; otherwise LightGBM's own
``pred_contrib`` returns mathematically identical TreeSHAP values, and the
report records which path produced the numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.evaluation.datasets import Dataset
from app.evaluation.metrics import SEED

MAX_ROWS = 2000


# ---------------------------------------------------------------------------
# Core: SHAP values with a recorded provenance
# ---------------------------------------------------------------------------

def shap_values(model, matrix: pd.DataFrame) -> tuple[np.ndarray, str, float | None]:
    """(contributions, engine, bias) for a tree model.

    The bias is the model's expected output over its training background; when
    the ``shap`` package is used it comes from the explainer, otherwise from
    LightGBM's own ``pred_contrib`` base value.
    """
    matrix = matrix.reset_index(drop=True)
    try:
        import shap  # noqa: F401

        explainer = _tree_explainer(model)
        if explainer is not None:
            raw = explainer.shap_values(matrix)
            if isinstance(raw, list):
                raw = raw[0]
            values = np.asarray(raw, dtype=float)
            bias = float(np.asarray(explainer.expected_value).reshape(-1)[0])
            return values, "shap.TreeExplainer", bias
    except Exception:
        pass

    raw = np.asarray(model.predict(matrix, pred_contrib=True), dtype=float)
    values = raw[:, : matrix.shape[1]]
    bias = float(raw[0, -1]) if raw.ndim == 2 and raw.shape[1] > matrix.shape[1] else 0.0
    return values, "lightgbm.pred_contrib", bias


def _tree_explainer(model):
    import shap

    inner = getattr(model, "booster_", None)
    try:
        return shap.TreeExplainer(model)
    except Exception:
        return shap.TreeExplainer(inner) if inner is not None else None


def sample_rows(frame: pd.DataFrame, limit: int = MAX_ROWS, seed: int = SEED) -> pd.DataFrame:
    if len(frame) <= limit:
        return frame
    return frame.sample(n=limit, random_state=seed).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def fidelity(model, matrix: pd.DataFrame, values: np.ndarray, bias: float) -> dict:
    """``base + sum(contributions)`` must reproduce ``predict`` exactly."""
    matrix = matrix.reset_index(drop=True)
    reconstruction = values.sum(axis=1) + bias
    prediction = np.asarray(model.predict(matrix), dtype=float)
    error = np.abs(reconstruction - prediction)
    scale = max(float(np.max(np.abs(prediction))), 1e-9)
    return {
        "max_absolute_error": float(error.max()),
        "mean_absolute_error": float(error.mean()),
        "relative_to_prediction_scale": float(error.max() / scale),
        "exact": bool(error.max() <= 1e-6 * scale),
        "n_rows": int(len(matrix)),
    }


def faithfulness(
    model, matrix: pd.DataFrame, values: np.ndarray, columns: list[str], top: int = 8
) -> dict:
    """Deleting a feature must move the prediction the way its attribution says.

    "Deleting" means replacing the column by its own median, which keeps the
    row inside the data distribution. Zeroing was tried first and is not used
    here: for a column whose typical value is ``0.09`` (savings rate), setting
    it to ``0`` moves every row far off-manifold, and the resulting prediction
    change reflects extrapolation rather than the feature's contribution.
    """
    matrix = matrix.reset_index(drop=True)
    baseline = np.asarray(model.predict(matrix), dtype=float)
    mean_abs = np.abs(values).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][: min(top, len(columns))]

    checked = 0
    agreed = 0
    details: list[dict] = []
    for position in order:
        column = columns[int(position)]
        if column not in matrix.columns:
            continue
        perturbed = matrix.copy()
        perturbed[column] = float(np.median(matrix[column].to_numpy(dtype=float)))
        shifted = np.asarray(model.predict(perturbed), dtype=float)
        delta = shifted - baseline
        expected = -values[:, int(position)]
        sign_match = np.sign(delta) == np.sign(expected)
        # Rows where the attribution is effectively zero carry no claim.
        material = np.abs(expected) > 1e-6
        if material.sum() == 0:
            continue
        checked += int(material.sum())
        agreed += int((sign_match & material).sum())
        details.append(
            {
                "feature": column,
                "mean_abs_shap": round(float(mean_abs[int(position)]), 6),
                "direction_agreement": round(float(sign_match[material].mean()), 4),
                "n_rows": int(material.sum()),
            }
        )

    return {
        "top_features_checked": [d["feature"] for d in details],
        "direction_agreement": round(agreed / checked, 4) if checked else None,
        "n_comparisons": checked,
        "per_feature": details,
        "deletion_value": "column median",
        "definition": (
            "For each top feature, replace it by its median for every row and "
            "compare the prediction change against the negated SHAP "
            "attribution. Agreement means the explanation correctly predicts "
            "the direction the model would move. Chance is 0.5."
        ),
    }


def stability(model, frame_a: pd.DataFrame, frame_b: pd.DataFrame, columns: list[str]) -> dict:
    """Spearman correlation of mean |SHAP| between two windows."""
    from scipy.stats import spearmanr

    parts: dict[str, np.ndarray] = {}
    for name, subset in (("a", frame_a), ("b", frame_b)):
        subset = subset.reset_index(drop=True)
        if subset.empty:
            return {"available": False, "reason": f"window '{name}' is empty"}
        values, _, _ = shap_values(model, subset[columns])
        parts[name] = np.abs(values).mean(axis=0)

    a, b = parts["a"], parts["b"]
    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return {"available": True, "spearman": None, "reason": "attributions are constant"}
    rho, p_value = spearmanr(a, b)
    top_a = [columns[i] for i in np.argsort(a)[::-1][:5]]
    top_b = [columns[i] for i in np.argsort(b)[::-1][:5]]
    return {
        "available": True,
        "spearman": round(float(rho), 4),
        "p_value": float(p_value),
        "top5_window_a": top_a,
        "top5_window_b": top_b,
        "top5_overlap": len(set(top_a) & set(top_b)),
        "n_features": len(columns),
        "n_rows_a": int(len(frame_a)),
        "n_rows_b": int(len(frame_b)),
        "definition": (
            "Two independently scored windows of the same model should name the "
            "same drivers. Spearman is computed on mean |SHAP| per feature."
        ),
    }


def sanity(model, matrix: pd.DataFrame, values: np.ndarray, columns: list[str],
           seed: int = SEED) -> dict:
    """Does the attribution track the customer's value, or only the column?

    Method: permute one column, recompute its attributions, and measure how
    well the new vector tracks the old one for the *same rows*. If the
    explainer is keyed to the data, permuting the inputs must break the
    agreement; if it is keyed to the column's identity or to a constant bias,
    agreement survives.

    Two quantities are reported:

    ``attribution_decorrelation``  Spearman(original, permuted) per feature.
                                   **This is the pass criterion** -- it should
                                   fall close to zero.
    ``mean_abs_retained_share``    mean |SHAP| after permutation divided by
                                   before. This is *expected to stay near 1*:
                                   a permutation preserves the column's
                                   marginal distribution, and mean |SHAP| is a
                                   function of that distribution. It is
                                   reported so that nobody mistakes an
                                   unchanged magnitude for a failed check.

    Uses LightGBM's ``pred_contrib`` directly rather than re-instantiating a
    TreeExplainer per permutation.
    """
    from scipy.stats import spearmanr

    rng = np.random.default_rng(seed)
    matrix = matrix.reset_index(drop=True)
    mean_abs = np.abs(values).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][:8]

    rows: list[dict] = []
    for position in order:
        column = columns[int(position)]
        if column not in matrix.columns:
            continue
        shuffled = matrix.copy()
        shuffled[column] = rng.permutation(shuffled[column].to_numpy())
        raw = np.asarray(model.predict(shuffled, pred_contrib=True), dtype=float)
        after_values = raw[:, int(position)]
        before_values = values[:, int(position)]

        before = float(np.abs(before_values).mean())
        after = float(np.abs(after_values).mean())
        if np.allclose(before_values, before_values[0]) or np.allclose(
            after_values, after_values[0]
        ):
            decorrelation = None
        else:
            rho, _ = spearmanr(before_values, after_values)
            decorrelation = round(float(rho), 4)

        rows.append(
            {
                "feature": column,
                "mean_abs_shap_before": round(before, 6),
                "mean_abs_shap_after_permutation": round(after, 6),
                "mean_abs_retained_share": round(after / before, 4) if before > 0 else None,
                "attribution_decorrelation": decorrelation,
            }
        )

    decorrelated = [r["attribution_decorrelation"] for r in rows if r["attribution_decorrelation"] is not None]
    retained = [r["mean_abs_retained_share"] for r in rows if r["mean_abs_retained_share"] is not None]
    return {
        "per_feature": rows,
        "mean_attribution_decorrelation": round(float(np.mean(decorrelated)), 4)
        if decorrelated
        else None,
        "mean_retained_share": round(float(np.mean(retained)), 4) if retained else None,
        "pass": bool(decorrelated and float(np.mean(decorrelated)) < 0.30),
        "pass_threshold": "mean attribution decorrelation < 0.30",
        "definition": (
            "Permuting a column must make its attributions for each row "
            "uncorrelated with what they were. A high retained *magnitude* is "
            "not a failure: permutation preserves the value distribution."
        ),
    }


# ---------------------------------------------------------------------------
# Global importance blocks
# ---------------------------------------------------------------------------

def global_importance(model, matrix: pd.DataFrame, columns: list[str], top: int = 12) -> list[dict]:
    values, engine, _ = shap_values(model, sample_rows(matrix))
    mean_abs = np.abs(values).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][:top]
    total = float(mean_abs.sum()) or 1.0
    return [
        {
            "feature": columns[int(i)],
            "mean_abs_shap": round(float(mean_abs[int(i)]), 6),
            "share_of_total": round(float(mean_abs[int(i)]) / total, 4),
        }
        for i in order
    ]


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------

def run(dataset: Dataset, health_bundle: dict | None, verbose: bool = False) -> dict:
    """Explainability checks for every fitted health model."""
    if health_bundle is None or not health_bundle.get("regressors"):
        return {"fitted": False, "reason": "no fitted health regressors"}

    columns = health_bundle["features"]
    folds = {
        cut: dataset.build_frame(f"features_{cut}", lambda c=cut: _features_for(dataset, c))
        for cut in ("validation", "test")
    }

    reports: dict[str, dict] = {}
    for target, model in health_bundle["regressors"].items():
        matrix_validation = _clean(folds["validation"], columns)
        matrix_test = _clean(folds["test"], columns)
        if matrix_validation.empty or matrix_test.empty:
            continue
        if len(matrix_test) > MAX_ROWS:
            matrix_test = sample_rows(matrix_test)

        values, engine, bias = shap_values(model, matrix_test)
        entry = {
            "engine": engine,
            "bias": bias,
            "global_importance": global_importance(model, matrix_test, columns),
            "fidelity": fidelity(model, matrix_test, values, bias),
            "faithfulness": faithfulness(model, matrix_test, values, columns),
            "stability": stability(model, matrix_validation, matrix_test, columns),
            "sanity": sanity(model, matrix_test, values, columns),
        }
        reports[target] = entry
        if verbose:
            f = entry["fidelity"]
            print(
                f"  {target:24s} engine={entry['engine']:24s} "
                f"fidelity_err={f['max_absolute_error']:.2e} "
                f"faithfulness={entry['faithfulness']['direction_agreement']} "
                f"stability={entry['stability'].get('spearman')} "
                f"sanity_pass={entry['sanity']['pass']}"
            )

    return {
        "fitted": True,
        "method": "TreeSHAP (shap.TreeExplainer, or LightGBM pred_contrib as an identical fallback)",
        "targets": reports,
        "checks": ["fidelity", "faithfulness", "stability", "sanity"],
        "sample_limit": MAX_ROWS,
    }


def _features_for(dataset: Dataset, cut: str) -> pd.DataFrame:
    from app.data.splits import build_features

    return build_features(cut).user


def _clean(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    available = [c for c in columns if c in frame.columns]
    matrix = frame[available].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if len(available) < len(columns):
        for column in columns:
            if column not in matrix.columns:
                matrix[column] = 0.0
        matrix = matrix[columns]
    return matrix.reset_index(drop=True)
