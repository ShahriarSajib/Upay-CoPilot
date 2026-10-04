/**
 * Domain types for the upay Financial Life Copilot frontend.
 *
 * These mirror `data/schema/*.csv` in the repository. Columnar JSON exported by
 * `scripts/export_frontend_snapshot.py` is decoded into these shapes at load time.
 */

export type Lang = "en" | "bn";

export type Direction = "inflow" | "outflow";

export type Persona =
  | "stable_saver"
  | "end_month_shortage"
  | "irregular_income"
  | "high_cash_dependency"
  | "goal_oriented"
  | "seasonal_spender"
  | "sudden_anomaly"
  | "financial_pressure";

export interface User {
  user_id: string;
  age_group: string;
  occupation: string;
  location_type: string;
  account_age_days: number;
  /** Ground truth from the generator. Evaluation screens only — never a model input. */
  persona: Persona;
  monthly_income_base: number;
  target_savings_rate: number;
}

export type WalletType = "upay" | "bank" | "cash" | "other_digital";

export interface Wallet {
  wallet_id: string;
  user_id: string;
  wallet_type: WalletType;
  opening_balance: number;
}

export interface IncomeEvent {
  income_id: string;
  user_id: string;
  timestamp: string;
  income_type: string;
  amount: number;
  regularity: string;
  source: string;
}

export interface RecurringExpense {
  recurring_id: string;
  user_id: string;
  expense_name: string;
  category: string;
  amount: number;
  frequency: string;
  next_due_date: string;
  mandatory: boolean;
  due_day: number;
}

export interface Transaction {
  transaction_id: string;
  user_id: string;
  wallet_id: string;
  timestamp: string;
  transaction_type: string;
  direction: Direction;
  amount: number;
  category: string;
  subcategory: string;
  merchant_type: string;
  channel: string;
  cash_out: boolean;
  balance_after: number;
  fee_amount: number;
  /** Ground truth. Evaluation only. */
  is_anomaly: boolean;
  /** Ground truth. Evaluation only. */
  pattern_type: string;
}

export interface FinancialGoal {
  goal_id: string;
  user_id: string;
  goal_name: string;
  target_amount: number;
  current_amount: number;
  target_date: string;
  priority: "high" | "medium" | "low";
  created_date: string;
  horizon_months: number;
}

export interface GoalContribution {
  contribution_id: string;
  goal_id: string;
  user_id: string;
  timestamp: string;
  amount: number;
}

export interface FinancialProfile {
  user_id: string;
  monthly_income_avg: number;
  monthly_expense_avg: number;
  average_monthly_savings: number;
  savings_rate: number;
  income_stability: number;
  cash_dependency: number;
  emergency_fund_months: number;
}

export interface BehaviourLabel {
  user_id: string;
  period: string;
  end_month_shortage_label: number;
  high_cash_dependency_label: number;
  irregular_income_label: number;
  overspending_label: number;
  goal_progress_label: number;
  financial_pressure_label: number;
  anomaly_count: number;
}

export interface InjectedPattern {
  user_id: string;
  period: string;
  pattern_type: string;
  amount: number;
  category: string;
  timestamp: string;
  transaction_id: string;
}

export interface Snapshot {
  meta: {
    source: string;
    exported_by: string;
    currency: string;
    note: string;
    window_start: string;
    window_end: string;
    label_columns: string[];
  };
  cohort: string[];
  tables: Record<string, { columns: string[]; rows: unknown[][] }>;
}

/* ------------------------------------------------------------------ *
 * Engine output types
 * ------------------------------------------------------------------ */

/** Every number shown to the customer carries an evidence trail. */
export interface EvidenceItem {
  id: string;
  label: string;
  value: number | string;
  unit?: "bdt" | "percent" | "ratio" | "count" | "days" | "months" | "text";
  detail?: string;
  source: string;
}

export interface Evidence {
  engine: string;
  headline: string;
  confidence: number;
  confidenceNote: string;
  metrics: EvidenceItem[];
  reasons: { polarity: "positive" | "negative" | "neutral"; text: string; weight?: number }[];
  assumptions: string[];
  sources: string[];
  /** For evaluated engines: measured accuracy against the generator's ground truth. */
  evaluation?: { metric: string; value: number; unit: string }[];
}

export interface ScoreBand {
  score: number;
  band: "strong" | "good" | "moderate" | "weak" | "critical";
}

export interface Dimension {
  key: string;
  label: string;
  labelBn: string;
  value: number;
  /** 0..1 — how much this dimension pulled the composite score up or down. */
  contribution: number;
  detail: string;
}

export interface Insight {
  id: string;
  kind: "warning" | "positive" | "info" | "action";
  severity: "high" | "medium" | "low";
  title: string;
  titleBn: string;
  body: string;
  bodyBn: string;
  engine: string;
  evidence: Evidence;
}

export interface AnomalyHit {
  transaction: Transaction;
  score: number;
  reasons: { label: string; value: number; z: number }[];
  knownPattern: boolean;
}

export interface ForecastPoint {
  date: string;
  dayOfMonth: number;
  balance: number;
  income: number;
  expense: number;
  lower: number;
  upper: number;
  recurringDue: number;
  belowBuffer: boolean;
}

export interface Forecast {
  points: ForecastPoint[];
  horizonDays: number;
  expectedIncome: number;
  expectedExpense: number;
  expectedEndingBalance: number;
  buffer: number;
  minBalance: number;
  minBalanceDate: string | null;
  lowBalanceWindows: { from: string; to: string; probability: number }[];
  confidence: number;
  method: string;
  baseline: { expectedEndingBalance: number; mae: number };
  evidence: Evidence;
}

export interface GoalPlanScenario {
  key: "conservative" | "balanced" | "aggressive";
  label: string;
  labelBn: string;
  monthlyContribution: number;
  shortfall: number;
  targetDate: string | null;
  achievable: boolean;
  probability: number;
  minBalance: number;
  bufferBreached: boolean;
  tradeoff: string;
  tradeoffBn: string;
}

export interface GoalFeasibility {
  goal: FinancialGoal;
  requiredMonthly: number;
  estimatedCapacity: number;
  shortfall: number;
  probability: number;
  monthsLeft: number;
  scenarios: GoalPlanScenario[];
  verdict: "on_track" | "tight" | "at_risk" | "infeasible";
  evidence: Evidence;
}

export interface SimulationScenario {
  monthlySavingChange: number;
  incomeChangePercent: number;
  expenseChange: number;
  unexpectedExpense: number;
  buffer: number;
}

export interface SimulationResult {
  baseline: SimulationOutcome;
  scenario: SimulationOutcome;
  goalDateShiftMonths: number | null;
  riskLevel: "low" | "moderate" | "elevated" | "high";
  balanceDelta: number;
  firstShortfallMonth: string | null;
  explanation: { en: string; bn: string }[];
  series: { date: string; baseline: number; scenario: number }[];
  evidence: Evidence;
}

export interface SimulationOutcome {
  monthlySaving: number;
  totalSaved: number;
  endingBalance: number;
  minBalance: number;
  goalDate: string | null;
  shortfall: number;
}

export interface LiteracyTopic {
  id: string;
  title: string;
  titleBn: string;
  hook: string;
  hookBn: string;
  minutes: number;
  triggerLabel: string;
  triggerLabelBn: string;
  sections: { heading: string; headingBn: string; body: string; bodyBn: string }[];
  quiz: {
    question: string;
    questionBn: string;
    options: { en: string; bn: string }[];
    answer: number;
    explain: string;
    explainBn: string;
  };
  relatedSignal: string;
}

export interface RngNote {
  term: string;
  evidence: string;
  source: string;
}

export interface ToolCallTrace {
  tool: string;
  args: Record<string, unknown>;
  durationMs: number;
  ok: boolean;
}

export interface AssistantTurn {
  id: string;
  role: "user" | "copilot";
  text: string;
  lang: Lang;
  detectedIntent?: string;
  intentConfidence?: number;
  normalized?: string;
  traces?: ToolCallTrace[];
  evidence?: Evidence[];
  blocked?: boolean;
  createdAt: number;
}