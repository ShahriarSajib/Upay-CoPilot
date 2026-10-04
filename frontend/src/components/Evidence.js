import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { ChevronDown, Database, FlaskConical, ShieldCheck } from "lucide-react";
import { taka, percent } from "@/lib/format";
import { Chip, cx } from "./ui";
import { useCopilot } from "@/data/store";
/* ------------------------------------------------------------------ *
 * Evidence is a first-class UI object, not a footnote.
 *
 * Every number in this product is produced by an engine that returns an
 * Evidence record: the metrics it used, the reasons it weighted them, the
 * assumptions it made and the source tables it read. The components below
 * render that record so a customer can always get from "what should I do?"
 * down to "which rows produced that?".
 * ------------------------------------------------------------------ */
function formatValue(value, unit, lang = "en") {
    if (typeof value === "string")
        return value;
    switch (unit) {
        case "bdt":
            return taka(value, { lang });
        case "percent":
            return percent(value, lang, 1);
        case "ratio":
            return value.toFixed(2);
        default:
            return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
    }
}
export function ConfidenceDot({ value }) {
    const tone = value >= 0.7 ? "bg-mint-500" : value >= 0.5 ? "bg-amber-500" : "bg-brand-500";
    const label = value >= 0.7 ? "high" : value >= 0.5 ? "moderate" : "low";
    return (_jsxs("span", { className: "inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink-500", children: [_jsx("span", { className: cx("h-1.5 w-1.5 rounded-full", tone) }), label, " \u00B7 ", (value * 100).toFixed(0), "%"] }));
}
export function EvidenceButton({ evidence, className }) {
    const [open, setOpen] = useState(false);
    const { pushEvidence, lang } = useCopilot();
    return (_jsxs(_Fragment, { children: [_jsxs("button", { type: "button", onClick: () => {
                    setOpen((v) => !v);
                    if (!open)
                        pushEvidence(evidence);
                }, className: cx("inline-flex items-center gap-1.5 rounded-full border border-ink-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-ink-600 transition hover:border-brand-300 hover:text-brand-700", className), children: [_jsx(FlaskConical, { className: "h-3.5 w-3.5" }), lang === "bn" ? "প্রমাণ" : "evidence", _jsx(ChevronDown, { className: cx("h-3 w-3 transition-transform", open && "rotate-180") })] }), open ? (_jsx("div", { className: "mt-3", children: _jsx(EvidenceBody, { evidence: evidence }) })) : null] }));
}
export function EvidenceBody({ evidence }) {
    const { lang } = useCopilot();
    const bn = lang === "bn";
    return (_jsxs("div", { className: "animate-in rounded-xl border border-ink-200 bg-ink-50/70 p-4", children: [_jsxs("div", { className: "mb-3 flex flex-wrap items-center justify-between gap-2", children: [_jsx("div", { className: "text-[12px] font-bold text-ink-900", children: evidence.headline }), _jsx(ConfidenceDot, { value: evidence.confidence })] }), _jsx("p", { className: "mb-3 text-[12px] leading-relaxed text-ink-600", children: evidence.confidenceNote }), evidence.metrics.length ? (_jsxs(_Fragment, { children: [_jsx("div", { className: "mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase", children: bn ? "মূল সংখ্যা" : "Key numbers" }), _jsx("div", { className: "mb-4 grid gap-2 sm:grid-cols-2", children: evidence.metrics.map((m) => (_jsxs("div", { className: "rounded-lg border border-ink-200 bg-white px-3 py-2", children: [_jsxs("div", { className: "flex items-baseline justify-between gap-2", children: [_jsx("span", { className: "truncate text-[11px] font-semibold text-ink-500", children: m.label }), _jsx("span", { className: "tabular shrink-0 text-[13px] font-bold text-ink-900", children: formatValue(m.value, m.unit, lang) })] }), m.detail ? _jsx("div", { className: "mt-0.5 text-[11px] leading-snug text-ink-400", children: m.detail }) : null] }, m.id))) })] })) : null, evidence.reasons.length ? (_jsxs(_Fragment, { children: [_jsx("div", { className: "mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase", children: bn ? "কেন" : "Why" }), _jsx("ul", { className: "mb-4 space-y-1.5", children: evidence.reasons.map((r, i) => (_jsxs("li", { className: "flex items-start gap-2 text-[12px] leading-relaxed text-ink-700", children: [_jsx("span", { className: cx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", r.polarity === "positive" ? "bg-mint-500" : r.polarity === "negative" ? "bg-brand-500" : "bg-ink-300") }), r.text] }, i))) })] })) : null, _jsxs("div", { className: "grid gap-4 sm:grid-cols-2", children: [evidence.assumptions.length ? (_jsxs("div", { children: [_jsx("div", { className: "mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase", children: bn ? "ধরণাবিধান" : "Assumptions" }), _jsx("ul", { className: "space-y-1 text-[12px] leading-relaxed text-ink-600", children: evidence.assumptions.map((a, i) => (_jsxs("li", { children: ["\u00B7 ", a] }, i))) })] })) : null, evidence.sources.length ? (_jsxs("div", { children: [_jsx("div", { className: "mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase", children: bn ? "উৎস" : "Sources" }), _jsx("ul", { className: "space-y-1 text-[12px] leading-relaxed text-ink-600", children: evidence.sources.map((s, i) => (_jsxs("li", { className: "flex items-start gap-1.5", children: [_jsx(Database, { className: "mt-0.5 h-3 w-3 shrink-0 text-ink-400" }), _jsx("span", { className: "font-mono text-[11px]", children: s })] }, i))) })] })) : null] }), evidence.evaluation?.length ? (_jsx("div", { className: "mt-4 flex flex-wrap gap-2 border-t border-ink-200 pt-3", children: evidence.evaluation.map((e) => (_jsxs(Chip, { tone: "neutral", children: [e.metric, ": ", e.value.toFixed(3), " ", e.unit] }, e.metric))) })) : null] }));
}
/** Inline, always-visible disclaimer used on the readiness and evaluation screens. */
export function ResponsibleNotice({ children, icon }) {
    return (_jsxs("div", { className: "flex items-start gap-2.5 rounded-xl border border-ink-200 bg-white px-4 py-3 text-[12px] leading-relaxed text-ink-600", children: [_jsx("span", { className: "mt-0.5 shrink-0 text-mint-600", children: icon ?? _jsx(ShieldCheck, { className: "h-4 w-4" }) }), _jsx("div", { children: children })] }));
}
export function GroundTruthStrip({ children }) {
    return _jsx("div", { className: "gt-stripes rounded-xl border border-amber-200/70 px-4 py-3", children: children });
}
