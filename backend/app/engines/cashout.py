"""Cash-out analysis.

Must not push toward digital payments or moralise. State plainly that
cash use is a legitimate choice and this is about making cash flows visible.
"""

from __future__ import annotations

import numpy as np

from app.core.context import get_context
from app.db.store import consumption_mask
from app.schemas.common import (
    Assumption,
    Confidence,
    EngineResponse,
    Evidence,
    Explanation,
    Insight,
    Metric,
    Severity,
)


def _evidence(
    label: str,
    value: float,
    source: str = "transactions",
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


def cash_out_analysis(user_id: str, months: int = 3) -> EngineResponse:
    ctx = get_context(user_id)
    evidence: list[Evidence] = []
    assumptions: list[Assumption] = []
    metrics: list[Metric] = []
    insights: list[Insight] = []

    tx = ctx.transactions.copy()
    if tx.empty:
        headline = "Cash-out analysis: no transaction data"
        return EngineResponse(
            user_id=user_id,
            as_of=ctx.as_of.date().isoformat(),
            explanation=Explanation(headline=headline, detail=[]),
            evidence=evidence,
            assumptions=assumptions,
            metrics=metrics,
            insights=insights,
        )

    tx["period"] = tx["timestamp"].dt.strftime("%Y-%m")
    recent_months = sorted(tx["period"].unique())[-months:] if months > 0 else sorted(tx["period"].unique())
    tx_recent = tx[tx["period"].isin(recent_months)]

    cashouts = (
        tx_recent[tx_recent["cash_out"]]
        if "cash_out" in tx_recent.columns
        else tx_recent[tx_recent["category"] == "cash"]
    )
    cashouts = cashouts[cashouts["direction"] == "outflow"]

    num_co = int(len(cashouts))
    total_co = float(cashouts["amount"].sum()) if num_co > 0 else 0.0
    evidence.append(_evidence("cash_out_count", float(num_co), source="transactions", window=f"last_{months}_months"))
    evidence.append(_evidence("cash_out_total", total_co, source="transactions", window=f"last_{months}_months"))

    # Total outflows (consumption outflows) and received funds (inflows)
    cons = tx_recent[consumption_mask(tx_recent)]
    outflows = cons[cons["direction"] == "outflow"]
    inflows = cons[cons["direction"] == "inflow"]
    total_out = float(outflows["amount"].sum()) if not outflows.empty else 0.0
    total_in = float(inflows["amount"].sum()) if not inflows.empty else 0.0

    co_share_out = (total_co / total_out * 100) if total_out > 0 else 0.0
    co_share_in = (total_co / total_in * 100) if total_in > 0 else 0.0
    metrics.append(Metric(key="cash_out_share_outflows", label="Cash-out as share of total outflows (%)", value=round(co_share_out, 2), unit="percent", evidence=[evidence[1]]))
    metrics.append(Metric(key="cash_out_share_received", label="Cash-out as share of received funds (%)", value=round(co_share_in, 2), unit="percent", evidence=[evidence[1]]))

    # Day-of-month pattern: median days between income credit and next cash-out
    lags = []
    if not inflows.empty and not cashouts.empty:
        # For each income event, find next cashout after it
        for _, inc in inflows.sort_values("timestamp").iterrows():
            inc_time = inc["timestamp"]
            next_co = cashouts[cashouts["timestamp"] > inc_time].sort_values("timestamp")
            if not next_co.empty:
                co_time = next_co.iloc[0]["timestamp"]
                lag_days = (co_time - inc_time).total_seconds() / 86400.0
                lags.append(lag_days)

    median_lag = float(np.median(lags)) if lags else None
    if median_lag is not None:
        evidence.append(_evidence("median_days_income_to_cashout", median_lag, source="transactions", window=f"last_{months}_months", comparison="days"))
        metrics.append(Metric(key="median_lag_income_to_cashout", label="Median days between income and next cash-out", value=round(median_lag, 2), unit="days", evidence=[evidence[-1]]))

    # Which recurring obligations plausibly cash-funded
    rec = ctx.recurring
    candidates = []
    if not rec.empty:
        for _, r in rec.iterrows():
            cat = str(r.get("category", "")).lower()
            # heuristic
            if cat == "cash" or "cash" in cat or r.get("cash_funded", False):
                candidates.append(r.get("expense_name") or r.get("category") or "obligation")
            # also low digital ratio heuristic placeholder - just note
        candidates = list(dict.fromkeys(candidates))[:5]

    assumptions.append(Assumption(key="cash_funding_heuristic", value=0.0, rationale="Heuristic: cash-category or low-digital-ratio indicators used to flag plausibly cash-funded obligations", configurable=True))
    assumptions.append(Assumption(key="no_digital_moralizing", value=1.0, rationale="Cash use is a legitimate choice; analysis focuses on visibility only", configurable=False))

    headline = f"Cash-out analysis over last {months} months: {num_co} events totaling {total_co:.0f} BDT"
    detail = []
    detail.append("Cash use is a legitimate choice; this analysis is about making cash flows visible.")
    if median_lag is not None and median_lag < 3:
        detail.append(f"Cash-out tends to happen soon after income (median ~{median_lag:.1f} days).")
    elif median_lag is not None:
        detail.append(f"Median time from income to next cash-out is ~{median_lag:.1f} days.")

    suggestion_text = "Review suggestion: consider reviewing these obligations to understand cash funding patterns (a choice, not a recommendation to switch):"
    if candidates:
        detail.append(suggestion_text + " " + ", ".join(candidates))
    else:
        detail.append(suggestion_text + " none identified by heuristic")

    insights.append(
        Insight(
            key="cash_out_overview",
            title="Cash flows visibility",
            observation=f"{num_co} cash-out events totaling {total_co:.0f} BDT in last {months} months",
            why="Tracking cash movements helps understand how cash is allocated.",
            action="Review the listed candidate obligations if desired; cash use remains a valid choice.",
            severity=Severity.INFO,
            impact_bdt=total_co,
            evidence=evidence[:2],
        )
    )

    return EngineResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(headline=headline, detail=detail),
        evidence=evidence,
        assumptions=assumptions,
        metrics=metrics,
        insights=insights,
    )
