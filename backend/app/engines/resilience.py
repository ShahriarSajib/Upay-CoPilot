"""Resilience: what happens to this month when something unexpected arrives.

Why this is a stress test and not a second health score
------------------------------------------------------
Health asks how well the month *ran*. Resilience asks a different question -- can
the customer absorb a cost they did not plan for -- and answering it with
health's arithmetic would hide the only interesting case. A customer can have
perfectly steady habits and still be one bad month away from trouble, so the
seventh dimension is simulated rather than inferred:

* the shock is one month of the customer's **own** recurring obligations, not a
  fixed percentage of income, because the household bill is already in their
  history and is the most likely shape a surprise takes;
* the shock is absorbed by the balance actually in hand, and the result is
  stated in directions the customer can check rather than a single yes/no: the
  cost as a share of a typical month's spending, the share of the reserve it
  would take, the months of cover left afterwards, and how many costs of that
  size the reserve could absorb in a row;
* the same arithmetic is replayed against **every observed month-end balance**,
  which turns "can I afford this" into "in how many of the last N months would
  this have left me short". The second number is the honest one, and it is what
  separates a large balance that has been eaten down month by month from a large
  balance that has not.

Everything else stays deterministic and measured: no sampling, no fitted model,
no randomness of any kind. The disclaimer's exact wording is fixed as a class
default on :class:`ResilienceResponse` so it cannot be paraphrased away by a
caller showing the number next to a lending conversation.

The dimension set deliberately overlaps health on income variation and buffer
size and differs everywhere else: expense *stability* rather than expense
*level*, savings *consistency* rather than savings rate, and cash reliance
measured on how the amount moves rather than only how much leaves in cash.

The measurement plumbing is shared with :mod:`app.engines.health` on purpose --
the two engines must not be able to disagree about what a customer's savings
rate or income variation is, so they read the same record and the same ladders.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.context import UserContext, get_context
from app.engines.health import (
    BUFFER_MONTHS_LADDER,
    CASH_OUT_STABILITY_LADDER,
    CASH_SHARE_LADDER,
    EXPENSE_RATIO_CV_LADDER,
    FUNDING_LADDER,
    GOAL_PROGRESS_LADDER,
    INCOME_CONSISTENCY_LADDER,
    INCOME_CV_LADDER,
    LATE_MONTH_SHARE_LADDER,
    LOW_BALANCE_LADDER,
    MIN_BALANCE_MONTHS_LADDER,
    NEUTRAL_COMPONENT_SCORE,
    SHORT_FREQUENCY_LADDER,
    SURPLUS_SIGN_LADDER,
    SURPLUS_VARIABILITY_LADDER,
    TOLERANCE_AFTER_SHOCK_LADDER,
    band_for,
    bdt,
    clamp,
    combine,
    confidence_for,
    dedupe,
    dispersion,
    measurements,
    money,
    months,
    pct,
    ramp,
    ratio,
)
from app.schemas.common import (
    Assumption,
    Band,
    Confidence,
    Evidence,
    Explanation,
    Insight,
    Metric,
    Severity,
)
from app.schemas.wellbeing import (
    ComponentResult,
    HealthMeasurements,
    ResilienceAssessment,
    ResilienceDimension,
    ResilienceGrade,
    ResilienceResponse,
    ShockSimulation,
)

SPEND_CV_LADDER = ((0.03, 100.0), (0.10, 88.0), (0.20, 72.0), (0.35, 54.0), (0.55, 32.0), (0.85, 10.0))

RESILIENCE_DIMENSION_WEIGHTS: dict[ResilienceDimension, float] = {
    ResilienceDimension.INCOME_STABILITY: 0.18,
    ResilienceDimension.EXPENSE_STABILITY: 0.15,
    ResilienceDimension.LIQUIDITY_BUFFER: 0.22,
    ResilienceDimension.SAVINGS_CONSISTENCY: 0.13,
    ResilienceDimension.GOAL_PROGRESS: 0.10,
    ResilienceDimension.CASH_OUT_DEPENDENCY: 0.10,
    ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE: 0.12,
}

RESILIENCE_DIMENSION_LABELS: dict[ResilienceDimension, str] = {
    ResilienceDimension.INCOME_STABILITY: "How predictable income is",
    ResilienceDimension.EXPENSE_STABILITY: "How predictable spending is",
    ResilienceDimension.LIQUIDITY_BUFFER: "Reserve held against a bad month",
    ResilienceDimension.SAVINGS_CONSISTENCY: "Whether saving happens reliably",
    ResilienceDimension.GOAL_PROGRESS: "Distance run toward savings goals",
    ResilienceDimension.CASH_OUT_DEPENDENCY: "Reliance on cash",
    ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE: "Room for a one-off cost",
}

RESILIENCE_DIMENSION_PHRASES: dict[ResilienceDimension, tuple[str, str]] = {
    ResilienceDimension.INCOME_STABILITY: (
        "Income arrives about the same each month",
        "Income swings from month to month",
    ),
    ResilienceDimension.EXPENSE_STABILITY: (
        "Spending is steady month to month",
        "Spending swings from month to month",
    ),
    ResilienceDimension.LIQUIDITY_BUFFER: (
        "A reserve is held back for a bad month",
        "Little is held back for a bad month",
    ),
    ResilienceDimension.SAVINGS_CONSISTENCY: (
        "Saving happens most months",
        "Saving happens in some months only",
    ),
    ResilienceDimension.GOAL_PROGRESS: (
        "Savings goals are moving",
        "Savings goals are barely moving",
    ),
    ResilienceDimension.CASH_OUT_DEPENDENCY: (
        "Little spending goes through cash",
        "Most spending goes through cash",
    ),
    ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE: (
        "Room for an unexpected cost",
        "No room for an unexpected cost",
    ),
}

RESILIENCE_SUB_WEIGHTS: dict[ResilienceDimension, dict[str, float]] = {
    ResilienceDimension.INCOME_STABILITY: {"income_cv": 0.60, "income_consistency": 0.40},
    ResilienceDimension.EXPENSE_STABILITY: {
        "spend_cv": 0.50,
        "late_month_concentration": 0.30,
        "expense_ratio_stability": 0.20,
    },
    ResilienceDimension.LIQUIDITY_BUFFER: {
        "buffer_months": 0.55,
        "min_balance_months": 0.25,
        "low_balance_frequency": 0.20,
    },
    ResilienceDimension.SAVINGS_CONSISTENCY: {
        "positive_surplus_share": 0.45,
        "surplus_variability": 0.35,
        "funding_consistency": 0.20,
    },
    ResilienceDimension.GOAL_PROGRESS: {"progress_rate": 0.60, "funding_consistency": 0.40},
    ResilienceDimension.CASH_OUT_DEPENDENCY: {"cash_share": 0.65, "cash_out_stability": 0.35},
    ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE: {
        "buffer_months_after_shock": 0.60,
        "months_short_after_shock": 0.40,
    },
}

RESILIENCE_GRADE_CUTS: tuple[tuple[float, ResilienceGrade], ...] = (
    (75.0, ResilienceGrade.STRONG),
    (55.0, ResilienceGrade.STEADY),
    (35.0, ResilienceGrade.THIN),
    (0.0, ResilienceGrade.FRAGILE),
)

SOURCE_MONTHLY = "monthly_features"
SOURCE_RECURRING = "recurring_expenses"
SOURCE_ENGINE = "engines.resilience"

ESSENTIAL_SPEND_FALLBACK_SHARE = 0.55

TRIVIAL_SHOCK_SHARE = 0.01


def _grade_for(score: float) -> ResilienceGrade:
    for cut, grade in RESILIENCE_GRADE_CUTS:
        if score >= cut:
            return grade
    return ResilienceGrade.FRAGILE


def _result(
    dimension: ResilienceDimension,
    score: float,
    detail: str,
    evidence: list[Evidence],
    sub_scores: dict[str, float],
) -> ComponentResult:
    rounded = money(clamp(score))
    weight = RESILIENCE_DIMENSION_WEIGHTS[dimension]
    return ComponentResult(
        key=dimension.value,
        label=RESILIENCE_DIMENSION_LABELS[dimension],
        score=rounded,
        band=band_for(rounded).value,
        weight=weight,
        contribution=money(rounded * weight),
        detail=detail,
        evidence=evidence,
        sub_scores={key: money(value) for key, value in sub_scores.items()},
    )


def _held_neutral(
    dimension: ResilienceDimension,
    detail: str,
    evidence: list[Evidence],
) -> ComponentResult:
    """A dimension the customer's own history cannot measure, at the midpoint."""
    weight = RESILIENCE_DIMENSION_WEIGHTS[dimension]
    return ComponentResult(
        key=dimension.value,
        label=RESILIENCE_DIMENSION_LABELS[dimension],
        score=NEUTRAL_COMPONENT_SCORE,
        band=band_for(NEUTRAL_COMPONENT_SCORE).value,
        weight=weight,
        contribution=money(NEUTRAL_COMPONENT_SCORE * weight),
        detail=detail,
        evidence=evidence,
        held_neutral=True,
        sub_scores={},
    )


def _essential_spend(context: UserContext, measure: HealthMeasurements) -> tuple[float, str]:
    """The customer's own monthly essentials, with an explicit fallback chain."""
    if measure.recurring_amount_mean > 0:
        return measure.recurring_amount_mean, "recurring_obligations"
    if not context.recurring.empty:
        table_mean = float(context.recurring["amount"].mean())
        if table_mean > 0:
            return table_mean, "recurring_table"
    return measure.monthly_expense * ESSENTIAL_SPEND_FALLBACK_SHARE, "expense_share_fallback"


def shock_simulation(context: UserContext, measure: HealthMeasurements) -> ShockSimulation:
    """Absorb one month of the customer's own essentials from the balance.

    Also replayed against every month-end balance in the window, so the shortfall
    frequency is a count of months that really happened rather than a projection.
    """
    essentials, basis = _essential_spend(context, measure)
    buffer_before = max(measure.ending_balance, 0.0)
    buffer_after = buffer_before - essentials
    buffer_months_before = (
        buffer_before / measure.monthly_expense if measure.monthly_expense > 0 else 0.0
    )
    months_absorbed = essentials / measure.monthly_expense if measure.monthly_expense > 0 else 0.0
    reserve_share = essentials / buffer_before if buffer_before > 0 else 0.0
    shocks_covered = buffer_before / essentials if essentials > 0 else 0.0
    months_remaining = buffer_months_before - months_absorbed

    months_short = 0.0
    if essentials > 0 and not context.monthly.empty:
        balances = context.monthly["ending_balance"].to_numpy(dtype=float)
        months_short = float((balances - essentials < settings.minimum_balance_buffer).mean())

    note: str | None = None
    if essentials <= 0:
        note = (
            "No recurring obligations or spending are on file, so no one-off cost could be "
            "sized. This dimension is reported as neutral rather than as full marks."
        )
    elif basis == "expense_share_fallback":
        note = (
            "No recurring obligations are on file, so a month's essentials are estimated at "
            f"{int(ESSENTIAL_SPEND_FALLBACK_SHARE * 100)}% of average spending."
        )
    elif buffer_after < 0:
        note = (
            f"A {essentials:,.0f} BDT one-off cost is larger than the {buffer_before:,.0f} BDT "
            "balance in hand, so it would have to be met from the next month's income."
        )

    return ShockSimulation(
        essential_monthly_spend=money(essentials),
        months_of_spending_absorbed=months(months_absorbed),
        buffer_before=money(buffer_before),
        buffer_after=money(buffer_after),
        buffer_months_remaining=months(months_remaining),
        reserve_share_consumed=ratio(reserve_share),
        shocks_absorbed_by_buffer=months(shocks_covered),
        shortfall=money(max(essentials - buffer_before, 0.0)),
        months_short_after_shock=ratio(months_short),
        affordable=bool(essentials > 0 and buffer_after >= settings.minimum_balance_buffer),
        basis=basis,
        note=note,
    )


def _shock_evidence(measure: HealthMeasurements, shock: ShockSimulation) -> list[Evidence]:
    window = measure.window
    evidence = [
        Evidence(
            label="one_off_cost",
            value=money(shock.essential_monthly_spend),
            source=SOURCE_RECURRING,
            window=window,
            comparison="the customer's own recurring obligations, used as the one-off cost",
        ),
        Evidence(
            label="buffer_before_shock",
            value=money(shock.buffer_before),
            source=f"{SOURCE_MONTHLY}.ending_balance",
            window=window,
            comparison="balance in hand at the end of the latest month",
        ),
        Evidence(
            label="buffer_after_shock",
            value=money(shock.buffer_after),
            source=f"{SOURCE_MONTHLY}.ending_balance",
            window=window,
            comparison="balance once that one-off cost has been paid",
        ),
        Evidence(
            label="months_of_spending_absorbed",
            value=months(shock.months_of_spending_absorbed),
            unit="months",
            source=SOURCE_ENGINE,
            window=window,
            comparison="the one-off cost as a share of a typical month's spending",
        ),
        Evidence(
            label="reserve_share_consumed",
            value=ratio(shock.reserve_share_consumed),
            unit="ratio",
            source=SOURCE_ENGINE,
            window=window,
            comparison="the one-off cost as a share of the reserve in hand",
        ),
        Evidence(
            label="shocks_absorbed_by_buffer",
            value=months(shock.shocks_absorbed_by_buffer),
            unit="months",
            source=SOURCE_ENGINE,
            window=window,
            comparison="how many costs of this size the reserve could cover in a row",
        ),
        Evidence(
            label="months_short_after_shock",
            value=ratio(shock.months_short_after_shock),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.ending_balance",
            window=window,
            comparison=(
                f"months out of {measure.months_observed} where this cost would have left the "
                f"balance under {bdt(settings.minimum_balance_buffer)}"
            ),
        ),
    ]
    if measure.surprise_events > 0:
        evidence.append(
            Evidence(
                label="flagged_unusual_charges",
                value=float(int(measure.surprise_events)),
                unit="charges",
                source="transactions.is_anomaly",
                window=window,
                comparison="unusual charges already flagged in this window",
            )
        )
    return evidence


def _income_dimension(
    context: UserContext,
    measure: HealthMeasurements,
    shock: ShockSimulation,
    confidence: Confidence,
) -> ComponentResult:
    sub_scores = {
        "income_cv": ramp(measure.income_cv, INCOME_CV_LADDER),
        "income_consistency": ramp(measure.income_consistency, INCOME_CONSISTENCY_LADDER),
    }
    score = combine(sub_scores, RESILIENCE_SUB_WEIGHTS[ResilienceDimension.INCOME_STABILITY])
    evidence = [
        Evidence(
            label="income_cv",
            value=ratio(measure.income_cv),
            unit="ratio",
            source="user_features.income_cv",
            window=measure.window,
            comparison="how far each month strays from the customer's own average income",
            confidence=confidence,
        ),
        Evidence(
            label="income_consistency",
            value=ratio(measure.income_consistency),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.income",
            window=measure.window,
            comparison="months that arrived close to that average",
            confidence=confidence,
        ),
        Evidence(
            label="monthly_income",
            value=money(measure.monthly_income),
            source=f"{SOURCE_MONTHLY}.income",
            window=measure.window,
            comparison="average income across the observed months",
            confidence=confidence,
        ),
    ]
    detail = (
        f"Income moves about {pct(measure.income_cv)} around its average, and "
        f"{pct(measure.income_consistency)} of months arrive close to it."
    )
    return _result(ResilienceDimension.INCOME_STABILITY, score, detail, evidence, sub_scores)


def _expense_dimension(
    context: UserContext,
    measure: HealthMeasurements,
    shock: ShockSimulation,
    confidence: Confidence,
) -> ComponentResult:
    sub_scores = {
        "spend_cv": ramp(measure.spend_cv, SPEND_CV_LADDER),
        "late_month_concentration": ramp(measure.late_month_share, LATE_MONTH_SHARE_LADDER),
        "expense_ratio_stability": ramp(measure.expense_ratio_cv, EXPENSE_RATIO_CV_LADDER),
    }
    score = combine(sub_scores, RESILIENCE_SUB_WEIGHTS[ResilienceDimension.EXPENSE_STABILITY])
    evidence = [
        Evidence(
            label="spend_cv",
            value=ratio(measure.spend_cv),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.spend",
            window=measure.window,
            comparison="month-to-month variation in total spending",
            confidence=confidence,
        ),
        Evidence(
            label="late_month_share",
            value=ratio(measure.late_month_share),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.late_share",
            window=measure.window,
            comparison="share of spending landing from the 23rd of the month onwards",
            confidence=confidence,
        ),
        Evidence(
            label="expense_ratio_variation",
            value=ratio(measure.expense_ratio_cv),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.expense_income_ratio",
            window=measure.window,
            comparison="variation in spending measured against that month's income",
            confidence=confidence,
        ),
    ]
    detail = (
        f"Monthly spending varies by about {pct(measure.spend_cv)}, with "
        f"{pct(measure.late_month_share)} of it landing in the last third of the month."
    )
    return _result(ResilienceDimension.EXPENSE_STABILITY, score, detail, evidence, sub_scores)


def _liquidity_dimension(
    context: UserContext,
    measure: HealthMeasurements,
    shock: ShockSimulation,
    confidence: Confidence,
) -> ComponentResult:
    min_balance_months = (
        max(measure.lowest_balance, 0.0) / measure.monthly_expense
        if measure.monthly_expense > 0
        else 0.0
    )
    sub_scores = {
        "buffer_months": ramp(measure.emergency_buffer_months, BUFFER_MONTHS_LADDER),
        "min_balance_months": ramp(min_balance_months, MIN_BALANCE_MONTHS_LADDER),
        "low_balance_frequency": ramp(measure.low_balance_frequency, LOW_BALANCE_LADDER),
    }
    score = combine(sub_scores, RESILIENCE_SUB_WEIGHTS[ResilienceDimension.LIQUIDITY_BUFFER])
    evidence = [
        Evidence(
            label="emergency_buffer_months",
            value=months(measure.emergency_buffer_months),
            unit="months",
            source="user_features.emergency_buffer_months",
            window=measure.window,
            comparison="months of average spending covered by the balance",
            confidence=confidence,
        ),
        Evidence(
            label="min_balance_months",
            value=months(min_balance_months),
            unit="months",
            source=f"{SOURCE_MONTHLY}.min_balance",
            window=measure.window,
            comparison="months of spending covered by the lowest balance in the window",
            confidence=confidence,
        ),
        Evidence(
            label="low_balance_frequency",
            value=ratio(measure.low_balance_frequency),
            unit="ratio",
            source="user_features.low_balance_frequency",
            window=measure.window,
            comparison="share of days spent below the minimum-balance line",
            confidence=confidence,
        ),
    ]
    detail = (
        f"The balance covers about {months(measure.emergency_buffer_months)} months of spending, "
        f"and the lowest balance in the window covers about {months(min_balance_months)}."
    )
    return _result(ResilienceDimension.LIQUIDITY_BUFFER, score, detail, evidence, sub_scores)


def _savings_dimension(
    context: UserContext,
    measure: HealthMeasurements,
    shock: ShockSimulation,
    confidence: Confidence,
) -> ComponentResult:
    positive_share = max(1.0 - measure.negative_surplus_share, 0.0)
    surplus_variability = (
        float(measure.surplus_dispersion / measure.monthly_income)
        if measure.monthly_income > 0
        else 0.0
    )
    sub_scores = {
        "positive_surplus_share": ramp(positive_share, SURPLUS_SIGN_LADDER),
        "surplus_variability": ramp(surplus_variability, SURPLUS_VARIABILITY_LADDER),
    }
    if measure.goal_count > 0:
        sub_scores["funding_consistency"] = ramp(measure.funding_consistency, FUNDING_LADDER)
    score = combine(sub_scores, RESILIENCE_SUB_WEIGHTS[ResilienceDimension.SAVINGS_CONSISTENCY])
    surplus_months = int(round(positive_share * measure.months_observed))
    evidence = [
        Evidence(
            label="positive_surplus_share",
            value=ratio(positive_share),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.surplus",
            window=measure.window,
            comparison=f"months left with something spare out of {measure.months_observed}",
            confidence=confidence,
        ),
        Evidence(
            label="surplus_variability",
            value=ratio(surplus_variability),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.surplus",
            window=measure.window,
            comparison="how much the amount left over moves, relative to average income",
            confidence=confidence,
        ),
        Evidence(
            label="funding_consistency",
            value=ratio(measure.funding_consistency),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.goal_contribution",
            window=measure.window,
            comparison="months with a goal contribution, where a goal exists",
            confidence=confidence,
        ),
    ]
    detail = (
        f"Something was left over in {surplus_months} of {measure.months_observed} months, "
        f"averaging {bdt(measure.monthly_surplus)} a month."
    )
    return _result(ResilienceDimension.SAVINGS_CONSISTENCY, score, detail, evidence, sub_scores)


def _goal_dimension(
    context: UserContext,
    measure: HealthMeasurements,
    shock: ShockSimulation,
    confidence: Confidence,
) -> ComponentResult:
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
            label="goal_progress",
            value=ratio(measure.goal_progress),
            unit="ratio",
            source="user_features.goal_progress",
            window=measure.window,
            comparison="share of the target amount already reached",
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
    ]
    if measure.goal_count <= 0:
        return _held_neutral(
            ResilienceDimension.GOAL_PROGRESS,
            "No savings goal is set, so this dimension is held at the midpoint rather than "
            "read as a gap.",
            evidence,
        )
    sub_scores = {
        "progress_rate": ramp(measure.goal_progress, GOAL_PROGRESS_LADDER),
        "funding_consistency": ramp(measure.funding_consistency, FUNDING_LADDER),
    }
    score = combine(sub_scores, RESILIENCE_SUB_WEIGHTS[ResilienceDimension.GOAL_PROGRESS])
    detail = (
        f"Goals are {pct(measure.goal_progress)} funded, with a contribution recorded in "
        f"{pct(measure.funding_consistency)} of months."
    )
    return _result(ResilienceDimension.GOAL_PROGRESS, score, detail, evidence, sub_scores)


def _cash_out_variation(context: UserContext) -> float:
    """How much the amount moved to cash each month changes, over the same window."""
    if context.monthly.empty:
        return 0.0
    return dispersion(context.monthly["cash_out_amount"].to_numpy(dtype=float))


def _cash_dimension(
    context: UserContext,
    measure: HealthMeasurements,
    shock: ShockSimulation,
    confidence: Confidence,
) -> ComponentResult:
    cash_out_cv = _cash_out_variation(context)
    sub_scores = {
        "cash_share": ramp(measure.cash_dependency, CASH_SHARE_LADDER),
        "cash_out_stability": ramp(cash_out_cv, CASH_OUT_STABILITY_LADDER),
    }
    score = combine(sub_scores, RESILIENCE_SUB_WEIGHTS[ResilienceDimension.CASH_OUT_DEPENDENCY])
    evidence = [
        Evidence(
            label="cash_dependency",
            value=ratio(measure.cash_dependency),
            unit="ratio",
            source="user_features.cash_dependency",
            window=measure.window,
            comparison="share of spending paid out of cash wallets",
            confidence=confidence,
        ),
        Evidence(
            label="cash_out_variation",
            value=ratio(cash_out_cv),
            unit="ratio",
            source=f"{SOURCE_MONTHLY}.cash_out_amount",
            window=measure.window,
            comparison="how much the amount moved to cash changes month to month",
            confidence=confidence,
        ),
        Evidence(
            label="has_cash_wallet",
            value=1.0 if measure.has_cash_wallet else 0.0,
            unit="flag",
            source="wallets.wallet_type",
            window=measure.window,
            comparison="whether a cash wallet is on the account",
            confidence=confidence,
        ),
    ]
    detail = (
        f"About {pct(measure.cash_dependency)} of spending is in cash, and that share moves by "
        f"{pct(cash_out_cv)} month to month, so part of the month stays outside this history."
    )
    return _result(ResilienceDimension.CASH_OUT_DEPENDENCY, score, detail, evidence, sub_scores)


def _tolerance_dimension(
    context: UserContext,
    measure: HealthMeasurements,
    shock: ShockSimulation,
    confidence: Confidence,
) -> ComponentResult:
    evidence = [
        item.model_copy(update={"confidence": confidence})
        for item in _shock_evidence(measure, shock)
    ]
    measurable = shock.essential_monthly_spend > TRIVIAL_SHOCK_SHARE * settings.minimum_balance_buffer
    if not measurable:
        return _held_neutral(
            ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE,
            "There is not enough recorded spending to size a one-off cost, so this dimension is "
            "held at the midpoint instead of counting as full marks.",
            evidence,
        )
    sub_scores = {
        "buffer_months_after_shock": ramp(
            shock.buffer_months_remaining, TOLERANCE_AFTER_SHOCK_LADDER
        ),
        "months_short_after_shock": ramp(shock.months_short_after_shock, SHORT_FREQUENCY_LADDER),
    }
    score = combine(
        sub_scores, RESILIENCE_SUB_WEIGHTS[ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE]
    )
    detail = (
        f"A {bdt(shock.essential_monthly_spend)} one-off cost, about "
        f"{months(shock.months_of_spending_absorbed)} of average spending, would use "
        f"{pct(shock.reserve_share_consumed)} of the reserve in hand and leave "
        f"{months(shock.buffer_months_remaining)} months of cover."
    )
    return _result(
        ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE, score, detail, evidence, sub_scores
    )


def _dimension_confidence(
    measure: HealthMeasurements, dimension: ResilienceDimension
) -> Confidence:
    """Confidence for a dimension, tightened where the input is thin.

    Goal progress and the shock test both need more than a couple of months
    before they say anything about the future rather than about one month, so
    they are reported as low confidence below four and three months respectively.
    """
    if dimension is ResilienceDimension.GOAL_PROGRESS and measure.months_observed < 4:
        return confidence_for(
            measure.months_observed, measure.income_cv, measure.spend_cv, thin_input=True
        )
    return confidence_for(measure.months_observed, measure.income_cv, measure.spend_cv)


_DIMENSION_BUILDERS = {
    ResilienceDimension.INCOME_STABILITY: _income_dimension,
    ResilienceDimension.EXPENSE_STABILITY: _expense_dimension,
    ResilienceDimension.LIQUIDITY_BUFFER: _liquidity_dimension,
    ResilienceDimension.SAVINGS_CONSISTENCY: _savings_dimension,
    ResilienceDimension.GOAL_PROGRESS: _goal_dimension,
    ResilienceDimension.CASH_OUT_DEPENDENCY: _cash_dimension,
    ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE: _tolerance_dimension,
}


def _ranked(dimensions: list[ComponentResult]) -> tuple[list[ComponentResult], list[ComponentResult]]:
    measurable = [item for item in dimensions if not item.held_neutral]
    ordered = sorted(measurable, key=lambda item: (-item.score, item.key))
    return ordered[:2], list(reversed(ordered[-2:]))


def _phrase(item: ComponentResult, positive: bool) -> str:
    dimension = ResilienceDimension(item.key)
    good, bad = RESILIENCE_DIMENSION_PHRASES[dimension]
    return good if positive else bad


def _weakest_confidence(dimensions: list[ComponentResult]) -> Confidence:
    order = {"low": 0, "medium": 1, "high": 2}
    levels = [item.evidence[0].confidence.value for item in dimensions if item.evidence]
    if not levels:
        return Confidence.LOW
    return Confidence(min(levels, key=lambda level: order[level]))


def resilience_assessment(user_id: str) -> ResilienceAssessment:
    """The scored resilience result for one customer."""
    context = get_context(user_id)
    measure = measurements(context)
    shock = shock_simulation(context, measure)

    dimensions: list[ComponentResult] = [
        _DIMENSION_BUILDERS[dimension](
            context,
            measure,
            shock,
            _dimension_confidence(measure, dimension),
        )
        for dimension in RESILIENCE_DIMENSION_WEIGHTS
    ]

    total = clamp(money(sum(item.contribution for item in dimensions)))
    strengths, attention = _ranked(dimensions)
    return ResilienceAssessment(
        user_id=context.user_id,
        as_of=context.as_of.date().isoformat(),
        total_score=total,
        label=_grade_for(total).value,
        dimensions=dimensions,
        strengths=[_phrase(item, True) for item in strengths],
        attention_areas=[_phrase(item, False) for item in attention],
        confidence=_weakest_confidence(dimensions),
        months_observed=measure.months_observed,
        shock=shock,
    )


def _explanation(
    measure: HealthMeasurements, shock: ShockSimulation, grade: ResilienceGrade, total: float
) -> Explanation:
    headline_phrase = {
        ResilienceGrade.STRONG: "there is real room here for something unplanned",
        ResilienceGrade.STEADY: "a surprise would be absorbed, though not comfortably every time",
        ResilienceGrade.THIN: "an unexpected cost would land in the same month it arrives",
        ResilienceGrade.FRAGILE: "there is very little between this month's balance and the next bill",
    }[grade]
    headline = f"{grade.value.capitalize()}: {headline_phrase} ({total:.0f} of 100)."

    detail = [
        f"A one-off cost the size of a month's own bills, {bdt(shock.essential_monthly_spend)}, "
        f"is about {months(shock.months_of_spending_absorbed)} of average spending.",
        f"Paid from the {bdt(shock.buffer_before)} in hand, it would take "
        f"{pct(shock.reserve_share_consumed)} of the reserve, leave "
        f"{months(shock.buffer_months_remaining)} months of cover, and could be repeated "
        f"{months(shock.shocks_absorbed_by_buffer)} times before the reserve runs out.",
    ]
    if measure.months_observed > 0:
        if shock.months_short_after_shock > 0:
            short_months = int(round(shock.months_short_after_shock * measure.months_observed))
            detail.append(
                "Replayed against each month-end balance in this window, that cost would have "
                f"left the balance under {bdt(settings.minimum_balance_buffer)} in {short_months} "
                f"of {measure.months_observed} months."
            )
        else:
            detail.append(
                "Replayed against each month-end balance in this window, that cost would still "
                f"have left the balance above {bdt(settings.minimum_balance_buffer)} every month."
            )
    if measure.income_cv >= 0.30:
        detail.append(
            f"Income moves about {pct(measure.income_cv)} month to month, so a worse-than-average "
            "month is worth planning for on its own."
        )
    elif measure.spend_cv >= 0.20:
        detail.append(
            f"Spending itself moves about {pct(measure.spend_cv)} month to month, which is most of "
            "what makes a month hard to plan."
        )
    return Explanation(headline=headline, detail=detail[:4])


_RESILIENCE_ACTIONS: dict[str, str] = {
    ResilienceDimension.INCOME_STABILITY.value: (
        "Plan to a conservative monthly income and treat anything above it as headroom."
    ),
    ResilienceDimension.EXPENSE_STABILITY.value: (
        "Move the flexible spending earlier in the month, before the balance is already tight."
    ),
    ResilienceDimension.LIQUIDITY_BUFFER.value: (
        "Add a small automatic transfer after payday until the reserve reaches "
        f"{settings.emergency_fund_months:.0f} months of spending."
    ),
    ResilienceDimension.SAVINGS_CONSISTENCY.value: (
        "Set the saving to leave the account first, so it happens before the month spends it."
    ),
    ResilienceDimension.GOAL_PROGRESS.value: (
        "Keep one goal running at an amount that survives a low-income month."
    ),
    ResilienceDimension.CASH_OUT_DEPENDENCY.value: (
        "Leave a small digital float for everyday payments so more of the month stays visible."
    ),
    ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE.value: (
        "Treat one month of bills as the thing to reserve for, and fund it deliberately rather "
        "than by accident."
    ),
}


def _insight(assessment: ResilienceAssessment, shock: ShockSimulation) -> Insight | None:
    candidates = [
        item
        for item in assessment.dimensions
        if not item.held_neutral and item.evidence and item.score < 70.0
    ]
    if not candidates:
        return None
    weakest = min(candidates, key=lambda item: item.score)
    is_tolerance = weakest.key == ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE.value
    return Insight(
        key=f"resilience.{weakest.key}",
        title=f"{weakest.label}: the dimension with the least room",
        observation=weakest.detail,
        why=(
            f"It contributes {weakest.contribution:.1f} of the {assessment.total_score:.0f} total "
            f"at a weight of {weakest.weight:.2f}."
        ),
        action=_RESILIENCE_ACTIONS[weakest.key],
        severity=Severity.WARNING if weakest.score < 25.0 else Severity.ATTENTION,
        impact_bdt=shock.shortfall if is_tolerance and shock.shortfall > 0 else None,
        evidence=weakest.evidence[:3],
    )


def resilience_score(user_id: str) -> ResilienceResponse:
    """Resilience for one customer, with the one-off-cost simulation attached."""
    context = get_context(user_id)
    measure = measurements(context)
    assessment = resilience_assessment(user_id)
    shock = assessment.shock

    all_evidence = dedupe(
        [item for dimension in assessment.dimensions for item in dimension.evidence]
    )
    tolerance = next(
        item
        for item in assessment.dimensions
        if item.key == ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE.value
    )
    liquidity = next(
        item
        for item in assessment.dimensions
        if item.key == ResilienceDimension.LIQUIDITY_BUFFER.value
    )
    income = next(
        item
        for item in assessment.dimensions
        if item.key == ResilienceDimension.INCOME_STABILITY.value
    )
    evidence_by_label = {item.label: item for item in all_evidence}

    def labelled(label: str, fallback: list[Evidence]) -> list[Evidence]:
        item = evidence_by_label.get(label)
        return [item] if item is not None else fallback

    metrics = [
        Metric(
            key="resilience_score",
            label="Resilience score",
            value=assessment.total_score,
            unit="score",
            confidence=assessment.confidence,
            evidence=all_evidence,
        ),
        Metric(
            key="one_off_cost",
            label="One-off cost absorbed by the reserve",
            value=money(shock.essential_monthly_spend),
            confidence=assessment.confidence,
            evidence=labelled("one_off_cost", tolerance.evidence[:1]),
        ),
        Metric(
            key="reserve_share_consumed",
            label="Share of the reserve that cost would use",
            value=ratio(shock.reserve_share_consumed),
            unit="ratio",
            confidence=assessment.confidence,
            evidence=labelled("reserve_share_consumed", tolerance.evidence[:1]),
        ),
        Metric(
            key="shocks_absorbed_by_buffer",
            label="Costs of this size the reserve could cover",
            value=months(shock.shocks_absorbed_by_buffer),
            unit="months",
            confidence=assessment.confidence,
            evidence=labelled("shocks_absorbed_by_buffer", tolerance.evidence[:1]),
        ),
        Metric(
            key="buffer_months_after_shock",
            label="Months of cover left after that cost",
            value=months(shock.buffer_months_remaining),
            unit="months",
            confidence=assessment.confidence,
            evidence=labelled("buffer_after_shock", tolerance.evidence[:1]),
        ),
        Metric(
            key="emergency_buffer_months",
            label="Months of spending covered by the balance",
            value=months(measure.emergency_buffer_months),
            unit="months",
            confidence=assessment.confidence,
            evidence=labelled("emergency_buffer_months", liquidity.evidence[:1]),
        ),
        Metric(
            key="monthly_income",
            label="Average monthly income",
            value=money(measure.monthly_income),
            confidence=assessment.confidence,
            evidence=labelled("monthly_income", income.evidence[:1]),
        ),
    ]

    return ResilienceResponse(
        user_id=context.user_id,
        as_of=context.as_of.date().isoformat(),
        explanation=_explanation(
            measure, shock, _grade_for(assessment.total_score), assessment.total_score
        ),
        evidence=all_evidence,
        assumptions=_assumptions(),
        metrics=metrics,
        insights=[item for item in [_insight(assessment, shock)] if item is not None],
        label=assessment.label,
        window=measure.window,
        months_observed=assessment.months_observed,
        dimensions=assessment.dimensions,
        bands=list(assessment.dimensions),
        strengths=assessment.strengths,
        attention_areas=assessment.attention_areas,
        confidence=assessment.confidence,
        shock=shock,
    )


def _assumptions() -> list[Assumption]:
    return [
        Assumption(
            key="weight.income_stability",
            value=RESILIENCE_DIMENSION_WEIGHTS[ResilienceDimension.INCOME_STABILITY],
            rationale=(
                "A month with no income cannot absorb anything, so income predictability is the "
                "first thing this score measures."
            ),
        ),
        Assumption(
            key="weight.expense_stability",
            value=RESILIENCE_DIMENSION_WEIGHTS[ResilienceDimension.EXPENSE_STABILITY],
            rationale=(
                "Predictable spending is what makes a reserve last; an irregular month is where "
                "reserves disappear."
            ),
        ),
        Assumption(
            key="weight.liquidity_buffer",
            value=RESILIENCE_DIMENSION_WEIGHTS[ResilienceDimension.LIQUIDITY_BUFFER],
            rationale=(
                "The single largest weight: money already set aside is the only thing that can "
                "absorb a cost on the day it arrives."
            ),
        ),
        Assumption(
            key="weight.savings_consistency",
            value=RESILIENCE_DIMENSION_WEIGHTS[ResilienceDimension.SAVINGS_CONSISTENCY],
            rationale=(
                "Saving that happens reliably builds a reserve; saving that happens only in good "
                "months does not."
            ),
        ),
        Assumption(
            key="weight.goal_progress",
            value=RESILIENCE_DIMENSION_WEIGHTS[ResilienceDimension.GOAL_PROGRESS],
            rationale=(
                "Distance toward a goal is the forward-looking form of the same habit, so it "
                "carries the smallest weight of the three saving dimensions."
            ),
        ),
        Assumption(
            key="weight.cash_out_dependency",
            value=RESILIENCE_DIMENSION_WEIGHTS[ResilienceDimension.CASH_OUT_DEPENDENCY],
            rationale=(
                "Cash reliance matters here because cash spending is missing from this history: "
                "without it the score would look better than the month really was."
            ),
        ),
        Assumption(
            key="weight.unexpected_expense_tolerance",
            value=RESILIENCE_DIMENSION_WEIGHTS[ResilienceDimension.UNEXPECTED_EXPENSE_TOLERANCE],
            rationale=(
                "The simulation is the question the product exists to answer, so it outweighs any "
                "single habit."
            ),
        ),
        Assumption(
            key="shock_size_months",
            value=1.0,
            rationale=(
                "The one-off cost is exactly one month of the customer's own recurring "
                "obligations, so the shock is scaled to their household rather than to an "
                "average account."
            ),
        ),
        Assumption(
            key="essential_spend_fallback_share",
            value=ESSENTIAL_SPEND_FALLBACK_SHARE,
            rationale=(
                "With no recurring obligations on file, a month's essentials are estimated at "
                "55% of average spending. This is a guess about a household and is shown as one."
            ),
        ),
        Assumption(
            key="minimum_balance_buffer",
            value=float(settings.minimum_balance_buffer),
            rationale=(
                "The minimum-balance line decides when the simulation counts as a shortfall. It "
                "is a product setting, not an observation."
            ),
        ),
        Assumption(
            key="buffer_months_after_shock_target",
            value=TOLERANCE_AFTER_SHOCK_LADDER[-2][0],
            rationale=(
                "One month of cover left after the shock scores 80 and three months scores 100; "
                "nothing left scores 42 and a two-month shortfall scores zero."
            ),
        ),
        Assumption(
            key="months_short_ceiling",
            value=SHORT_FREQUENCY_LADDER[3][0],
            rationale=(
                "The cost leaving the balance under the minimum line in half of the observed "
                "months scores 38; in every month it scores zero."
            ),
        ),
        Assumption(
            key="min_balance_months_target",
            value=MIN_BALANCE_MONTHS_LADDER[-1][0],
            rationale=(
                "A lowest-ever balance covering two months of spending scores 100, because the "
                "worst point of the history matters more than its average."
            ),
        ),
        Assumption(
            key="spend_cv_steady_max",
            value=SPEND_CV_LADDER[1][0],
            rationale=(
                "Total spending varying by 10% a month scores 88; beyond 35% it scores 54, "
                "because a reserve has to be sized for the worst month, not the average one."
            ),
        ),
        Assumption(
            key="late_month_share_target",
            value=LATE_MONTH_SHARE_LADDER[2][0],
            rationale=(
                "When 35% of spending lands in the last third of the month the score is 70. "
                "Concentration there is measured because that is when the balance gets tight."
            ),
        ),
        Assumption(
            key="cash_share_comfortable_max",
            value=CASH_SHARE_LADDER[2][0],
            rationale=(
                "Cash at 35% of spending scores 64 and 70% scores 22. It measures how much of "
                "the month this history cannot see."
            ),
        ),
        Assumption(
            key="surplus_variability_target",
            value=SURPLUS_VARIABILITY_LADDER[1][0],
            rationale=(
                "A leftover amount that moves by 8% of monthly income scores 88. Saving that "
                "arrives erratically does not build a reserve the same way steady saving does."
            ),
        ),
    ]


def resilience_bands(user_id: str) -> list[Band]:
    """The seven scored dimensions, for an explainable score display."""
    return list(resilience_assessment(user_id).dimensions)
