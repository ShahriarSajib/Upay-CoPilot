# Synthetic Data Assumptions

Every number in this dataset is invented. This file records the assumptions
behind the simulation, so results are not mistaken for findings about real
people's money behaviour.

## Generation contract

- Seed `42`, 500 users, 9 months from 2026-01-01. Identical input gives a
  byte-identical dataset; verified by re-running and comparing checksums.
- Each generation stage gets its own RNG stream (`seed`, `seed+1`, ...), so
  changing one stage does not reshuffle the others.
- Amounts are stored as plain floats in BDT with no explicit unit column.

## Population

- No PII. A user is an age band, an occupation and a location type — there are
  no names, phone numbers, addresses or real account numbers anywhere.
- Income level is drawn from an occupation band, then scaled by an age
  multiplier and a location multiplier (urban 1.18x, semi_urban 1.0x, rural
  0.82x). These multipliers are **stylised**, not measured.
- Observed occupation mix: 156 private employee, 132 self employed, 83
  freelancer, 66 business, 52 other, 11 student.
- Every account is at least as old as the simulated window, so there are no
  unexplained pre-history gaps.

## Personas

Eight personas are assigned up front and act as ground truth. Observed
distribution: `stable_saver` 103, `goal_oriented` 82, `irregular_income` 68,
`high_cash_dependency` 65, `end_month_shortage` 59, `seasonal_spender` 52,
`financial_pressure` 48, `sudden_anomaly` 23.

The persona is **not** stored as a behavioural rule applied at scoring time. It
only shifts the sampling distribution of income timing, spending days,
categories, ticket sizes, cash usage, recurring reliability and anomaly rate.
The declared behaviour is therefore observable in the generated data, which is
what the validator checks:

| Persona | Observable signature |
| --- | --- |
| `stable_saver` | 17.5% of spend after day 23, lowest among all personas |
| `end_month_shortage` | 46.0% of spend after day 23, highest |
| `seasonal_spender` | 37.8% late-month spend, largest mean ticket among savers |
| `irregular_income` | Income CV roughly 5x `stable_saver` |
| `high_cash_dependency` | Highest share of spend settled in cash |
| `sudden_anomaly` | Mean ticket ~2.9k vs ~1.4-2.2k for others, 6x the anomaly rate |
| `financial_pressure` | Spends more than it earns; lowest mean ticket |
| `goal_oriented` | Highest contribution rate and goal count |

## Accounting assumptions

- **Double entry per wallet.** Every movement is on exactly one wallet, and
  `balance_after` is a true running balance recomputed in timestamp order.
  Verified drift is exactly `0.0`.
- **No overdraft and no credit.** `balance_after >= 0` always. This is a hard
  constraint from the project brief, so it has a cost: when a purchase cannot be
  funded it is **dropped**, along with its matching cash leg. In the full run
  this skipped 971 of ~158k events (0.6%), concentrated in
  `financial_pressure` personas who spend more than they earn.
  This slightly *understates* their overspending; treat their observed totals as
  a lower bound.
- Opening balances are sized as 1.0-1.4x the spending runway needed for the
  whole window, so shortfalls come from genuinely overspending users rather than
  an arbitrary starting balance.
- Cash is an internal transfer: the `cash_out` and `cash_in` legs are equal and
  appear on two wallets. They are excluded from consumption totals so spending is
  never double counted.
- Income is credited only to the `upay` wallet, and `sum(income_events.amount)`
  equals the credited `transfer`/`inflow` total exactly.
- Rounding is applied at write time to 2 decimals. Ledger checks allow a 0.01
  tolerance to absorb float representation error.

## Recurring expenses

- 1-5 standing obligations per user, drawn from a fixed catalogue and scaled to
  that user's income. Observed: mobile recharge 306, electricity 304, rent 298,
  internet 171, subscription 108, medicine 84, insurance 65, tuition 63.
- Each obligation has a `due_day`; the actual payment day jitters by +/-2 days,
  and the amount varies by ~3% (electricity also follows the seasonal curve).
- Payment reliability varies by persona: `stable_saver` misses ~2% of bills,
  `financial_pressure` ~18%.
- The transaction's `subcategory` always equals the obligation's
  `expense_name`, and `recurring_id` links the two, so the relationship is
  explicit rather than inferred. 100% of obligations have at least one linked
  payment.
- `next_due_date` is the first due date **after** the window, so the schedule
  explains the generated history without claiming to predict it.

## Seasonality

Monthly spending pressure: Jan 1.05, Feb 0.95, **Mar 1.35**, Apr 1.05, May 0.95,
Jun 1.00, Jul 1.05, Aug 1.00, Sep 0.95.

The March peak is an **approximation** of Eid al-Fitr spending. 2026 Eid al-Fitr
falls around 19-20 March; the generator does not model the exact date, lunar
calendar or any festival calendar, so this is a plausible-looking heuristic, not
a verified calendar. Do not cite it as a Bangladesh holiday fact.

## Goals and savings

- Goal counts and priorities vary by persona: `goal_oriented` holds 2-3 goals,
  several others hold 0-1.
- Contributions are taken from **observed** monthly surplus and capped at the
  goal's remaining target. Two invariants hold by construction:
  `current_amount == sum(contributions)`, and no single contribution exceeds the
  user's surplus that month. Both are unit-tested.
- Contributions represent savings, so they are **not** booked as ledger
  outflows. Bookkeeping them as spending would double-count money.
- 71 of 542 goals reach their target inside 9 months. That is deliberately
  modest: most goals are long-horizon (an emergency fund of 2-4x monthly income
  cannot be funded in 9 months from surplus alone).
- `target_date` is clamped to the end of the window so no goal is overdue in the
  data, which would make the label meaningless.

## Labels

- Labels are computed by fixed thresholds from data available up to each period
  end (`LABEL_THRESHOLDS` in `ml/dataset/config.py`). The persona assignment is
  never read when building labels.
- The persona is instead used to *evaluate* the labels, which is what makes the
  dataset useful as ground truth.
- Only user-months with observed spending receive a label row (4,500 rows), so
  there are no degenerate all-zero months.
- Thresholds are chosen to give both classes signal (7%-34% positive rate). They
  are a judgement call, not a calibrated threshold; a different competition
  objective would justify different cutoffs.

## Anomalies

Four kinds are injected: `round_number_spike` (202), `unusual_merchant` (190),
`large_unplanned_charge` (184), `duplicate_charge` (179). Mean injected ticket
is ~21.4k against ~3.3k for normal spending.

- `injected_patterns.csv` is derived from the ledger rows that actually
  survived replay, so it can never claim an anomaly that was dropped.
- Anomalies are labelled by construction, not detected by an algorithm. Real
  detectors must not be evaluated against this flag without also handling
  legitimate large purchases, which exist in the data too.

## Known limitations

1. **Opening balances are generous.** Real accounts often start near zero, which
   would produce far more dropped purchases here.
2. **No merchant identity.** `subcategory` and `merchant_type` exist but there
   is no merchant name, so merchant-level repeat detection is not possible.
3. **Categorisation is generative, not inferred.** Categories are assigned by
   the sampler, not predicted from a description, so no classifier can be
   trained on this dataset to categorise raw transactions.
4. **No transfers between users.** `p2p` income exists but the counterparty
   outflow is not simulated, so the ledger does not balance across users. It
   balances exactly per wallet, which is what the brief requires.
5. **No credit, loan, EMI or bill arrears cascade.** A missed recurring bill is
   simply absent that month; real arrears would accumulate.
6. **Personas are stylised.** They are exaggerated for learnability. Do not
   treat label rates as population estimates for Bangladesh.
7. **One currency, one locale, no inflation or exchange rate.**