import type {
  BehaviourLabel,
  FinancialGoal,
  FinancialProfile,
  GoalContribution,
  IncomeEvent,
  InjectedPattern,
  RecurringExpense,
  Snapshot,
  Transaction,
  User,
  Wallet,
} from "@/types";
import { apiBase } from "./auth";

const SNAPSHOT_URL = `${apiBase()}/api/dataset`;
const TOKEN_KEY = "upay.copilot.token";

export interface Dataset {
  meta: Snapshot["meta"];
  cohort: string[];
  users: User[];
  wallets: Wallet[];
  transactions: Transaction[];
  incomeEvents: IncomeEvent[];
  recurring: RecurringExpense[];
  goals: FinancialGoal[];
  contributions: GoalContribution[];
  profiles: FinancialProfile[];
  labels: BehaviourLabel[];
  patterns: InjectedPattern[];
}

/** Decode the columnar encoding written by scripts/export_frontend_snapshot.py. */
function decode<T>(table: { columns: string[]; rows: unknown[][] } | T[] | undefined): T[] {
  if (!table) return [];
  if (Array.isArray(table)) return table;
  const { columns, rows } = table;
  return rows.map((row) => {
    const obj: Record<string, unknown> = {};
    columns.forEach((col, i) => {
      obj[col] = row[i];
    });
    return obj as T;
  });
}

let cache: Dataset | null = null;

export function invalidateDatasetCache() {
  cache = null;
}

export async function loadDataset(signal?: AbortSignal, forceReload = false): Promise<Dataset> {
  if (cache && !forceReload) return cache;
  const token = localStorage.getItem(TOKEN_KEY);
  let json: Snapshot | null = null;

  try {
    const res = await fetch(SNAPSHOT_URL, {
      ...(signal ? { signal } : {}),
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) {
      json = (await res.json()) as Snapshot;
    }
  } catch {
    // Backend fetch failed; will attempt fallback
  }

  if (!json) {
    const fallbackRes = await fetch("/data/snapshot.json", {
      ...(signal ? { signal } : {}),
    });
    if (!fallbackRes.ok) {
      throw new Error(`Could not load dataset from server or static snapshot.`);
    }
    json = (await fallbackRes.json()) as Snapshot;
  }

  const t = json.tables;

  cache = {
    meta: json.meta,
    cohort: json.cohort,
    users: decode<User>(t.users),
    wallets: decode<Wallet>(t.wallets),
    transactions: decode<Transaction>(t.transactions)
      .filter((row) => row && row.transaction_id)
      .map((row) => ({ ...row, timestamp: String(row.timestamp) }))
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
    incomeEvents: decode<IncomeEvent>(t.income_events)
      .filter((row) => row && row.income_id)
      .map((row) => ({ ...row, timestamp: String(row.timestamp) })),
    recurring: decode<RecurringExpense>(t.recurring_expenses).filter((r) => r && r.recurring_id),
    goals: decode<FinancialGoal>(t.financial_goals).filter((g) => g && g.goal_id),
    contributions: decode<GoalContribution>(t.goal_contributions).filter((c) => c && c.contribution_id),
    profiles: decode<FinancialProfile>(t.financial_profiles).filter((p) => p && p.user_id),
    labels: decode<BehaviourLabel>(t.behavior_labels).filter((l) => l && l.user_id),
    patterns: decode<InjectedPattern>(t.injected_patterns).filter((p) => p && p.user_id),
  };
  return cache;
}