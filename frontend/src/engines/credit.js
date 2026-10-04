import { bandFor, clamp, quantiles, round, sum } from "@/lib/format";
import { estimateEssentialMonthly } from "./spending";
import { estimateCapacity } from "./goals";
/**
 * Responsible Credit Readiness
 * ---------------------------------------------------------------------------
 * This engine exists to satisfy the challenge constraint: the assistant may
 * surface financial readiness *patterns* for education and planning, and it must
 * never approve, decline, score or recommend a lending decision.
 *
 * Deliberate design choices:
 *  • the output is a band over observable behaviour, not a credit score;
 *  • there is no approve/decline path anywhere in the codebase;
 *  • every surface that renders this output repeats the disclaimer;
 *  • the affordability calculator uses synthetic, clearly-labelled terms.
 */
export const READINESS_DISCLAIMER = "Planning indicator only — this describes cash-flow patterns, not creditworthiness. It does not determine loan approval, and upay Financial Life Copilot never makes lending decisions.";
export const READINESS_DISCLAIMER_BN = "এটি শুধু একটি পরিকল্পনা-সংক্রান্ত সূচক — এটি কার্ড ঝুঁকির মান নয়, ঋণ অনুমোদন নির্ধারণ করে না, এবং upay Financial Life Copilot কখনো ঋণ সংক্রান্ত সিদ্ধান্ত নেয় না।";
export function runReadinessEngine(ctx) {
    const plan = estimateCapacity(ctx);
    const essential = estimateEssentialMonthly(ctx);
    const monthlyIncome = ctx.monthlyIncomeAvg;
    const spend = ctx.monthlySpendAvg;
    const obligationRatio = monthlyIncome > 0 ? spend / monthlyIncome : 1;
    const bufferMonths = spend > 0 ? ctx.liquidBalance / spend : 0;
    const contributionMonths = ctx.monthly.filter((m) => m.contribution > 0).length;
    const consistency = ctx.monthly.length ? contributionMonths / ctx.monthly.length : 0;
    const surplus = plan.surplusMean;
    const raw = {
        income_consistency: clamp(1 / (1 + ctx.incomeCv * 1.3), 0, 1),
        repayment_capacity: clamp(surplus / Math.max(1, monthlyIncome * 0.25), 0, 1),
        balance_stability: clamp(bufferMonths / 3, 0, 1),
        savings_behaviour: clamp(consistency * 0.7 + clamp(surplus / Math.max(1, monthlyIncome * 0.3), 0, 1) * 0.3, 0, 1),
        obligation_pressure: clamp(1 - obligationRatio, 0, 1),
        essentials_coverage: clamp(plan.capacity / Math.max(1, essential * 0.4), 0, 1),
    };
    const weights = {
        income_consistency: 0.2,
        repayment_capacity: 0.24,
        balance_stability: 0.16,
        savings_behaviour: 0.16,
        obligation_pressure: 0.14,
        essentials_coverage: 0.1,
    };
    let composite = 0;
    const dimensions = Object.entries(raw).map(([key, value]) => {
        const contribution = value * weights[key] * 100;
        composite += contribution;
        return {
            key,
            label: READINESS_LABELS[key].en,
            labelBn: READINESS_LABELS[key].bn,
            value: round(value * 100, 0),
            contribution: round(contribution, 1),
            detail: describe(key, ctx, { monthlyIncome, spend, bufferMonths, consistency, surplus }),
        };
    });
    const score = round(clamp(composite, 0, 100), 0);
    const obligations = [...ctx.recurring]
        .sort((a, b) => (a.due_day ?? 1) - (b.due_day ?? 1))
        .map((r) => ({ name: r.expense_name, amount: r.amount, dueDay: r.due_day ?? 1, mandatory: r.mandatory }));
    const evidence = {
        engine: "Responsible Credit Readiness (informational)",
        headline: `Readiness pattern: ${READINESS_BANDS[bandFor(score)]}`,
        confidence: round(clamp(0.4 + ctx.monthly.length * 0.05, 0.4, 0.82), 2),
        confidenceNote: "Derived from the same behavioural evidence as the health engine, but weighted toward repayment capacity. It carries no regulatory meaning.",
        metrics: [
            { id: "band", label: "Readiness band", value: READINESS_BANDS[bandFor(score)], unit: "text", detail: "behavioural pattern, not a score", source: "derived" },
            { id: "obligations", label: "Monthly commitments", value: round(sum(obligations.map((o) => o.amount)), 0), unit: "bdt", detail: `${obligations.length} recurring obligations`, source: "recurring_expenses" },
            { id: "obligation_ratio", label: "Spend-to-income ratio", value: round(obligationRatio, 3), unit: "ratio", detail: "average monthly spend ÷ income", source: "ledger" },
            { id: "buffer_months", label: "Buffer in months of spend", value: round(bufferMonths, 2), unit: "months", detail: "liquid balance ÷ average monthly spend", source: "wallets" },
            { id: "surplus", label: "Average monthly surplus", value: round(surplus, 0), unit: "bdt", detail: "income − spend, averaged", source: "ledger" },
        ],
        reasons: [
            { polarity: "neutral", text: READINESS_DISCLAIMER },
            {
                polarity: surplus > 0 ? "positive" : "negative",
                text: surplus > 0
                    ? `Average monthly surplus is ${round(surplus, 0).toLocaleString("en-US")}, which is the amount an instalment would have to fit inside.`
                    : `Average monthly surplus is negative — an instalment would currently be funded from the buffer.`,
            },
        ],
        assumptions: [
            READINESS_DISCLAIMER,
            "Bands describe observable behaviour over the observed window, not credit risk.",
            "No bureau data, no collateral, no protected attributes and no external score is used.",
        ],
        sources: ["transactions.csv", "recurring_expenses.csv", "wallets.csv"],
    };
    return {
        band: bandFor(score),
        dimensions: dimensions.sort((a, b) => b.contribution - a.contribution),
        strengths: dimensions.filter((d) => d.value >= 65),
        attention: dimensions.filter((d) => d.value < 55),
        obligations,
        monthlyObligation: round(sum(obligations.map((o) => o.amount)), 0),
        evidence,
    };
}
export const READINESS_LABELS = {
    income_consistency: { en: "Income consistency", bn: "আয়ের ধারাবাহিকতা" },
    repayment_capacity: { en: "Repayment capacity", bn: "ফেরত দেওয়ার সক্ষমতা" },
    balance_stability: { en: "Balance stability", bn: "ব্যালেন্স স্থিতিশীলতা" },
    savings_behaviour: { en: "Savings behaviour", bn: "সঞ্চয় আচরণ" },
    obligation_pressure: { en: "Obligation pressure", bn: "দায়বদ্ধতার চাপ" },
    essentials_coverage: { en: "Essentials coverage", bn: "প্রয়োজনীয় খরচের কভারেজ" },
};
export const READINESS_BANDS = {
    strong: "Strong, consistent pattern",
    good: "Generally healthy pattern",
    moderate: "Mixed pattern — review obligations",
    weak: "Strained pattern — stabilise cash flow first",
    critical: "Currently under significant pressure",
};
export const READINESS_BANDS_BN = {
    strong: "শক্তিশালী ও ধারাবাহিক ধরন",
    good: "সাধারণত সুস্থ ধরন",
    moderate: "মিশ্র ধরন — দায়বদ্ধতা পর্যালোচনা করুন",
    weak: "কাঁচা ধরন — আগে ক্যাশ-ফ্লো স্থিতিশীল করুন",
    critical: "বর্তমানে উল্লেখযোগ্য আর্থিক চাপে",
};
function describe(key, ctx, v) {
    const taka = (n) => `৳${Math.round(n).toLocaleString("en-US")}`;
    switch (key) {
        case "income_consistency":
            return `Monthly income varies ${(ctx.incomeCv * 100).toFixed(0)}% around ${taka(v.monthlyIncome)}.`;
        case "repayment_capacity":
            return `Surplus of ${taka(v.surplus)} per month sits above essential commitments.`;
        case "balance_stability":
            return `Liquid balance covers ${v.bufferMonths.toFixed(1)} months of current spending.`;
        case "savings_behaviour":
            return `${Math.round(v.consistency * 100)}% of months included a savings contribution.`;
        case "obligation_pressure":
            return `Spend equals ${v.monthlyIncome > 0 ? (v.spend / v.monthlyIncome).toFixed(2) : "n/a"}× monthly income.`;
        case "essentials_coverage":
            return `Essential commitments total ${taka(sum(ctx.recurring.map((r) => r.amount)))} per cycle.`;
        default:
            return "";
    }
}
export function fairnessProbe(contexts, key) {
    const groups = new Map();
    for (const ctx of contexts) {
        const raw = key === "occupation"
            ? ctx.user.occupation
            : key === "age_group"
                ? ctx.user.age_group
                : ctx.user.location_type === "rural"
                    ? "lower-resource geography"
                    : "urban / semi-urban";
        const list = groups.get(raw) ?? [];
        const plan = estimateCapacity(ctx);
        list.push(plan.surplusMean);
        groups.set(raw, list);
    }
    const rows = [...groups.entries()].map(([group, values]) => {
        const q = quantiles(values);
        return {
            group,
            members: values.length,
            meanBand: round(q.p50, 0),
            spread: round(q.p90 - q.p10, 0),
        };
    });
    return rows.sort((a, b) => b.members - a.members);
}
