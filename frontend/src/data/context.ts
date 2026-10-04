import type {
  BehaviourLabel,
  FinancialGoal,
  FinancialProfile,
  GoalContribution,
  IncomeEvent,
  InjectedPattern,
  Persona,
  RecurringExpense,
  Transaction,
  User,
  Wallet,
} from "@/types";
import type { Dataset } from "./snapshot";
import {
  addDays,
  coefficientOfVariation,
  isoDate,
  mean,
  monthDaysIn,
  monthKey,
  startOfDay,
  sum,
} from "@/lib/format";

/* ------------------------------------------------------------------ *
 * Ledger semantics
 *
 * Two deliberately different views of the same ledger:
 *
 *  1. Product semantics (used for every customer-facing number):
 *     a cash-in / cash-out pair moves money between a digital wallet and
 *     physical cash. It is neither income nor consumption, so both legs are
 *     excluded, and user-to-user send/receive pairs are excluded as internal
 *     movements. This matches ml/dataset/profiles.py.
 *
 *  2. Labeller semantics (used only by engines/behaviour.ts to re-implement
 *     ml/dataset/labels.py for the evaluation screen): only the two transfer
 *     types are excluded, so a cash-in leg counts as inflow.
 * ------------------------------------------------------------------ */

export const TRANSFER_TYPES = new Set(["send_money", "receive_money"]);

export const isTransfer = (t: Transaction) => TRANSFER_TYPES.has(t.transaction_type);
export const isCashLeg = (t: Transaction) => t.category === "cash";

/** Inflow that represents real money arriving: not a transfer, not a cash deposit. */
export const isProductIncome = (t: Transaction) => t.direction === "inflow" && !isTransfer(t) && !isCashLeg(t);
/** Outflow that represents real consumption: not a transfer, not a cash movement. */
export const isProductSpend = (t: Transaction) => t.direction === "outflow" && !isTransfer(t) && !isCashLeg(t);

export interface DailyPoint {
  date: Date;
  iso: string;
  income: number;
  spend: number;
  net: number;
  cashOut: number;
  cashIn: number;
  transferIn: number;
  transferOut: number;
  txCount: number;
}

export interface MonthlyPoint {
  key: string;
  income: number;
  spend: number;
  savings: number;
  savingsRate: number;
  lateSpend: number;
  lateShare: number;
  cashSpend: number;
  cashShare: number;
  contribution: number;
  anomalyCount: number;
  txCount: number;
}

export interface WalletSnapshot extends Wallet {
  closingBalance: number;
  lastSeen: string;
  txCount: number;
}

export interface UserContext {
  user: User;
  asOf: Date;
  windowStart: Date;
  windowEnd: Date;
  wallets: WalletSnapshot[];
  walletType: Map<string, Wallet["wallet_type"]>;
  cashWalletIds: Set<string>;
  transactions: Transaction[];
  incomeEvents: IncomeEvent[];
  recurring: RecurringExpense[];
  goals: FinancialGoal[];
  contributions: GoalContribution[];
  contributionsByGoal: Map<string, number>;
  profile: FinancialProfile | undefined;
  labels: BehaviourLabel[];
  patterns: InjectedPattern[];
  daily: DailyPoint[];
  dailyIndex: Map<string, DailyPoint>;
  monthly: MonthlyPoint[];
  currentMonth: MonthlyPoint;
  previousMonth: MonthlyPoint | undefined;
  upayBalance: number;
  liquidBalance: number;
  incomeCv: number;
  monthlyIncomeAvg: number;
  monthlySpendAvg: number;
  contributionRate: number;
}

/* ------------------------------------------------------------------ */

function emptyMonth(key: string): MonthlyPoint {
  return {
    key,
    income: 0,
    spend: 0,
    savings: 0,
    savingsRate: 0,
    lateSpend: 0,
    lateShare: 0,
    cashSpend: 0,
    cashShare: 0,
    contribution: 0,
    anomalyCount: 0,
    txCount: 0,
  };
}

export function buildUserContext(data: Dataset, userId: string): UserContext {
  const user = data.users.find((u) => u.user_id === userId) as User;
  const wallets = data.wallets.filter((w) => w.user_id === userId);
  const transactions = data.transactions.filter((t) => t.user_id === userId);
  const incomeEvents = data.incomeEvents.filter((i) => i.user_id === userId);
  const recurring = data.recurring.filter((r) => r.user_id === userId);
  const goals = data.goals.filter((g) => g.user_id === userId);
  const contributions = data.contributions.filter((c) => c.user_id === userId);
  const profile = data.profiles.find((p) => p.user_id === userId);
  const labels = data.labels.filter((l) => l.user_id === userId);
  const patterns = data.patterns.filter((p) => p.user_id === userId);

  const walletType = new Map(wallets.map((w) => [w.wallet_id, w.wallet_type] as const));
  const cashWalletIds = new Set(
    transactions.filter((t) => t.transaction_type === "cash_in").map((t) => t.wallet_id),
  );

  // Window and "today". Anchoring on the ledger rather than the wall clock keeps
  // forecasts reproducible regardless of when the demo is run.
  const stamps = transactions.map((t) => t.timestamp).sort();
  const windowEnd = startOfDay(new Date(stamps[stamps.length - 1] ?? "2026-09-30"));
  const windowStart = startOfDay(new Date(stamps[0] ?? "2026-01-01"));
  const asOf = windowEnd;

  // Daily ledger roll-up over product semantics.
  const dailyMap = new Map<string, DailyPoint>();
  for (const day of monthDaysIn(windowStart, windowEnd)) {
    dailyMap.set(isoDate(day), {
      date: day,
      iso: isoDate(day),
      income: 0,
      spend: 0,
      net: 0,
      cashOut: 0,
      cashIn: 0,
      transferIn: 0,
      transferOut: 0,
      txCount: 0,
    });
  }

  for (const t of transactions) {
    const iso = t.timestamp.slice(0, 10);
    const point = dailyMap.get(iso);
    if (!point) continue;
    point.txCount += 1;
    if (t.transaction_type === "cash_out") point.cashOut += t.amount;
    else if (t.transaction_type === "cash_in") point.cashIn += t.amount;
    else if (t.transaction_type === "receive_money") point.transferIn += t.amount;
    else if (t.transaction_type === "send_money") point.transferOut += t.amount;
    if (isProductIncome(t)) point.income += t.amount;
    else if (isProductSpend(t)) point.spend += t.amount;
  }
  for (const point of dailyMap.values()) point.net = point.income - point.spend;

  const daily = [...dailyMap.values()];

  // Monthly roll-up, mirroring the label rules in ml/dataset/labels.py so that
  // the evaluation screen can reproduce them faithfully.
  const monthMap = new Map<string, MonthlyPoint>();
  const getMonth = (key: string) => {
    let m = monthMap.get(key);
    if (!m) {
      m = emptyMonth(key);
      monthMap.set(key, m);
    }
    return m;
  };
  for (const day of daily) getMonth(monthKey(day.date));

  const patternCountByMonth = new Map<string, number>();
  for (const p of patterns) {
    const key = p.timestamp.slice(0, 7);
    patternCountByMonth.set(key, (patternCountByMonth.get(key) ?? 0) + 1);
  }
  for (const t of transactions) {
    const key = t.timestamp.slice(0, 7);
    const m = getMonth(key);
    m.txCount += 1;
    if (isProductIncome(t)) m.income += t.amount;
    if (isProductSpend(t)) {
      m.spend += t.amount;
      if (Number(t.timestamp.slice(8, 10)) >= 23) m.lateSpend += t.amount;
      if (cashWalletIds.has(t.wallet_id)) m.cashSpend += t.amount;
    }
  }
  for (const c of contributions) {
    const key = c.timestamp.slice(0, 7);
    getMonth(key).contribution += c.amount;
  }
  for (const [key, m] of monthMap) {
    m.savings = m.income - m.spend;
    m.savingsRate = m.income > 0 ? m.savings / m.income : 0;
    m.lateShare = m.spend > 0 ? m.lateSpend / m.spend : 0;
    m.cashShare = m.spend > 0 ? m.cashSpend / m.spend : 0;
    m.anomalyCount = patternCountByMonth.get(key) ?? 0;
  }

  const monthly = [...monthMap.values()].sort((a, b) => a.key.localeCompare(b.key));
  const currentMonth = monthly[monthly.length - 1] ?? emptyMonth(monthKey(asOf));
  const previousMonth = monthly.length > 1 ? monthly[monthly.length - 2] : undefined;

  // Wallet closing balances: last observed balance_after per wallet.
  const lastByWallet = new Map<string, Transaction>();
  for (const t of transactions) {
    const prev = lastByWallet.get(t.wallet_id);
    if (!prev || t.timestamp >= prev.timestamp) lastByWallet.set(t.wallet_id, t);
  }
  const txCountByWallet = new Map<string, number>();
  for (const t of transactions) txCountByWallet.set(t.wallet_id, (txCountByWallet.get(t.wallet_id) ?? 0) + 1);

  const walletSnapshots: WalletSnapshot[] = wallets.map((w) => {
    const last = lastByWallet.get(w.wallet_id);
    return {
      ...w,
      closingBalance: last ? Math.max(0, last.balance_after) : w.opening_balance,
      lastSeen: last?.timestamp ?? w.opening_balance.toString(),
      txCount: txCountByWallet.get(w.wallet_id) ?? 0,
    };
  });

  const upayBalance = sum(
    walletSnapshots.filter((w) => w.wallet_type === "upay").map((w) => w.closingBalance),
  );
  const liquidBalance = sum(
    walletSnapshots
      .filter((w) => w.wallet_type === "upay" || w.wallet_type === "bank" || w.wallet_type === "cash")
      .map((w) => w.closingBalance),
  );

  const contributionsByGoal = new Map<string, number>();
  for (const c of contributions) {
    contributionsByGoal.set(c.goal_id, (contributionsByGoal.get(c.goal_id) ?? 0) + c.amount);
  }

  const incomeCv = coefficientOfVariation(monthly.map((m) => m.income));
  const monthlyIncomeAvg = mean(monthly.map((m) => m.income));
  const monthlySpendAvg = mean(monthly.map((m) => m.spend));
  const contributionRate =
    monthlyIncomeAvg > 0 ? sum(monthly.map((m) => m.contribution)) / monthly.length / monthlyIncomeAvg : 0;

  return {
    user,
    asOf,
    windowStart,
    windowEnd,
    wallets: walletSnapshots,
    walletType,
    cashWalletIds,
    transactions,
    incomeEvents,
    recurring,
    goals,
    contributions,
    contributionsByGoal,
    profile,
    labels,
    patterns,
    daily,
    dailyIndex: new Map(daily.map((d) => [d.iso, d])),
    monthly,
    currentMonth,
    previousMonth,
    upayBalance,
    liquidBalance,
    incomeCv,
    monthlyIncomeAvg,
    monthlySpendAvg,
    contributionRate,
  };
}

/* ------------------------------------------------------------------ *
 * Shared derivations
 * ------------------------------------------------------------------ */

/** Reference date used for "next month" arithmetic: end of the observed window. */
export function horizonEnd(ctx: UserContext, days: number): Date {
  return addDays(ctx.asOf, days);
}

export const personaLabel: Record<Persona, { en: string; bn: string; blurb: string }> = {
  stable_saver: { en: "Stable saver", bn: "স্থিতিশীল সঞ্চয়কারী", blurb: "Regular income, low cash-out, steady saving." },
  end_month_shortage: {
    en: "Month-end shortage",
    bn: "মাস শেষে টাকা ঘাটতি",
    blurb: "Back-loaded spending drives the balance toward zero.",
  },
  irregular_income: {
    en: "Irregular income",
    bn: "অনিয়মিত আয়",
    blurb: "Income arrives in bursts, so averages mislead.",
  },
  high_cash_dependency: {
    en: "High cash dependency",
    bn: "নগদের উপর নির্ভরশীল",
    blurb: "A large share of spending settles in physical cash.",
  },
  goal_oriented: {
    en: "Goal oriented",
    bn: "লক্ষ্যনির্ভর",
    blurb: "Multiple active goals with consistent contributions.",
  },
  seasonal_spender: {
    en: "Seasonal spender",
    bn: "মৌসুমি খরচকারী",
    blurb: "Spending spikes around festival and travel periods.",
  },
  sudden_anomaly: {
    en: "Sudden anomaly",
    bn: "হঠাৎ অস্বাভাবিক",
    blurb: "Occasional large unplanned charges among normal tickets.",
  },
  financial_pressure: {
    en: "Financial pressure",
    bn: "আর্থিক চাপ",
    blurb: "Spending outpaces income and savings decline.",
  },
};