"""Behavioural segmentation evaluation.

A silhouette score is a *relative* number: it always improves if you allow more
clusters, and it says nothing about whether the groups describe customers or
merely the sample. This module therefore reports four kinds of evidence
together:

1. **Internal** -- the silhouette / Davies-Bouldin / Calinski-Harabasz curve
   across every candidate ``k``, not just the chosen one, so the flatness of the
   curve is visible.
2. **Against generator ground truth** -- adjusted Rand index and normalised
   mutual information against the eight ``persona`` labels the dataset was
   generated from. The clustering never sees them.
3. **Against behaviour flags** -- ARI against ``behavior_labels``.
4. **Temporal stability** -- ARI between the fit built on the train cut and an
   independent fit built on the validation cut. A segmentation that reshuffles
   when a month of data arrives describes the month, not the customer.

Persona recovery
----------------
The 500-user splits ship ``features/users.csv`` with the persona column stripped
(it is a generator-side label). It is recovered by replaying the generator's own
seeded call -- :func:`ml.dataset.users.generate_users` with ``seed=42`` -- and is
only trusted after every ``user_id``/age/occupation/location/tenure tuple has
been checked against the shipped file. If any row disagrees the recovery is
discarded and the persona block reports ``available: false`` rather than
silently scoring against the wrong reference.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.evaluation.datasets import Dataset

IDENTITY_COLUMNS = (
    "user_id",
    "age_group",
    "occupation",
    "location_type",
    "account_age_days",
)


def recover_personas(dataset: Dataset) -> tuple[pd.DataFrame, dict]:
    """Regenerate the generator's persona column and verify it matches."""
    reference = dataset.features.get("users")
    if reference is None:
        reference = _load_user_features(dataset)
        dataset.features["users"] = reference

    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[3] / "ml"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from dataset import config as gen_config
        from dataset.users import generate_users
    except Exception as exc:  # pragma: no cover - generator not importable
        return pd.DataFrame(columns=["user_id", "persona"]), {
            "available": False,
            "reason": f"generator not importable: {exc}",
        }

    try:
        recovered = generate_users(
            np.random.default_rng(gen_config.SEED),
            gen_config.NUM_USERS,
            gen_config.MONTHS,
            named=False,
        )[list(IDENTITY_COLUMNS) + ["persona"]]
    except Exception as exc:  # pragma: no cover - regeneration failed
        return pd.DataFrame(columns=["user_id", "persona"]), {
            "available": False,
            "reason": f"persona regeneration failed: {exc}",
        }

    left = recovered[list(IDENTITY_COLUMNS)]
    right = reference[[c for c in IDENTITY_COLUMNS if c in reference.columns]]
    joined = left.merge(right, on="user_id", suffixes=("_recovered", "_shipped"))
    mismatches = 0
    for column in IDENTITY_COLUMNS[1:]:
        a, b = f"{column}_recovered", f"{column}_shipped"
        if a in joined.columns and b in joined.columns:
            mismatches += int((joined[a] != joined[b]).sum())

    if mismatches or len(joined) != len(reference):
        return pd.DataFrame(columns=["user_id", "persona"]), {
            "available": False,
            "reason": (
                f"recovered personas do not reproduce the shipped user table "
                f"({mismatches} mismatches across {len(joined)} joined rows)"
            ),
        }

    distribution = recovered["persona"].value_counts().to_dict()
    return recovered, {
        "available": True,
        "method": (
            "replayed ml.dataset.users.generate_users(seed=42, n=500) and "
            "verified all four identity columns against features/users.csv"
        ),
        "n_verified": int(len(joined)),
        "mismatches": mismatches,
        "persona_distribution": {str(k): int(v) for k, v in distribution.items()},
        "n_personas": int(len(distribution)),
        "note": (
            "Persona is a generator-side label and is never a feature. It is "
            "used here only as an external reference the clustering never saw."
        ),
    }


def _load_user_features(dataset: Dataset) -> pd.DataFrame:
    """Identity columns only -- the shipped ``features/users.csv``.

    This table is deliberately *not* the clustering grain: it carries five
    columns, four of which are protected attributes. It is used here purely as
    the reference the recovered personas are verified against.
    """
    return dataset.splits["train"].feature("users")


def _user_frame(dataset: Dataset, cut: str) -> pd.DataFrame:
    """The engineered one-row-per-customer frame, built the trainer's way."""
    from app.data.splits import build_features

    return build_features(cut).user


def persona_alignment(
    dataset: Dataset, frame: pd.DataFrame, labels: np.ndarray
) -> dict:
    """ARI / NMI between the clusters and the generator's personas."""
    from app.evaluation.metrics import agreement_metrics

    recovered, status = recover_personas(dataset)
    if not status.get("available"):
        return status

    position = {user_id: i for i, user_id in enumerate(frame["user_id"].tolist())}
    shared = recovered[recovered["user_id"].isin(position)]
    if len(shared) < 20:
        return {
            "available": False,
            "reason": f"only {len(shared)} persona-labelled customers in the frame",
        }

    index = [position[u] for u in shared["user_id"]]
    scores = agreement_metrics(shared["persona"].to_numpy(), np.asarray(labels)[index])

    # Per-persona recall: which generator personas did the clustering split or merge?
    per_persona: dict[str, dict] = {}
    predicted = np.asarray(labels)[index]
    truth = shared["persona"].to_numpy()
    for persona in sorted(set(truth.tolist())):
        mask = truth == persona
        counts = pd.Series(predicted[mask]).value_counts()
        per_persona[persona] = {
            "n": int(mask.sum()),
            "concentrated_in_cluster": int(counts.index[0]) if len(counts) else None,
            "concentration_share": round(float(counts.iloc[0] / mask.sum()), 4)
            if len(counts)
            else None,
            "spread_over_clusters": int(len(counts)),
        }

    return {
        **status,
        **scores,
        "n_clusters": int(len(np.unique(labels))),
        "n_personas": int(len(set(truth.tolist()))),
        "per_persona": per_persona,
        "interpretation": (
            "ARI is chance-corrected: 0 means the two partitions are unrelated, "
            "1 means identical, and negative means worse than random. A "
            "behavioural segmentation is not required to reproduce the persona "
            "taxonomy -- personas also encode life circumstances the ledger "
            "cannot show -- so this is reported as a reference point, not a "
            "pass/fail gate."
        ),
    }


def run(dataset: Dataset, verbose: bool = False) -> dict:
    """Fit, score and stress-test the segmentation."""
    from app.ml import segmentation as ml_segmentation

    train_features = dataset.build_frame(
        "features_train", lambda: _user_frame(dataset, "train")
    )
    validation_features = dataset.build_frame(
        "features_validation", lambda: _user_frame(dataset, "validation")
    )

    bundle = ml_segmentation.fit(train_features)
    if not bundle.get("fitted"):
        return {"fitted": False, "reason": bundle.get("reason")}
    if verbose:
        print(
            f"  k chosen by {bundle['chosen_by']} = {bundle['n_clusters']}  "
            f"silhouette curve {bundle['silhouette_by_k']}"
        )

    labels = ml_segmentation.assign(bundle, train_features)
    curves = _curves(bundle)
    evaluation = ml_segmentation.evaluate(bundle, train_features, dataset.behaviour_labels)
    persona = persona_alignment(dataset, train_features, labels)

    validation_bundle = ml_segmentation.fit(validation_features)
    stability = ml_segmentation.temporal_stability(
        bundle, train_features, validation_bundle, validation_features
    )

    # k-sensitivity: an alternative cut that picks a different k is the
    # clearest possible demonstration that the silhouette curve is flat.
    k_sensitivity = {
        "chosen_k_train_cut": bundle["n_clusters"],
        "chosen_k_validation_cut": validation_bundle.get("n_clusters"),
        "agreement": stability.get("adjusted_rand_index"),
        "identical_assignment_share": stability.get("identical_assignment_share"),
    }

    if verbose:
        print(f"  silhouette curve: {bundle['silhouette_by_k']}")
        if persona.get("available"):
            print(
                f"  persona ARI={persona['adjusted_rand_index']} "
                f"NMI={persona['normalized_mutual_information']} "
                f"(n={persona['n']} of {persona['n_personas']} personas)"
            )
        if stability.get("available"):
            print(
                f"  temporal stability ARI={stability['adjusted_rand_index']} "
                f"identical={stability['identical_assignment_share']}"
            )

    return {
        "task": "unsupervised behavioural grouping of customers",
        "algorithm": "KMeans on standardised user-level behavioural features",
        "fitted": True,
        "n_clusters": bundle["n_clusters"],
        "chosen_by": bundle["chosen_by"],
        "k_candidates": bundle["k_candidates"],
        "population_size": bundle["population_size"],
        "features": bundle["features"],
        "internal_metrics": curves,
        "clusters": evaluation["clusters"],
        "cluster_sizes": evaluation["cluster_sizes"],
        "persona_alignment": persona,
        "behaviour_flag_alignment": evaluation["external_alignment"],
        "temporal_stability": stability,
        "k_sensitivity": k_sensitivity,
        "why_not_hdbscan": (
            "HDBSCAN is not installed, and on a population this size it would "
            "return one cluster plus noise -- which is indistinguishable from a "
            "bug. The candidate set is reported per k instead so the shape of "
            "the curve is visible."
        ),
        "seed": bundle["seed"],
    }


def _curves(bundle: dict) -> dict:
    """Silhouette / inertia per candidate k, plus internal scores at the choice."""
    return {
        "silhouette_by_k": bundle["silhouette_by_k"],
        "inertia_by_k": bundle["inertia_by_k"],
        "chosen_k": bundle["n_clusters"],
        "chosen_silhouette": bundle["silhouette"],
        "flatness_note": (
            "A shallow silhouette curve means the population is a continuum "
            "rather than a set of discrete types; the chosen k is then a "
            "useful summary, not a discovered structure."
        ),
    }
