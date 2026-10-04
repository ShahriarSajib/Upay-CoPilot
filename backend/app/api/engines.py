"""API version of deterministic engines.

Return only pre-computed, evidenced values. No generation. These endpoints
are what the LLM tool layer must call -- never recompute the numbers.
"""

from fastapi import APIRouter, HTTPException

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

router = APIRouter(prefix="/api", tags=["engines"])


@router.get("/forecast/{user_id}")
def forecast(user_id: str, horizon_days: int = 30):
    try:
        return cashflow_forecast(user_id, horizon_days=horizon_days)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc


@router.get("/literacy/{user_id}")
def literacy(user_id: str, topic: str | None = None):
    try:
        return financial_literacy(user_id, topic=topic)
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc


@router.get("/credit/readiness/{user_id}")
def readiness(user_id: str):
    try:
        return credit_readiness(user_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc


@router.get("/goals/status/{user_id}")
def goals_status(user_id: str):
    try:
        return goal_status(user_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc


@router.get("/goals/plan/{user_id}")
def goals_plan(user_id: str, target: float, months: int, scenario: str = "balanced"):
    try:
        return goal_plan(user_id, target_amount=float(target), months=float(months), scenario=scenario)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc


@router.get("/goals/conflicts/{user_id}")
def goals_conflicts(user_id: str):
    try:
        return goal_conflicts(user_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc


@router.get("/emergency/{user_id}")
def emergency(user_id: str):
    try:
        return emergency_fund(user_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc


@router.post("/simulate")
def simulate_scenario(user_id: str, body: dict):
    try:
        return simulate(user_id=user_id, **body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}: {exc}") from exc

