"""Additional deterministic engine routes.

These wrap engines that existed before the ML work. They follow the same rule:
numbers come from the engine, never from a model.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.context import get_context, list_users
from app.engines.bills import upcoming_bills
from app.engines.cashout import cash_out_analysis
from app.engines.health import financial_health
from app.engines.resilience import resilience_score
from app.engines.segmentation import describe_user, population_segments
from app.engines.spending import (
    late_month_analysis,
    recurring_summary,
    spending_leaks,
    spending_summary,
    unusual_spending,
)
from app.ml.artifacts import list_cards

router = APIRouter(prefix="/api", tags=["engines"])


def _guarded(fn, user_id: str, *args, **kwargs):
    try:
        return fn(user_id, *args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {user_id}") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/users")
def users():
    frame = list_users()
    return {
        "count": int(len(frame)),
        "users": frame.to_dict("records") if hasattr(frame, "to_dict") else frame,
    }


@router.get("/models")
def models():
    return {"cards": list_cards()}


@router.get("/health/{user_id}")
def health(user_id: str):
    return _guarded(financial_health, user_id)


@router.get("/resilience/{user_id}")
def resilience(user_id: str):
    return _guarded(resilience_score, user_id)


@router.get("/spending/{user_id}")
def spending(user_id: str, period: str | None = None):
    return _guarded(spending_summary, user_id, period=period)


@router.get("/spending/{user_id}/unusual")
def spending_unusual(user_id: str, period: str | None = None):
    return _guarded(unusual_spending, user_id, period=period)


@router.get("/spending/{user_id}/recurring")
def spending_recurring(user_id: str):
    return _guarded(recurring_summary, user_id)


@router.get("/spending/{user_id}/leaks")
def spending_leaks_route(user_id: str, period: str | None = None, threshold: float = 500.0):
    return _guarded(spending_leaks, user_id, period=period, threshold=threshold)


@router.get("/spending/{user_id}/late-month")
def spending_late(user_id: str, months: int = 3):
    return _guarded(late_month_analysis, user_id, months=months)


@router.get("/cashout/{user_id}")
def cashout(user_id: str, months: int = 3):
    return _guarded(cash_out_analysis, user_id, months=months)


@router.get("/bills/{user_id}")
def bills(user_id: str, days_ahead: int = 45):
    return _guarded(upcoming_bills, user_id, days_ahead=days_ahead)


@router.get("/segments")
def segments():
    return {"segments": population_segments()}


@router.get("/segments/{user_id}")
def segment_for_user(user_id: str):
    return _guarded(describe_user, user_id)


@router.get("/context/{user_id}")
def context(user_id: str):
    return _guarded(lambda uid: get_context(uid).summary(), user_id)
