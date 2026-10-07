"""Train every model from ``data/dev/splits`` and write the evaluation report.

    cd backend && .venv/bin/python scripts/train_all_splits.py

What gets trained
-----------------
====================  ==================  ==========================================
model                  algorithm           evaluation
====================  ==================  ==========================================
forecast               LightGBM + a       MAE / RMSE / MAPE / bias on validation and
(income, spend level)  learned volatility  test, vs a structural trailing baseline
                       gate
anomaly                Isolation Forest    precision / recall / F1 / AP / P@k on
                                         validation and test, against the injected
                                         ground truth
segmentation           KMeans on the       silhouette curve, adjusted Rand index vs
                       user grain          behaviour flags, temporal stability
health / resilience    LightGBM           MAE / RMSE / R2 / Spearman per target vs a
                                           training-mean baseline; behaviour
                                           classifiers get precision / recall / F1 /
                                           ROC-AUC
====================  ==================  ==========================================

Leakage discipline
------------------
* Transactions are split **by time**: train 2026-01..05, validation 06..07,
  test 08..09. Windows are asserted disjoint before anything is fitted.
* The forecast gate is fitted on the validation window only.
* The anomaly operating point is tuned on validation only.
* Ground-truth columns (``is_anomaly``, ``pattern_type``, ``is_achieved``,
  ``progress_ratio``, ``persona``) live under ``labels/`` and the loader raises
  if any of them is found on a feature frame.
* The health/segmentation folds are **expanding windows**: the feature vector for
  the validation cut is built from 2026-01..07 only, and the feature vector for
  the test cut from 2026-01..09 only, because the profile label is a
  full-horizon property of a customer.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.splits import (  # noqa: E402
    SPLIT_NAMES,
    assert_disjoint_periods,
    build_features,
    describe_all,
    load_all_splits,
    reset_cache,
)
from app.ml import health as ml_health  # noqa: E402
from app.ml import segmentation as ml_segmentation  # noqa: E402
from app.ml.anomaly import (  # noqa: E402
    evaluate_anomaly_model,
    train_anomaly_model,
    tune_contamination,
)
from app.ml.artifacts import ModelCard, json_safe, save_bundle, save_card  # noqa: E402
from app.ml.forecast import train_level_forecasters  # noqa: E402

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "evaluation_report.json"


def _split_source() -> str:
    from app.data.splits import splits_root

    return str(splits_root())


def _rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# 1. forecast
# ---------------------------------------------------------------------------

def train_forecast(report: dict) -> None:
    _rule("1/4  Cash-flow forecast (LightGBM + learned volatility gate)")
    splits = load_all_splits()
    train_periods = set(splits["train"].periods)
    validation_periods = set(splits["validation"].periods)
    test_periods = set(splits["test"].periods)

    transactions = pd.concat(
        [splits[name].transactions for name in SPLIT_NAMES], ignore_index=True
    )
    wallets = (
        pd.concat([splits[name].feature("wallets") for name in SPLIT_NAMES], ignore_index=True)
        .drop_duplicates(subset=["wallet_id"])
    )
    contributions = pd.concat(
        [splits[name].feature("goal_contributions") for name in SPLIT_NAMES], ignore_index=True
    )
    goals = pd.concat([splits[name].goals for name in SPLIT_NAMES], ignore_index=True)

    from app.features.build import _reindex_calendar, daily_features, monthly_features

    daily = _reindex_calendar(daily_features(transactions, wallets))
    monthly = monthly_features(daily, contributions, goals)
    print(f"  monthly rows={len(monthly)}  daily rows={len(daily)}")
    print(f"  train={sorted(train_periods)}")
    print(f"  validation={sorted(validation_periods)}")
    print(f"  test={sorted(test_periods)}")

    fitted = train_level_forecasters(
        monthly, train_periods, validation_periods, test_periods, verbose=True
    )

    save_bundle(
        "forecast",
        {
            "models": fitted["models"],
            "gates": fitted["gates"],
            "features": fitted["features"],
            "train_periods": fitted["train_periods"],
            "validation_periods": fitted["validation_periods"],
            "history_windows": fitted["history_windows"],
            "source": _split_source(),
        },
    )

    entry: dict = {
        "train_periods": sorted(train_periods),
        "validation_periods": sorted(validation_periods),
        "test_periods": sorted(test_periods),
        "n_monthly_rows": int(len(monthly)),
        "feature_importance": json_safe(fitted["importance"]),
    }
    for target in ("spend", "income"):
        test_entry = fitted["report"]["test"][target]
        card = ModelCard(
            name=f"forecast_{target}_level",
            task="predict next-period monthly income/spend level",
            trained_at=report["trained_at"],
            train_window=f"{min(train_periods)}..{max(train_periods)}",
            validation_window=f"{min(validation_periods)}..{max(validation_periods)}",
            features=fitted["features"][target],
            metrics=json_safe(test_entry["volatility_gate"]),
            baselines=json_safe(
                {
                    "structural_trailing": test_entry["structural_trailing"],
                    "gbm_only": test_entry["gbm_lgbm"],
                }
            ),
            notes=(
                "Volatility-gated stack. A plain LightGBM regressor LOSES to the "
                "customer's own trailing mean on monthly spend, because monthly spend "
                "is drawn proportional to that month's income, leaving little exploitable "
                "structure. The gate learns from the customer's own coefficient of "
                "variation how far to trust each estimator: it tracks the trailing mean "
                "for stable customers and the GBM for volatile ones. Gate thresholds "
                "were fitted on the validation window only."
            ),
        )
        save_card(f"forecast_{target}_level", card)
        entry[target] = {
            "test": json_safe(
                {
                    "structural_trailing": test_entry["structural_trailing"],
                    "gbm_only": test_entry["gbm_lgbm"],
                    "volatility_gate": test_entry["volatility_gate"],
                    "gate": test_entry["gate"],
                }
            ),
            "validation": json_safe(
                {
                    "structural_trailing": fitted["report"]["validation"][target][
                        "structural_trailing"
                    ],
                    "gbm_only": fitted["report"]["validation"][target]["gbm_lgbm"],
                    "volatility_gate": fitted["report"]["validation"][target][
                        "volatility_gate"
                    ],
                }
            ),
            "test_by_volatility_band": json_safe(test_entry["segments"]["volatility_gate"]),
            "mae_improvement_vs_trailing_percent": round(
                100.0
                * (
                    test_entry["structural_trailing"]["mae"]
                    - test_entry["volatility_gate"]["mae"]
                )
                / max(test_entry["structural_trailing"]["mae"], 1e-9),
                2,
            ),
        }
        print(
            f"  {target}: trailing={test_entry['structural_trailing']['mae']:.0f} "
            f"gbm={test_entry['gbm_lgbm']['mae']:.0f} "
            f"GATED={test_entry['volatility_gate']['mae']:.0f} "
            f"({entry[target]['mae_improvement_vs_trailing_percent']:+.1f}% vs trailing)"
        )
    report["forecast"] = entry


# ---------------------------------------------------------------------------
# 2. anomaly
# ---------------------------------------------------------------------------

def train_anomaly(report: dict) -> None:
    _rule("2/4  Unusual-spending detector (Isolation Forest)")
    splits = load_all_splits()
    transactions = pd.concat(
        [splits[name].transactions for name in SPLIT_NAMES], ignore_index=True
    )
    train_periods = set(splits["train"].periods)
    validation_periods = set(splits["validation"].periods)
    test_periods = splits["test"].periods

    selection = tune_contamination(transactions, train_periods, validation_periods)
    print(f"  contamination chosen on validation: {selection['contamination']}")

    anomaly = train_anomaly_model(
        transactions, train_periods, contamination=selection["contamination"]
    )
    save_bundle(
        "anomaly",
        {
            "model": anomaly["model"],
            "features": anomaly["features"],
            "contamination": anomaly["contamination"],
            "selection": selection,
            "source": _split_source(),
        },
    )

    metrics: dict[str, dict] = {}
    for period in test_periods:
        metrics[period] = evaluate_anomaly_model(anomaly, transactions, period)
    for split_name in ("validation", "test"):
        periods = (
            sorted(splits["validation"].periods)
            if split_name == "validation"
            else sorted(splits["test"].periods)
        )
        pooled = evaluate_anomaly_model(anomaly, transactions, periods)
        metrics[f"{split_name}_pooled"] = pooled
        print(
            f"  {split_name} pooled: P={pooled['precision']:.3f} R={pooled['recall']:.3f} "
            f"F1={pooled['f1']:.3f} AP={pooled['average_precision']:.3f} "
            f"P@50={pooled['precision_at_k']:.3f} n={pooled['n']}"
        )

    save_card(
        "anomaly_detection",
        ModelCard(
            name="anomaly_detection",
            task="rank unusual spending transactions for review",
            trained_at=report["trained_at"],
            train_window=f"{min(train_periods)}..{max(train_periods)}",
            validation_window=f"{min(validation_periods)}..{max(validation_periods)}",
            features=anomaly["features"],
            metrics=json_safe(
                {
                    split_name: {k: v for k, v in m.items() if k != "by_pattern"}
                    for split_name, m in metrics.items()
                }
            ),
            baselines={"injected_anomaly_rate": anomaly["prior_anomaly_rate"]},
            notes=(
                "Unsupervised Isolation Forest; ground-truth labels are used only to "
                "score it, never to fit it. The operating point was chosen on the "
                "validation window. Known limitation: the injected 'unusual_merchant' "
                "pattern is detected poorly because a single novel merchant at a "
                "mid-range amount is genuinely indistinguishable from ordinary spending "
                "on transaction features alone -- that signal lives in sequence context. "
                "Detection is kept deliberately conservative: falsely accusing a customer "
                "of irregular spending is worse than missing a pattern."
            ),
        ),
    )
    report["anomaly"] = {
        "contamination": anomaly["contamination"],
        "contamination_selection": json_safe(selection),
        "prior_anomaly_rate": anomaly["prior_anomaly_rate"],
        "features": anomaly["features"],
        "metrics": json_safe({k: {kk: vv for kk, vv in v.items()} for k, v in metrics.items()}),
    }


# ---------------------------------------------------------------------------
# 3. segmentation
# ---------------------------------------------------------------------------

def train_segmentation(report: dict) -> None:
    _rule("3/4  Behavioural segmentation (KMeans on the user grain)")
    splits = load_all_splits()
    behaviour = pd.concat(
        [splits[name].label("behavior_labels") for name in SPLIT_NAMES], ignore_index=True
    ).drop_duplicates(subset=["user_id", "period"])

    train_bundle_features = build_features("train")
    validation_bundle_features = build_features("validation")

    bundle = ml_segmentation.fit(train_bundle_features.user)
    if not bundle.get("fitted"):
        report["segmentation"] = {"fitted": False, "reason": bundle["reason"]}
        print(f"  skipped: {bundle['reason']}")
        return

    evaluation = ml_segmentation.evaluate(bundle, train_bundle_features.user, behaviour)
    validation_fit = ml_segmentation.fit(validation_bundle_features.user)
    stability = ml_segmentation.temporal_stability(
        bundle, train_bundle_features.user, validation_fit, validation_bundle_features.user
    )

    print(f"  k chosen by {bundle['chosen_by']}: {bundle['n_clusters']}")
    print(f"  silhouette curve: {bundle['silhouette_by_k']}")
    print(f"  inertia curve:    {bundle['inertia_by_k']}")
    for cluster in evaluation["clusters"]:
        tops = ", ".join(
            f"{f['feature']} {f['standardised_difference']:+.2f}sd"
            for f in cluster["top_distinctive"]
        )
        print(f"   cluster {cluster['cluster_id']}: n={cluster['size']:3d}  {tops}")
    alignment = evaluation["external_alignment"]
    if alignment.get("available"):
        print(f"  mean ARI vs behaviour flags: {alignment['mean_adjusted_rand_index']}")
    if stability.get("available"):
        print(
            f"  temporal stability (train cut vs validation cut): "
            f"ARI={stability['adjusted_rand_index']} "
            f"identical={stability['identical_assignment_share']}"
        )

    from app.engines.segmentation import _assign_labels  # noqa: PLC0415

    label_by_cluster, generic = _assign_labels(bundle["model"].cluster_centers_, bundle["features"])
    save_bundle(
        "segmentation",
        {
            "scaler": bundle["scaler"],
            "model": bundle["model"],
            "features": bundle["features"],
            "n_clusters": bundle["n_clusters"],
            "silhouette_by_k": bundle["silhouette_by_k"],
            "inertia_by_k": bundle["inertia_by_k"],
            "seed": bundle["seed"],
            "labels": {str(k): v.value for k, v in label_by_cluster.items()},
            "generic_label_used": bool(generic),
            "source": _split_source(),
        },
    )
    save_card(
        "segmentation",
        ModelCard(
            name="segmentation",
            task="unsupervised behavioural grouping of customers",
            trained_at=report["trained_at"],
            train_window="2026-01..2026-05",
            validation_window="2026-06..2026-07",
            features=bundle["features"],
            metrics=json_safe(
                {
                    "silhouette": evaluation["silhouette"],
                    "inertia": evaluation["inertia"],
                    "cluster_sizes": evaluation["cluster_sizes"],
                    "mean_adjusted_rand_index_vs_behaviour_flags": alignment.get(
                        "mean_adjusted_rand_index"
                    ),
                    "temporal_adjusted_rand_index": stability.get("adjusted_rand_index"),
                    "temporal_identical_assignment_share": stability.get(
                        "identical_assignment_share"
                    ),
                }
            ),
            baselines=json_safe({"silhouette_by_k": evaluation["silhouette_by_k"]}),
            notes=(
                "KMeans on standardised user-level behavioural features; k chosen by "
                "silhouette. HDBSCAN was not used: it is not installed and on this "
                "population size it would return one cluster plus noise, which is "
                "indistinguishable from 'no structure'. Internal metrics are reported "
                "alongside adjusted Rand index against the generator's behaviour flags "
                "and against an independently refit segmentation on a longer history, "
                "because a silhouette can always be raised by adding clusters."
            ),
        ),
    )
    report["segmentation"] = {
        "fitted": True,
        "evaluation": json_safe(evaluation),
        "temporal_stability": json_safe(stability),
        "cluster_labels": {str(k): v.value for k, v in label_by_cluster.items()},
    }


# ---------------------------------------------------------------------------
# 4. health / resilience
# ---------------------------------------------------------------------------

def train_health(report: dict) -> None:
    _rule("4/4  Financial-health model (LightGBM, exact TreeSHAP)")
    splits = load_all_splits()
    profile = splits["train"].label("financial_profiles")
    behaviour = splits["train"].label("behavior_labels")
    if profile.empty:
        report["health"] = {"fitted": False, "reason": "financial_profiles.csv is empty"}
        print("  skipped: no financial_profiles labels")
        return

    folds: dict[str, dict] = {}
    for cut in ("train", "validation", "test"):
        features = build_features(cut).user
        folds[cut] = {
            "features": features,
            "supervised": ml_health.supervised_frame(features, profile, behaviour),
            "periods": build_features(cut).periods,
        }
        print(
            f"  fold '{cut}': {len(features)} customers built from "
            f"{folds[cut]['periods'][0]}..{folds[cut]['periods'][-1]}"
        )

    train_supervised = folds["train"]["supervised"]
    bundle = ml_health.train_health_models(train_supervised)
    bundle["train_matrix"] = ml_health.design_matrix(train_supervised, bundle["features"])
    print(f"  regressors fitted: {sorted(bundle['regressors'])}")
    print(f"  classifiers fitted: {sorted(bundle['classifiers'])}")
    if bundle["skipped"]:
        print(f"  skipped (too little data): {bundle['skipped']}")

    evaluation: dict = {"skipped": bundle["skipped"], "folds": {}}
    for cut in ("validation", "test"):
        fold = ml_health.evaluate(bundle, folds[cut]["supervised"], train_supervised)
        evaluation["folds"][cut] = fold
        print(f"\n  --- fold '{cut}' ---")
        for target, entry in fold["regression"].items():
            baseline = entry.get("train_mean_baseline", {}).get("mae")
            direct = evaluation.get("direct_feature_baseline", {}).get(target, {})
            line = (
                f"   {target:24s} MAE={entry['mae']:.4f} RMSE={entry['rmse']:.4f} "
                f"R2={entry['r2']:.3f}"
            )
            if baseline is not None:
                line += f"  | train-mean baseline MAE={baseline:.4f}"
            if direct:
                line += f" | direct-feature MAE={direct['mae']:.4f}"
            print(line)
        for target, entry in fold["classification"].items():
            auc = entry.get("roc_auc")
            print(
                f"   {target:24s} F1={entry['f1']:.3f} P={entry['precision']:.3f} "
                f"R={entry['recall']:.3f} AUC={auc if auc is None else round(auc, 3)} "
                f"(+{entry['positives']}/-{entry['negatives']})"
            )

    # ---- leakage probes. Run before anything is written to disk. --------
    evaluation["direct_feature_baseline"] = ml_health.direct_feature_baseline(
        folds["test"]["supervised"]
    )
    control = ml_health.null_control(train_supervised, folds["test"]["supervised"])
    evaluation["null_control"] = json_safe(control)
    print("\n  --- leakage probes ---")
    print("  direct feature baseline (no model, copy the engine feature):")
    for target, entry in evaluation["direct_feature_baseline"].items():
        print(f"   {target:24s} MAE={entry['mae']:.4f} R2={entry['r2']:.3f}")
    print("  null control (labels shuffled before fitting -- must be at chance):")
    for target, entry in control["regression"].items():
        print(f"   {target:24s} MAE={entry['mae']:.4f} R2={entry['r2']:.3f}")
    for target, entry in control["classification"].items():
        if entry.get("available") is False:
            continue
        auc = entry.get("roc_auc")
        print(
            f"   {target:24s} F1={entry['f1']:.3f} "
            f"AUC={auc if auc is None else round(auc, 3)}"
        )
    verdict = ml_health.honest_verdict(
        evaluation["folds"]["test"], evaluation["direct_feature_baseline"], control
    )
    evaluation["honest_verdict"] = verdict
    print("\n  --- verdict: did the model beat the trivial baselines? ---")
    for row in verdict:
        if row.get("task") == "regression":
            print(
                f"   {row['target']:24s} {row['verdict']:26s} "
                f"model MAE={row['model_mae']:.4f} "
                f"direct={row['direct_feature_baseline_mae']}"
            )
        else:
            print(
                f"   {row['target']:24s} {row['verdict']:26s} "
                f"model F1={row['model_f1']:.3f} "
                f"majority F1={row['majority_baseline_f1']} "
                f"null AUC={row['null_control_roc_auc']}"
            )
    evaluation["caveat"] = ml_health.leakage_by_construction_note()
    print("\n  CAVEAT:", evaluation["caveat"][:96], "...")

    save_bundle(
        "health",
        {
            "features": bundle["features"],
            "regressors": bundle["regressors"],
            "classifiers": bundle["classifiers"],
            "skipped": bundle["skipped"],
            "seed": bundle["seed"],
            "source": _split_source(),
            "protected_columns_excluded": list(ml_health.PROTECTED_COLUMNS),
        },
    )
    importance = ml_health.global_importance(bundle)
    save_card(
        "health",
        ModelCard(
            name="health",
            task="predict ground-truth financial profile + behaviour flags",
            trained_at=report["trained_at"],
            train_window="2026-01..2026-05",
            validation_window="2026-06..2026-07",
            features=bundle["features"],
            metrics=json_safe(
                {
                    cut: {
                        "regression": {
                            t: {"mae": e["mae"], "rmse": e["rmse"], "r2": e["r2"]}
                            for t, e in fold["regression"].items()
                        },
                        "classification": {
                            t: {"f1": e["f1"], "recall": e["recall"], "precision": e["precision"]}
                            for t, e in fold["classification"].items()
                        },
                    }
                    for cut, fold in evaluation["folds"].items()
                }
            ),
            baselines=json_safe(
                {
                    cut: {
                        t: e.get("train_mean_baseline")
                        for t, e in fold["regression"].items()
                    }
                    for cut, fold in evaluation["folds"].items()
                }
            ),
            notes=(
                ml_health.leakage_by_construction_note()
                + " || Expanding-window evaluation: the validation cut's features are built "
                "from 2026-01..07 and the test cut's from 2026-01..09, because the "
                "financial_profiles label is a full-horizon property of a customer. "
                "Protected attributes (age_group, occupation, location_type) are "
                "excluded from the design matrix so the score cannot become a proxy for "
                "who the customer is. Explanation uses LightGBM pred_contrib, which is "
                "exact TreeSHAP computed inside the model, not a sampled approximation. "
                "The customer-facing health score itself stays the deterministic ladder "
                "engine in app.engines.health; this model is a calibration layer that "
                "states its own error."
            ),
        ),
    )
    report["health"] = {
        "fitted": True,
        "caveat": evaluation["caveat"],
        "features": bundle["features"],
        "protected_columns_excluded": list(ml_health.PROTECTED_COLUMNS),
        "evaluation": json_safe(evaluation),
        "global_treeshap_importance": json_safe(importance),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    reset_cache()
    from app.core.config import settings
    from app.data.splits import splits_root

    root = splits_root()
    report: dict = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "source": str(root),
        "split_root_guard": "roots containing 'generated' are refused by app.data.splits",
        "splits": describe_all(),
        "disjoint_periods": assert_disjoint_periods(),
        "runtime": {
            "python_packages": {
                "lightgbm": _version("lightgbm"),
                "scikit_learn": _version("scikit-learn"),
                "xgboost": _version("xgboost"),
                "shap": _version("shap"),
                "pandas": _version("pandas"),
                "numpy": _version("numpy"),
            },
            "optional_missing": _missing(
                ("statsmodels", "hdbscan", "prophet")
            ),
            "data_root": str(settings.data_root),
        },
    }

    train_forecast(report)
    train_anomaly(report)
    train_segmentation(report)
    train_health(report)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(json_safe(report), indent=2), encoding="utf-8")
    print(f"\nEvaluation report -> {REPORT_PATH}")
    print(f"Model cards       -> {Path(__file__).resolve().parents[1] / 'artifacts'}")
    return 0


def _version(module: str) -> str:
    try:
        import importlib.metadata as metadata

        return metadata.version(module)
    except Exception:  # pragma: no cover - metadata is always present in practice
        return "not installed"


def _missing(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if _version(name) == "not installed"]


if __name__ == "__main__":
    raise SystemExit(main())