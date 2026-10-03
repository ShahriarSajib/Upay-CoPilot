import type { Evidence, FinancialGoal, SimulationOutcome, SimulationResult, SimulationScenario } from "@/types";
import type { UserContext } from "@/data/context";
import { clamp, mean, median, monthsBetween, round } from "@/lib/format";
import { estimateCapacity } from "./goals";
import { defaultBuffer } from "./forecast";
import { estimateEssentialMonthly } from "./spending";

/**
 * What-If Simulation Engine
 * ---------------------------------------------------------------------------
 * Re-runs the same month-by-month model the optimiser uses, with one perturbed
 * input. Nothing here recommends anything: it answers "if this changed, what
 * would the ledger look like?" so the customer can compare the trade-offs
 * themselves and stay in control of the decision.
 */

const HORIZON_MONTHS = 12;

export const DEFAULT_SCENARIO: SimulationScenario = {
  monthlySavingChange: 0,
  incomeChangePercent: 0,
  expenseChange: 0,
  unexpectedExpense: 0,
  buffer: 0,
};

interface ProjectionInput {
  ctx: UserContext;
  goal: FinancialGoal | null;
  monthlySaving: number;
  incomeFactor: number;
  expenseDelta: number;
  unexpectedExpense: number;
}

interface Projection {
  outcome: SimulationOutcome;
  series: { month: string; balance: number; pot: number }[];
}

function project(input: ProjectionInput): Projection {
  const { ctx, goal, monthlySaving, incomeFactor, expenseDelta, unexpectedExpense } = input;
  const plan = estimateCapacity(ctx);
  const baseSurplus = plan.surplusMean * incomeFactor - expenseDelta;

  let balance = ctx.liquidBalance;
  let pot = goal?.current_amount ?? 0;
  const series: Projection["series"] = [];
  let minBalance = balance;
  let totalSaved = 0;

  for (let m = 1; m <= HORIZON_MONTHS; m += 1) {
    const contribution = Math.max(0, Math.round(monthlySaving));
    const shock = m === 1 ? unexpectedExpense : 0;
    balance += baseSurplus - contribution - shock;
    pot += contribution;
    totalSaved += contribution;
    minBalance = Math.min(minBalance, balance);
    const d = new Date(ctx.asOf.getFullYear(), ctx.asOf.getMonth() + m, 1);
    series.push({
      month: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
      balance: round(balance, 0),
      pot: round(pot, 0),
    });
  }

  const goalDate =
    goal && monthlySaving > 0
      ? monthsAhead(
          Math.ceil(Math.max(0, goal.target_amount - goal.current_amount) / monthlySaving),
          ctx.asOf,
        )
      : null;

  return {
    series,
    outcome: {
      monthlySaving: Math.max(0, Math.round(monthlySaving)),
      totalSaved: round(totalSaved, 0),
      endingBalance: round(series[series.length - 1]?.balance ?? balance, 0),
      minBalance: round(minBalance, 0),
      goalDate,
      shortfall: goal ? round(Math.max(0, goal.target_amount - (goal.current_amount + totalSaved)), 0) : 0,
    },
  };
}

function monthsAhead(months: number, from: Date): string {
  const d = new Date(from.getFullYear(), from.getMonth() + months, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function runSimulation(
  ctx: UserContext,
  scenario: SimulationScenario,
  goalId?: string,
): SimulationResult {
  const plan = estimateCapacity(ctx);
  const buffer = scenario.buffer > 0 ? scenario.buffer : defaultBuffer(ctx);
  const goal = ctx.goals.find((g) => g.goal_id === goalId) ?? ctx.goals[0] ?? null;

  const baseMonthly = Math.max(0, Math.min(plan.capacity, plan.surplusMean));
  const scenarioMonthly = Math.max(0, baseMonthly + scenario.monthlySavingChange);

  const baseline = project({ ctx, goal, monthlySaving: baseMonthly, incomeFactor: 1, expenseDelta: 0, unexpectedExpense: 0 });
  const scenarioRun = project({
    ctx,
    goal,
    monthlySaving: scenarioMonthly,
    incomeFactor: 1 + scenario.incomeChangePercent / 100,
    expenseDelta: scenario.expenseChange,
    unexpectedExpense: scenario.unexpectedExpense,
  });

  const goalShift =
    baseline.outcome.goalDate && scenarioRun.outcome.goalDate
      ? monthsBetween(new Date(`${baseline.outcome.goalDate}-01`), new Date(`${scenarioRun.outcome.goalDate}-01`))
      : null;

  const balanceDelta = scenarioRun.outcome.endingBalance - baseline.outcome.endingBalance;
  const worst = scenarioRun.outcome.minBalance;
  const riskLevel: SimulationResult["riskLevel"] =
    worst < 0 ? "high" : worst < buffer * 0.5 ? "elevated" : worst < buffer ? "moderate" : "low";

  const firstShortfallMonth = scenarioRun.series.find((p) => p.balance < buffer)?.month ?? null;

  const explanation: SimulationResult["explanation"] = [];
  if (goalShift === 0) {
    explanation.push({
      en: "The goal completion date does not move under this scenario.",
      bn: "এই পরিস্থিতিতে লক্ষ্য সম্পন্নের তারিখে পরিবর্তন আসছে না।",
    });
  } else if (goalShift !== null) {
    explanation.push({
      en: `Goal completion moves approximately ${Math.abs(goalShift)} month(s) ${goalShift < 0 ? "earlier" : "later"}.`,
      bn: `লক্ষ্য সম্পন্ন হওয়ার সময় প্রায় ${Math.abs(goalShift)} মাস ${goalShift < 0 ? "আগে" : "পরে"} চলে যাচ্ছে।`,
    });
  }
  explanation.push({
    en:
      balanceDelta >= 0
        ? `Projected closing balance improves by ৳${Math.abs(Math.round(balanceDelta)).toLocaleString("en-US")} over ${HORIZON_MONTHS} months.`
        : `Projected closing balance falls by ৳${Math.abs(Math.round(balanceDelta)).toLocaleString("en-US")} over ${HORIZON_MONTHS} months.`,
    bn:
      balanceDelta >= 0
        ? `${HORIZON_MONTHS} মাসে প্রকৃতিপত শেষ ব্যালেন্স ৳${Math.abs(Math.round(balanceDelta)).toLocaleString("en-US")} বেড়ে যাচ্ছে।`
        : `${HORIZON_MONTHS} মাসে প্রকৃতিপত শেষ ব্যালেন্স ৳${Math.abs(Math.round(balanceDelta)).toLocaleString("en-US")} কমে যাচ্ছে।`,
  });
  explanation.push({
    en:
      riskLevel === "low"
        ? `The minimum projected balance stays above the ৳${Math.round(buffer).toLocaleString("en-US")} buffer in every month.`
        : `The minimum projected balance reaches ৳${Math.abs(Math.round(worst)).toLocaleString("en-US")}, ${worst < buffer ? "below" : "close to"} the ৳${Math.round(buffer).toLocaleString("en-US")} buffer.`,
    bn:
      riskLevel === "low"
        ? `প্রতিটি মাসেই সর্বনিম্ন ব্যালেন্স ৳${Math.round(buffer).toLocaleString("en-US")} রিজার্ভের উপরে থাকছে।`
        : `সর্বনিম্ন ব্যালেন্স ৳${Math.abs(Math.round(worst)).toLocaleString("en-US")} হয়, যা ৳${Math.round(buffer).toLocaleString("en-US")} রিজার্ভের ${worst < buffer ? "নিচে" : "কাছে"}।`,
  });
  if (scenario.unexpectedExpense > 0) {
    explanation.push({
      en: `A one-off ৳${Math.round(scenario.unexpectedExpense).toLocaleString("en-US")} shock is applied in month 1.`,
      bn: `প্রথম মাসে একবারের ৳${Math.round(scenario.unexpectedExpense).toLocaleString("en-US")} অপ্রত্যাশিত ব্যয় ধরা হয়েছে।`,
    });
  }

  const evidence: Evidence = {
    engine: "What-If Simulation Engine",
    headline: `12-month simulation · risk ${riskLevel}`,
    confidence: round(clamp(0.5 + Math.min(ctx.monthly.length, 9) * 0.04, 0.5, 0.86), 2),
    confidenceNote:
      "Both arms run through the identical month-by-month model, so every difference is caused only by the scenario inputs.",
    metrics: [
      { id: "baseline_saving", label: "Baseline monthly saving", value: baseline.outcome.monthlySaving, unit: "bdt", detail: "min(capacity, historical surplus)", source: "ledger" },
      { id: "scenario_saving", label: "Scenario monthly saving", value: scenarioRun.outcome.monthlySaving, unit: "bdt", detail: `baseline + ৳${Math.round(scenario.monthlySavingChange).toLocaleString("en-US")}`, source: "scenario" },
      { id: "ending_baseline", label: "Baseline closing balance", value: baseline.outcome.endingBalance, unit: "bdt", detail: `after ${HORIZON_MONTHS} months`, source: "model" },
      { id: "ending_scenario", label: "Scenario closing balance", value: scenarioRun.outcome.endingBalance, unit: "bdt", detail: `after ${HORIZON_MONTHS} months`, source: "model" },
      { id: "min_scenario", label: "Scenario minimum balance", value: scenarioRun.outcome.minBalance, unit: "bdt", detail: `buffer ৳${Math.round(buffer).toLocaleString("en-US")}`, source: "model" },
      { id: "essential", label: "Essential monthly spend", value: round(estimateEssentialMonthly(ctx), 0), unit: "bdt", detail: "non-deferrable baseline", source: "transactions" },
    ],
    reasons: explanation.slice(0, 3).map((e) => ({ polarity: "neutral" as const, text: e.en })),
    assumptions: [
      `Monthly surplus of ৳${Math.round(plan.surplusMean).toLocaleString("en-US")} repeats for ${HORIZON_MONTHS} months without shocks.`,
      "Goal contributions are earmarked savings: they leave the liquid balance and grow the goal pot.",
      "An income change applies to every month; an unexpected expense applies once, in month 1.",
    ],
    sources: ["transactions.csv", "financial_goals.csv", "goal_contributions.csv", "recurring_expenses.csv"],
  };

  return {
    baseline: baseline.outcome,
    scenario: scenarioRun.outcome,
    goalDateShiftMonths: goalShift,
    riskLevel,
    balanceDelta: round(balanceDelta, 0),
    firstShortfallMonth,
    explanation,
    series: baseline.series.map((p, i) => ({
      date: p.month,
      baseline: p.balance,
      scenario: scenarioRun.series[i]?.balance ?? p.balance,
    })),
    evidence,
  };
}

/* ------------------------------------------------------------------ *
 * Responsible credit readiness — hypothetical affordability only
 * ------------------------------------------------------------------ */

export interface AffordabilityRow {
  amount: number;
  months: number;
  monthlyPayment: number;
  remainingMonthlyCash: number;
  bufferRetained: boolean;
  label: string;
}

export function loanAffordability(
  ctx: UserContext,
  amounts: number[],
  terms: number[],
  annualRate = 0.12,
): AffordabilityRow[] {
  const plan = estimateCapacity(ctx);
  const monthlyRate = annualRate / 12;
  const rows: AffordabilityRow[] = [];
  for (const amount of amounts) {
    for (const months of terms) {
      const payment =
        monthlyRate > 0
          ? (amount * monthlyRate) / (1 - Math.pow(1 + monthlyRate, -months))
          : amount / months;
      const remaining = plan.surplusMean - payment;
      rows.push({
        amount,
        months,
        monthlyPayment: round(payment, 0),
        remainingMonthlyCash: round(remaining, 0),
        bufferRetained: remaining > 0,
        label: `৳${Math.round(amount).toLocaleString("en-US")} over ${months} months`,
      });
    }
  }
  return rows;
}

/** How a given monthly saving target maps onto this customer's spending. */
export function savingsLevers(ctx: UserContext, amount: number) {
  const monthlySpend = mean(ctx.monthly.map((m) => m.spend));
  const medianMonthly = median(ctx.monthly.map((m) => m.spend));
  const essential = estimateEssentialMonthly(ctx);
  const pool = Math.max(0, medianMonthly - essential);
  return {
    amount: round(amount, 0),
    asShareOfSpend: monthlySpend > 0 ? round(amount / monthlySpend, 4) : 0,
    discretionaryPool: round(pool, 0),
    monthsToFund: pool > 0 ? round(amount / pool, 2) : 0,
  };
}