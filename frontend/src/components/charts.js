import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, } from "recharts";
import { shortDate, takaCompact, monthLabel } from "@/lib/format";
import { cx } from "./ui";
/**
 * Recharts wrappers.
 *
 * All of them share one axis/grid/tooltip treatment so charts read as a single
 * system, and every value formatter respects the customer's language and
 * numeral preference rather than hard-coding "en-US".
 */
const AXIS = { stroke: "#cbc7c1", tickLine: false, axisLine: false, fontSize: 11 };
const GRID = { stroke: "#e3e1dd", strokeDasharray: "3 3", vertical: false };
export const VIZ = ["#d71f42", "#0f766e", "#7c3aed", "#b45309", "#0369a1", "#be185d", "#4d7c0f", "#0891b2"];
function axisMoney(lang) {
    return (v) => takaCompact(v, lang);
}
/** Recharts hands tooltips loosely-typed values; narrow them here once. */
function moneyTooltip(lang) {
    return (v, n) => [takaCompact(Number(v ?? 0), lang), String(n)];
}
export function Panel({ title, subtitle, right, children, className, height = 240, }) {
    return (_jsxs("section", { className: cx("card p-5", className), children: [_jsxs("header", { className: "mb-4 flex items-start justify-between gap-4", children: [_jsxs("div", { className: "min-w-0", children: [_jsx("h3", { className: "text-[15px] font-semibold text-ink-900", children: title }), subtitle ? _jsx("p", { className: "mt-1 text-[12px] leading-relaxed text-ink-500", children: subtitle }) : null] }), right ? _jsx("div", { className: "shrink-0", children: right }) : null] }), _jsx("div", { style: { height }, children: children })] }));
}
/** Daily balance / income-expense area chart. */
export function AreaTrend({ data, keys, xKey = "date", lang = "en", formatter = axisMoney(lang), height = 240, }) {
    return (_jsx(ResponsiveContainer, { width: "100%", height: height, children: _jsxs(AreaChart, { data: data, margin: { top: 4, right: 8, left: 4, bottom: 0 }, children: [_jsx("defs", { children: keys.map((k, i) => (_jsxs("linearGradient", { id: `grad-${k.key}`, x1: "0", y1: "0", x2: "0", y2: "1", children: [_jsx("stop", { offset: "0%", stopColor: k.color ?? VIZ[i], stopOpacity: 0.28 }), _jsx("stop", { offset: "100%", stopColor: k.color ?? VIZ[i], stopOpacity: 0.02 })] }, k.key))) }), _jsx(CartesianGrid, { ...GRID }), _jsx(XAxis, { dataKey: xKey, ...AXIS, tickFormatter: (v) => shortDate(v, lang), minTickGap: 28 }), _jsx(YAxis, { ...AXIS, tickFormatter: formatter, width: 52 }), _jsx(Tooltip, { contentStyle: { fontSize: 12 }, formatter: (v, n) => [formatter(Number(v ?? 0)), String(n)], labelFormatter: (v) => shortDate(String(v), lang) }), _jsx(Legend, { wrapperStyle: { fontSize: 11, paddingTop: 6 }, iconType: "circle", iconSize: 7 }), keys.map((k, i) => (_jsx(Area, { type: "monotone", dataKey: k.key, name: k.label, stroke: k.color ?? VIZ[i], strokeWidth: 2, fill: `url(#grad-${k.key})`, dot: false, activeDot: { r: 3 } }, k.key)))] }) }));
}
export function MoneyBars({ data, xKey = "date", keys, lang = "en", stacked = false, height = 240, xTick, }) {
    return (_jsx(ResponsiveContainer, { width: "100%", height: height, children: _jsxs(BarChart, { data: data, margin: { top: 4, right: 8, left: 4, bottom: 0 }, barGap: 2, children: [_jsx(CartesianGrid, { ...GRID }), _jsx(XAxis, { dataKey: xKey, ...AXIS, tickFormatter: xTick ?? ((v) => shortDate(v, lang)), minTickGap: 20 }), _jsx(YAxis, { ...AXIS, tickFormatter: axisMoney(lang), width: 52 }), _jsx(Tooltip, { contentStyle: { fontSize: 12 }, cursor: { fill: "#f1f0ee", radius: 6 }, formatter: moneyTooltip(lang), labelFormatter: (v) => shortDate(String(v), lang) }), _jsx(Legend, { wrapperStyle: { fontSize: 11, paddingTop: 6 }, iconType: "circle", iconSize: 7 }), keys.map((k, i) => (_jsx(Bar, { dataKey: k.key, name: k.label, fill: k.color ?? VIZ[i], stackId: stacked ? "stack" : undefined, radius: stacked ? 0 : [4, 4, 0, 0], maxBarSize: 26 }, k.key)))] }) }));
}
/** Monthly income vs spending bars with a surplus line. */
export function MonthlyFlowChart({ data, lang = "en", height = 240, }) {
    return (_jsx(ResponsiveContainer, { width: "100%", height: height, children: _jsxs(BarChart, { data: data, margin: { top: 4, right: 8, left: 4, bottom: 0 }, children: [_jsx(CartesianGrid, { ...GRID }), _jsx(XAxis, { dataKey: "key", ...AXIS, tickFormatter: (v) => monthLabel(v, lang) }), _jsx(YAxis, { ...AXIS, tickFormatter: axisMoney(lang), width: 52 }), _jsx(Tooltip, { contentStyle: { fontSize: 12 }, cursor: { fill: "#f1f0ee", radius: 6 }, formatter: moneyTooltip(lang), labelFormatter: (v) => monthLabel(String(v), lang) }), _jsx(Legend, { wrapperStyle: { fontSize: 11, paddingTop: 6 }, iconType: "circle", iconSize: 7 }), _jsx(Bar, { dataKey: "income", name: lang === "bn" ? "আয়" : "Income", fill: VIZ[1], radius: [4, 4, 0, 0], maxBarSize: 22 }), _jsx(Bar, { dataKey: "spend", name: lang === "bn" ? "ব্যয়" : "Spending", fill: VIZ[0], radius: [4, 4, 0, 0], maxBarSize: 22 }), _jsx(Line, { type: "monotone", dataKey: "savings", name: lang === "bn" ? "সঞ্চয়" : "Savings", stroke: VIZ[3], strokeWidth: 2, dot: false })] }) }));
}
export function Donut({ data, lang = "en", height = 220, valueKey = "value", nameKey = "name", centerLabel, centerValue, }) {
    return (_jsxs("div", { className: "relative", children: [_jsx(ResponsiveContainer, { width: "100%", height: height, children: _jsxs(PieChart, { children: [_jsx(Pie, { data: data, dataKey: valueKey, nameKey: nameKey, innerRadius: "58%", outerRadius: "86%", paddingAngle: 2, strokeWidth: 0, children: data.map((_, i) => (_jsx(Cell, { fill: VIZ[i % VIZ.length] }, i))) }), _jsx(Tooltip, { contentStyle: { fontSize: 12 }, formatter: moneyTooltip(lang) })] }) }), centerValue ? (_jsxs("div", { className: "pointer-events-none absolute inset-0 flex flex-col items-center justify-center", children: [_jsx("span", { className: "tabular text-[18px] font-bold text-ink-900", children: centerValue }), centerLabel ? _jsx("span", { className: "text-[11px] text-ink-500", children: centerLabel }) : null] })) : null] }));
}
/** Baseline vs scenario line comparison — the simulator's core visual. */
export function CompareChart({ data, series, lang = "en", height = 260, reference, referenceLabel, }) {
    return (_jsx(ResponsiveContainer, { width: "100%", height: height, children: _jsxs(LineChart, { data: data, margin: { top: 6, right: 8, left: 4, bottom: 0 }, children: [_jsx(CartesianGrid, { ...GRID }), _jsx(XAxis, { dataKey: "date", ...AXIS, tickFormatter: (v) => monthLabel(v, lang) }), _jsx(YAxis, { ...AXIS, tickFormatter: axisMoney(lang), width: 52 }), _jsx(Tooltip, { contentStyle: { fontSize: 12 }, formatter: moneyTooltip(lang), labelFormatter: (v) => monthLabel(String(v), lang) }), _jsx(Legend, { wrapperStyle: { fontSize: 11, paddingTop: 6 }, iconType: "circle", iconSize: 7 }), reference !== undefined ? (_jsx(ReferenceLine, { y: reference, stroke: "#7b746c", strokeDasharray: "4 4", label: { value: referenceLabel, fontSize: 10, fill: "#7b746c" } })) : null, series.map((s, i) => (_jsx(Line, { type: "monotone", dataKey: s.key, name: s.label, stroke: s.color ?? VIZ[i], strokeWidth: 2.2, dot: false, strokeDasharray: s.key === "scenario" ? undefined : "5 4" }, s.key)))] }) }));
}
/** Forecast with an uncertainty band drawn as a translucent range. */
export function ForecastChart({ points, lang = "en", height = 280, buffer, }) {
    const data = points.map((p) => ({ ...p, band: Math.max(0, p.upper - p.lower), floor: p.lower }));
    return (_jsx(ResponsiveContainer, { width: "100%", height: height, children: _jsxs(AreaChart, { data: data, margin: { top: 4, right: 8, left: 4, bottom: 0 }, children: [_jsx("defs", { children: _jsxs("linearGradient", { id: "band", x1: "0", y1: "0", x2: "0", y2: "1", children: [_jsx("stop", { offset: "0%", stopColor: "#d71f42", stopOpacity: 0.16 }), _jsx("stop", { offset: "100%", stopColor: "#d71f42", stopOpacity: 0.04 })] }) }), _jsx(CartesianGrid, { ...GRID }), _jsx(XAxis, { dataKey: "date", ...AXIS, tickFormatter: (v) => shortDate(v, lang), minTickGap: 26 }), _jsx(YAxis, { ...AXIS, tickFormatter: axisMoney(lang), width: 52 }), _jsx(Tooltip, { contentStyle: { fontSize: 12 }, formatter: moneyTooltip(lang), labelFormatter: (v) => shortDate(String(v), lang) }), _jsx(Legend, { wrapperStyle: { fontSize: 11, paddingTop: 6 }, iconType: "circle", iconSize: 7 }), buffer !== undefined ? (_jsx(ReferenceLine, { y: Math.max(0, buffer), stroke: "#b45309", strokeDasharray: "4 4", label: { value: lang === "bn" ? "রিজার্ভ" : "buffer", fontSize: 10, fill: "#b45309" } })) : null, _jsx(Area, { dataKey: "band", name: lang === "bn" ? "আস্থা ব্যাপ্তি" : "uncertainty", stackId: "b", stroke: "none", fill: "url(#band)" }), _jsx(Area, { type: "monotone", dataKey: "floor", name: lang === "bn" ? "নিম্ন সীমা" : "lower", stackId: "b", stroke: "none", fill: "transparent", dot: false }), _jsx(Area, { type: "monotone", dataKey: "balance", name: lang === "bn" ? "প্রকৃতিপত ব্যালেন্স" : "projected balance", stroke: "#d71f42", strokeWidth: 2.4, fill: "none", dot: false })] }) }));
}
export function Legend2({ items }) {
    return (_jsx("div", { className: "flex flex-wrap items-center gap-x-4 gap-y-1.5", children: items.map((i) => (_jsxs("span", { className: "inline-flex items-center gap-1.5 text-[11px] text-ink-600", children: [_jsx("span", { className: "h-2 w-2 rounded-full", style: { background: i.color } }), i.label] }, i.label))) }));
}
