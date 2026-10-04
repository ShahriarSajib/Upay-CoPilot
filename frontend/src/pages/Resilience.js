import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Activity, ShieldQuestion, TrendingDown } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { MoneyBars, Panel, VIZ } from "@/components/charts";
import { RESILIENCE_LABELS, negativeSurplusMonths } from "@/engines/resilience";
import { runSimulation, DEFAULT_SCENARIO } from "@/engines/simulator";
import { bandFor } from "@/lib/format";
const BAND = {
    strong: { en: "Strong", bn: "শক্তিশালী" },
    good: { en: "Good", bn: "ভালো" },
    moderate: { en: "Moderate", bn: "মাঝারি" },
    weak: { en: "Weak", bn: "দুর্বল" },
    critical: { en: "Critical", bn: "সংকটজনক" },
};
export default function Resilience() {
    const bundle = useBundle();
    const f = useFmt();
    const { lang } = useCopilot();
    if (!bundle)
        return null;
    const { ctx, resilience, health, cashOut } = bundle;
    const pressure = negativeSurplusMonths(ctx);
    const shocks = [0.25, 0.5, 0.75, 1].map((share) => {
        const amount = Math.round(ctx.monthlySpendAvg * 0.6 * share);
        const sim = runSimulation(ctx, { ...DEFAULT_SCENARIO, unexpectedExpense: amount });
        return {
            label: `${f.num(share * 100, 0)}%`,
            balance: Math.max(0, Math.round(sim.scenario.minBalance)),
            absorbed: sim.scenario.minBalance >= 0,
            risk: sim.riskLevel,
        };
    });
    const biggestShock = shocks[3].balance;
    return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("resilience", lang), subtitle: f.loc === "bn"
                    ? "স্বাস্থ্য স্কোরের প্রশ্ন হলো ‘এখন কেমন করছেন’। সহনশীলতার প্রশ্ন হলো ‘কতটা খারাপ ঘটলেও আপনি বাধ্য হবেন না’ — দুটি প্রায়ই অল্প ব্যতীত মেলে না।"
                    : "Health asks how you are managing now. Resilience asks how much could go wrong before a bad decision becomes necessary — the two often disagree." }), _jsxs(Grid, { cols: 4, className: "mb-5", children: [_jsxs(Card, { children: [_jsx("div", { className: "text-[11px] font-semibold tracking-wide text-ink-400 uppercase", children: copy("resilience", lang) }), _jsxs("div", { className: "tabular mt-1 flex items-end gap-2", children: [_jsx("span", { className: "text-[44px] leading-none font-black tracking-[-0.03em] text-ink-900", children: resilience.score }), _jsx("span", { className: "mb-1.5 text-[13px] font-semibold text-ink-400", children: "/100" })] }), _jsx("div", { className: "mt-1 text-[14px] font-bold text-brand-700", children: f.bi(BAND[resilience.band].en, BAND[resilience.band].bn) }), _jsx("div", { className: "mt-3", children: _jsx(Meter, { value: resilience.score, tone: resilience.score >= 68 ? "good" : resilience.score >= 45 ? "warn" : "bad" }) })] }), _jsxs(Card, { children: [_jsx(Stat, { label: f.loc === "bn" ? "স্বাস্থ্য বনাম সহনশীলতা" : "Health vs resilience", value: _jsxs("span", { className: "text-[18px]", children: [f.num(health.score), " ", _jsx("span", { className: "text-ink-300", children: "vs" }), " ", f.num(resilience.score)] }), hint: Math.abs(health.score - resilience.score) <= 5
                                    ? f.loc === "bn" ? "দুটি প্রায় এক" : "the two broadly agree"
                                    : f.loc === "bn"
                                        ? `${health.score > resilience.score ? "স্বাস্থ্য" : "সহনশীলতা"} বেশি ${f.num(Math.abs(health.score - resilience.score))} পয়েন্ট`
                                        : `${health.score > resilience.score ? "health" : "resilience"} runs ${f.num(Math.abs(health.score - resilience.score))} points higher` }), _jsx("p", { className: "mt-2 text-[11.5px] leading-relaxed text-ink-500", children: f.loc === "bn"
                                    ? "গড় বেশি খরচ করলেও জমানো টাকা বেশি থাকলে সহনশীলতা বেশি হতে পারে — এই কারণে এটি আলাদা একটি স্কোর।"
                                    : "A household can spend more than average and still be resilient if the buffer is thick. That is exactly why this is a separate score." })] }), _jsxs(Card, { children: [_jsx(Stat, { label: f.loc === "bn" ? "শোক সহনের ক্ষমতা" : "Shock absorption", value: f.num(resilience.shockTolerance, 1), big: true, tone: resilience.shockTolerance >= 2 ? "good" : resilience.shockTolerance >= 1 ? "warn" : "bad", hint: `${f.loc === "bn" ? "গড় মাসের" : "of a"} ${f.taka(ctx.monthlySpendAvg * 0.6)} ${f.loc === "bn" ? "ধাক্কা" : "shock"}` }), _jsx("div", { className: "mt-2", children: _jsx(Meter, { value: (resilience.shockTolerance / 3) * 100, tone: resilience.shockTolerance >= 2 ? "good" : "warn" }) })] }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "ঋণাত্মক মাস" : "Negative-surplus months", value: f.num(pressure.count), big: true, tone: pressure.count > 2 ? "bad" : pressure.count > 0 ? "warn" : "good", hint: `${f.percent(pressure.share, 0)} ${f.loc === "bn" ? "মাস" : "of months"} · ${f.loc === "bn" ? "সবচেয়ে খারাপ" : "worst"} ${f.taka(pressure.worst)}` }) })] }), _jsxs(Grid, { cols: 2, className: "mb-5", children: [_jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "সাতটি মাত্রা" : "Seven dimensions", title: f.loc === "bn" ? "কোনটি কতটা টেনেছে" : "What moved the score", right: _jsx(EvidenceButton, { evidence: resilience.evidence }) }), _jsx("div", { className: "space-y-2.5", children: resilience.dimensions.map((d) => (_jsxs("div", { children: [_jsxs("div", { className: "mb-1 flex items-baseline justify-between gap-3", children: [_jsx("span", { className: "truncate text-[12.5px] font-semibold text-ink-800", children: f.bi(d.label, d.labelBn ?? RESILIENCE_LABELS[d.key]?.bn ?? d.label) }), _jsxs("span", { className: "tabular shrink-0 text-[11.5px] font-bold text-ink-600", children: [f.num(d.value), "/100 \u00B7 ", d.contribution >= 0 ? "+" : "", f.num(d.contribution, 1), " ", f.loc === "bn" ? "পয়েন্ট" : "pts"] })] }), _jsx(Meter, { value: d.value, tone: d.value >= 65 ? "good" : d.value >= 45 ? "warn" : "bad" }), _jsx("p", { className: "mt-1 text-[11.5px] leading-snug text-ink-500", children: d.detail })] }, d.key))) })] }), _jsxs("div", { className: "space-y-4", children: [_jsx(Panel, { title: f.loc === "bn" ? "বাজেটের ধাক্কা সহ্য" : "Shock tolerance test", subtitle: f.loc === "bn"
                                    ? `প্রতিটি ধাক্কা মাসে আয়ের ৬০% পর্যন্ত ব্যয়ের সমান — একটি সাধারণ "বড় খরচ"।`
                                    : `Each shock is sized against 60% of a month's spend — a plausible large unplanned bill.`, height: 220, children: _jsx(MoneyBars, { lang: f.tlang, height: 220, xKey: "label", data: shocks.map((s) => ({ label: s.label, remaining: s.balance, absorbed: s.absorbed ? 1 : 0 })), keys: [
                                        { key: "remaining", label: f.loc === "bn" ? "হওয়ার পর ব্যালেন্স" : "balance after", color: VIZ[1] },
                                        { key: "absorbed", label: f.loc === "bn" ? "শোষিত" : "absorbed", color: VIZ[3] },
                                    ] }) }), _jsxs(Card, { children: [_jsx(CardHeader, { title: f.loc === "bn" ? "শোক টেস্টের ফল" : "What the test shows" }), _jsx("div", { className: "space-y-2.5", children: shocks.map((s) => (_jsxs("div", { className: "flex items-center justify-between gap-3", children: [_jsx("span", { className: "text-[12px] font-semibold text-ink-700", children: f.loc === "bn" ? `মাসের ${s.label} খরচ` : `${s.label} of monthly spend` }), _jsx("span", { className: cx("tabular text-[12px] font-bold", s.absorbed ? "text-mint-700" : "text-brand-700"), children: s.absorbed
                                                        ? f.loc === "bn"
                                                            ? "সামলানো যায়"
                                                            : "absorbed"
                                                        : f.loc === "bn"
                                                            ? "রিজার্ভ ভাঙবে"
                                                            : "breaks the buffer" })] }, s.label))) }), _jsx("p", { className: "mt-3 text-[11.5px] leading-relaxed text-ink-500", children: f.loc === "bn"
                                            ? `বড়তম ধাক্কার পরেও ${f.taka(biggestShock)} বাকি থাকে। ঋণ নেওয়ার প্রয়োজন হতে শুরু করার সঙ্কেপ যে কোথায় — সেটিই এই সংখ্যা।`
                                            : `A ${f.taka(ctx.monthlySpendAvg * 0.6)} shock leaves ${f.taka(biggestShock)} behind. That is the point at which a decision starts being forced rather than chosen.` })] })] })] }), _jsxs(Grid, { cols: 2, className: "mb-5", children: [_jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "শক্তি" : "Strengths", title: f.loc === "bn" ? "যা ভালো দাঁড়িয়ে" : "What is holding", right: _jsx(Chip, { tone: "good", children: resilience.strengths.length }) }), resilience.strengths.length ? (_jsx("ul", { className: "space-y-2", children: resilience.strengths.map((d) => (_jsxs("li", { className: "rounded-xl border border-mint-100 bg-mint-50/50 px-3.5 py-2.5", children: [_jsxs("div", { className: "flex items-baseline justify-between gap-2", children: [_jsx("span", { className: "text-[12.5px] font-bold text-ink-900", children: f.bi(d.label, d.labelBn) }), _jsx("span", { className: "tabular text-[11.5px] font-bold text-mint-700", children: f.num(d.value) })] }), _jsx("p", { className: "mt-1 text-[11.5px] leading-relaxed text-ink-600", children: d.detail })] }, d.key))) })) : (_jsx("p", { className: "text-[12.5px] text-ink-500", children: copy("noData", lang) }))] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "মনোযোগ" : "Needs attention", title: f.loc === "bn" ? "যা দুর্বল দিক" : "Where the exposure is", right: _jsx(Chip, { tone: resilience.attention.length > 3 ? "bad" : "warn", children: resilience.attention.length }) }), resilience.attention.length ? (_jsx("ul", { className: "space-y-2", children: resilience.attention.map((d) => (_jsxs("li", { className: "rounded-xl border border-amber-100 bg-amber-50/40 px-3.5 py-2.5", children: [_jsxs("div", { className: "flex items-baseline justify-between gap-2", children: [_jsx("span", { className: "text-[12.5px] font-bold text-ink-900", children: f.bi(d.label, d.labelBn) }), _jsx("span", { className: "tabular text-[11.5px] font-bold text-amber-ink", children: f.num(d.value) })] }), _jsx("p", { className: "mt-1 text-[11.5px] leading-relaxed text-ink-600", children: d.detail })] }, d.key))) })) : (_jsx("p", { className: "text-[12.5px] text-ink-500", children: f.loc === "bn" ? "কোনো মাত্রাই দুর্বল ব্যান্ডে নেই।" : "No dimension sits in the weak band." }))] })] }), _jsxs(Card, { className: "mb-5", children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "মাসভিত্তিক চাপ" : "Month-by-month pressure", title: f.loc === "bn" ? "অতিশেষ কেমন বদলায়" : "How the surplus behaves" }), _jsx(Table, { align: "right", head: [
                            f.loc === "bn" ? "মাস" : "Month",
                            f.loc === "bn" ? "আয়" : "Income",
                            f.loc === "bn" ? "ব্যয়" : "Spend",
                            f.loc === "bn" ? "অতিশেষ" : "Surplus",
                            f.loc === "bn" ? "নগদের অংশ" : "Cash share",
                            f.loc === "bn" ? "লক্ষ্যে জমা" : "Goal deposit",
                        ], rows: ctx.monthly.map((m) => [
                            f.month(m.key),
                            f.taka(m.income),
                            f.taka(m.spend),
                            _jsx("span", { className: cx("tabular font-semibold", m.savings < 0 ? "text-brand-700" : "text-mint-700"), children: f.taka(m.savings) }),
                            f.percent(m.cashShare, 0),
                            f.taka(m.contribution),
                        ]) }), _jsx("p", { className: "mt-3 text-[11.5px] leading-relaxed text-ink-500", children: f.loc === "bn"
                            ? `${ctx.monthly.length} মাসের মধ্যে ${pressure.count} মাসে অতিশেষ ঋণাত্মক ছিল। গড় অতিশেষ ${f.taka(pressure.meanSurplus)}, মোট ${f.taka(pressure.total)}।`
                            : `${pressure.count} of ${ctx.monthly.length} months ran a negative surplus. Mean surplus ${f.taka(pressure.meanSurplus)}, cumulative ${f.taka(pressure.total)}.` })] }), _jsxs(Grid, { cols: 2, className: "mb-5", children: [_jsx(Banner, { tone: "info", title: f.loc === "bn" ? "এটি কী নয়" : "What this is not", icon: _jsx(ShieldQuestion, { className: "h-4 w-4" }), children: _jsx("p", { children: f.loc === "bn"
                                ? "সহনশীলতা স্কোর কোনো কাল্পনিক ঋণ স্কোর নয়, কোনো প্রতিষ্ঠান একে দেখে না, এবং এটি কোনো সিদ্ধান্তে ব্যবহার করা হয় না। এটি কেবল আপনার নিজের পরিকল্পনার সাহায্য।"
                                : "The resilience score is not a credit score, no institution sees it, and it feeds no decision. It exists to help you plan for yourself." }) }), _jsx(Banner, { tone: "neutral", title: f.loc === "bn" ? "কী বাদ পড়ে" : "What is not modelled", icon: _jsx(Activity, { className: "h-4 w-4" }), children: _jsx("p", { children: f.loc === "bn"
                                ? `পরিবারের সদস্য, ঋণ, বাড়ির খাত বা আয় থেকে বিরতির মতো বাস্তব জীবনের বিষয়গুলো এখানে নেই। নগদ থেকে হওয়া ${f.percent(cashOut.shareOfSpend, 0)} ব্যয়ও অন্তর্ভুক্ত, ফলে প্রকৃত অবস্থা কিছুটা ভালো হতে পারে।`
                                : `Family support, existing loans, housing costs and income gaps are not in this model. Because ${f.percent(cashOut.shareOfSpend, 0)} of spending settles in cash, reality may actually look somewhat better than this.` }) })] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: copy("evidence", lang), title: resilience.evidence.headline, right: _jsxs(Chip, { tone: "neutral", children: [Math.round(resilience.evidence.confidence * 100), "% ", copy("confidence", lang)] }) }), _jsx(EvidenceBody, { evidence: resilience.evidence }), _jsxs("p", { className: "mt-4 flex items-start gap-2 text-[11.5px] leading-relaxed text-ink-500", children: [_jsx(TrendingDown, { className: "mt-0.5 h-3.5 w-3.5 shrink-0" }), f.loc === "bn"
                                ? `ব্যান্ড: ${f.bi(BAND[bandFor(resilience.score)].en, BAND[bandFor(resilience.score)].bn)}। স্কোরে বয়স, লিঙ্গ, ঠিকানা বা ভাষার মতো কোনো সুরক্ষিত বৈশিষ্ট্য ব্যবহার করা হয়নি।`
                                : `Band: ${resilience.band}. No protected attribute — age, gender, location or language — is an input to this score.`] })] })] }));
}
