import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Flag, Layers, Target } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Segmented, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { CompareChart, Panel, VIZ } from "@/components/charts";
import { simulateGoalTimeline } from "@/engines/goals";
const VERDICT = {
    on_track: { en: "On track", bn: "লক্ষ্যমুখী", tone: "good" },
    tight: { en: "Tight but doable", bn: "কঠিন হলেও সম্ভব", tone: "warn" },
    at_risk: { en: "At risk", bn: "ঝুঁকিতে", tone: "warn" },
    infeasible: { en: "Not feasible at this rate", bn: "এই গতিতে সম্ভব নয়", tone: "bad" },
};
export default function Goals() {
    const bundle = useBundle();
    const f = useFmt();
    const { lang } = useCopilot();
    const [openId, setOpenId] = useState(bundle?.goals.goals[0]?.goal_id ?? "");
    const [plan, setPlan] = useState("priority");
    if (!bundle)
        return null;
    const { ctx, goals, feasibility, allocations, capacity } = bundle;
    const active = feasibility[openId] ?? goals.feasibility[0];
    const allocation = allocations.find((a) => a.key === plan) ?? allocations[0];
    if (!active) {
        return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("goals", lang) }), _jsx(Banner, { tone: "info", title: copy("noData", lang) })] }));
    }
    const timeline = simulateGoalTimeline(active.goal, active.scenarios[1].monthlyContribution, ctx.asOf);
    const reached = timeline.findIndex((p) => p.balance >= active.goal.target_amount);
    return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("goals", lang), subtitle: f.loc === "bn"
                    ? "প্রতিটি লক্ষ্যের জন্য সম্ভাব্যতা আপনার নিজের মাসিক সঞ্চয়ের ইতিহাস থেকে হিসাব করা — অনুমান নয়।"
                    : "Feasibility is computed from your own monthly-surplus distribution, not a generic savings rule. Three scenarios come from the 25th, 50th and 75th percentile of that history." }), _jsxs(Grid, { cols: 4, className: "mb-5", children: [_jsxs(Card, { children: [_jsx(Stat, { label: f.loc === "bn" ? "লক্ষ্যের অগ্রগতি" : "Portfolio progress", value: f.percent(goals.progress, 0), big: true, tone: goals.progress > 0.3 ? "good" : "warn", hint: `${f.taka(goals.totalSaved)} ${f.loc === "bn" ? "জমেছে" : "saved"} / ${f.taka(goals.totalTarget)}` }), _jsx("div", { className: "mt-3", children: _jsx(Meter, { value: goals.progress * 100, tone: goals.progress > 0.3 ? "good" : "warn" }) })] }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "মাসিক সঞ্চয়ের সক্ষমতা" : "Monthly capacity", value: f.taka(capacity.capacity), big: true, tone: capacity.capacity > 0 ? "good" : "bad", hint: `${f.loc === "bn" ? "আয়" : "median income"} ${f.taka(capacity.sustainableIncome)} − ${f.loc === "bn" ? "ব্যয়" : "planned spend"} ${f.taka(capacity.plannedSpend)}` }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "সঞ্চয়ের উচ্চতা" : "Surplus volatility", value: f.taka(capacity.surplusStd), hint: `${f.loc === "bn" ? "গড়" : "mean"} ${f.taka(capacity.surplusMean)} ± ${f.taka(capacity.surplusStd)}` }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "সক্রিয় লক্ষ্য" : "Active goals", value: f.num(goals.goals.length), hint: `${goals.feasibility.filter((x) => x.verdict === "on_track").length} ${f.loc === "bn" ? "টি লক্ষ্যমুখী" : "on track"} · ${goals.feasibility.filter((x) => x.verdict === "infeasible").length} ${f.loc === "bn" ? "টি অসম্ভব" : "infeasible"}` }) })] }), _jsxs(Grid, { cols: 3, className: "mb-5", children: [_jsxs(Card, { className: "sm:col-span-1", children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "আপনার লক্ষ্য" : "Your goals", title: f.loc === "bn" ? "একটি বেছে নিন" : "Pick one to inspect" }), _jsx("div", { className: "space-y-2", children: goals.feasibility.map((g) => (_jsxs("button", { type: "button", onClick: () => setOpenId(g.goal.goal_id), className: cx("block w-full rounded-xl border px-3.5 py-3 text-left transition", g.goal.goal_id === active.goal.goal_id
                                        ? "border-brand-300 bg-brand-50/50"
                                        : "border-ink-200 bg-white hover:border-ink-300"), children: [_jsxs("div", { className: "flex items-start justify-between gap-2", children: [_jsx("span", { className: "text-[13px] font-bold text-ink-900", children: f.bi(g.goal.goal_name, g.goal.goal_name) }), _jsx(Chip, { tone: VERDICT[g.verdict].tone, children: f.bi(VERDICT[g.verdict].en, VERDICT[g.verdict].bn) })] }), _jsx("div", { className: "mt-1.5", children: _jsx(Meter, { value: (g.goal.current_amount / g.goal.target_amount) * 100, tone: g.verdict === "infeasible" ? "bad" : "brand" }) }), _jsxs("div", { className: "tabular mt-1 flex items-center justify-between text-[11.5px] text-ink-500", children: [_jsxs("span", { children: [f.taka(g.goal.current_amount), " / ", f.taka(g.goal.target_amount)] }), _jsxs("span", { children: [f.percent(g.probability, 0), " ", f.loc === "bn" ? "সম্ভাবনা" : "likely"] })] })] }, g.goal.goal_id))) })] }), _jsxs("div", { className: "space-y-4 sm:col-span-2", children: [_jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "নির্বাচিত লক্ষ্য" : "Selected goal", title: active.goal.goal_name, subtitle: f.loc === "bn"
                                            ? `লক্ষ্যের তারিখ ${f.fullDate(active.goal.target_date)} · বাকি ${f.num(active.monthsLeft)} মাস`
                                            : `Target date ${f.fullDate(active.goal.target_date)} · ${f.num(active.monthsLeft)} months remain`, right: _jsx(EvidenceButton, { evidence: active.evidence }) }), _jsxs(Grid, { cols: 4, children: [_jsx(Stat, { label: f.loc === "bn" ? "লক্ষ্য" : "Target", value: f.taka(active.goal.target_amount) }), _jsx(Stat, { label: f.loc === "bn" ? "জমেছে" : "Saved", value: f.taka(active.goal.current_amount), tone: "good" }), _jsx(Stat, { label: f.loc === "bn" ? "প্রয়োজনীয়/মাস" : "Required/month", value: f.taka(active.requiredMonthly), tone: active.requiredMonthly > capacity.capacity ? "bad" : "good" }), _jsx(Stat, { label: f.loc === "bn" ? "সম্ভাবনা" : "Probability", value: f.percent(active.probability, 0), big: true, tone: active.verdict === "on_track" ? "good" : active.verdict === "infeasible" ? "bad" : "warn", hint: f.bi(VERDICT[active.verdict].en, VERDICT[active.verdict].bn) })] }), active.shortfall > 0 ? (_jsx("div", { className: "mt-4", children: _jsx(Banner, { tone: "warn", title: `${f.taka(active.shortfall)} ${f.loc === "bn" ? "ঘাটতি" : "shortfall"} at the current rate`, icon: _jsx(AlertTriangle, { className: "h-4 w-4" }), children: _jsx("p", { children: f.loc === "bn"
                                                    ? `বর্তমান সঞ্চয়ের গতিতে লক্ষ্যের তারিখে প্রায় ${f.taka(active.shortfall)} ঘাটতি থাকবে। নিচের পরিস্থিতিগুলো থেকে দেখুন সময়সীমা পূরণ করা কতটা সম্ভব।`
                                                    : `At ৳${f.num(active.estimatedCapacity)}/month the goal lands about ${f.taka(active.shortfall)} short. The scenarios below show what it would take instead.` }) }) })) : null, _jsxs("div", { className: "mt-4", children: [_jsx("div", { className: "mb-2 text-[11px] font-semibold tracking-wide text-ink-400 uppercase", children: f.loc === "bn" ? "তিনটি পরিস্থিতি" : "Three scenarios from your own distribution" }), _jsx(Table, { head: [
                                                    f.loc === "bn" ? "পরিস্থিতি" : "Scenario",
                                                    f.loc === "bn" ? "মাসে জমা" : "Monthly",
                                                    f.loc === "bn" ? "লক্ষ্যে পৌঁছাবে" : "Reaches by",
                                                    f.loc === "bn" ? "সম্ভাবনা" : "Probability",
                                                    f.loc === "bn" ? "ঘাটতি" : "Shortfall",
                                                    f.loc === "bn" ? "সর্বনিম্ন ব্যালেন্স" : "Min balance",
                                                ], rows: active.scenarios.map((s) => [
                                                    _jsx("span", { className: "font-semibold text-ink-800", children: f.bi(s.label, s.labelBn) }),
                                                    f.taka(s.monthlyContribution),
                                                    s.targetDate ? f.month(s.targetDate) : "—",
                                                    _jsx("span", { className: cx("tabular font-bold", s.probability >= 0.75 ? "text-mint-700" : s.probability >= 0.4 ? "text-amber-ink" : "text-brand-700"), children: f.percent(s.probability, 0) }),
                                                    s.shortfall > 0 ? _jsx("span", { className: "text-brand-700", children: f.taka(s.shortfall) }) : _jsx("span", { className: "text-mint-700", children: "\u2014" }),
                                                    _jsx("span", { className: cx(s.bufferBreached && "font-semibold text-brand-700"), children: f.taka(s.minBalance) }),
                                                ]) }), _jsx("ul", { className: "mt-3 space-y-2", children: active.scenarios.map((s) => (_jsxs("li", { className: "rounded-lg border border-ink-200 bg-ink-50/60 px-3 py-2 text-[12px] leading-relaxed text-ink-600", children: [_jsxs("span", { className: "font-semibold text-ink-800", children: [f.bi(s.label, s.labelBn), ":"] }), " ", f.bi(s.tradeoff, s.tradeoffBn)] }, s.key))) })] })] }), _jsxs(Panel, { title: f.loc === "bn" ? "সুষম পরিস্থিতিতে অগ্রগতি" : "Progress under the balanced scenario", subtitle: f.loc === "bn"
                                    ? `মাসে ${f.taka(active.scenarios[1].monthlyContribution)} জমালে`
                                    : `${f.taka(active.scenarios[1].monthlyContribution)} per month`, height: 220, children: [_jsx(CompareChart, { data: timeline.map((p) => ({
                                            date: p.date,
                                            projected: p.balance,
                                            target: active.goal.target_amount,
                                            buffer: capacity.buffer,
                                        })), series: [
                                            { key: "projected", label: f.loc === "bn" ? "লক্ষ্যের টাকা" : "goal pot", color: VIZ[0] },
                                            { key: "target", label: f.loc === "bn" ? "লক্ষ্যের পরিমাণ" : "target", color: VIZ[2] },
                                        ], lang: f.tlang, reference: capacity.buffer, referenceLabel: f.loc === "bn" ? "রিজার্ভ" : "buffer", height: 220 }), _jsx("p", { className: "mt-2 text-[12px] text-ink-500", children: reached >= 0
                                            ? f.loc === "bn"
                                                ? `এই গতিতে লক্ষ্য পূরণ হবে ${f.month(timeline[reached].date)} মাসে।`
                                                : `At this rate the goal completes in ${f.month(timeline[reached].date)}.`
                                            : f.loc === "bn"
                                                ? `এই গতিতে লক্ষ্যের তারিখের মধ্যে পৌঁছানো যাচ্ছে না।`
                                                : `At this rate the target date is not reachable.` })] })] })] }), allocations.length ? (_jsxs(Card, { className: "mb-5", children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "একাধিক লক্ষ্য" : "Multiple goals", title: f.loc === "bn" ? "কোনো লক্ষ্যকে কত অগ্রাধিকার" : "How to split capacity across goals", subtitle: f.loc === "bn"
                            ? "তিনটি বিন্যাসই একই মোট ক্ষমতা ব্যবহার করে — পার্থক্য শুধু ভাগ বণ্টনে।"
                            : "All three plans spend the same total capacity; only the split changes. The optimiser ranks them by total shortfall.", right: _jsx(Segmented, { value: plan, onChange: setPlan, options: allocations.map((a) => ({ value: a.key, label: f.bi(a.name, a.nameBn) })) }) }), _jsx(Table, { align: "right", head: [
                            f.loc === "bn" ? "লক্ষ্য" : "Goal",
                            f.loc === "bn" ? "ভাগ" : "Share",
                            f.loc === "bn" ? "মাসে জমা" : "Monthly",
                            f.loc === "bn" ? "লক্ষ্যে পৌঁছাবে" : "Reaches by",
                            f.loc === "bn" ? "ঘাটতি" : "Shortfall",
                        ], rows: allocation.allocations.map((a) => [
                            _jsx("span", { className: "font-semibold text-ink-800", children: a.goal_name }),
                            f.percent(a.share, 0),
                            f.taka(a.monthly),
                            a.targetDate ? f.month(a.targetDate) : "—",
                            a.shortfall > 0 ? _jsx("span", { className: "text-brand-700", children: f.taka(a.shortfall) }) : _jsx("span", { className: "text-mint-700", children: "\u2014" }),
                        ]) }), _jsxs("p", { className: "mt-3 text-[12px] leading-relaxed text-ink-500", children: [f.bi(allocation.description, allocation.descriptionBn), " ", allocation.totalShortfall > 0
                                ? f.loc === "bn"
                                    ? `এই বিন্যাসে মোট ঘাটতি ${f.taka(allocation.totalShortfall)}।`
                                    : `This plan still leaves ${f.taka(allocation.totalShortfall)} of combined shortfall.`
                                : f.loc === "bn"
                                    ? "এই বিন্যাসে কোনো ঘাটতি নেই।"
                                    : "This plan leaves no combined shortfall."] })] })) : null, _jsxs(Card, { children: [_jsx(CardHeader, { kicker: copy("evidence", lang), title: active.evidence.headline, right: _jsxs(Chip, { tone: "neutral", children: [Math.round(active.evidence.confidence * 100), "% ", copy("confidence", lang)] }) }), _jsx(EvidenceBody, { evidence: active.evidence }), _jsxs("div", { className: "mt-4 grid gap-3 sm:grid-cols-3", children: [_jsx(Stat, { label: f.loc === "bn" ? "প্রয়োজনীয় / ক্ষমতা" : "Required vs capacity", value: `${f.taka(active.requiredMonthly)} / ${f.taka(active.estimatedCapacity)}`, hint: active.estimatedCapacity > 0
                                    ? `${f.num(active.requiredMonthly / active.estimatedCapacity, 2)}× ${f.loc === "bn" ? "বর্তমান গতি" : "current pace"}`
                                    : f.loc === "bn" ? "ক্ষমতা নেই" : "no capacity" }), _jsx(Stat, { label: f.loc === "bn" ? "অগ্রাধিকার" : "Priority", value: _jsx(Chip, { tone: active.goal.priority === "high" ? "bad" : active.goal.priority === "medium" ? "warn" : "neutral", children: active.goal.priority }), hint: `${f.loc === "bn" ? "তৈরি" : "created"} ${f.fullDate(active.goal.created_date)}` }), _jsx(Stat, { label: f.loc === "bn" ? "লক্ষ্যের ধরন" : "Verdict", value: f.bi(VERDICT[active.verdict].en, VERDICT[active.verdict].bn), tone: VERDICT[active.verdict].tone === "neutral" ? "neutral" : VERDICT[active.verdict].tone, hint: active.verdict === "on_track" ? (_jsxs("span", { className: "inline-flex items-center gap-1 text-mint-700", children: [_jsx(CheckCircle2, { className: "h-3 w-3" }), " ", f.loc === "bn" ? "সময়সীমায় পৌঁছানো সম্ভব" : "reachable on time"] })) : active.verdict === "infeasible" ? (_jsxs("span", { className: "inline-flex items-center gap-1 text-brand-700", children: [_jsx(Flag, { className: "h-3 w-3" }), " ", f.loc === "bn" ? "তারিখ বাড়াতে হবে" : "deadline needs to move"] })) : (_jsxs("span", { className: "inline-flex items-center gap-1 text-amber-ink", children: [_jsx(Layers, { className: "h-3 w-3" }), " ", f.loc === "bn" ? "ভারসাম্য দরকার" : "trade-offs needed"] })) })] }), _jsxs("p", { className: "mt-4 flex items-start gap-2 text-[11.5px] leading-relaxed text-ink-500", children: [_jsx(Target, { className: "mt-0.5 h-3.5 w-3.5 shrink-0" }), f.loc === "bn"
                                ? "সম্ভাব্যতা আপনার মাসিক অতিশেষের স্বাভাবিক বণ্টনের ধারণায় হিসাব করা — কোনো ঋণ বা বিনিয়োগের প্রতিশ্রুতি নয়।"
                                : "The probability assumes your monthly surplus stays normally distributed around its own history. It is a planning figure, not a promise."] })] })] }));
}
