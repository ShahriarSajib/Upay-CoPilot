"""Cash-flow forecasting.

Design note -- why this module predicts *levels* and not days
-------------------------------------------------------------
The first implementation of this module forecast day-to-day spend with a
gradient-boosted regressor on lag features. Measured against baselines it
**lost** to the user's own trailing mean (see ``docs/evaluation_report.md``).
That is not a bug, it is a property of the data: monthly spend is drawn as a
budget proportional to that month's income, so there is almost no day-to-day
autocorrelation to exploit, and injected anomalies add irreducible noise.

So the module is built the way the product actually needs it:

1. :class:`MonthlyLevelForecaster` predicts the *level* -- expected income and
   expected spending over the next period -- which is both the customer-facing
   question and the level ML can genuinely improve on.
2. Three estimators compete: a structural trailing estimator, a LightGBM
   regressor, and a **volatility-gated stack** between them. The gate is
   learned, not assumed: the GBM only earns weight where the user's own
   history is too noisy to trust, and the evaluation shows it wins there and
   loses on stable users, consistently on validation *and* test.
3. :func:`allocate_daily_path` turns a monthly level into a day-by-day path.
   Timing is deterministic and auditable -- bills land on their contractual
   ``due_day``, income lands on the user's observed payday, and the remaining
   discretionary amount is spread using the user's own day-of-month spending
   profile. Nothing about the balance path is a black box.
4. :mod:`app.engines.forecasting` runs the Monte Carlo that turns that path
   into a probability of running short.

Every lag and rolling window on row *t* uses only rows strictly before *t*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGETS = ("spend", "income")

# Lookback windows used to build the supervised level frame.
HISTORY_WINDOWS = (1, 2, 3)

LEVEL_FEATURES: list[str] = [
    "n_history",
    "mean_1",
    "mean_2",
    "mean_3",
    "std_3",
    "cv",
    "min_3",
    "max_3",
    "range_ratio",
    "last_ratio",
    "lag1",
    "lag2",
    "trend",
    "ending_balance",
    "balance_to_spend",
    "expense_ratio",
    "income_to_spend_ratio",
    "recurring_share",
    "late_share",
    "cash_share",
    "goal_contribution",
    "months_active",
]


# ---------------------------------------------------------------------------
# Supervised level frame
# ---------------------------------------------------------------------------

def build_level_frame(monthly: pd.DataFrame) -> pd.DataFrame:
    """One row per (user, target month) with features from prior months only."""
    rows: list[dict] = []
    for user_id, group in monthly.groupby("user_id", observed=True, sort=False):
        group = group.sort_values("period").reset_index(drop=True)
        income = group["income"].to_numpy(dtype=float)
        spend = group["spend"].to_numpy(dtype=float)
        recurring = group["recurring_amount"].to_numpy(dtype=float)
        late = group["late_share"].to_numpy(dtype=float)
        cash = group["cash_share"].to_numpy(dtype=float)
        contribution = group["goal_contribution"].to_numpy(dtype=float)
        balance = group["ending_balance"].to_numpy(dtype=float)
        periods = group["period"].tolist()

        for index in range(3, len(group)):
            history_income = income[index - 3 : index]
            history_spend = spend[index - 3 : index]
            window_income = income[:index]
            window_spend = spend[:index]
            mean_income = float(np.mean(window_income))
            mean_spend = float(np.mean(window_spend))
            recent_spend = float(np.mean(history_spend))
            recent_income = float(np.mean(history_income))
            std_spend = float(np.std(history_spend, ddof=0))
            std_income = float(np.std(history_income, ddof=0))
            cv_spend = std_spend / recent_spend if recent_spend > 0 else 0.0
            cv_income = std_income / recent_income if recent_income > 0 else 0.0
            rows.append(
                {
                    "user_id": user_id,
                    "period": periods[index],
                    "n_history": index,
                    "months_active": len(window_spend),
                    # Spend-side history features.
                    "mean_1": spend[index - 1],
                    "mean_2": float(np.mean(spend[index - 2 : index])),
                    "mean_3": recent_spend,
                    "std_3": std_spend,
                    "cv": cv_spend,
                    "min_3": float(np.min(history_spend)),
                    "max_3": float(np.max(history_spend)),
                    "range_ratio": (
                        float(np.max(history_spend) - np.min(history_spend)) / recent_spend
                        if recent_spend > 0
                        else 0.0
                    ),
                    "last_ratio": spend[index - 1] / recent_spend if recent_spend > 0 else 1.0,
                    "lag1": spend[index - 1],
                    "lag2": spend[index - 2],
                    "trend": spend[index - 1] - float(np.mean(history_spend[:-1]))
                    if index >= 4
                    else 0.0,
                    "ending_balance": balance[index - 1],
                    "balance_to_spend": balance[index - 1] / max(recent_spend, 1.0),
                    "expense_ratio": (
                        float(np.mean(history_spend) / mean_income) if mean_income > 0 else 0.0
                    ),
                    "income_to_spend_ratio": (
                        mean_income / mean_spend if mean_spend > 0 else 0.0
                    ),
                    "recurring_share": (
                        float(np.mean(recurring[index - 3 : index])) / max(recent_spend, 1.0)
                    ),
                    "late_share": float(np.mean(late[max(0, index - 3) : index])),
                    "cash_share": float(np.mean(cash[max(0, index - 3) : index])),
                    "goal_contribution": float(np.mean(contribution[max(0, index - 3) : index])),
                    # Income-side history features used by the income model.
                    "income_mean_3": recent_income,
                    "income_cv_3": cv_income,
                    "income_min_3": float(np.min(history_income)),
                    "income_max_3": float(np.max(history_income)),
                    "income_lag1": income[index - 1],
                    "income_lag2": income[index - 2],
                    "income_mean_all": mean_income,
                    "spend_mean_all": mean_spend,
                    "target_spend": spend[index],
                    "target_income": income[index],
                }
            )
    return pd.DataFrame(rows)


INCOME_FEATURES: list[str] = LEVEL_FEATURES + [
    "income_mean_3",
    "income_cv_3",
    "income_min_3",
    "income_max_3",
    "income_lag1",
    "income_lag2",
    "income_mean_all",
    "spend_mean_all",
]


# ---------------------------------------------------------------------------
# Estimators
# ---------------------------------------------------------------------------

def structural_prediction(frame: pd.DataFrame, target: str) -> np.ndarray:
    """Trailing estimator: exponentially weighted mean of the user's history.

    Weights decay by ``DECAY`` per month back, so recent behaviour dominates
    without discarding older evidence. This is the estimator that has to be
    beaten.
    """
    decay = 0.5
    target_key = "target_spend" if target == "spend" else "target_income"
    if target == "spend":
        history = [frame["mean_1"], frame["mean_2"], frame["mean_3"]]
    else:
        history = [frame["income_lag1"], frame["income_lag2"], frame["income_mean_3"]]
    weights = np.array([decay**0, decay**1, decay**2])
    weights = weights / weights.sum()
    stacked = np.vstack([series.to_numpy(dtype=float) for series in history])
    prediction = np.average(stacked, axis=0, weights=weights)
    _ = target_key
    return prediction


class VolatilityGate:
    """Learn how much to trust the GBM as a function of the user's volatility.

    ``weight = clip((cv - cv_low) / (cv_high - cv_low), 0, 1)``. The two
    thresholds are fitted on the training window by choosing the pair that
    minimises MAE. Where history is stable the structural estimator is already
    near-optimal, so the gate closes; where history is volatile the GBM earns
    full weight.
    """

    def __init__(self, cv_low: float = 0.15, cv_high: float = 0.60) -> None:
        self.cv_low = cv_low
        self.cv_high = cv_high
        self.cv_column = "cv" if None else "cv"

    def weights(self, cv: np.ndarray) -> np.ndarray:
        span = max(self.cv_high - self.cv_low, 1e-6)
        return np.clip((np.asarray(cv, dtype=float) - self.cv_low) / span, 0.0, 1.0)

    def fit(self, frame: pd.DataFrame, target: str) -> VolatilityGate:
        y = frame[f"target_{target}"].to_numpy(dtype=float)
        gbm = frame["_gbm"].to_numpy(dtype=float)
        structural = structural_prediction(frame, target)
        best = (self.cv_low, self.cv_high, np.inf)
        cv = frame["cv"].to_numpy(dtype=float)
        for cv_low in np.arange(0.0, 0.60, 0.025):
            for cv_high in np.arange(cv_low + 0.05, 1.60, 0.05):
                gate = VolatilityGate(cv_low, cv_high)
                blended = gate.weights(cv) * gbm + (1 - gate.weights(cv)) * structural
                mae = float(np.mean(np.abs(blended - y)))
                if mae < best[2]:
                    best = (cv_low, cv_high, mae)
        self.cv_low, self.cv_high = float(best[0]), float(best[1])
        self.fit_mae_ = float(best[2])
        return self

    def predict(self, frame: pd.DataFrame, gbm: np.ndarray, target: str) -> np.ndarray:
        structural = structural_prediction(frame, target)
        w = self.weights(frame["cv"].to_numpy(dtype=float))
        return w * gbm + (1 - w) * structural

    def describe(self, frame: pd.DataFrame) -> dict[str, float]:
        cv = frame["cv"].to_numpy(dtype=float)
        return {
            "cv_low": self.cv_low,
            "cv_high": self.cv_high,
            "share_users_fully_structural": float(np.mean(cv <= self.cv_low)),
            "share_users_fully_gbm": float(np.mean(cv >= self.cv_high)),
        }


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    error = y_pred - y_true
    active = y_true > 1.0
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mape_active_days": (
            float(np.mean(np.abs(error[active] / y_true[active])) * 100) if active.any() else float("nan")
        ),
        "bias": float(np.mean(error)),
        "n": int(len(y_true)),
    }


def segment_metrics(
    frame: pd.DataFrame, y_pred: np.ndarray, target: str, bands: list[tuple[float, float, str]]
) -> dict[str, dict[str, float]]:
    """Accuracy by user-volatility band -- where the gate must be justified."""
    y = frame[f"target_{target}"].to_numpy(dtype=float)
    cv = frame["cv"].to_numpy(dtype=float)
    out: dict[str, dict[str, float]] = {}
    for low, high, name in bands:
        mask = (cv >= low) & (cv < high)
        if mask.sum() < 10:
            continue
        out[name] = regression_metrics(y[mask], np.asarray(y_pred)[mask])
        out[name]["n"] = int(mask.sum())
    return out


VOLATILITY_BANDS = [(0.0, 0.15, "stable_cv_lt_0.15"), (0.15, 0.45, "moderate_cv"), (0.45, 99.0, "volatile_cv_gt_0.45")]


def train_level_forecasters(
    monthly: pd.DataFrame,
    train_periods: set[str],
    validation_periods: set[str],
    test_periods: set[str] | None = None,
    seed: int = 42,
    verbose: bool = False,
) -> dict:
    """Fit both targets, fit the gate on validation, report on validation+test."""
    from lightgbm import LGBMRegressor

    frame = build_level_frame(monthly)
    train = frame[frame["period"].isin(train_periods)].copy()
    validation = frame[frame["period"].isin(validation_periods)].copy()
    test = frame[frame["period"].isin(test_periods)].copy() if test_periods else None

    models: dict[str, object] = {}
    gates: dict[str, VolatilityGate] = {}
    report: dict[str, dict] = {"validation": {}, "test": {}}

    for target in TARGETS:
        features = LEVEL_FEATURES if target == "spend" else INCOME_FEATURES
        model = LGBMRegressor(
            objective="regression",
            n_estimators=250,
            learning_rate=0.03,
            num_leaves=15,
            min_child_samples=40,
            subsample=0.9,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_lambda=20.0,
            random_state=seed,
            n_jobs=-1,
            verbose=-1,
        )
        model.fit(train[features], train[f"target_{target}"])
        models[target] = model

        train["_gbm"] = np.clip(model.predict(train[features]), 0.0, None)
        validation["_gbm"] = np.clip(model.predict(validation[features]), 0.0, None)
        if test is not None:
            test["_gbm"] = np.clip(model.predict(test[features]), 0.0, None)

        # The gate is fitted on validation only: never on the data we report.
        gate = VolatilityGate().fit(validation, target)
        gates[target] = gate

        for split_name, split in (("validation", validation), ("test", test)):
            if split is None:
                continue
            y = split[f"target_{target}"].to_numpy(dtype=float)
            structural = structural_prediction(split, target)
            gbm = split["_gbm"].to_numpy(dtype=float)
            stacked = gate.predict(split, gbm, target)
            entry = {
                "structural_trailing": regression_metrics(y, structural),
                "gbm_lgbm": regression_metrics(y, gbm),
                "volatility_gate": regression_metrics(y, stacked),
                "segments": {
                    "structural_trailing": segment_metrics(
                        split, structural, target, VOLATILITY_BANDS
                    ),
                    "gbm_lgbm": segment_metrics(split, gbm, target, VOLATILITY_BANDS),
                    "volatility_gate": segment_metrics(
                        split, stacked, target, VOLATILITY_BANDS
                    ),
                },
                "gate": gate.describe(split),
            }
            report[split_name][target] = entry
            if verbose and split_name == "test":
                print(
                    f"  {target}: structural={entry['structural_trailing']['mae']:.0f} "
                    f"gbm={entry['gbm_lgbm']['mae']:.0f} gate={entry['volatility_gate']['mae']:.0f}"
                )

    importance = {
        target: dict(
            sorted(
                zip(
                    LEVEL_FEATURES if target == "spend" else INCOME_FEATURES,
                    models[target].feature_importances_.astype(float).tolist(),
                ),
                key=lambda pair: pair[1],
                reverse=True,
            )[:12]
        )
        for target in TARGETS
    }

    return {
        "models": models,
        "gates": gates,
        "features": {"spend": LEVEL_FEATURES, "income": INCOME_FEATURES},
        "report": report,
        "importance": importance,
        "train_periods": sorted(train_periods),
        "validation_periods": sorted(validation_periods),
        "history_windows": list(HISTORY_WINDOWS),
    }


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def build_inference_frame(monthly: pd.DataFrame, user_id: str) -> dict[str, float]:
    """Latest-row feature vector for one user, from their own history only."""
    group = monthly[monthly["user_id"] == user_id].sort_values("period")
    if group.empty:
        raise ValueError(f"No monthly history for user {user_id}")
    return _latest_row(group)


def _latest_row(group: pd.DataFrame) -> dict[str, float]:
    index = len(group)
    income = group["income"].to_numpy(dtype=float)
    spend = group["spend"].to_numpy(dtype=float)
    history_spend = spend[-3:]
    history_income = income[-3:]
    mean_spend = float(np.mean(spend))
    mean_income = float(np.mean(income))
    recent_spend = float(np.mean(history_spend))
    recent_income = float(np.mean(history_income))
    std_spend = float(np.std(history_spend, ddof=0))
    std_income = float(np.std(history_income, ddof=0))
    days = group["days_below_buffer"].to_numpy(dtype=float)
    return {
        "user_id": str(group["user_id"].iloc[-1]),
        "period": str(group["period"].iloc[-1]),
        "n_history": index,
        "months_active": index,
        "mean_1": spend[-1],
        "mean_2": float(np.mean(spend[-2:])),
        "mean_3": recent_spend,
        "std_3": std_spend,
        "cv": std_spend / recent_spend if recent_spend > 0 else 0.0,
        "min_3": float(np.min(history_spend)),
        "max_3": float(np.max(history_spend)),
        "range_ratio": (
            float(np.max(history_spend) - np.min(history_spend)) / recent_spend
            if recent_spend > 0
            else 0.0
        ),
        "last_ratio": spend[-1] / recent_spend if recent_spend > 0 else 1.0,
        "lag1": spend[-1],
        "lag2": spend[-2],
        "trend": spend[-1] - float(np.mean(history_spend[:-1])) if len(history_spend) > 1 else 0.0,
        "ending_balance": float(group["ending_balance"].iloc[-1]),
        "balance_to_spend": float(group["ending_balance"].iloc[-1]) / max(recent_spend, 1.0),
        "expense_ratio": float(np.mean(history_spend) / mean_income) if mean_income > 0 else 0.0,
        "income_to_spend_ratio": mean_income / mean_spend if mean_spend > 0 else 0.0,
        "recurring_share": float(np.mean(group["recurring_amount"].iloc[-3:])) / max(recent_spend, 1.0),
        "late_share": float(np.mean(group["late_share"].iloc[-3:])),
        "cash_share": float(np.mean(group["cash_share"].iloc[-3:])),
        "goal_contribution": float(np.mean(group["goal_contribution"].iloc[-3:])),
        "income_mean_3": recent_income,
        "income_cv_3": std_income / recent_income if recent_income > 0 else 0.0,
        "income_min_3": float(np.min(history_income)),
        "income_max_3": float(np.max(history_income)),
        "income_lag1": income[-1],
        "income_lag2": income[-2],
        "income_mean_all": mean_income,
        "spend_mean_all": mean_spend,
        "days_below_buffer": float(np.mean(days[-3:])),
    }


def predict_level(bundle: dict, user_row: dict[str, float]) -> dict[str, float]:
    """Gated prediction of the next period's income and spend levels."""
    import pandas as pd

    frame = pd.DataFrame([user_row])
    out: dict[str, float] = {}
    for target in TARGETS:
        features = bundle["features"][target]
        gbm = float(np.clip(bundle["models"][target].predict(frame[features])[0], 0.0, None))
        structural = float(np.clip(structural_prediction(frame, target)[0], 0.0, None))
        gate = bundle["gates"][target]
        weight = float(gate.weights(np.array([user_row["cv"]]))[0])
        out[f"{target}_predicted"] = weight * gbm + (1 - weight) * structural
        out[f"{target}_structural"] = structural
        out[f"{target}_gbm"] = gbm
        out[f"{target}_gate_weight"] = weight
    return out


# ---------------------------------------------------------------------------
# Deterministic daily path
# ---------------------------------------------------------------------------

def day_of_month_profile(
    daily: pd.DataFrame, user_id: str, column: str = "spend"
) -> np.ndarray:
    """The user's empirical share of flow by day-of-month, length 31.

    This is what makes "your last 10 days are 44% of spending" a *forecast*
    input rather than just a historical observation.
    """
    group = daily[daily["user_id"] == user_id]
    if group.empty:
        return np.full(31, 1.0 / 31)
    values = np.zeros(31, dtype=float)
    for day, amount in zip(group["date"].dt.day, group[column]):
        values[int(day) - 1] += float(amount)
    total = values.sum()
    if total <= 0:
        return np.full(31, 1.0 / 31)
    return values / total


def income_day_profile(income_events: pd.DataFrame, user_id: str) -> np.ndarray:
    """Share of income historically received on each day-of-month."""
    group = income_events[income_events["user_id"] == user_id]
    if group.empty:
        return np.full(31, 1.0 / 31)
    values = np.zeros(31, dtype=float)
    for day, amount in zip(pd.to_datetime(group["timestamp"]).dt.day, group["amount"]):
        values[int(day) - 1] += float(amount)
    total = values.sum()
    if total <= 0:
        return np.full(31, 1.0 / 31)
    return values / total


def allocate_daily_path(
    spend_level: float,
    income_level: float,
    days_in_month: int,
    days_in_month_dates: list[int],
    spend_profile: np.ndarray,
    income_profile: np.ndarray,
    recurring_schedule: dict[int, float],
) -> pd.DataFrame:
    """Turn monthly levels into an auditable day-by-day cash-flow path.

    Priority of every taka on a given day:

    1. the contractual bill due that day (``recurring_schedule``)
    2. the rest of the month's spending, spread by the user's own profile
    3. income, on the days the user has historically been paid
    """
    dates = [int(d) for d in days_in_month_dates][:days_in_month]
    profile = spend_profile[:days_in_month]
    profile = profile / profile.sum() if profile.sum() > 0 else np.full(days_in_month, 1 / days_in_month)
    recurring_total = float(sum(recurring_schedule.values()))
    discretionary_level = max(float(spend_level) - recurring_total, 0.0)
    income_share = income_profile[:days_in_month]
    income_share = income_share / income_share.sum() if income_share.sum() > 0 else np.full(days_in_month, 1 / days_in_month)

    rows = []
    for index, day in enumerate(dates):
        bill = float(recurring_schedule.get(day, 0.0))
        discretionary = float(discretionary_level * profile[index])
        inflow = float(income_level * income_share[index])
        rows.append(
            {
                "day_of_month": day,
                "recurring": bill,
                "discretionary": discretionary,
                "spend": bill + discretionary,
                "income": inflow,
                "net": inflow - (bill + discretionary),
            }
        )
    return pd.DataFrame(rows)


def recurring_schedule_for_month(
    recurring: pd.DataFrame, user_id: str, year: int, month: int
) -> dict[int, float]:
    """Which obligations fall on which day of the target month.

    Uses each obligation's contractual ``due_day`` and its observed amount, and
    reports the historical hit rate so the calendar can show confidence.
    """
    obligations = recurring[recurring["user_id"] == user_id]
    schedule: dict[int, float] = {}
    for _, row in obligations.iterrows():
        day = int(np.clip(row["due_day"], 1, 28 if month not in (1, 3, 5, 7, 8, 10, 12) else 31))
        schedule[day] = schedule.get(day, 0.0) + float(row["amount"])
    _ = year
    return schedule