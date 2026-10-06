"""Generate the compact 50-user development dataset.

The full population (500 users / ~191k transactions) is the right dataset for
offline evaluation but too slow to iterate against while building an API and a
UI. This script produces a development dataset that keeps **every generator,
persona, invariant and validation rule identical** and changes only the
population size and the transaction volume, so a bug found here is a real bug.

    python scripts/generate_dev_dataset.py

Outputs ``data/dev/*.csv`` plus chronological ``data/dev_{train,validation,test}``
splits, and fails loudly if the dataset exceeds the row budget or breaks any
schema, ledger, vocabulary or leakage rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from ml.dataset.config import (  # noqa: E402
    DEV_MONTHS,
    DEV_NUM_USERS,
    DEV_OUTPUT_DIR,
    DEV_SPLIT_DIRS,
    DEV_SPLIT_ROOT,
    DEV_TRANSACTION_VOLUME,
    SEED,
)
from ml.dataset.leakage import render, run_leakage_check  # noqa: E402
from ml.dataset.pipeline import TABLE_ORDER, generate_all  # noqa: E402
from ml.dataset.validation import validate  # noqa: E402

# Hard ceiling for the development dataset, as agreed for iteration speed.
ROW_BUDGET = 10_000


def main() -> int:
    tables = generate_all(
        seed=SEED,
        num_users=DEV_NUM_USERS,
        months_count=DEV_MONTHS,
        output_dir=DEV_OUTPUT_DIR,
        split_dirs=DEV_SPLIT_DIRS,
        named=True,
        volume_scale=DEV_TRANSACTION_VOLUME,
    )

    print("\n" + "=" * 70)
    print("ROW BUDGET")
    print("=" * 70)
    total = 0
    for name in TABLE_ORDER:
        rows = len(tables[name])
        total += rows
        print(f"  {name:24s} {rows:6d}")
    print(f"  {'TOTAL':24s} {total:6d}  (budget {ROW_BUDGET:,})")

    if total > ROW_BUDGET:
        print(f"\nFAIL: dataset is {total:,} rows, over the {ROW_BUDGET:,} budget.")
        print("      Lower DEV_TRANSACTION_VOLUME or DEV_NUM_USERS in ml/dataset/config.py.")
        return 1

    # Every persona must be represented, otherwise a behaviour cannot be demoed.
    personas = tables["users"]["persona"].value_counts().to_dict()
    print("\n" + "=" * 70)
    print("PERSONA COVERAGE")
    print("=" * 70)
    for persona, count in sorted(personas.items()):
        print(f"  {persona:24s} {count:3d} users")
    if len(personas) < 8:
        print(f"\nFAIL: only {len(personas)}/8 personas present in the dev population.")
        return 1

    print("\n" + "=" * 70)
    print("IDENTITIES (first 10)")
    print("=" * 70)
    print(tables["users"][["user_id", "full_name", "name_bn", "persona"]].head(10).to_string(index=False))

    print("\n" + "=" * 70)
    print("SCHEMA / LEDGER / VOCABULARY VALIDATION")
    print("=" * 70)
    report = validate(tables, ROOT / "data" / "schema")
    print(report.render())
    if not report.passed:
        print("\nFAIL: validation errors above.")
        return 1

    print("\n" + "=" * 70)
    print("LEAKAGE CHECK")
    print("=" * 70)
    violations = run_leakage_check(ROOT / DEV_SPLIT_ROOT, tables)
    print(render(violations))
    if violations:
        print("\nFAIL: leakage violations above.")
        return 1

    tx = tables["transactions"]
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  users            {tables['users']['user_id'].nunique()}")
    print(f"  wallets          {tables['wallets']['wallet_id'].nunique()}")
    print(f"  transactions     {len(tx):,}  ({len(tx) / max(tables['users']['user_id'].nunique(), 1):.0f}/user)")
    print(f"  per user/month   {len(tx) / 50 / DEV_MONTHS:.1f}")
    print(f"  income events    {len(tables['income_events']):,}")
    print(f"  recurring        {len(tables['recurring_expenses']):,}")
    print(f"  goals            {len(tables['financial_goals']):,}")
    print(f"  contributions    {len(tables['goal_contributions']):,}")
    print(f"  window            {tx['timestamp'].min()} .. {tx['timestamp'].max()}")
    print(f"  injected patterns {len(tables['injected_patterns']):,}")
    print(f"\nDev dataset ready at {DEV_OUTPUT_DIR}/")

    summary = pd.DataFrame(
        [{"table": name, "rows": len(tables[name])} for name in TABLE_ORDER]
    )
    summary.to_csv(ROOT / DEV_OUTPUT_DIR / "row_budget.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())