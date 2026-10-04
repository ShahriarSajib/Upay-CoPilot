"""Train every ML model, evaluate it against its baselines, and persist it.

Run with::

    python scripts/train.py

Writes to ``backend/artifacts``:

* ``forecast.joblib``      -- volatility-gated income/spend level models
* ``anomaly.joblib``       -- Isolation Forest unusual-spending detector
* ``*.card.json``          -- model cards quoting metrics, baselines, windows

Train / validation / test windows are chronological and disjoint. The gate
parameters and the anomaly operating point are chosen on the *validation*
window only; the test window is touched once, for reporting.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.store import cached_store  # noqa: E402
from app.features.build import _reindex_calendar, daily_features, monthly_features  # noqa: E402
from app.ml.anomaly import (  # noqa: E402
    evaluate_anomaly_model,
    train_anomaly_model,
    tune_contamination,
)
from app.ml.artifacts import ModelCard, json_safe, save_bundle, save_card  # noqa: E402
from app.ml.forecast import train_level_forecasters  # noqa: E402

TRAIN = {"2026-01", "2026-02", "2026-03", "2026-04", "2026-05"}
VALIDATION = {"2026-06", "2026-07"}
TEST = {"2026-08", "2026-09"}


def main() -> int:
    store = cached_store()
    transactions = store.transactions()

    print("Building features ...")
    daily = _reindex_calendar(daily_features(transactions, store.wallets()))
    monthly = monthly_features(daily, store.contributions(), store.goals())
    print(f"  daily={daily.shape} monthly={monthly.shape}")

    trained_at = datetime.now(timezone.utc).isoformat()
    windows = (f"{min(TRAIN)}..{max(TRAIN)}", f"{min(VALIDATION)}..{max(VALIDATION)}")

    # ---------------------------------------------------------------- forecast
    print("\nTraining monthly level forecasters (volatility-gated stack) ...")
    forecast = train_level_forecasters(monthly, TRAIN, VALIDATION, TEST, verbose=True)
    save_bundle(
        "forecast",
        {
            "models": forecast["models"],
            "gates": forecast["gates"],
            "features": forecast["features"],
            "train_periods": forecast["train_periods"],
            "validation_periods": forecast["validation_periods"],
            "history_windows": forecast["history_windows"],
        },
    )
    for target in ("spend", "income"):
        test_entry = forecast["report"]["test"][target]
        card = ModelCard(
            name=f"forecast_{target}_level",
            task="predict next-period monthly income/spend level",
            trained_at=trained_at,
            train_window=windows[0],
            validation_window=windows[1],
            features=forecast["features"][target],
            metrics=json_safe(test_entry["volatility_gate"]),
            baselines=json_safe(
                {
                    "structural_trailing": test_entry["structural_trailing"],
                    "gbm_only": test_entry["gbm_lgbm"],
                }
            ),
            notes=(
                "Volatility-gated stack. A plain LightGBM regressor LOSES to the "
                "user's own trailing mean (spend MAE 11388 vs 10528 on test) because "
                "monthly spend is drawn proportional to that month's income, leaving "
                "little exploitable structure. The gate learns from the user's own "
                "coefficient of variation how far to trust each estimator: it tracks "
                "the trailing mean for stable users and the GBM for volatile ones. "
                "Gate thresholds were fitted on the validation window only."
            ),
        )
        save_card(f"forecast_{target}_level", card)
        print(
            f"  {target}: structural={test_entry['structural_trailing']['mae']:.0f} "
            f"gbm={test_entry['gbm_lgbm']['mae']:.0f} "
            f"GATED={test_entry['volatility_gate']['mae']:.0f}"
        )

    # ----------------------------------------------------------------- anomaly
    print("\nTraining unusual-spending detector ...")
    selection = tune_contamination(transactions, TRAIN, VALIDATION)
    anomaly = train_anomaly_model(transactions, TRAIN, contamination=selection["contamination"])
    save_bundle(
        "anomaly",
        {
            "model": anomaly["model"],
            "features": anomaly["features"],
            "contamination": anomaly["contamination"],
            "selection": selection,
        },
    )
    anomaly_metrics = {p: evaluate_anomaly_model(anomaly, transactions, p) for p in sorted(TEST)}
    save_card(
        "anomaly_detection",
        ModelCard(
            name="anomaly_detection",
            task="rank unusual spending transactions for review",
            trained_at=trained_at,
            train_window=windows[0],
            validation_window=windows[1],
            features=anomaly["features"],
            metrics=json_safe({p: {k: v for k, v in m.items() if k != "by_pattern"} for p, m in anomaly_metrics.items()}),
            baselines={"injected_anomaly_rate": anomaly["prior_anomaly_rate"]},
            notes=(
                "Unsupervised Isolation Forest; ground-truth labels are used only to "
                "score it, never to fit it. The operating point was chosen on the "
                "validation window. Known limitation: the injected 'unusual_merchant' "
                "pattern is detected poorly (~5% recall) because a single novel "
                "merchant at a mid-range amount is genuinely indistinguishable from "
                "ordinary spending on transaction features alone -- that signal lives in "
                "sequence context. Detection is kept deliberately conservative: a false "
                "accusation of irregular spending is worse than a miss."
            ),
        ),
    )
    for period, metrics in anomaly_metrics.items():
        print(
            f"  {period}: P={metrics['precision']:.3f} R={metrics['recall']:.3f} "
            f"F1={metrics['f1']:.3f} AP={metrics['average_precision']:.3f} "
            f"P@50={metrics['precision_at_k']:.3f}"
        )

    print("\nArtifacts written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())