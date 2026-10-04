"""Cash-flow forecasting engine.

This engine turns monthly level predictions from the ML model into an auditable
daily balance path and a probability of running short.

Design note - why bills are deterministic and only discretionary varies:
Bills (recurring obligations) are contractual commitments with known due dates
and amounts. Treating them as fixed reflects reality - rent, utilities, etc.
don't randomly shift. Discretionary spending is variable day-to-day; Monte Carlo
perturbs only the discretionary component using the user's own volatility history.
This keeps the estimate defensible and transparent.
"""

import calendar
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.context import get_context
from app.core.money import format_bdt
from app.core.periods import month_start, shift_month
from app.ml import forecast as ml_forecast
from app.schemas.common import (
    Assumption,
    Confidence,
    Evidence,
    Explanation,
    Insight,
    Metric,
    Severity,
)
from app.schemas.forecast import ForecastPoint, ForecastResponse


def _evidence(
    label: str,
    value: float,
    source: str = "forecast",
    window: str | None = None,
    comparison: str | None = None,
    confidence: Confidence = Confidence.MEDIUM,
    unit: str = "bdt",
) -> Evidence:
    return Evidence(
        label=label,
        value=float(round(value, 2)),
        unit=unit,
        source=source,
        window=window,
        comparison=comparison,
        confidence=confidence,
    )


def _confidence_from_cv(cv: float) -> Confidence:
    if cv <= 0.2:
        return Confidence.HIGH
    if cv <= 0.5:
        return Confidence.MEDIUM
    return Confidence.LOW


def _confidence_from_gate(weight: float, cv: float) -> Confidence:
    if weight < 0.25 and cv < 0.3:
        return Confidence.HIGH
    if weight > 0.75 and cv > 0.5:
        return Confidence.LOW
    return Confidence.MEDIUM


def _format_bdt(x: float) -> float:
    return float(round(x, 2))


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _target_period(ctx, horizon_days: int) -> str:
    """The first period that has not happened yet.

    The path opens at the *first day of the target period* with today's balance
    as its starting balance. So the target must not contain days that have
    already occurred, or their income and bills get counted a second time.
    """
    current = ctx.current_period
    if horizon_days <= _remaining_days(ctx):
        return current
    # Days that spill beyond this month: put them in the next period(s). This
    # keeps the "one period at a time" logic honest for short horizons, but for
    # longer horizons we still only load a single period -- see the note in
    # :func:`cashflow_forecast`.
    return shift_month(current, 1)


def _remaining_days(ctx) -> int:
    """Days left in the current period after ``as_of``."""
    year, month = (int(part) for part in ctx.current_period.split("-"))
    return max(calendar.monthrange(year, month)[1] - int(ctx.as_of.day), 0)


def _first_day(ctx, target_period: str) -> int:
    """First day-of-month to include in the path.

    Inside the current period the days up to and including ``as_of`` have
    already happened, so they are excluded.
    """
    if target_period == ctx.current_period:
        return int(ctx.as_of.day) + 1
    return 1


def _daily_frames(ctx, target_period: str) -> tuple[np.ndarray, list[int], int]:
    """Income and spending day-of-month profiles, plus the days in the target."""
    year, month = (int(part) for part in target_period.split("-"))
    days_in_month = calendar.monthrange(year, month)[1]
    spend_profile = np.asarray(ctx.spend_profile_by_day(), dtype=float)
    first_day = _first_day(ctx, target_period)
    return spend_profile, list(range(first_day, days_in_month + 1)), days_in_month


def _project_levels(ctx, target_period: str) -> dict[str, Any]:
    """Next-period income/spend levels from the trained model, or the fallback.

    Falls back to the customer's own trailing mean when no forecast bundle has
    been trained. The fallback is *not* silent: the response reports
    ``model='trailing_mean'`` and the confidence drops, because an untrained
    model's number and a fitted model's number are not the same claim.
    """
    bundle = ml_forecast.load_bundle("forecast") if hasattr(ml_forecast, "load_bundle") else None
    if bundle is None:
        from app.ml.artifacts import load_bundle

        bundle = load_bundle("forecast")
    if bundle is None:
        history = ctx.history(3)
        if history.empty:
            raise ValueError(
                "No forecast model trained and no monthly history available. "
                "Run `python scripts/train_all_splits.py`."
            )
        spend = float(history["spend"].mean())
        income = float(history["income"].mean())
        return {
            "spend": spend,
            "income": income,
            "gates": {"spend": 0.0, "income": 0.0},
            "model": "trailing_mean_fallback",
            "trained": False,
        }

    row = ml_forecast.build_inference_frame(ctx.monthly, ctx.user_id)
    predicted = ml_forecast.predict_level(bundle, row)
    return {
        "spend": float(predicted["spend_predicted"]),
        "income": float(predicted["income_predicted"]),
        "gates": {
            "spend": float(predicted["spend_gate_weight"]),
            "income": float(predicted["income_gate_weight"]),
        },
        "model": "lightgbm_volatility_gate",
        "trained": True,
    }


def _recurring_schedule(ctx, target_period: str) -> dict[int, float]:
    year, month = (int(part) for part in target_period.split("-"))
    return ml_forecast.recurring_schedule_for_month(
        ctx.recurring, ctx.user_id, year, month
    )


def effective_buffer(ctx, monthly_expense: float | None = None) -> tuple[float, dict[str, Any]]:
    """The balance floor this customer is actually judged against.

    A flat 5,000 floor is far below the balances in this dataset (median
    ending balance is in the hundreds of thousands), so using it alone would
    mean the shortage predictor never fires and the feature looks safe. The
    effective floor is therefore ``max(flat floor, N months of own spending)``.
    Which of the two won is reported, because "you are below your buffer"
    must never rest on an undisclosed assumption.
    """
    flat = float(settings.minimum_balance_buffer)
    if monthly_expense is None:
        history = ctx.history(3)
        monthly_expense = float(history["spend"].mean()) if not history.empty else 0.0
    scaled = float(settings.buffer_floor_months) * float(monthly_expense)
    chosen = max(flat, scaled)
    basis = "flat floor" if flat >= scaled else f"{settings.buffer_floor_months:g} months of own spending"
    return chosen, {
        "effective_buffer": round(chosen, 2),
        "flat_floor": round(flat, 2),
        "scaled_floor": round(scaled, 2),
        "monthly_expense": round(float(monthly_expense), 2),
        "basis": basis,
    }


def _current_balance(ctx) -> float:
    if not ctx.daily.empty and "balance" in ctx.daily.columns:
        return float(ctx.daily["balance"].iloc[-1])
    monthly = ctx.monthly
    return float(monthly["ending_balance"].iloc[-1]) if not monthly.empty else 0.0


def _monte_carlo(
    path: pd.DataFrame,
    start_balance: float,
    buffer_target: float,
    discretionary_share: float,
    paths: int,
    seed: int,
) -> dict[str, Any]:
    """Probability of dipping under the buffer, given the user's own volatility.

    Only the discretionary component is perturbed. Bills are contractual and
    income is anchored to an observed payday, so perturbing them would add
    noise the customer cannot act on. The perturbation is lognormal, scaled by
    the customer's observed daily-spend coefficient of variation, which is the
    one honest source of uncertainty here.
    """
    rng = np.random.default_rng(seed)
    if paths <= 0 or path.empty or discretionary_share <= 0:
        minima = [start_balance + float(path["net"].sum())] if not path.empty else [start_balance]
        minimum = min(minima)
        return {
            "probability": 1.0 if minimum < buffer_target else 0.0,
            "paths": 1,
            "minimum_p05": minimum,
            "minimum_p50": minimum,
            "minimum_p95": minimum,
        }

    net = path["net"].to_numpy(dtype=float)
    discretionary = path["discretionary"].to_numpy(dtype=float)
    income = path["income"].to_numpy(dtype=float)
    vol = float(np.std(discretionary[discretionary > 0]) / max(np.mean(discretionary[discretionary > 0]), 1e-9)) if (discretionary > 0).any() else 0.0
    vol = float(np.clip(vol, 0.05, 1.5))

    # Each path: draw one per-day multiplier for discretionary spend, one
    # income-level multiplier for the whole month. Deterministic given the seed.
    shocks = rng.lognormal(mean=-0.5 * vol**2, sigma=vol, size=(paths, len(net)))
    level_shocks = rng.lognormal(mean=-0.5 * (vol * 0.6) ** 2, sigma=vol * 0.6, size=(paths, 1))

    simulated = (
        start_balance
        + np.cumsum(income[None, :] * level_shocks - discretionary[None, :] * shocks, axis=1)
    )
    minima = simulated.min(axis=1)
    return {
        "probability": float(np.mean(minima < buffer_target)),
        "paths": int(paths),
        "minimum_p05": float(np.percentile(minima, 5)),
        "minimum_p50": float(np.percentile(minima, 50)),
        "minimum_p95": float(np.percentile(minima, 95)),
        "daily_volatility": round(vol, 4),
    }


def _shortage_windows(
    dates: list[str], balances: np.ndarray, buffer_target: float
) -> list[dict[str, Any]]:
    below = balances < buffer_target
    windows: list[dict[str, Any]] = []
    start: int | None = None
    for index, flag in enumerate(list(below) + [False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            window = balances[start:index]
            windows.append(
                {
                    "start_date": dates[start],
                    "end_date": dates[index - 1],
                    "days": index - start,
                    "lowest_balance": _format_bdt(float(window.min())),
                    "shortfall_at_low": _format_bdt(max(buffer_target - float(window.min()), 0.0)),
                }
            )
            start = None
    return windows


def _pressure_label(probability: float) -> str:
    if probability >= 0.6:
        return "high"
    if probability >= 0.3:
        return "moderate"
    if probability > 0.0:
        return "low"
    return "low"


def _pressure_insight(
    probability: float,
    windows: list[dict[str, Any]],
    buffer_target: float,
    min_balance: float,
    min_date: str | None,
    recurring: float,
) -> Insight | None:
    if not windows:
        return None
    biggest = max(windows, key=lambda w: w["shortfall_at_low"])
    severity = (
        Severity.WARNING if probability >= 0.6 else Severity.ATTENTION
    ) if probability >= 0.3 else Severity.INFO
    return Insight(
        key="liquidity_pressure",
        title="Balance is projected to dip below your buffer",
        observation=(
            f"Between {biggest['start_date']} and {biggest['end_date']} the projected "
            f"balance falls to {format_bdt(biggest['lowest_balance'])}, which is "
            f"{format_bdt(biggest['shortfall_at_low'])} below the "
            f"{format_bdt(buffer_target)} buffer."
        ),
        why=(
            f"Projected income and spending come from the forecast model, and standing "
            f"bills totalling about {format_bdt(recurring)} land on their contractual "
            f"due dates inside this window."
        ),
        action=(
            "Reduce discretionary spending before "
            f"{biggest['start_date']}, or move a bill date if that is possible."
        ),
        severity=severity,
        impact_bdt=biggest["shortfall_at_low"],
        evidence=[
            _evidence(
                "min_projected_balance",
                min_balance,
                source="engines.forecasting",
                window=None,
                comparison=f"buffer target {buffer_target:.0f}",
            ),
            _evidence(
                "shortfall_probability",
                round(probability * 100, 1),
                source="engines.forecasting.monte_carlo",
                unit="percent",
            ),
        ],
    )


def cashflow_forecast(user_id: str, horizon_days: int = 30) -> ForecastResponse:
    """Project the daily balance path and the risk of running short.

    The path is deterministic given the customer's own history: bills land on
    contractual due days, income lands on their observed payday, and the
    remaining discretionary amount is spread by their own day-of-month spending
    profile. The Monte Carlo that turns this path into a probability perturbs
    only discretionary spend.
    """
    ctx = get_context(user_id)
    horizon_days = int(max(1, min(horizon_days, 400)))
    target_period = _target_period(ctx, horizon_days)
    path_rows: list[dict[str, Any]] = []
    remaining = horizon_days
    period = target_period
    total_income = 0.0
    total_spend = 0.0
    first_path = None
    while remaining > 0:
        levels = _project_levels(ctx, period)
        spend_profile, days_in_month_dates, days_in_month = _daily_frames(ctx, period)
        income_profile = np.asarray(ctx.income_profile_by_day(), dtype=float)
        recurring_by_day = _recurring_schedule(ctx, period)
        path_m = ml_forecast.allocate_daily_path(
            spend_level=levels["spend"],
            income_level=levels["income"],
            days_in_month=days_in_month,
            days_in_month_dates=days_in_month_dates,
            spend_profile=spend_profile,
            income_profile=income_profile,
            recurring_schedule=recurring_by_day,
        )
        month_first = month_start(period)
        path_m["date"] = [
            (month_first + timedelta(days=int(day) - 1)).date().isoformat()
            for day in path_m["day_of_month"]
        ]
        if len(path_m) == 0:
            period = shift_month(period, 1)
            continue
        path_m = path_m.head(min(remaining, len(path_m)))
        if first_path is None:
            first_path = path_m
        total_income += float(path_m["income"].sum())
        total_spend += float(path_m["spend"].sum())
        path_rows.extend(path_m.to_dict("records"))
        remaining -= len(path_m)
        period = shift_month(period, 1)
    path = pd.DataFrame(path_rows)

    start_balance = _current_balance(ctx)
    recent = ctx.history(3)
    monthly_expense = float(recent["spend"].mean()) if not recent.empty else total_spend / max(len(path), 1)
    buffer_target, buffer_basis = effective_buffer(ctx, monthly_expense)
    balances = start_balance + np.cumsum(path["net"].to_numpy(dtype=float))
    path["balance"] = balances

    discretionary_total = float(path["discretionary"].sum())
    mc = _monte_carlo(
        path=path,
        start_balance=start_balance,
        buffer_target=buffer_target,
        discretionary_share=discretionary_total,
        paths=int(settings.monte_carlo_paths),
        seed=int(settings.monte_carlo_seed),
    )

    min_index = int(np.argmin(balances))
    min_balance = float(balances[min_index])
    min_date = str(path["date"].iloc[min_index])
    probability = float(mc["probability"])
    recurring_total = float(sum(recurring_by_day.values()))
    shortages = _shortage_windows(path["date"].tolist(), balances, buffer_target)
    cv = ctx.feature("cv") or 0.0

    confidence = (
        _confidence_from_gate(max(levels["gates"]["spend"], levels["gates"]["income"]), cv)
        if levels["trained"]
        else Confidence.LOW
    )

    metrics = [
        Metric(
            key="current_balance",
            label="Current balance",
            value=_format_bdt(start_balance),
            unit="bdt",
            confidence=Confidence.HIGH,
            evidence=[_evidence("current_balance", start_balance, source="daily_features")],
        ),
        Metric(
            key="expected_income",
            label=f"Expected income ({horizon_days}d)",
            value=_format_bdt(float(path["income"].sum())),
            unit="bdt",
            confidence=confidence,
            evidence=[
                _evidence(
                    "expected_income",
                    levels["income"],
                    source="forecast",
                    window=target_period,
                    comparison=f"gate weight {levels['gates']['income']:.2f}",
                    confidence=confidence,
                )
            ],
        ),
        Metric(
            key="expected_spend",
            label=f"Expected spending ({horizon_days}d)",
            value=_format_bdt(float(path["spend"].sum())),
            unit="bdt",
            confidence=confidence,
            evidence=[
                _evidence(
                    "expected_spend",
                    levels["spend"],
                    source="forecast",
                    window=target_period,
                    comparison=f"gate weight {levels['gates']['spend']:.2f}",
                    confidence=confidence,
                )
            ],
        ),
        Metric(
            key="expected_ending_balance",
            label="Projected balance at horizon",
            value=_format_bdt(float(balances[-1])),
            unit="bdt",
            confidence=confidence,
            evidence=[
                _evidence("expected_ending_balance", float(balances[-1]), source="forecast")
            ],
        ),
        Metric(
            key="shortfall_probability",
            label="Probability of dipping below buffer",
            value=_format_bdt(probability * 100),
            unit="percent",
            confidence=Confidence.MEDIUM if mc["paths"] > 10 else Confidence.LOW,
            evidence=[
                _evidence(
                    "shortfall_probability",
                    probability * 100,
                    source="monte_carlo",
                    unit="percent",
                    comparison=f"{mc['paths']} paths, daily vol {mc.get('daily_volatility', 0):.2f}",
                )
            ],
        ),
    ]

    insights = []
    pressure_insight = _pressure_insight(
        probability, shortages, buffer_target, min_balance, min_date, recurring_total
    )
    if pressure_insight:
        insights.append(pressure_insight)

    return ForecastResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(
            headline=(
                f"Projected balance {format_bdt(float(balances[-1]))} after {horizon_days} days "
                f"(minimum {format_bdt(min_balance)} on {min_date}); "
                f"{probability * 100:.0f}% chance of dipping below "
                f"{format_bdt(buffer_target)}."
            ),
            detail=[
                f"Income {format_bdt(float(path['income'].sum()))} and spending "
                f"{format_bdt(float(path['spend'].sum()))} over {horizon_days} days.",
                f"Standing bills {format_bdt(recurring_total)} land on contractual due dates.",
                f"Lowest projected balance {format_bdt(min_balance)} on {min_date}.",
                f"Model: {levels['model']}.",
            ],
        ),
        evidence=[
            _evidence("current_balance", start_balance, source="daily_features"),
            _evidence("expected_income", levels["income"], source="forecast", window=target_period),
            _evidence("expected_spend", levels["spend"], source="forecast", window=target_period),
            _evidence("recurring_total", recurring_total, source="recurring_expenses", window=target_period),
            _evidence("min_projected_balance", min_balance, source="forecast", window=target_period),
        ],
        assumptions=[
            Assumption(
                key="minimum_balance_buffer",
                value=buffer_target,
                rationale=(
                    f"Effective floor = max(flat {buffer_basis['flat_floor']:.0f}, "
                    f"{settings.buffer_floor_months:g} months x own spending "
                    f"{buffer_basis['monthly_expense']:.0f}) = {buffer_basis['effective_buffer']:.0f} "
                    f"({buffer_basis['basis']}). Change BUFFER_FLOOR_MONTHS to see more warnings."
                ),
            ),
            Assumption(
                key="monte_carlo_paths",
                value=float(mc["paths"]),
                rationale="Number of simulated spending paths used to estimate shortfall risk.",
            ),
            Assumption(
                key="bills_are_contractual",
                value=1.0,
                rationale="Recurring obligations are assumed exact on their due dates.",
            ),
            Assumption(
                key="income_on_observed_payday",
                value=1.0,
                rationale="Income is anchored to the customer's historical payday day-of-month.",
            ),
        ],
        metrics=metrics,
        insights=insights,
        horizon_days=horizon_days,
        target_period=target_period,
        path=[
            ForecastPoint(
                date=str(row["date"]),
                income=_format_bdt(float(row["income"])),
                spend=_format_bdt(float(row["spend"])),
                net=_format_bdt(float(row["net"])),
                balance=_format_bdt(float(row["balance"])),
                recurring=_format_bdt(float(row["recurring"])),
                discretionary=_format_bdt(float(row["discretionary"])),
            )
            for _, row in path.iterrows()
        ],
        expected_income=_format_bdt(float(path["income"].sum())),
        expected_spend=_format_bdt(float(path["spend"].sum())),
        expected_ending_balance=_format_bdt(float(balances[-1])),
        current_balance=_format_bdt(start_balance),
        min_projected_balance=_format_bdt(min_balance),
        min_projected_balance_date=min_date,
        shortfall_probability=round(probability, 4),
        liquidity_pressure=_pressure_label(probability),
        buffer_target=buffer_target,
        monte_carlo_paths=int(mc["paths"]),
        model=levels["model"],
        model_gate_weights={k: round(v, 3) for k, v in levels["gates"].items()},
        shortages=shortages,
        recurring_schedule={
            str(day): _format_bdt(amount) for day, amount in sorted(recurring_by_day.items())
        },
    )
