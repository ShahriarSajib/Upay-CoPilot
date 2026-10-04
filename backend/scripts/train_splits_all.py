from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.build import _reindex_calendar, daily_features, monthly_features
from app.ml.anomaly import evaluate_anomaly_model, train_anomaly_model, tune_contamination
from app.ml.artifacts import ModelCard, json_safe, save_bundle, save_card
from app.ml.forecast import train_level_forecasters

SPLITS = Path(__file__).resolve().parents[2] / "data" / "dev" / "splits"


def load_split(name: str) -> dict[str, pd.DataFrame]:
    root = SPLITS / name
    feats = root / "features"
    labs = root / "labels"
    res = {
        "users": pd.read_csv(feats / "users.csv"),
        "wallets": pd.read_csv(feats / "wallets.csv"),
        "transactions": pd.read_csv(feats / "transactions.csv", parse_dates=["timestamp"]),
        "income_events": pd.read_csv(feats / "income_events.csv", parse_dates=["timestamp"]),
        "recurring_expenses": pd.read_csv(feats / "recurring_expenses.csv", parse_dates=["next_due_date"]),
        "financial_goals": pd.read_csv(feats / "financial_goals.csv", parse_dates=["target_date", "created_date"]),
        "goal_contributions": pd.read_csv(feats / "goal_contributions.csv", parse_dates=["timestamp"]),
    }
    if (labs / "injected_patterns.csv").exists():
        res["injected_patterns"] = pd.read_csv(labs / "injected_patterns.csv", parse_dates=["timestamp"])
    return res


def main() -> int:
    train = load_split("train")
    val = load_split("validation")
    test = load_split("test")

    transactions = pd.concat([train["transactions"], val["transactions"], test["transactions"]], ignore_index=True)
    wallets = pd.concat([train["wallets"], val["wallets"], test["wallets"]], ignore_index=True).drop_duplicates(subset=["wallet_id"])
    contributions = pd.concat([train["goal_contributions"], val["goal_contributions"], test["goal_contributions"]], ignore_index=True)
    goals = pd.concat([train["financial_goals"], val["financial_goals"], test["financial_goals"]], ignore_index=True)
    injected = pd.concat([train["injected_patterns"], val["injected_patterns"], test["injected_patterns"]], ignore_index=True) if "injected_patterns" in train else pd.DataFrame()
    if not injected.empty:
        transactions = transactions.merge(injected[["transaction_id", "pattern_type"]], on="transaction_id", how="left")
        transactions["is_anomaly"] = transactions["transaction_id"].isin(injected["transaction_id"])
    else:
        transactions["is_anomaly"] = False
        transactions["pattern_type"] = pd.NA

    print("Building features ...")
    daily = _reindex_calendar(daily_features(transactions, wallets))
    monthly = monthly_features(daily, contributions, goals)
    print(f"  daily={daily.shape} monthly={monthly.shape}")

    TRAIN = {"2026-01", "2026-02", "2026-03", "2026-04", "2026-05"}
    VALIDATION = {"2026-06", "2026-07"}
    TEST = {"2026-08", "2026-09"}

    trained_at = datetime.now(timezone.utc).isoformat()
    windows = ("2026-01..2026-05", "2026-06..2026-07")

    print("\n[1/4] Forecast")
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
        te = forecast["report"]["test"][target]
        card = ModelCard(
            name=f"forecast_{target}_level",
            task="predict next-period monthly income/spend level",
            trained_at=trained_at,
            train_window=windows[0],
            validation_window=windows[1],
            features=forecast["features"][target],
            metrics=json_safe(te["volatility_gate"]),
            baselines=json_safe({"structural_trailing": te["structural_trailing"], "gbm_only": te["gbm_lgbm"]}),
            notes="Volatility-gated stack trained on data/dev/splits.",
        )
        save_card(f"forecast_{target}_level", card)
        print(f"  {target}: GATED MAE={te['volatility_gate']['mae']:.0f}")

    print("\n[2/4] Anomaly")
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
            notes="Isolation Forest; labels used only for scoring. Trained on data/dev/splits.",
        ),
    )
    for period, m in anomaly_metrics.items():
        print(f"  {period}: P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} AP={m['average_precision']:.3f}")
    print("\nArtifacts written to backend/artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
