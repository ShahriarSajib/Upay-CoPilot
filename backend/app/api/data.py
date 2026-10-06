from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.core.config import settings
from app.db.store import cached_store

router = APIRouter(prefix="/api", tags=["data"])


def _records(name: str) -> list[dict]:
    frame = cached_store().table(name).copy()
    frame = frame.astype(object).where(frame.notna(), None)
    for column in frame.columns:
        if column in {"timestamp", "target_date", "created_date", "next_due_date"}:
            frame[column] = frame[column].map(
                lambda value: value.isoformat() if hasattr(value, "isoformat") else value
            )
    return frame.to_dict("records")


@router.get("/dataset")
def dataset(_: dict = Depends(current_user)):
    """Return the same generated tables used by the engines to authenticated clients."""
    store = cached_store()
    return {
        "meta": {
            "source": "postgres" if settings.use_postgres else str(settings.data_root),
            "currency": "BDT",
            "label_columns": ["persona", "is_anomaly", "pattern_type"],
        },
        "cohort": store.users()["user_id"].tolist(),
        "tables": {
            "users": _records("users"),
            "wallets": _records("wallets"),
            "income_events": _records("income_events"),
            "recurring_expenses": _records("recurring_expenses"),
            "transactions": _records("transactions"),
            "financial_goals": _records("financial_goals"),
            "goal_contributions": _records("goal_contributions"),
            "financial_profiles": _records("financial_profiles"),
            "behavior_labels": _records("behavior_labels"),
            "injected_patterns": _records("injected_patterns"),
        },
    }
