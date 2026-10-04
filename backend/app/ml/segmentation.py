"""Behavioural segmentation: KMeans on the user-level feature grain.

Two things this module does that the serving engine cannot
--------------------------------------------------------
1. **Trains and persists a fit from the split folders.** The engine
   (:mod:`app.engines.segmentation`) fits on whatever population it is handed,
   which is right for serving and wrong for measurement: a model that is refit
   on every request has no stable version to report metrics for.
2. **Measures whether the clusters are real.** Silhouette and inertia are
   internal metrics and are gameable by increasing k. So the fit is also
   scored against two external references that the clustering never saw:

   * ``labels/behavior_labels.csv`` -- the generator's own behaviour flags.
     Scored with adjusted Rand index and normalised mutual information.
   * the train/validation/test temporal folds -- adjusted Rand index between
     the cluster assignment from the *train-cut* fit and the assignment from the
     *validation-cut* fit for the same customers. A segmentation that reshuffles
     when a month of data arrives is a description of the sample, not of the
     customers.

HDBSCAN is deliberately not used. It is not installed, and on a 50-customer
development population it would return a single cluster plus noise labels,
which would be reported as "no structure found" and be indistinguishable from
a bug. The candidate set is therefore reported per k so the flatness of the
curve is visible instead of hidden behind one chosen number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 42
N_INIT = 20

K_CANDIDATES = (2, 3, 4, 5, 6)

# Behaviour flag -> the segmentation dimensions it should line up with.
BEHAVIOUR_REFERENCE: dict[str, tuple[str, ...]] = {
    "end_month_shortage_label": ("late_month_share", "late_month_share_max", "days_below_buffer"),
    "high_cash_dependency_label": ("cash_dependency", "has_cash_wallet"),
    "irregular_income_label": ("income_cv", "income_stability"),
    "overspending_label": ("expense_income_ratio", "months_negative_surplus"),
    "financial_pressure_label": ("emergency_buffer_months", "months_negative_surplus"),
    "goal_progress_label": ("goal_progress", "funding_consistency", "goal_count"),
}

NON_NUMERIC_COLUMNS = ("user_id", "top_category", "age_group", "occupation", "location_type")

MIN_USERS_PER_CLUSTER = 5
MIN_POPULATION = 20


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Sorted numeric behavioural columns, ids and display columns removed."""
    return sorted(
        column
        for column in frame.columns
        if column not in NON_NUMERIC_COLUMNS and pd.api.types.is_numeric_dtype(frame[column])
    )


def design_matrix(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    matrix = frame[columns].to_numpy(dtype=float)
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)


def max_candidates(population_size: int) -> int:
    ceiling = max(2, population_size // MIN_USERS_PER_CLUSTER)
    return max(2, min(ceiling, max(K_CANDIDATES)))


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def fit(
    frame: pd.DataFrame,
    columns: list[str] | None = None,
    n_clusters: int | None = None,
    seed: int = SEED,
) -> dict:
    """Fit scaler + KMeans, returning the whole bundle plus the k curve."""
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    columns = list(columns or feature_columns(frame))
    population = len(frame)
    if population < MIN_POPULATION or not columns:
        return {
            "fitted": False,
            "reason": (
                f"{population} customers with {len(columns)} features; "
                f"need >= {MIN_POPULATION} customers to score a silhouette."
            ),
            "population_size": population,
            "features": columns,
        }

    matrix = design_matrix(frame, columns)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)

    if n_clusters is not None:
        candidates = [int(max(1, min(n_clusters, population)))]
        chosen_by = "requested"
    else:
        ceiling = max_candidates(population)
        candidates = [k for k in K_CANDIDATES if k <= ceiling] or [2]
        chosen_by = "silhouette"

    silhouette_by_k: dict[int, float] = {}
    inertia_by_k: dict[int, float] = {}
    best: tuple[int, float] = (candidates[0], float("-inf"))

    from sklearn.metrics import silhouette_score

    for k in candidates:
        model = KMeans(n_clusters=k, n_init=N_INIT, random_state=seed)
        labels = model.fit_predict(scaled)
        inertia_by_k[k] = float(model.inertia_)
        score = float("-inf")
        if len(set(labels.tolist())) > 1:
            try:
                score = float(silhouette_score(scaled, labels))
            except ValueError:
                score = float("-inf")
        if score > float("-inf"):
            silhouette_by_k[k] = round(score, 4)
        if score > best[1]:
            best = (k, score)

    best_k = best[0]
    model = KMeans(n_clusters=best_k, n_init=N_INIT, random_state=seed)
    labels = model.fit_predict(scaled)

    return {
        "fitted": True,
        "scaler": scaler,
        "model": model,
        "features": columns,
        "n_clusters": int(best_k),
        "silhouette": round(best[1], 4) if best[1] > float("-inf") else None,
        "inertia": float(model.inertia_),
        "silhouette_by_k": silhouette_by_k,
        "inertia_by_k": {k: round(v, 4) for k, v in inertia_by_k.items()},
        "chosen_by": chosen_by,
        "k_candidates": candidates,
        "population_size": population,
        "seed": seed,
    }


def assign(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    """Cluster ids for rows of ``frame`` under an existing fit."""
    matrix = bundle["scaler"].transform(design_matrix(frame, bundle["features"]))
    return bundle["model"].predict(matrix)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def cluster_profiles(bundle: dict, frame: pd.DataFrame, labels: np.ndarray) -> list[dict]:
    """Per-cluster mean of every feature, plus the population mean for contrast."""
    columns = bundle["features"]
    population_mean = frame[columns].mean()
    out: list[dict] = []
    for cluster in sorted(set(int(x) for x in labels)):
        mask = labels == cluster
        members = frame.loc[mask, columns]
        deltas = (members.mean() - population_mean) / frame[columns].std(ddof=0).replace(0, np.nan)
        ranked = deltas.abs().sort_values(ascending=False).head(3)
        out.append(
            {
                "cluster_id": cluster,
                "size": int(mask.sum()),
                "share": round(float(mask.mean()), 4),
                "mean_profile": {c: round(float(members[c].mean()), 4) for c in columns},
                "top_distinctive": [
                    {
                        "feature": feature,
                        "cluster_mean": round(float(members[feature].mean()), 4),
                        "population_mean": round(float(population_mean[feature]), 4),
                        "standardised_difference": round(float(ranked[feature]), 4),
                    }
                    for feature in ranked.index
                ],
            }
        )
    return out


def external_alignment(bundle: dict, frame: pd.DataFrame, labels: np.ndarray,
                       behavior_labels: pd.DataFrame) -> dict:
    """Agreement between the clusters and the generator's behaviour flags."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    if behavior_labels.empty:
        return {"available": False}

    reference = (
        behavior_labels.groupby("user_id", observed=True)
        .max(numeric_only=True)
        .reset_index()
    )
    shared = frame[["user_id"]].merge(reference, on="user_id", how="inner")
    if len(shared) < MIN_POPULATION:
        return {"available": False, "reason": f"only {len(shared)} shared users"}

    position = {user_id: i for i, user_id in enumerate(frame["user_id"].tolist())}
    index = [position[u] for u in shared["user_id"] if u in position]
    shared = shared.loc[[u in position for u in shared["user_id"]]]
    cluster_ids = np.asarray(labels)[index]

    per_flag: dict[str, dict] = {}
    for flag, dimensions in BEHAVIOUR_REFERENCE.items():
        if flag not in shared.columns:
            continue
        values = shared[flag].to_numpy(dtype=int)
        if len(set(values.tolist())) < 2 or len(set(cluster_ids.tolist())) < 2:
            per_flag[flag] = {"available": False, "reason": "constant label"}
            continue
        per_flag[flag] = {
            "available": True,
            "adjusted_rand_index": round(float(adjusted_rand_score(values, cluster_ids)), 4),
            "normalised_mutual_information": round(
                float(normalized_mutual_info_score(values, cluster_ids)), 4
            ),
            "expected_dimensions": list(dimensions),
            "n": int(len(values)),
            "positives": int(values.sum()),
        }

    usable = [v for v in per_flag.values() if v.get("available")]
    return {
        "available": True,
        "n_users": int(len(shared)),
        "flags": per_flag,
        "mean_adjusted_rand_index": round(
            float(np.mean([v["adjusted_rand_index"] for v in usable])), 4
        )
        if usable
        else None,
    }


def temporal_stability(
    bundle_train: dict,
    frame_train: pd.DataFrame,
    bundle_validation: dict | None,
    frame_validation: pd.DataFrame | None,
) -> dict:
    """Adjusted Rand index between two independently fitted segmentations.

    Both fits see the same 50 customers but different amounts of history
    (train cut vs validation cut). High agreement means the groups describe
    the customers; low agreement means they describe whichever months were
    available.
    """
    from sklearn.metrics import adjusted_rand_score

    if not bundle_train.get("fitted") or bundle_validation is None:
        return {"available": False, "reason": "no comparison fit"}
    if not bundle_validation.get("fitted") or frame_validation is None:
        return {"available": False, "reason": "validation fit unavailable"}

    labels_train = assign(bundle_train, frame_train)
    labels_validation = assign(bundle_validation, frame_validation)
    position = {u: i for i, u in enumerate(frame_validation["user_id"].tolist())}
    shared = [u for u in frame_train["user_id"].tolist() if u in position]
    if len(shared) < MIN_POPULATION:
        return {"available": False, "reason": f"only {len(shared)} shared customers"}
    a = np.asarray([labels_train[frame_train["user_id"].tolist().index(u)] for u in shared])
    b = np.asarray([labels_validation[position[u]] for u in shared])
    return {
        "available": True,
        "n_users": len(shared),
        "adjusted_rand_index": round(float(adjusted_rand_score(a, b)), 4),
        "identical_assignment_share": round(float((a == b).mean()), 4),
        "train_k": bundle_train["n_clusters"],
        "validation_k": bundle_validation["n_clusters"],
    }


def evaluate(bundle: dict, frame: pd.DataFrame, behavior_labels: pd.DataFrame) -> dict:
    labels = assign(bundle, frame)
    return {
        "n_clusters": bundle["n_clusters"],
        "silhouette": bundle["silhouette"],
        "inertia": round(float(bundle["inertia"]), 4),
        "silhouette_by_k": bundle["silhouette_by_k"],
        "inertia_by_k": bundle["inertia_by_k"],
        "chosen_by": bundle["chosen_by"],
        "k_candidates": bundle["k_candidates"],
        "population_size": bundle["population_size"],
        "clusters": cluster_profiles(bundle, frame, labels),
        "external_alignment": external_alignment(bundle, frame, labels, behavior_labels),
        "cluster_sizes": {
            str(int(k)): int((labels == k).sum()) for k in sorted(set(labels.tolist()))
        },
    }