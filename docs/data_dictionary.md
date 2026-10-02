# Data Dictionary

Synthetic financial behaviour dataset for Upay-CoPilot. All data is **entirely
synthetic** and contains no real people, accounts or transactions. No PII is
generated: users have only an age band, an occupation and a location type.

Regenerate everything with:

```bash
python scripts/generate_synthetic_data.py
```

Seed `42` produces a byte-identical dataset on every run.

## Simulated world

| Property | Value |
| --- | --- |
| Users | 500 |
| Wallets | 1,159 |
| History window | 2026-01-01 to 2026-09-30 (9 months) |
| Transactions | 157,782 |
| Income events | 6,939 |
| Recurring obligations | 1,399 |
| Goals / contributions | 542 / 2,693 |
| Currency | BDT (unlabelled numeric amounts) |

## Core tables

### `users.csv` (500 rows)

The simulated population. Contains no personal data.

| Column | Type | Description |
| --- | --- | --- |
| `user_id` | string | Primary key, `U00001`-style |
| `age_group` | category | `18-24`, `25-34`, `35-44`, `45-54`, `55+` |
| `occupation` | category | `student`, `private_employee`, `business`, `freelancer`, `self_employed`, `other` |
| `location_type` | category | `urban`, `semi_urban`, `rural` |
| `account_age_days` | int | Days since the account opened; always covers the full window |

Ground-truth columns (never features, see `dataset_split.md`): `persona`,
`monthly_income_base`, `expense_ratio`, `income_cv`, `cash_out_rate`,
`digital_ratio`, `target_savings_rate`, `goal_count`, `anomaly_rate`.

### `wallets.csv` (1,159 rows)

| Column | Type | Description |
| --- | --- | --- |
| `wallet_id` | string | Primary key |
| `user_id` | FK | Owner of the wallet |
| `wallet_type` | category | `upay` (exactly one per user), `bank`, `cash`, `other_digital` |
| `opening_balance` | float | Balance before 2026-01-01, large enough to avoid any overdraft |

### `transactions.csv` (157,782 rows)

The double-entry ledger. One row per movement on one wallet.

| Column | Type | Description |
| --- | --- | --- |
| `transaction_id` | string | Primary key |
| `user_id` | FK | Redundant with `wallet_id`; used for fast grouping |
| `wallet_id` | FK | Wallet the movement happened on |
| `timestamp` | datetime | Minute-resolution local time |
| `transaction_type` | category | `payment`, `transfer`, `bill_payment`, `cash_out`, `cash_in` |
| `direction` | category | `inflow` or `outflow` |
| `amount` | float | Always strictly positive; sign comes from `direction` |
| `category` | category | 13 controlled values, see below |
| `subcategory` | category | Controlled per category, e.g. `grocery` under `food` |
| `merchant_type` | category | `merchant`, `agent`, `ecommerce`, `utility`, `person` |
| `channel` | category | `upay`, `agent`, `merchant`, `bank`, `online` |
| `cash_out` | bool | True when the movement settled from a physical cash wallet |
| `balance_after` | float | Exact running balance of that wallet; never negative |
| `recurring_id` | FK | Set when the row *is* a recurring payment |
| `is_anomaly` | bool | True for deliberately injected anomalies (ground truth) |
| `pattern_type` | string | Which anomaly was injected (ground truth) |

Categories: `food`, `transport`, `shopping`, `education`, `health`, `utilities`,
`communication`, `entertainment`, `family`, `housing`, `cash`, `transfer`,
`other`.

**Ledger invariants**, all asserted by `scripts/validate_dataset.py`:

- `balance_after = opening_balance + inflows - outflows`, chronologically, per wallet (max drift 0.0).
- `balance_after >= 0` everywhere. There is no credit facility, so an unaffordable purchase is dropped rather than overdrawing.
- A cash withdrawal always appears as a matched `cash_out`/`cash_in` pair on two wallets.
- Credited `transfer`/`inflow` total equals the `income_events` total exactly.

### `income_events.csv` (6,939 rows)

| Column | Type | Description |
| --- | --- | --- |
| `income_id` | string | Primary key |
| `user_id` | FK | Recipient |
| `timestamp` | datetime | Credit time |
| `income_type` | category | `salary`, `business`, `freelance`, `allowance`, `family_support`, `p2p` |
| `amount` | float | Gross credit |
| `regularity` | category | `regular`, `semi_regular`, `irregular` |
| `source` | category | `employer`, `own_business`, `freelance_client`, `family`, `self` |

Every row here has a matching `inflow` in `transactions.csv`, so income is never
counted twice.

### `recurring_expenses.csv` (1,399 rows)

Standing obligations. These are the *source* of the recurring rows in
`transactions.csv`, not a decorative list.

| Column | Type | Description |
| --- | --- | --- |
| `recurring_id` | string | Primary key |
| `user_id` | FK | Owner |
| `expense_name` | category | `rent`, `electricity`, `internet`, `mobile_recharge`, `tuition`, `medicine`, `family_support`, `subscription`, `insurance` |
| `category` | category | Matches the transactions category |
| `amount` | float | Nominal monthly amount |
| `frequency` | category | `monthly` |
| `next_due_date` | date | First due date after the window |
| `mandatory` | bool | Essential bill or discretionary subscription |
| `due_day` | int | Day of month the bill falls due |

## Derived tables

### `financial_goals.csv` (542 rows)

| Column | Type | Description |
| --- | --- | --- |
| `goal_id` | string | Primary key |
| `user_id` | FK | Owner |
| `goal_name` | category | `emergency_fund`, `education`, `laptop`, `phone`, `travel`, `family`, `other` |
| `target_amount` | float | Goal value |
| `current_amount` | float | Exactly `sum(goal_contributions.amount)` for this goal |
| `target_date` | date | Deadline, always on/after `created_date` |
| `priority` | category | `high`, `medium`, `low` |
| `created_date` | date | Start of the window |
| `horizon_months` | int | Months the user intended to take |
| `is_achieved` | bool | `current_amount >= target_amount` (71 of 542) |
| `progress_ratio` | float | `current_amount / target_amount` |

### `goal_contributions.csv` (2,693 rows)

| Column | Type | Description |
| --- | --- | --- |
| `contribution_id` | string | Primary key |
| `goal_id` | FK | Goal being funded |
| `user_id` | FK | Must match the goal owner |
| `timestamp` | datetime | Contribution time |
| `amount` | float | Positive, capped at the goal's remaining target |

Contributions are drawn from **observed monthly surplus**
(`income - spending` for that user-month) and are capped so they can never
exceed it. They are savings, so they are deliberately *not* booked as extra
ledger outflows: doing so would double-count money already spent.

### `financial_profiles.csv` (500 rows)

Calculated, not invented. One row per user over the whole window.

| Column | Type | Description |
| --- | --- | --- |
| `user_id` | PK | User |
| `monthly_income_avg` | float | Mean monthly inflow |
| `monthly_expense_avg` | float | Mean monthly outflow, excluding internal cash transfers |
| `average_monthly_savings` | float | Mean of `income - spend` |
| `savings_rate` | float | `average_monthly_savings / monthly_income_avg` |
| `income_stability` | float | `1 / (1 + CV of monthly income)`, 1.0 is perfectly stable |
| `cash_dependency` | float | Share of spend settled from cash wallets |
| `emergency_fund_months` | float | Liquid balance / `monthly_expense_avg` |

These are whole-window aggregates, so they are deliberately kept off the
feature side of the splits.

### `behavior_labels.csv` (4,500 rows) — ground truth

One row per user-month **with observed spending**. Labels come from fixed rules
over information available up to that period end; the persona is never read.

| Column | Type | Description |
| --- | --- | --- |
| `user_id` | FK | User |
| `period` | string | `YYYY-MM` |
| `end_month_shortage_label` | 0/1 | 26.6% positive: >40% of spend on/after day 23 |
| `high_cash_dependency_label` | 0/1 | 7.4% positive: >40% of spend from cash wallets |
| `irregular_income_label` | 0/1 | 10.0% positive: income CV > 0.35 |
| `overspending_label` | 0/1 | 15.0% positive: spending exceeded income |
| `goal_progress_label` | 0/1 | 33.9% positive: at least one contribution that month |
| `financial_pressure_label` | 0/1 | 15.0% positive: overspending **and** savings rate < 5% |
| `anomaly_count` | int | Injected anomalies for that user-month |

Thresholds live in `ml/dataset/config.py` (`LABEL_THRESHOLDS`).

### `injected_patterns.csv` (755 rows) — ground truth

Every deliberately injected anomaly, for evaluating detectors. Derived from the
surviving ledger rows, so it can never reference a dropped transaction.

| Column | Type | Description |
| --- | --- | --- |
| `user_id` | FK | User |
| `period` | string | `YYYY-MM` |
| `pattern_type` | category | `large_unplanned_charge` (184), `unusual_merchant` (190), `duplicate_charge` (179), `round_number_spike` (202) |
| `amount` | float | Amount of the anomalous transaction |
| `category` | category | Category of the anomalous transaction |
| `timestamp` | datetime | When it happened |

## Entity relationships

```
users 1---* wallets
users 1---* income_events        (each credited in transactions)
users 1---* recurring_expenses   (each drives monthly transactions)
users 1---* financial_goals      1---* goal_contributions
users 1---1 financial_profiles
wallets 1---* transactions
users  *---* behavior_labels     (per user-month)
```

Relationship between the real `users.csv` and the real `wallets.csv`: one user
has one `upay` wallet, plus optionally a `bank`, `cash` and `other_digital`
wallet. Observed mix: 500 upay, 358 bank, 191 cash, 110 other_digital.