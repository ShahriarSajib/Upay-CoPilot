import type { Evidence, Transaction } from "@/types";
import { isProductSpend, type DailyPoint, type MonthlyPoint, type UserContext } from "@/data/context";
import { clamp, mean, median, monthKey, quantiles, round, sum } from "@/lib/format";

/**
 * Smart Spending Intelligence
 * ---------------------------------------------------------------------------
 * Category roll-up, discretionary share, small-purchase accumulation,
 * recurring-obligation detection straight from the ledger, and the
 * day-of-month concentration profile that drives the shortage predictor.
 */

export const CATEGORY_LABELS: Record<string, { en: string; bn: string }> = {
  food: { en: "Food", bn: "খাবার" },
  transport: { en: "Transport", bn: "পরিবহন" },
  shopping: { en: "Shopping", bn: "কেনাকাটা" },
  education: { en: "Education", bn: "শিক্ষা" },
  health: { en: "Health", bn: "স্বাস্থ্য" },
  utilities: { en: "Utilities", bn: "ইউটিলিটি" },
  communication: { en: "Communication", bn: "যোগাযোগ" },
  entertainment: { en: "Entertainment", bn: "বিনোদন" },
  family: { en: "Family", bn: "পরিবার" },
  housing: { en: "Housing", bn: "বাসা" },
  cash: { en: "Cash movement", bn: "নগদ" },
  transfer: { en: "Transfer", bn: "ট্রান্সফার" },
  other: { en: "Other", bn: "অন্যান্য" },
};

export const ESSENTIAL_CATEGORIES = ["housing", "utilities", "communication", "transport", "health", "education"];

/** Share of each category that a household cannot easily defer. */
const ESSENTIAL_SHARE: Record<string, number> = {
  housing: 1,
  utilities: 1,
  communication: 0.8,
  transport: 0.7,
  health: 1,
  education: 0.6,
  food: 0.65,
  family: 0.3,
  shopping: 0.05,
  entertainment: 0,
  other: 0.1,
};

export interface CategorySlice {
  key: string;
  label: string;
  labelBn: string;
  amount: number;
  share: number;
  count: number;
  avgTicket: number;
  vsLastMonth: number | null;
  essentialShare: number;
  topSubcategories: { name: string; amount: number }[];
}

export interface SmallPurchaseLeak {
  threshold: number;
  count: number;
  amount: number;
  shareOfSpend: number;
  topCategories: { key: string; label: string; amount: number; count: number }[];
  note: string;
  noteBn: string;
}

export interface DetectedRecurring {
  name: string;
  label: string;
  category: string;
  amount: number;
  amountSpread: number;
  occurrences: number;
  frequency: "monthly" | "weekly" | "fortnightly";
  expectedDay: number;
  confidence: number;
  mandatoryHint: boolean;
}

export interface DayOfMonthProfile {
  buckets: { label: string; dayStart: number; dayEnd: number; amount: number; share: number }[];
  lateShare: number;
  lateVsEarlyRatio: number;
  peakDay: number;
  peakAmount: number;
}

export interface SpendingResult {
  monthKey: string;
  totalSpend: number;
  essentialSpend: number;
  discretionarySpend: number;
  discretionaryShare: number;
  categories: CategorySlice[];
  prevCategories: CategorySlice[];
  smallPurchases: SmallPurchaseLeak;
  recurring: DetectedRecurring[];
  dayProfile: DayOfMonthProfile;
  essentialMonthly: number;
  txCount: number;
  avgTicket: number;
  evidence: Evidence;
}

/* ------------------------------------------------------------------ */

function sliceTransactions(ctx: UserContext, month: string | null): Transaction[] {
  return ctx.transactions.filter(
    (t) => isProductSpend(t) && (month === null || t.timestamp.slice(0, 7) === month),
  );
}

function buildCategorySlices(rows: Transaction[], prevRows: Transaction[]): CategorySlice[] {
  const prevTotals = new Map<string, { amount: number; count: number }>();
  for (const t of prevRows) {
    const e = prevTotals.get(t.category) ?? { amount: 0, count: 0 };
    e.amount += t.amount;
    e.count += 1;
    prevTotals.set(t.category, e);
  }

  const totals = new Map<string, { amount: number; count: number; subs: Map<string, number> }>();
  for (const t of rows) {
    const e = totals.get(t.category) ?? { amount: 0, count: 0, subs: new Map<string, number>() };
    e.amount += t.amount;
    e.count += 1;
    e.subs.set(t.subcategory, (e.subs.get(t.subcategory) ?? 0) + t.amount);
    totals.set(t.category, e);
  }

  const grand = sum([...totals.values()].map((v) => v.amount)) || 1;
  return [...totals.entries()]
    .map(([key, v]) => {
      const prev = prevTotals.get(key);
      const subs = [...v.subs.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([name, amount]) => ({ name, amount }));
      return {
        key,
        label: CATEGORY_LABELS[key]?.en ?? key,
        labelBn: CATEGORY_LABELS[key]?.bn ?? key,
        amount: round(v.amount, 2),
        share: round(v.amount / grand, 4),
        count: v.count,
        avgTicket: round(v.amount / Math.max(1, v.count), 2),
        vsLastMonth: prev && prev.amount > 0 ? round(v.amount / prev.amount - 1, 4) : null,
        essentialShare: ESSENTIAL_SHARE[key] ?? 0,
        topSubcategories: subs,
      };
    })
    .sort((a, b) => b.amount - a.amount);
}

function detectSmallPurchases(rows: Transaction[], total: number, threshold: number): SmallPurchaseLeak {
  const small = rows.filter((t) => t.amount <= threshold);
  const amount = sum(small.map((t) => t.amount));
  const byCat = new Map<string, { amount: number; count: number }>();
  for (const t of small) {
    const e = byCat.get(t.category) ?? { amount: 0, count: 0 };
    e.amount += t.amount;
    e.count += 1;
    byCat.set(t.category, e);
  }
  const top = [...byCat.entries()]
    .sort((a, b) => b[1].amount - a[1].amount)
    .slice(0, 4)
    .map(([key, v]) => ({
      key,
      label: CATEGORY_LABELS[key]?.en ?? key,
      amount: round(v.amount, 2),
      count: v.count,
    }));
  return {
    threshold,
    count: small.length,
    amount: round(amount, 2),
    shareOfSpend: total > 0 ? round(amount / total, 4) : 0,
    topCategories: top,
    note: `${small.length} purchases at or below ৳${threshold.toLocaleString("en-US")} added up to ৳${Math.round(amount).toLocaleString("en-US")} this month. Worth a look if you want more room to save.`,
    noteBn: `৳${threshold.toLocaleString("en-US")} বা তার কম দামের ${small.length} টি কেনাকাটায় এই মাসে ৳${Math.round(amount).toLocaleString("en-US")} ব্যয় হয়েছে। বেশি সঞ্চয় করতে চাইলে এই খাতগুলো দেখা যেতে পারে।`,
  };
}

function detectRecurring(ctx: UserContext): DetectedRecurring[] {
  const rows = ctx.transactions.filter(isProductSpend);
  const groups = new Map<string, Transaction[]>();
  for (const t of rows) {
    const key = `${t.category}|${t.subcategory}`;
    const list = groups.get(key) ?? [];
    list.push(t);
    groups.set(key, list);
  }

  const out: DetectedRecurring[] = [];
  for (const [key, list] of groups) {
    if (list.length < 3) continue;
    const sorted = [...list].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const amounts = sorted.map((t) => t.amount);
    const meanAmount = mean(amounts);
    const spread = meanAmount > 0 ? (quantiles(amounts).p90 - quantiles(amounts).p10) / meanAmount : 1;
    const gaps = sorted.slice(1).map((t, i) => dayDiff(sorted[i].timestamp, t.timestamp));
    const medianGap = median(gaps);
    const frequency: DetectedRecurring["frequency"] =
      medianGap <= 10 ? "weekly" : medianGap <= 20 ? "fortnightly" : "monthly";
    const expectedGap = frequency === "weekly" ? 7 : frequency === "fortnightly" ? 14 : 30;
    const regularity = medianGap > 0 ? 1 - clamp(Math.abs(medianGap - expectedGap) / expectedGap, 0, 1) : 0;
    const stability = 1 - clamp(spread, 0, 1);
    const confidence = round(clamp(0.35 * regularity + 0.4 * stability + 0.25 * clamp(list.length / 8, 0, 1), 0, 1), 2);
    if (confidence < 0.45) continue;
    const [category, subcategory] = key.split("|");
    out.push({
      name: subcategory || category,
      label: `${titleCase(subcategory || category)} · ${CATEGORY_LABELS[category]?.en ?? category}`,
      category,
      amount: round(meanAmount, 2),
      amountSpread: round(spread, 3),
      occurrences: list.length,
      frequency,
      expectedDay: median(sorted.map((t) => Number(t.timestamp.slice(8, 10)))),
      confidence,
      mandatoryHint: ESSENTIAL_CATEGORIES.includes(category),
    });
  }
  return out.sort((a, b) => b.amount * b.confidence - a.amount * a.confidence).slice(0, 8);
}

function dayDiff(a: string, b: string): number {
  return Math.round(
    (new Date(`${b.slice(0, 10)}T00:00:00`).getTime() - new Date(`${a.slice(0, 10)}T00:00:00`).getTime()) /
      86_400_000,
  );
}

function buildDayProfile(month: MonthlyPoint, daily: DailyPoint[]): DayOfMonthProfile {
  const inMonth = daily.filter((d) => monthKey(d.date) === month.key);
  const early = sum(inMonth.filter((d) => d.date.getDate() <= 10).map((d) => d.spend));
  const mid = sum(inMonth.filter((d) => d.date.getDate() > 10 && d.date.getDate() <= 20).map((d) => d.spend));
  const late = sum(inMonth.filter((d) => d.date.getDate() > 20).map((d) => d.spend));
  const total = early + mid + late || 1;

  const windows = [
    { label: "Days 1–10", dayStart: 1, dayEnd: 10, amount: early },
    { label: "Days 11–20", dayStart: 11, dayEnd: 20, amount: mid },
    { label: "Days 21–30", dayStart: 21, dayEnd: 31, amount: late },
  ];

  let peakDay = 0;
  let peakAmount = 0;
  for (const d of inMonth) {
    if (d.spend > peakAmount) {
      peakAmount = d.spend;
      peakDay = d.date.getDate();
    }
  }

  return {
    buckets: windows.map((w) => ({ ...w, share: round(w.amount / total, 4) })),
    lateShare: round(month.lateShare, 4),
    lateVsEarlyRatio: early > 0 ? round(late / early, 3) : late > 0 ? 3 : 0,
    peakDay,
    peakAmount: round(peakAmount, 2),
  };
}

/* ------------------------------------------------------------------ */

export function estimateEssentialMonthly(ctx: UserContext): number {
  const perMonth = ctx.monthly.map((m) => essentialOfMonth(ctx, m.key));
  const positive = perMonth.filter((v) => v > 0);
  return round(median(positive.length ? positive : perMonth), 2);
}

function essentialOfMonth(ctx: UserContext, key: string): number {
  const rows = sliceTransactions(ctx, key);
  return sum(rows.map((t) => t.amount * (ESSENTIAL_SHARE[t.category] ?? 0)));
}

/** Category-weighted essential spend for every observed month, oldest first. */
export function essentialByMonth(ctx: UserContext): number[] {
  return ctx.monthly.map((m) => essentialOfMonth(ctx, m.key));
}

export function discretionaryOfMonth(ctx: UserContext, key: string): number {
  const rows = sliceTransactions(ctx, key);
  return round(
    sum(rows.map((t) => t.amount * (1 - (ESSENTIAL_SHARE[t.category] ?? 0)))),
    2,
  );
}

export function discretionaryRows(ctx: UserContext, key: string): Transaction[] {
  return sliceTransactions(ctx, key).filter((t) => (ESSENTIAL_SHARE[t.category] ?? 0) < 0.5);
}

export function runSpendingEngine(ctx: UserContext, monthIndex = -1): SpendingResult {
  const month =
    monthIndex >= 0 && ctx.monthly[monthIndex] ? ctx.monthly[monthIndex] : ctx.currentMonth;
  const prev = ctx.monthly[ctx.monthly.indexOf(month) - 1];
  const rows = sliceTransactions(ctx, month.key);
  const prevRows = prev ? sliceTransactions(ctx, prev.key) : [];
  const total = sum(rows.map((t) => t.amount));
  const essential = essentialOfMonth(ctx, month.key);
  const categories = buildCategorySlices(rows, prevRows);
  const prevCategories = prev ? buildCategorySlices(prevRows, []) : [];

  // Threshold for "small frequent" accumulation: the 30th percentile of this
  // customer's own monthly tickets, floored at a psychologically round ৳300.
  const threshold = Math.max(300, Math.round(quantiles(rows.map((t) => t.amount)).p30 / 50) * 50);
  const smallPurchases = detectSmallPurchases(rows, total, threshold);
  const recurring = detectRecurring(ctx);
  const dayProfile = buildDayProfile(month, ctx.daily);

  const evidence: Evidence = {
    engine: "Smart Spending Intelligence",
    headline: `${month.key} spending ৳${Math.round(total).toLocaleString("en-US")}`,
    confidence: round(clamp(0.45 + Math.min(ctx.monthly.length, 9) * 0.055, 0.45, 0.95), 2),
    confidenceNote: `${rows.length} transactions classified in ${month.key}; categories come from the merchant labels recorded at the point of sale.`,
    metrics: [
      { id: "total", label: "Total spend", value: round(total, 2), unit: "bdt", detail: "outflows excluding transfers and cash movements", source: "transactions" },
      { id: "essential", label: "Essential spend", value: round(essential, 2), unit: "bdt", detail: "category-weighted non-deferrable share", source: "transactions" },
      { id: "discretionary", label: "Discretionary spend", value: round(total - essential, 2), unit: "bdt", detail: "the adjustable portion", source: "transactions" },
      { id: "late_share", label: "Spend after day 23", value: month.lateShare, unit: "percent", detail: "share of the month spent in the last third", source: "transactions" },
      { id: "small_purchase_total", label: `Purchases ≤ ৳${threshold}`, value: smallPurchases.amount, unit: "bdt", detail: `${smallPurchases.count} small purchases`, source: "transactions" },
      { id: "avg_ticket", label: "Average ticket", value: round(total / Math.max(1, rows.length), 2), unit: "bdt", detail: "mean outflow amount", source: "transactions" },
    ],
    reasons: [
      { polarity: "neutral", text: `${categories.length} spending categories active; the largest is ${categories[0]?.label ?? "n/a"} at ৳${Math.round(categories[0]?.amount ?? 0).toLocaleString("en-US")}.` },
      { polarity: "negative", text: `The final 10 days carry ${(month.lateShare * 100).toFixed(0)}% of this month's spending.` },
      { polarity: "neutral", text: `${recurring.length} recurring commitments were detected automatically from the ledger.` },
    ],
    assumptions: [
      `Small-purchase threshold is ৳${threshold.toLocaleString("en-US")}, set at this customer's own 30th percentile ticket (floor ৳300).`,
      "Essential share per category is a fixed household assumption, not a learned personal model.",
      "Merchant labels are taken as recorded; no model reclassifies them at inference time.",
    ],
    sources: ["transactions.csv (category, subcategory, merchant_type, channel)"],
  };

  return {
    monthKey: month.key,
    totalSpend: round(total, 2),
    essentialSpend: round(essential, 2),
    discretionarySpend: round(total - essential, 2),
    discretionaryShare: total > 0 ? round((total - essential) / total, 4) : 0,
    categories,
    prevCategories,
    smallPurchases,
    recurring,
    dayProfile,
    essentialMonthly: estimateEssentialMonthly(ctx),
    txCount: rows.length,
    avgTicket: round(total / Math.max(1, rows.length), 2),
    evidence,
  };
}

export function titleCase(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function monthRows(ctx: UserContext, key: string): DailyPoint[] {
  return ctx.daily.filter((d) => monthKey(d.date) === key);
}