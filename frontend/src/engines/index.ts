import type { UserContext } from "@/data/context";
import { runHealthEngine, type HealthResult } from "./health";
import { runSpendingEngine, type SpendingResult } from "./spending";
import { runAnomalyEngine, type AnomalyResult } from "./anomaly";
import { runForecast, backtestForecast, monthEndProjection, type BacktestResult } from "./forecast";
import {
  compareLabels,
  runShortageEngine,
  shortageRiskBand,
  type LabelAgreement,
  type ShortageResult,
} from "./behaviour";
import {
  goalPortfolioSummary,
  optimiseGoalAllocation,
  type AllocationPlan,
  type CapacityPlan,
  type GoalFeasibility,
} from "./goals";
import { runEmergencyPlanner, type EmergencyPlan } from "./emergency";
import { runCashOutEngine, runSourceEngine, type CashOutResult, type SourceResult } from "./cashout";
import { runResilienceEngine, type ResilienceResult } from "./resilience";
import { runReadinessEngine, type ReadinessResult } from "./credit";
import { runLiteracyEngine, type LiteracyRecommendation } from "./literacy";
import { runActionCentre, runInsights, type ActionItem } from "./insights";
import { runBillsEngine, type BillsResult } from "./bills";

/**
 * Financial Context Engine (assembly layer)
 * ---------------------------------------------------------------------------
 * Runs every engine once per selected customer and hands the pages a single
 * immutable object. This is the "Financial Context Engine" block in the
 * architecture diagram; no page reaches the raw dataset directly.
 */

export interface CopilotBundle {
  ctx: UserContext;
  health: HealthResult;
  spending: SpendingResult;
  anomaly: AnomalyResult;
  forecast30: ReturnType<typeof runForecast>;
  forecast90: ReturnType<typeof runForecast>;
  monthEnd: ReturnType<typeof monthEndProjection>;
  bills: BillsResult;
  shortage: ShortageResult;
  shortageRisk: ReturnType<typeof shortageRiskBand>;
  goals: ReturnType<typeof goalPortfolioSummary>;
  feasibility: Record<string, GoalFeasibility>;
  allocations: AllocationPlan[];
  capacity: CapacityPlan;
  emergency: EmergencyPlan;
  cashOut: CashOutResult;
  sources: SourceResult;
  resilience: ResilienceResult;
  readiness: ReadinessResult;
  literacy: LiteracyRecommendation[];
  actions: ActionItem[];
  insights: ReturnType<typeof runInsights>;
  backtest: BacktestResult;
  labelAgreement: LabelAgreement;
}

export function buildBundle(ctx: UserContext): CopilotBundle {
  const goals = goalPortfolioSummary(ctx);
  const feasibility: Record<string, GoalFeasibility> = {};
  for (const f of goals.feasibility) feasibility[f.goal.goal_id] = f;

  return {
    ctx,
    health: runHealthEngine(ctx),
    spending: runSpendingEngine(ctx),
    anomaly: runAnomalyEngine(ctx),
    forecast30: runForecast(ctx, 30),
    forecast90: runForecast(ctx, 90),
    monthEnd: monthEndProjection(ctx),
    bills: runBillsEngine(ctx),
    shortage: runShortageEngine(ctx),
    shortageRisk: shortageRiskBand(ctx),
    goals,
    feasibility,
    allocations: optimiseGoalAllocation(ctx),
    capacity: goals.capacity,
    emergency: runEmergencyPlanner(ctx),
    cashOut: runCashOutEngine(ctx),
    sources: runSourceEngine(ctx),
    resilience: runResilienceEngine(ctx),
    readiness: runReadinessEngine(ctx),
    literacy: runLiteracyEngine(ctx),
    actions: runActionCentre(ctx),
    insights: runInsights(ctx),
    backtest: backtestForecast(ctx),
    labelAgreement: compareLabels(ctx),
  };
}

export type {
  HealthResult,
  SpendingResult,
  AnomalyResult,
  BacktestResult,
  ShortageResult,
  LabelAgreement,
  GoalFeasibility,
  AllocationPlan,
  CapacityPlan,
  EmergencyPlan,
  CashOutResult,
  SourceResult,
  ResilienceResult,
  ReadinessResult,
  LiteracyRecommendation,
  ActionItem,
  BillsResult,
};