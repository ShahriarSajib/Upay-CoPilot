"""Credit readiness -- explicitly *not* a credit score.

Boundaries, because this is the part of a financial product that does real
damage when it overreaches:

* It is not a credit score, it is not a bureau report, and it must never be
  presented as one. It is a self-assessment of readiness built from a
  customer's own transaction patterns.
* It cannot approve or deny anything. There is no lender here.
* It does not estimate a repayment capacity or a loan amount, because this
  dataset has no debt, no loan history and no obligation balances -- only
  recurring bills. Anything implying otherwise would be invented.
* Protected attributes are not inputs. ``age_group``, ``occupation`` and
  ``location_type`` exist in the profile table and are deliberately unused;
  :data:`EXCLUDED_ATTRIBUTES` names them so the omission is auditable rather
  than accidental, and the response repeats the list to the caller.

Every projected number is produced by re-running :func:`score_readiness` against
a *modified copy* of the customer's own features. Nothing here estimates an
uplift in score points; it recalculates.
"""

from __future__ import annotations

from typing import Any

from app.core.context import UserContext, get_context
from app.schemas.common import (
    Assumption,
    Confidence,
    Direction,
    Evidence,
    Explanation,
    Insight,
    Metric,
    Severity,
)
from app.schemas.credit import (
    CreditReadinessResponse,
    ReadinessAction,
    ReadinessComponent,
    ReadinessOverall,
)

# Named here so the exclusion is a visible, testable statement.
EXCLUDED_ATTRIBUTES = ("age_group", "occupation", "location_type", "gender", "name")

# Months of history below which nothing here is worth saying.
MIN_MONTHS = 3

# Bands, top to bottom. Readiness never has a "not eligible" floor: the
# customer is not being judged, they are being told where they stand.
BANDS: tuple[tuple[float, str], ...] = (
    (80.0, "ready"),
    (65.0, "almost"),
    (50.0, "building"),
    (30.0, "early"),
    (0.0, "starting"),
)
BAND_ORDER = ("starting", "early", "building", "almost", "ready")

# Hard stops. These cap the band rather than produce a refusal, because a cap
# is recoverable in a way a rejection is not.
BLOCKERS: tuple[tuple[str, str, str], ...] = (
    (
        "thin_history",
        "Not enough history to judge",
        f"Fewer than {MIN_MONTHS} months of transactions are available, so this is "
        "left as unknown instead of being scored from a thin sample.",
    ),
    (
        "chronic_negative_surplus",
        "Money going backwards for months",
        "Three or more months ended in a deficit. Until a surplus is the normal "
        "case, new obligations add risk rather than building it.",
    ),
    (
        "chronic_late_payments",
        "Bills are habitually late",
        "Obligations were paid after their due date in half or more of the "
        "observed months. Late payment history is the fastest way to become "
        "ineligible later.",
    ),
)

WEIGHTS: dict[str, float] = {
    "liquidity": 0.22,
    "saving_consistency": 0.18,
    "payment_history": 0.18,
    "income_stability": 0.14,
    "debt_service": 0.12,
    "spending_control": 0.10,
    "financial_footprint": 0.06,
}


def _evidence(
    label: str,
    value: float,
    source: str,
    window: str | None = None,
    comparison: str | None = None,
    unit: str = "bdt",
    confidence: Confidence = Confidence.MEDIUM,
) -> Evidence:
    return Evidence(
        label=label,
        value=float(round(value, 4)),
        unit=unit,
        source=source,
        window=window,
        comparison=comparison,
        confidence=confidence,
    )


def _clip(value: float) -> float:
    return float(max(0.0, min(100.0, value)))


def _band_for(value: float) -> str:
    for threshold, label in BANDS:
        if value >= threshold:
            return label
    return "starting"


def _band_index(label: str) -> int:
    return BAND_ORDER.index(label) if label in BAND_ORDER else 0


def features_from_context(ctx: UserContext) -> dict[str, float]:
    """Flatten the measured inputs. Nothing else is permitted to feed the score."""
    return {
        "emergency_buffer_months": ctx.feature("emergency_buffer_months") or 0.0,
        "savings_rate": ctx.feature("savings_rate") or 0.0,
        "months_observed": ctx.feature("months_observed") or 0.0,
        "months_negative_surplus": ctx.feature("months_negative_surplus") or 0.0,
        "late_month_share": ctx.feature("late_month_share") or 0.0,
        "late_month_share_max": ctx.feature("late_month_share_max") or 0.0,
        "income_stability": ctx.feature("income_stability") or 0.0,
        "funding_consistency": ctx.feature("funding_consistency") or 0.0,
        "recurring_obligation_ratio": ctx.feature("recurring_obligation_ratio") or 0.0,
        "monthly_expense": ctx.feature("monthly_expense") or 0.0,
        "monthly_income": ctx.feature("monthly_income") or 0.0,
        "monthly_recurring_amount": ctx.feature("monthly_recurring_amount") or 0.0,
        "obligation_count": ctx.feature("obligation_count") or 0.0,
        "digital_ratio": ctx.feature("digital_ratio") or 0.0,
        "cash_dependency": ctx.feature("cash_dependency") or 0.0,
        "account_age_months": ctx.feature("account_age_months") or 0.0,
        "txn_per_month": ctx.feature("txn_per_month") or 0.0,
        "balance_volatility": ctx.feature("balance_volatility") or 0.0,
        "mean_balance": ctx.feature("mean_balance") or 0.0,
    }


def _saving_month_share(ctx: UserContext) -> float:
    """Share of observed months that ended in a surplus."""
    months = int(ctx.feature("months_observed") or 0)
    history = ctx.history(months) if months else ctx.history(3)
    if history.empty:
        return 0.0
    return float((history["savings_rate"].astype(float) > 0).mean())


def _discretionary_share(ctx: UserContext) -> float:
    history = ctx.history(3)
    if history.empty:
        return 0.0
    wants = 0.0
    for category in ("shopping", "entertainment", "other"):
        column = history.get(f"spend_{category}")
        if column is not None:
            wants += float(column.sum())
    total = float(history["spend"].sum())
    return wants / total if total > 0 else 0.0


def score_readiness(
    features: dict[str, float],
    *,
    window: str | None = None,
    saving_month_share: float = 0.0,
    discretionary_share: float = 0.0,
) -> tuple[float, list[ReadinessComponent], list[str]]:
    """Pure function of measured features -> (score, components, blockers).

    Kept pure so :func:`credit_readiness` can re-run it against modified
    features and report a real recalculation for each action.
    """

    def f(key: str) -> float:
        return float(features.get(key, 0.0) or 0.0)

    buffer_months = f("emergency_buffer_months")
    late_share = f("late_month_share")
    late_max = f("late_month_share_max")
    negative_months = f("months_negative_surplus")
    income_stability = f("income_stability")
    funding = f("funding_consistency")
    recurring_ratio = f("recurring_obligation_ratio")
    digital = f("digital_ratio")
    savings_rate = f("savings_rate")
    age_months = f("account_age_months")
    txn_per_month = f("txn_per_month")

    components: list[ReadinessComponent] = []

    # 1. Liquidity -----------------------------------------------------------
    liquidity = _clip(min(buffer_months / 3.0, 1.0) * 100)
    components.append(
        ReadinessComponent(
            key="liquidity",
            label="Money set aside",
            score=round(liquidity, 1),
            weight=WEIGHTS["liquidity"],
            contribution=round(liquidity * WEIGHTS["liquidity"], 2),
            band=_band_for(liquidity),
            detail=(
                f"{buffer_months:.1f} months of essentials held as a buffer. "
                + (
                    "Three months is the usual target."
                    if buffer_months < 3
                    else "This is the strongest single signal here."
                )
            ),
            evidence=[
                _evidence(
                    "emergency_buffer_months",
                    buffer_months,
                    "features.emergency_buffer_months",
                    window=window,
                    comparison="3 months of essentials is the usual target.",
                    unit="months",
                )
            ],
        )
    )

    # 2. Saving consistency --------------------------------------------------
    consistency = _clip(saving_month_share * 70 + min(max(savings_rate, 0.0) / 0.15, 1.0) * 30)
    components.append(
        ReadinessComponent(
            key="saving_consistency",
            label="Saving consistently",
            score=round(consistency, 1),
            weight=WEIGHTS["saving_consistency"],
            contribution=round(consistency * WEIGHTS["saving_consistency"], 2),
            band=_band_for(consistency),
            detail=(
                f"Saving happened in {saving_month_share:.0%} of observed months, "
                f"averaging {savings_rate:.0%} of income."
            ),
            evidence=[
                _evidence(
                    "months_with_surplus_share",
                    saving_month_share,
                    "monthly.savings_rate",
                    window=window,
                    unit="ratio",
                ),
                _evidence(
                    "savings_rate",
                    savings_rate,
                    "monthly.savings_rate",
                    window=window,
                    unit="ratio",
                ),
            ],
        )
    )

    # 3. Payment history -----------------------------------------------------
    payment = _clip((1.0 - min(late_share * 1.6, 1.0)) * 100)
    components.append(
        ReadinessComponent(
            key="payment_history",
            label="Paying on time",
            score=round(payment, 1),
            weight=WEIGHTS["payment_history"],
            contribution=round(payment * WEIGHTS["payment_history"], 2),
            band=_band_for(payment),
            detail=(
                f"Obligations were late in {late_share:.0%} of months"
                + (
                    f", peaking at {late_max:.0%}."
                    if late_max > late_share
                    else "."
                )
            ),
            evidence=[
                _evidence(
                    "late_month_share",
                    late_share,
                    "features.late_month_share",
                    window=window,
                    unit="ratio",
                ),
                _evidence(
                    "late_month_share_max",
                    late_max,
                    "features.late_month_share_max",
                    window=window,
                    unit="ratio",
                ),
            ],
        )
    )

    # 4. Income stability ----------------------------------------------------
    stability = _clip(
        income_stability * 55
        + funding * 25
        + max(0.0, 1.0 - negative_months / 6.0) * 20
    )
    components.append(
        ReadinessComponent(
            key="income_stability",
            label="Steady income",
            score=round(stability, 1),
            weight=WEIGHTS["income_stability"],
            contribution=round(stability * WEIGHTS["income_stability"], 2),
            band=_band_for(stability),
            detail=(
                f"Income stability {income_stability:.0%}, funding consistency "
                f"{funding:.0%}, {negative_months:.0f} deficit months."
            ),
            evidence=[
                _evidence(
                    "income_stability",
                    income_stability,
                    "features.income_stability",
                    window=window,
                    unit="ratio",
                ),
                _evidence(
                    "months_negative_surplus",
                    negative_months,
                    "features.months_negative_surplus",
                    window=window,
                    unit="months",
                ),
            ],
        )
    )

    # 5. Debt service (proxy only) ------------------------------------------
    # Named "existing commitments" rather than debt: this dataset has bills,
    # not loans. Claiming a debt-service ratio from bills would be a fiction.
    commitments = _clip(max(0.0, (0.75 - recurring_ratio) / 0.55) * 100)
    components.append(
        ReadinessComponent(
            key="debt_service",
            label="Existing commitments",
            score=round(commitments, 1),
            weight=WEIGHTS["debt_service"],
            contribution=round(commitments * WEIGHTS["debt_service"], 2),
            band=_band_for(commitments),
            detail=(
                f"{recurring_ratio:.0%} of spending is already committed to "
                f"recurring bills. This is a proxy: there is no loan or debt data "
                f"in this dataset, so no debt-service ratio is claimed."
            ),
            evidence=[
                _evidence(
                    "recurring_obligation_ratio",
                    recurring_ratio,
                    "features.recurring_obligation_ratio",
                    window=window,
                    comparison="Share of spend already committed.",
                    unit="ratio",
                ),
                _evidence(
                    "obligation_count",
                    f("obligation_count"),
                    "recurring_obligations",
                    window=window,
                    unit="count",
                ),
            ],
        )
    )

    # 6. Spending control ----------------------------------------------------
    control = _clip((0.6 - discretionary_share) / 0.5 * 100)
    components.append(
        ReadinessComponent(
            key="spending_control",
            label="Control over spending",
            score=round(control, 1),
            weight=WEIGHTS["spending_control"],
            contribution=round(control * WEIGHTS["spending_control"], 2),
            band=_band_for(control),
            detail=(
                f"{discretionary_share:.0%} of recent spending is on chosen "
                f"rather than necessary items."
            ),
            evidence=[
                _evidence(
                    "discretionary_spend_share",
                    discretionary_share,
                    "monthly.spend_shopping+entertainment+other",
                    window=window,
                    unit="ratio",
                )
            ],
        )
    )

    # 7. Financial footprint -------------------------------------------------
    footprint = _clip(
        min(digital / 0.8, 1.0) * 40
        + min(age_months / 24.0, 1.0) * 35
        + min(txn_per_month / 40.0, 1.0) * 25
    )
    components.append(
        ReadinessComponent(
            key="financial_footprint",
            label="Traceable money",
            score=round(footprint, 1),
            weight=WEIGHTS["financial_footprint"],
            contribution=round(footprint * WEIGHTS["financial_footprint"], 2),
            band=_band_for(footprint),
            detail=(
                f"{digital:.0%} of spending is digital, account is {age_months:.0f} "
                f"months old, {txn_per_month:.0f} transactions a month."
            ),
            evidence=[
                _evidence(
                    "digital_ratio",
                    digital,
                    "features.digital_ratio",
                    window=window,
                    comparison="Untracked cash cannot be evidenced.",
                    unit="ratio",
                ),
                _evidence(
                    "account_age_months",
                    age_months,
                    "features.account_age_months",
                    window=window,
                    unit="months",
                ),
            ],
        )
    )

    overall = sum(c.contribution for c in components)

    blockers: list[str] = []
    if f("months_observed") < MIN_MONTHS:
        blockers.append(BLOCKERS[0][1])
    else:
        if negative_months >= 3:
            blockers.append(BLOCKERS[1][1])
        if late_share >= 0.5:
            blockers.append(BLOCKERS[2][1])

    return overall, components, blockers


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _action_candidates() -> list[dict[str, Any]]:
    """Candidate changes, each expressed as an edit to the measured features."""
    return [
        {
            "key": "add_buffer_month",
            "title": "Add one month of buffer",
            "action": "Move a fixed amount every month into savings until the buffer reaches one month.",
            "reason": "A month of buffer is the smallest amount of money that changes how a bad month feels.",
            "effort": "low",
            "component": "liquidity",
            "mutate": lambda f: {**f, "emergency_buffer_months": f["emergency_buffer_months"] + 1.0},
        },
        {
            "key": "reach_three_month_buffer",
            "title": "Push the buffer toward three months",
            "action": "Increase the monthly transfer until the buffer reaches three months.",
            "reason": "Three months is where a buffer stops being a cushion and starts being resilience.",
            "effort": "medium",
            "component": "liquidity",
            "mutate": lambda f: {**f, "emergency_buffer_months": max(f["emergency_buffer_months"], 3.0)},
        },
        {
            "key": "pay_on_time",
            "title": "Pay obligations on time",
            "action": "Move every recurring payment to a scheduled date before its due day.",
            "reason": "Late payment is the cheapest habit to fix and the most expensive one to keep.",
            "effort": "low",
            "component": "payment_history",
            "mutate": lambda f: {**f, "late_month_share": 0.0, "late_month_share_max": 0.0},
        },
        {
            "key": "trim_wants",
            "title": "Cut chosen spending by 10 points",
            "action": "Reduce discretionary categories by ten percentage points of total spend.",
            "reason": "This is the only lever that creates room without needing more income.",
            "effort": "medium",
            "component": "spending_control",
            "mutate": "trim_wants",
        },
        {
            "key": "smooth_income",
            "title": "Smooth irregular income",
            "action": "Treat the leanest recent month as the baseline and plan from there.",
            "reason": "Planning on a good month is what turns an irregular income into a shortfall.",
            "effort": "medium",
            "component": "income_stability",
            "mutate": lambda f: {
                **f,
                "income_stability": min(f["income_stability"] + 0.2, 1.0),
                "funding_consistency": min(f["funding_consistency"] + 0.1, 1.0),
                "months_negative_surplus": max(0.0, f["months_negative_surplus"] - 1.0),
            },
        },
        {
            "key": "track_cash",
            "title": "Track the cash that is currently untracked",
            "action": "Route the remaining cash spending through a traceable channel.",
            "reason": "Money that is not visible is money that cannot be evidenced to anyone.",
            "effort": "medium",
            "component": "financial_footprint",
            "mutate": lambda f: {**f, "digital_ratio": 1.0, "cash_dependency": 0.0},
        },
        {
            "key": "save_every_month",
            "title": "Save in every month, not the good ones",
            "action": "Set a fixed monthly transfer that happens regardless of the month.",
            "reason": "Surplus-based saving stops working in exactly the months it is needed.",
            "effort": "low",
            "component": "saving_consistency",
            "mutate": lambda f: {**f, "savings_rate": max(f["savings_rate"], 0.05)},
            "also_saving_share": 1.0,
        },
    ]


def credit_readiness(user_id: str) -> CreditReadinessResponse:
    """Explainable readiness view. Not a credit score, not a decision."""
    ctx = get_context(user_id)
    features = features_from_context(ctx)
    saving_share = _saving_month_share(ctx)
    discretionary_share = _discretionary_share(ctx)
    window = ctx.current_period

    overall, components, blockers = score_readiness(
        features,
        window=window,
        saving_month_share=saving_share,
        discretionary_share=discretionary_share,
    )

    band = _band_for(overall)
    if blockers:
        # A blocker caps rather than rejects, so the customer can see the way
        # out. An unconditional "not eligible" is the kind of dead end this
        # product exists to avoid.
        cap_index = _band_index("early")
        if _band_index(band) > cap_index:
            band = "early"

    # -- actions, each projected by re-running the same scorer ---------------
    actions: list[ReadinessAction] = []
    for candidate in _action_candidates():
        mutate = candidate["mutate"]
        if mutate == "trim_wants":
            trimmed = max(0.0, discretionary_share - 0.10)
            projected, _, projected_blockers = score_readiness(
                features,
                window=window,
                saving_month_share=saving_share,
                discretionary_share=trimmed,
            )
        else:
            trial = mutate(features)
            projected, _, projected_blockers = score_readiness(
                trial,
                window=window,
                saving_month_share=float(candidate.get("also_saving_share", saving_share)),
                discretionary_share=discretionary_share,
            )
        if projected <= overall + 0.05:
            # No gain, so do not offer it as a step. Listing an action that
            # moves nothing is how a plan starts looking padded.
            continue
        actions.append(
            ReadinessAction(
                key=candidate["key"],
                title=candidate["title"],
                action=candidate["action"],
                reason=candidate["reason"],
                effort=candidate["effort"],
                component=candidate["component"],
                monthly_bdt=None,
                projected_overall=round(projected, 1),
                projected_band=_band_for(projected),
                evidence=[
                    _evidence(
                        "projected_overall",
                        projected,
                        "score_readiness (recalculated on modified features)",
                        window=window,
                        comparison=f"Current readiness {overall:.1f}.",
                        unit="score",
                    )
                ],
            )
        )
    actions.sort(key=lambda a: (a.projected_overall or 0.0), reverse=True)

    # -- monthly cost of the top action, in real money ----------------------
    for action in actions:
        if action.component == "liquidity":
            essentials = float(features["monthly_expense"]) * 0.6
            current_buffer = float(features["mean_balance"])
            months_needed = max(0.0, min(3.0, 3.0 - features["emergency_buffer_months"]))
            if months_needed > 0 and essentials > 0:
                action.monthly_bdt = round(max(essentials - current_buffer, 0.0) / months_needed, 2)

    # -- timeline ------------------------------------------------------------
    capacity = float(ctx.feature("monthly_surplus") or 0.0)
    timeline: list[dict] = []
    months_to_next: float | None = None
    current_index = _band_index(band)
    per_month = 0.0
    if current_index < len(BAND_ORDER) - 1:
        next_band = BAND_ORDER[current_index + 1]
        threshold = next(th for th, lbl in BANDS if lbl == next_band)
        gap = max(threshold - overall, 0.0)
        if capacity > 0:
            # Points of readiness per month, measured the honest way: take the
            # top action's gain and assume it accrues at the observed saving
            # rate. Not a promise, an extrapolation labelled as such.
            best = actions[0].projected_overall if actions and actions[0].projected_overall else overall
            per_month = max((best - overall), 0.0) / 6.0
            months_to_next = round(gap / per_month, 1) if per_month > 0 else None
        timeline = [
            {
                "month": 0,
                "overall": round(overall, 1),
                "band": band,
                "note": "Today.",
            }
        ]
        for month in (3, 6, 12):
            projected = overall + per_month * month if capacity > 0 else overall
            timeline.append(
                {
                    "month": month,
                    "overall": round(min(projected, 100.0), 1),
                    "band": _band_for(min(projected, 100.0)),
                    "note": (
                        "If the top action stays in place."
                        if capacity > 0
                        else "No monthly surplus observed, so no trajectory is claimed."
                    ),
                }
            )

    strengths = [c.label for c in components if c.band in ("ready", "almost")]
    attention = [c.label for c in components if c.band in ("starting", "early")]

    score = ReadinessOverall(
        value=round(overall, 1),
        label=band,
        band_index=current_index,
        strengths=strengths,
        attention_areas=attention,
        disclaimer=(
            "This is not a credit score and not a credit decision. upay does not "
            "lend, and nothing here approves, denies or prices any credit. It is "
            "a readiness view built from your own transaction patterns, and it "
            "ignores age, occupation, location and name entirely."
        ),
        confidence=Confidence.MEDIUM if features["months_observed"] >= 6 else Confidence.LOW,
    )

    insights: list[Insight] = []
    if blockers:
        insights.append(
            Insight(
                key="readiness_blocker",
                title=blockers[0],
                observation=(
                    "One or more signals cap readiness at 'early' regardless of the "
                    "overall score."
                ),
                why="These are the signals that turn into rejections later, so they are worth fixing first.",
                action=(
                    actions[0].action if actions else "Ask the assistant which signal to fix first."
                ),
                severity=Severity.WARNING,
                evidence=[
                    _evidence(
                        "months_negative_surplus",
                        features["months_negative_surplus"],
                        "features.months_negative_surplus",
                        window=window,
                        unit="months",
                    ),
                    _evidence(
                        "late_month_share",
                        features["late_month_share"],
                        "features.late_month_share",
                        window=window,
                        unit="ratio",
                    ),
                ],
            )
        )
    elif actions:
        top = actions[0]
        insights.append(
            Insight(
                key="readiness_top_action",
                title=top.title,
                observation=(
                    f"Recalculating readiness with this one change in place gives "
                    f"{top.projected_overall:.0f} instead of {overall:.0f}."
                ),
                why=top.reason,
                action=top.action,
                severity=Severity.ATTENTION,
                impact_bdt=top.monthly_bdt,
                evidence=top.evidence,
            )
        )

    detail = [
        f"Readiness {overall:.0f}/100, band '{band}', from "
        f"{features['months_observed']:.0f} months of your own transactions.",
        "No credit bureau data, loan history or debt balances exist in this dataset, "
        "so no credit score, repayment capacity or loan amount is estimated.",
        "Age, occupation, location and name are not inputs to any component.",
    ]
    if blockers:
        detail.append("Capped by: " + "; ".join(blockers) + ".")
    elif actions:
        detail.append(f"Highest-value step: {actions[0].title}.")

    return CreditReadinessResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        overall=score,
        components=components,
        actions=actions,
        blockers=blockers,
        months_to_next_band=months_to_next,
        timeline=timeline,
        disclaimer=score.disclaimer or "",
        excluded_attributes=list(EXCLUDED_ATTRIBUTES),
        explanation=Explanation(
            headline=(
                f"Readiness {overall:.0f}/100 ({band.replace('_', ' ')})."
                + (f" Capped by {len(blockers)} signal(s)." if blockers else "")
            ),
            detail=detail,
        ),
        evidence=[e for c in components for e in c.evidence],
        assumptions=[
            Assumption(
                key="buffer_target_months",
                value=3.0,
                rationale=(
                    "Three months of essentials is the conventional full buffer, "
                    "used only to scale the liquidity score."
                ),
            ),
            Assumption(
                key="component_weights",
                value=1.0,
                rationale=(
                    "Weights are a deliberate editorial choice, published here so "
                    "they can be argued with rather than hidden."
                ),
                configurable=False,
            ),
        ],
        metrics=[
            Metric(
                key="readiness_score",
                label="Readiness",
                value=round(overall, 1),
                unit="score",
                direction=Direction.FLAT,
                confidence=score.confidence,
                comparison="Not a credit score.",
            ),
            Metric(
                key="blocking_signals",
                label="Capping signals",
                value=float(len(blockers)),
                unit="count",
                previous_value=float(len(blockers)),
                direction=Direction.FLAT,
            ),
        ],
        insights=insights,
    )


__all__ = ["credit_readiness", "score_readiness", "features_from_context", "EXCLUDED_ATTRIBUTES"]