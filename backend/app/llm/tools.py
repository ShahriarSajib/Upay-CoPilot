"""Allowlisted tool layer for the LLM.

The only allowed way for an assistant to access numbers is through these tools.
Each tool returns the Pydantic response serialised (or a compact form). No
free-form SQL, no writes, no score changes, and no autonomous credit decisions.
The router between Gemini (primary) and Groq (fallback) must only call these.
"""

from __future__ import annotations

from typing import Any

from app.engines.credit import credit_readiness
from app.engines.forecasting import cashflow_forecast
from app.engines.literacy import financial_literacy
from app.engines.planning import (
    emergency_fund,
    goal_conflicts,
    goal_plan,
    goal_status,
    simulate,
)

ALLOWED_TOOLS = {
    "cashflow_forecast",
    "financial_literacy",
    "credit_readiness",
    "goal_status",
    "goal_plan",
    "goal_conflicts",
    "emergency_fund",
    "simulate",
}


def tool_cashflow_forecast(user_id: str, horizon_days: int = 30) -> dict[str, Any]:
    r = cashflow_forecast(user_id, horizon_days=horizon_days)
    return r.model_dump(mode="json")


def tool_financial_literacy(user_id: str, topic: str | None = None) -> dict[str, Any]:
    r = financial_literacy(user_id, topic=topic)
    return r.model_dump(mode="json")


def tool_credit_readiness(user_id: str) -> dict[str, Any]:
    r = credit_readiness(user_id)
    return r.model_dump(mode="json")


def tool_goal_status(user_id: str) -> dict[str, Any]:
    r = goal_status(user_id)
    return r.model_dump(mode="json")


def tool_goal_plan(user_id: str, target_amount: float, months: float, scenario: str = "balanced") -> dict[str, Any]:
    r = goal_plan(user_id, target_amount=float(target_amount), months=float(months), scenario=scenario)
    return r.model_dump(mode="json")


def tool_goal_conflicts(user_id: str) -> dict[str, Any]:
    r = goal_conflicts(user_id)
    return r.model_dump(mode="json")


def tool_emergency_fund(user_id: str) -> dict[str, Any]:
    r = emergency_fund(user_id)
    return r.model_dump(mode="json")


def tool_simulate(user_id: str, **kwargs: Any) -> dict[str, Any]:
    r = simulate(user_id=user_id, **kwargs)
    return r.model_dump(mode="json")


TOOLS = {
    "cashflow_forecast": tool_cashflow_forecast,
    "financial_literacy": tool_financial_literacy,
    "credit_readiness": tool_credit_readiness,
    "goal_status": tool_goal_status,
    "goal_plan": tool_goal_plan,
    "goal_conflicts": tool_goal_conflicts,
    "emergency_fund": tool_emergency_fund,
    "simulate": tool_simulate,
}
