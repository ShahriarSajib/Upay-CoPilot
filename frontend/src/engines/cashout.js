import { isProductSpend } from "@/data/context";
import { clamp, mean, parseDate, quantiles, round, sum } from "@/lib/format";
export function runCashOutEngine(ctx) {
    const cashOuts = ctx.transactions.filter((t) => t.transaction_type === "cash_out");
    const cashOutTotal = sum(cashOuts.map((t) => t.amount));
    const spendRows = ctx.transactions.filter(isProductSpend);
    const spendTotal = sum(spendRows.map((t) => t.amount));
    const cashSettled = ctx.transactions.filter((t) => isProductSpend(t) && ctx.cashWalletIds.has(t.wallet_id));
    const cashSettledSpend = sum(cashSettled.map((t) => t.amount));
    const incoming = ctx.transactions.filter((t) => t.direction === "inflow" && !t.cash_out);
    const incomingTotal = sum(incoming.map((t) => t.amount));
    // Days between an inflow and the next cash-out tells us how tightly the two are linked.
    const inflowTimes = ctx.transactions
        .filter((t) => t.direction === "inflow" && t.category !== "cash")
        .map((t) => new Date(t.timestamp).getTime())
        .sort((a, b) => a - b);
    const gaps = [];
    for (const out of cashOuts) {
        const t = new Date(out.timestamp).getTime();
        let best = Infinity;
        for (const inflow of inflowTimes) {
            if (inflow <= t && t - inflow < best)
                best = t - inflow;
        }
        if (Number.isFinite(best))
            gaps.push(Math.round(best / 86_400_000));
    }
    const daysAfterIncomeMedian = gaps.length ? round(quantiles(gaps).p50, 1) : null;
    const byCategory = new Map();
    for (const t of cashSettled)
        byCategory.set(t.category, (byCategory.get(t.category) ?? 0) + t.amount);
    const topCashCategories = [...byCategory.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([key, amount]) => ({
        key,
        label: key.charAt(0).toUpperCase() + key.slice(1),
        amount: round(amount, 0),
        share: cashSettledSpend > 0 ? round(amount / cashSettledSpend, 4) : 0,
    }));
    const digitalSpend = spendTotal - cashSettledSpend;
    const chain = [
        {
            step: "in",
            label: "Money received",
            labelBn: "আসা টাকা",
            amount: round(incomingTotal, 0),
            share: 1,
            count: incoming.length,
        },
        {
            step: "digital",
            label: "Stays digital",
            labelBn: "ডিজিটালেই থাকে",
            amount: round(digitalSpend, 0),
            share: spendTotal > 0 ? round(digitalSpend / spendTotal, 4) : 0,
            count: spendRows.filter((t) => !ctx.cashWalletIds.has(t.wallet_id)).length,
        },
        {
            step: "cash",
            label: "Converted to cash",
            labelBn: "নগদে রূপান্তর",
            amount: round(cashOutTotal, 0),
            share: incomingTotal > 0 ? round(cashOutTotal / incomingTotal, 4) : 0,
            count: cashOuts.length,
        },
        {
            step: "cash_spend",
            label: "Spent from cash",
            labelBn: "নগদ থেকে খরচ",
            amount: round(cashSettledSpend, 0),
            share: spendTotal > 0 ? round(cashSettledSpend / spendTotal, 4) : 0,
            count: cashSettled.length,
        },
    ];
    const months = Math.max(1, ctx.monthly.length);
    const trend = ctx.monthly.map((m) => ({ month: m.key, cashShare: m.cashShare }));
    const shareOfSpend = spendTotal > 0 ? cashSettledSpend / spendTotal : 0;
    const evidence = {
        engine: "Cash-Out Dependency Analyzer",
        headline: `${(shareOfSpend * 100).toFixed(0)}% of spending settles in cash`,
        confidence: round(clamp(0.55 + Math.min(months, 9) * 0.04, 0.55, 0.9), 2),
        confidenceNote: `Cash wallets are identified as any wallet that has ever received a cash-in, matching the dataset's own definition.`,
        metrics: [
            { id: "cash_out_count", label: "Cash-out transactions", value: cashOuts.length, unit: "count", detail: `${(cashOuts.length / months).toFixed(1)} per month`, source: "transactions" },
            { id: "cash_out_total", label: "Total converted to cash", value: round(cashOutTotal, 0), unit: "bdt", detail: `average ৳${Math.round(mean(cashOuts.map((t) => t.amount)) || 0).toLocaleString("en-US")} per withdrawal`, source: "transactions" },
            { id: "cash_spend_share", label: "Cash share of consumption", value: round(shareOfSpend, 4), unit: "percent", detail: "cash-wallet spend ÷ total spend", source: "transactions" },
            { id: "cash_of_incoming", label: "Cash as share of money received", value: incomingTotal > 0 ? round(cashOutTotal / incomingTotal, 4) : 0, unit: "percent", detail: "cash-out ÷ non-cash inflow", source: "transactions" },
            { id: "lag", label: "Typical gap after income", value: daysAfterIncomeMedian ?? 0, unit: "days", detail: "median days from inflow to the next cash-out", source: "transactions" },
        ],
        reasons: [
            {
                polarity: shareOfSpend > 0.4 ? "negative" : "neutral",
                text: `${cashOuts.length} withdrawals totalling ৳${Math.round(cashOutTotal).toLocaleString("en-US")} moved money out of the digital system across ${months} months.`,
            },
            ...(daysAfterIncomeMedian !== null
                ? [
                    {
                        polarity: daysAfterIncomeMedian <= 3 ? "negative" : "neutral",
                        text: `Cash-outs typically happen ${daysAfterIncomeMedian} day(s) after money arrives.`,
                    },
                ]
                : []),
            {
                polarity: "neutral",
                text: `Most cash-funded categories: ${topCashCategories.slice(0, 3).map((c) => `${c.label} (৳${Math.round(c.amount).toLocaleString("en-US")})`).join(", ") || "n/a"}.`,
            },
        ],
        assumptions: [
            "Cash settled spending is measured only where a wallet has previously received physical cash.",
            "Cash use is reported as a fact about the ledger, never as a judgement about which channel the customer should prefer.",
        ],
        sources: ["transactions.csv", "wallets.csv"],
    };
    return {
        cashOutCount: cashOuts.length,
        cashOutTotal: round(cashOutTotal, 0),
        shareOfSpend: round(shareOfSpend, 4),
        shareOfIncoming: incomingTotal > 0 ? round(cashOutTotal / incomingTotal, 4) : 0,
        avgCashOut: round(mean(cashOuts.map((t) => t.amount)), 0),
        cashOutFrequencyPerMonth: round(cashOuts.length / months, 1),
        daysAfterIncomeMedian,
        cashSettledSpend: round(cashSettledSpend, 0),
        chain,
        topCashCategories,
        months,
        trend,
        evidence,
    };
}
export function runSourceEngine(ctx) {
    const byKey = new Map();
    for (const ev of ctx.incomeEvents) {
        const key = `${ev.income_type}|${ev.source}`;
        const e = byKey.get(key) ?? { amounts: [], days: [], regularity: ev.regularity, type: ev.income_type, source: ev.source };
        e.amounts.push(ev.amount);
        e.days.push(Number(ev.timestamp.slice(8, 10)));
        byKey.set(key, e);
    }
    const total = sum([...byKey.values()].map((e) => sum(e.amounts)));
    const incomeSources = [...byKey.values()]
        .map((e) => {
        const m = mean(e.amounts);
        const sd = e.amounts.length > 1 ? Math.sqrt(mean(e.amounts.map((a) => (a - m) ** 2))) : 0;
        const cv = m > 0 ? sd / m : 0;
        return {
            key: e.source,
            label: titleCase(e.source.replace(/_/g, " ")),
            labelBn: SOURCE_LABELS_BN[e.source] ?? titleCase(e.source.replace(/_/g, " ")),
            amount: round(sum(e.amounts), 0),
            share: total > 0 ? round(sum(e.amounts) / total, 4) : 0,
            occurrences: e.amounts.length,
            stability: round(clamp(1 / (1 + cv), 0, 1), 3),
            cv: round(cv, 3),
            typicalDay: Math.round(mean(e.days)),
            regularity: e.regularity,
        };
    })
        .sort((a, b) => b.amount - a.amount);
    const liquidTypes = new Set(["upay", "bank", "cash"]);
    const closingTotal = sum(ctx.wallets.filter((w) => liquidTypes.has(w.wallet_type)).map((w) => w.closingBalance));
    const wallets = ctx.wallets.map((w) => {
        const rows = ctx.transactions.filter((t) => t.wallet_id === w.wallet_id);
        const inflow = sum(rows.filter((t) => t.direction === "inflow").map((t) => t.amount));
        const outflow = sum(rows.filter((t) => t.direction === "outflow").map((t) => t.amount));
        return {
            walletId: w.wallet_id,
            type: w.wallet_type,
            opening: round(w.opening_balance, 0),
            closing: round(w.closingBalance, 0),
            inflow: round(inflow, 0),
            outflow: round(outflow, 0),
            txCount: rows.length,
            share: closingTotal > 0 && liquidTypes.has(w.wallet_type) ? round(w.closingBalance / closingTotal, 4) : 0,
        };
    });
    const stabilitySpread = incomeSources.length
        ? Math.max(...incomeSources.map((s) => s.stability)) - Math.min(...incomeSources.map((s) => s.stability))
        : 0;
    const volatile = incomeSources.filter((s) => s.stability < 0.7);
    const forecastImpact = volatile.length > 0
        ? `${volatile.map((v) => v.label).join(", ")} ${volatile.length === 1 ? "varies" : "vary"} significantly, so the forecast gives that part of the income a wider confidence band.`
        : "All income sources are regular, so the forecast can place income on a specific day with reasonable confidence.";
    const evidence = {
        engine: "Money Source Intelligence",
        headline: `${incomeSources.length} income source(s), ${ctx.wallets.length} wallet(s)`,
        confidence: round(clamp(0.55 + Math.min(ctx.monthly.length, 9) * 0.04, 0.55, 0.9), 2),
        confidenceNote: "Stability per source is 1 / (1 + coefficient of variation) over observed events.",
        metrics: incomeSources.slice(0, 6).map((s, i) => ({
            id: `source_${i}`,
            label: s.label,
            value: s.amount,
            unit: "bdt",
            detail: `${(s.share * 100).toFixed(0)}% of income · stability ${(s.stability * 100).toFixed(0)}% · ${s.regularity}`,
            source: "income_events",
        })),
        reasons: [
            { polarity: "neutral", text: forecastImpact },
            {
                polarity: "neutral",
                text: `Closing balances: ${ctx.wallets
                    .filter((w) => w.wallet_type !== "other_digital")
                    .map((w) => `${w.wallet_type} ৳${Math.round(w.closingBalance).toLocaleString("en-US")}`)
                    .join(", ")}.`,
            },
        ],
        assumptions: [
            "Wallet type is taken from the wallet record, not inferred from transaction behaviour.",
            "Day-31 income events are normalised to day 28 when planning, because not every month has 31 days.",
        ],
        sources: ["income_events.csv", "wallets.csv", "transactions.csv"],
    };
    return { incomeSources, wallets, stabilitySpread, forecastImpact, forecastImpactBn: forecastImpact, evidence };
}
const SOURCE_LABELS_BN = {
    employer: "নিয়োগকর্তা",
    own_business: "নিজের ব্যবসা",
    freelance_client: "ফ্রিল্যান্স ক্লায়েন্ট",
    family: "পরিবার",
};
function titleCase(value) {
    return value.replace(/\b\w/g, (c) => c.toUpperCase());
}
/** Timeline of a typical cash-out cycle, for the diagram on the cash-out page. */
export function cashOutTimeline(ctx) {
    return ctx.daily
        .filter((d) => d.cashOut > 0)
        .slice(-40)
        .map((d) => ({ date: d.iso, cashOut: round(d.cashOut, 0), income: round(d.income, 0) }));
}
export function cashOutHourHistogram(ctx) {
    const buckets = Array.from({ length: 24 }, (_, hour) => ({ hour, count: 0 }));
    for (const t of ctx.transactions.filter((x) => x.transaction_type === "cash_out")) {
        buckets[parseDate(t.timestamp).getHours()].count += 1;
    }
    return buckets.filter((b) => b.count > 0);
}
