from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.build import _reindex_calendar, daily_features, monthly_features
from app.ml.artifacts import ModelCard, json_safe, save_bundle, save_card
from app.ml.forecast import train_level_forecasters

SPLITS = Path(__file__).resolve().parents[2] / "data" / "dev" / "splits"


def load_split(name: str) -> dict[str, pd.DataFrame]:
    root = SPLITS / name
    feats = root / "features"
    return {
        "users": pd.read_csv(feats / "users.csv"),
        "wallets": pd.read_csv(feats / "wallets.csv"),
        "transactions": pd.read_csv(feats / "transactions.csv", parse_dates=["timestamp"]),
        "income_events": pd.read_csv(feats / "income_events.csv", parse_dates=["timestamp"]),
        "recurring_expenses": pd.read_csv(feats / "recurring_expenses.csv", parse_dates=["next_due_date"]),
        "financial_goals": pd.read_csv(feats / "financial_goals.csv", parse_dates=["target_date", "created_date"]),
        "goal_contributions": pd.read_csv(feats / "goal_contributions.csv", parse_dates=["timestamp"]),
    }


def main() -> int:
    train = load_split("train")
    val = load_split("validation")
    test = load_split("test")

    transactions = pd.concat([train["transactions"], val["transactions"], test["transactions"]], ignore_index=True)
    wallets = pd.concat([train["wallets"], val["wallets"], test["wallets"]], ignore_index=True).drop_duplicates(subset=["wallet_id"])
    contributions = pd.concat([train["goal_contributions"], val["goal_contributions"], test["goal_contributions"]], ignore_index=True)
    goals = pd.concat([train["financial_goals"], val["financial_goals"], test["financial_goals"]], ignore_index=True)

    print("Building features ...")
    daily = _reindex_calendar(daily_features(transactions, wallets))
    monthly = monthly_features(daily, contributions, goals)
    print(f"  daily={daily.shape} monthly={monthly.shape}")

    TRAIN = {"2026-01", "2026-02", "2026-03", "2026-04", "2026-05"}
    VALIDATION = {"2026-06", "2026-07"}
    TEST = {"2026-08", "2026-09"}

    trained_at = datetime.now(timezone.utc).isoformat()
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
            train_window="2026-01..2026-05",
            validation_window="2026-06..2026-07",
            features=forecast["features"][target],
            metrics=json_safe(te["volatility_gate"]),
            baselines=json_safe({"structural_trailing": te["structural_trailing"], "gbm_only": te["gbm_lgbm"]}),
            notes="Volatility-gated stack trained on data/dev/splits.",
        )
        save_card(f"forecast_{target}_level", card)
        print(f"  {target}: GATED MAE={te['volatility_gate']['mae']:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
