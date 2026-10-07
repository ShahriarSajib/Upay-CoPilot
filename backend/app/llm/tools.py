"""Allowlisted tool layer for the LLM.

The only allowed way for an assistant to access numbers is through these tools.
Each tool returns the Pydantic response serialised (or a compact form). No
free-form SQL, no writes, no score changes, and no autonomous credit decisions.
The router between Gemini (primary) and Groq (fallback) must only call these.

Tools are grouped by domain:

* Understand : financial_health, resilience_score, population_segments,
               describe_user, spending_summary, spending_recurring,
               spending_leaks, spending_unusual, spending_late_month
* Predict    : cashflow_forecast, upcoming_bills
* Plan       : goal_status, goal_plan, goal_conflicts, emergency_fund,
               simulate
* Assist     : financial_literacy
* Trust      : credit_readiness, cash_out_analysis

Every tool declares its parameter schema so the language model can call it
with concrete arguments instead of inventing them.
"""

from __future__ import annotations

from typing import Any

from app.engines.bills import upcoming_bills
from app.engines.cashout import cash_out_analysis
from app.engines.credit import credit_readiness
from app.engines.forecasting import cashflow_forecast
from app.engines.health import financial_health
from app.engines.literacy import financial_literacy
from app.engines.planning import (
    emergency_fund,
    goal_conflicts,
    goal_plan,
    goal_status,
    simulate,
)
from app.engines.resilience import resilience_score
from app.engines.segmentation import describe_user, population_segments
from app.engines.spending import (
    late_month_analysis,
    recurring_summary,
    spending_leaks,
    spending_summary,
    unusual_spending,
)


# ---------------------------------------------------------------------------
# Tool implementations -- each one is a thin wrapper around a deterministic
# engine. The LLM never sees the raw data store; it only sees the engine's
# pre-computed, evidenced response.
# ---------------------------------------------------------------------------


def _dump(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return result
    return {"value": result}


def tool_cashflow_forecast(user_id: str, horizon_days: int = 30) -> dict[str, Any]:
    return _dump(cashflow_forecast(user_id, horizon_days=horizon_days))


def tool_financial_literacy(user_id: str, topic: str | None = None) -> dict[str, Any]:
    return _dump(financial_literacy(user_id, topic=topic))


def tool_credit_readiness(user_id: str) -> dict[str, Any]:
    return _dump(credit_readiness(user_id))


def tool_goal_status(user_id: str) -> dict[str, Any]:
    return _dump(goal_status(user_id))


def tool_goal_plan(
    user_id: str,
    target_amount: float,
    months: float,
    scenario: str = "balanced",
) -> dict[str, Any]:
    return _dump(
        goal_plan(
            user_id,
            target_amount=float(target_amount),
            months=float(months),
            scenario=scenario,
        )
    )


def tool_goal_conflicts(user_id: str) -> dict[str, Any]:
    return _dump(goal_conflicts(user_id))


def tool_emergency_fund(user_id: str) -> dict[str, Any]:
    return _dump(emergency_fund(user_id))


def tool_simulate(user_id: str, **kwargs: Any) -> dict[str, Any]:
    return _dump(simulate(user_id=user_id, **kwargs))


def tool_financial_health(user_id: str) -> dict[str, Any]:
    return _dump(financial_health(user_id))


def tool_resilience_score(user_id: str) -> dict[str, Any]:
    return _dump(resilience_score(user_id))


def tool_spending_summary(user_id: str, period: str | None = None) -> dict[str, Any]:
    return _dump(spending_summary(user_id, period=period))


def tool_spending_unusual(user_id: str, period: str | None = None) -> dict[str, Any]:
    return _dump(unusual_spending(user_id, period=period))


def tool_spending_recurring(user_id: str) -> dict[str, Any]:
    return _dump(recurring_summary(user_id))


def tool_spending_leaks(
    user_id: str,
    period: str | None = None,
    threshold: float = 500.0,
) -> dict[str, Any]:
    return _dump(spending_leaks(user_id, period=period, threshold=threshold))


def tool_spending_late_month(user_id: str, months: int = 3) -> dict[str, Any]:
    return _dump(late_month_analysis(user_id, months=months))


def tool_cash_out_analysis(user_id: str, months: int = 3) -> dict[str, Any]:
    return _dump(cash_out_analysis(user_id, months=months))


def tool_upcoming_bills(user_id: str, days_ahead: int = 45) -> dict[str, Any]:
    return _dump(upcoming_bills(user_id, days_ahead=days_ahead))


def tool_population_segments() -> dict[str, Any]:
    return {"segments": population_segments()}


def tool_describe_user(user_id: str) -> dict[str, Any]:
    return _dump(describe_user(user_id))


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


ALLOWED_TOOLS = {
    "cashflow_forecast",
    "financial_literacy",
    "credit_readiness",
    "goal_status",
    "goal_plan",
    "goal_conflicts",
    "emergency_fund",
    "simulate",
    "financial_health",
    "resilience_score",
    "spending_summary",
    "spending_unusual",
    "spending_recurring",
    "spending_leaks",
    "spending_late_month",
    "cash_out_analysis",
    "upcoming_bills",
    "population_segments",
    "describe_user",
}


TOOLS = {
    "cashflow_forecast": tool_cashflow_forecast,
    "financial_literacy": tool_financial_literacy,
    "credit_readiness": tool_credit_readiness,
    "goal_status": tool_goal_status,
    "goal_plan": tool_goal_plan,
    "goal_conflicts": tool_goal_conflicts,
    "emergency_fund": tool_emergency_fund,
    "simulate": tool_simulate,
    "financial_health": tool_financial_health,
    "resilience_score": tool_resilience_score,
    "spending_summary": tool_spending_summary,
    "spending_unusual": tool_spending_unusual,
    "spending_recurring": tool_spending_recurring,
    "spending_leaks": tool_spending_leaks,
    "spending_late_month": tool_spending_late_month,
    "cash_out_analysis": tool_cash_out_analysis,
    "upcoming_bills": tool_upcoming_bills,
    "population_segments": tool_population_segments,
    "describe_user": tool_describe_user,
}


# ---------------------------------------------------------------------------
# Tool schemas -- declared once and reused for Gemini and Groq. Each entry
# lists every parameter the matching engine actually accepts, plus a short
# description, so the model can call tools with real arguments.
# ---------------------------------------------------------------------------


def _number(name: str, description: str, default: float | None = None) -> dict:
    schema: dict[str, Any] = {"type": "number", "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def _string(name: str, description: str, enum: list[str] | None = None) -> dict:
    schema: dict[str, Any] = {"type": "string", "description": description}
    if enum is not None:
        schema["enum"] = enum
    return schema


def _optional(name: str, base: dict) -> dict:
    """Mark a parameter as not required."""
    return {**base, "name": name}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "cashflow_forecast",
        "description": (
            "Predict the next-N-days balance path, expected income, expected "
            "expenses, and probability of running short. Pass horizon_days in "
            "{7,14,30,60,90}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "horizon_days": _number(
                    "horizon_days",
                    "Number of days to project forward.",
                    default=30,
                ),
            },
            "required": [],
        },
    },
    {
        "name": "financial_literacy",
        "description": (
            "Return a personalised financial-literacy recommendation based on "
            "the customer's observed behaviour. Topic may be one of: "
            "cash_flow_gap, emergency_fund, savings_habit, irregular_income, "
            "cash_dependency, budgeting, overspending, goal_plan, debt_aware. "
            "If omitted, the engine picks the most relevant topic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": _string(
                    "topic",
                    "Optional literacy topic key.",
                ),
            },
            "required": [],
        },
    },
    {
        "name": "credit_readiness",
        "description": (
            "Hypothetical credit-readiness overview derived from transaction "
            "patterns. NEVER a lending decision -- the response carries a "
            "disclaimer."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "goal_status",
        "description": "List the customer's financial goals and progress.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "goal_plan",
        "description": (
            "Compute a savings plan for a target amount over a number of "
            "months. Scenario is one of {conservative, balanced, aggressive}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_amount": _number(
                    "target_amount",
                    "Goal target amount in BDT.",
                ),
                "months": _number(
                    "months",
                    "Number of months until the target date.",
                ),
                "scenario": _string(
                    "scenario",
                    "Plan scenario: conservative | balanced | aggressive.",
                    enum=["conservative", "balanced", "aggressive"],
                ),
            },
            "required": ["target_amount", "months"],
        },
    },
    {
        "name": "goal_conflicts",
        "description": (
            "Detect whether the customer's existing goals conflict over their "
            "available monthly saving capacity."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "emergency_fund",
        "description": (
            "Estimate the recommended emergency-fund target and gap based on "
            "essential spending."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "simulate",
        "description": (
            "Run a what-if scenario over the customer's forecast. Accepted "
            "levers: monthly_saving_change, income_change_pct, expense_change, "
            "unexpected_expense. Any other key is rejected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "monthly_saving_change": _number(
                    "monthly_saving_change",
                    "Change in monthly savings in BDT (can be negative).",
                    default=0,
                ),
                "income_change_pct": _number(
                    "income_change_pct",
                    "Percentage change in expected income.",
                    default=0,
                ),
                "expense_change": _number(
                    "expense_change",
                    "Change in expected monthly expenses in BDT.",
                    default=0,
                ),
                "unexpected_expense": _number(
                    "unexpected_expense",
                    "One-off unexpected expense in BDT.",
                    default=0,
                ),
            },
            "required": [],
        },
    },
    {
        "name": "financial_health",
        "description": (
            "Return the seven-dimension financial-health score with reasons "
            "and evidence."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "resilience_score",
        "description": (
            "Return the seven-dimension resilience score including shock-"
            "absorption evidence."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "spending_summary",
        "description": (
            "Return period spending summary with essential/discretionary "
            "breakdown and category breakdown."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "period": _string(
                    "period",
                    "Optional YYYY-MM period. Defaults to the latest month.",
                ),
            },
            "required": [],
        },
    },
    {
        "name": "spending_unusual",
        "description": "Detect unusual transactions relative to the customer's history.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": _string(
                    "period",
                    "Optional YYYY-MM period. Defaults to the latest month.",
                ),
            },
            "required": [],
        },
    },
    {
        "name": "spending_recurring",
        "description": "List detected recurring obligations and their cadence.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "spending_leaks",
        "description": (
            "Detect small frequent purchases that contributed to spend. "
            "Threshold is the BDT ceiling for a 'small' purchase."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "period": _string(
                    "period",
                    "Optional YYYY-MM period. Defaults to the latest month.",
                ),
                "threshold": _number(
                    "threshold",
                    "Maximum BDT amount to qualify as a small frequent purchase.",
                    default=500,
                ),
            },
            "required": [],
        },
    },
    {
        "name": "spending_late_month",
        "description": (
            "Analyse end-of-month spending concentration over the last N "
            "months."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "months": _number(
                    "months",
                    "Lookback window in months.",
                    default=3,
                ),
            },
            "required": [],
        },
    },
    {
        "name": "cash_out_analysis",
        "description": (
            "Quantify cash-out dependency and what share of received funds is "
            "later withdrawn as cash."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "months": _number(
                    "months",
                    "Lookback window in months.",
                    default=3,
                ),
            },
            "required": [],
        },
    },
    {
        "name": "upcoming_bills",
        "description": (
            "List upcoming bills and projected balance before/after each "
            "obligation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days_ahead": _number(
                    "days_ahead",
                    "Calendar window to project bills across.",
                    default=45,
                ),
            },
            "required": [],
        },
    },
    {
        "name": "population_segments",
        "description": (
            "Return the population segmentation derived from behavioural "
            "features. No parameters."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "describe_user",
        "description": (
            "Describe a single customer's behaviour relative to the population "
            "segments."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


def tool_schemas() -> list[dict[str, Any]]:
    """Return the tool schemas in the order they should be advertised."""
    return TOOL_SCHEMAS


__all__ = [
    "ALLOWED_TOOLS",
    "TOOLS",
    "TOOL_SCHEMAS",
    "tool_schemas",
]