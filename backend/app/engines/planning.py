"""Goal planning, savings optimisation and the what-if simulator.

Design rule for everything in this module
-----------------------------------------
**No arithmetic is estimated, and no arithmetic is done by a language model.**

Two functions carry the whole planning product:

* :func:`disposable_capacity` -- how much a month of income is genuinely free
  after essential spending and after keeping the balance above its buffer.
  Every plan in this module is capped by it, which is what makes
  ``feasible=False`` a meaningful word rather than a disclaimer.
* :func:`simulate_path` -- one shared day-by-day engine, reused by the goal
  planner, the emergency-fund planner, the multi-goal conflict optimiser and
  the what-if endpoint. They differ only in what they vary, so they cannot
  disagree about how money moves.

The optimiser is deliberately deterministic. A goal plan is a promise about the
customer's own money; making it reproducible means the same question asked
twice gives the same answer, and the trade-offs can be argued about instead of
re-rolled.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.context import UserContext, get_context
from app.core.money import format_bdt
from app.core.periods import month_start, months_between, shift_month
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
from app.schemas.planning import (
    EmergencyFundResponse,
    GoalConflictPlan,
    GoalConflictResponse,
    GoalPlan,
    GoalPlanResponse,
    GoalStatus,
    GoalStatusResponse,
    SimulationResponse,
    SimulationScenario,
)

# Monthly amount treated as already committed to goals by past behaviour.
HISTORY_CONTRIBUTION_FALLBACK = 0.0

# Fraction of capacity a "conservative" plan deliberately leaves unused.
CONSERVATIVE_UTILISATION = 0.75

# Fraction of capacity an "aggressive" plan is allowed to reach. Never above 1:
# a plan that allocates more than the capacity exists is not ambitious, it is
# wrong.
MAX_UTILISATION = 1.0

PLAN_LABELS = {
    "conservative": "Conservative",
    "balanced": "Balanced",
    "aggressive": "Aggressive",
}


def _evidence(
    label: str,
    value: float,
    source: str,
    window: str | None = None,
    comparison: str | None = None,
    confidence: Confidence = Confidence.MEDIUM,
    unit: str = "bdt",
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


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------

def disposable_capacity(ctx: UserContext) -> dict[str, Any]:
    """How much of a month is genuinely available to allocate.

    Deliberately conservative, and the order matters:

    1. take the customer's own recent average income (not a forecast level, so
       the capacity does not inherit forecast error),
    2. subtract recent average spending,
    3. subtract what they already contribute to goals,
    4. keep back whatever is needed for the balance to stay above its buffer
       next month.

    Steps 1-3 are observations. Step 4 is a choice and is reported as such.
    """
    history = ctx.history(3)
    if history.empty:
        raise ValueError(f"No monthly history available for {ctx.user_id}")

    income = float(history["income"].mean())
    spend = float(history["spend"].mean())
    recurring = float(ctx.feature("monthly_recurring_amount") or 0.0)
    existing_contribution = float(history["goal_contribution"].mean())
    if existing_contribution <= 0:
        existing_contribution = HISTORY_CONTRIBUTION_FALLBACK

    surplus = income - spend
    buffer_target, buffer_basis = _buffer_for(ctx, spend)

    current_balance = float(ctx.daily["balance"].iloc[-1]) if not ctx.daily.empty else 0.0
    # What the buffer costs the customer over one month is simply the floor
    # itself, not a rate: if they already sit above it, it constrains nothing.
    buffer_cost = max(buffer_target - current_balance, 0.0)

    capacity = max(surplus - existing_contribution - buffer_cost, 0.0)
    capacity = min(capacity, surplus)  # never allocate more than the surplus

    volatility = float(history["spend"].std(ddof=0) / max(spend, 1e-9)) if len(history) > 1 else 0.0
    confidence = Confidence.HIGH if len(history) >= 4 else Confidence.MEDIUM

    return {
        "monthly_income": income,
        "monthly_spend": spend,
        "monthly_surplus": surplus,
        "monthly_recurring": recurring,
        "existing_contribution": existing_contribution,
        "buffer_target": buffer_target,
        "buffer_basis": buffer_basis,
        "buffer_cost": buffer_cost,
        "current_balance": current_balance,
        "capacity": float(capacity),
        "spend_cv": volatility,
        "months_used": int(len(history)),
        "confidence": confidence,
    }


def _buffer_for(ctx: UserContext, monthly_expense: float) -> tuple[float, str]:
    flat = float(settings.minimum_balance_buffer)
    scaled = float(settings.buffer_floor_months) * float(monthly_expense)
    if flat >= scaled:
        return flat, "flat floor"
    return scaled, f"{settings.buffer_floor_months:g} months of own spending"


def _months_forward(ctx: UserContext, months: float) -> str:
    return shift_month(ctx.current_period, max(int(math.ceil(months)), 0))


# ---------------------------------------------------------------------------
# One shared path engine
# ---------------------------------------------------------------------------

def simulate_path(
    ctx: UserContext,
    months: int,
    monthly_income: float,
    monthly_spend: float,
    monthly_goal_contribution: float,
    buffer_target: float,
    start_balance: float | None = None,
    one_off_expense: float = 0.0,
    one_off_month_index: int = 0,
) -> pd.DataFrame:
    """Day-by-day balance for ``months`` months under fixed monthly amounts.

    Timing inside a month uses the same deterministic rules as the forecast
    engine -- bills on contractual due days, income on the observed payday, the
    rest spread by the customer's own day-of-month profile -- so a simulated
    path and a forecast path are comparable line for line.
    """
    from app.ml.forecast import allocate_daily_path, recurring_schedule_for_month

    balance = (
        start_balance
        if start_balance is not None
        else (float(ctx.daily["balance"].iloc[-1]) if not ctx.daily.empty else 0.0)
    )
    spend_profile = np.asarray(ctx.spend_profile_by_day(), dtype=float)
    income_profile = np.asarray(ctx.income_profile_by_day(), dtype=float)

    rows: list[dict[str, Any]] = []
    for offset in range(months):
        period = shift_month(ctx.current_period, offset + 1)
        year, month = (int(p) for p in period.split("-"))
        recurring_by_day = recurring_schedule_for_month(ctx.recurring, ctx.user_id, year, month)
        import calendar

        days = calendar.monthrange(year, month)[1]
        path = allocate_daily_path(
            spend_level=monthly_spend,
            income_level=monthly_income,
            days_in_month=days,
            days_in_month_dates=list(range(1, days + 1)),
            spend_profile=spend_profile,
            income_profile=income_profile,
            recurring_schedule=recurring_by_day,
        )
        first = month_start(period)
        path["date"] = [
            (first + pd.Timedelta(days=int(d) - 1)).date().isoformat()
            for d in path["day_of_month"]
        ]
        path["period"] = period
        # The goal contribution is a daily outflow that ``allocate_daily_path``
        # does not know about, so it is spread evenly across the month here.
        daily_contribution = float(monthly_goal_contribution) / max(days, 1)
        running = balance
        for _, row in path.iterrows():
            daily_net = float(row["net"]) - daily_contribution
            running += daily_net
            rows.append(
                {
                    "date": row["date"],
                    "period": period,
                    "income": float(row["income"]),
                    "spend": float(row["spend"]),
                    "recurring": float(row["recurring"]),
                    "discretionary": float(row["discretionary"]),
                    "goal_contribution": daily_contribution,
                    "net": daily_net,
                    "balance": running,
                }
            )
        if offset == one_off_month_index and one_off_expense:
            running -= one_off_expense
        balance = running

    frame = pd.DataFrame(rows)
    _ = buffer_target  # the floor is checked by the caller, not enforced here
    return frame


def _buffer_breaches(path: pd.DataFrame, buffer_target: float) -> dict[str, Any]:
    if path.empty:
        return {"breached": False, "days": 0, "worst": 0.0}
    below = path["balance"] < buffer_target
    return {
        "breached": bool(below.any()),
        "days": int(below.sum()),
        "worst": float(path["balance"].min()),
        "worst_shortfall": float(max(buffer_target - path["balance"].min(), 0.0)),
    }


# ---------------------------------------------------------------------------
# Goals: status
# ---------------------------------------------------------------------------

def _goal_rows(ctx: UserContext) -> pd.DataFrame:
    goals = ctx.goals
    if goals.empty:
        return goals
    saved = (
        ctx.contributions.groupby("goal_id", observed=True)["amount"].sum()
        if not ctx.contributions.empty
        else pd.Series(dtype=float)
    )
    goals = goals.copy()
    goals["current_amount"] = (
        saved.reindex(goals["goal_id"]).fillna(0.0).to_numpy()
        if not saved.empty
        else 0.0
    )
    goals["remaining_amount"] = (goals["target_amount"] - goals["current_amount"]).clip(lower=0.0)
    goals["progress_ratio"] = (
        goals["current_amount"] / goals["target_amount"].clip(lower=1.0)
    )
    return goals


def _months_remaining(ctx: UserContext, target_date) -> float:
    if target_date is None or pd.isna(target_date):
        return 0.0
    deadline = month_start(str(pd.Timestamp(target_date).strftime("%Y-%m")))
    return float(max(months_between(ctx.current_period, deadline.strftime("%Y-%m")), 0))


def goal_status(user_id: str, goal_id: str | None = None) -> GoalStatusResponse:
    """Every goal, its pace, and whether it lands on time at current capacity."""
    ctx = get_context(user_id)
    capacity = disposable_capacity(ctx)
    goals = _goal_rows(ctx)
    if goals.empty:
        return GoalStatusResponse(
            user_id=user_id,
            as_of=ctx.as_of.date().isoformat(),
            explanation=Explanation(headline="No savings goals are set up yet."),
            goals=[],
            goals_tracked=0,
        )

    capacity_per_goal = capacity["capacity"] / max(len(goals), 1)
    statuses: list[GoalStatus] = []
    on_track = 0

    for _, row in goals.iterrows():
        remaining = float(row["remaining_amount"])
        months_left = _months_remaining(ctx, row["target_date"])
        required = remaining / months_left if months_left > 0 else float("inf")
        completion_months = remaining / capacity_per_goal if capacity_per_goal > 0 else None
        pace = required / capacity_per_goal if capacity_per_goal > 0 else float("inf")
        is_on_track = bool(required <= capacity_per_goal) and months_left > 0
        if is_on_track:
            on_track += 1

        statuses.append(
            GoalStatus(
                user_id=user_id,
                as_of=ctx.as_of.date().isoformat(),
                goal_id=str(row["goal_id"]),
                goal_name=str(row["goal_name"]),
                target_amount=float(row["target_amount"]),
                current_amount=float(row["current_amount"]),
                remaining_amount=remaining,
                target_date=(
                    str(pd.Timestamp(row["target_date"]).date().isoformat())
                    if pd.notna(row["target_date"])
                    else None
                ),
                months_remaining=round(months_left, 1),
                priority=str(row.get("priority", "medium")),
                progress_ratio=round(float(row["progress_ratio"]), 4),
                required_monthly=round(required, 2) if math.isfinite(required) else -1.0,
                pace_ratio=round(pace, 4) if math.isfinite(pace) else -1.0,
                on_track=is_on_track,
                projected_completion=(
                    _months_forward(ctx, completion_months)
                    if completion_months is not None
                    else None
                ),
                months_to_completion=(
                    round(completion_months, 1) if completion_months is not None else None
                ),
                evidence=[
                    _evidence(
                        "goal_progress", float(row["progress_ratio"]), "goal_contributions", unit="ratio"
                    ),
                    _evidence(
                        "required_monthly", required if math.isfinite(required) else 0.0,
                        "engines.goals", unit="bdt",
                    ),
                ],
            )
        )

    total_target = float(goals["target_amount"].sum())
    total_saved = float(goals["current_amount"].sum())
    metrics = [
        Metric(
            key="total_target", label="Total goal target", value=total_target, unit="bdt",
            evidence=[_evidence("total_target", total_target, "financial_goals")],
        ),
        Metric(
            key="total_saved", label="Saved towards goals", value=total_saved, unit="bdt",
            previous_value=0.0,
            evidence=[
                _evidence("total_saved", total_saved, "goal_contributions"),
                _evidence("progress_ratio", total_saved / max(total_target, 1.0), "derived", unit="ratio"),
            ],
        ),
        Metric(
            key="goals_on_track",
            label="Goals on track",
            value=float(on_track),
            unit="count",
            direction=Direction.INCREASE if on_track == len(statuses) else Direction.FLAT,
            evidence=[
                _evidence("goals_on_track", float(on_track), "engines.goals", unit="count")
            ],
        ),
        Metric(
            key="disposable_capacity",
            label="Monthly capacity for goals",
            value=capacity["capacity"],
            unit="bdt",
            confidence=capacity["confidence"],
            evidence=[
                _evidence("monthly_income", capacity["monthly_income"], "monthly_features"),
                _evidence("monthly_spend", capacity["monthly_spend"], "monthly_features"),
                _evidence("buffer_cost", capacity["buffer_cost"], "settings"),
            ],
        ),
    ]

    active = goal_id or (
        statuses[0].goal_id if len(statuses) == 1 else (statuses[0].goal_id if statuses else None)
    )
    if goal_id:
        statuses = [s for s in statuses if s.goal_id == goal_id] or statuses

    behind = [s for s in statuses if not s.on_track]
    insights = []
    if behind:
        worst = max(behind, key=lambda s: (s.required_monthly if s.required_monthly > 0 else 0.0))
        insights.append(
            Insight(
                key="goal_behind_pace",
                title=f"'{worst.goal_name}' is ahead of its savings pace",
                observation=(
                    f"Reaching {format_bdt(worst.target_amount)} by {worst.target_date} needs "
                    f"about {format_bdt(max(worst.required_monthly, 0))} a month, while the "
                    f"monthly capacity is {format_bdt(capacity['capacity'])}."
                ),
                why=(
                    f"Capacity is {format_bdt(capacity['monthly_surplus'])} of monthly surplus "
                    f"after {format_bdt(capacity['monthly_spend'])} of spending, less "
                    f"{format_bdt(capacity['existing_contribution'])} already going to goals."
                ),
                action="Run a goal plan to see the three trade-offs and pick one.",
                severity=Severity.ATTENTION,
                impact_bdt=max(worst.required_monthly - capacity["capacity"], 0.0),
                evidence=[
                    _evidence("required_monthly", max(worst.required_monthly, 0.0), "engines.goals"),
                    _evidence("disposable_capacity", capacity["capacity"], "engines.goals"),
                ],
            )
        )

    return GoalStatusResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(
            headline=(
                f"{on_track} of {len(statuses)} goals on track; "
                f"{format_bdt(total_saved)} saved of {format_bdt(total_target)}."
            ),
            detail=[
                f"Monthly capacity after spending, existing contributions and the "
                f"{format_bdt(capacity['buffer_target'])} balance floor: "
                f"{format_bdt(capacity['capacity'])}.",
                f"Capacity is measured over the last {capacity['months_used']} months.",
            ],
        ),
        evidence=[
            _evidence("monthly_income", capacity["monthly_income"], "monthly_features"),
            _evidence("monthly_spend", capacity["monthly_spend"], "monthly_features"),
            _evidence("disposable_capacity", capacity["capacity"], "engines.goals"),
            _evidence("buffer_target", capacity["buffer_target"], "settings"),
        ],
        assumptions=[
            Assumption(
                key="buffer_floor_months",
                value=float(settings.buffer_floor_months),
                rationale=(
                    "Capacity reserves whatever is needed to keep the balance at or above "
                    f"max(flat {settings.minimum_balance_buffer:.0f}, "
                    f"{settings.buffer_floor_months:g} months of spending)."
                ),
            ),
            Assumption(
                key="capacity_window_months",
                value=3.0,
                rationale="Capacity uses the customer's own last 3 months, not a forecast.",
            ),
        ],
        metrics=metrics,
        insights=insights,
        goals=statuses,
        goals_tracked=len(statuses),
        goals_on_track=on_track,
        total_target=total_target,
        total_saved=total_saved,
        active_goal_id=active,
    )


# ---------------------------------------------------------------------------
# Goals: plan
# ---------------------------------------------------------------------------

def goal_plan(
    user_id: str,
    target_amount: float,
    months: float,
    goal_id: str | None = None,
    scenario: str | None = None,
) -> GoalPlanResponse:
    """Three ways to reach ``target_amount`` in ``months``, plus feasibility.

    Every option is capped by :func:`disposable_capacity`. When the required
    contribution exceeds capacity the plan says so and reports the shortfall;
    it never returns an unaffordable number with a reassuring label.
    """
    ctx = get_context(user_id)
    target_amount = float(max(target_amount, 0.0))
    months = float(max(months, 1.0))
    capacity = disposable_capacity(ctx)
    goals = _goal_rows(ctx)

    current_amount = 0.0
    if goal_id and not goals.empty:
        match = goals[goals["goal_id"] == goal_id]
        if not match.empty:
            current_amount = float(match.iloc[0]["current_amount"])
    remaining = max(target_amount - current_amount, 0.0)
    required = remaining / months
    available = capacity["capacity"]

    buffer_target = capacity["buffer_target"]
    income = capacity["monthly_income"]
    spend = capacity["monthly_spend"]

    scenarios: dict[str, float] = {
        # Conservative: leave a quarter of capacity unused, on purpose.
        "conservative": available * CONSERVATIVE_UTILISATION,
        # Balanced: exactly what the deadline demands, capped by capacity.
        "balanced": min(required, available),
        # Aggressive: everything available, which either hits the target early
        # or is the honest ceiling.
        "aggressive": min(available * MAX_UTILISATION, max(required * 1.15, available)),
    }

    options: list[GoalPlan] = []
    for key, contribution in scenarios.items():
        contribution = max(float(contribution), 0.0)
        completion_months = remaining / contribution if contribution > 0 else None
        horizon = int(math.ceil(min(months, completion_months or months))) or 1
        path = simulate_path(
            ctx,
            months=horizon,
            monthly_income=income,
            monthly_spend=spend,
            monthly_goal_contribution=contribution,
            buffer_target=buffer_target,
        )
        breach = _buffer_breaches(path, buffer_target)
        shortfall = max(required - contribution, 0.0)
        binding = ""
        if shortfall > 0:
            binding = "disposable_capacity"
        elif breach["breached"]:
            binding = "balance_buffer"
        feasible = shortfall <= 1.0 and not breach["breached"]

        trade_offs = []
        if key == "conservative":
            trade_offs.append(
                f"Leaves {format_bdt(available - contribution)} a month unallocated as a cushion."
            )
        if shortfall > 0:
            trade_offs.append(
                f"Falls short of the deadline by {format_bdt(shortfall)} a month."
            )
        if breach["breached"]:
            trade_offs.append(
                f"Dips below the {format_bdt(buffer_target)} buffer on "
                f"{breach['days']} days."
            )
        if contribution >= available and shortfall <= 0:
            trade_offs.append("Uses the entire monthly capacity; nothing left for surprises.")

        options.append(
            GoalPlan(
                user_id=user_id,
                as_of=ctx.as_of.date().isoformat(),
                scenario=PLAN_LABELS[key],
                monthly_contribution=round(contribution, 2),
                required_monthly=round(required, 2),
                feasible=feasible,
                shortfall=round(shortfall, 2),
                months_to_completion=(
                    round(completion_months, 1) if completion_months is not None else None
                ),
                projected_completion=(
                    _months_forward(ctx, completion_months) if completion_months is not None else None
                ),
                projected_balance_at_deadline=round(
                    float(path["balance"].iloc[-1]) if not path.empty else 0.0, 2
                ),
                buffer_respected=not breach["breached"],
                binding_constraint=binding,
                explanation=Explanation(
                    headline=(
                        f"{PLAN_LABELS[key]}: {format_bdt(contribution)} a month"
                        + ("" if feasible else " -- not achievable as specified")
                    ),
                    detail=trade_offs,
                ),
                evidence=[
                    _evidence("required_monthly", required, "engines.goals"),
                    _evidence("disposable_capacity", available, "engines.goals"),
                    _evidence(
                        "balance_at_deadline",
                        float(path["balance"].iloc[-1]) if not path.empty else 0.0,
                        "simulate_path",
                    ),
                ],
                assumptions=[
                    Assumption(
                        key="scenario_utilisation",
                        value=contribution / available if available > 0 else 0.0,
                        rationale=(
                            "Share of monthly capacity this scenario commits."
                        ),
                    )
                ],
            )
        )

    requested = (scenario or "").lower().strip()
    if requested:
        if requested not in PLAN_LABELS:
            raise ValueError(
                f"Unknown scenario '{scenario}'. Known: {', '.join(PLAN_LABELS)}"
            )
        chosen = next(o for o in options if o.scenario == PLAN_LABELS[requested])
        # An infeasible scenario is still returned with its shortfall and
        # binding constraint: refusing to answer would hide the very reason the
        # customer needs to see. It just does not become the recommendation.
        recommended = chosen.scenario if chosen.feasible else None
        if recommended is None:
            recommended = next((o.scenario for o in options if o.feasible), options[1].scenario)
    else:
        recommended = next(
            (o.scenario for o in options if o.feasible and o.scenario == "Balanced"), None
        )
        if recommended is None:
            recommended = next(
                (o.scenario for o in options if o.feasible), options[1].scenario
            )

    feasible_any = any(o.feasible for o in options)
    return GoalPlanResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(
            headline=(
                f"Reaching {format_bdt(target_amount)} in {months:g} months needs "
                f"{format_bdt(required)} a month; the monthly capacity is {format_bdt(available)}."
                + ("" if feasible_any else " No scenario clears both the deadline and the buffer.")
            ),
            detail=[
                f"Monthly income {format_bdt(income)}, spending {format_bdt(spend)}, "
                f"surplus {format_bdt(capacity['monthly_surplus'])}.",
                f"Buffer floor {format_bdt(buffer_target)} ({capacity['buffer_basis']}).",
            ],
        ),
        evidence=[
            _evidence("required_monthly", required, "engines.goals"),
            _evidence("disposable_capacity", available, "engines.goals", confidence=capacity["confidence"]),
            _evidence("monthly_income", income, "monthly_features"),
            _evidence("monthly_spend", spend, "monthly_features"),
            _evidence("buffer_target", buffer_target, "settings"),
        ],
        assumptions=[
            Assumption(
                key="buffer_floor_months",
                value=float(settings.buffer_floor_months),
                rationale="Buffer floor used to test whether a plan stays solvent.",
            ),
            Assumption(
                key="income_held_flat",
                value=1.0,
                rationale=(
                    "Plan holds income and spending at the customer's own 3-month average. "
                    "Use the simulator for changes to either."
                ),
            ),
        ],
        metrics=[
            Metric(key="required_monthly", label="Required a month", value=required, unit="bdt"),
            Metric(
                key="disposable_capacity",
                label="Monthly capacity",
                value=available,
                unit="bdt",
                confidence=capacity["confidence"],
            ),
            Metric(
                key="goal_feasible",
                label="Goal feasible on this capacity",
                value=1.0 if feasible_any else 0.0,
                unit="bool",
            ),
        ],
        insights=[
            Insight(
                key="goal_feasibility",
                title=("This goal is reachable" if feasible_any else "This goal is not reachable as specified"),
                observation=(
                    f"Needs {format_bdt(required)} a month against {format_bdt(available)} of capacity."
                ),
                why=(
                    "Capacity is your own average surplus after spending, existing goal "
                    "contributions and the balance floor."
                ),
                action=(
                    "Pick one of the three plans above."
                    if feasible_any
                    else "Extend the deadline, lower the target, or free up capacity."
                ),
                severity=Severity.INFO if feasible_any else Severity.WARNING,
                impact_bdt=round(min(required - available, 0.0) if required > available else 0.0, 2),
            )
        ],
        target_amount=target_amount,
        current_amount=current_amount,
        remaining_amount=round(remaining, 2),
        months_available=months,
        required_monthly=round(required, 2),
        disposable_capacity_monthly=round(available, 2),
        capacity_basis=(
            f"{capacity['months_used']}-month average: income {format_bdt(income)} "
            f"- spend {format_bdt(spend)} - goals {format_bdt(capacity['existing_contribution'])} "
            f"- buffer reserve {format_bdt(capacity['buffer_cost'])}"
        ),
        buffer_target=buffer_target,
        options=options,
        recommended_scenario=recommended,
        feasible_any=feasible_any,
    )


# ---------------------------------------------------------------------------
# Goals: conflict optimiser
# ---------------------------------------------------------------------------

PRIORITY_WEIGHTS = {"high": 1.0, "medium": 0.6, "low": 0.3}


def goal_conflicts(user_id: str) -> GoalConflictResponse:
    """Split one monthly capacity across competing goals, three ways.

    This is the honest answer to "I have a laptop, an emergency fund and a trip,
    and I cannot do all three": the system does not silently pick one, it shows
    three allocations and names the goal each one delays.
    """
    ctx = get_context(user_id)
    capacity = disposable_capacity(ctx)
    goals = _goal_rows(ctx)
    if goals.empty or len(goals) < 2:
        return GoalConflictResponse(
            user_id=user_id,
            as_of=ctx.as_of.date().isoformat(),
            explanation=Explanation(
                headline=(
                    "Only one goal is active, so there is nothing to trade off."
                    if not goals.empty
                    else "No goals are set up yet."
                )
            ),
            capacity_monthly=round(capacity["capacity"], 2),
            competing_goals=0 if goals.empty else len(goals),
            plans=[],
        )

    available = capacity["capacity"]
    rows = []
    for _, row in goals.iterrows():
        remaining = float(row["remaining_amount"])
        months_left = max(_months_remaining(ctx, row["target_date"]), 1.0)
        rows.append(
            {
                "goal_id": str(row["goal_id"]),
                "goal_name": str(row["goal_name"]),
                "priority": str(row.get("priority", "medium")),
                "required": remaining / months_left,
                "months_left": months_left,
                "remaining": remaining,
            }
        )

    total_required = sum(item["required"] for item in rows)

    def allocate(weights: dict[str, float]) -> dict[str, float]:
        """Weighted split of capacity, capped at what each goal actually needs.

        Three passes, and the cap matters most:

        1. each goal's *fair share* of capacity by weight, clipped so no goal is
           ever allocated more than its deadline requires (over-funding a goal
           is how a plan silently starves another);
        2. any capacity still unclaimed is redistributed among goals that are
           still short, in proportion to weight;
        3. whatever remains unmet is the honest shortfall, reported as
           ``goals_delayed`` -- never papered over.

        Total allocation can never exceed ``available``: a plan that invents
        capacity is worse than one that admits a goal will slip.
        """
        total_weight = sum(max(weights.get(i["goal_id"], 0.0), 0.0) for i in rows)
        if total_weight <= 0:
            total_weight = float(len(rows)) or 1.0
        fair = {
            item["goal_id"]: min(
                available * max(weights.get(item["goal_id"], 0.0), 0.0) / total_weight,
                item["required"],
            )
            for item in rows
        }
        allocated = sum(fair.values())
        leftover = max(available - allocated, 0.0)

        if leftover > 0:
            short = [i for i in rows if fair[i["goal_id"]] < i["required"] - 1e-9]
            short_weight = sum(max(weights.get(i["goal_id"], 0.0), 0.0) for i in short)
            if short_weight > 0:
                for item in short:
                    share = leftover * max(weights.get(item["goal_id"], 0.0), 0.0) / short_weight
                    fair[item["goal_id"]] = min(
                        fair[item["goal_id"]] + share, item["required"]
                    )
            else:
                for item in short:
                    fair[item["goal_id"]] = min(
                        fair[item["goal_id"]] + leftover / len(short), item["required"]
                    )

        # Final safety net: never exceed capacity, even if rounding drifted.
        over = sum(fair.values()) - available
        if over > 0:
            for item in sorted(rows, key=lambda i: -fair[i["goal_id"]]):
                take = min(over, fair[item["goal_id"]])
                fair[item["goal_id"]] -= take
                over -= take
                if over <= 1e-9:
                    break
        return {k: max(v, 0.0) for k, v in fair.items()}

    by_id = {item["goal_id"]: item for item in rows}
    strategies: list[tuple[str, str, dict[str, float]]] = [
        ("Deadline first", "Give every goal what its deadline needs, oldest pressure first.",
         {i["goal_id"]: (1.0 if i["required"] > 0 else 0.0) for i in rows}),
        ("Priority weighted", "Split capacity by stated priority: high, then medium, then low.",
         {i["goal_id"]: PRIORITY_WEIGHTS.get(i["priority"], 0.6) for i in rows}),
        ("Even split", "Split capacity equally between all goals.",
         {i["goal_id"]: 1.0 for i in rows}),
    ]

    plans: list[GoalConflictPlan] = []
    for name, strategy, weights in strategies:
        allocation = allocate(weights)
        met: list[str] = []
        delayed: list[str] = []
        max_delay = 0.0
        for goal_id, amount in allocation.items():
            item = by_id[goal_id]
            if amount >= item["required"] - 1.0:
                met.append(goal_id)
            else:
                delayed.append(goal_id)
                completion = item["remaining"] / amount if amount > 0 else float("inf")
                if math.isfinite(completion):
                    max_delay = max(max_delay, completion - item["months_left"])
        plans.append(
            GoalConflictPlan(
                user_id=user_id,
                as_of=ctx.as_of.date().isoformat(),
                name=name,
                strategy=strategy,
                allocations={k: round(v, 2) for k, v in allocation.items()},
                goals_met_on_time=met,
                goals_delayed=delayed,
                months_delayed_max=round(max_delay, 1),
                capacity_used=round(sum(allocation.values()), 2),
                capacity_unused=round(max(available - sum(allocation.values()), 0.0), 2),
                explanation=Explanation(
                    headline=(
                        f"{name}: {len(met)} of {len(rows)} goals on time, "
                        f"longest delay {max_delay:.0f} months."
                    ),
                    detail=[strategy],
                ),
                evidence=[
                    _evidence("capacity_monthly", available, "engines.goals"),
                    _evidence("total_required_monthly", total_required, "engines.goals"),
                ],
            )
        )

    recommended = min(plans, key=lambda p: (len(p.goals_delayed), p.months_delayed_max))
    return GoalConflictResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(
            headline=(
                f"{len(rows)} goals compete for {format_bdt(available)} a month; "
                f"together they need {format_bdt(total_required)}."
            ),
            detail=[
                "Each plan below names the goals it delays. None of them is recommended outright.",
            ],
        ),
        evidence=[
            _evidence("capacity_monthly", available, "engines.goals"),
            _evidence("total_required_monthly", total_required, "engines.goals"),
        ],
        assumptions=[
            Assumption(
                key="capacity_is_fixed",
                value=1.0,
                rationale=(
                    "Total allocation is capped at the customer's disposable capacity. "
                    "Plans cannot invent savings."
                ),
            )
        ],
        capacity_monthly=round(available, 2),
        competing_goals=len(rows),
        total_required_monthly=round(total_required, 2),
        overall_shortfall_monthly=round(max(total_required - available, 0.0), 2),
        plans=plans,
        recommended_plan=recommended.name,
    )


# ---------------------------------------------------------------------------
# Emergency fund
# ---------------------------------------------------------------------------

ESSENTIAL_CATEGORIES = ("housing", "utilities", "food", "transport", "communication", "health")


def emergency_fund(user_id: str) -> EmergencyFundResponse:
    """Size an emergency cushion from this customer's own essential spending.

    The target is ``emergency_fund_months`` times *their* essential monthly
    spend, where essentials are their own recurring obligations plus their
    observed spending in essential categories. This is a planning estimate, not
    a rule, which is why the multiple is a configurable assumption and is
    reported.
    """
    ctx = get_context(user_id)
    capacity = disposable_capacity(ctx)
    monthly = ctx.history(3)
    if monthly.empty:
        raise ValueError(f"No monthly history for {user_id}")

    recurring = float(ctx.feature("mandatory_obligation_amount") or ctx.feature("monthly_recurring_amount") or 0.0)

    essential_columns = [f"spend_{c}" for c in ESSENTIAL_CATEGORIES if f"spend_{c}" in monthly.columns]
    if essential_columns:
        essential_categories = float(monthly[essential_columns].to_numpy(dtype=float).mean())
    else:
        essential_categories = 0.0

    if recurring > 0:
        essential = recurring + essential_categories
        basis = "mandatory obligations + essential-category spending (3-month mean)"
    else:
        essential = essential_categories
        basis = "essential-category spending (3-month mean)"

    target_months = float(settings.emergency_fund_months)
    target = essential * target_months
    current = max(
        float(ctx.daily["balance"].iloc[-1]) if not ctx.daily.empty else 0.0,
        0.0,
    )
    remaining = max(target - current, 0.0)
    available = capacity["capacity"]
    months_to_target = remaining / available if available > 0 else None
    progress = current / target if target > 0 else 1.0

    insights = []
    if progress >= 1.0:
        insights.append(
            Insight(
                key="emergency_funded",
                title="Your emergency buffer is funded",
                observation=f"Available balance covers {current / essential:.1f} months of essentials.",
                why=f"Target is {target_months:g} months of {format_bdt(essential)} essential spending.",
                action="Consider directing spare capacity to your goals instead.",
                severity=Severity.INFO,
            )
        )
    elif available <= 0:
        insights.append(
            Insight(
                key="emergency_no_capacity",
                title="No monthly capacity to build a buffer yet",
                observation="Recent spending absorbs the whole of monthly income.",
                why=(
                    f"Average income {format_bdt(capacity['monthly_income'])} versus average "
                    f"spending {format_bdt(capacity['monthly_spend'])}."
                ),
                action="Start with a smaller one-month target, then raise it.",
                severity=Severity.WARNING,
            )
        )
    else:
        insights.append(
            Insight(
                key="emergency_build",
                title=f"Buffer is {progress * 100:.0f}% funded",
                observation=(
                    f"{format_bdt(remaining)} to go at {format_bdt(available)} a month is about "
                    f"{months_to_target:.0f} months."
                )
                if months_to_target
                else f"{format_bdt(remaining)} to go.",
                why=f"Essential spending is {format_bdt(essential)} a month ({basis}).",
                action="Set an automatic transfer after payday if your account supports it.",
                severity=Severity.ATTENTION,
                impact_bdt=round(remaining, 2),
            )
        )

    return EmergencyFundResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(
            headline=(
                f"Emergency buffer {progress * 100:.0f}% of the way to "
                f"{target_months:g} months of essentials ({format_bdt(target)})."
            ),
            detail=[
                f"Essential monthly spend {format_bdt(essential)} -- {basis}.",
                f"Current balance {format_bdt(current)}.",
            ],
        ),
        evidence=[
            _evidence("essential_monthly_spend", essential, "engines.planning"),
            _evidence("target_amount", target, "settings", comparison=f"{target_months:g} months"),
            _evidence("current_savings", current, "daily_features"),
            _evidence("disposable_capacity", available, "engines.planning"),
        ],
        assumptions=[
            Assumption(
                key="emergency_fund_months",
                value=target_months,
                rationale=(
                    "A planning convention, not a financial rule. Three months is common "
                    "guidance; change it to match your own situation."
                ),
            ),
            Assumption(
                key="essential_categories",
                value=float(len(ESSENTIAL_CATEGORIES)),
                rationale="Categories counted as essential: " + ", ".join(ESSENTIAL_CATEGORIES),
            ),
        ],
        metrics=[
            Metric(key="essential_monthly_spend", label="Essential spend a month", value=essential, unit="bdt"),
            Metric(key="target_amount", label="Suggested buffer", value=target, unit="bdt"),
            Metric(key="current_savings", label="Current balance", value=current, unit="bdt"),
            Metric(key="progress_ratio", label="Funded", value=progress, unit="ratio"),
        ],
        insights=insights,
        essential_monthly_spend=round(essential, 2),
        basis=basis,
        target_months=target_months,
        target_amount=round(target, 2),
        current_savings=round(current, 2),
        remaining_amount=round(remaining, 2),
        progress_ratio=round(progress, 4),
        months_to_target=round(months_to_target, 1) if months_to_target else None,
        affordable_monthly=round(available, 2),
        affordable=bool(available > 0),
        disposable_capacity_monthly=round(available, 2),
        funded=bool(progress >= 1.0),
    )


# ---------------------------------------------------------------------------
# What-if simulator
# ---------------------------------------------------------------------------

def simulate(
    user_id: str,
    monthly_saving_change: float = 0.0,
    income_change_percent: float = 0.0,
    expense_change: float = 0.0,
    unexpected_expense: float = 0.0,
    months: int = 12,
) -> SimulationResponse:
    """Run one counterfactual against the same engine the forecast uses.

    The baseline and the scenario are both produced by
    :func:`simulate_path`, so the difference reported is caused only by the
    change the customer asked about -- not by two different forecasting methods.
    """
    ctx = get_context(user_id)
    months = int(max(1, min(months, 60)))
    capacity = disposable_capacity(ctx)
    baseline_income = capacity["monthly_income"]
    baseline_spend = capacity["monthly_spend"]
    baseline_contribution = capacity["existing_contribution"]
    buffer_target = capacity["buffer_target"]
    start_balance = capacity["current_balance"]

    baseline_path = simulate_path(
        ctx, months, baseline_income, baseline_spend, baseline_contribution,
        buffer_target, start_balance=start_balance,
    )
    scenario_path = simulate_path(
        ctx,
        months,
        monthly_income=baseline_income * (1.0 + float(income_change_percent) / 100.0),
        monthly_spend=max(baseline_spend + float(expense_change), 0.0),
        monthly_goal_contribution=max(baseline_contribution + float(monthly_saving_change), 0.0),
        buffer_target=buffer_target,
        start_balance=start_balance,
        one_off_expense=max(float(unexpected_expense), 0.0),
    )

    baseline_breach = _buffer_breaches(baseline_path, buffer_target)
    scenario_breach = _buffer_breaches(scenario_path, buffer_target)

    baseline_final = float(baseline_path["balance"].iloc[-1]) if not baseline_path.empty else 0.0
    scenario_final = float(scenario_path["balance"].iloc[-1]) if not scenario_path.empty else 0.0
    delta = scenario_final - baseline_final

    # Saving more moves money OUT of the spendable wallet and INTO savings. It
    # does not destroy money. Reporting the raw balance delta alone would say
    # that saving 2,000 a month "loses" 24,000 over a year, which is nonsense
    # and is exactly the kind of number that discredits the feature. So the
    # response separates the spendable balance from the savings stock, and
    # reports the net-worth effect separately.
    savings_baseline = capacity["existing_contribution"] * months
    savings_scenario = max(capacity["existing_contribution"] + float(monthly_saving_change), 0.0) * months
    savings_change = savings_scenario - savings_baseline
    net_worth_change = delta + savings_change

    # How many whole goals does the scenario unlock? Uses the customer's own
    # goals and required pace -- no invented targets.
    goals = _goal_rows(ctx)
    per_goal_capacity = (
        max(baseline_contribution + float(monthly_saving_change), 0.0) / max(len(goals), 1)
    )
    goals_unlocked = 0
    goals_still_short = 0
    for _, row in goals.iterrows():
        months_left = max(_months_remaining(ctx, row["target_date"]), 1.0)
        required = float(row["remaining_amount"]) / months_left
        if per_goal_capacity >= required - 1.0:
            goals_unlocked += 1
        else:
            goals_still_short += 1

    if scenario_breach["breached"] and not baseline_breach["breached"]:
        risk = "high"
    elif scenario_breach["breached"]:
        risk = "high"
    elif delta >= 0:
        risk = "low"
    else:
        risk = "moderate"

    explanations: list[str] = []
    if monthly_saving_change:
        explanations.append(
            f"Saving {format_bdt(abs(float(monthly_saving_change)))} "
            f"{'more' if monthly_saving_change > 0 else 'less'} a month leaves "
            f"{format_bdt(abs(delta))} {'less' if delta < 0 else 'more'} in the spendable wallet "
            f"after {months} months, and puts {format_bdt(abs(savings_change))} "
            f"{'into' if savings_change >= 0 else 'out of'} savings. Your total money is "
            f"{format_bdt(abs(net_worth_change))} "
            f"{'better' if net_worth_change >= 0 else 'worse'}."
        )
    if income_change_percent:
        explanations.append(
            f"Income {float(income_change_percent):+.0f}% changes your total money by "
            f"{format_bdt(baseline_income * float(income_change_percent) / 100.0 * months)} "
            f"over {months} months."
        )
    if expense_change:
        explanations.append(
            f"Spending {format_bdt(abs(float(expense_change)))} "
            f"{'more' if expense_change > 0 else 'less'} a month changes your total money by "
            f"{format_bdt(-float(expense_change) * months)} over {months} months."
        )
    if unexpected_expense:
        explanations.append(
            f"A one-off {format_bdt(float(unexpected_expense))} in the first month changes your "
            f"total money by {format_bdt(-float(unexpected_expense))}."
        )
    if not explanations:
        explanations.append("Nothing changed, so nothing moved. Try a different scenario.")

    insights = []
    if scenario_breach["breached"]:
        insights.append(
            Insight(
                key="scenario_buffer_breach",
                title="This scenario drops you below your buffer",
                observation=(
                    f"Lowest projected balance {format_bdt(scenario_breach['worst'])}, "
                    f"{format_bdt(scenario_breach['worst_shortfall'])} below the floor, on "
                    f"{scenario_breach['days']} days."
                ),
                why=f"The floor is {format_bdt(buffer_target)} ({capacity['buffer_basis']}).",
                action="Soften the change or shift part of it to a later month.",
                severity=Severity.WARNING,
                impact_bdt=round(scenario_breach["worst_shortfall"], 2),
            )
        )
    elif net_worth_change >= 0 and goals_unlocked:
        insights.append(
            Insight(
                key="scenario_unlocks_goals",
                title=f"This change puts {goals_unlocked} goal(s) back on pace",
                observation=(
                    f"Total money improves by {format_bdt(net_worth_change)} over "
                    f"{months} months; {goals_still_short} goal(s) still need more."
                ),
                why=f"Per-goal capacity becomes {format_bdt(per_goal_capacity)} a month.",
                action="Open the goal plan to see the three trade-offs.",
                severity=Severity.INFO,
                impact_bdt=round(net_worth_change, 2),
            )
        )

    curve = [
        {
            "period": str(base_row["period"]),
            "date": str(base_row["date"]),
            "baseline_balance": round(float(base_row["balance"]), 2),
            "scenario_balance": round(float(scenario_row["balance"]), 2),
            "delta": round(float(scenario_row["balance"]) - float(base_row["balance"]), 2),
        }
        for base_row, scenario_row in zip(
            baseline_path.to_dict("records"), scenario_path.to_dict("records")
        )
    ]

    return SimulationResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(
            headline=(
                f"After {months} months the spendable balance would be "
                f"{format_bdt(scenario_final)}, {format_bdt(abs(delta))} "
                f"{'more' if delta >= 0 else 'less'} in the wallet than today, with savings holding "
                f"{format_bdt(savings_scenario)}."
            ),
            detail=explanations,
        ),
        evidence=[
            _evidence("baseline_ending_balance", baseline_final, "simulate_path", window=f"+{months}m"),
            _evidence("scenario_ending_balance", scenario_final, "simulate_path", window=f"+{months}m"),
            _evidence("balance_change", delta, "derived", window=f"+{months}m"),
            _evidence("savings_change", savings_change, "derived", window=f"+{months}m"),
            _evidence("net_worth_change", net_worth_change, "derived", window=f"+{months}m"),
            _evidence("buffer_target", buffer_target, "settings"),
            _evidence("start_balance", start_balance, "daily_features"),
        ],
        assumptions=[
            Assumption(
                key="income_and_spend_held_flat",
                value=1.0,
                rationale=(
                    "Unchanged amounts are held at the customer's own 3-month averages, not "
                    "forecast levels, so the delta is caused only by the change asked about."
                ),
            ),
            Assumption(
                key="unexpected_expense_month",
                value=1.0,
                rationale="A one-off expense is applied in the first projected month.",
            ),
            Assumption(
                key="simulation_is_hypothetical",
                value=1.0,
                rationale="Nothing here is applied to the ledger. This is a counterfactual.",
            ),
        ],
        metrics=[
            Metric(key="baseline_ending_balance", label="Balance without the change", value=round(baseline_final, 2), unit="bdt"),
            Metric(key="scenario_ending_balance", label="Balance with the change", value=round(scenario_final, 2), unit="bdt"),
            Metric(
                key="balance_change", label="Spendable balance change", value=round(delta, 2),
                unit="bdt", direction=Direction.INCREASE if delta >= 0 else Direction.DECREASE,
                previous_value=baseline_final,
                comparison="Saving more moves money out of the wallet, not out of your life.",
            ),
            Metric(
                key="savings_change", label="Savings change", value=round(savings_change, 2),
                unit="bdt",
                direction=Direction.INCREASE if savings_change >= 0 else Direction.DECREASE,
            ),
            Metric(
                key="net_worth_change", label="Total money change", value=round(net_worth_change, 2),
                unit="bdt",
                direction=Direction.INCREASE if net_worth_change >= 0 else Direction.DECREASE,
                comparison="Spendable balance plus savings.",
            ),
            Metric(
                key="goals_unlocked", label="Goals back on pace", value=float(goals_unlocked), unit="count"
            ),
            Metric(key="risk_level", label="Buffer risk", value=float({"low": 1, "moderate": 2, "high": 3}[risk]), unit="ordinal"),
        ],
        insights=insights,
        scenario=SimulationScenario(
            user_id=user_id,
            as_of=ctx.as_of.date().isoformat(),
            monthly_saving_change=float(monthly_saving_change),
            income_change_percent=float(income_change_percent),
            expense_change=float(expense_change),
            unexpected_expense=float(unexpected_expense),
            applied=False,
            explanation=Explanation(headline="Hypothetical. Nothing has been changed."),
        ),
        baseline_ending_balance=round(baseline_final, 2),
        scenario_ending_balance=round(scenario_final, 2),
        balance_change=round(delta, 2),
        savings_change=round(savings_change, 2),
        net_worth_change=round(net_worth_change, 2),
        savings_baseline=round(savings_baseline, 2),
        savings_scenario=round(savings_scenario, 2),
        risk_level=risk,
        min_baseline_balance=round(float(baseline_path["balance"].min()), 2) if not baseline_path.empty else 0.0,
        min_scenario_balance=round(float(scenario_path["balance"].min()), 2) if not scenario_path.empty else 0.0,
        buffer_respected=not scenario_breach["breached"],
        buffer_breach_days=scenario_breach["days"],
        goals_unlocked=goals_unlocked,
        goals_still_short=goals_still_short,
        months=months,
        curve=curve,
    )