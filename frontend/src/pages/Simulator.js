import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo, useState } from "react";
import { Info, RotateCcw, Sparkles, TriangleAlert } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, PageHeader, Slider, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { CompareChart, Panel, VIZ } from "@/components/charts";
import { DEFAULT_SCENARIO, runSimulation, savingsLevers } from "@/engines/simulator";
export default function Simulator() {
    const bundle = useBundle();
    const f = useFmt();
    const { lang } = useCopilot();
    const [scenario, setScenario] = useState(DEFAULT_SCENARIO);
    const [goalId, setGoalId] = useState(bundle?.ctx.goals[0]?.goal_id ?? "");
    const result = useMemo(() => (bundle ? runSimulation(bundle.ctx, scenario, goalId) : null), [bundle, scenario, goalId]);
    if (!bundle || !result)
        return null;
    const { ctx, capacity } = bundle;
    const levers = savingsLevers(ctx, Math.max(0, scenario.monthlySavingChange));
    const dirty = scenario.monthlySavingChange !== 0 ||
        scenario.incomeChangePercent !== 0 ||
        scenario.expenseChange !== 0 ||
        scenario.unexpectedExpense !== 0;
    const riskTone = result.riskLevel === "low" ? "good" : result.riskLevel === "moderate" ? "warn" : result.riskLevel === "elevated" ? "warn" : "bad";
    return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("simulator", lang), subtitle: f.loc === "bn"
                    ? "একটি ধারণা বদলে দেখুন ১২ মাসে কী হতে পারে। কিছুই বাস্তবে পরিবর্তন হয় না — এটি শুধু তুলনার জন্য।"
                    : "Change one assumption and watch 12 months re-run. Nothing is applied anywhere — this only compares two versions of your own ledger.", actions: _jsxs("button", { type: "button", onClick: () => setScenario(DEFAULT_SCENARIO), disabled: !dirty, className: cx("inline-flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-[12px] font-semibold transition", dirty ? "text-ink-700 hover:border-ink-300" : "text-ink-300"), children: [_jsx(RotateCcw, { className: "h-3.5 w-3.5" }), copy("reset", lang)] }) }), _jsxs(Grid, { cols: 4, className: "mb-5", children: [_jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "শেষ ব্যালেন্সের পরিবর্তন" : "Closing balance change", value: `${result.balanceDelta >= 0 ? "+" : "−"}${f.taka(Math.abs(result.balanceDelta))}`, big: true, tone: result.balanceDelta >= 0 ? "good" : "bad", hint: `${f.loc === "bn" ? "১২ মাস পর" : "after 12 months"} · ${copy("baseline", lang)} ${f.taka(result.baseline.endingBalance)}` }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "লক্ষ্যের তারিখে স্থানচ্যুতি" : "Goal date shift", value: result.goalDateShiftMonths === null
                                ? "—"
                                : `${result.goalDateShiftMonths >= 0 ? "+" : "−"}${f.num(Math.abs(result.goalDateShiftMonths))} ${copy("months", lang)}`, big: true, tone: result.goalDateShiftMonths !== null && result.goalDateShiftMonths < 0 ? "good" : "neutral", hint: result.scenario.goalDate
                                ? `${f.loc === "bn" ? "নতুন তারিখ" : "new date"} ${f.month(result.scenario.goalDate)}`
                                : copy("noData", lang) }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "সর্বনিম্ন ব্যালেন্স" : "Minimum balance", value: f.taka(result.scenario.minBalance), tone: result.scenario.minBalance < 0 ? "bad" : "neutral", hint: `${copy("baseline", lang)} ${f.taka(result.baseline.minBalance)}` }) }), _jsx(Card, { children: _jsx(Stat, { label: f.loc === "bn" ? "ঝুঁকির স্তর" : "Risk level", value: result.riskLevel, big: true, tone: riskTone, hint: result.firstShortfallMonth
                                ? `${f.loc === "bn" ? "প্রথম ঘাটতি" : "first shortfall"} ${f.month(result.firstShortfallMonth)}`
                                : f.loc === "bn" ? "রিজার্ভ অক্ষত" : "buffer holds" }) })] }), _jsxs(Grid, { cols: 3, className: "mb-5", children: [_jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "নিয়ন্ত্রণ" : "Controls", title: f.loc === "bn" ? "কী বদলাচ্ছেন" : "What you are changing", subtitle: f.loc === "bn"
                                    ? `সঞ্চয়ের ক্ষমতা ${f.taka(capacity.capacity)} প্রতি মাসে — এর বেশি সাধারণত রিজার্ভ ভাঙে।`
                                    : `Your estimated capacity is ${f.taka(capacity.capacity)} per month. Pushing much beyond that usually eats the buffer.` }), _jsxs("div", { className: "space-y-5", children: [_jsx(Slider, { label: f.loc === "bn" ? "মাসে অতিরিক্ত সঞ্চয়" : "Extra saving per month", value: scenario.monthlySavingChange, min: -5000, max: 15000, step: 250, onChange: (v) => setScenario((s) => ({ ...s, monthlySavingChange: v })), display: `${scenario.monthlySavingChange >= 0 ? "+" : "−"}${f.taka(Math.abs(scenario.monthlySavingChange))}` }), _jsx(Slider, { label: f.loc === "bn" ? "আয়ের পরিবর্তন" : "Income change", value: scenario.incomeChangePercent, min: -40, max: 40, step: 1, onChange: (v) => setScenario((s) => ({ ...s, incomeChangePercent: v })), display: `${scenario.incomeChangePercent >= 0 ? "+" : "−"}${f.num(Math.abs(scenario.incomeChangePercent))}%` }), _jsx(Slider, { label: f.loc === "bn" ? "মাসিক ব্যয়ের পরিবর্তন" : "Monthly spending change", value: scenario.expenseChange, min: -8000, max: 8000, step: 100, onChange: (v) => setScenario((s) => ({ ...s, expenseChange: v })), display: `${scenario.expenseChange >= 0 ? "+" : "−"}${f.taka(Math.abs(scenario.expenseChange))}` }), _jsx(Slider, { label: f.loc === "bn" ? "একবারের অপ্রত্যাশিত ব্যয়" : "One-off unexpected expense", value: scenario.unexpectedExpense, min: 0, max: 40000, step: 500, onChange: (v) => setScenario((s) => ({ ...s, unexpectedExpense: v })), display: f.taka(scenario.unexpectedExpense) }), ctx.goals.length ? (_jsxs("div", { children: [_jsx("div", { className: "mb-1.5 text-[12px] font-semibold text-ink-700", children: f.loc === "bn" ? "কোন লক্ষ্য" : "Goal to track" }), _jsx("div", { className: "flex flex-wrap gap-1.5", children: ctx.goals.map((g) => (_jsx("button", { type: "button", onClick: () => setGoalId(g.goal_id), className: cx("rounded-full border px-2.5 py-1 text-[11.5px] font-semibold transition", goalId === g.goal_id
                                                        ? "border-brand-300 bg-brand-50 text-brand-700"
                                                        : "border-ink-200 text-ink-500 hover:border-ink-300"), children: g.goal_name }, g.goal_id))) })] })) : null] }), scenario.monthlySavingChange > 0 ? (_jsxs("div", { className: "mt-5 rounded-xl border border-ink-200 bg-ink-50 p-3", children: [_jsxs("div", { className: "mb-1 flex items-center gap-1.5 text-[12px] font-bold text-ink-800", children: [_jsx(Sparkles, { className: "h-3.5 w-3.5" }), f.loc === "bn" ? "এই পরিমাণটি কতটা বাস্তবসম্মত" : "Is that amount realistic?"] }), _jsx("p", { className: "text-[12px] leading-relaxed text-ink-600", children: f.loc === "bn"
                                            ? `${f.taka(scenario.monthlySavingChange)} মাসে জমাতে হলে আপনার ব্যয়ের ${f.percent(levers.asShareOfSpend, 1)} কমাতে হবে। সমন্বয়যোগ্য পুলে প্রায় ${f.taka(levers.discretionaryPool)} আছে, তাই এটি সাধারণত ${f.num(levers.monthsToFund, 1)} মাসের উপরে টানবে।`
                                            : `Saving ${f.taka(scenario.monthlySavingChange)} a month means trimming ${f.percent(levers.asShareOfSpend, 1)} of spending. Your estimated discretionary pool is ${f.taka(levers.discretionaryPool)}, so this typically takes about ${f.num(levers.monthsToFund, 1)} month(s) of sustained change rather than one decision.` })] })) : null] }), _jsxs("div", { className: "space-y-4 sm:col-span-2", children: [_jsx(Panel, { title: f.loc === "bn" ? "বর্তমান বনাম পরিস্থিতি" : "Baseline vs scenario", subtitle: f.loc === "bn"
                                    ? `মাসে জমা ${f.taka(result.scenario.monthlySaving)} বনাম ${f.taka(result.baseline.monthlySaving)}`
                                    : `${f.taka(result.scenario.monthlySaving)}/month saved vs ${f.taka(result.baseline.monthlySaving)} baseline`, height: 280, right: _jsx(EvidenceButton, { evidence: result.evidence }), children: _jsx(CompareChart, { data: result.series.map((p) => ({
                                        date: p.date,
                                        baseline: p.baseline,
                                        scenario: p.scenario,
                                    })), series: [
                                        { key: "baseline", label: copy("baseline", lang), color: VIZ[3] },
                                        { key: "scenario", label: copy("scenario", lang), color: VIZ[0] },
                                    ], lang: f.tlang, reference: capacity.buffer, referenceLabel: f.loc === "bn" ? "রিজার্ভ" : "buffer", height: 280 }) }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "ফলাফল" : "Outcome", title: f.loc === "bn" ? "এই পরিবর্তনের ফল" : "What this change produces" }), _jsx("ul", { className: "space-y-2", children: result.explanation.map((e, i) => (_jsxs("li", { className: "flex items-start gap-2 text-[12.5px] leading-relaxed text-ink-700", children: [_jsx("span", { className: "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" }), f.bi(e.en, e.bn)] }, i))) }), _jsx("div", { className: "mt-4", children: _jsx(Table, { align: "right", head: [
                                                f.loc === "bn" ? "মাপ" : "Measure",
                                                copy("baseline", lang),
                                                copy("scenario", lang),
                                                f.loc === "bn" ? "পার্থক্য" : "Difference",
                                            ], rows: [
                                                [
                                                    f.loc === "bn" ? "মাসে জমা" : "Monthly saving",
                                                    f.taka(result.baseline.monthlySaving),
                                                    f.taka(result.scenario.monthlySaving),
                                                    f.taka(result.scenario.monthlySaving - result.baseline.monthlySaving),
                                                ],
                                                [
                                                    f.loc === "bn" ? "১২ মাসে মোট জমা" : "Total saved over 12m",
                                                    f.taka(result.baseline.totalSaved),
                                                    f.taka(result.scenario.totalSaved),
                                                    f.taka(result.scenario.totalSaved - result.baseline.totalSaved),
                                                ],
                                                [
                                                    f.loc === "bn" ? "শেষ ব্যালেন্স" : "Closing balance",
                                                    f.taka(result.baseline.endingBalance),
                                                    f.taka(result.scenario.endingBalance),
                                                    _jsx("span", { className: cx("font-semibold", result.balanceDelta >= 0 ? "text-mint-700" : "text-brand-700"), children: f.taka(result.balanceDelta) }),
                                                ],
                                                [
                                                    f.loc === "bn" ? "সর্বনিম্ন ব্যালেন্স" : "Minimum balance",
                                                    f.taka(result.baseline.minBalance),
                                                    f.taka(result.scenario.minBalance),
                                                    f.taka(result.scenario.minBalance - result.baseline.minBalance),
                                                ],
                                                [
                                                    f.loc === "bn" ? "লক্ষ্যের ঘাটতি" : "Goal shortfall",
                                                    f.taka(result.baseline.shortfall),
                                                    f.taka(result.scenario.shortfall),
                                                    f.taka(result.scenario.shortfall - result.baseline.shortfall),
                                                ],
                                            ] }) })] })] })] }), result.riskLevel === "high" || result.riskLevel === "elevated" ? (_jsx("div", { className: "mb-5", children: _jsx(Banner, { tone: "warn", title: f.loc === "bn" ? "এই পরিস্থিতিতে ব্যালেন্স নেতেবাচক হয়" : "This scenario runs the balance negative", icon: _jsx(TriangleAlert, { className: "h-4 w-4" }), children: _jsx("p", { children: f.loc === "bn"
                            ? `সর্বনিম্ন প্রকৃতিপত ব্যালেন্স ${f.taka(Math.abs(result.scenario.minBalance))}। এখানে সিমুলেটর কিছু পরিবর্তন করেনি — এটি শুধু দেখায় যে বর্তমান সেটিংসে এই সম্পর্তাতি টেকা কঠিন।`
                            : `The minimum projected balance is ${f.taka(Math.abs(result.scenario.minBalance))}. The simulator changed nothing — it only shows that these settings make this particular shock hard to absorb.` }) }) })) : null, _jsxs(Card, { children: [_jsx(CardHeader, { kicker: copy("evidence", lang), title: result.evidence.headline, right: _jsxs(Chip, { tone: "neutral", children: [Math.round(result.evidence.confidence * 100), "% ", copy("confidence", lang)] }) }), _jsx(EvidenceBody, { evidence: result.evidence }), _jsxs("p", { className: "mt-4 flex items-start gap-2 text-[11.5px] leading-relaxed text-ink-500", children: [_jsx(Info, { className: "mt-0.5 h-3.5 w-3.5 shrink-0" }), f.loc === "bn"
                                ? "দুটি লাইন একই মডেলে চলেছে, তাই পার্থক্য শুধু আপনার দেওয়া অনুমান থেকেই এসেছে। এটি কোনো পরামর্শ নয় — সিদ্ধান্ত আপনার।"
                                : "Both lines run through the identical model, so every difference traces back to the inputs you changed. This is not a recommendation — the decision stays yours."] })] })] }));
}
