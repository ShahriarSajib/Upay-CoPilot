# Dataset Split

The split is **strictly temporal**. No row is ever assigned by chance, so a
model can never be evaluated on a period that precedes its training data.

| Split | Periods | Months | Rows (transactions) | Share |
| --- | --- | --- | --- | --- |
| Train | 2026-01 .. 2026-05 | 5 | 87,891 | 55.7% |
| Validation | 2026-06 .. 2026-07 | 2 | 34,870 | 22.1% |
| Test | 2026-08 .. 2026-09 | 2 | 35,021 | 22.2% |

Split periods are defined in `SPLIT_PERIODS` in `ml/dataset/splits.py`.

## Layout

Each split is written as `data/<split>/features/` and `data/<split>/labels/`:

```
data/train/features/     users.csv  wallets.csv  income_events.csv
                         recurring_expenses.csv  transactions.csv
                         financial_goals.csv  goal_contributions.csv
data/train/labels/       behavior_labels.csv  injected_patterns.csv
                         financial_profiles.csv
```

`users.csv` and `wallets.csv` are dimensions rather than time series, so they are
copied into every split with ground-truth columns stripped.

## Row counts

| Table | Side | Train | Validation | Test | Total |
| --- | --- | --- | --- | --- | --- |
| `income_events` | features | 3,908 | 1,495 | 1,536 | 6,939 |
| `recurring_expenses` | features | 1,399 | 1,399 | 1,399 | 1,399 |
| `transactions` | features | 87,891 | 34,870 | 35,021 | 157,782 |
| `financial_goals` | features | 542 | 542 | 542 | 542 |
| `goal_contributions` | features | 1,570 | 579 | 544 | 2,693 |
| `financial_profiles` | labels | 500 | 500 | 500 | 500 |
| `behavior_labels` | labels | 4,500 | 4,500 | 4,500 | 4,500 |
| `injected_patterns` | labels | 408 | 180 | 167 | 755 |

`recurring_expenses`, `financial_goals`, `financial_profiles` and
`behavior_labels` are not time-scoped tables, so they appear in full in each
split. For the first two that is intentional: a goal's existence and its
standing obligations are legitimate prior information. For `financial_profiles`
and `behavior_labels` they are on the label side for the reason below.

## What is kept out of the features

Three classes of column are removed from every feature file. This is enforced by
`ml/dataset/splits.py` and re-checked by `scripts/leakage_check.py`.

**1. Ground truth (the answer itself)**

`persona`, `is_anomaly`, `pattern_type`, and the generator knobs
`monthly_income_base`, `expense_ratio`, `income_cv`, `cash_out_rate`,
`digital_ratio`, `target_savings_rate`, `goal_count`, `anomaly_rate`. These
determine the outcome by construction, so using them is cheating.

**2. Label columns**

`end_month_shortage_label`, `high_cash_dependency_label`,
`irregular_income_label`, `overspending_label`, `goal_progress_label`,
`financial_pressure_label`, `anomaly_count`. These live in
`<split>/labels/behavior_labels.csv`.

**3. Whole-window aggregates (time leakage)**

`financial_profiles.csv`, plus `current_amount`, `progress_ratio` and
`is_achieved` on `financial_goals`. These are correct in `data/generated/` but
wrong as features: they aggregate the entire window including the test period, so
using them to predict January would leak September into the model. The profile
table is therefore written to `labels/` in each split, and the three goal columns
are dropped from the feature file.

Note that `recurring_id` **is** kept: it is a real foreign key observable at
transaction time, not an answer.

## Guarantees checked by `scripts/leakage_check.py`

- No ground-truth or whole-window column appears in any `features/` file.
- `behavior_labels.csv` and `injected_patterns.csv` exist only under `labels/`.
- Every split contains only its own periods.
- No `transaction_id` appears in more than one split.
- Splits are strictly chronological: `validation` starts after `train` ends, and
  `test` starts after `validation` ends.

Each guarantee has a unit test in `tests/test_dataset.py`, including a test that
injects a `persona` column and asserts the leakage check catches it.

## Using the split

```python
import pandas as pd

features = pd.read_csv("data/train/features/transactions.csv", parse_dates=["timestamp"])
labels = pd.read_csv("data/train/labels/behavior_labels.csv")
merged = features.merge(labels, on=["user_id", "period"], how="inner")
```

Keep `features/` and `labels/` as separate directories. Merging them into one
frame before fitting is the most common way this split gets undone.