# Evaluation report

Generated 2026-10-07T04:50:42+00:00 from seed `42` against `D:\diu_last\Upay-CoPilot\data` in 176.9s.

Reproduce with:

```bash
PYTHONPATH=backend python -m app.evaluation.pipeline
```

## Headline

**14 supported, 2 mixed, 4 not supported (of 20).**

| Measure | Value |
| --- | --- |
| Spend forecast vs best naive baseline | 0.38% |
| Income forecast vs best naive baseline | -2.95% |
| Anomaly detector F1 (test) | 0.5765 |
| Anomaly detector vs best naive rule | +36.8% |
| Anomalous taka put in front of the customer | 0.7612 |
| Segmentation temporal stability (ARI) | 0.9686 |
| Retrieval recall@3 | 1 |
| Guard false positives on legitimate questions | 0 |
| Live provider suite | unavailable |
| Simulation placebo moved nothing | yes |
| Customers able to follow a saving plan | 0.7 |

## Claims

Each claim states what would have to be true *before* the run; the thresholds live in `app/evaluation/pipeline.py::CLAIM_RULES`. Rows are sorted so that what did not hold appears first.

| Status | Claim | Value | Evidence |
| --- | --- | --- | --- |
| FAIL | Do next-month deficit warnings tell the customer something they do not already know? | 0 | `customer_impact.deficit_warnings.actionability.novel_warning_share` |
| FAIL | Is the share of wrongly-flagged taka small enough not to erode trust? | 0.3768 | `customer_impact.detection_value.wrongly_flagged_share_of_flagged_value` |
| FAIL | Does removing a top feature move the model the way the explanation says it will? (chance = 0.5) | 0.4547 | `explainability.aggregate.faithfulness_min_direction_agreement` |
| FAIL | Does the shipped income forecast beat the best naive baseline on the untouched test window? | -2.95 | `forecasting.summary.income.test_improvement_over_best_baseline_percent` |
| MIXED | Does the shipped spend forecast beat the best naive baseline on the untouched test window? | 0.38 | `forecasting.summary.spend.test_improvement_over_best_baseline_percent` |
| MIXED | Do the clusters recover the generator's persona taxonomy? | 0.2566 | `segmentation.persona_alignment.adjusted_rand_index` |
| PASS | Does the copilot retrieve the right document for questions the product actually claims to answer? | 1 | `llm.headline.retrieval_recall_at_3` |
| PASS | Does the copilot refuse prompt injection, PII disclosure and off-topic requests without blocking legitimate questions? | injection_pass_rate=1.0; pii_redaction_pass_rate=1.0; off_topic_pass_rate=1.0; output_guard_pass_rate=1.0; legitimate_false_positive_rate=0.0 | `llm.headline` |
| PASS | Does the copilot refuse questions outside its scope rather than guessing? | 1 | `llm.headline.out_of_scope_refusal_rate` |
| PASS | Is every tool the copilot can invoke both contract-closed and executably safe? | contract_closed=True; execution_pass_rate=1.0; live=unavailable | `llm.headline` |
| PASS | Does the anomaly detector beat the best single naive rule? | 36.8 | `anomaly.headline.f1_improvement_over_best_rule_percent` |
| PASS | Does the detector put most of the anomalous spend in front of the customer, measured in taka on the test window? | 0.7612 | `customer_impact.detection_value.value_coverage` |
| PASS | Can next month's behaviour flags be predicted better than simply assuming this month repeats? | end_month_shortage +18.8%; high_cash_dependency +15.4%; irregular_income -17.7%; overspending +3.7%; financial_pressure +3.7% | `health.early_warning.targets` |
| PASS | Are the attributions stable across two different score frames? | 0.9971 | `explainability.aggregate.stability_min_spearman` |
| PASS | Do the SHAP attributions describe this customer's row, or only the column identity? (shuffling the inputs must collapse them) | 0.1946 | `explainability.aggregate.sanity_worst_mean_attribution_decorrelation` |
| PASS | Do the health models beat a trivial baseline on at least one target? | {'no_gain_over_rule': 4, 'beats_trivial': 6} | `health.profile_calibration.verdict_counts` |
| PASS | Are the health models never worse than a trivial baseline on the untouched test window? | {'no_gain_over_rule': 4, 'beats_trivial': 6} | `health.profile_calibration.verdict_counts` |
| PASS | Can most customers actually follow a save-more recommendation? | 0.7 | `customer_impact.simulation.recommendation_actionability.share_with_positive_capacity` |
| PASS | Are the clusters stable when the same algorithm is refit on the next time window? | 0.9686 | `segmentation.temporal_stability.adjusted_rand_index` |
| PASS | Does a zero intervention really move nothing (is the simulation harness sensitive to the intervention and nothing else)? | yes | `customer_impact.simulation.placebo.harness_sensitive` |

## Protocol

| Split | Periods | Transactions | Injected anomalies |
| --- | --- | --- | --- |
| train | 2026-01..2026-05 | 103,705 | 426 |
| validation | 2026-06..2026-07 | 44,158 | 188 |
| test | 2026-08..2026-09 | 43,304 | 139 |

Train is used to fit every model, validation to choose hyperparameters and thresholds, and test is scored once by the block that needs it. Windows are disjoint by construction; `dataset.disjoint` in the report records the check. Ground-truth tables (personas, injected patterns, behaviour flags) are used for scoring only and are listed as such.

## Forecasting

Task: predict the next period's monthly income and spend level

| Target | Best baseline | Baseline MAE | Shipped model | Model MAE | Improvement |
| --- | --- | --- | --- | --- | --- |
| spend | moving_average_3 | 9,600.8 | volatility_gate | 9,564.6 | 0.38% |
| income | moving_average_3 | 6,551.5 | volatility_gate | 6,745.1 | -2.95% |

## Anomaly detection

Detector `IsolationForest`, contamination `0.012` chosen on validation (2026-06..2026-07). Ground truth: injected_patterns.csv (generator ground truth, scoring only).

| Window | n | Precision | Recall | F1 | AP | P@50 | FPR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| validation | 37,362 | 0.5714 | 0.5319 | 0.551 | 0.3139 | 0.56 | 0.002 |
| test | 36,670 | 0.5704 | 0.5827 | 0.5765 | 0.283 | 0.46 | 0.0017 |

| Window | Best naive rule | Rule F1 | Detector improvement |
| --- | --- | --- | --- |
| validation | amount_outlier | 0.4044 | 36.23% |
| test | amount_outlier | 0.4214 | 36.8% |

Recall by injected pattern (test):

| Pattern | Injected | Detected | Recall |
| --- | --- | --- | --- |
| duplicate_charge | 36 | 20 | 0.5556 |
| large_unplanned_charge | 36 | 35 | 0.9722 |
| round_number_spike | 33 | 22 | 0.6667 |
| unusual_merchant | 34 | 4 | 0.1176 |

## Segmentation

k = 4 chosen by silhouette over 500 customers.

| k | Silhouette |
| --- | --- |
| 2 | 0.1848 |
| 3 | 0.2057 |
| 4 | 0.2116 |
| 5 | 0.1926 |
| 6 | 0.1475 |

| Check | Metric | Value |
| --- | --- | --- |
| Agreement with generator personas (ARI) | ARI | 0.2566 |
| Agreement with generator personas (NMI) | NMI | 0.4317 |
| Customers compared | n | 500 |
| Temporal stability across time cuts (ARI) | ARI | 0.9686 |
| Temporal stability: identical assignments | share | 0.006 |

## Financial health models

Profile recovery: recover the generator's ground-truth financial profile from behaviour

| Target | Type | Verdict | Model | Baseline |
| --- | --- | --- | --- | --- |
| savings_rate | regression | no_gain_over_rule | 0.1655 | 0.0076 |
| emergency_fund_months | regression | no_gain_over_rule | 0.9401 | 0.0089 |
| cash_dependency | regression | no_gain_over_rule | 0.0248 | 0 |
| income_stability | regression | no_gain_over_rule | 0.0062 | 0 |
| end_month_shortage | classification | beats_trivial | 0.9938 | 0.7775 |
| high_cash_dependency | classification | beats_trivial | 0.8988 | 0.8751 |
| irregular_income | classification | beats_trivial | 0.8382 | 0 |
| overspending | classification | beats_trivial | 0.9314 | 0 |
| financial_pressure | classification | beats_trivial | 0.9314 | 0 |
| goal_progress | classification | beats_trivial | 0.6075 | 0 |

> LEAKAGE BY CONSTRUCTION. The dataset generator derives both financial_profiles and behavior_labels by aggregating the same transactions these features are built from: label_savings_rate is close to the savings_rate feature, and the behaviour flags are thresholded versions of late_month_share, cash_dependency, expense_income_ratio and emergency_buffer_months. A model can therefore reach a very high R2 / F1 while learning nothing a rule could not, because it is re-deriving a statistic it was handed. Read the null_control and direct_feature_baseline rows beside every score: the honest claim is that the pipeline reproduces the ground truth reliably on unseen customers and unseen months, NOT that it predicts future financial behaviour. Proving the latter needs held-out real-customer data, which does not exist for this challenge.

Early warning: predict whether the customer will hit a behaviour flag NEXT month from the ledger strictly up to this month

| Target | Constant | Persistence | Best model | Best F1 | vs persistence |
| --- | --- | --- | --- | --- | --- |
| end_month_shortage | 0.4424 | 0.5793 | lightgbm | 0.6883 | 18.82% |
| high_cash_dependency | 0.4165 | 0.516 | logistic | 0.5954 | 15.38% |
| irregular_income | 0.227 | 1 | lightgbm | 0.8226 | -17.74% |
| overspending | 0.1718 | 0.3093 | lightgbm | 0.3207 | 3.69% |
| financial_pressure | 0.1718 | 0.3093 | lightgbm | 0.3207 | 3.69% |

## Explainability

Method: TreeSHAP (shap.TreeExplainer, or LightGBM pred_contrib as an identical fallback)

Checks per target: fidelity (does the explanation reproduce the model), faithfulness (does removing a top feature move the model the way the explanation says), stability (do two windows name the same drivers), sanity (do the attributions collapse when inputs are shuffled).

| Target | Fidelity max rel. error | Faithfulness (chance 0.5) | Stability Spearman | Decorrelation |
| --- | --- | --- | --- | --- |
| savings_rate | 0 | 0.4547 | 0.9996 | 0.1946 |
| emergency_fund_months | 0 | 0.6977 | 0.9991 | -0.0614 |
| cash_dependency | 0 | 0.658 | 0.9993 | -0.0583 |
| income_stability | 0 | 0.5146 | 0.9971 | 0.0141 |

Worst target across all checks:

| Check | Worst value |
| --- | --- |
| Fidelity relative error | 0 |
| Faithfulness direction agreement | 0.4547 |
| Stability Spearman | 0.9971 |
| Attribution decorrelation | 0.1946 |

## Copilot: safety and grounding

| Check | Result |
| --- | --- |
| injection_pass_rate | 1 |
| pii_redaction_pass_rate | 1 |
| off_topic_pass_rate | 1 |
| legitimate_false_positive_rate | 0 |
| output_guard_pass_rate | 1 |
| retrieval_recall_at_1 | 0.8571 |
| retrieval_recall_at_3 | 1 |
| retrieval_mrr | 0.9167 |
| out_of_scope_refusal_rate | 1 |
| tool_contract_closed | yes |
| tool_execution_pass_rate | 1 |
| live_suite_status | unavailable |
| all_offline_checks_passed | yes |

Out-of-scope refusal rate: 1 over 8 cases.

**Live provider suite: unavailable.** every live case failed before a model answered: RouterError: both providers unavailable This is coverage the evaluation does *not* have; the offline suites above still ran.

## Customer impact

Detection value, measured in taka on the untouched test window:

| Measure | Value |
| --- | --- |
| Anomalous taka in the window | 3,410,463.2 |
| Anomalous taka flagged | 2,596,127.9 |
| Coverage | 0.7612 |
| Taka wrongly flagged | 1,569,472.2 |
| Wrongly flagged share of what was shown | 0.3768 |

| Injected pattern | Events | Detected | Value coverage |
| --- | --- | --- | --- |
| duplicate_charge | 36 | 20 | 0.7764 |
| large_unplanned_charge | 36 | 35 | 0.982 |
| round_number_spike | 33 | 22 | 0.6889 |
| unusual_merchant | 34 | 4 | 0.1938 |

Deficit warnings: predict an observed month-end deficit (spend > income) next month

Best model `lightgbm` F1 0.6709, 3.91% over persistence. Outcome: observed monthly net from the transactions themselves (features side, not a label table)

| Warnings emitted | Correct | Novel | Novel share | Missed |
| --- | --- | --- | --- | --- |
| 131 | 105 | 0 | 0 | 77 |

Simulation on 50 customers from the product population. Placebo (no intervention) moved nothing: True.

| Arm | Policy | Mean spendable balance change | Mean net worth change | Mean goals unlocked |
| --- | --- | --- | --- | --- |
| saving_arm | redirect 20% of measured disposable capacity into savings every month | -13,686.9 | 0 | 0.08 |
| expense_arm | cut discretionary spending by 10% of measured monthly spend | 62,797.9 | 62,797.9 | 0.08 |

| Measure | Value |
| --- | --- |
| n_customers | 50 |
| median_disposable_capacity_monthly | 3,180.6 |
| share_with_positive_capacity | 0.7 |
| share_sitting_below_their_buffer | 0 |
| emergency_fund_affordable_share | 0.7 |
| emergency_fund_funded_share | 1 |
| customers_with_a_remaining_gap | 0 |
| median_months_to_target_for_open_gaps | n/a |
| share_of_open_gaps_never_reaching_target | n/a |
| mean_remaining_amount | 0 |

> Every product customer already holds more than the emergency fund their own history implies, so this feature has nothing to do on this population and the horizon statistics are empty. That is a product finding, not a modelling result: the useful signal here is the capacity line, because share_with_positive_capacity is exactly the share of customers who could follow a save-more recommendation at all. The rest are already below the buffer the engine itself computes.

## What did not hold

| Status | Claim | Value |
| --- | --- | --- |
| FAIL | Do next-month deficit warnings tell the customer something they do not already know? | 0 |
| FAIL | Is the share of wrongly-flagged taka small enough not to erode trust? | 0.3768 |
| FAIL | Does removing a top feature move the model the way the explanation says it will? (chance = 0.5) | 0.4547 |
| FAIL | Does the shipped income forecast beat the best naive baseline on the untouched test window? | -2.95 |
| MIXED | Does the shipped spend forecast beat the best naive baseline on the untouched test window? | 0.38 |
| MIXED | Do the clusters recover the generator's persona taxonomy? | 0.2566 |

## Known data defects

- none reported

---

Every figure above comes from `backend/reports/evidence_report.json`, which is what the Evidence Dashboard in the app serves. Nothing in this document is entered by hand.
