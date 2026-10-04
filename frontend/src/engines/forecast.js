import { addDays, clamp, coefficientOfVariation, isoDate, mean, monthKey, round, stdDev, sum } from "@/lib/format";
/**
 * Cash-Flow Forecasting Engine
 * ---------------------------------------------------------------------------
 * Two models are built for every horizon and compared, exactly as the technical
 * validation plan requires:
 *
 *   Baseline — "recent daily average": the mean daily outflow of the trailing 30
 *              days, repeated every day. This is the number a customer would get
 *              by eyeballing their app.
 *
 *   Model    — exponentially weighted daily outflow rate × day-of-week factor ×
 *              day-of-month factor, with known recurring obligations placed on
 *              their due day and scheduled income placed on its typical arrival
 *              day. Uncertainty widens with the square root of the horizon.
 *
 * No language model touches these numbers; they are the evidence the assistant
 * is later asked to explain.
 */
export const HORIZONS = [7, 14, 30, 60, 90];
function weekdayFactor(ctx) {
    const spendByDow = Array.from({ length: 7 }, () => []);
    for (const d of ctx.daily)
        spendByDow[d.date.getDay()].push(d.spend);
    const all = mean(ctx.daily.map((d) => d.spend));
    return spendByDow.map((values) => (all > 0 && values.length ? mean(values) / all : 1));
}
function dayOfMonthFactor(ctx) {
    const spendByDom = Array.from({ length: 32 }, () => []);
    for (const d of ctx.daily)
        spendByDom[d.date.getDate()].push(d.spend);
    const all = mean(ctx.daily.map((d) => d.spend));
    return spendByDom.map((values) => (all > 0 && values.length ? clamp(mean(values) / all, 0.4, 2.4) : 1));
}
/** Exponentially weighted mean daily outflow, halflife 30 days. */
function ewmaDailyRate(ctx, halflife = 30) {
    const n = ctx.daily.length;
    if (!n)
        return 0;
    const lambda = Math.LN2 / halflife;
    let num = 0;
    let den = 0;
    for (let i = 0; i < n; i += 1) {
        const age = n - 1 - i;
        const w = Math.exp(-lambda * age);
        num += w * ctx.daily[i].spend;
        den += w;
    }
    return den > 0 ? num / den : 0;
}
export function planIncome(ctx) {
    const byKey = new Map();
    for (const ev of ctx.incomeEvents) {
        const day = Number(ev.timestamp.slice(8, 10));
        // 31-day months push day-31 income to day-28; normalise so plans stack.
        const normalised = day > 28 ? 28 : day;
        const key = `${ev.income_type}|${ev.source}|${ev.regularity}`;
        const e = byKey.get(key) ?? { amounts: [], days: [], regularity: ev.regularity, incomeType: ev.income_type, source: ev.source };
        e.amounts.push(ev.amount);
        e.days.push(normalised);
        byKey.set(key, e);
    }
    return [...byKey.values()].map((e) => {
        const cv = coefficientOfVariation(e.amounts);
        return {
            dayOfMonth: Math.round(mean(e.days)),
            expectedAmount: mean(e.amounts),
            regularity: e.regularity,
            incomeType: e.incomeType,
            source: e.source,
            stability: clamp(1 / (1 + cv), 0, 1),
        };
    });
}
/** Upcoming obligations inside the horizon, expanded from the recurring table. */
export function obligationCalendar(ctx, until) {
    const items = [];
    // Walk whole months so a due day late in the horizon month is still counted,
    // then drop anything outside the window below.
    const cursor = new Date(ctx.asOf.getFullYear(), ctx.asOf.getMonth(), 1);
    while (cursor <= until) {
        for (const r of ctx.recurring) {
            const monthLength = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
            const due = new Date(cursor.getFullYear(), cursor.getMonth(), Math.min(r.due_day || 1, monthLength));
            if (due.getTime() < ctx.asOf.getTime() || due > until)
                continue;
            items.push({ date: due, amount: r.amount, name: r.expense_name, mandatory: r.mandatory, category: r.category });
        }
        cursor.setMonth(cursor.getMonth() + 1);
    }
    return items;
}
export function runForecast(ctx, horizonDays = 30, bufferOverride) {
    const dow = weekdayFactor(ctx);
    const dom = dayOfMonthFactor(ctx);
    const rate = ewmaDailyRate(ctx);
    const residual = Math.max(200, stdDev(ctx.daily.slice(-60).map((d) => d.spend)) || mean(ctx.daily.slice(-30).map((d) => d.spend)) * 0.4);
    const incomePlan = planIncome(ctx);
    const end = addDays(ctx.asOf, horizonDays);
    const obligations = obligationCalendar(ctx, end);
    const buffer = bufferOverride ?? defaultBuffer(ctx);
    const points = [];
    let balance = ctx.liquidBalance;
    let baselineBalance = ctx.liquidBalance;
    const trailing30 = mean(ctx.daily.slice(-30).map((d) => d.spend));
    for (let step = 1; step <= horizonDays; step += 1) {
        const date = addDays(ctx.asOf, step);
        const daySpend = rate * dow[date.getDay()] * dom[date.getDate()];
        let scheduledIncome = 0;
        for (const plan of incomePlan) {
            if (plan.dayOfMonth === date.getDate() || (date.getDate() === 1 && plan.dayOfMonth > 28)) {
                scheduledIncome += plan.expectedAmount;
            }
        }
        // Irregular income is spread as a daily accrual instead of a single date.
        const irregularDaily = sum(incomePlan.filter((p) => p.regularity !== "regular" && p.stability < 0.6).map((p) => p.expectedAmount)) / 30;
        const recurringDue = sum(obligations.filter((o) => isoDate(o.date) === isoDate(date)).map((o) => o.amount));
        const expense = daySpend + recurringDue;
        const income = scheduledIncome + irregularDaily;
        balance += income - expense;
        baselineBalance += irregularDaily - trailing30;
        const spread = residual * Math.sqrt(step) * (0.55 + 0.45 * (1 - mean(incomePlan.map((p) => p.stability))));
        points.push({
            date: isoDate(date),
            dayOfMonth: date.getDate(),
            balance: round(balance, 0),
            income: round(income, 0),
            expense: round(expense, 0),
            lower: round(balance - spread, 0),
            upper: round(balance + spread, 0),
            recurringDue: round(recurringDue, 0),
            belowBuffer: balance < buffer,
        });
    }
    const expectedIncome = sum(points.map((p) => p.income));
    const expectedExpense = sum(points.map((p) => p.expense));
    const ending = points[points.length - 1]?.balance ?? balance;
    const baselineEnding = baselineBalance;
    const minPoint = points.reduce((acc, p) => (!acc || p.balance < acc.balance ? p : acc), null);
    const windows = lowBalanceWindows(points);
    const confidence = round(clamp(0.75 - horizonDays * 0.0035 - mean(incomePlan.map((p) => 1 - p.stability)) * 0.18, 0.35, 0.85), 2);
    const evidence = {
        engine: "Cash-Flow Forecasting Engine",
        headline: `${horizonDays}-day projected closing balance ৳${Math.round(ending).toLocaleString("en-US")}`,
        confidence,
        confidenceNote: `Uncertainty band = trailing daily residual × √horizon, widened by income instability ` +
            `(income CV ${ctx.incomeCv.toFixed(2)}).`,
        metrics: [
            { id: "current_balance", label: "Liquid balance today", value: round(ctx.liquidBalance, 0), unit: "bdt", detail: "upay + bank + cash closing balances", source: "wallets" },
            { id: "expected_income", label: `Expected income (${horizonDays}d)`, value: round(expectedIncome, 0), unit: "bdt", detail: "scheduled + irregular accrual", source: "income_events" },
            { id: "expected_expense", label: `Expected expense (${horizonDays}d)`, value: round(expectedExpense, 0), unit: "bdt", detail: "modelled daily rate + recurring calendar", source: "transactions + recurring_expenses" },
            { id: "ending_balance", label: "Projected closing balance", value: round(ending, 0), unit: "bdt", detail: `baseline model projects ৳${Math.round(baselineEnding).toLocaleString("en-US")}`, source: "model" },
            { id: "min_balance", label: "Projected minimum", value: round(minPoint?.balance ?? ending, 0), unit: "bdt", detail: `trough ${minPoint ? `on day ${minPoint.dayOfMonth}` : "n/a"}`, source: "model" },
            { id: "obligations", label: "Scheduled obligations", value: round(sum(obligations.map((o) => o.amount)), 0), unit: "bdt", detail: `${obligations.length} payments inside the horizon`, source: "recurring_expenses" },
        ],
        reasons: [
            { polarity: "neutral", text: `Baseline (30-day average of ৳${Math.round(trailing30).toLocaleString("en-US")}/day) projects ৳${Math.round(baselineEnding).toLocaleString("en-US")}; the seasonal model projects ৳${Math.round(ending).toLocaleString("en-US")}.` },
            ...incomePlan.slice(0, 3).map((p) => ({
                polarity: (p.stability > 0.8 ? "positive" : "negative"),
                text: `${p.incomeType} (${p.source}) typically arrives on day ${p.dayOfMonth} with stability ${(p.stability * 100).toFixed(0)}%.`,
            })),
            ...(windows.length
                ? [{ polarity: "negative", text: `Projected balance dips below the ৳${Math.round(buffer).toLocaleString("en-US")} buffer between ${windows[0].from} and ${windows[0].to}.` }]
                : []),
        ],
        assumptions: [
            "Recurring obligations repeat on their recorded due day with their recorded amount (no utility-bill drift).",
            "Income regularity 'regular' is scheduled on the mean arrival day; everything else accrues uniformly across the month.",
            `The safety buffer defaults to ৳${Math.round(buffer).toLocaleString("en-US")}, about one week of essential spend.`,
            "No future transactions are used. All coefficients come from the trailing window only.",
        ],
        sources: ["transactions.csv", "income_events.csv", "recurring_expenses.csv", "wallets.csv"],
    };
    return {
        points,
        horizonDays,
        expectedIncome: round(expectedIncome, 0),
        expectedExpense: round(expectedExpense, 0),
        expectedEndingBalance: round(ending, 0),
        buffer: round(buffer, 0),
        minBalance: round(minPoint?.balance ?? ending, 0),
        minBalanceDate: minPoint?.date ?? null,
        lowBalanceWindows: windows,
        confidence,
        method: "EWMA daily rate × weekday × day-of-month seasonality + scheduled obligations and income",
        baseline: { expectedEndingBalance: round(baselineEnding, 0), mae: 0 },
        evidence,
    };
}
export function defaultBuffer(ctx) {
    const essentials = mean(ctx.monthly.map((m) => m.spend)) * 0.62;
    return Math.max(5000, Math.round(essentials / 4));
}
function lowBalanceWindows(points) {
    const out = [];
    let open = null;
    for (const p of points) {
        if (p.belowBuffer && !open)
            open = p;
        if (!p.belowBuffer && open) {
            out.push({
                from: open.date,
                to: p.date,
                probability: 1,
            });
            open = null;
        }
    }
    if (open)
        out.push({ from: open.date, to: (points[points.length - 1] ?? open).date, probability: 1 });
    return out;
}
export function backtestForecast(ctx, window = 14, folds = 6) {
    const modelErr = [];
    const baseErr = [];
    const actualErr = [];
    const foldSize = Math.max(window, Math.floor(ctx.daily.length / (folds + 2)));
    const start = Math.max(30, ctx.daily.length - foldSize * (folds + 1));
    for (let f = 0; f < folds; f += 1) {
        const cutoff = start + f * foldSize;
        const test = ctx.daily.slice(cutoff, cutoff + foldSize);
        if (test.length < window)
            break;
        // Model: EWMA on the trailing slice + seasonality estimated from that slice.
        const train = ctx.daily.slice(0, cutoff);
        const rate = ewmaDailyRate({ ...ctx, daily: train });
        const domLocal = dayOfMonthFactor({ ...ctx, daily: train });
        const dowLocal = weekdayFactor({ ...ctx, daily: train });
        const baseRate = mean(train.slice(-30).map((d) => d.spend));
        let modelTotal = 0;
        let baseTotal = 0;
        for (let i = 0; i < window; i += 1) {
            const d = test[i];
            modelTotal += rate * dowLocal[d.date.getDay()] * domLocal[d.date.getDate()];
            baseTotal += baseRate;
        }
        const actual = sum(test.slice(0, window).map((d) => d.spend));
        modelErr.push(Math.abs(modelTotal - actual));
        baseErr.push(Math.abs(baseTotal - actual));
        actualErr.push(Math.abs(actual));
    }
    const maeModel = modelErr.length ? mean(modelErr) : 0;
    const maeBaseline = baseErr.length ? mean(baseErr) : 0;
    const rmseModel = modelErr.length ? Math.sqrt(mean(modelErr.map((e) => e ** 2))) : 0;
    const rmseBaseline = baseErr.length ? Math.sqrt(mean(baseErr.map((e) => e ** 2))) : 0;
    const mapeModel = actualErr.length
        ? mean(modelErr.map((e, i) => (actualErr[i] > 0 ? (e / actualErr[i]) * 100 : 0)))
        : 0;
    const mapeBaseline = actualErr.length
        ? mean(baseErr.map((e, i) => (actualErr[i] > 0 ? (e / actualErr[i]) * 100 : 0)))
        : 0;
    return {
        maeModel: round(maeModel, 0),
        maeBaseline: round(maeBaseline, 0),
        rmseModel: round(rmseModel, 0),
        rmseBaseline: round(rmseBaseline, 0),
        mapeModel: round(mapeModel, 2),
        mapeBaseline: round(mapeBaseline, 2),
        windows: modelErr.length,
        improvementPct: maeBaseline > 0 ? round((1 - maeModel / maeBaseline) * 100, 1) : 0,
    };
}
/** Month-end view: expected closing balance for the remainder of the month. */
export function monthEndProjection(ctx) {
    const daysInMonth = new Date(ctx.asOf.getFullYear(), ctx.asOf.getMonth() + 1, 0).getDate();
    const remaining = daysInMonth - ctx.asOf.getDate();
    const forecast = runForecast(ctx, Math.max(1, remaining));
    const key = monthKey(ctx.asOf);
    const monthSoFar = ctx.monthly.find((m) => m.key === key) ?? ctx.currentMonth;
    return {
        daysRemaining: Math.max(0, remaining),
        monthSoFar,
        forecast,
    };
}
