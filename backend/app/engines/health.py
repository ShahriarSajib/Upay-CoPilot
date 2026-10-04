"""Financial health: one explainable number from six observable habits.

Why the total is a weighted composite rather than a model
--------------------------------------------------------
A health score is shown next to a person's name, so it has to be arguable. A
black-box model would not be: the customer would be asked to accept a number
whose inputs they cannot see and disagree with. Every component here is a small
number of measured ratios, each with its own :class:`Evidence`, and the only
judgement call -- how much each habit counts -- is declared as an
:class:`Assumption` and shown.

Three design choices that are not obvious from the output:

1. **Personas are never inputs.** The synthetic population carries a
   ``persona`` ground-truth column, and reading it would make the score a
   lookup table that scores perfectly and generalises to nothing. Personas are
   only ever used to *check* this engine offline. The same reasoning applies to
   ``goal_progress`` and friends: the only thing that moves a component is a
   measurement or an explicitly declared planning constant.
2. **A component that cannot be measured is held at the midpoint, not
   penalised.** A customer with no savings goal has not done anything wrong by
   not having one, so ``goal_progress`` sits at 50 with ``held_neutral`` set,
   the contribution is still visible in the total, and the component is kept out
   of the attention list. Zero is a claim; 50 with an explanation is not.
3. **The trend is recomputed, never re-based.** :func:`health_trend` re-derives
   the whole score from the history available *as of* each period, so a rising
   line means behaviour changed. Diffing a rolling window, or scoring each
   period with the full-history feature row, would both leak the future into a
   number the product shows as history.

Tone is a requirement, not a styling preference. Nothing here says a customer
wasted, overspent or failed; every ``detail`` names a pattern and its
consequence ("spending rises in the last third of the month, which is when the
balance gets tight"). A shaming score is not merely unpleasant, it is wrong
about the mechanism, and it teaches customers to distrust the number.

How the constants work
----------------------
Every ladder in this module is a monotone piecewise-linear map from a measured
ratio to a 0-100 sub-score, and every anchor in it is chosen rather than
observed. That is why each one also appears in :func:`_assumptions`, with the
point at which it scores full marks and a rationale for the rest of the ladder:
changing a customer's standing means changing a published constant, never the
code path that reads their history. Inside a component, a sub-score that cannot
be measured is dropped and the remainder re-normalised, so a missing input never
silently becomes a zero. An income month counts as "as expected" when it lands
within :data:`INCOME_MONTH_TOLERANCE` of the customer's own average, and a
window of fewer than :data:`MINIMUM_CONFIDENCE_MONTHS` months caps confidence
however clean the numbers look.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.context import UserContext, get_context
from app.schemas.common import (
    Assumption,
    Band,
    Confidence,
    Direction,
    Evidence,
    Explanation,
    Insight,
    Metric,
    Severity,
)
from app.schemas.wellbeing import (
    ComponentBand,
    ComponentResult,
    HealthAssessment,
    HealthComponent,
    HealthGrade,
    HealthMeasurements,
    HealthResponse,
    HealthTrendPoint,
)

SAVINGS_RATE_LADDER = ((-0.05, 0.0), (0.0, 12.0), (0.05, 32.0), (0.10, 50.0), (0.20, 76.0), (0.30, 100.0))
FUNDING_LADDER = ((0.0, 20.0), (0.25, 42.0), (0.5, 66.0), (0.75, 86.0), (1.0, 100.0))
EXPENSE_RATIO_LADDER = ((0.50, 100.0), (0.70, 88.0), (0.85, 70.0), (1.00, 48.0), (1.15, 24.0), (1.30, 0.0))
EXPENSE_RATIO_CV_LADDER = ((0.02, 100.0), (0.08, 88.0), (0.15, 74.0), (0.30, 52.0), (0.50, 30.0), (0.80, 8.0))
OVERSPEND_LADDER = ((0.0, 100.0), (0.12, 84.0), (0.25, 66.0), (0.45, 44.0), (0.70, 20.0), (1.0, 0.0))
INCOME_CV_LADDER = ((0.02, 100.0), (0.08, 92.0), (0.15, 80.0), (0.25, 62.0), (0.40, 42.0), (0.60, 20.0), (0.90, 0.0))
INCOME_CONSISTENCY_LADDER = ((0.0, 10.0), (0.40, 35.0), (0.60, 55.0), (0.80, 78.0), (1.0, 100.0))
BUFFER_MONTHS_LADDER = ((0.0, 0.0), (0.25, 16.0), (0.50, 32.0), (1.00, 52.0), (2.00, 72.0), (3.00, 86.0), (6.00, 100.0))
LOW_BALANCE_LADDER = ((0.0, 100.0), (0.05, 88.0), (0.15, 70.0), (0.30, 48.0), (0.50, 26.0), (0.75, 8.0))
GOAL_PROGRESS_LADDER = ((0.0, 12.0), (0.10, 32.0), (0.25, 56.0), (0.50, 80.0), (0.75, 94.0), (1.0, 100.0))
CASH_SHARE_LADDER = ((0.0, 100.0), (0.15, 86.0), (0.35, 64.0), (0.50, 46.0), (0.70, 22.0), (0.90, 0.0))

LATE_MONTH_SHARE_LADDER = ((0.05, 100.0), (0.20, 88.0), (0.35, 70.0), (0.50, 48.0), (0.65, 26.0))

LATE_MONTH_STRETCH_BUFFER_MONTHS = 2.0
SURPLUS_SIGN_LADDER = ((0.0, 0.0), (0.40, 22.0), (0.60, 45.0), (0.80, 72.0), (1.0, 100.0))
SURPLUS_VARIABILITY_LADDER = ((0.02, 100.0), (0.08, 88.0), (0.15, 74.0), (0.25, 56.0), (0.40, 34.0), (0.60, 12.0))
MIN_BALANCE_MONTHS_LADDER = ((0.0, 0.0), (0.1, 22.0), (0.25, 44.0), (0.5, 68.0), (1.0, 88.0), (2.0, 100.0))
CASH_OUT_STABILITY_LADDER = ((0.0, 100.0), (0.20, 86.0), (0.40, 70.0), (0.70, 46.0), (1.0, 20.0), (1.50, 0.0))
TOLERANCE_AFTER_SHOCK_LADDER = ((-2.0, 0.0), (-1.0, 8.0), (-0.5, 20.0), (0.0, 42.0), (0.5, 62.0), (1.0, 80.0), (3.0, 100.0))
SHORT_FREQUENCY_LADDER = ((0.0, 100.0), (0.10, 84.0), (0.25, 64.0), (0.50, 38.0), (1.0, 0.0))

HEALTH_COMPONENT_WEIGHTS: dict[HealthComponent, float] = {
    HealthComponent.SAVINGS_BEHAVIOUR: 0.20,
    HealthComponent.EXPENSE_CONTROL: 0.20,
    HealthComponent.INCOME_STABILITY: 0.15,
    HealthComponent.LIQUIDITY_BUFFER: 0.20,
    HealthComponent.GOAL_PROGRESS: 0.15,
    HealthComponent.CASH_DEPENDENCY: 0.10,
}

HEALTH_COMPONENT_LABELS: dict[HealthComponent, str] = {
    HealthComponent.SAVINGS_BEHAVIOUR: "Saving after spending",
    HealthComponent.EXPENSE_CONTROL: "Spending against income",
    HealthComponent.INCOME_STABILITY: "Consistency of income",
    HealthComponent.LIQUIDITY_BUFFER: "Money kept in reserve",
    HealthComponent.GOAL_PROGRESS: "Progress toward savings goals",
    HealthComponent.CASH_DEPENDENCY: "Spending paid in cash",
}

HEALTH_SUB_WEIGHTS: dict[HealthComponent, dict[str, float]] = {
    HealthComponent.SAVINGS_BEHAVIOUR: {"savings_rate": 0.65, "funding_consistency": 0.35},
    HealthComponent.EXPENSE_CONTROL: {
        "expense_ratio_level": 0.45,
        "expense_ratio_stability": 0.25,
        "overspend_frequency": 0.30,
    },
    HealthComponent.INCOME_STABILITY: {"income_cv": 0.65, "income_consistency": 0.35},
    HealthComponent.LIQUIDITY_BUFFER: {"buffer_months": 0.60, "low_balance_frequency": 0.40},
    HealthComponent.GOAL_PROGRESS: {"funding_consistency": 0.50, "progress_rate": 0.50},
    HealthComponent.CASH_DEPENDENCY: {"cash_share": 1.0},
}

BAND_CUTS: tuple[tuple[float, ComponentBand], ...] = (
    (70.0, ComponentBand.STRONG),
    (45.0, ComponentBand.MODERATE),
    (25.0, ComponentBand.WATCH),
    (0.0, ComponentBand.NEEDS_ATTENTION),
)

HEALTH_GRADE_CUTS: tuple[tuple[float, HealthGrade], ...] = (
    (75.0, HealthGrade.STRONG),
    (55.0, HealthGrade.STEADY),
    (35.0, HealthGrade.STRAINED),
    (0.0, HealthGrade.TIGHT),
)

NEUTRAL_COMPONENT_SCORE = 50.0

HIGH_CONFIDENCE_MONTHS = 5
MINIMUM_CONFIDENCE_MONTHS = 3
DISPERSED_INCOME_CV = 0.45
DISPERSED_SPEND_CV = 0.30

INCOME_CONSISTENCY_FLOOR = 0.60

SOURCE_USER_FEATURES = "user_features"
SOURCE_MONTHLY = "monthly_features"
SOURCE_RECURRING = "recurring_expenses"
SOURCE_WALLETS = "wallets"
SOURCE_ENGINE = "engines.health"


def ramp(value: float, ladder: tuple[tuple[float, float], ...]) -> float:
    """Piecewise-linear map of a measured ratio onto a 0-100 sub-score."""
    if not ladder:
        return 0.0
    if value <= ladder[0][0]:
        return float(ladder[0][1])
    if value >= ladder[-1][0]:
        return float(ladder[-1][1])
    for (low_x, low_y), (high_x, high_y) in zip(ladder, ladder[1:]):
        if low_x <= value <= high_x:
            if high_x == low_x:
                return float(high_y)
            share = (value - low_x) / (high_x - low_x)
            return float(low_y + (high_y - low_y) * share)
    return float(ladder[-1][1])


def money(value: float) -> float:
    """BDT rounded to 2dp, with negative zero normalised away."""
    return round(float(value) + 0.0, 2)


def ratio(value: float) -> float:
    return round(float(value) + 0.0, 4)


def months(value: float) -> float:
    return round(float(value) + 0.0, 2)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(min(max(float(value), low), high))


def pct(value: float, digits: int = 0) -> str:
    return f"{float(value) * 100:.{digits}f}%"


def bdt(value: float) -> str:
    return f"BDT {float(value):,.0f}"


def band_for(score: float) -> ComponentBand:
    for cut, band in BAND_CUTS:
        if score >= cut:
            return band
    return ComponentBand.NEEDS_ATTENTION


def _grade_for(score: float) -> HealthGrade:
    for cut, grade in HEALTH_GRADE_CUTS:
        if score >= cut:
            return grade
    return HealthGrade.TIGHT


def combine(sub_scores: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted mean over the sub-scores that exist, re-normalised."""
    usable = {key: value for key, value in sub_scores.items() if key in weights}
    total_weight = sum(weights[key] for key in usable)
    if total_weight <= 0:
        return 0.0
    return clamp(sum(usable[key] * weights[key] for key in usable) / total_weight)


def mean(values: Sequence[float]) -> float:
    """Mean of a sample, or 0.0 when there is nothing to average."""
    array = np.asarray(list(values), dtype=float)
    return float(np.mean(array)) if array.size else 0.0


def dispersion(values: Sequence[float]) -> float:
    """Population coefficient of variation, matching the feature definition."""
    array = np.asarray(list(values), dtype=float)
    if array.size < 2:
        return 0.0
    average = float(np.mean(array))
    if average <= 0:
        return 0.0
    return float(np.std(array, ddof=0) / average)


def confidence_for(
    months_observed: int,
    income_cv: float,
    spend_cv: float,
    thin_input: bool = False,
) -> Confidence:
    """Confidence from sample size and dispersion, never from how good the news is.

    A high score on two months of history is still low confidence, and that
    asymmetry is deliberate: the product would rather admit it is guessing than
    tell a customer their month is healthy on a single observation.
    """
    if months_observed < MINIMUM_CONFIDENCE_MONTHS or thin_input:
        return Confidence.LOW
    if months_observed < HIGH_CONFIDENCE_MONTHS:
        return Confidence.MEDIUM
    if max(income_cv, spend_cv) >= DISPERSED_SPEND_CV:
        return Confidence.MEDIUM
    return Confidence.HIGH


def dedupe(items: list[Evidence]) -> list[Evidence]:
    seen: set[str] = set()
    out: list[Evidence] = []
    for item in items:
        if item.label in seen:
            continue
        seen.add(item.label)
        out.append(item)
    return out


def _window_text(periods: list[str]) -> str:
    if not periods:
        return "no observed months"
    if len(periods) == 1:
        return f"{periods[0]} (1 month)"
    return f"{periods[0]} to {periods[-1]} ({len(periods)} months)"


def _slice_monthly(monthly: pd.DataFrame, upto_period: str | None) -> pd.DataFrame:
    if upto_period is None or monthly.empty:
        return monthly
    return monthly[monthly["period"] <= upto_period]


def measurements(context: UserContext, upto_period: str | None = None) -> HealthMeasurements:
    """Every quantity the components read, from one flat record.

    When ``upto_period`` is None the user-level feature row is preferred for the
    fields it already aggregates correctly (goal progress, whole-window cash
    share, day-level low-balance frequency) and the monthly history fills in
    the dispersion measures. When a period is given, nothing is read from the
    user-level row: it was built from the whole history and would leak the
    future into a past score.
    """
    monthly = _slice_monthly(context.monthly, upto_period)
    full_history = upto_period is None

    if monthly.empty:
        return HealthMeasurements(
            months_observed=0,
            window=_window_text([]),
            goal_count=int(context.feature("goal_count", 0.0) or 0.0),
        )

    income = monthly["income"].to_numpy(dtype=float)
    spend = monthly["spend"].to_numpy(dtype=float)
    surplus = monthly["surplus"].to_numpy(dtype=float)
    ratios = monthly["expense_income_ratio"].to_numpy(dtype=float)
    mean_income = mean(income)
    observed_days = float(monthly["observed_days"].sum()) or float(len(monthly) * 30)

    positive_contributions = float((monthly["goal_contribution"] > 0).sum())
    funding_consistency = positive_contributions / float(len(monthly))
    recurring_amount_mean = mean(monthly["recurring_amount"].to_numpy(dtype=float))

    essentials = recurring_amount_mean or mean(
        context.recurring["amount"].to_numpy(dtype=float)
        if not context.recurring.empty
        else np.zeros(0)
    )
    ending_balance = float(monthly["ending_balance"].iloc[-1])
    lowest_balance = float(monthly["min_balance"].min())
    months_short = float(
        (monthly["ending_balance"] - essentials < settings.minimum_balance_buffer).sum()
    )

    goal_count = int(context.feature("goal_count", 0.0) or 0.0) if full_history else int(
        context.goals["goal_id"].nunique() if not context.goals.empty else 0
    )
    contributed = float(monthly["goal_contribution"].sum())
    target_total = float(context.feature("goal_target_total", 0.0) or 0.0) if full_history else float(
        context.goals["target_amount"].sum() if not context.goals.empty else 0.0
    )
    goal_progress = min(contributed / target_total, 1.0) if target_total > 0 else 0.0
    if full_history:
        goal_progress = float(context.feature("goal_progress", goal_progress) or goal_progress)

    measure = HealthMeasurements(
        months_observed=int(len(monthly)),
        window=_window_text(monthly["period"].astype(str).tolist()),
        savings_rate=mean(monthly["savings_rate"].to_numpy(dtype=float)),
        funding_consistency=funding_consistency,
        goal_count=goal_count,
        goal_progress=goal_progress,
        expense_income_ratio=mean(ratios),
        expense_ratio_cv=dispersion(ratios),
        negative_surplus_share=float((surplus < 0).sum()) / float(len(monthly)),
        late_month_share=mean(monthly["late_share"].to_numpy(dtype=float)),
        income_cv=dispersion(income),
        income_consistency=float(
            np.mean(income >= INCOME_CONSISTENCY_FLOOR * mean_income) if mean_income > 0 else 0.0
        ),
        emergency_buffer_months=(max(ending_balance, 0.0) / mean(spend)) if mean(spend) > 0 else 0.0,
        low_balance_frequency=float(monthly["days_below_buffer"].sum()) / observed_days,
        days_below_buffer=float(monthly["days_below_buffer"].sum()),
        cash_dependency=float(monthly["cash_spend"].sum()) / float(monthly["spend"].sum())
        if float(monthly["spend"].sum()) > 0
        else 0.0,
        monthly_income=mean_income,
        monthly_expense=mean(spend),
        monthly_surplus=mean(surplus),
        ending_balance=ending_balance,
        lowest_balance=lowest_balance,
        recurring_amount_mean=essentials,
        mandatory_obligation_amount=float(
            context.feature("mandatory_obligation_amount", 0.0) or 0.0
        ),
        spend_cv=dispersion(spend),
        surplus_dispersion=float(np.std(surplus, ddof=0)) if surplus.size else 0.0,
        surprise_events=float(monthly["anomaly_events"].sum()),
        months_short_after_shock=months_short / float(len(monthly)),
        has_cash_wallet=bool(context.feature("has_cash_wallet", 0.0) or 0.0) > 0,
    )

    if not full_history:
        return measure

    measure.savings_rate = float(context.feature("savings_rate", measure.savings_rate))
    measure.expense_income_ratio = float(context.feature("expense_income_ratio", measure.expense_income_ratio))
    measure.funding_consistency = float(context.feature("funding_consistency", measure.funding_consistency))
    measure.income_cv = float(context.feature("income_cv", measure.income_cv))
    measure.late_month_share = float(context.feature("late_month_share", measure.late_month_share))
    measure.cash_dependency = float(context.feature("cash_dependency", measure.cash_dependency))
    measure.emergency_buffer_months = float(
        context.feature("emergency_buffer_months", measure.emergency_buffer_months)
    )
    measure.low_balance_frequency = float(
        context.feature("low_balance_frequency", measure.low_balance_frequency)
    )
    measure.monthly_income = float(context.feature("monthly_income", measure.monthly_income))
    measure.monthly_expense = float(context.feature("monthly_expense", measure.monthly_expense))
    measure.monthly_surplus = float(context.feature("monthly_surplus", measure.monthly_surplus))
    measure.ending_balance = float(context.feature("ending_balance", measure.ending_balance))
    measure.recurring_amount_mean = float(
        context.feature("monthly_recurring_amount", measure.recurring_amount_mean)
        or measure.recurring_amount_mean
    )
    measure.surprise_events = float(context.feature("anomaly_events", measure.surprise_events) or 0.0)
    return measure


def _savings_component(measure: HealthMeasurements, confidence: Confidence) -> ComponentResult:
    evidence = [
        Evidence(
            label="savings_rate",
            value=ratio(measure.savings_rate),
            unit="ratio",
            source=f"{SOURCE_USER_FEATURES}.savings_rate",
            window=measure.window,
            comparison="share of monthly income left after spending",
            confidence=confidence,
        ),
        Evidence(
            label="funding_consistency",
            value=ratio(measure.funding_consistency),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.goal_contribution",
            window=measure.window,
            comparison="months with a goal contribution out of months observed",
            confidence=confidence,
        ),
    ]
    sub_scores = {"savings_rate": ramp(measure.savings_rate, SAVINGS_RATE_LADDER)}
    if measure.goal_count > 0:
        sub_scores["funding_consistency"] = ramp(measure.funding_consistency, FUNDING_LADDER)
        goal_clause = f" and a goal was funded in {pct(measure.funding_consistency)} of months"
    else:
        goal_clause = ", with no savings goal set so goal funding is left out of this part"
    score = combine(sub_scores, HEALTH_SUB_WEIGHTS[HealthComponent.SAVINGS_BEHAVIOUR])
    savings_clause = (
        f"About {pct(measure.savings_rate)} of a month's income is left after spending"
        if measure.savings_rate >= 0
        else f"About {pct(abs(measure.savings_rate))} more leaves than stays after spending each month"
    )
    detail = f"{savings_clause}{goal_clause}."
    evidence.append(
        Evidence(
            label="monthly_surplus",
            value=money(measure.monthly_surplus),
            source=f"{SOURCE_MONTHLY}.surplus",
            window=measure.window,
            comparison="amount left after spending in a typical month",
            confidence=confidence,
        )
    )
    return ComponentResult(
        key=HealthComponent.SAVINGS_BEHAVIOUR.value,
        label=HEALTH_COMPONENT_LABELS[HealthComponent.SAVINGS_BEHAVIOUR],
        score=money(score),
        band=band_for(score).value,
        weight=HEALTH_COMPONENT_WEIGHTS[HealthComponent.SAVINGS_BEHAVIOUR],
        contribution=money(score * HEALTH_COMPONENT_WEIGHTS[HealthComponent.SAVINGS_BEHAVIOUR]),
        detail=detail,
        evidence=evidence,
        held_neutral=False,
        sub_scores={key: money(value) for key, value in sub_scores.items()},
    )


def _expense_component(measure: HealthMeasurements, confidence: Confidence) -> ComponentResult:
    sub_scores = {
        "expense_ratio_level": ramp(measure.expense_income_ratio, EXPENSE_RATIO_LADDER),
        "expense_ratio_stability": ramp(measure.expense_ratio_cv, EXPENSE_RATIO_CV_LADDER),
        "overspend_frequency": ramp(measure.negative_surplus_share, OVERSPEND_LADDER),
    }
    score = combine(sub_scores, HEALTH_SUB_WEIGHTS[HealthComponent.EXPENSE_CONTROL])
    months_observed = max(measure.months_observed, 1)
    overspend_months = int(round(measure.negative_surplus_share * months_observed))
    evidence = [
        Evidence(
            label="expense_income_ratio",
            value=ratio(measure.expense_income_ratio),
            unit="ratio",
            source=f"{SOURCE_USER_FEATURES}.expense_income_ratio",
            window=measure.window,
            comparison="spending as a share of income; 1.0 means spending matches income",
            confidence=confidence,
        ),
        Evidence(
            label="expense_ratio_variation",
            value=ratio(measure.expense_ratio_cv),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.expense_income_ratio",
            window=measure.window,
            comparison="month-to-month variation in that share",
            confidence=confidence,
        ),
        Evidence(
            label="overspend_months",
            value=float(overspend_months),
            unit="months",
            source=f"{SOURCE_MONTHLY}.surplus",
            window=measure.window,
            comparison=f"months out of {measure.months_observed} where spending exceeded income",
            confidence=confidence,
        ),
    ]
    detail = (
        f"Spending takes about {pct(measure.expense_income_ratio)} of income and ran above "
        f"income in {overspend_months} of {measure.months_observed} months."
    )
    return ComponentResult(
        key=HealthComponent.EXPENSE_CONTROL.value,
        label=HEALTH_COMPONENT_LABELS[HealthComponent.EXPENSE_CONTROL],
        score=money(score),
        band=band_for(score).value,
        weight=HEALTH_COMPONENT_WEIGHTS[HealthComponent.EXPENSE_CONTROL],
        contribution=money(score * HEALTH_COMPONENT_WEIGHTS[HealthComponent.EXPENSE_CONTROL]),
        detail=detail,
        evidence=evidence,
        held_neutral=False,
        sub_scores={key: money(value) for key, value in sub_scores.items()},
    )


def _income_component(measure: HealthMeasurements, confidence: Confidence) -> ComponentResult:
    sub_scores = {
        "income_cv": ramp(measure.income_cv, INCOME_CV_LADDER),
        "income_consistency": ramp(measure.income_consistency, INCOME_CONSISTENCY_LADDER),
    }
    score = combine(sub_scores, HEALTH_SUB_WEIGHTS[HealthComponent.INCOME_STABILITY])
    evidence = [
        Evidence(
            label="income_cv",
            value=ratio(measure.income_cv),
            unit="ratio",
            source=f"{SOURCE_USER_FEATURES}.income_cv",
            window=measure.window,
            comparison="variation in monthly income around its own average",
            confidence=confidence,
        ),
        Evidence(
            label="income_consistency",
            value=ratio(measure.income_consistency),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.income",
            window=measure.window,
            comparison=f"months landing within {int(INCOME_CONSISTENCY_FLOOR * 100)}% of average income",
            confidence=confidence,
        ),
        Evidence(
            label="monthly_income",
            value=money(measure.monthly_income),
            source=f"{SOURCE_MONTHLY}.income",
            window=measure.window,
            comparison="average monthly income in the window",
            confidence=confidence,
        ),
    ]
    detail = (
        f"Monthly income averages {bdt(measure.monthly_income)} and moves about "
        f"{pct(measure.income_cv)} around its average."
    )
    return ComponentResult(
        key=HealthComponent.INCOME_STABILITY.value,
        label=HEALTH_COMPONENT_LABELS[HealthComponent.INCOME_STABILITY],
        score=money(score),
        band=band_for(score).value,
        weight=HEALTH_COMPONENT_WEIGHTS[HealthComponent.INCOME_STABILITY],
        contribution=money(score * HEALTH_COMPONENT_WEIGHTS[HealthComponent.INCOME_STABILITY]),
        detail=detail,
        evidence=evidence,
        held_neutral=False,
        sub_scores={key: money(value) for key, value in sub_scores.items()},
    )


def _liquidity_component(measure: HealthMeasurements, confidence: Confidence) -> ComponentResult:
    sub_scores = {
        "buffer_months": ramp(measure.emergency_buffer_months, BUFFER_MONTHS_LADDER),
        "low_balance_frequency": ramp(measure.low_balance_frequency, LOW_BALANCE_LADDER),
    }
    score = combine(sub_scores, HEALTH_SUB_WEIGHTS[HealthComponent.LIQUIDITY_BUFFER])
    evidence = [
        Evidence(
            label="emergency_buffer_months",
            value=months(measure.emergency_buffer_months),
            unit="months",
            source=f"{SOURCE_USER_FEATURES}.emergency_buffer_months",
            window=measure.window,
            comparison=f"months of average spending covered by the {bdt(measure.ending_balance)} balance",
            confidence=confidence,
        ),
        Evidence(
            label="days_below_buffer",
            value=float(int(measure.days_below_buffer)),
            unit="days",
            source=f"{SOURCE_MONTHLY}.days_below_buffer",
            window=measure.window,
            comparison=(
                f"days the balance sat under the {bdt(settings.minimum_balance_buffer)} "
                "minimum-balance line"
            ),
            confidence=confidence,
        ),
        Evidence(
            label="low_balance_frequency",
            value=ratio(measure.low_balance_frequency),
            unit="ratio",
            source=f"{SOURCE_USER_FEATURES}.low_balance_frequency",
            window=measure.window,
            comparison="share of days spent below that line",
            confidence=confidence,
        ),
    ]
    detail = (
        f"The balance covers about {months(measure.emergency_buffer_months)} months of average "
        f"spending and sat below the minimum-balance line on "
        f"{int(measure.days_below_buffer)} days."
    )
    return ComponentResult(
        key=HealthComponent.LIQUIDITY_BUFFER.value,
        label=HEALTH_COMPONENT_LABELS[HealthComponent.LIQUIDITY_BUFFER],
        score=money(score),
        band=band_for(score).value,
        weight=HEALTH_COMPONENT_WEIGHTS[HealthComponent.LIQUIDITY_BUFFER],
        contribution=money(score * HEALTH_COMPONENT_WEIGHTS[HealthComponent.LIQUIDITY_BUFFER]),
        detail=detail,
        evidence=evidence,
        held_neutral=False,
        sub_scores={key: money(value) for key, value in sub_scores.items()},
    )


def _goal_component(measure: HealthMeasurements, confidence: Confidence) -> ComponentResult:
    weight = HEALTH_COMPONENT_WEIGHTS[HealthComponent.GOAL_PROGRESS]
    evidence = [
        Evidence(
            label="goal_count",
            value=float(measure.goal_count),
            unit="goals",
            source="financial_goals",
            window=measure.window,
            comparison="savings goals currently open",
            confidence=confidence,
        ),
        Evidence(
            label="funding_consistency",
            value=ratio(measure.funding_consistency),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.goal_contribution",
            window=measure.window,
            comparison="months with a contribution out of months observed",
            confidence=confidence,
        ),
        Evidence(
            label="goal_progress",
            value=ratio(measure.goal_progress),
            unit="ratio",
            source=f"{SOURCE_USER_FEATURES}.goal_progress",
            window=measure.window,
            comparison="share of the target amount reached so far",
            confidence=confidence,
        ),
    ]
    if measure.goal_count <= 0:
        return ComponentResult(
            key=HealthComponent.GOAL_PROGRESS.value,
            label=HEALTH_COMPONENT_LABELS[HealthComponent.GOAL_PROGRESS],
            score=NEUTRAL_COMPONENT_SCORE,
            band=band_for(NEUTRAL_COMPONENT_SCORE).value,
            weight=weight,
            contribution=money(NEUTRAL_COMPONENT_SCORE * weight),
            detail=(
                "No savings goal is set, so this part of the score is held at the midpoint "
                "rather than read as a gap."
            ),
            evidence=evidence,
            held_neutral=True,
            sub_scores={},
        )
    sub_scores = {
        "funding_consistency": ramp(measure.funding_consistency, FUNDING_LADDER),
        "progress_rate": ramp(measure.goal_progress, GOAL_PROGRESS_LADDER),
    }
    score = combine(sub_scores, HEALTH_SUB_WEIGHTS[HealthComponent.GOAL_PROGRESS])
    months_funded = int(round(measure.funding_consistency * measure.months_observed))
    detail = (
        f"A goal was funded in {months_funded} of {measure.months_observed} months and is "
        f"{pct(measure.goal_progress)} of the way to its target."
    )
    return ComponentResult(
        key=HealthComponent.GOAL_PROGRESS.value,
        label=HEALTH_COMPONENT_LABELS[HealthComponent.GOAL_PROGRESS],
        score=money(score),
        band=band_for(score).value,
        weight=weight,
        contribution=money(score * weight),
        detail=detail,
        evidence=evidence,
        held_neutral=False,
        sub_scores={key: money(value) for key, value in sub_scores.items()},
    )


def _cash_component(measure: HealthMeasurements, confidence: Confidence) -> ComponentResult:
    score = ramp(measure.cash_dependency, CASH_SHARE_LADDER)
    evidence = [
        Evidence(
            label="cash_dependency",
            value=ratio(measure.cash_dependency),
            unit="ratio",
            source=f"{SOURCE_USER_FEATURES}.cash_dependency",
            window=measure.window,
            comparison="share of all spending paid out of cash wallets",
            confidence=confidence,
        ),
        Evidence(
            label="has_cash_wallet",
            value=1.0 if measure.has_cash_wallet else 0.0,
            unit="flag",
            source=f"{SOURCE_WALLETS}.wallet_type",
            window=measure.window,
            comparison="whether a cash wallet is on the account",
            confidence=confidence,
        ),
    ]
    detail = (
        f"About {pct(measure.cash_dependency)} of spending is paid in cash, which does not "
        "appear in the transaction history."
    )
    return ComponentResult(
        key=HealthComponent.CASH_DEPENDENCY.value,
        label=HEALTH_COMPONENT_LABELS[HealthComponent.CASH_DEPENDENCY],
        score=money(score),
        band=band_for(score).value,
        weight=HEALTH_COMPONENT_WEIGHTS[HealthComponent.CASH_DEPENDENCY],
        contribution=money(score * HEALTH_COMPONENT_WEIGHTS[HealthComponent.CASH_DEPENDENCY]),
        detail=detail,
        evidence=evidence,
        held_neutral=False,
        sub_scores={"cash_share": money(score)},
    )


_COMPONENT_BUILDERS = {
    HealthComponent.SAVINGS_BEHAVIOUR: _savings_component,
    HealthComponent.EXPENSE_CONTROL: _expense_component,
    HealthComponent.INCOME_STABILITY: _income_component,
    HealthComponent.LIQUIDITY_BUFFER: _liquidity_component,
    HealthComponent.GOAL_PROGRESS: _goal_component,
    HealthComponent.CASH_DEPENDENCY: _cash_component,
}


def _band_confidence(measure: HealthMeasurements, component: HealthComponent) -> Confidence:
    thin = component is HealthComponent.GOAL_PROGRESS and measure.months_observed < 4
    return confidence_for(
        measure.months_observed,
        measure.income_cv,
        measure.spend_cv,
        thin_input=thin,
    )


def _components(measure: HealthMeasurements) -> list[ComponentResult]:
    """Score all six components in the published weight order."""
    out: list[ComponentResult] = []
    for component, builder in _COMPONENT_BUILDERS.items():
        out.append(builder(measure, _band_confidence(measure, component)))
    return out


def _assumptions() -> list[Assumption]:
    out: list[Assumption] = [
        Assumption(
            key="weight.savings_behaviour",
            value=HEALTH_COMPONENT_WEIGHTS[HealthComponent.SAVINGS_BEHAVIOUR],
            rationale=(
                "Keeping money back after spending is the largest single lever a customer "
                "controls, so it carries the joint-highest weight."
            ),
        ),
        Assumption(
            key="weight.expense_control",
            value=HEALTH_COMPONENT_WEIGHTS[HealthComponent.EXPENSE_CONTROL],
            rationale=(
                "Whether spending stays inside income is the other half of a month that ends "
                "with money left."
            ),
        ),
        Assumption(
            key="weight.income_stability",
            value=HEALTH_COMPONENT_WEIGHTS[HealthComponent.INCOME_STABILITY],
            rationale=(
                "Income steadiness is important but partly outside the customer's control, so "
                "it is weighted below the two habits they set."
            ),
        ),
        Assumption(
            key="weight.liquidity_buffer",
            value=HEALTH_COMPONENT_WEIGHTS[HealthComponent.LIQUIDITY_BUFFER],
            rationale=(
                "Money already set aside is what absorbs an unexpected cost, which is why it "
                "carries the joint-highest weight."
            ),
        ),
        Assumption(
            key="weight.goal_progress",
            value=HEALTH_COMPONENT_WEIGHTS[HealthComponent.GOAL_PROGRESS],
            rationale=(
                "Progress toward a goal is a leading indicator of saving, but it is only "
                "measurable for customers who have set one."
            ),
        ),
        Assumption(
            key="weight.cash_dependency",
            value=HEALTH_COMPONENT_WEIGHTS[HealthComponent.CASH_DEPENDENCY],
            rationale=(
                "Cash spending changes visibility of the month more than it changes the month, "
                "so it carries the smallest weight."
            ),
        ),
        Assumption(
            key="late_month_stretch_buffer_months",
            value=LATE_MONTH_STRETCH_BUFFER_MONTHS * settings.emergency_fund_months,
            rationale=(
                "Late-month spending is described as a strain on the balance only while cover "
                f"is at or below {LATE_MONTH_STRETCH_BUFFER_MONTHS:.0f}x the "
                f"{settings.emergency_fund_months:.0f}-month cushion this plan works from; beyond "
                "that it is reported as a habit, not a problem."
            ),
        ),
        Assumption(
            key="savings_rate_full_marks",
            value=SAVINGS_RATE_LADDER[-1][0],
            rationale=(
                "Keeping 30% of monthly income after spending scores full marks. The ladder runs "
                "12 at break-even, 32 at 5%, 50 at 10%, 76 at 20%."
            ),
        ),
        Assumption(
            key="goal_funding_target",
            value=FUNDING_LADDER[-2][0],
            rationale=(
                "Funding a goal in 75% of months scores 86 and every month scores 100, on the "
                "basis that an unfunded month is where goals quietly stall."
            ),
        ),
        Assumption(
            key="expense_ratio_ceiling",
            value=EXPENSE_RATIO_LADDER[-1][0],
            rationale=(
                f"Spending above {int(EXPENSE_RATIO_LADDER[-1][0] * 100)}% of income scores zero. "
                "0.85 scores 70 and 1.00 scores 48, because a ratio of 1.0 means a typical "
                "month ends with nothing spare."
            ),
        ),
        Assumption(
            key="expense_ratio_stability_tolerance",
            value=EXPENSE_RATIO_CV_LADDER[1][0],
            rationale=(
                "Month-to-month variation of 8% in the spending ratio still scores 88; beyond "
                "30% the month stops being predictable and scores 52."
            ),
        ),
        Assumption(
            key="overspend_share_ceiling",
            value=OVERSPEND_LADDER[3][0],
            rationale=(
                "Spending above income in 45% of months scores 44. One such month is normal "
                "life; half of them is a pattern."
            ),
        ),
        Assumption(
            key="income_cv_steady_max",
            value=INCOME_CV_LADDER[2][0],
            rationale=(
                "Income variation of 15% a month scores 80, 25% scores 62, and 60% or more "
                "scores 20 because a monthly plan built on the average would be wrong most "
                "months."
            ),
        ),
        Assumption(
            key="income_consistency_floor",
            value=INCOME_CONSISTENCY_FLOOR,
            rationale=(
                "A month counts as income arriving as expected when it lands within 40% of the "
                "customer's own average; that share of months is scored from 10 to 100."
            ),
        ),
        Assumption(
            key="emergency_fund_months",
            value=float(settings.emergency_fund_months),
            rationale=(
                "Three months of spending is the reserve this product plans around, so it "
                "scores 86 rather than 100. Full marks need six months."
            ),
        ),
        Assumption(
            key="minimum_balance_buffer",
            value=float(settings.minimum_balance_buffer),
            rationale=(
                "The minimum-balance line defines \"low balance\" for this score. It is a "
                "product setting, not something observed in the history."
            ),
        ),
        Assumption(
            key="goal_progress_target",
            value=GOAL_PROGRESS_LADDER[3][0],
            rationale=(
                "Halfway to a goal target scores 80; a quarter scores 56. The ladder measures "
                "distance covered, not effort, so an old goal is not penalised for age."
            ),
        ),
        Assumption(
            key="cash_share_comfortable_max",
            value=CASH_SHARE_LADDER[2][0],
            rationale=(
                "Cash at 35% of spending scores 64 and 70% scores 22. This measures how much "
                "of the month is invisible in the history, not how the money is spent."
            ),
        ),
        Assumption(
            key="confidence_minimum_months",
            value=float(MINIMUM_CONFIDENCE_MONTHS),
            rationale=(
                "Fewer than three observed months is reported as low confidence: one month is "
                "a single event, not a habit."
            ),
        ),
        Assumption(
            key="confidence_dispersion_ceiling",
            value=DISPERSED_SPEND_CV,
            rationale=(
                "When spending or income moves by more than 30% a month, component scores are "
                "capped at medium confidence even with a full history."
            ),
        ),
    ]
    return out


def _ranked(components: list[ComponentResult]) -> tuple[list[ComponentResult], list[ComponentResult]]:
    measurable = [item for item in components if not item.held_neutral]
    ordered = sorted(measurable, key=lambda item: (-item.score, item.key))
    return ordered[:2], list(reversed(ordered[-2:]))


def _assess(measure: HealthMeasurements) -> tuple[float, list[ComponentResult], Confidence]:
    components = _components(measure)
    total = sum(item.contribution for item in components)
    total = clamp(money(total))
    confidence = min(
        (item.evidence[0].confidence for item in components if item.evidence),
        key=lambda level: ["low", "medium", "high"].index(level.value),
    )
    return total, components, confidence


def health_assessment(user_id: str, upto_period: str | None = None) -> HealthAssessment:
    """The scored health result for one customer, optionally as of a past period."""
    context = get_context(user_id)
    measure = measurements(context, upto_period=upto_period)
    total, components, confidence = _assess(measure)
    strengths, attention = _ranked(components)
    return HealthAssessment(
        user_id=context.user_id,
        as_of=context.as_of.date().isoformat(),
        total_score=total,
        label=_grade_for(total).value,
        components=components,
        strengths=[item.label for item in strengths],
        attention_areas=[item.label for item in attention],
        confidence=confidence,
        months_observed=measure.months_observed,
        window=measure.window,
    )


def health_bands(user_id: str) -> list[Band]:
    """The six scored components, for an explainable score display."""
    return list(health_assessment(user_id).components)


def health_trend(user_id: str) -> list[dict]:
    """Health score as of each observed period, recomputed on past-only history.

    Each point is a full re-score from the monthly rows up to and including that
    period, so a rising line means the behaviour changed rather than that a
    rolling window moved. The first point rests on a single month and is
    reported as low confidence rather than smoothed away.
    """
    context = get_context(user_id)
    points: list[dict] = []
    if context.monthly.empty:
        return points
    for period in context.monthly["period"].astype(str).tolist():
        assessment = health_assessment(user_id, upto_period=period)
        points.append(
            HealthTrendPoint(
                period=period,
                health_score=assessment.total_score,
                label=assessment.label,
                confidence=assessment.confidence,
                months_observed=assessment.months_observed,
                strengths=assessment.strengths,
                attention_areas=assessment.attention_areas,
                note=(
                    f"Only {assessment.months_observed} month"
                    f"{'' if assessment.months_observed == 1 else 's'} of history, so this "
                    "point is indicative rather than settled."
                    if assessment.months_observed < MINIMUM_CONFIDENCE_MONTHS
                    else None
                ),
            ).model_dump(mode="json")
        )
    return points


def _explanation(measure: HealthMeasurements, grade: HealthGrade, total: float) -> Explanation:
    headline_phrase = {
        HealthGrade.STRONG: "money is in a good position this month, with room for the unexpected",
        HealthGrade.STEADY: "the month is running fairly smoothly, with some room to build",
        HealthGrade.STRAINED: "most months land close to income, so one surprise would show quickly",
        HealthGrade.TIGHT: "spending has been running close to or above income, which leaves little room",
    }[grade]
    headline = f"{grade.value.capitalize()}: {headline_phrase} ({total:.0f} of 100)."

    surplus_phrase = (
        f"leaving about {bdt(measure.monthly_surplus)} a month"
        if measure.monthly_surplus >= 0
        else f"coming to about {bdt(abs(measure.monthly_surplus))} less than it spends"
    )
    detail = [
        f"Income has averaged {bdt(measure.monthly_income)} a month and spending "
        f"{bdt(measure.monthly_expense)}, {surplus_phrase}."
    ]
    if measure.savings_rate >= 0:
        detail.append(
            f"That is roughly {pct(measure.savings_rate)} of income kept back in a typical month."
        )
    else:
        detail.append(
            f"That is about {bdt(abs(measure.monthly_surplus))} more spent than earned in a "
            "typical month."
        )
    detail.append(
        f"The balance of {bdt(measure.ending_balance)} covers about "
        f"{months(measure.emergency_buffer_months)} months of average spending"
        + (
            f", under the {settings.emergency_fund_months:.0f}-month cushion this plan works "
            "from, so one large bill would pull it down quickly"
            if measure.emergency_buffer_months < settings.emergency_fund_months
            else ""
        )
        + "."
    )

    months_observed = max(measure.months_observed, 1)
    overspend_months = int(round(measure.negative_surplus_share * months_observed))
    optional = []
    if measure.negative_surplus_share >= 0.25:
        optional.append(
            f"Spending ran above income in {overspend_months} of {measure.months_observed} months, "
            "often in months where a large one-off cost landed."
        )
    if measure.late_month_share >= 0.30:
        late_clause = (
            "onwards, which is when the balance is most stretched."
            if measure.emergency_buffer_months
            <= LATE_MONTH_STRETCH_BUFFER_MONTHS * settings.emergency_fund_months
            else "onwards, though the reserve in hand covers that stretch comfortably."
        )
        optional.append(
            f"{pct(measure.late_month_share)} of spending lands from the 23rd of the month "
            f"{late_clause}"
        )
    if measure.income_cv >= 0.30:
        optional.append(
            f"Income has moved about {pct(measure.income_cv)} around its average, so planning to a "
            "range works better than planning to one number."
        )
    if measure.cash_dependency >= 0.20:
        optional.append(
            f"About {pct(measure.cash_dependency)} of spending is paid in cash. Cash payments do "
            "not appear in transaction history, so these figures describe the part of the month "
            "that is visible here."
        )
    if measure.goal_count <= 0:
        optional.append(
            "No savings goal is set, so goal progress is held at the midpoint rather than read as "
            "a gap."
        )
    elif measure.funding_consistency >= 0.5:
        funded = int(round(measure.funding_consistency * months_observed))
        optional.append(
            f"A goal was funded in {funded} of {measure.months_observed} months, which is what "
            "keeps the target moving."
        )
    else:
        funded = int(round(measure.funding_consistency * months_observed))
        optional.append(
            f"A goal was funded in {funded} of {measure.months_observed} months. A smaller "
            "automatic amount after payday would keep it moving in lean months too."
        )
    return Explanation(headline=headline, detail=(detail + optional)[:4])


def _insight(assessment: HealthAssessment, measure: HealthMeasurements) -> Insight | None:
    """One prioritised observation for the weakest measurable component."""
    candidates = [
        item
        for item in assessment.components
        if not item.held_neutral and item.evidence and item.score < 70.0
    ]
    if not candidates:
        return None
    weakest = min(candidates, key=lambda item: item.score)
    actions = {
        HealthComponent.SAVINGS_BEHAVIOUR.value: (
            "Move a fixed amount to a goal on payday, small enough to keep even in a lean month."
        ),
        HealthComponent.EXPENSE_CONTROL.value: (
            "Set a soft ceiling for the days just before payday, when spending tends to cluster."
        ),
        HealthComponent.INCOME_STABILITY.value: (
            "Plan to a conservative monthly income and treat anything above it as headroom."
        ),
        HealthComponent.LIQUIDITY_BUFFER.value: (
            f"Build toward {settings.emergency_fund_months:.0f} months of spending by adding a small "
            "automatic transfer after each payday."
        ),
        HealthComponent.GOAL_PROGRESS.value: (
            "Set one goal with a monthly amount that survives a low-income month."
        ),
        HealthComponent.CASH_DEPENDENCY.value: (
            "Keep a small digital float for everyday payments so more of the month is visible in "
            "the history."
        ),
    }
    component = next(
        (item for item in assessment.components if item.key == weakest.key),
        weakest,
    )
    severity = Severity.WARNING if component.score < 25.0 else Severity.ATTENTION
    component_assumptions = [
        item
        for item in _assumptions()
        if item.key.endswith(component.key.split("_", 1)[-1])
        or item.key.startswith(f"weight.{component.key}")
    ]
    return Insight(
        key=f"health.{component.key}",
        title=f"{component.label}: the part with the most room",
        observation=component.detail,
        why=(
            f"It contributes {component.contribution:.1f} of the {assessment.total_score:.0f} "
            f"total at a weight of {component.weight:.2f}, and the pattern behind it repeats."
        ),
        action=actions[component.key],
        severity=severity,
        impact_bdt=None,
        evidence=component.evidence,
        assumptions=component_assumptions,
    )


def _narrative_evidence(
    context: UserContext, measure: HealthMeasurements, confidence: Confidence
) -> list[Evidence]:
    """The measurements the narrative quotes that no component scores.

    The three figures a reader checks first -- what a month costs, what is in
    the account, and how late spending lands -- are read by the explanation but
    drive no sub-score, so without these entries the sentences would quote
    numbers the response cannot account for.
    """
    window = measure.window
    return [
        Evidence(
            label="monthly_expense",
            value=money(measure.monthly_expense),
            source=f"{SOURCE_MONTHLY}.expense",
            window=window,
            comparison="average monthly spending across the window",
            confidence=confidence,
        ),
        Evidence(
            label="ending_balance",
            value=money(measure.ending_balance),
            source=f"{SOURCE_MONTHLY}.ending_balance",
            window=window,
            comparison="balance at the end of the latest month in the window",
            confidence=confidence,
        ),
        Evidence(
            label="late_month_share",
            value=ratio(measure.late_month_share),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.late_share",
            window=window,
            comparison="share of spending from the 23rd of the month onwards",
            confidence=confidence,
        ),
    ]


def financial_health(user_id: str) -> HealthResponse:
    """Financial health for one customer: total, breakdown, evidence, narrative."""
    context = get_context(user_id)
    measure = measurements(context)
    assessment = health_assessment(user_id)
    grade = _grade_for(assessment.total_score)
    explanation = _explanation(measure, grade, assessment.total_score)

    trend = health_trend(user_id)
    previous = trend[-2] if len(trend) >= 2 else None
    change_percent = None
    direction = Direction.FLAT
    previous_evidence: list[Evidence] = []
    if previous is not None:
        previous_value = float(previous["health_score"])
        change_percent = (
            ratio((assessment.total_score - previous_value) / previous_value * 100.0)
            if previous_value > 0
            else None
        )
        if abs(assessment.total_score - previous_value) < 1.0:
            direction = Direction.FLAT
        elif assessment.total_score > previous_value:
            direction = Direction.INCREASE
        else:
            direction = Direction.DECREASE
        previous_evidence = [
            Evidence(
                label="health_score_previous_period",
                value=money(previous_value),
                unit="score",
                source="engines.health.health_trend",
                window=str(previous["period"]),
                comparison=f"same six components, scored on history up to {previous['period']}",
                confidence=Confidence(previous["confidence"]),
            )
        ]

    narrative_evidence = _narrative_evidence(context, measure, assessment.confidence)
    all_evidence = dedupe(
        [item for component in assessment.components for item in component.evidence]
        + narrative_evidence
    )
    savings = next(
        item for item in assessment.components if item.key == HealthComponent.SAVINGS_BEHAVIOUR.value
    )
    liquidity = next(
        item for item in assessment.components if item.key == HealthComponent.LIQUIDITY_BUFFER.value
    )

    metrics = [
        Metric(
            key="health_score",
            label="Financial health score",
            value=assessment.total_score,
            unit="score",
            previous_value=previous["health_score"] if previous else None,
            change_percent=change_percent,
            direction=direction,
            confidence=assessment.confidence,
            evidence=all_evidence + previous_evidence,
        ),
        Metric(
            key="monthly_surplus",
            label="Average money left after spending",
            value=money(measure.monthly_surplus),
            confidence=assessment.confidence,
            evidence=[item for item in savings.evidence if item.label == "monthly_surplus"],
        ),
        Metric(
            key="emergency_buffer_months",
            label="Months of spending covered by the balance",
            value=months(measure.emergency_buffer_months),
            unit="months",
            confidence=assessment.confidence,
            evidence=[item for item in liquidity.evidence if item.label == "emergency_buffer_months"],
        ),
        Metric(
            key="monthly_income",
            label="Average monthly income",
            value=money(measure.monthly_income),
            confidence=assessment.confidence,
            evidence=next(
                (item.evidence for item in assessment.components if item.key == HealthComponent.INCOME_STABILITY.value),
                [],
            ),
        ),
    ]

    return HealthResponse(
        user_id=context.user_id,
        as_of=context.as_of.date().isoformat(),
        explanation=explanation,
        evidence=all_evidence,
        assumptions=_assumptions(),
        metrics=metrics,
        insights=[item for item in [_insight(assessment, measure)] if item is not None],
        label=assessment.label,
        window=assessment.window,
        months_observed=assessment.months_observed,
        components=assessment.components,
        bands=list(assessment.components),
        strengths=assessment.strengths,
        attention_areas=assessment.attention_areas,
        confidence=assessment.confidence,
    )
