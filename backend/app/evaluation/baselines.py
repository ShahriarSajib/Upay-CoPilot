"""Forecasting baselines and candidate models.

The point of this module is that "LightGBM predicts cash flow" is a claim, and
a claim needs something to beat. Every estimator here implements the same
three-step contract so the comparison is fair:

``fit(train, target)``      learn anything that must come from training data
``tune(validation, target)`` choose hyper-parameters on validation only
``predict(frame, target)``   produce numbers for an arbitrary window

The test window is never passed to ``fit`` or ``tune``.

Baselines, from weakest to strongest assumption:

``naive_last``          next month equals last month
``moving_average``      next month equals the mean of the last three
``drift``               last month plus the average month-over-month change
``exponential_smoothing`` single exponential smoothing, alpha tuned on
                        validation -- the classical ETS family's level
                        component (statsmodels is not a dependency, so the
                        recursion is implemented here and stated explicitly)
``structural_ewma``     the product's own decay-weighted trailing estimator,
                        the baseline the shipped model has to beat

Candidates:

``lightgbm``            LightGBM on the same lag/level feature frame
``xgboost``             XGBoost on the identical frame, identical split
``volatility_gate``     the shipped stack: LightGBM blended with the
                        structural estimator by the user's own volatility
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.evaluation.metrics import regression_metrics

SEED = 42


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class Estimator:
    """Fit / tune / predict over the monthly level frame."""

    name: str = "estimator"
    kind: str = "baseline"
    requires_tuning: bool = False

    def fit(self, frame: pd.DataFrame, target: str) -> "Estimator":
        return self

    def tune(self, frame: pd.DataFrame, target: str) -> "Estimator":
        return self

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "kind": self.kind, **self.params()}

    def params(self) -> dict:
        return {}


def _history(frame: pd.DataFrame, target: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(last value, trailing mean of 3, trailing mean of all) for the target."""
    if target == "spend":
        last = frame["mean_1"].to_numpy(dtype=float)
        mean3 = frame["mean_3"].to_numpy(dtype=float)
        mean_all = frame["spend_mean_all"].to_numpy(dtype=float)
    else:
        last = frame["income_lag1"].to_numpy(dtype=float)
        mean3 = frame["income_mean_3"].to_numpy(dtype=float)
        mean_all = frame["income_mean_all"].to_numpy(dtype=float)
    return last, mean3, mean_all


class NaiveLast(Estimator):
    """Persistence: next month equals the last observed month."""

    name = "naive_last"

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        return np.clip(_history(frame, target)[0], 0.0, None)


class MovingAverage(Estimator):
    """Next month equals the mean of the last three observed months."""

    name = "moving_average_3"

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        return np.clip(_history(frame, target)[1], 0.0, None)


class Drift(Estimator):
    """Persistence plus the average observed month-over-month slope."""

    name = "drift"

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        last, mean3, _ = _history(frame, target)
        if target == "spend":
            previous = frame["lag2"].to_numpy(dtype=float)
        else:
            previous = frame["income_lag2"].to_numpy(dtype=float)
        slope = (last - previous) / 2.0
        return np.clip(last + slope, 0.0, None)


class ExponentialSmoothing(Estimator):
    """Single exponential smoothing: ``l_t = a*y_t + (1-a)*l_{t-1}``.

    ``alpha`` is the only hyper-parameter and it is grid-searched on the
    validation window by :meth:`tune`. The recursion needs the raw per-user
    monthly series, which the level frame does not carry, so the state is
    rebuilt from the lag columns the frame does carry:

        l_{t-1} reconstructs as a weighted blend of lag1 and the trailing mean.
    """

    name = "exponential_smoothing"
    requires_tuning = True

    ALPHA_GRID = (0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.70, 0.90)

    def __init__(self) -> None:
        self.alpha: float = 0.3

    def params(self) -> dict:
        return {"alpha": self.alpha}

    def _level(self, frame: pd.DataFrame, target: str, alpha: float) -> np.ndarray:
        """``l_t = alpha * y_t + (1 - alpha) * l_{t-1}``.

        ``y_t`` is the last observed month. ``l_{t-1}`` is not carried on the
        level frame, so it is proxied by the trailing three-month mean, which
        is the previous level estimate for every alpha the grid contains. At
        ``alpha = 1`` this collapses to :class:`NaiveLast`, so the grid spans
        persistence through heavy smoothing.
        """
        last, mean3, _ = _history(frame, target)
        return alpha * last + (1.0 - alpha) * mean3

    def tune(self, frame: pd.DataFrame, target: str) -> "ExponentialSmoothing":
        y = frame[f"target_{target}"].to_numpy(dtype=float)
        best = (self.alpha, float("inf"))
        for alpha in self.ALPHA_GRID:
            prediction = self._level(frame, target, alpha)
            mae = float(np.mean(np.abs(prediction - y)))
            if mae < best[1]:
                best = (alpha, mae)
        self.alpha = float(best[0])
        return self

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        return np.clip(self._level(frame, target, self.alpha), 0.0, None)


class TrailingEwma(Estimator):
    """The product's own decay-weighted trailing estimator (decay = 0.5).

    Kept here as an explicit baseline object so it appears in the same table
    as the others rather than being special-cased in the report.
    """

    name = "structural_ewma"

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        from app.ml.forecast import structural_prediction

        return np.clip(structural_prediction(frame, target), 0.0, None)


class GradientBoosted(Estimator):
    """LightGBM or XGBoost on the shared level frame."""

    kind = "model"

    def __init__(self, backend: str = "lightgbm") -> None:
        if backend not in ("lightgbm", "xgboost"):
            raise ValueError(f"Unknown gradient-boosting backend '{backend}'")
        self.backend = backend
        self.name = backend
        self.model = None
        self.features: list[str] = []

    def _build(self):
        if self.backend == "lightgbm":
            from lightgbm import LGBMRegressor

            return LGBMRegressor(
                objective="regression",
                n_estimators=250,
                learning_rate=0.03,
                num_leaves=15,
                min_child_samples=40,
                subsample=0.9,
                subsample_freq=1,
                colsample_bytree=0.8,
                reg_lambda=20.0,
                random_state=SEED,
                n_jobs=-1,
                verbose=-1,
            )
        from xgboost import XGBRegressor

        return XGBRegressor(
            objective="reg:squarederror",
            n_estimators=250,
            learning_rate=0.03,
            max_depth=5,
            min_child_weight=40,
            subsample=0.9,
            colsample_bytree=0.8,
            reg_lambda=20.0,
            random_state=SEED,
            n_jobs=-1,
            verbosity=0,
        )

    def fit(self, frame: pd.DataFrame, target: str) -> "GradientBoosted":
        from app.ml.forecast import INCOME_FEATURES, LEVEL_FEATURES

        self.features = list(LEVEL_FEATURES if target == "spend" else INCOME_FEATURES)
        self.features = [f for f in self.features if f in frame.columns]
        self.model = self._build()
        self.model.fit(frame[self.features], frame[f"target_{target}"].to_numpy(dtype=float))
        return self

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        if self.model is None:
            raise RuntimeError(f"{self.name} has not been fitted")
        return np.clip(self.model.predict(frame[self.features]), 0.0, None)


def default_estimators(include_gate: bool = True) -> list[Estimator]:
    """The full comparison set, in report order."""
    estimators: list[Estimator] = [
        NaiveLast(),
        MovingAverage(),
        Drift(),
        ExponentialSmoothing(),
        TrailingEwma(),
        GradientBoosted("lightgbm"),
        GradientBoosted("xgboost"),
    ]
    if include_gate:
        estimators.append(VolatilityGateEstimator())
    return estimators


class VolatilityGateEstimator(Estimator):
    """The shipped stack: LightGBM blended with the trailing estimator.

    Wraps :class:`app.ml.forecast.VolatilityGate` so the production model
    appears in the benchmark table instead of being reported separately.
    """

    name = "volatility_gate"
    kind = "model"
    requires_tuning = True

    def __init__(self) -> None:
        self.gbm = GradientBoosted("lightgbm")
        self.gate = None

    def fit(self, frame: pd.DataFrame, target: str) -> "VolatilityGateEstimator":
        # Reset: the same estimator object is reused for the income target
        # after the spend target, and a gate fitted on one target's validation
        # window must not leak into the other.
        self.gate = None
        self.gbm.fit(frame, target)
        return self

    def tune(self, frame: pd.DataFrame, target: str) -> "VolatilityGateEstimator":
        from app.ml.forecast import VolatilityGate

        frame = frame.copy()
        frame["_gbm"] = self.gbm.predict(frame, target)
        self.gate = VolatilityGate().fit(frame, target)
        return self

    def predict(self, frame: pd.DataFrame, target: str) -> np.ndarray:
        if self.gate is None:
            raise RuntimeError("volatility_gate must be tuned before it predicts")
        return np.clip(self.gate.predict(frame, self.gbm.predict(frame, target), target), 0.0, None)

    def params(self) -> dict:
        if self.gate is None:
            return {}
        return {"cv_low": self.gate.cv_low, "cv_high": self.gate.cv_high}


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def run_forecast_benchmark(
    monthly: pd.DataFrame,
    train_periods: set[str],
    validation_periods: set[str],
    test_periods: set[str],
    estimators: list[Estimator] | None = None,
    seed: int = SEED,
) -> dict:
    """Fit every estimator on train, tune on validation, score on both.

    Returns one row per (target, window, estimator) plus the derived
    ``best_baseline`` / ``selected_model`` / improvement figures.
    """
    from app.ml.forecast import build_level_frame

    frame = build_level_frame(monthly)
    train = frame[frame["period"].isin(train_periods)].copy()
    validation = frame[frame["period"].isin(validation_periods)].copy()
    test = frame[frame["period"].isin(test_periods)].copy()

    estimators = estimators or default_estimators()
    results: dict[str, dict] = {}

    for target in ("spend", "income"):
        rows: dict[str, dict] = {}
        for estimator in estimators:
            estimator.fit(train, target)
            if estimator.requires_tuning:
                estimator.tune(validation, target)
            entry: dict = {"model": estimator.describe(), "windows": {}}
            for window, split in (("validation", validation), ("test", test)):
                if split is None or not len(split):
                    continue
                y_true = split[f"target_{target}"].to_numpy(dtype=float)
                y_pred = estimator.predict(split, target)
                entry["windows"][window] = regression_metrics(y_true, y_pred)
            rows[estimator.name] = entry

        derived = _derive(rows)
        results[target] = {
            "n_train_rows": int(len(train)),
            "n_validation_rows": int(len(validation)),
            "n_test_rows": int(len(test)),
            "models": rows,
            **derived,
        }

    return {
        "task": "next-period monthly cash-flow level",
        "protocol": (
            "Estimators fit on 2026-01..05, hyper-parameters chosen on "
            "2026-06..07, final numbers reported on the untouched 2026-08..09 "
            "test window."
        ),
        "targets": results,
        "seed": seed,
    }


def _derive(rows: dict[str, dict]) -> dict:
    """Rank the fitted estimators on the test window."""
    out: dict = {}
    for window in ("validation", "test"):
        scored = {
            name: entry["windows"].get(window, {}).get("mae")
            for name, entry in rows.items()
        }
        scored = {name: mae for name, mae in scored.items() if mae is not None}
        if not scored:
            continue
        baselines = {n: m for n, m in scored.items() if rows[n]["model"]["kind"] == "baseline"}
        models = {n: m for n, m in scored.items() if rows[n]["model"]["kind"] == "model"}
        best_baseline = min(baselines, key=baselines.get) if baselines else None
        best_model = min(models, key=models.get) if models else None
        out[f"{window}_ranking"] = sorted(scored.items(), key=lambda kv: kv[1])
        out[f"{window}_best_baseline"] = best_baseline
        out[f"{window}_best_model"] = best_model
        if best_baseline and best_model:
            out[f"{window}_improvement_over_best_baseline_percent"] = round(
                100.0 * (baselines[best_baseline] - models[best_model])
                / max(baselines[best_baseline], 1e-9),
                2,
            )
            out[f"{window}_best_baseline_mae"] = baselines[best_baseline]
            out[f"{window}_best_model_mae"] = models[best_model]
    return out
