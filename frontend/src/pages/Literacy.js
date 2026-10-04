import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { BookOpen, CheckCircle2, CircleHelp, Clock, Lightbulb, XCircle } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, cx } from "@/components/ui";
import { EvidenceButton } from "@/components/Evidence";
import { allTopics } from "@/engines/literacy";
export default function Literacy() {
    const bundle = useBundle();
    const f = useFmt();
    const { lang } = useCopilot();
    const [open, setOpen] = useState(null);
    const [picked, setPicked] = useState({});
    if (!bundle)
        return null;
    const { literacy } = bundle;
    const everything = allTopics();
    const recIds = new Set(literacy.map((r) => r.topic.id));
    const rest = everything.filter((t) => !recIds.has(t.id));
    return (_jsxs("div", { children: [_jsx(PageHeader, { title: copy("literacy", lang), subtitle: f.loc === "bn"
                    ? "কোনো সাধারণ টিপস নয় — প্রতিটি পাঠ আপনার লেজারে মাপা একটি সংকেত দিয়ে চালু হয়েছে এবং ব্যাখ্যায় আপনার নিজের সংখ্যা ব্যবহার করে।"
                    : "Not a generic tip list. Every lesson below was triggered by a signal measured in your own ledger and explains itself using your own numbers.", actions: _jsxs(Chip, { tone: "brand", children: [_jsx(BookOpen, { className: "h-3 w-3" }), f.num(literacy.length), " ", f.loc === "bn" ? "পাঠ" : "lessons"] }) }), _jsx("div", { className: "mb-5", children: _jsx(Banner, { tone: "info", title: f.loc === "bn" ? "কীভাবে পাঠ বাছাই হয়" : "How these were chosen", icon: _jsx(Lightbulb, { className: "h-4 w-4" }), children: _jsx("p", { children: f.loc === "bn"
                            ? "বয়স, লিঙ্গ, পেশা বা আয়ের পরিমাণ দেখে কোনো পাঠ বাছাই হয়নি। শুধু আপনার আচরণ থেকে পাওয়া সংকেত — যেমন মাসের শেষে খরচ বেড়ে যাওয়া — পাঠটি চালু করেছে।"
                            : "Nothing here was selected by age, gender, occupation or income level. Only behaviour-derived signals — such as spending rising late in the month — turn a lesson on." }) }) }), literacy.length ? (_jsxs(_Fragment, { children: [_jsx("p", { className: "mb-3 text-[11px] font-bold tracking-wide text-ink-400 uppercase", children: f.loc === "bn" ? "আপনার জন্য প্রাসঙ্গিক" : "Recommended for you" }), _jsx("div", { className: "mb-5 space-y-3", children: literacy.map((rec) => {
                            const isOpen = open === rec.topic.id;
                            const choice = picked[rec.topic.id];
                            return (_jsxs(Card, { children: [_jsxs("div", { className: "flex flex-wrap items-start justify-between gap-3", children: [_jsxs("div", { className: "min-w-0", children: [_jsxs("div", { className: "flex flex-wrap items-center gap-2", children: [_jsx("h2", { className: "text-[16px] font-bold text-ink-900", children: f.bi(rec.topic.title, rec.topic.titleBn) }), _jsxs(Chip, { tone: "brand", children: [_jsx(Clock, { className: "h-3 w-3" }), f.num(rec.topic.minutes, 0), " ", f.loc === "bn" ? "মিনিট" : "min"] }), choice !== undefined ? (_jsx(Chip, { tone: choice === rec.topic.quiz.answer ? "good" : "warn", children: choice === rec.topic.quiz.answer
                                                                    ? f.loc === "bn" ? "সঠিক" : "correct"
                                                                    : f.loc === "bn" ? "আবার দেখুন" : "revise" })) : null] }), _jsx("p", { className: "mt-1.5 max-w-3xl text-[13px] leading-relaxed text-ink-600", children: f.bi(rec.topic.hook, rec.topic.hookBn) }), _jsxs("p", { className: "mt-2 inline-flex items-center gap-2 rounded-lg bg-ink-50 px-2.5 py-1.5 text-[11.5px] text-ink-600", children: [_jsx("span", { className: "font-bold text-ink-800", children: f.loc === "bn" ? "সংকেত:" : "Signal:" }), rec.signal] })] }), _jsxs("div", { className: "flex shrink-0 items-center gap-2", children: [_jsx(EvidenceButton, { evidence: rec.evidence }), _jsx("button", { type: "button", onClick: () => setOpen(isOpen ? null : rec.topic.id), className: "rounded-lg bg-brand-500 px-3.5 py-2 text-[12.5px] font-bold text-white transition hover:bg-brand-600", children: isOpen
                                                            ? f.loc === "bn" ? "বন্ধ করুন" : "Close"
                                                            : f.loc === "bn" ? "পড়ুন" : "Read lesson" })] })] }), _jsxs("div", { className: "mt-3", children: [_jsxs("div", { className: "mb-1 flex items-baseline justify-between gap-2 text-[11px] font-semibold text-ink-500", children: [_jsx("span", { children: f.loc === "bn" ? "সংকেতের মাত্রা" : "Signal strength" }), _jsx("span", { className: "tabular", children: f.percent(rec.strength, 0) })] }), _jsx(Meter, { value: rec.strength * 100, tone: rec.strength > 0.6 ? "warn" : "brand" })] }), isOpen ? (_jsxs("div", { className: "mt-4 space-y-3 border-t border-ink-100 pt-4", children: [rec.topic.sections.map((s) => (_jsxs("div", { className: "rounded-xl border border-ink-200 bg-ink-50/40 px-4 py-3", children: [_jsx("h3", { className: "text-[12.5px] font-bold text-ink-900", children: f.bi(s.heading, s.headingBn) }), _jsx("p", { className: "mt-1.5 text-[12.5px] leading-relaxed text-ink-600", children: f.bi(s.body, s.bodyBn) })] }, s.heading))), _jsxs("div", { className: "rounded-xl border border-brand-100 bg-brand-50/40 px-4 py-3.5", children: [_jsxs("div", { className: "mb-2.5 flex items-center gap-2 text-[12.5px] font-bold text-brand-800", children: [_jsx(CircleHelp, { className: "h-4 w-4" }), f.bi(rec.topic.quiz.question, rec.topic.quiz.questionBn)] }), _jsx("div", { className: "space-y-1.5", children: rec.topic.quiz.options.map((o, i) => {
                                                            const chosen = choice === i;
                                                            const isAnswer = i === rec.topic.quiz.answer;
                                                            const show = choice !== undefined;
                                                            return (_jsxs("button", { type: "button", onClick: () => setPicked((p) => ({ ...p, [rec.topic.id]: i })), className: cx("flex w-full items-start gap-2.5 rounded-lg border px-3 py-2 text-left text-[12.5px] leading-relaxed transition", !show
                                                                    ? "border-ink-200 bg-white text-ink-700 hover:border-brand-300"
                                                                    : isAnswer
                                                                        ? "border-mint-200 bg-mint-50 text-mint-700"
                                                                        : chosen
                                                                            ? "border-brand-200 bg-brand-50 text-brand-800"
                                                                            : "border-ink-100 bg-white text-ink-400"), children: [show && isAnswer ? (_jsx(CheckCircle2, { className: "mt-0.5 h-4 w-4 shrink-0" })) : show && chosen ? (_jsx(XCircle, { className: "mt-0.5 h-4 w-4 shrink-0" })) : (_jsx("span", { className: "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" })), _jsx("span", { children: f.bi(o.en, o.bn) })] }, i));
                                                        }) }), choice !== undefined ? (_jsx("p", { className: "mt-2.5 text-[12px] leading-relaxed text-ink-600", children: f.bi(rec.topic.quiz.explain, rec.topic.quiz.explainBn) })) : null] })] })) : null] }, rec.topic.id));
                        }) })] })) : (_jsx("div", { className: "mb-5", children: _jsx(Banner, { tone: "good", title: f.loc === "bn" ? "এখন কোনো পাঠ দরকার নেই" : "Nothing urgent to teach right now", children: _jsx("p", { children: f.loc === "bn"
                            ? "আপনার লেজারে এখন কোনো ঝুঁকির সংকেত নেই। সব পাঠ নিষ্ক্রিয় — আপনি চাইলে নিচে থেকে যেকোনো সময় পড়তে পারেন।"
                            : "Your ledger shows no warning signals at the moment. Every lesson is still available below if you want to read one." }) }) })), _jsxs(Grid, { cols: 3, className: "mb-5", children: [_jsxs("div", { className: "col-span-2", children: [_jsx("p", { className: "mb-3 text-[11px] font-bold tracking-wide text-ink-400 uppercase", children: f.loc === "bn" ? "সব পাঠ" : "All lessons" }), _jsx("div", { className: "grid gap-3 sm:grid-cols-2", children: rest.map((topic) => (_jsxs(Card, { className: "opacity-80", children: [_jsxs("div", { className: "flex items-start justify-between gap-3", children: [_jsxs("div", { className: "min-w-0", children: [_jsx("h3", { className: "text-[13.5px] font-bold text-ink-900", children: f.bi(topic.title, topic.titleBn) }), _jsx("p", { className: "mt-1 text-[11.5px] leading-relaxed text-ink-500", children: f.bi(topic.hook, topic.hookBn) })] }), _jsxs(Chip, { tone: "neutral", children: [f.num(topic.minutes, 0), "\u2032"] })] }), _jsxs("p", { className: "mt-3 border-t border-ink-100 pt-2.5 text-[11px] leading-relaxed text-ink-400", children: [_jsx("span", { className: "font-bold text-ink-500", children: f.loc === "bn" ? "চালু হবে যখন:" : "Triggers when:" }), " ", f.bi(topic.triggerLabel, topic.triggerLabelBn)] })] }, topic.id))) })] }), _jsxs(Card, { children: [_jsx(CardHeader, { kicker: f.loc === "bn" ? "যা লক্ষ্য রাখা হয়নি" : "Not by design", title: f.loc === "bn" ? "শিক্ষার নির্বাচনের ভিত্তি" : "How selection works" }), _jsxs("ul", { className: "space-y-2 text-[11.5px] leading-relaxed text-ink-600", children: [_jsxs("li", { className: "flex items-start gap-2", children: [_jsx("span", { className: "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-mint-500" }), f.loc === "bn"
                                                ? "প্রতিটি পাঠ একটি মাপা সংকেতের উপর ভিত্তি করে — অনুমান বা বিভাগের নাম নয়।"
                                                : "Each lesson is anchored to one measured signal, never to a guess or a category name."] }), _jsxs("li", { className: "flex items-start gap-2", children: [_jsx("span", { className: "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-mint-500" }), f.loc === "bn"
                                                ? "ব্যাখ্যায় আপনার লেজারের সংখ্যা বসানো হয়, সাধারণ উদাহরণ নয়।"
                                                : "Explanations quote your own figures rather than a textbook example."] }), _jsxs("li", { className: "flex items-start gap-2", children: [_jsx("span", { className: "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-mint-500" }), f.loc === "bn"
                                                ? "প্রতিটি পাঠে একটি যাচাই-প্রশ্ন আছে, তাই আপনি নিজে বুঝেছেন কি না তা মাপা যায়।"
                                                : "Every lesson ends in one check question, so comprehension is measured rather than assumed."] }), _jsxs("li", { className: "flex items-start gap-2", children: [_jsx("span", { className: "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" }), f.loc === "bn"
                                                ? "কোনো পাঠ কোনো সুবিধা বা কেনাকাটার প্রস্তাব দেয় না।"
                                                : "No lesson promotes a product or a purchase."] })] }), _jsx("p", { className: "mt-4 text-[11px] leading-relaxed text-ink-400", children: f.loc === "bn"
                                    ? `${f.num(literacy.length)} টি পাঠ সক্রিয়, ${f.num(rest.length)} টি নিষ্ক্রিয়।`
                                    : `${literacy.length} active, ${rest.length} dormant.` })] })] })] }));
}
