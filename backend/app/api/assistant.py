"""Assistant and intent routes.

The assistant never computes. It routes to the allowlisted tool layer; if no
provider is configured the endpoint degrades to a deterministic answer rather
than failing, because a product that stops working when a model is down is not
a financial product.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.engines.credit import credit_readiness
from app.engines.forecasting import cashflow_forecast
from app.engines.literacy import financial_literacy
from app.engines.planning import emergency_fund, goal_status
from app.llm.router import RouterError, router_answer

router = APIRouter(prefix="/api", tags=["assistant"])


class ChatRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=2000)


class IntentRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=2000)


# Deterministic intent -> engine map. This is the fallback when no LLM is
# configured, and the *only* thing the intent endpoint trusts.
INTENT_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("overdraft", "run out", "short", "shortage", "end of month"), "cashflow_forecast"),
    (("save for", "goal", "target", "education", "laptop", "travel"), "goal_status"),
    (("emergency", "buffer", "rainy day", "safety net"), "emergency_fund"),
    (("credit", "loan", "ready", "eligib"), "credit_readiness"),
    (("learn", "literacy", "skill", "budget", "how do i"), "financial_literacy"),
]


def detect_intent(message: str) -> str:
    text = message.lower()
    for keywords, intent in INTENT_KEYWORDS:
        if any(word in text for word in keywords):
            return intent
    return "cashflow_forecast"


def _deterministic_answer(user_id: str, intent: str) -> dict:
    if intent == "goal_status":
        result = goal_status(user_id)
    elif intent == "emergency_fund":
        result = emergency_fund(user_id)
    elif intent == "credit_readiness":
        result = credit_readiness(user_id)
    elif intent == "financial_literacy":
        result = financial_literacy(user_id)
    else:
        result = cashflow_forecast(user_id, horizon_days=30)
    headline = result.explanation.headline if result.explanation else "Here is what I found."
    return {
        "answer": headline,
        "tool": intent,
        "grounded": True,
        "provider": "deterministic",
        "result": result.model_dump(mode="json"),
    }


@router.post("/assistant")
def assistant(body: ChatRequest):
    try:
        return router_answer(body.message, user_id=body.user_id)
    except RouterError:
        # No provider configured or both unavailable: deterministic answer.
        return _deterministic_answer(body.user_id, detect_intent(body.message))
    except KeyError as exc:
        raise HTTPException(404, f"unknown user {body.user_id}") from exc


@router.post("/intent")
def intent(body: IntentRequest):
    name = detect_intent(body.message)
    return _deterministic_answer(body.user_id, name)
