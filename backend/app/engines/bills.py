"""Upcoming bills and calendar.

Projects recurring obligations forward, respecting month length (clamp due_day
to last valid day of each month). Reports totals and projected balance impact.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

import pandas as pd

from app.core.context import get_context
from app.schemas.common import (
    Assumption,
    Confidence,
    EngineResponse,
    Evidence,
    Explanation,
    Metric,
)


def _confidence_from_count(n: int) -> Confidence:
    if n >= 6:
        return Confidence.HIGH
    if n >= 3:
        return Confidence.MEDIUM
    return Confidence.LOW


def _evidence(
    label: str,
    value: float,
    source: str = "recurring_expenses",
    window: str | None = None,
    comparison: str | None = None,
    confidence: Confidence = Confidence.MEDIUM,
) -> Evidence:
    return Evidence(
        label=label,
        value=float(round(value, 2)),
        unit="bdt",
        source=source,
        window=window,
        comparison=comparison,
        confidence=confidence,
    )




def _clamp_due_day(year: int, month: int, due_day: int) -> int:
    if due_day is None:
        return 1
    last = monthrange(year, month)[1]
    return min(int(due_day), last)


def bill_calendar(user_id: str, days_ahead: int = 45) -> list[dict]:
    ctx = get_context(user_id)
    rec = ctx.recurring.copy() if not ctx.recurring.empty else pd.DataFrame()
    as_of = ctx.as_of.date()

    entries = []
    if rec.empty:
        return entries

    for _, row in rec.iterrows():
        due_day = row.get("due_day")
        if due_day is None or pd.isna(due_day):
            continue
        amount = float(row.get("amount", 0.0))
        label = row.get("expense_name") or row.get("category") or "bill"
        category = row.get("category") or "other"
        mandatory = bool(row.get("mandatory", False))
        if "confidence" in row and row.get("confidence") is not None:
            try:
                n_obs = int(row.get("confidence"))
            except Exception:
                n_obs = 1
        else:
            n_obs = 1
        conf = _confidence_from_count(n_obs)

        cur = as_of.replace(day=1)
        for _ in range(0, 12):
            year, month = cur.year, cur.month
            d = _clamp_due_day(year, month, int(due_day))
            due_date = date(year, month, d)
            if due_date < as_of:
                cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
                continue
            days_until = (due_date - as_of).days
            if days_until > days_ahead:
                cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
                continue
            entries.append(
                {
                    "due_date": due_date.isoformat(),
                    "label": str(label),
                    "category": str(category),
                    "amount": round(amount, 2),
                    "confidence": conf.value,
                    "days_until": days_until,
                    "mandatory": mandatory,
                }
            )
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
            if days_until > days_ahead:
                pass

    entries.sort(key=lambda x: (x["due_date"], x["amount"]))
    return entries


def upcoming_bills(user_id: str, days_ahead: int = 45) -> EngineResponse:
    ctx = get_context(user_id)
    evidence: list[Evidence] = []
    assumptions: list[Assumption] = []
    metrics: list[Metric] = []

    assumptions.append(
        Assumption(
            key="due_day_clamping",
            value=1.0,
            rationale="Bills due on 31st land on last valid day of shorter months",
            configurable=False,
        )
    )
    assumptions.append(
        Assumption(
            key="projection_window_days",
            value=float(days_ahead),
            rationale="Bills projected forward from as_of by days_ahead",
            configurable=True,
        )
    )

    cal = bill_calendar(user_id, days_ahead=days_ahead)
    total_due = sum(float(e["amount"]) for e in cal)

    bal_upay = 0.0
    if not ctx.wallets.empty:
        upay = ctx.wallets[ctx.wallets["wallet_type"] == "upay"]
        if not upay.empty:
            bal_upay = float(upay.iloc[0].get("balance", 0.0))
    if bal_upay == 0.0 and not ctx.monthly.empty and "ending_balance" in ctx.monthly:
        bal_upay = float(ctx.monthly["ending_balance"].mean())

    projected_after = bal_upay - total_due
    evidence.append(_evidence("total_due_window", total_due, source="recurring_expenses", window=f"next_{days_ahead}_days"))
    evidence.append(_evidence("current_balance_upay", bal_upay, source="wallets", comparison="upay balance or mean ending"))
    metrics.append(Metric(key="total_due_in_window", label=f"Total due in next {days_ahead} days", value=round(total_due, 2), unit="bdt", evidence=[evidence[0]]))
    metrics.append(Metric(key="projected_balance_after_bills", label="Projected balance after all bills in window", value=round(projected_after, 2), unit="bdt", evidence=[evidence[1], evidence[0]]))

    by_month: dict[str, list] = {}
    for e in cal:
        m = e["due_date"][:7]
        by_month.setdefault(m, []).append(e)

    headline = f"{len(cal)} bills due in next {days_ahead} days, total {total_due:.0f} BDT"
    detail = [f"Projected balance after all of them: {projected_after:.0f} BDT (based on current balance)."]
    for m, items in sorted(by_month.items()):
        detail.append(f"{m}: " + ", ".join(f"{i['label']} {i['amount']:.0f} BDT" for i in items[:3]))

    return EngineResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(headline=headline, detail=detail),
        evidence=evidence,
        assumptions=assumptions,
        metrics=metrics,
        insights=[],
    )
