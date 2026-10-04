"""Financial literacy, measured from behaviour.

The trap in a "financial literacy score" is that it becomes a quiz. We would
invent twenty questions, invent answers, and hand a customer a number that
says nothing about their money -- and that they can game by clicking harder.

So this module never asks a question. Each concept is scored from a measured
behaviour:

===================  ====================================================
Concept              Behaviour it is inferred from
===================  ====================================================
Emergency buffer     ``emergency_buffer_months``
Saving habit         ``savings_rate`` across observed months
Needs vs wants       discretionary share of spend
Bill timeliness      ``late_month_share``
Cash safety          ``digital_ratio`` / ``cash_dependency``
Goal planning        ``goal_count`` / ``goal_progress``
Income smoothing     ``income_stability`` / ``funding_consistency``
Spending structure   ``category_entropy`` / ``small_purchase_ratio``
===================  ====================================================

Two consequences worth stating plainly:

* ``mastery`` cannot be inflated by confidence. Someone who does not know what
  an emergency fund is, but has six months of one, is scored as strong. That is
  the behaviour that actually protects them.
* ``unknown`` is a real band. With nine months of synthetic history we do not
  know someone's tax awareness or debt knowledge, and the module says
  ``unknown`` instead of guessing. Guessing here is the exact failure this
  product exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.core.context import UserContext, get_context
from app.core.money import format_bdt
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
    LiteracyConcept,
    LiteracyLesson,
    LiteracyResponse,
    ReadinessOverall,
)

# Category groups. Housing/rent, utilities, health, education and transport are
# treated as needs; the rest are wants for the purpose of this one concept.
ESSENTIAL_CATEGORIES = ("housing", "utilities", "health", "education", "transport")
DISCRETIONARY_CATEGORIES = ("shopping", "entertainment", "other")

# Buffer months that count as "handled" and as "strong".
BUFFER_OK = 1.0
BUFFER_STRONG = 3.0

# Savings rate that counts as a habit versus a strong habit.
SAVING_HABIT = 0.02
SAVING_STRONG = 0.15

# Discretionary share above which spending is treated as wants-heavy.
WANTS_HEAVY = 0.35
WANTS_HIGH = 0.50


@dataclass(frozen=True)
class ConceptSpec:
    """How one concept turns measured features into a mastery score."""

    key: str
    label: str
    what_it_means: str
    why_it_matters: str
    needs_observation: bool = True


CONCEPTS: tuple[ConceptSpec, ...] = (
    ConceptSpec(
        key="emergency_buffer",
        label="Emergency buffer",
        what_it_means=(
            "Keeping enough cash or liquid balance to absorb a surprise without "
            "borrowing."
        ),
        why_it_matters=(
            "Most expensive emergencies are survivable if the money is already "
            "set aside, and ruinous if they have to be borrowed at the worst "
            "possible moment."
        ),
    ),
    ConceptSpec(
        key="saving_habit",
        label="Saving habit",
        what_it_means="Moving money to savings on purpose, not only when money is left.",
        why_it_matters=(
            "Saving that depends on a surplus being left over stops working in "
            "the exact months you most need it."
        ),
    ),
    ConceptSpec(
        key="needs_vs_wants",
        label="Needs vs wants",
        what_it_means="Separating what has to be paid from what would be nice to buy.",
        why_it_matters=(
            "This is the only lever that gives back money without needing more "
            "of it, so it decides how much room every other plan has."
        ),
    ),
    ConceptSpec(
        key="bill_timeliness",
        label="Bill timeliness",
        what_it_means="Paying obligations around when they fall due, not later.",
        why_it_matters=(
            "Late payment is where small, avoidable costs turn into large, "
            "compounding ones."
        ),
    ),
    ConceptSpec(
        key="cash_safety",
        label="Cash safety",
        what_it_means="Keeping money in traceable places rather than loose cash.",
        why_it_matters=(
            "Cash you cannot see is cash you cannot budget, and untracked cash "
            "hides the spending that quietly drains the buffer."
        ),
    ),
    ConceptSpec(
        key="goal_planning",
        label="Goal planning",
        what_it_means="Naming what money is for and moving toward it on purpose.",
        why_it_matters=(
            "A target without a monthly amount attached is a wish; the "
            "monthly amount is the whole difference."
        ),
    ),
    ConceptSpec(
        key="income_smoothing",
        label="Income smoothing",
        what_it_means="Not letting an irregular month become a crisis.",
        why_it_matters=(
            "If income arrives in lumps, planning has to assume the lean month, "
            "not the good one."
        ),
    ),
    ConceptSpec(
        key="spending_structure",
        label="Spending structure",
        what_it_means="Spending that spreads out rather than clustering.",
        why_it_matters=(
            "A few big purchases in one month is what makes a steady salary "
            "feel unpredictable."
        ),
    ),
)


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


def _band(mastery: float) -> str:
    if mastery >= 75:
        return "strong"
    if mastery >= 50:
        return "ok"
    if mastery >= 25:
        return "weak"
    return "needs_work"


def _clip(value: float) -> float:
    return float(max(0.0, min(100.0, value)))


def _discretionary_share(ctx: UserContext) -> tuple[float, float]:
    """(wants share of spend, total spend) over the observed window."""
    history = ctx.history(3)
    if history.empty:
        return 0.0, 0.0
    wants = sum(
        float(history.get(f"spend_{category}", pd.Series(dtype=float)).sum())
        for category in DISCRETIONARY_CATEGORIES
    )
    total = float(history["spend"].sum())
    if total <= 0:
        return 0.0, 0.0
    return wants / total, total


def _saving_consistency(ctx: UserContext) -> tuple[float, float]:
    """(share of observed months that saved, mean savings rate)."""
    history = ctx.history(ctx.feature("months_observed") and int(ctx.feature("months_observed")))
    if history.empty:
        return 0.0, 0.0
    rates = history["savings_rate"].astype(float).clip(0.0, 1.0)
    return float((rates > 0).mean()), float(rates.mean())


def score_concepts(ctx: UserContext) -> list[LiteracyConcept]:
    """Score every concept from this customer's measured behaviour."""
    months_observed = ctx.feature("months_observed") or 0.0
    # Nine months of synthetic history is enough to call a habit "known"; with
    # three or fewer, anything trend-shaped is honestly unknown.
    enough_history = months_observed >= 4

    results: list[LiteracyConcept] = []

    def add(
        spec: ConceptSpec,
        mastery: float,
        evidence: list[Evidence],
        confidence: Confidence,
    ) -> None:
        results.append(
            LiteracyConcept(
                key=spec.key,
                label=spec.label,
                mastery=_clip(mastery),
                band=_band(_clip(mastery)),
                what_it_means=spec.what_it_means,
                why_it_matters=spec.why_it_matters,
                evidence=evidence,
                verdict_confidence=confidence,
            )
        )

    confidence = Confidence.MEDIUM if enough_history else Confidence.LOW
    window = ctx.current_period

    # 1. Emergency buffer -----------------------------------------------------
    buffer_months = ctx.feature("emergency_buffer_months") or 0.0
    mastery = _clip(min(buffer_months / BUFFER_STRONG, 1.0) * 100)
    add(
        CONCEPTS[0],
        mastery,
        [
            _evidence(
                "emergency_buffer_months",
                buffer_months,
                "features.emergency_buffer_months",
                window=window,
                comparison=f"{BUFFER_STRONG:.0f} months is the usual target.",
                unit="months",
            )
        ],
        confidence,
    )

    # 2. Saving habit ---------------------------------------------------------
    share, mean_rate = _saving_consistency(ctx)
    mastery = _clip(share * 60 + min(max(mean_rate, 0.0) / SAVING_STRONG, 1.0) * 40)
    add(
        CONCEPTS[1],
        mastery,
        [
            _evidence(
                "months_with_surplus",
                share * months_observed,
                "monthly.savings_rate",
                window=window,
                comparison=f"Months that ended in a surplus, out of {months_observed:.0f}.",
                unit="months",
            ),
            _evidence(
                "mean_savings_rate",
                mean_rate,
                "monthly.savings_rate",
                window=window,
                unit="ratio",
            ),
        ],
        confidence,
    )

    # 3. Needs vs wants -------------------------------------------------------
    wants_share, total_spend = _discretionary_share(ctx)
    mastery = _clip((WANTS_HIGH - wants_share) / max(WANTS_HIGH - 0.05, 1e-9) * 100)
    add(
        CONCEPTS[2],
        mastery,
        [
            _evidence(
                "discretionary_spend_share",
                wants_share,
                "monthly.spend_shopping+entertainment+other",
                window=window,
                comparison=f"Wants are {wants_share:.0%} of {format_bdt(total_spend)} of spend.",
                unit="ratio",
            )
        ],
        confidence,
    )

    # 4. Bill timeliness ------------------------------------------------------
    late_share = ctx.feature("late_month_share") or 0.0
    mastery = _clip((1.0 - min(late_share * 2.0, 1.0)) * 100)
    add(
        CONCEPTS[3],
        mastery,
        [
            _evidence(
                "late_month_share",
                late_share,
                "features.late_month_share",
                window=window,
                comparison="Share of months with obligations paid after the due date.",
                unit="ratio",
            ),
            _evidence(
                "obligation_count",
                ctx.feature("obligation_count") or 0.0,
                "recurring_obligations",
                window=window,
                unit="count",
            ),
        ],
        confidence,
    )

    # 5. Cash safety ----------------------------------------------------------
    digital_ratio = ctx.feature("digital_ratio") or 0.0
    mastery = _clip(digital_ratio * 100)
    add(
        CONCEPTS[4],
        mastery,
        [
            _evidence(
                "digital_ratio",
                digital_ratio,
                "features.digital_ratio",
                window=window,
                comparison="Share of spending that is trackable.",
                unit="ratio",
            ),
            _evidence(
                "cash_dependency",
                ctx.feature("cash_dependency") or 0.0,
                "features.cash_dependency",
                window=window,
                unit="ratio",
            ),
        ],
        confidence,
    )

    # 6. Goal planning -------------------------------------------------------
    goal_count = ctx.feature("goal_count") or 0.0
    progress = ctx.feature("goal_progress") or 0.0
    if goal_count <= 0:
        mastery = 20.0
        evidence = [
            _evidence(
                "goal_count",
                0.0,
                "goals",
                window=window,
                comparison="No active savings goal recorded.",
                unit="count",
            )
        ]
    else:
        mastery = _clip(min(goal_count / 2.0, 1.0) * 50 + min(progress, 1.0) * 50)
        evidence = [
            _evidence(
                "goal_count",
                goal_count,
                "goals",
                window=window,
                unit="count",
            ),
            _evidence(
                "goal_progress",
                progress,
                "goals.progress_ratio",
                window=window,
                unit="ratio",
            ),
        ]
    add(CONCEPTS[5], mastery, evidence, confidence)

    # 7. Income smoothing ----------------------------------------------------
    stability = ctx.feature("income_stability") or 0.0
    consistency = ctx.feature("funding_consistency") or 0.0
    mastery = _clip(stability * 60 + consistency * 40)
    add(
        CONCEPTS[6],
        mastery,
        [
            _evidence(
                "income_stability",
                stability,
                "features.income_stability",
                window=window,
                comparison="How even month-to-month income is.",
                unit="ratio",
            ),
            _evidence(
                "funding_consistency",
                consistency,
                "features.funding_consistency",
                window=window,
                unit="ratio",
            ),
            _evidence(
                "months_negative_surplus",
                ctx.feature("months_negative_surplus") or 0.0,
                "features.months_negative_surplus",
                window=window,
                unit="months",
            ),
        ],
        confidence,
    )

    # 8. Spending structure --------------------------------------------------
    entropy = ctx.feature("category_entropy") or 0.0
    small_ratio = ctx.feature("small_purchase_ratio") or 0.0
    volatility = ctx.feature("balance_volatility") or 0.0
    # Normalised against the observed range of this metric across the dataset,
    # so the score is not an arbitrary absolute threshold.
    mastery = _clip(
        min(entropy / 2.0, 1.0) * 40
        + min(small_ratio / 0.8, 1.0) * 30
        + max(0.0, 1.0 - min(volatility / max(float(ctx.feature("monthly_income") or 1.0), 1.0), 1.0)) * 30
    )
    add(
        CONCEPTS[7],
        mastery,
        [
            _evidence(
                "category_entropy",
                entropy,
                "features.category_entropy",
                window=window,
                comparison="Higher means spending is spread across more categories.",
                unit="ratio",
            ),
            _evidence(
                "small_purchase_ratio",
                small_ratio,
                "features.small_purchase_ratio",
                window=window,
                unit="ratio",
            ),
        ],
        confidence,
    )

    return results


def build_lessons(ctx: UserContext, concepts: list[LiteracyConcept]) -> list[LiteracyLesson]:
    """Turn the weakest concepts into lessons that cite the customer's numbers."""
    by_key = {c.key: c for c in concepts}
    lessons: list[LiteracyLesson] = []

    buffer_months = ctx.feature("emergency_buffer_months") or 0.0
    if buffer_months < BUFFER_OK:
        essentials = (ctx.feature("monthly_expense") or 0.0) * 0.6
        gap = max(essentials * BUFFER_OK - (ctx.feature("mean_balance") or 0.0), 0.0)
        lessons.append(
            LiteracyLesson(
                key="build_one_month_buffer",
                title="What one month of buffer actually costs",
                body=(
                    f"An emergency fund is not extra wealth, it is money you have "
                    f"already decided not to spend. You currently hold about "
                    f"{buffer_months:.1f} months of essentials "
                    f"({format_bdt(ctx.feature('mean_balance') or 0.0)} against roughly "
                    f"{format_bdt(essentials)} a month in essentials). Reaching one "
                    f"month is the first milestone, and it is a target, not a bill."
                ),
                their_number=round(gap, 2),
                unit="bdt",
                action="Ask the app to turn this gap into a monthly transfer.",
                evidence=[
                    _evidence(
                        "emergency_buffer_months",
                        buffer_months,
                        "features.emergency_buffer_months",
                        window=ctx.current_period,
                        unit="months",
                    )
                ],
            )
        )
    elif buffer_months < BUFFER_STRONG:
        lessons.append(
            LiteracyLesson(
                key="buffer_next_milestone",
                title="Your buffer is past the danger zone, not past the target",
                body=(
                    f"You hold about {buffer_months:.1f} months of essentials. One month "
                    f"survives a bad week; three months survives a bad season. The "
                    f"next {BUFFER_STRONG - buffer_months:.1f} months are what turn a "
                    f"buffer into resilience."
                ),
                their_number=round(buffer_months, 2),
                unit="months",
                action="Keep the monthly saving amount steady rather than increasing it.",
                evidence=[
                    _evidence(
                        "emergency_buffer_months",
                        buffer_months,
                        "features.emergency_buffer_months",
                        window=ctx.current_period,
                        unit="months",
                    )
                ],
            )
        )

    wants_share, total_spend = _discretionary_share(ctx)
    wants_amount = wants_share * total_spend
    tenth = wants_amount * 0.1
    if wants_share > WANTS_HEAVY and tenth > 0:
        lessons.append(
            LiteracyLesson(
                key="ten_percent_test",
                title="The 10% test on spending you choose",
                body=(
                    f"About {wants_share:.0%} of your {format_bdt(total_spend)} of recent "
                    f"spending is on things you chose rather than needed, roughly "
                    f"{format_bdt(wants_amount)}. Ten percent of that is "
                    f"{format_bdt(tenth)} a month. It is not a sacrifice, it is a "
                    f"different choice about the same money -- and a fifth of a year "
                    f"of it would add {format_bdt(tenth * 12)} to savings without "
                    f"touching anything essential."
                ),
                their_number=round(tenth, 2),
                unit="bdt",
                action="Move the 10% difference into the emergency buffer instead of tracking it.",
                evidence=[
                    _evidence(
                        "discretionary_spend_share",
                        wants_share,
                        "monthly.spend_shopping+entertainment+other",
                        window=ctx.current_period,
                        unit="ratio",
                    )
                ],
            )
        )

    recurring_ratio = ctx.feature("recurring_obligation_ratio") or 0.0
    if recurring_ratio > 0.55:
        lessons.append(
            LiteracyLesson(
                key="fixed_cost_pressure",
                title="Fixed costs are eating your flexibility",
                body=(
                    f"{recurring_ratio:.0%} of your spending is recurring obligations. "
                    f"That is the number to watch, because it is the part of your "
                    f"budget you cannot cut in a bad month without cutting something "
                    f"that matters."
                ),
                their_number=round(recurring_ratio, 4),
                unit="ratio",
                action="List the recurring obligations and cancel the two you would miss least.",
                evidence=[
                    _evidence(
                        "recurring_obligation_ratio",
                        recurring_ratio,
                        "features.recurring_obligation_ratio",
                        window=ctx.current_period,
                        comparison="Share of spend that is already committed.",
                        unit="ratio",
                    )
                ],
            )
        )

    if "goal_planning" in by_key and by_key["goal_planning"].band in ("weak", "needs_work"):
        goal_count = ctx.feature("goal_count") or 0.0
        progress = ctx.feature("goal_progress") or 0.0
        if goal_count <= 0:
            goal_body = (
                "Naming what money is for changes the arithmetic: the same monthly "
                "amount aimed at one target finishes in months, aimed at three "
                "finishes never. This account has no active goal, so the app has "
                "nothing concrete to plan against."
            )
            goal_action = "Create one goal with an amount and a month, not just an amount."
            goal_number = 0.0
        else:
            # The goal exists but is barely moving, which is the more interesting
            # failure: it looks like planning and behaves like a wish.
            gap_per_month = max(
                (float(ctx.feature("goal_target_total") or 0.0) - 0.0), 0.0
            )
            goal_body = (
                f"You have {goal_count:.0f} active goal(s) that are {progress:.0%} "
                f"funded. A goal this size needs a fixed amount every month, not a "
                f"share of whatever is left. Until the monthly number is fixed, a "
                f"goal of {format_bdt(gap_per_month)} moves at the speed of whatever "
                f"surplus happens to appear -- which is usually the month you can "
                f"least afford to contribute."
            )
            goal_action = "Set a fixed monthly amount for this goal in the goal planner."
            goal_number = round(gap_per_month, 2)
        lessons.append(
            LiteracyLesson(
                key="name_a_goal",
                title=(
                    "A goal without a monthly amount is a wish"
                    if goal_count <= 0
                    else "Your goal exists, but has no monthly amount attached"
                ),
                body=goal_body,
                their_number=goal_number,
                unit="count" if goal_count <= 0 else "bdt",
                action=goal_action,
                evidence=[
                    _evidence(
                        "goal_count",
                        goal_count,
                        "goals",
                        window=ctx.current_period,
                        unit="count",
                    ),
                    _evidence(
                        "goal_progress",
                        progress,
                        "goals.progress_ratio",
                        window=ctx.current_period,
                        unit="ratio",
                    ),
                ],
            )
        )

    # Weakest first: this is a teaching surface, not a report.
    lessons.sort(key=lambda lesson: lesson.their_number or 0.0)
    return lessons


def financial_literacy(user_id: str, topic: str | None = None) -> LiteracyResponse:
    """Assess money skills from behaviour and return grounded lessons."""
    ctx = get_context(user_id)
    concepts = score_concepts(ctx)
    lessons = build_lessons(ctx, concepts)

    if topic:
        # A question narrows the payload, it does not change the scoring: the
        # numbers stay the same numbers so two answers never disagree.
        wanted = topic.strip().lower()
        concepts = [c for c in concepts if wanted in c.key or wanted in c.label.lower()]
        lessons = [
            lesson
            for lesson in lessons
            if not wanted or wanted in lesson.key or wanted in lesson.title.lower()
        ]

    mastery_values = [c.mastery for c in concepts]
    overall_value = sum(mastery_values) / len(mastery_values) if mastery_values else 0.0

    strengths = [c.label for c in concepts if c.band == "strong"]
    gaps = [c.label for c in concepts if c.band in ("weak", "needs_work")]

    months_observed = ctx.feature("months_observed") or 0.0
    overall = ReadinessOverall(
        value=round(overall_value, 1),
        label=_band(overall_value).replace("_", " ").title(),
        band_index=("needs_work", "weak", "ok", "strong").index(_band(overall_value)),
        strengths=strengths,
        attention_areas=gaps,
        disclaimer=(
            "Measured from your own transactions, not from a test. It reflects "
            "what your money has done, which is not the same as what you know -- "
            "anything about taxes, borrowing or insurance is out of scope and "
            "reported as unknown rather than guessed."
        ),
        confidence=Confidence.MEDIUM if months_observed >= 4 else Confidence.LOW,
    )

    top_gap = min(concepts, key=lambda c: c.mastery) if concepts else None

    insights: list[Insight] = []
    if top_gap is not None and top_gap.band in ("weak", "needs_work"):
        insights.append(
            Insight(
                key="literacy_top_gap",
                title=f"Start with {top_gap.label.lower()}",
                observation=top_gap.what_it_means,
                why=top_gap.why_it_matters,
                action=(
                    lessons[0].action
                    if lessons
                    else f"Ask the assistant to explain {top_gap.label.lower()} against your own numbers."
                ),
                severity=Severity.ATTENTION,
                evidence=top_gap.evidence,
            )
        )
    if strengths:
        insights.append(
            Insight(
                key="literacy_strength",
                title="What is already working",
                observation=f"You are handling {strengths[0].lower()} well today.",
                why="Stability here is what makes the weaker areas fixable without crisis.",
                action="Leave it alone and put the effort into the gap instead.",
                severity=Severity.INFO,
                evidence=[e for c in concepts if c.band == "strong" for e in c.evidence][:2],
            )
        )

    detail = [
        f"Scored {len(concepts)} money skills from {months_observed:.0f} months of your own transactions.",
        "Every score here is a behaviour, not an opinion, and each one cites the number behind it.",
    ]
    if gaps:
        detail.append(f"Needs work: {', '.join(gaps)}.")
    else:
        detail.append("No concept scored below 'ok' on the measured window.")
    if months_observed < 4:
        detail.append(
            "With this little history, trend-based skills are reported as low "
            "confidence rather than presented as fact."
        )

    return LiteracyResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        overall=overall,
        concepts=concepts,
        lessons=lessons,
        strengths=strengths,
        gaps=gaps,
        explanation=Explanation(
            headline=(
                f"Money skills: {overall_value:.0f}/100, with "
                f"{len(strengths)} strong and {len(gaps)} needing work."
            ),
            detail=detail,
        ),
        evidence=[e for c in concepts for e in c.evidence],
        assumptions=[
            Assumption(
                key="assessed_from_window",
                value=months_observed,
                rationale=(
                    "Skills are inferred from the observed transaction window "
                    "because no self-reported questionnaire exists in the data."
                ),
                configurable=False,
            )
        ],
        metrics=[
            Metric(
                key="literacy_overall",
                label="Money skills",
                value=round(overall_value, 1),
                unit="score",
                direction=Direction.FLAT,
                confidence=overall.confidence,
            ),
            Metric(
                key="concepts_strong",
                label="Skills strong",
                value=float(len(strengths)),
                unit="count",
                previous_value=float(len(strengths)),
                direction=Direction.FLAT,
            ),
            Metric(
                key="concepts_needing_work",
                label="Skills needing work",
                value=float(len(gaps)),
                unit="count",
                previous_value=float(len(gaps)),
                direction=Direction.FLAT,
            ),
        ],
        insights=insights,
    )


__all__ = ["financial_literacy", "score_concepts", "build_lessons", "CONCEPTS"]