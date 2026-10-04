import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarRange, CheckCircle2, ClipboardList, Sparkles, TriangleAlert } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { MonthlyFlowChart, MoneyBars, Panel, VIZ } from "@/components/charts";
const PRIORITY_LABEL = {
    "do-now": { en: "Do now", bn: "এখনই করুন" },
    plan: { en: "Plan", bn: "পরিকল্পনা" },
    watch: { en: "Watch", bn: "লক্ষ্য রাখুন" },
};
const PRIORITY_TONE = {
    "do-now": "bad",
    plan: "warn",
    watch: "neutral",
};
export default function MonthlyReview() {
    const bundle = useBundle();
    const f = useFmt();
    const { lang } = useCopilot();
    if (!bundle)
        return null;
    const { ctx, actions, insights, anomaly, health, spending, monthEnd } = bundle;
    const last = ctx.monthly[ctx.monthly.length - 1];
    const prev = ctx.monthly[ctx.monthly.length - 2];
    const delta = last && prev ? last.spend - prev.spend : 0;
    const topCategories = [...spending.categories].sort((a, b) => b.amount - a.amount).slice(0, 6);
    const flagged = anomaly.hits.filter((h) => h.score > anomaly.threshold);
    return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("review", lang), subtitle: f.loc === "bn"
                    ? "এই মাসের একটি সংক্ষিপ্ত সমীক্ষা: কী ভালো হয়েছে, কী সতর্কতা দাবি করছে, এবং একটি কাজ বেছে নিতে হলে কোনটি আগে।"
                    : "A short review of where this month stands: what improved, what deserves a second look, and which single action comes first.", actions: _jsxs(Chip, { tone: "neutral", children: [_jsx(CalendarRange, { className: "h-3 w-3" }), last ? f.month(last.key) : copy("noData", lang)] }) }), _jsxs(Grid, { cols: 4, className: "mb-5", children: [_jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "আয়" : "Income", value: f.taka(last?.income ?? 0), hint: prev ? `${f.bi(prev.income >= (last?.income ?? 0) ? "above" : "below", prev.income >= (last?.income ?? 0) ? "আগের মাসের তুলনায় বেশি" : "আগের মাসের তুলনায় কম")} ${f.taka(Math.abs((last?.income ?? 0) - prev.income))}` : undefined }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "ব্যয়" : "Spending", value: f.taka(last?.spend ?? 0), tone: delta > 0 ? "warn" : "good", hint: prev
                                ? `${delta >= 0 ? "+" : ""}${f.taka(delta)} ${f.loc === "bn" ? "আগের মাসের তুলনায়" : "vs last month"}`
                                : undefined }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "অতিশেষ" : "Surplus", value: f.taka(last?.savings ?? 0), big: true, tone: (last?.savings ?? 0) >= 0 ? "good" : "bad", hint: `${f.loc === "bn" ? "লক্ষ্যে জমা" : "toward goals"} ${f.taka(last?.contribution ?? 0)}` }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "মাস শেষের পূর্বাভাস" : "Month-end outlook", value: f.taka(monthEnd.forecast.expectedEndingBalance), tone: monthEnd.forecast.expectedEndingBalance < 0 ? "bad" : "good", hint: f.loc === "bn"
                                ? `আর ${f.num(monthEnd.daysRemaining, 0)} দিন বাকি · নিম্নমুখ ${f.taka(monthEnd.forecast.minBalance)}`
                                : `${monthEnd.daysRemaining} days left · trough ${f.taka(monthEnd.forecast.minBalance)}` }) })] }), _jsxs(Grid, { cols: 3, className: "mb-5", children: [_jsxs("div", { className: "col-span-2 space-y-4", children: [_jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "এই মাসের সারসংক্ষেপ" : "The month in one view", title: f.loc === "bn" ? "আয়, ব্যয় ও অতিশেষ" : "Income, spending and surplus", right: _jsx(EvidenceButton, { evidence: spending.evidence }) }), _jsx(MonthlyFlowChart, { data: ctx.monthly.slice(-8).map((m) => ({
                                            key: m.key,
                                            income: Math.round(m.income),
                                            spend: Math.round(m.spend),
                                            savings: Math.round(m.savings),
                                        })), lang: f.tlang, height: 250 }), _jsx("p", { className: "mt-3 text-[11.5px] leading-relaxed text-ink-500", children: f.loc === "bn"
                                            ? `${ctx.monthly.length} মাসের গড় অতিশেষ ${f.taka(ctx.monthlyIncomeAvg - ctx.monthlySpendAvg)}। স্বাস্থ্য স্কোর এখন ${f.num(health.score)}/100।`
                                            : `Mean surplus across ${ctx.monthly.length} months is ${f.taka(ctx.monthlyIncomeAvg - ctx.monthlySpendAvg)}. Health currently sits at ${health.score}/100.` })] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "খাতভিত্তিক" : "By category", title: f.loc === "bn" ? "কোথায় টাকা গেছে" : "Where the money went", subtitle: f.loc === "bn"
                                            ? "শুধুমাত্র এই মাসের লেজার থেকে।"
                                            : "From this month's ledger only." }), _jsx(MoneyBars, { lang: f.tlang, height: 220, xKey: "label", data: topCategories.map((c) => ({ label: f.bi(c.label, c.labelBn), amount: Math.round(c.amount) })), keys: [{ key: "amount", label: f.loc === "bn" ? "ব্যয়" : "spend", color: VIZ[0] }] }), _jsx("div", { className: "mt-4", children: _jsx(Table, { align: "right", head: [
                                                f.loc === "bn" ? "খাত" : "Category",
                                                f.loc === "bn" ? "পরিমাণ" : "Amount",
                                                f.loc === "bn" ? "অংশ" : "Share",
                                                f.loc === "bn" ? "ট্রেন্ড" : "Trend",
                                            ], rows: topCategories.map((c) => {
                                                const trend = c.vsLastMonth ?? 0;
                                                return [
                                                    _jsx("span", { className: "font-semibold text-ink-800", children: f.bi(c.label, c.labelBn) }),
                                                    f.taka(c.amount),
                                                    f.percent(c.share, 0),
                                                    _jsxs("span", { className: cx("tabular font-bold", trend > 0 ? "text-brand-700" : trend < 0 ? "text-mint-700" : "text-ink-400"), children: [trend > 0 ? "▲" : trend < 0 ? "▼" : "—", " ", trend !== 0 ? f.percent(Math.abs(trend), 0) : ""] }),
                                                ];
                                            }) }) })] })] }), _jsxs("div", { className: "space-y-4", children: [_jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "করণীয়" : "Next step", title: f.loc === "bn" ? "একটি কাজ বেছে নিন" : "Pick one thing", subtitle: f.loc === "bn"
                                            ? "সব ফলাফল একসঙ্গে করা যায় না — তাই সবচেয়ে বেশি পার্থক্য তৈরি করে এমন একটিই দেখানো হয়েছে।"
                                            : "Doing everything at once is how nothing happens, so only the highest-leverage item is shown.", right: _jsxs(Chip, { tone: "neutral", children: [_jsx(ClipboardList, { className: "h-3 w-3" }), actions.length] }) }), actions[0] ? (_jsxs("div", { className: "rounded-xl border border-brand-200 bg-brand-50/40 p-4", children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx(Chip, { tone: PRIORITY_TONE[actions[0].priority], children: f.bi(PRIORITY_LABEL[actions[0].priority].en, PRIORITY_LABEL[actions[0].priority].bn) }), actions[0].amount ? (_jsx("span", { className: "tabular text-[12px] font-bold text-ink-700", children: f.taka(actions[0].amount) })) : null] }), _jsx("h3", { className: "mt-2 text-[15px] leading-snug font-bold text-ink-900", children: f.bi(actions[0].title, actions[0].titleBn) }), _jsx("dl", { className: "mt-3 space-y-2.5", children: [
                                                    { k: f.loc === "bn" ? "কেন" : "Why", v: f.bi(actions[0].why, actions[0].whyBn) },
                                                    { k: f.loc === "bn" ? "কী" : "What", v: f.bi(actions[0].what, actions[0].whatBn) },
                                                    { k: f.loc === "bn" ? "আপনি কী করতে পারেন" : "What you can do", v: f.bi(actions[0].doThis, actions[0].doThisBn) },
                                                ].map((row) => (_jsxs("div", { children: [_jsx("dt", { className: "text-[10.5px] font-bold tracking-wide text-ink-400 uppercase", children: row.k }), _jsx("dd", { className: "mt-0.5 text-[12.5px] leading-relaxed text-ink-700", children: row.v })] }, row.k))) }), actions[0].route ? (_jsxs(Link, { to: actions[0].route, className: "mt-3.5 inline-flex items-center gap-1.5 text-[12.5px] font-bold text-brand-700 hover:underline", children: [f.loc === "bn" ? "সংশ্লিষ্ট পেজ দেখুন" : "Open the related page", _jsx(ArrowRight, { className: "h-3.5 w-3.5" })] })) : null] })) : (_jsx("p", { className: "text-[12.5px] text-ink-500", children: copy("noData", lang) })), actions.length > 1 ? (_jsx("ul", { className: "mt-4 space-y-2 border-t border-ink-100 pt-3", children: actions.slice(1).map((a) => (_jsxs("li", { className: "flex items-start justify-between gap-3", children: [_jsx("span", { className: "text-[12px] leading-snug text-ink-600", children: f.bi(a.title, a.titleBn) }), _jsx("span", { className: "shrink-0", children: _jsx(Chip, { tone: PRIORITY_TONE[a.priority], children: f.bi(PRIORITY_LABEL[a.priority].en, PRIORITY_LABEL[a.priority].bn) }) })] }, a.id))) })) : null] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "বিশেষ লক্ষ্য" : "Worth a look", title: f.loc === "bn" ? "সতর্কতার বিষয়" : "Signals this month" }), _jsxs("ul", { className: "space-y-2.5", children: [insights.map((i) => (_jsxs("li", { className: "flex items-start gap-2.5", children: [i.kind === "positive" ? (_jsx(CheckCircle2, { className: "mt-0.5 h-4 w-4 shrink-0 text-mint-600" })) : i.kind === "warning" ? (_jsx(TriangleAlert, { className: "mt-0.5 h-4 w-4 shrink-0 text-brand-600" })) : (_jsx(Sparkles, { className: "mt-0.5 h-4 w-4 shrink-0 text-sky-500" })), _jsxs("div", { className: "min-w-0", children: [_jsx("p", { className: "text-[12.5px] leading-snug font-bold text-ink-900", children: f.bi(i.title, i.titleBn) }), _jsx("p", { className: "mt-0.5 text-[11.5px] leading-relaxed text-ink-500", children: f.bi(i.body, i.bodyBn) }), _jsx("p", { className: "mt-1 text-[10.5px] text-ink-400", children: i.engine })] })] }, i.id))), !insights.length ? _jsx("li", { className: "text-[12.5px] text-ink-500", children: copy("noData", lang) }) : null] })] })] })] }), _jsxs(Grid, { cols: 2, className: "mb-5", children: [_jsx(Panel, { title: f.loc === "bn" ? "দিনভিত্তিক ব্যয়" : "Daily spending", subtitle: f.loc === "bn" ? "এই মাসের প্রতিদিন" : "this month, day by day", height: 220, children: _jsx(MoneyBars, { lang: f.tlang, height: 220, xKey: "day", xTick: (v) => f.num(Number(v), 0), data: ctx.daily.slice(-30).map((d) => ({ day: Number(d.iso.slice(8, 10)), spend: Math.round(d.spend) })), keys: [{ key: "spend", label: f.loc === "bn" ? "ব্যয়" : "spend", color: VIZ[0] }] }) }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "লেজার পর্যালোচনা" : "Ledger review", title: f.loc === "bn" ? "অস্বাভাবিক লেনদেন" : "Unusual transactions", subtitle: f.loc === "bn"
                                    ? "আইসোলেশন ফরেস্ট অতিক্রান্ত লেনদেনকে আলাদা করে দেখায় — এটি কোনো সন্দেহ নয়, কেবল পর্যালোচনার তালিকা।"
                                    : "An isolation forest flags transactions that do not look like this category's habit — a review list, not an accusation.", right: _jsx(Chip, { tone: flagged.length ? "warn" : "good", children: f.num(flagged.length) }) }), flagged.length ? (_jsx(Table, { align: "right", head: [
                                    f.loc === "bn" ? "তারিখ" : "Date",
                                    f.loc === "bn" ? "খাত" : "Category",
                                    f.loc === "bn" ? "পরিমাণ" : "Amount",
                                    f.loc === "bn" ? "স্কোর" : "Score",
                                ], rows: flagged.slice(0, 6).map((h) => [
                                    f.shortDate(h.transaction.timestamp.slice(0, 10)),
                                    h.transaction.category,
                                    f.taka(h.transaction.amount),
                                    _jsx("span", { className: "tabular font-bold text-brand-700", children: f.num(h.score, 2) }),
                                ]) })) : (_jsxs("div", { children: [_jsx("p", { className: "text-[12.5px] text-ink-500", children: f.loc === "bn"
                                            ? "এই মাসে কোনো লেনদেন অস্বাভাবিক মনে হয়নি।"
                                            : "Nothing in this month looked out of character." }), _jsx("div", { className: "mt-3", children: _jsx(Meter, { value: 100, tone: "good" }) })] })), _jsx("p", { className: "mt-3 text-[11px] text-ink-400", children: f.loc === "bn"
                                    ? `সীমা ${f.num(anomaly.threshold, 3)} · ${f.num(anomaly.hits.length)} টি মিলেছে মোট।`
                                    : `Threshold ${anomaly.threshold} · ${anomaly.hits.length} total hits.` })] })] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: copy("evidence", lang), title: spending.evidence.headline, right: _jsxs(Chip, { tone: "neutral", children: [Math.round(spending.evidence.confidence * 100), "% ", copy("confidence", lang)] }) }), _jsx(EvidenceBody, { evidence: spending.evidence })] }), _jsx("div", { className: "mt-5", children: _jsx(Banner, { tone: "neutral", title: f.loc === "bn" ? "পর্যালোচনার পরিধি" : "Scope of this review", children: _jsx("p", { children: f.loc === "bn"
                            ? `এই পাতা শুধু ${f.fullDate(ctx.asOf.toISOString().slice(0, 10))} তারিখ পর্যন্ত লেজারের তথ্য ব্যবহার করে এবং একটি নির্দিষ্ট মাসের সারসংক্ষেপ। এটি কোনো করা পরামর্শ নয়।`
                            : `This review uses the ledger only up to ${ctx.asOf.toISOString().slice(0, 10)} and summarises one specific month. It is not a set of instructions.` }) }) })] }));
}
