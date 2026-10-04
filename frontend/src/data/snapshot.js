import { apiBase } from "./auth";
const SNAPSHOT_URL = `${apiBase()}/api/dataset`;
const TOKEN_KEY = "upay.copilot.token";
/** Decode the columnar encoding written by scripts/export_frontend_snapshot.py. */
function decode(table) {
    if (!table)
        return [];
    if (Array.isArray(table))
        return table;
    const { columns, rows } = table;
    return rows.map((row) => {
        const obj = {};
        columns.forEach((col, i) => {
            obj[col] = row[i];
        });
        return obj;
    });
}
let cache = null;
export async function loadDataset(signal) {
    if (cache)
        return cache;
    const token = localStorage.getItem(TOKEN_KEY);
    const res = await fetch(SNAPSHOT_URL, {
        ...(signal ? { signal } : {}),
        headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
        throw new Error(`Could not load the authenticated dataset (${res.status}).`);
    }
    const json = (await res.json());
    const t = json.tables;
    cache = {
        meta: json.meta,
        cohort: json.cohort,
        users: decode(t.users),
        wallets: decode(t.wallets),
        transactions: decode(t.transactions)
            .filter((row) => row && row.transaction_id)
            .map((row) => ({ ...row, timestamp: String(row.timestamp) }))
            .sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
        incomeEvents: decode(t.income_events)
            .filter((row) => row && row.income_id)
            .map((row) => ({ ...row, timestamp: String(row.timestamp) })),
        recurring: decode(t.recurring_expenses).filter((r) => r && r.recurring_id),
        goals: decode(t.financial_goals).filter((g) => g && g.goal_id),
        contributions: decode(t.goal_contributions).filter((c) => c && c.contribution_id),
        profiles: decode(t.financial_profiles).filter((p) => p && p.user_id),
        labels: decode(t.behavior_labels).filter((l) => l && l.user_id),
        patterns: decode(t.injected_patterns).filter((p) => p && p.user_id),
    };
    return cache;
}
