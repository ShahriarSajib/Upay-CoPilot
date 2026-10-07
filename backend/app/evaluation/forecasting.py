"""Cash-flow forecasting benchmark.

The shipped model claims a MAE improvement over the customer's own trailing
mean. This module is what makes that claim checkable: it puts the production
stack next to five baselines on the same rows, on the same splits, and reports
the whole table rather than the flattering cell.

Why baselines matter here
-------------------------
Monthly spend in this dataset is drawn proportional to that month's income, so
there is little day-to-day autocorrelation to exploit. A gradient-boosted model
can therefore *lose* to ``mean of the last three months`` while looking
sophisticated. The benchmark forces that comparison into the open:

* ``naive_last`` / ``moving_average_3`` / ``drift`` -- zero-parameter
  persistence baselines any reviewer can recompute by hand;
* ``exponential_smoothing`` -- the classical ETS level component, with alpha
  grid-searched on validation only (``statsmodels`` is not a dependency, so the
  recursion is stated in :class:`app.evaluation.baselines.ExponentialSmoothing`);
* ``structural_ewma`` -- the product's own decay-weighted trailing estimator;
* ``lightgbm`` / ``xgboost`` -- gradient boosting on the identical feature
  frame and identical split;
* ``volatility_gate`` -- the shipped stack.

Headline numbers come from the **test** window. Validation numbers are the
tuning window and are labelled as optimistic for the estimators that tune.
"""

from __future__ import annotations

from app.evaluation.baselines import default_estimators, run_forecast_benchmark
from app.evaluation.datasets import Dataset


def _monthly(dataset: Dataset):
    from app.features.build import _reindex_calendar, daily_features, monthly_features

    if dataset.monthly is None:
        daily = _reindex_calendar(daily_features(dataset.transactions, dataset.wallets))
        dataset.daily = daily
        dataset.monthly = monthly_features(daily, dataset.contributions, dataset.goals)
    return dataset.monthly


def run(dataset: Dataset, verbose: bool = False) -> dict:
    """Full baseline benchmark for both cash-flow targets."""
    monthly = _monthly(dataset)
    if verbose:
        print(f"  monthly rows={len(monthly)}")

    benchmark = run_forecast_benchmark(
        monthly,
        dataset.train_periods,
        dataset.validation_periods,
        dataset.test_periods,
        estimators=default_estimators(include_gate=True),
        seed=dataset.seed,
    )

    # The shipped model's own report, for the gate's learned thresholds and
    # the per-volatility-band breakdown the benchmark table cannot show.
    from app.ml.forecast import train_level_forecasters

    fitted = train_level_forecasters(
        monthly,
        dataset.train_periods,
        dataset.validation_periods,
        dataset.test_periods,
        seed=dataset.seed,
    )

    summary = _summarise(benchmark)
    if verbose:
        for target, row in summary.items():
            print(
                f"  {target}: best baseline={row['test_best_baseline']} "
                f"MAE={row['test_best_baseline_mae']:.0f} | "
                f"best model={row['test_best_model']} MAE={row['test_best_model_mae']:.0f} "
                f"({row['test_improvement_over_best_baseline_percent']:+.1f}%)"
            )

    return {
        "task": "predict the next period's monthly income and spend level",
        "protocol": benchmark["protocol"],
        "splits": {
            "train": sorted(dataset.train_periods),
            "validation": sorted(dataset.validation_periods),
            "test": sorted(dataset.test_periods),
        },
        "n_monthly_rows": int(len(monthly)),
        "targets": benchmark["targets"],
        "summary": summary,
        "shipped_model": {
            "stack": "LightGBM blended with a trailing estimator by a learned volatility gate",
            "report": fitted["report"],
            "feature_importance": fitted["importance"],
            "test_by_volatility_band": {
                target: fitted["report"]["test"][target]["segments"]["volatility_gate"]
                for target in ("spend", "income")
            },
        },
        "seed": dataset.seed,
    }


def _summarise(benchmark: dict) -> dict[str, dict]:
    """One row per target: best baseline, best model, and the gap."""
    out: dict[str, dict] = {}
    for target, entry in benchmark["targets"].items():
        row = {
            "test_improvement_over_best_baseline_percent": entry.get(
                "test_improvement_over_best_baseline_percent"
            ),
            "test_best_baseline": entry.get("test_best_baseline"),
            "test_best_model": entry.get("test_best_model"),
            "test_best_baseline_mae": entry.get("test_best_baseline_mae"),
            "test_best_model_mae": entry.get("test_best_model_mae"),
            "validation_improvement_over_best_baseline_percent": entry.get(
                "validation_improvement_over_best_baseline_percent"
            ),
            "ranking": entry.get("test_ranking"),
        }
        out[target] = row
    return out
