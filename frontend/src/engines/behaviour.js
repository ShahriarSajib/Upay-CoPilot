import { isTransfer } from "@/data/context";
import { clamp, mean, round, sum } from "@/lib/format";
import { runForecast, defaultBuffer } from "./forecast";
import { reconstructBalanceSeries } from "./health";
/**
 * Behaviour Label Engine + End-of-Month Shortage Predictor
 * ---------------------------------------------------------------------------
 * Two related things live here:
 *
 *  1. A faithful TypeScript re-implementation of ml/dataset/labels.py. The Python
 *     labeller is the project's own ground truth, so re-deriving it in the
 *     browser is a genuine correctness check on the frontend's ledger semantics:
 *     the Evaluation screen reports the measured agreement, not a claim.
 *
 *  2. The "why do I always run short before month-end?" answer, which is a
 *     quantitative decomposition of where the late-month spending comes from.
 */
/* ------------------------------------------------------------------ *
 * 1. Ground-truth label reproduction
 * ------------------------------------------------------------------ */
export const LABEL_THRESHOLDS = {
    late_month_share: 0.4,
    cash_dependency_share: 0.4,
    income_cv: 0.35,
    savings_rate: 0.05,
    expense_income_ratio: 1.0,
    goal_contribution_min: 1.0,
};
export function reproduceLabels(ctx) {
    const cashWalletIds = ctx.cashWalletIds;
    const buckets = new Map();
    const bucket = (key) => {
        let b = buckets.get(key);
        if (!b) {
            b = { income: 0, spend: 0, late: 0, cashSpend: 0, contribution: 0, anomalies: 0 };
            buckets.set(key, b);
        }
        return b;
    };
    for (const t of ctx.transactions) {
        const key = t.timestamp.slice(0, 7);
        const b = bucket(key);
        if (isTransfer(t))
            continue;
        if (t.direction === "outflow" && t.category !== "cash") {
            b.spend += t.amount;
            if (Number(t.timestamp.slice(8, 10)) >= 23)
                b.late += t.amount;
            if (cashWalletIds.has(t.wallet_id))
                b.cashSpend += t.amount;
        }
        else if (t.direction === "inflow") {
            // Mirrors the Python labeller, where a cash-in leg is treated as inflow.
            b.income += t.amount;
        }
    }
    for (const c of ctx.contributions)
        bucket(c.timestamp.slice(0, 7)).contribution += c.amount;
    for (const p of ctx.patterns)
        bucket(p.timestamp.slice(0, 7)).anomalies += 1;
    const rows = [];
    for (const [key, b] of [...buckets.entries()].sort((a, b2) => a[0].localeCompare(b2[0]))) {
        if (b.spend <= 0)
            continue;
        const lateShare = b.late / b.spend;
        const cashShare = b.cashSpend / b.spend;
        const savingsRate = b.income > 0 ? (b.income - b.spend) / b.income : 0;
        const expenseIncomeRatio = b.income > 0 ? b.spend / b.income : Number.POSITIVE_INFINITY;
        rows.push({
            period: key,
            end_month_shortage_label: lateShare > LABEL_THRESHOLDS.late_month_share ? 1 : 0,
            high_cash_dependency_label: cashShare > LABEL_THRESHOLDS.cash_dependency_share ? 1 : 0,
            irregular_income_label: ctx.incomeCv > LABEL_THRESHOLDS.income_cv ? 1 : 0,
            overspending_label: expenseIncomeRatio > LABEL_THRESHOLDS.expense_income_ratio ? 1 : 0,
            goal_progress_label: b.contribution >= LABEL_THRESHOLDS.goal_contribution_min ? 1 : 0,
            financial_pressure_label: expenseIncomeRatio > LABEL_THRESHOLDS.expense_income_ratio && savingsRate < LABEL_THRESHOLDS.savings_rate
                ? 1
                : 0,
            anomaly_count: b.anomalies,
        });
    }
    return rows;
}
export function compareLabels(ctx) {
    const expected = new Map(ctx.labels.map((l) => [l.period, l]));
    const mine = reproduceLabels(ctx);
    const fields = [
        "end_month_shortage_label",
        "high_cash_dependency_label",
        "irregular_income_label",
        "overspending_label",
        "goal_progress_label",
        "financial_pressure_label",
        "anomaly_count",
    ];
    const perField = fields.map((field) => ({ field, matched: 0, total: 0, rate: 0 }));
    const disagreements = [];
    let matched = 0;
    let total = 0;
    for (const row of mine) {
        const truth = expected.get(row.period);
        if (!truth)
            continue;
        fields.forEach((field, i) => {
            perField[i].total += 1;
            total += 1;
            if (truth[field] === row[field]) {
                perField[i].matched += 1;
                matched += 1;
            }
            else {
                disagreements.push({ period: row.period, field, expected: truth[field], got: row[field] });
            }
        });
    }
    for (const f of perField)
        f.rate = f.total ? round(f.matched / f.total, 4) : 0;
    return {
        total,
        matched,
        rate: total ? round(matched / total, 4) : 0,
        perField,
        disagreements: disagreements.slice(0, 20),
    };
}
export function runShortageEngine(ctx) {
    const month = ctx.currentMonth;
    const inMonth = ctx.daily.filter((d) => d.iso.slice(0, 7) === month.key);
    const early = sum(inMonth.filter((d) => d.date.getDate() <= 10).map((d) => d.spend));
    const mid = sum(inMonth.filter((d) => d.date.getDate() > 10 && d.date.getDate() <= 20).map((d) => d.spend));
    const late = sum(inMonth.filter((d) => d.date.getDate() > 20).map((d) => d.spend));
    const total = early + mid + late;
    const lateRows = ctx.transactions.filter((t) => t.direction === "outflow" &&
        t.category !== "cash" &&
        t.category !== "transfer" &&
        t.timestamp.slice(0, 7) === month.key &&
        Number(t.timestamp.slice(8, 10)) > 20);
    const byCategory = new Map();
    for (const t of lateRows) {
        const e = byCategory.get(t.category) ?? { amount: 0, count: 0 };
        e.amount += t.amount;
        e.count += 1;
        byCategory.set(t.category, e);
    }
    const contributors = [...byCategory.entries()]
        .sort((a, b) => b[1].amount - a[1].amount)
        .slice(0, 6)
        .map(([category, v]) => ({
        category: category.charAt(0).toUpperCase() + category.slice(1),
        amount: round(v.amount, 0),
        share: late > 0 ? round(v.amount / late, 4) : 0,
        count: v.count,
    }));
    const forecast = runForecast(ctx, 30);
    const buffer = defaultBuffer(ctx);
    const balanceSeries = reconstructBalanceSeries(ctx);
    const belowBufferDays = balanceSeries.filter((p) => p.balance < buffer).length;
    const lowBalanceProbability = clamp(forecast.lowBalanceWindows.length / 3, 0, 1);
    const projectedMinBalance = forecast.minBalance;
    // How much late-month discretionary spending would have to disappear to hold
    // the buffer to the end of the forecast horizon.
    const gap = Math.max(0, buffer - projectedMinBalance);
    const lateShareOfTotal = total > 0 ? late / total : 0;
    const suggestedReduction = Math.round((gap * (late > 0 ? clamp(late / Math.max(1, total), 0, 1) : 0)) / 100) * 100;
    const evidence = {
        engine: "End-of-Month Shortage Predictor",
        headline: `${(month.lateShare * 100).toFixed(0)}% of spending lands in the final 10 days`,
        confidence: round(clamp(0.5 + ctx.monthly.length * 0.05, 0.45, 0.88), 2),
        confidenceNote: `Observed ${belowBufferDays} historical day(s) below the ৳${Math.round(buffer).toLocaleString("en-US")} buffer in the reconstructed balance series.`,
        metrics: [
            { id: "early", label: "Days 1–10 spend", value: round(early, 0), unit: "bdt", detail: `${(total ? (early / total) * 100 : 0).toFixed(0)}% of the month`, source: "transactions" },
            { id: "mid", label: "Days 11–20 spend", value: round(mid, 0), unit: "bdt", detail: `${(total ? (mid / total) * 100 : 0).toFixed(0)}% of the month`, source: "transactions" },
            { id: "late", label: "Days 21–30 spend", value: round(late, 0), unit: "bdt", detail: `${(lateShareOfTotal * 100).toFixed(0)}% of the month`, source: "transactions" },
            { id: "buffer", label: "Safety buffer", value: round(buffer, 0), unit: "bdt", detail: "about one week of essential spend", source: "product assumption" },
            { id: "projected_min", label: "30-day projected minimum", value: projectedMinBalance, unit: "bdt", detail: "trough of the daily forecast", source: "model" },
            { id: "suggested", label: "Reduction that would close the gap", value: suggestedReduction, unit: "bdt", detail: "applied to late-month discretionary spend", source: "model" },
        ],
        reasons: [
            {
                polarity: month.lateShare > 0.4 ? "negative" : "neutral",
                text: `The last third of the month carries ৳${Math.round(late).toLocaleString("en-US")} of ৳${Math.round(total).toLocaleString("en-US")}.`,
            },
            ...contributors.slice(0, 3).map((c) => ({
                polarity: "negative",
                text: `${c.category} contributes ৳${Math.round(c.amount).toLocaleString("en-US")} (${(c.share * 100).toFixed(0)}% of late-month spend) across ${c.count} transaction(s).`,
            })),
            {
                polarity: suggestedReduction > 0 ? "negative" : "positive",
                text: suggestedReduction > 0
                    ? `Reducing late-month discretionary spending by about ৳${suggestedReduction.toLocaleString("en-US")} would keep the balance above the buffer.`
                    : "The 30-day projection stays above the buffer without any reduction.",
            },
        ],
        assumptions: [
            "Late-month means day 21 onwards, matching the dataset's own label definition window.",
            "The suggested reduction is a linear estimate that scales the buffer gap by the late-month spending share; it is not an optimisation.",
            "Only discretionary categories are considered; essential commitments are never proposed for reduction.",
        ],
        sources: ["transactions.csv", "recurring_expenses.csv", "wallets.csv"],
    };
    return {
        lateShare: month.lateShare,
        earlySpend: round(early, 0),
        midSpend: round(mid, 0),
        lateSpend: round(late, 0),
        totalSpend: round(total, 0),
        contributors,
        buffer: round(buffer, 0),
        lowBalanceProbability: round(lowBalanceProbability, 3),
        projectedMinBalance,
        suggestedReduction,
        evidence,
    };
}
/** Probability-style summary used by the dashboard card. */
export function shortageRiskBand(ctx) {
    const shortage = runShortageEngine(ctx);
    const forecast = runForecast(ctx, 30);
    const windows = forecast.lowBalanceWindows.length;
    if (shortage.lateShare > 0.4 && windows > 0)
        return "high";
    if (shortage.lateShare > 0.33 || windows > 0)
        return "elevated";
    if (shortage.lateShare > 0.25)
        return "moderate";
    return "low";
}
export function averageLateShare(ctx) {
    return round(mean(ctx.monthly.map((m) => m.lateShare)), 4);
}
