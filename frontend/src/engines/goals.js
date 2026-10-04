import { clamp, mean, median, monthsBetween, round, stdDev, sum } from "@/lib/format";
import { estimateEssentialMonthly } from "./spending";
import { defaultBuffer } from "./forecast";
export function estimateCapacity(ctx) {
    const incomeWindow = ctx.monthly.slice(-6).map((m) => m.income);
    const surplusWindow = ctx.monthly.map((m) => m.spend === 0 ? 0 : m.income - m.spend);
    const essentialMonthly = estimateEssentialMonthly(ctx);
    const totalAvg = mean(ctx.monthly.map((m) => m.spend));
    const discretionaryMonthly = Math.max(0, totalAvg - essentialMonthly);
    const sustainableIncome = median(incomeWindow.filter((v) => v > 0).length ? incomeWindow.filter((v) => v > 0) : incomeWindow);
    const plannedSpend = essentialMonthly + discretionaryMonthly;
    const buffer = defaultBuffer(ctx);
    const capacity = Math.max(0, sustainableIncome - plannedSpend);
    return {
        sustainableIncome: round(sustainableIncome, 0),
        plannedSpend: round(plannedSpend, 0),
        essentialMonthly: round(essentialMonthly, 0),
        discretionaryMonthly: round(discretionaryMonthly, 0),
        capacity: round(capacity, 0),
        surplusMean: round(mean(surplusWindow), 0),
        surplusStd: round(stdDev(surplusWindow), 0),
        buffer,
    };
}
/** Abramowitz–Stegun normal CDF. */
function normalCdf(z) {
    const t = 1 / (1 + 0.2316419 * Math.abs(z));
    const d = 0.3989422804014327 * Math.exp((-z * z) / 2);
    const p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    return z > 0 ? 1 - p : p;
}
export function completionProbability(remaining, monthlySurplus, monthlyStd, months) {
    if (months <= 0)
        return remaining <= 0 ? 1 : 0;
    if (monthlyStd <= 0)
        return monthlySurplus * months >= remaining ? 1 : 0;
    const z = (monthlySurplus * months - remaining) / (monthlyStd * Math.sqrt(months));
    return round(clamp(normalCdf(z), 0, 1), 3);
}
export function monthsToAccumulate(monthlySurplus, target, from) {
    if (monthlySurplus <= 0)
        return null;
    const months = Math.ceil(target / monthlySurplus);
    const date = new Date(from.getFullYear(), from.getMonth() + months, 1);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}
export function runGoalEngine(ctx, goal) {
    const plan = estimateCapacity(ctx);
    const target = new Date(goal.target_date);
    const monthsLeft = Math.max(0, monthsBetween(ctx.asOf, target));
    const remaining = Math.max(0, goal.target_amount - goal.current_amount);
    const requiredMonthly = monthsLeft > 0 ? remaining / monthsLeft : remaining;
    const surplus = plan.surplusMean;
    const std = plan.surplusStd;
    const scenarioDefs = [
        { key: "conservative", label: "Conservative", labelBn: "সাবধানী", q: -0.674 },
        { key: "balanced", label: "Balanced", labelBn: "সুষম", q: 0 },
        { key: "aggressive", label: "Aggressive", labelBn: "আক্রমণাত্মক", q: 0.674 },
    ];
    const scenarios = scenarioDefs.map((def) => {
        const percentileMonthly = Math.max(0, surplus + def.q * std);
        // A contribution above the customer's typical surplus has to come out of the
        // liquid balance, so it is allowed but flagged as buffer pressure later on.
        const contribution = Math.max(0, Math.round(percentileMonthly));
        const monthsNeeded = contribution > 0 ? Math.ceil(remaining / contribution) : Infinity;
        const reachesTarget = Number.isFinite(monthsNeeded) && monthsNeeded <= monthsLeft;
        const shortfall = Math.max(0, remaining - contribution * monthsLeft);
        const liquidAtDeadline = ctx.liquidBalance + (surplus - contribution) * monthsLeft;
        const minLiquid = Math.min(ctx.liquidBalance, liquidAtDeadline);
        return {
            key: def.key,
            label: def.label,
            labelBn: def.labelBn,
            monthlyContribution: contribution,
            shortfall: round(shortfall, 0),
            targetDate: Number.isFinite(monthsNeeded) ? monthsToAccumulate(contribution, remaining, ctx.asOf) : null,
            achievable: reachesTarget,
            probability: completionProbability(remaining, contribution, std, monthsLeft),
            minBalance: round(minLiquid, 0),
            bufferBreached: minLiquid < plan.buffer,
            tradeoff: contribution === 0
                ? "This scenario leaves nothing for the goal, so the target date keeps slipping."
                : minLiquid < plan.buffer
                    ? `৳${contribution.toLocaleString("en-US")} a month reaches the goal sooner but pulls the liquid balance to ৳${Math.round(minLiquid).toLocaleString("en-US")}, below the ৳${plan.buffer.toLocaleString("en-US")} buffer.`
                    : reachesTarget
                        ? `৳${contribution.toLocaleString("en-US")} a month reaches the goal in about ${monthsNeeded} month(s), ${monthsLeft - monthsNeeded} month(s) ahead of the deadline, with the buffer intact.`
                        : `৳${contribution.toLocaleString("en-US")} a month lands about ৳${Math.round(shortfall).toLocaleString("en-US")} short by the deadline.`,
            tradeoffBn: contribution === 0
                ? "এই পরিকল্পনায় লক্ষ্যের জন্য কিছুই রাখা হচ্ছে না, তাই তারিখ পিছিয়ে যাবে।"
                : minLiquid < plan.buffer
                    ? `মাসে ৳${contribution.toLocaleString("en-US")} জমালে লক্ষ্যে আগেই পৌঁছানো যায়, তবে তরল ব্যালেন্স ৳${Math.round(minLiquid).toLocaleString("en-US")} এ নেমে আসে, যা ৳${plan.buffer.toLocaleString("en-US")} রিজার্ভের নিচে।`
                    : reachesTarget
                        ? `মাসে ৳${contribution.toLocaleString("en-US")} জমালে লক্ষ্যে পৌঁছাতে প্রায় ${monthsNeeded} মাস লাগবে, যা সময়সীমার চেয়ে ${monthsLeft - monthsNeeded} মাস আগে, আর রিজার্ভ অক্ষত থাকবে।`
                        : `মাসে ৳${contribution.toLocaleString("en-US")} জমালে সময়সীমার আগে প্রায় ৳${Math.round(shortfall).toLocaleString("en-US")} ঘাটতি থাকবে।`,
        };
    });
    const estimatedCapacity = Math.max(0, plan.capacity);
    const probability = completionProbability(remaining, estimatedCapacity, std, monthsLeft);
    const shortfall = Math.max(0, remaining - estimatedCapacity * monthsLeft);
    const verdict = probability >= 0.75 ? "on_track" : probability >= 0.5 ? "tight" : probability >= 0.25 ? "at_risk" : "infeasible";
    const evidence = {
        engine: "Goal & Savings Optimisation Engine",
        headline: `${goal.goal_name}: ${(probability * 100).toFixed(0)}% likely by ${goal.target_date}`,
        confidence: round(clamp(0.4 + Math.min(ctx.monthly.length, 9) * 0.05, 0.4, 0.85), 2),
        confidenceNote: `Surplus modelled as a normal distribution with mean ৳${plan.surplusMean.toLocaleString("en-US")} and σ ৳${plan.surplusStd.toLocaleString("en-US")} over ${ctx.monthly.length} months.`,
        metrics: [
            { id: "target", label: "Target amount", value: goal.target_amount, unit: "bdt", detail: goal.goal_name, source: "financial_goals" },
            { id: "saved", label: "Already saved", value: goal.current_amount, unit: "bdt", detail: `${((goal.current_amount / goal.target_amount) * 100).toFixed(0)}% of target`, source: "financial_goals + goal_contributions" },
            { id: "remaining", label: "Remaining", value: round(remaining, 0), unit: "bdt", detail: "target minus saved", source: "financial_goals" },
            { id: "required_monthly", label: "Required per month", value: round(requiredMonthly, 0), unit: "bdt", detail: `${monthsLeft} month(s) until ${goal.target_date}`, source: "derived" },
            { id: "capacity", label: "Estimated disposable capacity", value: estimatedCapacity, unit: "bdt", detail: `median income ৳${plan.sustainableIncome.toLocaleString("en-US")} − planned spend ৳${plan.plannedSpend.toLocaleString("en-US")}`, source: "ledger" },
            { id: "shortfall", label: "Projected shortfall", value: round(shortfall, 0), unit: "bdt", detail: "at current capacity by the deadline", source: "model" },
        ],
        reasons: [
            {
                polarity: shortfall > 0 ? "negative" : "positive",
                text: shortfall > 0
                    ? `At ৳${estimatedCapacity.toLocaleString("en-US")}/month the goal lands about ৳${Math.round(shortfall).toLocaleString("en-US")} short.`
                    : `At ৳${estimatedCapacity.toLocaleString("en-US")}/month the goal is reachable with about ৳${Math.round(-shortfall).toLocaleString("en-US")} to spare.`,
            },
            {
                polarity: "neutral",
                text: `Monthly surplus has been ৳${plan.surplusMean.toLocaleString("en-US")} ± ৳${plan.surplusStd.toLocaleString("en-US")}, which drives the probability band.`,
            },
            {
                polarity: "neutral",
                text: `Required ৳${Math.round(requiredMonthly).toLocaleString("en-US")}/month is ${estimatedCapacity > 0 ? `${(requiredMonthly / estimatedCapacity).toFixed(2)}×` : "unbounded"} current capacity.`,
            },
        ],
        assumptions: [
            "Monthly surplus is treated as normally distributed around the customer's own history — no seasonal uplift is assumed.",
            `Capacity holds discretionary spending at its current median (৳${plan.discretionaryMonthly.toLocaleString("en-US")}/month) and protects a ৳${plan.buffer.toLocaleString("en-US")} buffer.`,
            "Income and expense shocks within a month are ignored; the model works month by month.",
        ],
        sources: ["financial_goals.csv", "goal_contributions.csv", "transactions.csv", "recurring_expenses.csv"],
    };
    return {
        goal,
        requiredMonthly: round(requiredMonthly, 0),
        estimatedCapacity: round(estimatedCapacity, 0),
        shortfall: round(shortfall, 0),
        probability,
        monthsLeft,
        scenarios,
        verdict,
        evidence,
    };
}
const PRIORITY_WEIGHT = { high: 3, medium: 2, low: 1 };
export function optimiseGoalAllocation(ctx, options = {}) {
    const goals = ctx.goals.filter((g) => g.target_amount > 0 && g.current_amount < g.target_amount);
    if (!goals.length)
        return [];
    const capacity = options.capacity ?? estimateCapacity(ctx).capacity;
    const weightSets = {
        priority: (g) => PRIORITY_WEIGHT[g.priority] ** 2,
        balanced: (g) => PRIORITY_WEIGHT[g.priority],
        even: () => 1,
    };
    const meta = {
        priority: {
            name: "Priority first",
            nameBn: "অগ্রাধিকার আগে",
            description: "Highest-priority goals absorb most of the capacity.",
            descriptionBn: "উচ্চ অগ্রাধিকারের লক্ষ্য বেশির ভাগ নেয়।",
        },
        balanced: {
            name: "Balanced by priority",
            nameBn: "ভারসাম্যপূর্ণ",
            description: "Capacity split in proportion to stated priority.",
            descriptionBn: "ক্ষমতা অগ্রাধিকার অনুযায়ী ভাগ হয়।",
        },
        even: {
            name: "Equal share",
            nameBn: "সমান ভাগ",
            description: "Every active goal receives the same monthly amount.",
            descriptionBn: "প্রতিটি সক্রিয় লক্ষ্য একই পরিমাণ পায়।",
        },
    };
    return Object.keys(weightSets).map((key) => {
        const weightOf = weightSets[key];
        const totalWeight = sum(goals.map(weightOf));
        const allocations = goals.map((g) => {
            const share = totalWeight > 0 ? weightOf(g) / totalWeight : 0;
            const monthly = Math.max(0, Math.round(capacity * share));
            const remaining = Math.max(0, g.target_amount - g.current_amount);
            const targetDate = monthsToAccumulate(monthly, remaining, ctx.asOf);
            const monthsLeft = Math.max(0, monthsBetween(ctx.asOf, new Date(g.target_date)));
            const shortfall = Math.max(0, remaining - monthly * monthsLeft);
            return {
                goal_id: g.goal_id,
                goal_name: g.goal_name,
                share: round(share, 4),
                monthly,
                targetDate,
                shortfall: round(shortfall, 0),
            };
        });
        return {
            key,
            ...meta[key],
            allocations,
            totalShortfall: round(sum(allocations.map((a) => a.shortfall)), 0),
        };
    }).sort((a, b) => a.totalShortfall - b.totalShortfall);
}
export function goalPortfolioSummary(ctx) {
    const goals = ctx.goals;
    const totalTarget = sum(goals.map((g) => g.target_amount));
    const totalSaved = sum(goals.map((g) => g.current_amount));
    const feasibility = goals.map((g) => runGoalEngine(ctx, g));
    return {
        goals,
        totalTarget,
        totalSaved,
        progress: totalTarget > 0 ? totalSaved / totalTarget : 0,
        feasibility,
        capacity: estimateCapacity(ctx),
    };
}
/** Add a simulated month of contributions — used by the simulator page. */
export function simulateGoalTimeline(goal, monthly, from) {
    const out = [];
    let balance = goal.current_amount;
    for (let m = 1; m <= 60; m += 1) {
        balance += Math.max(0, monthly);
        const d = new Date(from.getFullYear(), from.getMonth() + m, 1);
        out.push({ date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, balance: round(balance, 0) });
        if (balance >= goal.target_amount)
            break;
    }
    return out;
}
