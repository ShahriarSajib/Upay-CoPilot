import type { Evidence } from "@/types";
import type { UserContext } from "@/data/context";
import { clamp, mean, monthsBetween, quantiles, round, sum } from "@/lib/format";
import { estimateEssentialMonthly, essentialByMonth } from "./spending";

/**
 * Emergency Fund Planner
 * ---------------------------------------------------------------------------
 * The "three months of essential expenses" rule of thumb is treated as a
 * configurable planning assumption, never as advice. The household's own
 * essential baseline is measured from the ledger, the multiplier is adjustable,
 * and the target is expressed as a range rather than a single truth.
 */

export interface EmergencyPlan {
  essentialMonthly: number;
  essentialLow: number;
  essentialHigh: number;
  monthsTarget: number;
  targetAmount: number;
  targetLow: number;
  targetHigh: number;
  liquidBalance: number;
  saved: number;
  remaining: number;
  progress: number;
  monthsOfCoverNow: number;
  monthlyToFund: number;
  monthsToFund: number;
  shortfallMonths: number;
  evidence: Evidence;
}

export function runEmergencyPlanner(ctx: UserContext, monthsTarget = 3): EmergencyPlan {
  const essentialMonthly = estimateEssentialMonthly(ctx);
  const q = quantiles(essentialByMonth(ctx));

  const targetAmount = essentialMonthly * monthsTarget;
  const liquid = ctx.liquidBalance;
  const saved = Math.min(liquid, targetAmount);
  const remaining = Math.max(0, targetAmount - liquid);
  const monthsOfCoverNow = essentialMonthly > 0 ? liquid / essentialMonthly : 0;

  const capacity = mean(ctx.monthly.map((m) => Math.max(0, m.income - m.spend)));
  const monthlyToFund = capacity > 0 ? Math.min(remaining, capacity) : 0;
  const monthsToFund = monthlyToFund > 0 ? Math.ceil(remaining / monthlyToFund) : Infinity;

  const evidence: Evidence = {
    engine: "Emergency Fund Planner",
    headline: `${monthsOfCoverNow.toFixed(1)} months of essential spend covered`,
    confidence: round(clamp(0.5 + Math.min(ctx.monthly.length, 9) * 0.045, 0.5, 0.9), 2),
    confidenceNote: "Essential baseline is the median category-weighted essential spend across observed months.",
    metrics: [
      { id: "essential_monthly", label: "Essential monthly spend", value: round(essentialMonthly, 0), unit: "bdt", detail: `range ৳${Math.round(q.p25).toLocaleString("en-US")}–৳${Math.round(q.p75).toLocaleString("en-US")}`, source: "transactions" },
      { id: "target", label: `Target (${monthsTarget}× essential)`, value: round(targetAmount, 0), unit: "bdt", detail: "configurable planning assumption", source: "product assumption" },
      { id: "liquid", label: "Liquid balance", value: round(liquid, 0), unit: "bdt", detail: "upay + bank + cash", source: "wallets" },
      { id: "remaining", label: "Still to fund", value: round(remaining, 0), unit: "bdt", detail: "target minus liquid balance", source: "derived" },
      { id: "months_to_fund", label: "Months to fund at current surplus", value: Number.isFinite(monthsToFund) ? monthsToFund : 0, unit: "months", detail: `৳${Math.round(monthlyToFund).toLocaleString("en-US")} per month`, source: "model" },
    ],
    reasons: [
      {
        polarity: monthsOfCoverNow >= monthsTarget ? "positive" : "negative",
        text:
          monthsOfCoverNow >= monthsTarget
            ? `The liquid balance already covers ${monthsOfCoverNow.toFixed(1)} months of essential spend.`
            : `The liquid balance covers ${monthsOfCoverNow.toFixed(1)} of the ${monthsTarget} months that the assumption targets.`,
      },
      {
        polarity: "neutral",
        text: `Household essential baseline is ৳${Math.round(essentialMonthly).toLocaleString("en-US")} per month (category-weighted, not self-declared).`,
      },
      {
        polarity: "neutral",
        text: `Recurring commitments alone total ৳${sum(ctx.recurring.map((r) => r.amount)).toLocaleString("en-US")} per cycle.`,
      },
    ],
    assumptions: [
      `"${monthsTarget} months of essential expenses" is a widely used planning convention, not a rule. Change the multiplier to test alternatives.`,
      "Essential baseline uses fixed category shares (housing/utilities = 100%, food = 65%, shopping = 5%).",
      "The whole liquid balance counts as available; restricted or committed funds are not modelled.",
    ],
    sources: ["transactions.csv", "wallets.csv", "recurring_expenses.csv"],
  };

  return {
    essentialMonthly: round(essentialMonthly, 0),
    essentialLow: round(q.p25, 0),
    essentialHigh: round(q.p75, 0),
    monthsTarget,
    targetAmount: round(targetAmount, 0),
    targetLow: round(q.p25 * monthsTarget, 0),
    targetHigh: round(q.p75 * monthsTarget, 0),
    liquidBalance: round(liquid, 0),
    saved: round(saved, 0),
    remaining: round(remaining, 0),
    progress: targetAmount > 0 ? clamp(liquid / targetAmount, 0, 1) : 0,
    monthsOfCoverNow: round(monthsOfCoverNow, 2),
    monthlyToFund: round(monthlyToFund, 0),
    monthsToFund: Number.isFinite(monthsToFund) ? monthsToFund : 0,
    shortfallMonths: round(Math.max(0, monthsTarget - monthsOfCoverNow), 2),
    evidence,
  };
}

/** Which month an emergency fund at `monthly` would be completed. */
export function emergencyCompletionDate(ctx: UserContext, monthly: number): string | null {
  const essential = estimateEssentialMonthly(ctx);
  const target = essential * 3;
  const remaining = Math.max(0, target - ctx.liquidBalance);
  if (monthly <= 0) return null;
  const months = monthsBetween(ctx.asOf, ctx.asOf) + Math.ceil(remaining / monthly);
  const d = new Date(ctx.asOf.getFullYear(), ctx.asOf.getMonth() + months, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}