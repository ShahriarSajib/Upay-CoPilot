/* ------------------------------------------------------------------ *
 * Currency
 * ------------------------------------------------------------------ */
const BN_DIGITS = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"];
/** Convert ASCII digits inside an already-formatted string to Bangla digits. */
export function toBanglaDigits(value) {
    return value.replace(/[0-9]/g, (d) => BN_DIGITS[Number(d)]);
}
/** `18500` → `৳18,500`. `lang: "bn"` renders the digits in Bangla script. */
export function taka(amount, opts = {}) {
    const { lang = "en", decimals = false } = opts;
    const safe = Number.isFinite(amount) ? amount : 0;
    const body = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: decimals ? 2 : 0,
        maximumFractionDigits: decimals ? 2 : 0,
    }).format(Math.round(safe * 100) / 100);
    const text = `৳${body}`;
    return lang === "bn" ? toBanglaDigits(text) : text;
}
/** `18500` → `৳18.5k` — for chart axes and dense tiles. */
export function takaCompact(amount, lang = "en") {
    const abs = Math.abs(amount);
    const sign = amount < 0 ? "-" : "";
    let body;
    if (abs >= 1_000_000)
        body = `${(abs / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
    else if (abs >= 1000)
        body = `${(abs / 1000).toFixed(abs >= 10_000 ? 0 : 1)}k`;
    else
        body = String(Math.round(abs));
    const text = `${sign}৳${body}`;
    return lang === "bn" ? toBanglaDigits(text) : text;
}
/** Bare number with locale digits (no currency mark). */
export function num(value, lang = "en", decimals = 0) {
    const text = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    }).format(value);
    return lang === "bn" ? toBanglaDigits(text) : text;
}
export function percent(value, lang = "en", decimals = 0) {
    const text = `${(value * 100).toFixed(decimals)}%`;
    return lang === "bn" ? toBanglaDigits(text) : text;
}
export function pctPoints(value, lang = "en", decimals = 0) {
    const text = `${value.toFixed(decimals)}%`;
    return lang === "bn" ? toBanglaDigits(text) : text;
}
/* ------------------------------------------------------------------ *
 * Dates
 * ------------------------------------------------------------------ */
const BN_MONTHS = [
    "জানুয়ারি",
    "ফেব্রুয়ারি",
    "মার্চ",
    "এপ্রিল",
    "মে",
    "জুন",
    "জুলাই",
    "আগস্ট",
    "সেপ্টেম্বর",
    "অক্টোবর",
    "নভেম্বর",
    "ডিসেম্বর",
];
const EN_MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
];
/** Parse a `YYYY-MM-DD HH:mm:ss` cell from the dataset as a *local* date. */
export function parseDate(value) {
    if (value instanceof Date)
        return value;
    const m = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (!m)
        return new Date(value);
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4] ?? 0), Number(m[5] ?? 0));
}
export function isoDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}
export function monthKey(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}
/** ISO day (`2026-09-29`) or month key (`2026-09`) — anything else is a text label. */
const ISO_DATE = /^\d{4}-\d{2}(-\d{2})?/;
function isDateValue(value) {
    if (value instanceof Date)
        return !Number.isNaN(value.getTime());
    return ISO_DATE.test(value);
}
export function monthLabel(key, lang = "en") {
    if (!ISO_DATE.test(key))
        return key;
    const [y, m] = key.split("-").map(Number);
    const name = (lang === "bn" ? BN_MONTHS : EN_MONTHS)[(m ?? 1) - 1] ?? "";
    return lang === "bn" ? `${name} ${toBanglaDigits(String(y))}` : `${name} ${y}`;
}
/**
 * Chart axes sometimes carry text categories ("Housing", "25% of monthly
 * spend") instead of dates. Formatting those as dates produces "NaN undefined"
 * on screen, so anything that is not a date is returned untouched.
 */
export function shortDate(value, lang = "en") {
    if (!isDateValue(value))
        return String(value);
    const d = parseDate(value);
    const day = String(d.getDate());
    const month = (lang === "bn" ? BN_MONTHS : EN_MONTHS)[d.getMonth()];
    const text = `${day} ${month}`;
    return lang === "bn" ? toBanglaDigits(text) : text;
}
export function fullDate(value, lang = "en") {
    if (!isDateValue(value))
        return String(value);
    const d = parseDate(value);
    const day = String(d.getDate());
    const month = (lang === "bn" ? BN_MONTHS : EN_MONTHS)[d.getMonth()];
    const text = `${day} ${month} ${d.getFullYear()}`;
    return lang === "bn" ? toBanglaDigits(text) : text;
}
export function weekdayLabel(value, lang = "en") {
    if (!isDateValue(value))
        return String(value);
    const d = parseDate(value);
    const en = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getDay()];
    const bn = ["রবি", "সোম", "মঙ্গল", "বুধ", "বৃহঃ", "শুক্র", "শনি"][d.getDay()];
    return lang === "bn" ? `${bn}` : `${en}`;
}
export function addDays(date, days) {
    const next = new Date(date.getTime());
    next.setDate(next.getDate() + days);
    return next;
}
export function daysBetween(a, b) {
    return Math.round((startOfDay(b).getTime() - startOfDay(a).getTime()) / 86_400_000);
}
export function startOfDay(date) {
    const d = new Date(date.getTime());
    d.setHours(0, 0, 0, 0);
    return d;
}
export function monthDaysIn(from, to) {
    const out = [];
    let cursor = startOfDay(from);
    const end = startOfDay(to);
    while (cursor <= end) {
        out.push(new Date(cursor.getTime()));
        cursor = addDays(cursor, 1);
    }
    return out;
}
export function monthsBetween(from, to) {
    const a = new Date(from.getFullYear(), from.getMonth(), 1);
    const b = new Date(to.getFullYear(), to.getMonth(), 1);
    return Math.max(0, (b.getFullYear() - a.getFullYear()) * 12 + (b.getMonth() - a.getMonth()));
}
/* ------------------------------------------------------------------ *
 * Misc
 * ------------------------------------------------------------------ */
export function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}
export function round(value, decimals = 0) {
    const f = 10 ** decimals;
    return Math.round(value * f) / f;
}
export function sum(values) {
    return values.reduce((a, b) => a + b, 0);
}
export function mean(values) {
    return values.length ? sum(values) / values.length : 0;
}
/** Coefficient of variation — the repo's income-stability primitive. */
export function coefficientOfVariation(values) {
    if (values.length < 2)
        return 0;
    const m = mean(values);
    if (m === 0)
        return 0;
    const variance = mean(values.map((v) => (v - m) ** 2));
    return Math.sqrt(variance) / Math.abs(m);
}
export function stdDev(values) {
    if (values.length < 2)
        return 0;
    const m = mean(values);
    return Math.sqrt(mean(values.map((v) => (v - m) ** 2)));
}
export function median(values) {
    if (!values.length)
        return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
export function quantiles(values) {
    if (!values.length)
        return { p10: 0, p25: 0, p30: 0, p50: 0, p75: 0, p90: 0 };
    const sorted = [...values].sort((a, b) => a - b);
    const at = (p) => {
        const idx = (sorted.length - 1) * p;
        const lo = Math.floor(idx);
        const hi = Math.ceil(idx);
        return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
    };
    return { p10: at(0.1), p25: at(0.25), p30: at(0.3), p50: at(0.5), p75: at(0.75), p90: at(0.9) };
}
/** Human title for a snake_case vocabulary token. */
export function humanize(token) {
    return token
        .replace(/[_-]+/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase())
        .replace(/\bUpay\b/g, "upay");
}
export function truncate(text, max) {
    return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}
export function bandFor(score) {
    if (score >= 82)
        return "strong";
    if (score >= 68)
        return "good";
    if (score >= 52)
        return "moderate";
    if (score >= 34)
        return "weak";
    return "critical";
}
