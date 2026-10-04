import { isProductSpend } from "@/data/context";
import { bandFor, clamp, mean, quantiles, round, sum } from "@/lib/format";
import { estimateEssentialMonthly } from "./spending";
const WEIGHTS = {
    savings_behaviour: 0.2,
    expense_control: 0.18,
    cashflow_stability: 0.15,
    emergency_buffer: 0.16,
    goal_progress: 0.11,
    balance_resilience: 0.12,
    payment_control: 0.08,
};
export const HEALTH_LABELS = {
    savings_behaviour: { en: "Savings behaviour", bn: "সঞ্চয় আচরণ" },
    expense_control: { en: "Expense control", bn: "খরচ নিয়ন্ত্রণ" },
    cashflow_stability: { en: "Cash-flow stability", bn: "ক্যাশ-ফ্লো স্থিতিশীলতা" },
    emergency_buffer: { en: "Emergency buffer", bn: "জরুরি রিজার্ভ" },
    goal_progress: { en: "Goal progress", bn: "লক্ষ্য অগ্রগতি" },
    balance_resilience: { en: "Balance resilience", bn: "ব্যালেন্স সহনশীলতা" },
    payment_control: { en: "Payment control", bn: "পেমেন্ট নিয়ন্ত্রণ" },
};
/* ------------------------------------------------------------------ */
export function runHealthEngine(ctx) {
    const income = ctx.monthlyIncomeAvg;
    const spend = ctx.monthlySpendAvg;
    const savingsRate = income > 0 ? (income - spend) / income : 0;
    const essentialMonthly = estimateEssentialMonthly(ctx);
    const emergencyMonths = essentialMonthly > 0 ? ctx.liquidBalance / essentialMonthly : 0;
    const digitalShare = digitalShareOf(ctx);
    const recurringMonthly = sum(ctx.recurring.map((r) => r.amount));
    const obligationRatio = essentialMonthly > 0 ? clamp(recurringMonthly / essentialMonthly, 0, 2) / 2 : 1;
    const lowBalanceDays = countLowBalanceDays(ctx, essentialMonthly);
    const volatileDays = countVolatileDays(ctx);
    const monthsWithContribution = ctx.monthly.filter((m) => m.contribution > 0).length;
    const contributionConsistency = ctx.monthly.length
        ? monthsWithContribution / ctx.monthly.length
        : 0;
    const goalProgress = goalProgressRatio(ctx);
    const raw = {
        savings_behaviour: scoreSavings(savingsRate),
        expense_control: scoreExpenseControl(income, spend),
        cashflow_stability: scoreStability(ctx.incomeCv),
        emergency_buffer: scoreEmergency(emergencyMonths),
        goal_progress: scoreGoalProgress(contributionConsistency, goalProgress),
        balance_resilience: scoreBalanceResilience(lowBalanceDays, volatileDays, ctx.monthly.length),
        payment_control: clamp(digitalShare * 0.75 + obligationRatio * 0.25, 0, 1),
    };
    let composite = 0;
    const dimensions = Object.entries(raw).map(([key, value]) => {
        const weight = WEIGHTS[key];
        const contribution = value * weight * 100;
        composite += contribution;
        return {
            key,
            label: HEALTH_LABELS[key].en,
            labelBn: HEALTH_LABELS[key].bn,
            value: round(value * 100, 0),
            contribution: round(contribution, 1),
            detail: describeDimension(key, ctx, { savingsRate, essentialMonthly, emergencyMonths, recurringMonthly }),
        };
    });
    const score = round(clamp(composite, 0, 100), 0);
    const positives = dimensions.filter((d) => d.value >= 65).sort((a, b) => b.value - a.value);
    const concerns = dimensions
        .filter((d) => d.value < 50)
        .sort((a, b) => a.value - b.value);
    const evidence = {
        engine: "Financial Health Engine",
        headline: `Financial health ${score}/100`,
        confidence: round(clamp(0.5 + ctx.monthly.length * 0.05, 0.4, 0.94), 2),
        confidenceNote: ctx.monthly.length >= 6
            ? `Scored from ${ctx.monthly.length} complete months of ledger history.`
            : `Only ${ctx.monthly.length} month(s) of history available — treat as provisional.`,
        metrics: [
            metric("savings_rate", savingsRate, "percent", "Savings rate", "monthly income − spend, ÷ income", "ledger"),
            metric("expense_to_income", income > 0 ? spend / income : 0, "ratio", "Expense-to-income", "spend ÷ income", "ledger"),
            metric("emergency_months", emergencyMonths, "months", "Emergency buffer", "liquid balance ÷ essential monthly spend", "wallets + ledger"),
            metric("income_cv", ctx.incomeCv, "ratio", "Income variability", "coefficient of variation of monthly income", "ledger"),
            metric("digital_share", digitalShare, "percent", "Digital payment share", "non-cash spend ÷ total spend", "ledger"),
            metric("recurring_monthly", recurringMonthly, "bdt", "Recurring commitments", "sum of detected recurring obligations", "recurring_expenses"),
        ],
        reasons: [
            ...positives.slice(0, 3).map((d) => ({
                polarity: "positive",
                text: `${d.label} is at ${d.value}/100 and contributed +${d.contribution} points.`,
                weight: d.contribution,
            })),
            ...concerns.slice(0, 3).map((d) => ({
                polarity: "negative",
                text: `${d.label} is at ${d.value}/100, holding ${-d.contribution} points back.`,
                weight: -d.contribution,
            })),
        ],
        assumptions: [
            `Essential monthly spend is estimated as ৳${Math.round(essentialMonthly).toLocaleString("en-US")} (see Spending Engine).`,
            "Cash withdrawals are money movement rather than consumption, matching the dataset's own profile definition.",
            "Dimension weights are fixed product assumptions, not fitted to this customer.",
        ],
        sources: ["transactions.csv", "wallets.csv", "recurring_expenses.csv", "financial_goals.csv"],
    };
    return {
        score,
        band: bandFor(score),
        dimensions: dimensions.sort((a, b) => b.contribution - a.contribution),
        positives,
        concerns,
        lowBalanceDays,
        emergencyMonths,
        essentialMonthly,
        digitalShare,
        recurringMonthly,
        evidence,
    };
}
/* ------------------------------------------------------------------ */
function metric(id, value, unit, label, detail, source) {
    return { id, label, value: round(value, 4), unit, detail, source };
}
export function goalProgressRatio(ctx) {
    const goals = ctx.goals.filter((g) => g.target_amount > 0);
    if (!goals.length)
        return 0;
    return sum(goals.map((g) => clamp(g.current_amount / g.target_amount, 0, 1))) / goals.length;
}
/**
 * Reconstruct the historical liquid position from the closing balance and the
 * daily net movement, then count days below half a month of essential spend.
 */
export function reconstructBalanceSeries(ctx) {
    const out = [];
    let running = ctx.liquidBalance;
    for (let i = ctx.daily.length - 1; i >= 0; i -= 1) {
        const day = ctx.daily[i];
        running -= day.net;
        out.unshift({ iso: day.iso, balance: running });
    }
    return out;
}
export function countLowBalanceDays(ctx, essentialMonthly) {
    const buffer = Math.max(essentialMonthly * 0.5, 1);
    return reconstructBalanceSeries(ctx).filter((p) => p.balance < buffer).length;
}
function countVolatileDays(ctx) {
    const net = ctx.daily.map((d) => d.net);
    const scale = Math.max(1, mean(net.map(Math.abs)));
    return net.filter((n) => Math.abs(n) > scale * 3).length;
}
function scoreSavings(savingsRate) {
    if (savingsRate >= 0.25)
        return 1;
    if (savingsRate <= 0)
        return 0;
    return clamp(savingsRate / 0.25, 0, 1);
}
function scoreExpenseControl(income, spend) {
    if (income <= 0)
        return 0.3;
    const ratio = spend / income;
    if (ratio <= 0.6)
        return 1;
    if (ratio >= 1)
        return 0;
    return clamp(1 - (ratio - 0.6) / 0.4, 0, 1);
}
function scoreStability(cv) {
    return clamp(1 / (1 + cv), 0, 1);
}
function scoreEmergency(months) {
    if (months >= 6)
        return 1;
    if (months <= 0)
        return 0;
    return clamp(months / 6, 0, 1);
}
function scoreGoalProgress(consistency, progress) {
    if (consistency === 0 && progress === 0)
        return 0.2;
    return clamp(consistency * 0.6 + progress * 0.4, 0, 1);
}
function scoreBalanceResilience(lowBalanceDays, volatileDays, months) {
    const lowPenalty = months > 0 ? clamp(lowBalanceDays / (months * 30) / 0.2, 0, 1) : 0;
    const volPenalty = clamp(volatileDays / 12, 0, 1);
    return clamp(1 - (lowPenalty * 0.65 + volPenalty * 0.35), 0, 1);
}
function digitalShareOf(ctx) {
    const spendRows = ctx.transactions.filter(isProductSpend);
    const total = sum(spendRows.map((t) => t.amount));
    if (total <= 0)
        return 0;
    const cash = sum(spendRows.filter((t) => ctx.cashWalletIds.has(t.wallet_id)).map((t) => t.amount));
    return 1 - cash / total;
}
function describeDimension(key, ctx, v) {
    const taka = (n) => `৳${Math.round(n).toLocaleString("en-US")}`;
    switch (key) {
        case "savings_behaviour":
            return v.savingsRate >= 0
                ? `You keep about ${(v.savingsRate * 100).toFixed(0)}% of monthly income across ${ctx.monthly.length} months.`
                : `You spend more than you receive on average across ${ctx.monthly.length} months.`;
        case "expense_control":
            return `Average spend ${taka(ctx.monthlySpendAvg)} against ${taka(ctx.monthlyIncomeAvg)} income.`;
        case "cashflow_stability":
            return ctx.incomeCv <= 0.2
                ? `Income varies by only ${(ctx.incomeCv * 100).toFixed(0)}% month to month.`
                : `Income varies by ${(ctx.incomeCv * 100).toFixed(0)}% month to month — the average hides the timing.`;
        case "emergency_buffer":
            return v.emergencyMonths >= 1
                ? `Liquid balance covers ${v.emergencyMonths.toFixed(1)} months of essential spend.`
                : `Liquid balance does not cover one month of essential spend (${taka(v.essentialMonthly)}).`;
        case "goal_progress": {
            const months = ctx.monthly.filter((m) => m.contribution > 0).length;
            return `${months} of ${ctx.monthly.length} months included a goal contribution.`;
        }
        case "balance_resilience": {
            const q = quantiles(ctx.monthly.map((m) => m.income - m.spend));
            return `Monthly surplus ranges ${taka(q.p10)} to ${taka(q.p90)}.`;
        }
        case "payment_control":
            return `${Math.round(digitalShareOf(ctx) * 100)}% of spending settles digitally; mandatory commitments total ${taka(v.recurringMonthly)} per cycle.`;
        default:
            return "";
    }
}
