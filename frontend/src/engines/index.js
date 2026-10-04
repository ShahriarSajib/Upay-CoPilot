import { runHealthEngine } from "./health";
import { runSpendingEngine } from "./spending";
import { runAnomalyEngine } from "./anomaly";
import { runForecast, backtestForecast, monthEndProjection } from "./forecast";
import { compareLabels, runShortageEngine, shortageRiskBand, } from "./behaviour";
import { goalPortfolioSummary, optimiseGoalAllocation, } from "./goals";
import { runEmergencyPlanner } from "./emergency";
import { runCashOutEngine, runSourceEngine } from "./cashout";
import { runResilienceEngine } from "./resilience";
import { runReadinessEngine } from "./credit";
import { runLiteracyEngine } from "./literacy";
import { runActionCentre, runInsights } from "./insights";
import { runBillsEngine } from "./bills";
export function buildBundle(ctx) {
    const goals = goalPortfolioSummary(ctx);
    const feasibility = {};
    for (const f of goals.feasibility)
        feasibility[f.goal.goal_id] = f;
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
