import { bandFor, clamp, coefficientOfVariation, mean, quantiles, round, sum } from "@/lib/format";
import { runCashOutEngine } from "./cashout";
import { goalProgressRatio } from "./health";
export function runResilienceEngine(ctx) {
    const cash = runCashOutEngine(ctx);
    const spendSeries = ctx.monthly.map((m) => m.spend).filter((v) => v > 0);
    const expenseCv = coefficientOfVariation(spendSeries);
    const incomeCv = ctx.incomeCv;
    const bufferMonths = ctx.monthlySpendAvg > 0 ? ctx.liquidBalance / ctx.monthlySpendAvg : 0;
    const contributionMonths = ctx.monthly.filter((m) => m.contribution > 0).length;
    const consistency = ctx.monthly.length ? contributionMonths / ctx.monthly.length : 0;
    const shockTolerance = ctx.monthlySpendAvg > 0 ? ctx.liquidBalance / (ctx.monthlySpendAvg * 0.6) : 0;
    const raw = {
        income_stability: clamp(1 / (1 + incomeCv * 1.4), 0, 1),
        expense_stability: clamp(1 / (1 + expenseCv), 0, 1),
        liquidity_buffer: clamp(bufferMonths / 4, 0, 1),
        savings_consistency: clamp(consistency, 0, 1),
        goal_progress: clamp(goalProgressRatio(ctx) * 1.6, 0, 1),
        channel_control: clamp(1 - cash.shareOfSpend, 0, 1),
        shock_absorption: clamp(shockTolerance / 2, 0, 1),
    };
    const weights = {
        income_stability: 0.15,
        expense_stability: 0.12,
        liquidity_buffer: 0.22,
        savings_consistency: 0.14,
        goal_progress: 0.1,
        channel_control: 0.09,
        shock_absorption: 0.18,
    };
    let composite = 0;
    const dimensions = Object.entries(raw).map(([key, value]) => {
        const contribution = value * weights[key] * 100;
        composite += contribution;
        return {
            key,
            label: RESILIENCE_LABELS[key].en,
            labelBn: RESILIENCE_LABELS[key].bn,
            value: round(value * 100, 0),
            contribution: round(contribution, 1),
            detail: describe(key, ctx, { incomeCv, expenseCv, bufferMonths, consistency, cashShare: cash.shareOfSpend, shockTolerance }),
        };
    });
    const score = round(clamp(composite, 0, 100), 0);
    const strengths = dimensions.filter((d) => d.value >= 65).sort((a, b) => b.value - a.value);
    const attention = dimensions.filter((d) => d.value < 55).sort((a, b) => a.value - b.value);
    const evidence = {
        engine: "Financial Resilience Engine",
        headline: `Financial resilience ${score}/100`,
        confidence: round(clamp(0.45 + ctx.monthly.length * 0.055, 0.4, 0.9), 2),
        confidenceNote: "This is a planning indicator computed from cash-flow behaviour. It is not a credit score and is not used for any eligibility decision.",
        metrics: [
            { id: "score", label: "Resilience score", value: score, unit: "ratio", detail: "weighted composite of 7 dimensions", source: "derived" },
            { id: "buffer_months", label: "Liquid balance in months of spend", value: round(bufferMonths, 2), unit: "months", detail: "liquid balance ÷ average monthly spend", source: "wallets + ledger" },
            { id: "income_cv", label: "Income volatility", value: round(incomeCv, 3), unit: "ratio", detail: "coefficient of variation", source: "ledger" },
            { id: "expense_cv", label: "Expense volatility", value: round(expenseCv, 3), unit: "ratio", detail: "coefficient of variation", source: "ledger" },
            { id: "cash_share", label: "Cash share of spending", value: round(cash.shareOfSpend, 4), unit: "percent", detail: "cash-wallet spend ÷ total spend", source: "ledger" },
            { id: "shock_tolerance", label: "Absorbable one-off shock", value: round(ctx.liquidBalance, 0), unit: "bdt", detail: "liquid balance available before borrowing", source: "wallets" },
        ],
        reasons: [
            ...strengths.slice(0, 3).map((d) => ({ polarity: "positive", text: `${d.label} at ${d.value}/100.`, weight: d.contribution })),
            ...attention.slice(0, 3).map((d) => ({ polarity: "negative", text: `${d.label} at ${d.value}/100.`, weight: -d.contribution })),
        ],
        assumptions: [
            "A household is treated as resilient if it can absorb roughly two months of average spending without new borrowing.",
            "Buffer and shock dimensions use total liquid balance; committed or restricted funds are not modelled.",
            "No protected attribute (age, gender, location, language) is used in the score.",
        ],
        sources: ["transactions.csv", "wallets.csv", "income_events.csv", "goal_contributions.csv"],
    };
    return {
        score,
        band: bandFor(score),
        dimensions: dimensions.sort((a, b) => b.value - a.value),
        strengths,
        attention,
        shockTolerance: round(shockTolerance, 2),
        evidence,
    };
}
export const RESILIENCE_LABELS = {
    income_stability: { en: "Income stability", bn: "আয়ের স্থিতিশীলতা" },
    expense_stability: { en: "Expense stability", bn: "খরচের স্থিতিশীলতা" },
    liquidity_buffer: { en: "Liquidity buffer", bn: "তরলতা বাফার" },
    savings_consistency: { en: "Savings consistency", bn: "সঞ্চয়ের ধারাবাহিকতা" },
    goal_progress: { en: "Goal progress", bn: "লক্ষ্য অগ্রগতি" },
    channel_control: { en: "Channel control", bn: "চ্যানেল নিয়ন্ত্রণ" },
    shock_absorption: { en: "Shock absorption", bn: "ঝুঁকি সহনশীলতা" },
};
function describe(key, ctx, v) {
    const taka = (n) => `৳${Math.round(n).toLocaleString("en-US")}`;
    switch (key) {
        case "income_stability":
            return `Monthly income varies ${(v.incomeCv * 100).toFixed(0)}% around its average.`;
        case "expense_stability":
            return `Monthly spend varies ${(v.expenseCv * 100).toFixed(0)}% around its average.`;
        case "liquidity_buffer":
            return `Liquid balance equals ${v.bufferMonths.toFixed(1)} months of average spending.`;
        case "savings_consistency":
            return `${Math.round(v.consistency * 100)}% of months included a goal contribution.`;
        case "goal_progress":
            return `${ctx.goals.length} active goal(s), ${(goalProgressRatio(ctx) * 100).toFixed(0)}% funded on average.`;
        case "channel_control":
            return `${(v.cashShare * 100).toFixed(0)}% of consumption settles in physical cash.`;
        case "shock_absorption":
            return `A ${taka(ctx.liquidBalance)} balance could absorb roughly ${v.shockTolerance.toFixed(1)}× a typical monthly shock of ${taka(ctx.monthlySpendAvg * 0.6)}.`;
        default:
            return "";
    }
}
/** Distribution of months where surplus turned negative — a pressure signal. */
export function negativeSurplusMonths(ctx) {
    const negative = ctx.monthly.filter((m) => m.savings < 0);
    const q = quantiles(ctx.monthly.map((m) => m.savings));
    return {
        count: negative.length,
        share: ctx.monthly.length ? negative.length / ctx.monthly.length : 0,
        worst: negative.length ? Math.min(...negative.map((m) => m.savings)) : 0,
        medianSurplus: round(q.p50, 0),
        meanSurplus: round(mean(ctx.monthly.map((m) => m.savings)), 0),
        total: round(sum(ctx.monthly.map((m) => m.savings)), 0),
    };
}
