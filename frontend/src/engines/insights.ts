import type { Evidence, Insight } from "@/types";
import type { UserContext } from "@/data/context";
import { runHealthEngine } from "./health";
import { runSpendingEngine } from "./spending";
import { runAnomalyEngine } from "./anomaly";
import { runShortageEngine, shortageRiskBand } from "./behaviour";
import { runForecast } from "./forecast";
import { runGoalEngine, estimateCapacity } from "./goals";
import { runEmergencyPlanner } from "./emergency";
import { runCashOutEngine } from "./cashout";

/**
 * Action Centre
 * ---------------------------------------------------------------------------
 * Deliberately capped and prioritised. A financial assistant that shows fifty
 * findings teaches nobody; this returns the handful of items where one concrete
 * change changes the outcome, each with WHY / WHAT / WHAT-CAN-I-DO attached to
 * the evidence that produced it.
 */

export interface ActionItem {
  id: string;
  rank: number;
  priority: "do-now" | "plan" | "watch";
  kind: "goal" | "obligation" | "spending" | "risk" | "learning" | "positive";
  title: string;
  titleBn: string;
  why: string;
  whyBn: string;
  what: string;
  whatBn: string;
  doThis: string;
  doThisBn: string;
  amount?: number;
  severity: "high" | "medium" | "low";
  evidence: Evidence;
  route?: string;
}

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 } as const;
const PRIORITY_ORDER = { "do-now": 0, plan: 1, watch: 2 } as const;

export function runActionCentre(ctx: UserContext): ActionItem[] {
  const health = runHealthEngine(ctx);
  const spending = runSpendingEngine(ctx);
  const anomaly = runAnomalyEngine(ctx);
  const shortage = runShortageEngine(ctx);
  const forecast = runForecast(ctx, 30);
  const capacity = estimateCapacity(ctx);
  const emergency = runEmergencyPlanner(ctx);
  const cash = runCashOutEngine(ctx);
  const items: ActionItem[] = [];

  // 1. Upcoming obligation that lands before the next income.
  const nextIncomeDay = ctx.incomeEvents
    .filter((e) => e.timestamp.slice(0, 10) > ctx.asOf.toISOString().slice(0, 10))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))[0];
  const nextIncomeDate = nextIncomeDay ? new Date(nextIncomeDay.timestamp.slice(0, 10)) : null;
  const upcoming = ctx.recurring
    .map((r) => {
      const monthLength = new Date(ctx.asOf.getFullYear(), ctx.asOf.getMonth() + 1, 0).getDate();
      const due = new Date(ctx.asOf.getFullYear(), ctx.asOf.getMonth(), Math.min(r.due_day || 1, monthLength));
      return { ...r, dueDate: due };
    })
    .filter((r) => r.dueDate > ctx.asOf)
    .sort((a, b) => a.dueDate.getTime() - b.dueDate.getTime());
  const soon = upcoming[0];
  if (soon && (!nextIncomeDate || soon.dueDate <= nextIncomeDate)) {
    const days = Math.round((soon.dueDate.getTime() - ctx.asOf.getTime()) / 86_400_000);
    items.push({
      id: "action_obligation",
      rank: 0,
      priority: "do-now",
      kind: "obligation",
      severity: days <= 3 ? "high" : "medium",
      title: `${titleise(soon.expense_name)} is due in ${days} day${days === 1 ? "" : "s"}`,
      titleBn: `${titleise(soon.expense_name)} এর পরিশোধ ${days} দিনের মধ্যে`,
      why: `${soon.expense_name} is a recurring charge of ৳${Math.round(soon.amount).toLocaleString("en-US")} on day ${soon.due_day} of each month.`,
      whyBn: `${soon.expense_name} প্রতি মাসের ${soon.due_day} তারিখে ৳${Math.round(soon.amount).toLocaleString("en-US")} নিয়মিত কাটা হয়।`,
      what: `The 30-day forecast holds ৳${forecast.expectedEndingBalance.toLocaleString("en-US")} after every scheduled obligation, with the trough at ৳${forecast.minBalance.toLocaleString("en-US")}.`,
      whatBn: `৩০ দিনের পূর্বাভাসে সব নির্ধারিত দায় পরিশোধ করে ৳${forecast.expectedEndingBalance.toLocaleString("en-US")} থাকবে, সর্বনিম্ন ৳${forecast.minBalance.toLocaleString("en-US")}।`,
      doThis: `Keep ৳${Math.round(soon.amount).toLocaleString("en-US")} aside ${Math.max(0, days - 1)} day(s) from now so it is not spent twice.`,
      doThisBn: `${Math.max(0, days - 1)} দিন আগেই ৳${Math.round(soon.amount).toLocaleString("en-US")} আলাদা রাখুন, যাতে একই টাকা দুবার না যায়।`,
      amount: soon.amount,
      route: "/forecast",
      evidence: forecast.evidence,
    });
  }

  // 2. Goal contribution.
  const openGoals = ctx.goals.filter((g) => g.target_amount > g.current_amount);
  const goal = openGoals[0];
  if (goal) {
    const feasibility = runGoalEngine(ctx, goal);
    const balanced = feasibility.scenarios.find((s) => s.key === "balanced")!;
    items.push({
      id: "action_goal",
      rank: 0,
      priority: feasibility.verdict === "on_track" ? "plan" : "do-now",
      kind: "goal",
      severity: feasibility.verdict === "infeasible" || feasibility.verdict === "at_risk" ? "high" : "medium",
      title: `Goal contribution for ${titleise(goal.goal_name)}: ৳${balanced.monthlyContribution.toLocaleString("en-US")}/month`,
      titleBn: `${titleise(goal.goal_name)} লক্ষ্যে মাসে ৳${balanced.monthlyContribution.toLocaleString("en-US")} জমানোর পরিকল্পনা`,
      why: `${Math.round((goal.current_amount / goal.target_amount) * 100)}% of ৳${Math.round(goal.target_amount).toLocaleString("en-US")} is saved, and ${feasibility.monthsLeft} month(s) remain until ${goal.target_date}.`,
      whyBn: `৳${Math.round(goal.target_amount).toLocaleString("en-US")} লক্ষ্যের ${Math.round((goal.current_amount / goal.target_amount) * 100)}% জমেছে, আর ${goal.target_date} পর্যন্ত ${feasibility.monthsLeft} মাস বাকি।`,
      what: feasibility.shortfall > 0
        ? `At the current capacity of ৳${feasibility.estimatedCapacity.toLocaleString("en-US")}/month the goal lands about ৳${Math.round(feasibility.shortfall).toLocaleString("en-US")} short.`
        : `At the current capacity the goal is reachable with about ৳${Math.round(-feasibility.shortfall).toLocaleString("en-US")} to spare.`,
      whatBn: feasibility.shortfall > 0
        ? `বর্তমান ৳${feasibility.estimatedCapacity.toLocaleString("en-US")}/month গতিতে লক্ষ্যে প্রায় ৳${Math.round(feasibility.shortfall).toLocaleString("en-US")} ঘাটতি থাকবে।`
        : `বর্তমান গতিতে লক্ষ্যে পৌঁছানো সম্ভব, প্রায় ৳${Math.round(-feasibility.shortfall).toLocaleString("en-US")} বাড়তি থাকবে।`,
      doThis: feasibility.shortfall > 0
        ? `Try the simulator: a ৳${Math.min(feasibility.shortfall / Math.max(1, feasibility.monthsLeft), capacity.capacity).toLocaleString("en-US")} higher monthly contribution closes the gap.`
        : "Keep the current pace and review the plan next month.",
      doThisBn: feasibility.shortfall > 0
        ? `সিমুলেটরে দেখুন: মাসে আরও ৳${Math.min(feasibility.shortfall / Math.max(1, feasibility.monthsLeft), capacity.capacity).toLocaleString("en-US")} জমালে ঘাটতি পূরণ হয়।`
        : "এই গতি ধরে রাখুন এবং পরের মাসে পরিকল্পনাটি পর্যালোচনা করুন।",
      amount: balanced.monthlyContribution,
      route: "/goals",
      evidence: feasibility.evidence,
    });
  }

  // 3. Late-month concentration.
  if (shortage.lateShare > 0.3) {
    items.push({
      id: "action_late_month",
      rank: 0,
      priority: shortage.lateShare > 0.4 ? "do-now" : "watch",
      kind: "spending",
      severity: shortage.lateShare > 0.4 ? "high" : "medium",
      title: `${(shortage.lateShare * 100).toFixed(0)}% of this month's spending lands in the last 10 days`,
      titleBn: `এই মাসের ${(shortage.lateShare * 100).toFixed(0)}% ব্যয় মাসের শেষ ১০ দিনে হয়েছে`,
      why: `${shortage.contributors.slice(0, 3).map((c) => `${c.category} ৳${Math.round(c.amount).toLocaleString("en-US")}`).join(", ")} drive most of it.`,
      whyBn: `${shortage.contributors.slice(0, 3).map((c) => `${c.category} ৳${Math.round(c.amount).toLocaleString("en-US")}`).join(", ")} এর বেশির ভাগ ব্যাখ্যা করে।`,
      what: shortage.suggestedReduction > 0
        ? `Reducing late-month discretionary spending by about ৳${shortage.suggestedReduction.toLocaleString("en-US")} keeps the balance above the ৳${shortage.buffer.toLocaleString("en-US")} buffer.`
        : `Even after this concentration the projected balance stays above the ৳${shortage.buffer.toLocaleString("en-US")} buffer.`,
      whatBn: shortage.suggestedReduction > 0
        ? `মাসের শেষের ব্যয় ৳${shortage.suggestedReduction.toLocaleString("en-US")} কমালে ব্যালেন্স ৳${shortage.buffer.toLocaleString("en-US")} রিজার্ভের উপরে থাকবে।`
        : `এই কেন্দ্রীভূত হওয়া সত্ত্বেও ব্যালেন্স ৳${shortage.buffer.toLocaleString("en-US")} রিজার্ভের উপরেই থাকবে।`,
      doThis: "Open the Spending page to see the day-by-day curve and the exact contributors.",
      doThisBn: "দিনভিত্তিক লেখচিত্র ও নির্দিষ্ট কারণ দেখতে স্পেন্ডিং পেজ খুলুন।",
      amount: shortage.suggestedReduction,
      route: "/spending",
      evidence: shortage.evidence,
    });
  }

  // 4. Small frequent purchases.
  if (spending.smallPurchases.shareOfSpend > 0.08 && spending.smallPurchases.count >= 5) {
    items.push({
      id: "action_small_purchases",
      rank: 0,
      priority: "plan",
      kind: "spending",
      severity: "low",
      title: `${spending.smallPurchases.count} small purchases added up to ৳${Math.round(spending.smallPurchases.amount).toLocaleString("en-US")}`,
      titleBn: `${spending.smallPurchases.count} টি ছোট কেনাকাটায় ৳${Math.round(spending.smallPurchases.amount).toLocaleString("en-US")} ব্যয়`,
      why: `Anything at or below ৳${spending.smallPurchases.threshold.toLocaleString("en-US")} is easy to miss individually but material in aggregate.`,
      whyBn: `৳${spending.smallPurchases.threshold.toLocaleString("en-US")} বা তার নিচের লেনদেন আলাদাভাবে চোখে পড়ে না, কিন্তু একসাথে বড় হয়ে ওঠে।`,
      what: `That is ${(spending.smallPurchases.shareOfSpend * 100).toFixed(0)}% of this month's spending, concentrated in ${spending.smallPurchases.topCategories.map((c) => c.label).join(", ")}.`,
      whatBn: `এটি এই মাসের ${(spending.smallPurchases.shareOfSpend * 100).toFixed(0)}% ব্যয়, যার বেশির ভাগ ${spending.smallPurchases.topCategories.map((c) => c.label).join(", ")}-এ।`,
      doThis: "This is information, not a verdict — review the list and decide for yourself what matters.",
      doThisBn: "এটি তথ্য, কোনো রায় নয় — তালিকাটি দেখে আপনি নিজে সিদ্ধান্ত নিন।",
      amount: spending.smallPurchases.amount,
      route: "/spending",
      evidence: spending.evidence,
    });
  }

  // 5. Unusual transaction.
  const topHit = anomaly.hits[0];
  if (topHit && topHit.score > anomaly.threshold * 1.15) {
    items.push({
      id: "action_anomaly",
      rank: 0,
      priority: "watch",
      kind: "spending",
      severity: topHit.knownPattern ? "high" : "medium",
      title: `Unusual: ৳${Math.round(topHit.transaction.amount).toLocaleString("en-US")} ${topHit.transaction.category} on ${topHit.transaction.timestamp.slice(0, 10)}`,
      titleBn: `অস্বাভাবিক: ${topHit.transaction.timestamp.slice(0, 10)} তারিখে ${topHit.transaction.category}-এ ৳${Math.round(topHit.transaction.amount).toLocaleString("en-US")}`,
      why: topHit.reasons.map((r) => r.label).slice(0, 3).join("; "),
      whyBn: topHit.reasons.map((r) => r.label).slice(0, 3).join("; "),
      what: `The isolation forest scored it ${topHit.score} against a ${anomaly.threshold} threshold, because it does not look like this category's usual behaviour.`,
      whatBn: `এই খাতের স্বাভাবিক আচরণের সঙ্গে মিল না থাকায় আইসোলেশন ফরেস্ট স্কোর দিয়েছে ${topHit.score}, সীমা ${anomaly.threshold}।`,
      doThis: topHit.knownPattern
        ? "The dataset confirms this was an injected anomaly. Review it in the Evaluation page."
        : "If this was not you, review the transaction on the Spending page.",
      doThisBn: topHit.knownPattern
        ? "ডেটাসেট নিশ্চিত করেছে এটি ইনজেক্টেড অস্বাভাবিক। Evaluation পেজে দেখুন।"
        : "এটি আপনার না হলে Spending পেজে লেনদেনটি দেখুন।",
      amount: topHit.transaction.amount,
      route: "/spending",
      evidence: anomaly.evidence,
    });
  }

  // 6. Emergency buffer.
  if (emergency.monthsOfCoverNow < emergency.monthsTarget) {
    items.push({
      id: "action_emergency",
      rank: 0,
      priority: emergency.monthsOfCoverNow < 1 ? "do-now" : "plan",
      kind: "risk",
      severity: emergency.monthsOfCoverNow < 1 ? "high" : "medium",
      title: `Emergency buffer covers ${emergency.monthsOfCoverNow.toFixed(1)} of ${emergency.monthsTarget} months`,
      titleBn: `জরুরি রিজার্ভ ${emergency.monthsTarget} মাসের মধ্যে ${emergency.monthsOfCoverNow.toFixed(1)} মাসই আছে`,
      why: `Essential monthly spend for this household is estimated at ৳${emergency.essentialMonthly.toLocaleString("en-US")}.`,
      whyBn: `এই পরিবারের প্রয়োজনীয় মাসিক ব্যয় আনুমানিক ৳${emergency.essentialMonthly.toLocaleString("en-US")}।`,
      what: `Still to fund: ৳${emergency.remaining.toLocaleString("en-US")}. At ৳${emergency.monthlyToFund.toLocaleString("en-US")}/month that is about ${emergency.monthsToFund} month(s).`,
      whatBn: `আর জমাতে হবে ৳${emergency.remaining.toLocaleString("en-US")}। মাসে ৳${emergency.monthlyToFund.toLocaleString("en-US")} জমালে প্রায় ${emergency.monthsToFund} মাস লাগবে।`,
      doThis: "Change the multiplier on the Emergency Fund page to see how the target moves.",
      doThisBn: "জরুরি তহবিল পেজে গুণক বদলে লক্ষ্য কীভাবে বদলায় তা দেখুন।",
      amount: emergency.remaining,
      route: "/emergency-fund",
      evidence: emergency.evidence,
    });
  }

  // 7. Cash dependency.
  if (cash.shareOfSpend > 0.35) {
    items.push({
      id: "action_cash_dependency",
      rank: 0,
      priority: "watch",
      kind: "learning",
      severity: "low",
      title: `${(cash.shareOfSpend * 100).toFixed(0)}% of spending is invisible to the forecast`,
      titleBn: `ব্যয়ের ${(cash.shareOfSpend * 100).toFixed(0)}% ফোরকাস্টের চোখের বাইরে`,
      why: `${cash.cashOutCount} cash-outs totalled ৳${Math.round(cash.cashOutTotal).toLocaleString("en-US")}${cash.daysAfterIncomeMedian !== null ? `, typically ${cash.daysAfterIncomeMedian} day(s) after money arrives` : ""}.`,
      whyBn: `${cash.cashOutCount} বার নগদ বের হয়ে ৳${Math.round(cash.cashOutTotal).toLocaleString("en-US")}${cash.daysAfterIncomeMedian !== null ? `, সাধারণত টাকা আসার ${cash.daysAfterIncomeMedian} দিন পর` : ""}।`,
      what: `Cash mostly funds ${cash.topCashCategories.slice(0, 3).map((c) => c.label).join(", ") || "a few categories"}.`,
      whatBn: `নগদে বেশি ব্যয় হয় ${cash.topCashCategories.slice(0, 3).map((c) => c.label).join(", ") || "কয়েকটি খাতে"}।`,
      doThis: "Review which of those genuinely need cash. Keep a small cash float if it helps.",
      doThisBn: "কোনগুলোর জন্য সত্যিই নগদ দরকার তা দেখুন। সাহায্য হলে অল্প নগদ রাখতে পারেন।",
      amount: cash.cashOutTotal,
      route: "/cash-out",
      evidence: cash.evidence,
    });
  }

  // 8. Health strengths — always show what is working.
  const strength = health.positives[0];
  if (strength) {
    items.push({
      id: "action_positive",
      rank: 0,
      priority: "watch",
      kind: "positive",
      severity: "low",
      title: `${strength.label} is holding at ${strength.value}/100`,
      titleBn: `${strength.labelBn} ${strength.value}/100 ভালো অবস্থায় আছে`,
      why: strength.detail,
      whyBn: strength.detail,
      what: "This dimension contributes the most positive points to your health score.",
      whatBn: "এই মাত্রাটি আপনার স্বাস্থ্য স্কোরে সবচেয়ে বেশি ইতিবাচক অবদান রাখছে।",
      doThis: "Keep it — it is the thing most worth protecting.",
      doThisBn: "এটি ধরে রাখুন — এটিই সবচেয়ে সুরক্ষা করার মতো অংশ।",
      route: "/health",
      evidence: health.evidence,
    });
  }

  const ranked = items
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] || PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
    .slice(0, 6)
    .map((item, i) => ({ ...item, rank: i + 1 }));

  return ranked;
}

/** Insight cards for the dashboard: shorter, warmer, insight-oriented. */
export function runInsights(ctx: UserContext): Insight[] {
  const health = runHealthEngine(ctx);
  const shortage = runShortageEngine(ctx);
  const risk = shortageRiskBand(ctx);
  const out: Insight[] = [];

  if (risk === "high" || risk === "elevated") {
    out.push({
      id: "insight_shortage",
      kind: "warning",
      severity: risk === "high" ? "high" : "medium",
      title: `Spending climbs in the final 10 days`,
      titleBn: "মাসের শেষ ১০ দিনে ব্যয় বাড়ে",
      body: `${(shortage.lateShare * 100).toFixed(0)}% of this month's spending happened after day 20, led by ${shortage.contributors.slice(0, 2).map((c) => c.category).join(" and ") || "a few categories"}. That pattern usually means a low balance just before the next income.`,
      bodyBn: `এই মাসের ${(shortage.lateShare * 100).toFixed(0)}% ব্যয় ২০ তারিখের পরে হয়েছে, প্রধানত ${shortage.contributors.slice(0, 2).map((c) => c.category).join(" ও ")} থেকে। এই প্যাটার্ন সাধারণত পরবর্তী আয়ের আগে কম ব্যালেন্সের কারণ হয়।`,
      engine: "End-of-Month Shortage Predictor",
      evidence: shortage.evidence,
    });
  }

  const savingsDim = health.dimensions.find((d) => d.key === "savings_behaviour");
  if (health.score >= 65 && savingsDim) {
    out.push({
      id: "insight_positive",
      kind: "positive",
      severity: "low",
      title: `Savings behaviour is ${bandWord(savingsDim.value)}`,
      titleBn: `সঞ্চয় আচরণ ${bandWordBn(savingsDim.value)}`,
      body: `Across ${ctx.monthly.length} months you kept about ${((ctx.monthlyIncomeAvg - ctx.monthlySpendAvg) / Math.max(1, ctx.monthlyIncomeAvg) * 100).toFixed(0)}% of income, which is the strongest contributor to your health score.`,
      bodyBn: `${ctx.monthly.length} মাসে আয়ের প্রায় ${((ctx.monthlyIncomeAvg - ctx.monthlySpendAvg) / Math.max(1, ctx.monthlyIncomeAvg) * 100).toFixed(0)}% সঞ্চয় করেছেন, যা আপনার স্বাস্থ্য স্কোরে সবচেয়ে বড় অবদান রাখছে।`,
      engine: "Financial Health Engine",
      evidence: health.evidence,
    });
  }

  if (health.concerns[0]) {
    const concern = health.concerns[0];
    out.push({
      id: `insight_${concern.key}`,
      kind: "warning",
      severity: concern.value < 35 ? "high" : "medium",
      title: `${concern.label} needs attention`,
      titleBn: `${concern.labelBn} নজর দেওয়ার দরকার`,
      body: concern.detail,
      bodyBn: concern.detail,
      engine: "Financial Health Engine",
      evidence: health.evidence,
    });
  }

  return out;
}

function titleise(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function bandWord(value: number): string {
  if (value >= 80) return "strong";
  if (value >= 60) return "healthy";
  if (value >= 40) return "inconsistent";
  return "weak";
}

function bandWordBn(value: number): string {
  if (value >= 80) return "শক্তিশালী";
  if (value >= 60) return "সুস্থ";
  if (value >= 40) return "অনিয়মিত";
  return "দুর্বল";
}