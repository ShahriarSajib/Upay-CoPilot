"""Contracts for the planning engines: goals, emergency fund, what-if.

Why a separate module
---------------------
``app.schemas.common`` has :class:`PlanOption`, which is enough for "here are
three ways to hit one number". The planning engines do more than that:

* :class:`GoalPlan` is a **constrained** plan. It carries the disposable
  capacity it was allowed to spend, the balance floor it had to respect, and an
  explicit ``feasible`` flag. A planner that can quietly emit an unaffordable
  monthly contribution is worse than no planner, because the customer will act
  on it.
* :class:`GoalConflictPlan` is the multi-goal case, where the interesting output
  is not a number but a **trade-off**: which goal slips, and by how much.
* :class:`SimulationScenario` is a *counterfactual* and says so in its own
  contract, so a simulated balance can never be mistaken for a forecast.

Every one of these inherits :class:`EngineResponse`, so the evidence,
assumption and insight machinery the rest of the system relies on applies here
without adaptation.
"""

from __future__ import annotations

from app.schemas.common import EngineResponse

__all__ = [
    "GoalConflictPlan",
    "GoalConflictResponse",
    "GoalPlan",
    "GoalPlanResponse",
    "GoalStatus",
    "GoalStatusResponse",
    "SimulationResponse",
    "SimulationScenario",
    "EmergencyFundResponse",
]


class SimulationScenario(EngineResponse):
    """One counterfactual the customer asked about.

    All fields are hypothetical. Nothing here is applied to the ledger, and
    ``applied=False`` is carried into the response so a client cannot render a
    simulation as a state change.
    """

    monthly_saving_change: float = 0.0
    income_change_percent: float = 0.0
    expense_change: float = 0.0
    unexpected_expense: float = 0.0
    applied: bool = False


class GoalStatus(EngineResponse):
    """One goal as it stands today, with pace against its deadline."""

    goal_id: str
    goal_name: str
    target_amount: float = 0.0
    current_amount: float = 0.0
    remaining_amount: float = 0.0
    target_date: str | None = None
    months_remaining: float = 0.0
    priority: str = "medium"
    progress_ratio: float = 0.0
    required_monthly: float = 0.0
    pace_ratio: float = 0.0
    on_track: bool = False
    projected_completion: str | None = None
    months_to_completion: float | None = None


class GoalStatusResponse(EngineResponse):
    goals: list[GoalStatus] = []
    goals_tracked: int = 0
    goals_on_track: int = 0
    total_target: float = 0.0
    total_saved: float = 0.0
    active_goal_id: str | None = None


class GoalPlan(EngineResponse):
    """One feasible-or-not way to reach a target amount by a deadline."""

    scenario: str
    monthly_contribution: float = 0.0
    required_monthly: float = 0.0
    feasible: bool = False
    shortfall: float = 0.0
    months_to_completion: float | None = None
    projected_completion: str | None = None
    projected_balance_at_deadline: float = 0.0
    buffer_respected: bool = True
    binding_constraint: str = ""


class GoalPlanResponse(EngineResponse):
    target_amount: float = 0.0
    current_amount: float = 0.0
    remaining_amount: float = 0.0
    months_available: float = 0.0
    required_monthly: float = 0.0
    disposable_capacity_monthly: float = 0.0
    capacity_basis: str = ""
    buffer_target: float = 0.0
    options: list[GoalPlan] = []
    recommended_scenario: str | None = None
    feasible_any: bool = False


class GoalConflictPlan(EngineResponse):
    """One allocation of a fixed monthly capacity across competing goals."""

    name: str
    strategy: str = ""
    allocations: dict[str, float] = {}
    goals_met_on_time: list[str] = []
    goals_delayed: list[str] = []
    months_delayed_max: float = 0.0
    capacity_used: float = 0.0
    capacity_unused: float = 0.0


class GoalConflictResponse(EngineResponse):
    capacity_monthly: float = 0.0
    competing_goals: int = 0
    total_required_monthly: float = 0.0
    overall_shortfall_monthly: float = 0.0
    plans: list[GoalConflictPlan] = []
    recommended_plan: str | None = None


class EmergencyFundResponse(EngineResponse):
    essential_monthly_spend: float = 0.0
    basis: str = ""
    target_months: float = 0.0
    target_amount: float = 0.0
    current_savings: float = 0.0
    remaining_amount: float = 0.0
    progress_ratio: float = 0.0
    months_to_target: float | None = None
    affordable_monthly: float = 0.0
    affordable: bool = False
    disposable_capacity_monthly: float = 0.0
    funded: bool = False


class SimulationResponse(EngineResponse):
    """Baseline vs scenario, with the full daily curve for charting."""

    baseline_ending_balance: float = 0.0
    scenario_ending_balance: float = 0.0
    balance_change: float = 0.0
    savings_change: float = 0.0
    net_worth_change: float = 0.0
    savings_baseline: float = 0.0
    savings_scenario: float = 0.0
    risk_level: str = "low"
    min_baseline_balance: float = 0.0
    min_scenario_balance: float = 0.0
    buffer_respected: bool = True
    buffer_breach_days: int = 0
    goals_unlocked: int = 0
    goals_still_short: int = 0
    months: int = 12
    curve: list[dict] = []
