"""Spending and cash-flow engines.

These engines return EngineResponse objects with evidenced numbers and
deterministic explanations. Important tone rule: when describing small
frequent purchases, we must phrase as "contributed approximately X" and
"may be worth reviewing" — never judgmental terms like "wasted", "leak",
or "burned". This rule is enforced in spending_leaks.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.core.context import get_context
from app.db.store import consumption_mask
from app.schemas.common import (
    Assumption,
    Confidence,
    Direction,
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


def _confidence_from_count(n: int) -> Confidence:
    if n >= 6:
        return Confidence.HIGH
    if n >= 3:
        return Confidence.MEDIUM
    return Confidence.LOW


def _normalize_period(user_id: str, period: str | None) -> str:
    if period is not None:
        return period
    ctx = get_context(user_id)
    return ctx.current_period


def _prev_period_from_ctx(ctx, period: str) -> str | None:
    months = list(ctx.monthly["period"]) if not ctx.monthly.empty else []
    if period in months:
        idx = months.index(period)
        if idx > 0:
            return months[idx - 1]
    try:
        dt = datetime.strptime(period, "%Y-%m")
        return (dt.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m")
    except Exception:
        return None


def _three_month_avg(ctx, exclude_period: str, n: int = 3) -> float | None:
    hist = ctx.monthly
    if hist.empty:
        return None
    relevant = hist[hist["period"] != exclude_period].sort_values("period").tail(n)
    if relevant.empty or len(relevant) == 0:
        relevant = hist.sort_values("period").tail(n)
    if relevant.empty:
        return None
    return float(relevant["spend"].mean())

def spending_summary(user_id: str, period: str | None = None) -> EngineResponse:
    ctx = get_context(user_id)
    p = _normalize_period(user_id, period)
    row = ctx.month_row(p)
    prev_p = _prev_period_from_ctx(ctx, p)
    prev_row = ctx.month_row(prev_p) if prev_p else None
    evidence: list[Evidence] = []
    assumptions: list[Assumption] = []
    metrics: list[Metric] = []

    income = float(row["income"]) if row is not None else 0.0
    spend = float(row["spend"]) if row is not None else 0.0
    net = float(row["net"]) if row is not None else (income - spend)
    window = row["period"] if row is not None else p

    if income < 0:
        income = 0.0
    if spend < 0:
        spend = 0.0

    evidence.append(_evidence("income", income, source="monthly", window=window))
    evidence.append(_evidence("spend", spend, source="monthly", window=window))
    evidence.append(_evidence("net_saved", net, source="monthly", window=window))

    savings_rate = (net / income * 100) if income > 0 else 0.0
    metrics.append(
        Metric(
            key="savings_rate",
            label="Savings rate (%)",
            value=round(savings_rate, 2),
            unit="percent",
            evidence=[evidence[2], evidence[0]],
            confidence=Confidence.MEDIUM,
        )
    )

    if prev_row is not None:
        prev_spend = float(prev_row["spend"])
        change_pct = ((spend - prev_spend) / abs(prev_spend)) * 100 if abs(prev_spend) > 0 else 0.0
        direction = (
            Direction.INCREASE
            if change_pct > 0.5
            else (Direction.DECREASE if change_pct < -0.5 else Direction.FLAT)
        )
        metrics.append(
            Metric(
                key="spend_vs_prev_month",
                label=f"Spend vs previous month ({prev_p})",
                value=round(spend, 2),
                unit="bdt",
                previous_value=round(prev_spend, 2),
                change_percent=round(change_pct, 2),
                direction=direction,
                evidence=[_evidence("spend_prev", prev_spend, source="monthly", window=prev_p)],
            )
        )

    avg3 = _three_month_avg(ctx, exclude_period=p, n=3)
    if avg3 is not None:
        change_pct_avg = ((spend - avg3) / abs(avg3)) * 100 if abs(avg3) > 0 else 0.0
        direction_avg = (
            Direction.INCREASE
            if change_pct_avg > 0.5
            else (Direction.DECREASE if change_pct_avg < -0.5 else Direction.FLAT)
        )
        metrics.append(
            Metric(
                key="spend_vs_3m_avg",
                label="Spend vs own 3-month average",
                value=round(spend, 2),
                unit="bdt",
                previous_value=round(avg3, 2),
                change_percent=round(change_pct_avg, 2),
                direction=direction_avg,
                evidence=[_evidence("spend_3m_avg", avg3, source="monthly", window="last_3_months")],
            )
        )

    tx_p = ctx.transactions[ctx.transactions["timestamp"].dt.strftime("%Y-%m") == p] if not ctx.transactions.empty else ctx.transactions
    cons = tx_p[consumption_mask(tx_p)] if not tx_p.empty else tx_p
    out = cons[cons["direction"] == "outflow"] if not cons.empty else cons
    cat_break = []
    if not out.empty:
        by_cat = out.groupby("category", observed=True)["amount"].sum().sort_values(ascending=False)
        total_spend = by_cat.sum()
        for cat, amt in by_cat.head(5).items():
            share = (amt / total_spend * 100) if total_spend > 0 else 0.0
            cat_break.append({"category": cat, "amount": float(amt), "share_pct": float(share)})
            evidence.append(_evidence(f"spend_category_{cat}", amt, source="transactions", window=p, comparison=f"share {share:.1f}%"))

    headline = f"Spending summary for {p}: income {income:.0f} BDT, spend {spend:.0f} BDT, net {net:.0f} BDT"
    detail = []
    if cat_break:
        detail.append(
            "Top categories: " + ", ".join(f"{c['category']} {c['amount']:.0f} BDT ({c['share_pct']:.1f}%)" for c in cat_break)
        )

    return EngineResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(headline=headline, detail=detail),
        evidence=evidence,
        assumptions=assumptions,
        metrics=metrics,
        insights=[],
    )

def _weekly_spend_range(consumption_df: pd.DataFrame) -> tuple[float, float] | None:
    if consumption_df.empty:
        return None
    out = consumption_df[consumption_df["direction"] == "outflow"].copy()
    if out.empty:
        return None
    out["week"] = out["timestamp"].dt.isocalendar().week
    out["year"] = out["timestamp"].dt.isocalendar().year
    weekly = out.groupby(["year", "week"], observed=True)["amount"].sum().values
    if len(weekly) == 0:
        return None
    p25 = float(np.percentile(weekly, 25))
    p75 = float(np.percentile(weekly, 75))
    return (p25, p75)


def unusual_spending(user_id: str, period: str | None = None) -> EngineResponse:
    ctx = get_context(user_id)
    p = _normalize_period(user_id, period)
    evidence: list[Evidence] = []
    assumptions: list[Assumption] = []
    metrics: list[Metric] = []
    insights: list[Insight] = []

    cons_all = ctx.consumption()
    weekly_range = _weekly_spend_range(cons_all)
    if weekly_range is not None:
        p25, p75 = weekly_range
        evidence.append(_evidence("weekly_spend_p25", p25, source="consumption", window="all_history", comparison="weekly outflow"))
        evidence.append(_evidence("weekly_spend_p75", p75, source="consumption", window="all_history", comparison="weekly outflow"))
        assumptions.append(
            Assumption(
                key="weekly_normal_range",
                value=0.0,
                rationale="Normal weekly spend defined as p25-p75 of weekly consumption outflow totals",
                configurable=True,
            )
        )

    flagged_df = pd.DataFrame()
    try:
        from app.ml import anomaly as anomaly_mod

        bundle = anomaly_mod.load_bundle("anomaly")
        if bundle is not None:
            flagged_df = anomaly_mod.score_anomalies(bundle, ctx.transactions, period=p)
    except Exception:
        flagged_df = pd.DataFrame()

    if not flagged_df.empty:
        flagged = flagged_df[flagged_df["is_flagged"]].copy()
        if not ctx.recurring.empty and "recurring_id" in flagged.columns:
            recurring_ids = set(ctx.recurring["recurring_id"].dropna().astype(str).tolist())
            flagged = flagged[~flagged["recurring_id"].astype(str).isin(recurring_ids)]

        for _, row in flagged.head(10).iterrows():
            insight_evidence: list[Evidence] = []
            insight_evidence.append(_evidence("anomaly_score", float(row.get("anomaly_score", 0.0)), source="anomaly_model", window=p))
            insight_evidence.append(_evidence("amount", float(row.get("amount", 0.0)), source="transactions", window=p))
            why = "The transaction appears unusual compared to the user's typical spending pattern."
            action = "May be worth reviewing the transaction details to confirm it was expected."
            insight = Insight(
                key=f"unusual_{row.get('transaction_id', '?')}",
                title="Unusual transaction",
                observation=f"Transaction of {row.get('amount', 0.0):.0f} BDT in {row.get('category', 'unknown')} flagged as unusual",
                why=why,
                action=action,
                severity=Severity.ATTENTION,
                impact_bdt=float(row.get("amount", 0.0)),
                evidence=insight_evidence,
            )
            insights.append(insight)

    headline = f"Unusual spending detection for {p}"
    detail = [
        "The detector is deliberately conservative, and the injected 'unusual merchant' pattern is hard to catch from a single transaction."
    ]
    if weekly_range is not None:
        p25, p75 = weekly_range
        detail.append(f"Normal weekly spend range (p25-p75 of weekly consumption totals): {p25:.0f}-{p75:.0f} BDT.")

    return EngineResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(headline=headline, detail=detail),
        evidence=evidence,
        assumptions=assumptions,
        metrics=metrics,
        insights=insights,
    )

def recurring_summary(user_id: str) -> EngineResponse:
    ctx = get_context(user_id)
    rec = ctx.recurring.copy() if not ctx.recurring.empty else pd.DataFrame()
    evidence: list[Evidence] = []
    assumptions: list[Assumption] = []
    metrics: list[Metric] = []
    insights: list[Insight] = []

    monthly_equiv = 0.0
    mandatory_total = 0.0
    optional_total = 0.0
    biggest = []

    if not rec.empty:
        for _, row in rec.iterrows():
            amt = float(row.get("amount", 0.0))
            freq = str(row.get("frequency", "monthly")).lower()
            if freq == "monthly":
                me = amt
            elif freq == "weekly":
                me = amt * 4.345
            elif freq == "quarterly":
                me = amt / 3.0
            elif freq == "yearly":
                me = amt / 12.0
            elif freq == "biweekly":
                me = amt * 2.0
            else:
                me = amt
            monthly_equiv += me
            if bool(row.get("mandatory", False)):
                mandatory_total += me
            else:
                optional_total += me

            if "confidence" in row and row.get("confidence") is not None:
                try:
                    n_obs = int(row.get("confidence"))
                except Exception:
                    n_obs = 1
            else:
                n_obs = 1
            conf = _confidence_from_count(n_obs)
            biggest.append((row.get("expense_name") or row.get("category") or "obligation", me, conf, bool(row.get("mandatory", False)), n_obs))

    biggest.sort(key=lambda x: x[1], reverse=True)
    top3 = biggest[:3]

    evidence.append(_evidence("recurring_monthly_equiv", monthly_equiv, source="recurring_expenses", comparison="monthly equivalent total"))
    evidence.append(_evidence("recurring_mandatory", mandatory_total, source="recurring_expenses"))
    evidence.append(_evidence("recurring_optional", optional_total, source="recurring_expenses"))

    assumptions.append(
        Assumption(
            key="monthly_equiv_convention",
            value=4.345,
            rationale="Weekly converted using ~4.345 weeks per month; biweekly treated as 2x monthly equivalent where applicable",
            configurable=True,
        )
    )
    assumptions.append(
        Assumption(
            key="recurring_confidence",
            value=0.0,
            rationale="Confidence based on how many months the obligation was actually observed paid (>=6 HIGH, 3-5 MEDIUM, <3 LOW)",
            configurable=True,
        )
    )

    for name, me, conf, _mandatory, n_obs in top3:
        metrics.append(
            Metric(
                key=f"recurring_top_{name}",
                label=f"Biggest recurring: {name}",
                value=round(me, 2),
                unit="bdt",
                confidence=conf,
                evidence=[_evidence(f"recurring_{name}_months_obs", float(n_obs), source="recurring_expenses", comparison="months observed paid")],
            )
        )

    headline = f"Recurring obligations: ~{monthly_equiv:.0f} BDT/month equivalent"
    detail = []
    if top3:
        detail.append("Biggest 3: " + ", ".join(f"{n} {m:.0f} BDT ({c.value}, obs={o})" for n, m, c, mand, o in top3))
    detail.append(f"Mandatory {mandatory_total:.0f} BDT, optional {optional_total:.0f} BDT")

    return EngineResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(headline=headline, detail=detail),
        evidence=evidence,
        assumptions=assumptions,
        metrics=metrics,
        insights=insights,
    )

def spending_leaks(user_id: str, period: str | None = None, threshold: float = 500.0) -> EngineResponse:
    """Identify small frequent purchases for optional review.

    TONE IS MANDATORY: must phrase as 'contributed approximately X',
    'may be worth reviewing'. NEVER 'wasted', 'leak', 'waste', 'burned'.
    Frame as an optional review area, not a judgement.
    """
    ctx = get_context(user_id)
    p = _normalize_period(user_id, period)
    evidence: list[Evidence] = []
    assumptions: list[Assumption] = []
    metrics: list[Metric] = []
    insights: list[Insight] = []

    assumptions.append(
        Assumption(
            key="small_purchase_threshold_bdt",
            value=float(threshold),
            rationale="Threshold for 'small' purchases (default 500 BDT)",
            configurable=True,
        )
    )

    tx_p = ctx.transactions[ctx.transactions["timestamp"].dt.strftime("%Y-%m") == p] if not ctx.transactions.empty else ctx.transactions
    cons = tx_p[consumption_mask(tx_p)] if not tx_p.empty else tx_p
    out = cons[cons["direction"] == "outflow"] if not cons.empty else cons
    small = out[out["amount"] < threshold] if not out.empty else out

    total_spend_period = float(out["amount"].sum()) if not out.empty else 0.0
    count_small = int(len(small)) if not small.empty else 0
    total_small = float(small["amount"].sum()) if not small.empty else 0.0

    evidence.append(_evidence("small_purchases_count", float(count_small), source="transactions", window=p))
    evidence.append(_evidence("small_purchases_total", total_small, source="transactions", window=p))
    evidence.append(_evidence("total_spend_period", total_spend_period, source="transactions", window=p))

    share = (total_small / total_spend_period * 100) if total_spend_period > 0 else 0.0
    metrics.append(
        Metric(
            key="small_purchases_share",
            label="Small purchases as share of spend",
            value=round(share, 2),
            unit="percent",
            evidence=[evidence[1], evidence[2]],
        )
    )

    top_small_cats = []
    if not small.empty:
        by_cat = small.groupby("category", observed=True)["amount"].sum().sort_values(ascending=False)
        for cat, amt in by_cat.head(3).items():
            top_small_cats.append({"category": cat, "amount": float(amt)})
            evidence.append(_evidence(f"small_cat_{cat}", amt, source="transactions", window=p))

    headline = f"In {p}, small frequent purchases (under {int(threshold)} BDT) contributed approximately {total_small:.0f} BDT across {count_small} transactions"
    detail = ["This is an optional review area and may be worth reviewing if it doesn't align with priorities."]
    if top_small_cats:
        detail.append("Top small-purchase categories: " + ", ".join(f"{c['category']} {c['amount']:.0f} BDT" for c in top_small_cats))

    observation = f"Small purchases under {int(threshold)} BDT contributed approximately {total_small:.0f} BDT in {p}"
    why = "Frequent small transactions can add up over time; reviewing them is optional."
    action = "May be worth reviewing which of these small purchases were necessary or could be consolidated."
    insights.append(
        Insight(
            key="small_frequent_purchases",
            title="Small frequent purchases (optional review)",
            observation=observation,
            why=why,
            action=action,
            severity=Severity.INFO,
            impact_bdt=total_small,
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

def late_month_analysis(user_id: str, months: int = 3) -> EngineResponse:
    ctx = get_context(user_id)
    evidence: list[Evidence] = []
    assumptions: list[Assumption] = []
    metrics: list[Metric] = []
    insights: list[Insight] = []

    assumptions.append(
        Assumption(
            key="late_month_windows",
            value=0.0,
            rationale="Spend split into days 1-10, 11-20, 21-31 for late-month pressure analysis",
            configurable=True,
        )
    )

    tx = ctx.transactions
    cons = tx[consumption_mask(tx)] if not tx.empty else tx
    out = cons[cons["direction"] == "outflow"].copy() if not cons.empty else pd.DataFrame()
    if not out.empty:
        out["period"] = out["timestamp"].dt.strftime("%Y-%m")
        out["day"] = out["timestamp"].dt.day

    recent_months = list(ctx.monthly["period"].sort_values())[-months:] if not ctx.monthly.empty else []
    band_data = []
    for m in recent_months:
        m_out = out[out["period"] == m] if not out.empty else pd.DataFrame()
        total_m = float(m_out["amount"].sum()) if not m_out.empty else 0.0
        for start, end, label in [(1, 10, "d1_10"), (11, 20, "d11_20"), (21, 31, "d21_31")]:
            band = m_out[(m_out["day"] >= start) & (m_out["day"] <= end)] if not m_out.empty else pd.DataFrame()
            mean_band = float(band["amount"].mean()) if not band.empty else 0.0
            sum_band = float(band["amount"].sum()) if not band.empty else 0.0
            share = (sum_band / total_m * 100) if total_m > 0 else 0.0
            top_cats = []
            if not band.empty:
                by_cat = band.groupby("category", observed=True)["amount"].sum().sort_values(ascending=False)
                for cat, amt in by_cat.head(2).items():
                    top_cats.append({"category": cat, "amount": float(amt)})
            band_data.append({
                "month": m,
                "window": label,
                "mean": mean_band,
                "sum": sum_band,
                "share_pct": share,
                "top_categories": top_cats,
            })

    late_means = [b["mean"] for b in band_data if b["window"] == "d21_31"]
    late_mean = float(np.mean(late_means)) if late_means else 0.0
    evidence.append(_evidence("late_window_mean_d21_31", late_mean, source="transactions", window=f"last_{months}_months"))

    metrics.append(
        Metric(
            key="projected_monthend_gain",
            label="Projected month-end balance gain from reducing discretionary spend in days 21-31 by ~X",
            value=round(late_mean, 2),
            unit="bdt",
            evidence=[evidence[-1]],
        )
    )

    headline = f"Late-month pressure analysis over last {months} months (split by day bands)"
    detail = [
        f"Mean spend in days 21-31: {late_mean:.0f} BDT across last {months} months.",
        f"Reducing discretionary spending in days 21-31 by about {late_mean:.0f} BDT per month raises the projected month-end balance by about {late_mean:.0f} BDT.",
    ]

    if band_data:
        last_third_shares = [b["share_pct"] for b in band_data if b["window"] == "d21_31"]
        if last_third_shares:
            detail.append(f"Share of total spend in last third (days 21-31) ranges: {min(last_third_shares):.1f}%-{max(last_third_shares):.1f}%")

    resp = EngineResponse(
        user_id=user_id,
        as_of=ctx.as_of.date().isoformat(),
        explanation=Explanation(headline=headline, detail=detail),
        evidence=evidence,
        assumptions=assumptions,
        metrics=metrics,
        insights=insights,
    )
    resp.assumptions.append(Assumption(key="day_band_profile", value=len(band_data), rationale=str(band_data), configurable=False))
    return resp
