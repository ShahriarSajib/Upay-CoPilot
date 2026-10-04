import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AlertTriangle, ArrowDown, CalendarClock, Lock, Repeat } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { AreaTrend, Panel, VIZ } from "@/components/charts";
export default function Bills() {
    const bundle = useBundle();
    const f = useFmt();
    const { lang, pushEvidence } = useCopilot();
    if (!bundle)
        return null;
    const { ctx, bills } = bundle;
    const paymentDays = bills.days.filter((d) => d.obligations > 0);
    const flexible = ctx.recurring.filter((r) => !r.mandatory);
    const byMonth = (() => {
        const groups = new Map();
        for (const row of bills.rows) {
            const key = row.date.slice(0, 7);
            groups.set(key, [...(groups.get(key) ?? []), row]);
        }
        return [...groups.entries()];
    })();
    return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("bills", lang), subtitle: f.loc === "bn"
                    ? "প্রতিটি বিলের নির্ধারিত দিনে ব্যালেন্স কত থাকবে, কত যাবে এবং পরে কত থাকবে — ফোরকাস্টের হিসাব থেকেই।"
                    : "On every due date: the projected balance before the bill, the bill itself, and what is left after. Taken from the forecast, so the two can never disagree.", actions: _jsx(EvidenceButton, { evidence: bills.evidence }) }), _jsxs(Grid, { cols: 4, className: "mb-5", children: [_jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "৭ দিনে দেনা" : "Due in 7 days", value: f.taka(bills.next7), hint: `${f.loc === "bn" ? "পরবর্তী ৭ দিনের তাৎক্ষণিক প্রয়োজন" : "immediate cash requirement"}`, tone: bills.next7 > ctx.liquidBalance * 0.5 ? "warn" : "good" }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "৩০ দিনে দেনা" : "Due in 30 days", value: f.taka(bills.next30), hint: `${f.loc === "bn" ? "তরল ব্যালেন্সের" : "of liquid balance"} ${f.percent(ctx.liquidBalance > 0 ? bills.next30 / ctx.liquidBalance : 0, 0)}`, tone: bills.next30 > ctx.liquidBalance ? "bad" : "good" }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "বাধ্যতামূলকের অংশ" : "Committed to mandatory bills", value: f.percent(bills.committedShare, 1), hint: `${f.taka(bills.mandatoryTotal)} ${f.loc === "bn" ? `${bills.horizonDays} দিনে` : `over ${bills.horizonDays} days`}`, tone: bills.committedShare > 0.6 ? "warn" : "good" }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "সবচেয়ে টাইট দিন" : "Tightest post-payment day", value: bills.tightest ? f.taka(bills.tightest.balanceAfter) : f.loc === "bn" ? "নেই" : "None", hint: bills.tightest
                                ? `${f.loc === "bn" ? "দিন" : "on"} ${f.shortDate(bills.tightest.date)} · ${f.loc === "bn" ? "বাফার" : "buffer"} ${f.taka(bills.buffer)}`
                                : f.loc === "bn" ? "এই সময়ে কোনো বিল নেই" : "no payment day in this window", tone: bills.tightest && bills.tightest.balanceAfter < bills.buffer ? "bad" : "good" }) })] }), _jsx("div", { className: "mb-5", children: _jsx(Banner, { tone: "neutral", title: f.loc === "bn" ? "শুধু দেখার জন্য — কিছুই পরিবর্তন হয় না" : "Read-only — nothing here changes your money", icon: _jsx(Lock, { className: "h-4 w-4" }), children: _jsx("p", { children: f.loc === "bn"
                            ? "এই ক্যালেন্ডার কোনো বিল পরিশোধ করতে পারে না, অটোপে বদলাতে পারে না এবং কোনো আর্থিক প্রতিশ্রুতি দিতে পারে না। তারিখ ও পরিমাণ লেজারের রেকর্ড থেকে নেওয়া, হাতে লেখা নয়।"
                            : "This calendar cannot pay a bill, change an autopay setting, or make any financial commitment. Due days and amounts are read from the ledger's recurring table, never typed in by hand." }) }) }), bills.shortfallDay ? (_jsx("div", { className: "mb-5", children: _jsxs(Banner, { tone: "neutral", title: f.loc === "bn"
                        ? "একটি পরিশোধের দিনে আয় নির্ধারিত নয়"
                        : "One payment day has no income scheduled on it", icon: _jsx(AlertTriangle, { className: "h-4 w-4" }), children: [_jsx("p", { children: f.loc === "bn"
                                ? `${f.shortDate(bills.shortfallDay.date)} তারিখে ${f.taka(bills.shortfallDay.gap)} বিল জমা থাকা ব্যালেন্স থেকে যেতে হবে, কারণ ওই দিনে কোনো আয় নির্ধারিত নেই। ব্যালেন্স কতটুকু থাকবে তা নিচে দেখানো হয়েছে।`
                                : `${f.taka(bills.shortfallDay.gap)} due on ${f.shortDate(bills.shortfallDay.date)} has to come out of the balance carried into that day, because no income is scheduled for it. The projected balance on that date is listed below.` }), _jsx("button", { type: "button", onClick: () => pushEvidence(bills.evidence), className: "mt-2 text-[11.5px] font-bold text-brand-700 hover:underline", children: copy("showEvidence", lang) })] }) })) : null, _jsxs(Grid, { cols: 2, className: "mb-5", children: [_jsxs(Panel, { title: f.loc === "bn" ? "প্রত্যাশিত ব্যালেন্স ও বিল" : "Projected balance against bills", subtitle: f.loc === "bn"
                            ? `${bills.horizonDays} দিন, দৈনিক ব্যালেন্স ও সেই দিনে বকেয়া বিল`
                            : `${bills.horizonDays} days: closing balance each day, with the bills charged on it`, height: 260, children: [_jsx(AreaTrend, { data: bills.days.map((d) => ({
                                    date: d.date,
                                    after: d.balanceAfter,
                                    obligations: d.obligations,
                                    lower: d.lower,
                                })), keys: [
                                    { key: "after", label: f.loc === "bn" ? "দিন শেষে ব্যালেন্স" : "closing balance", color: VIZ[0] },
                                    { key: "lower", label: f.loc === "bn" ? "নিম্ন সীমা" : "lower band", color: VIZ[5] },
                                    { key: "obligations", label: f.loc === "bn" ? "বিল" : "bills due", color: VIZ[2] },
                                ], lang: f.tlang, height: 260 }), _jsx("p", { className: "mt-2 text-[11.5px] leading-relaxed text-ink-500", children: f.loc === "bn"
                                    ? "ব্যালেন্স লাইনটি ক্যাশ-ফ্লো ফোরকাস্টের নিজের প্রক্ষেপণ, তাই এই পাতা আর ফোরকাস্ট পাতা কখনো দ্বন্দ্ব করতে পারে না।"
                                    : "The balance line is the cash-flow forecast's own projection, so this page and the Forecast page can never contradict each other." })] }), _jsxs(Panel, { title: f.loc === "bn" ? "মাসভিত্তিক বিল" : "Bills by month", subtitle: f.loc === "bn"
                            ? `${bills.mandatoryTotal > 0 ? f.taka(bills.mandatoryTotal) : f.taka(0)} বাধ্যতামূলক · ${f.taka(bills.optionalTotal)} ঐচ্ছিক`
                            : `${f.taka(bills.mandatoryTotal)} mandatory · ${f.taka(bills.optionalTotal)} flexible`, height: 260, children: [_jsx(AreaTrend, { data: byMonth.map(([key, rows]) => ({
                                    date: key,
                                    mandatory: Math.round(rows.filter((r) => r.mandatory).reduce((a, r) => a + r.amount, 0)),
                                    optional: Math.round(rows.filter((r) => !r.mandatory).reduce((a, r) => a + r.amount, 0)),
                                })), xKey: "date", keys: [
                                    { key: "mandatory", label: f.loc === "bn" ? "বাধ্যতামূলক" : "mandatory", color: VIZ[2] },
                                    { key: "optional", label: f.loc === "bn" ? "ঐচ্ছিক" : "flexible", color: VIZ[4] },
                                ], lang: f.tlang, formatter: (v) => f.taka(v), height: 260 }), flexible.length ? (_jsx("p", { className: "mt-2 text-[11.5px] leading-relaxed text-ink-500", children: f.loc === "bn"
                                    ? `${flexible.map((r) => f.bi(r.expense_name, r.expense_name)).join(", ")} — ঐচ্ছিক বিল, তাই জরুরি প্রয়োজনে এগুলো সময়মতো আসে।`
                                    : `${flexible.map((r) => r.expense_name).join(", ")} ${flexible.length === 1 ? "is" : "are"} flexible, so ${flexible.length === 1 ? "it" : "they"} can be the first thing deferred in a tight month — a decision for you, not for this page.` })) : null] })] }), _jsxs(Card, { className: "mb-5", children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "পরিশোধের দিন" : "Payment days", title: f.loc === "bn" ? "প্রতিটি বিলের আগে ও পরে" : "Before and after each bill", subtitle: f.loc === "bn"
                            ? "বাম দিকে ব্যালেন্স, তারপর বিল, তারপর বাকি। প্রতিটি ধার ফোরকাস্টের হিসাব থেকে।"
                            : "Balance before the payment, the payment itself, then what remains. Every figure comes from the forecast model.", right: _jsxs(Chip, { tone: "neutral", children: [_jsx(Repeat, { className: "h-3 w-3" }), f.num(ctx.recurring.length), " ", f.loc === "bn" ? "টি নিয়মিত" : "recurring"] }) }), paymentDays.length ? (_jsx("div", { className: "space-y-3", children: paymentDays.slice(0, 12).map((day) => (_jsxs("div", { className: "rounded-xl border border-ink-200", children: [_jsxs("div", { className: "flex flex-wrap items-center justify-between gap-2 border-b border-ink-100 bg-ink-50/60 px-3.5 py-2.5", children: [_jsxs("span", { className: "inline-flex items-center gap-1.5 text-[12.5px] font-bold text-ink-800", children: [_jsx(CalendarClock, { className: "h-3.5 w-3.5 text-brand-500" }), f.fullDate(day.date), _jsx("span", { className: "font-normal text-ink-500", children: f.loc === "bn" ? "দিন" : `day ${day.dayOfMonth}` })] }), _jsxs("span", { className: "inline-flex items-center gap-1.5", children: [day.income > 0 ? (_jsxs(Chip, { tone: "good", children: ["+", f.taka(day.income), " ", f.loc === "bn" ? "আয়" : "income"] })) : null, day.tight ? (_jsx(Chip, { tone: "bad", children: f.loc === "bn" ? "বাফারের নিচে" : "below buffer" })) : null] })] }), _jsx(Table, { align: "right", head: [
                                        f.loc === "bn" ? "বিল" : "Bill",
                                        f.loc === "bn" ? "পরিমাণ" : "Amount",
                                        f.loc === "bn" ? "এই দিনে আয়" : "Income that day",
                                        f.loc === "bn" ? "বিলের আগে" : "Balance before",
                                        f.loc === "bn" ? "বিলের পরে" : "Balance after",
                                        f.loc === "bn" ? "অবস্থা" : "Status",
                                    ], rows: day.items.map((item) => [
                                        _jsx("span", { className: "font-semibold text-ink-800", children: item.name }),
                                        _jsxs("span", { className: "tabular font-semibold text-brand-700", children: ["\u2212", f.taka(item.amount)] }),
                                        item.incomeSameDay > 0 ? (_jsxs("span", { className: "text-mint-700", children: ["+", f.taka(item.incomeSameDay)] })) : (_jsx("span", { className: "text-ink-400", children: "\u2014" })),
                                        _jsx("span", { className: "tabular", children: f.taka(item.balanceBefore) }),
                                        _jsx("span", { className: "tabular font-bold text-ink-900", children: f.taka(item.balanceAfter) }),
                                        item.affordable ? (_jsx(Chip, { tone: "good", children: f.loc === "bn" ? "পরিশোধযোগ্য" : "covered" })) : (_jsx(Chip, { tone: "bad", children: f.loc === "bn" ? "ঘাটতি" : "short" })),
                                    ]) }), _jsxs("div", { className: "flex items-center justify-end gap-2 px-3.5 py-2", children: [_jsx("span", { className: "hidden w-28 sm:inline-block", children: _jsx(Meter, { value: Math.max(0, Math.min(100, (day.balanceAfter / Math.max(day.buffer, 1)) * 100)), tone: day.tight ? "bad" : "good" }) }), _jsx("span", { className: cx("text-[11px]", day.tight ? "font-bold text-amber-ink" : "text-ink-500"), children: day.tight
                                                ? f.loc === "bn"
                                                    ? `বাফারের ${f.taka(day.buffer)} এর নিচে`
                                                    : `under the ${f.taka(day.buffer)} buffer`
                                                : f.loc === "bn"
                                                    ? "বাফারের ওপরে"
                                                    : "above the buffer" })] })] }, day.date))) })) : (_jsx("p", { className: "text-[12.5px] text-ink-500", children: copy("noData", lang) })), paymentDays.length > 12 ? (_jsxs("p", { className: "mt-3 flex items-center gap-1.5 text-[11.5px] text-ink-500", children: [_jsx(ArrowDown, { className: "h-3.5 w-3.5" }), f.loc === "bn"
                                ? `আরও ${f.num(paymentDays.length - 12)} টি পরিশোধের দিন নিচে আছে।`
                                : `${paymentDays.length - 12} more payment days are listed in the full schedule below.`] })) : null] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "পূর্ণ সূচি" : "Full schedule", title: f.loc === "bn"
                            ? `${bills.horizonDays} দিনের সব বিল`
                            : `Every payment due in the next ${bills.horizonDays} days`, subtitle: f.loc === "bn"
                            ? "তারিখ অনুযায়ী সাজানো। ‘আয়’ কলাম দেখায় সেই দিনে নির্ধারিত আয় কত আসার কথা।"
                            : "Ordered by due date. The income column shows what is scheduled to land on the same day." }), _jsx(Table, { align: "right", head: [
                            f.loc === "bn" ? "তারিখ" : "Due",
                            f.loc === "bn" ? "বিল" : "Bill",
                            f.loc === "bn" ? "খাত" : "Category",
                            f.loc === "bn" ? "পরিমাণ" : "Amount",
                            f.loc === "bn" ? "বিলের আগে" : "Before",
                            f.loc === "bn" ? "বিলের পরে" : "After",
                        ], rows: bills.rows.map((r) => [
                            _jsx("span", { className: "tabular text-ink-600", children: f.fullDate(r.date) }),
                            _jsxs("span", { className: "font-semibold text-ink-800", children: [r.name, " ", r.mandatory ? (_jsx(Chip, { tone: "warn", children: f.loc === "bn" ? "বাধ্যতামূলক" : "mandatory" })) : (_jsx(Chip, { tone: "neutral", children: f.loc === "bn" ? "ঐচ্ছিক" : "optional" }))] }),
                            _jsx("span", { className: "text-ink-500", children: r.category }),
                            _jsx("span", { className: "tabular font-semibold text-ink-900", children: f.taka(r.amount) }),
                            _jsx("span", { className: "tabular", children: f.taka(r.balanceBefore) }),
                            _jsx("span", { className: cx("tabular font-bold", r.tight ? "text-amber-ink" : "text-ink-900"), children: f.taka(r.balanceAfter) }),
                        ]) })] }), _jsx("div", { className: "mt-5", children: _jsxs(Card, { children: [_jsx(CardHeader, { kicker: copy("evidence", lang), title: bills.evidence.headline, right: _jsxs(Chip, { tone: "neutral", children: [Math.round(bills.evidence.confidence * 100), "% ", copy("confidence", lang)] }) }), _jsx(EvidenceBody, { evidence: bills.evidence })] }) })] }));
}
