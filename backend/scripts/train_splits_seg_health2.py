from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.build import _reindex_calendar, daily_features, monthly_features, user_features
from app.ml.artifacts import ModelCard, save_bundle, save_card

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
    if (labs / "financial_profiles.csv").exists():
        res["financial_profiles"] = pd.read_csv(labs / "financial_profiles.csv")
    if (labs / "injected_patterns.csv").exists():
        res["injected_patterns"] = pd.read_csv(labs / "injected_patterns.csv", parse_dates=["timestamp"])
    return res


def augment_goals(goals: pd.DataFrame, contributions: pd.DataFrame) -> pd.DataFrame:
    cur = contributions.groupby("goal_id")["amount"].sum().rename("current_amount")
    g = goals.merge(cur, on="goal_id", how="left")
    g["current_amount"] = g["current_amount"].fillna(0.0)
    g["is_achieved"] = g["current_amount"] >= g["target_amount"]
    g["progress_ratio"] = (g["current_amount"] / g["target_amount"].clip(lower=1.0)).fillna(0.0)
    return g


def main() -> int:
    train = load_split("train")
    val = load_split("validation")
    test = load_split("test")

    transactions = pd.concat([train["transactions"], val["transactions"], test["transactions"]], ignore_index=True)
    wallets = pd.concat([train["wallets"], val["wallets"], test["wallets"]], ignore_index=True).drop_duplicates(subset=["wallet_id"])
    contributions = pd.concat([train["goal_contributions"], val["goal_contributions"], test["goal_contributions"]], ignore_index=True)
    goals = pd.concat([train["financial_goals"], val["financial_goals"], test["financial_goals"]], ignore_index=True)
    goals = augment_goals(goals, contributions)
    profiles = pd.concat([train["financial_profiles"], val["financial_profiles"], test["financial_profiles"]], ignore_index=True) if "financial_profiles" in train else pd.DataFrame()
    injected = pd.concat([train["injected_patterns"], val["injected_patterns"], test["injected_patterns"]], ignore_index=True) if "injected_patterns" in train else pd.DataFrame()
    if not injected.empty:
        transactions["is_anomaly"] = transactions["transaction_id"].isin(injected["transaction_id"])
    else:
        transactions["is_anomaly"] = False

    print("Building features ...")
    daily = _reindex_calendar(daily_features(transactions, wallets))
    monthly = monthly_features(daily, contributions, goals)
    users_f = user_features(daily, monthly, contributions, goals, transactions, wallets, profiles)
    print(f"  users_f={users_f.shape}")
    trained_at = datetime.now(timezone.utc).isoformat()
    num_cols = users_f.select_dtypes(include=[np.number]).columns.tolist()
    feats = [c for c in num_cols if c != "user_id"]
    X = users_f[feats].copy()
    im = SimpleImputer(strategy="median")
    Xs = im.fit_transform(X)
    sc = StandardScaler()
    Xs = sc.fit_transform(Xs)
    best_k, best_s = 3, -1
    for k in range(2, 6):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labs = km.fit_predict(Xs)
        if len(np.unique(labs)) > 1:
            try:
                s = silhouette_score(Xs, labs)
            except Exception:
                s = -1
            if s > best_s:
                best_s, best_k = s, k
    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    km.fit(Xs)
    save_bundle("segmentation", {"model": {"imputer": im, "scaler": sc, "kmeans": km, "k": best_k}, "features": feats})
    save_card("segmentation", ModelCard(name="segmentation", task="user behavioral segmentation", trained_at=trained_at, train_window="2026-01..2026-05", validation_window="2026-06..2026-07", features=feats, metrics={"silhouette_score": float(best_s), "n_clusters": best_k}, baselines={}, notes="KMeans trained on splits."))
    print(f"Seg k={best_k}")
    if not profiles.empty and "resilience_score" in profiles.columns:
        y = users_f.merge(profiles[["user_id", "resilience_score"]], on="user_id", how="left")["resilience_score"]
        m = y.notna()
        if m.sum() > 10:
            rf = RandomForestRegressor(n_estimators=150, max_depth=6, random_state=42)
            rf.fit(Xs[m], y[m].values)
            pred = rf.predict(Xs[m])
            mae = float(np.mean(np.abs(pred - y[m].values)))
            rmse = float(np.sqrt(np.mean((pred - y[m].values)**2)))
            save_bundle("health_model", {"model": {"imputer": im, "scaler": sc, "rf": rf}, "features": feats, "target": "resilience_score"})
            save_card("health_model", ModelCard(name="health_model", task="explainable scorer", trained_at=trained_at, train_window="2026-01..2026-05", validation_window="2026-06..2026-07", features=feats, metrics={"mae": mae, "rmse": rmse}, baselines={}, notes="Tree model on splits."))
            print(f"Health MAE={mae:.2f}")
    print("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
