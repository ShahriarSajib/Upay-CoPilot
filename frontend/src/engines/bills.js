import { clamp, isoDate, mean, monthKey, round, sum } from "@/lib/format";
import { defaultBuffer, obligationCalendar, planIncome, runForecast } from "./forecast";
export function runBillsEngine(ctx, horizonDays = 60) {
    const forecast = runForecast(ctx, horizonDays);
    const buffer = defaultBuffer(ctx);
    const plans = planIncome(ctx);
    const end = new Date(ctx.asOf.getTime());
    end.setDate(end.getDate() + horizonDays);
    const obligations = obligationCalendar(ctx, end);
    const byDate = new Map();
    for (const o of obligations) {
        const key = isoDate(o.date);
        byDate.set(key, [...(byDate.get(key) ?? []), o]);
    }
    const incomeDays = [];
    const days = [];
    const rows = [];
    for (const point of forecast.points) {
        const due = byDate.get(point.date) ?? [];
        // The forecast point already subtracted the day's obligations, so adding
        // them back recovers the "before payments" balance for the same day.
        const before = point.balance + point.recurringDue;
        const items = [];
        let running = before;
        for (const o of due) {
            const after = running - o.amount;
            items.push({
                date: point.date,
                dayOfMonth: point.dayOfMonth,
                name: o.name,
                category: o.category,
                amount: round(o.amount, 0),
                mandatory: o.mandatory,
                incomeSameDay: round(point.income, 0),
                balanceBefore: round(running, 0),
                balanceAfter: round(after, 0),
                balanceLower: round(point.lower + point.recurringDue, 0),
                tight: after < buffer,
                affordable: running >= o.amount,
            });
            running = after;
        }
        if (due.length) {
            const sameDay = sum(plans
                .filter((p) => p.dayOfMonth === point.dayOfMonth || (point.dayOfMonth === 1 && p.dayOfMonth > 28))
                .map((p) => p.expectedAmount));
            if (sameDay > 0) {
                const matching = plans.filter((p) => p.dayOfMonth === point.dayOfMonth || (point.dayOfMonth === 1 && p.dayOfMonth > 28));
                incomeDays.push({
                    date: point.date,
                    dayOfMonth: point.dayOfMonth,
                    amount: round(sameDay, 0),
                    incomeType: matching[0]?.incomeType ?? "income",
                    source: matching.length > 1 ? "multiple sources" : matching[0]?.source ?? "unknown",
                    stability: round(mean(matching.map((p) => p.stability)), 2),
                });
            }
        }
        days.push({
            date: point.date,
            dayOfMonth: point.dayOfMonth,
            income: round(point.income, 0),
            balanceBefore: round(before, 0),
            obligations: round(sum(items.map((i) => i.amount)), 0),
            balanceAfter: round(running, 0),
            lower: round(point.lower, 0),
            buffer: round(buffer, 0),
            tight: running < buffer,
            items,
        });
        rows.push(...items);
    }
    const total = sum(rows.map((r) => r.amount));
    const mandatoryTotal = sum(rows.filter((r) => r.mandatory).map((r) => r.amount));
    const optionalTotal = total - mandatoryTotal;
    const asOfMs = ctx.asOf.getTime();
    const within = (daysAhead) => sum(rows
        .filter((r) => {
        const t = new Date(`${r.date}T00:00:00`).getTime();
        return t > asOfMs && t <= asOfMs + daysAhead * 86_400_000;
    })
        .map((r) => r.amount));
    const tightest = days.reduce((acc, d) => (d.obligations > 0 && (!acc || d.balanceAfter < acc.balanceAfter) ? d : acc), null);
    const shortfall = days.find((d) => d.obligations > d.income && d.obligations > 0);
    const committedShare = ctx.monthlyIncomeAvg > 0 ? mandatoryTotal / horizonDays / ctx.monthlyIncomeAvg : 0;
    const stability = plans.length ? mean(plans.map((p) => p.stability)) : 0.6;
    const confidence = round(clamp(0.55 + stability * 0.4 - (1 - stability) * 0.15, 0.4, 0.95), 2);
    const evidence = {
        engine: "Bill & Obligation Calendar Engine",
        headline: `${rows.length} payments totalling ৳${Math.round(total).toLocaleString("en-US")} due in the next ${horizonDays} days`,
        confidence,
        confidenceNote: `Due dates and amounts are fixed from the recurring table, so the schedule itself is exact. ` +
            `The balance is the cash-flow forecast's projection, whose uncertainty scales with income ` +
            `instability (mean income stability ${(stability * 100).toFixed(0)}%).`,
        metrics: [
            { id: "due_total", label: `Due in ${horizonDays} days`, value: round(total, 0), unit: "bdt", detail: `${rows.length} payments across ${new Set(rows.map((r) => monthKey(new Date(`${r.date}T00:00:00`)))).size} month(s)`, source: "recurring_expenses" },
            { id: "mandatory", label: "Mandatory share", value: round(mandatoryTotal, 0), unit: "bdt", detail: `${(committedShare * 100).toFixed(1)}% of average monthly income`, source: "recurring_expenses + income_events" },
            { id: "optional", label: "Optional / flexible", value: round(optionalTotal, 0), unit: "bdt", detail: "subscriptions and flexible recurring payments", source: "recurring_expenses" },
            { id: "next7", label: "Due in 7 days", value: round(within(7), 0), unit: "bdt", detail: "immediate cash requirement", source: "recurring_expenses" },
            { id: "tightest", label: "Tightest post-payment day", value: tightest ? tightest.balanceAfter : round(ctx.liquidBalance, 0), unit: "bdt", detail: tightest ? `on ${tightest.date} after ৳${tightest.obligations.toLocaleString("en-US")} of payments` : "no payment day inside horizon", source: "model" },
        ],
        reasons: [
            ...rows
                .slice()
                .sort((a, b) => b.amount - a.amount)
                .slice(0, 3)
                .map((r) => ({
                polarity: (r.mandatory ? "negative" : "neutral"),
                text: `${r.name} on day ${r.dayOfMonth}: ৳${r.amount.toLocaleString("en-US")}${r.mandatory ? " (mandatory)" : " (flexible)"} leaves a projected ৳${r.balanceAfter.toLocaleString("en-US")}.`,
            })),
            ...(shortfall
                ? [
                    {
                        polarity: "negative",
                        text: `No income is scheduled on ${shortfall.date}, so ${Math.round(shortfall.obligations).toLocaleString("en-US")} of bills due that day are paid from the balance carried in (projected ${Math.round(shortfall.balanceAfter).toLocaleString("en-US")} after payment).`,
                    },
                ]
                : [{ polarity: "positive", text: "On every payment day inside the horizon, scheduled income covers that day's bills before daily spending." }]),
            ...(incomeDays.length
                ? [{ polarity: "neutral", text: `Next scheduled income: ৳${incomeDays[0].amount.toLocaleString("en-US")} on day ${incomeDays[0].dayOfMonth} (${incomeDays[0].source}, stability ${(incomeDays[0].stability * 100).toFixed(0)}%).` }]
                : []),
        ],
        assumptions: [
            "Each recurring expense repeats on its recorded due day at its recorded amount; utility-bill seasonal drift is not modelled.",
            "No new subscription, bill or price increase is assumed inside the horizon.",
            "Balances are the cash-flow forecast's projection: EWMA daily rate × weekday × day-of-month, plus scheduled income and obligations.",
            "Income marked 'regular' is placed on its mean arrival day; irregular income accrues uniformly across the month.",
            `The tight flag compares the post-payment balance with a ৳${Math.round(buffer).toLocaleString("en-US")} buffer (about one week of essential spend).`,
            "This calendar is read-only. It cannot pay a bill, move money, or change an autopay setting.",
        ],
        sources: ["recurring_expenses.csv", "income_events.csv", "transactions.csv", "wallets.csv"],
    };
    return {
        horizonDays,
        asOf: isoDate(ctx.asOf),
        rows,
        days,
        incomeDays,
        total: round(total, 0),
        mandatoryTotal: round(mandatoryTotal, 0),
        optionalTotal: round(optionalTotal, 0),
        next7: round(within(7), 0),
        next30: round(within(30), 0),
        monthsCovered: new Set(rows.map((r) => monthKey(new Date(`${r.date}T00:00:00`)))).size,
        committedShare: round(committedShare, 3),
        nextIncome: incomeDays[0] ?? null,
        tightest: tightest ? { date: tightest.date, balanceAfter: tightest.balanceAfter } : null,
        tightDays: days.filter((d) => d.tight && d.obligations > 0).length,
        shortfallDay: shortfall ? { date: shortfall.date, gap: round(shortfall.obligations - shortfall.income, 0) } : null,
        buffer: round(buffer, 0),
        evidence,
    };
}
