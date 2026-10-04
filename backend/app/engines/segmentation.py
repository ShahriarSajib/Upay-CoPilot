"""Behavioural segmentation: unsupervised groups a customer can recognise.

Why K-Means and nothing cleverer
--------------------------------
A segment here is a *conversation starter*, not a prediction. It exists so the
product can say "your spending lands late in the month, like most customers in
your group" and point at a relevant plan. That rules out anything with more
capacity than the question can carry: with 40 standardised features and a few
hundred customers, a tree ensemble would find real structure and then produce
labels nobody can act on and could not defend to a customer who asked why.

Three decisions carry the design.

1. **Standardise, then cluster.** The features are mixed units -- taka, ratios,
   counts -- and unstandardised K-Means would partition on ``ending_balance``
   alone, which is a statement about the generator's opening balances rather
   than about behaviour. On standardised features the clusters separate on
   habits: saving, cash reliance, income variation, late-month concentration.
2. **Choose k by silhouette, and publish the curve.** ``silhouette_by_k`` is
   returned alongside the winner. A k chosen by a rule nobody can inspect is a
   rule nobody can defend, and on a population this size the honest reading of
   the curve is often "the shape is stable between 3 and 5".
3. **Names are assigned from the centroid's own z-scores, deterministically.**
   Each cluster is scored against a fixed set of archetype definitions, and the
   best unused match wins. No naming model, no sampling, no ordering dependence:
   the same features always produce the same label.

Small populations get an explicit, honest fallback rather than a number nobody
should trust: below :data:`MIN_POPULATION_FOR_CLUSTERING` customers, distances
in 40 dimensions are dominated by noise, so clustering is skipped and the
segment comes from the ground-truth persona column with a note saying so. That
note is the product requirement -- a plausible-looking cluster id on 50 users is
worse than an admission. The persona column is read for that fallback and for
offline checking only; it is never a clustering feature and never an archetype
key, because letting it into the matrix would produce segments that trivially
reproduce the generator's own labels.

Four constants carry most of the behaviour, and each is chosen rather than
measured:

* :data:`SEGMENT_RANDOM_STATE` is fixed because the same dataset must give the
  same clusters in the same order on every process. Without it a customer's
  segment label could change between two page loads.
* :data:`SILHOUETTE_CANDIDATES` is capped so no cluster is a handful of people:
  the largest k tried is also bounded by population size divided by
  :data:`MIN_USERS_PER_CLUSTER`.
* :data:`MIN_ARCHETYPE_AFFINITY` is the bar a cluster must clear to be given a
  behavioural name. Below it the cluster sits close enough to the population
  average that naming it would describe noise, so it is "balanced regulars".
* :data:`DUPLICATE_FEATURE_CORRELATION` exists because several features are one
  measurement twice -- goal funding by count and by consistency, standing bills
  by two aggregations -- and three near-identical numbers tell the customer one
  thing in three ways. When describing a cluster, near-duplicates are skipped.

A final detail that matters for the reader rather than the model: a cluster's
three distinctive features are ranked by absolute z-score, not by raw size, so a
group is described by what is *unusual* about it rather than by whichever
quantity happens to have the largest taka values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from app.core.context import get_context
from app.db.store import cached_store
from app.features.build import build_all
from app.schemas.common import Direction
from app.schemas.wellbeing import (
    FeatureDelta,
    PopulationSegment,
    SegmentationFit,
    SegmentBasis,
    SegmentLabel,
    UserSegmentProfile,
)

SEGMENT_RANDOM_STATE = 42
KMEANS_N_INIT = 20

MIN_POPULATION_FOR_CLUSTERING = 20

SILHOUETTE_CANDIDATES = (2, 3, 4, 5, 6)
MIN_USERS_PER_CLUSTER = 10

DISTINCTIVE_FEATURE_COUNT = 3
NEUTRAL_Z = 0.05

MIN_ARCHETYPE_AFFINITY = 0.35

DUPLICATE_FEATURE_CORRELATION = 0.9

NON_NUMERIC_COLUMNS = ("user_id", "top_category", "age_group", "occupation", "location_type")

FEATURE_LABELS: dict[str, str] = {
    "months_observed": "months of history",
    "monthly_income": "average monthly income",
    "monthly_expense": "average monthly spending",
    "monthly_surplus": "average left over after spending",
    "savings_rate": "share of income kept after spending",
    "expense_income_ratio": "spending as a share of income",
    "late_month_share": "share of spending in the last third of the month",
    "late_month_share_max": "worst month for late spending",
    "cash_dependency": "share of spending paid in cash",
    "recurring_obligation_ratio": "share of spending that is a standing bill",
    "small_purchase_ratio": "share of spending in small purchases",
    "monthly_recurring_amount": "monthly standing bills",
    "monthly_cash_out": "amount moved to cash each month",
    "txn_per_month": "transactions per month",
    "anomaly_events": "unusual charges flagged",
    "goal_contribution_monthly": "average monthly contribution to goals",
    "funding_months": "months a goal was funded",
    "funding_consistency": "how reliably a goal is funded",
    "ending_balance": "balance at the end of the window",
    "mean_balance": "average balance",
    "min_balance": "lowest balance",
    "balance_volatility": "day-to-day balance swings",
    "months_negative_surplus": "months where spending exceeded income",
    "income_cv": "how much income varies month to month",
    "income_stability": "steadiness of income",
    "digital_ratio": "share of spending paid digitally",
    "days_below_buffer": "days spent below the minimum balance line",
    "low_balance_frequency": "how often the balance runs low",
    "category_entropy": "spread of spending across categories",
    "goal_count": "open savings goals",
    "goal_progress": "progress toward savings goals",
    "goal_target_total": "total target across goals",
    "goals_achieved": "goals reached",
    "mandatory_obligation_amount": "mandatory monthly commitments",
    "obligation_count": "standing bills",
    "emergency_buffer_months": "months of spending covered by the balance",
    "has_cash_wallet": "holds a cash wallet",
    "wallet_count": "wallets on the account",
    "account_age_days": "days since the account opened",
    "account_age_months": "months since the account opened",
}

SEGMENT_ARCHETYPES: dict[SegmentLabel, dict[str, float]] = {
    SegmentLabel.STEADY_BUILDERS: {
        "savings_rate": 1.0,
        "funding_consistency": 0.5,
        "emergency_buffer_months": 1.0,
        "income_cv": -1.0,
        "cash_dependency": -0.5,
    },
    SegmentLabel.GOAL_DRIVEN_PLANNERS: {
        "goal_progress": 1.0,
        "goal_count": 0.75,
        "goal_contribution_monthly": 1.0,
        "funding_consistency": 0.75,
    },
    SegmentLabel.MONTH_END_STRETCHERS: {
        "late_month_share": 1.0,
        "late_month_share_max": 0.75,
        "low_balance_frequency": 1.0,
        "days_below_buffer": 0.5,
        "savings_rate": -0.75,
    },
    SegmentLabel.VOLATILE_IRREGULAR_EARNERS: {
        "income_cv": 1.0,
        "savings_rate": -0.5,
        "emergency_buffer_months": -0.5,
    },
    SegmentLabel.CASH_LEANING_SPENDERS: {
        "cash_dependency": 1.0,
        "monthly_cash_out": 1.0,
        "digital_ratio": -1.0,
    },
    SegmentLabel.SEASONAL_SPENDERS: {
        "expense_income_ratio": 1.0,
        "savings_rate": -0.5,
        "late_month_share": 0.5,
    },
    SegmentLabel.SHOCK_PRONE_SPENDERS: {
        "anomaly_events": 1.0,
        "balance_volatility": 0.5,
        "months_negative_surplus": 0.75,
    },
    SegmentLabel.SPENDING_AHEAD_OF_EARNINGS: {
        "expense_income_ratio": 1.0,
        "months_negative_surplus": 1.0,
        "emergency_buffer_months": -1.0,
        "savings_rate": -1.0,
    },
    SegmentLabel.BALANCED_REGULARS: {
        "savings_rate": 0.25,
        "income_cv": -0.25,
        "emergency_buffer_months": 0.25,
        "late_month_share": 0.25,
    },
}

PERSONA_SEGMENT_LABELS: dict[str, SegmentLabel] = {
    "stable_saver": SegmentLabel.STEADY_BUILDERS,
    "goal_oriented": SegmentLabel.GOAL_DRIVEN_PLANNERS,
    "end_month_shortage": SegmentLabel.MONTH_END_STRETCHERS,
    "irregular_income": SegmentLabel.VOLATILE_IRREGULAR_EARNERS,
    "high_cash_dependency": SegmentLabel.CASH_LEANING_SPENDERS,
    "seasonal_spender": SegmentLabel.SEASONAL_SPENDERS,
    "sudden_anomaly": SegmentLabel.SHOCK_PRONE_SPENDERS,
    "financial_pressure": SegmentLabel.SPENDING_AHEAD_OF_EARNINGS,
}

UNKNOWN_SEGMENT_LABEL = SegmentLabel.BALANCED_REGULARS

_CACHE: dict[str, object] = {}


def _persona_by_user() -> dict[str, str]:
    """Ground-truth behaviour type per customer, read from the user table.

    Used only for the small-population fallback and for reporting. It is never a
    clustering feature and never an archetype key: letting it into the matrix
    would produce segments that trivially reproduce the generator's own labels.
    """
    users = cached_store().users()
    if "persona" not in users.columns:
        return {}
    return dict(zip(users["user_id"].astype(str), users["persona"].astype(str)))


def _population_signature() -> tuple[str, int, str, int]:
    store = cached_store()
    users = store.users()
    return (
        str(store.root),
        int(len(users)),
        store.as_of_date().date().isoformat(),
        len(store.periods()),
    )


def population_features() -> pd.DataFrame:
    """The whole population's user-level feature frame, built once per process.

    Uses :func:`app.features.build.build_all` so the segmentation grain is the
    same frame every other engine reads, including the non-numeric columns that
    get excluded below. Cached against the dataset signature, because the dev
    and full populations are different sizes and must not share a fit.
    """
    signature = _population_signature()
    if _CACHE.get("signature") != signature:
        store = cached_store()
        _CACHE["frame"] = build_all(
            store.transactions(),
            store.wallets(),
            store.users(),
            store.recurring(),
            store.goals(),
            store.contributions(),
        )["user"]
        _CACHE["signature"] = signature
        _CACHE.pop("fit", None)
    frame = _CACHE.get("frame")
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def reset_segmentation_cache() -> None:
    """Drop the cached population frame and fit. Used by tests and dataset swaps."""
    _CACHE.clear()


def _feature_columns(frame: pd.DataFrame) -> list[str]:
    columns = [
        column
        for column in frame.columns
        if column not in NON_NUMERIC_COLUMNS and pd.api.types.is_numeric_dtype(frame[column])
    ]
    return sorted(columns)


def _design_matrix(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """Feature matrix with non-finite values collapsed to zero.

    ``user_features`` already fills gaps with zero; this is the guard for a
    production frame where a column can still be empty, because one NaN would
    otherwise propagate through the scaler into every centroid.
    """
    matrix = frame[columns].to_numpy(dtype=float)
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)


def _money(value: float) -> float:
    return round(float(value) + 0.0, 2)


def _ratio(value: float) -> float:
    return round(float(value) + 0.0, 4)


def _direction(standardised: float) -> Direction:
    if standardised > NEUTRAL_Z:
        return Direction.INCREASE
    if standardised < -NEUTRAL_Z:
        return Direction.DECREASE
    return Direction.FLAT


def _feature_delta(
    column: str,
    cluster_mean: float,
    population_mean: float,
    standardised: float,
) -> FeatureDelta:
    return FeatureDelta(
        feature=column,
        label=FEATURE_LABELS.get(column, column.replace("_", " ")),
        cluster_mean=_ratio(cluster_mean),
        population_mean=_ratio(population_mean),
        standardised_difference=_ratio(standardised),
        direction=_direction(standardised),
    )


def _affinities(centroid: np.ndarray, columns: list[str]) -> dict[SegmentLabel, float]:
    position = {column: index for index, column in enumerate(columns)}
    scores: dict[SegmentLabel, float] = {}
    for label, expectations in SEGMENT_ARCHETYPES.items():
        terms = [
            sign * float(centroid[position[name]])
            for name, sign in expectations.items()
            if name in position
        ]
        scores[label] = float(np.mean(terms)) if terms else float("-inf")
    return scores


def _assign_labels(
    centroids: np.ndarray, columns: list[str]
) -> tuple[dict[int, SegmentLabel], bool]:
    """One archetype per cluster, with no behavioural name used twice.

    Clusters are served in descending order of their best affinity, so the
    clearest cluster gets its clearest name. Afterwards, a cluster that matched
    nothing convincingly is renamed "balanced regulars": a generic label is more
    honest than a confident wrong one, and it is the only honest thing to say
    about a cluster whose centroid sits near the middle of the population. The
    second element of the result reports whether that happened, so the fit can
    say so in its notes.
    """
    scores = {index: _affinities(centroid, columns) for index, centroid in enumerate(centroids)}
    order = sorted(
        scores,
        key=lambda index: (
            -max(scores[index][label] for label in SEGMENT_ARCHETYPES if label is not UNKNOWN_SEGMENT_LABEL),
            index,
        ),
    )
    taken: set[SegmentLabel] = set()
    assigned: dict[int, SegmentLabel] = {}
    matched: dict[int, float] = {}
    for index in order:
        for label in sorted(
            (item for item in scores[index] if item is not UNKNOWN_SEGMENT_LABEL),
            key=lambda item: (-scores[index][item], item.value),
        ):
            if label not in taken:
                assigned[index] = label
                taken.add(label)
                matched[index] = scores[index][label]
                break
        else:
            assigned[index] = UNKNOWN_SEGMENT_LABEL
            matched[index] = 0.0
    generic_used = False
    weak = [index for index in order if matched[index] < MIN_ARCHETYPE_AFFINITY]
    if weak:
        weakest = min(weak, key=lambda index: (matched[index], index))
        assigned[weakest] = UNKNOWN_SEGMENT_LABEL
        generic_used = True
    return assigned, generic_used


def _distinctive_features(
    centroid: np.ndarray,
    columns: list[str],
    frame: pd.DataFrame,
    population_means: pd.Series,
    correlation: pd.DataFrame,
) -> list[FeatureDelta]:
    """The features where this group sits furthest from the population mean.

    Ranked by absolute z-score rather than by raw size, so a group is described
    by what is *unusual* about it: a cluster whose largest raw gap is a balance
    difference would otherwise be labelled by the generator's opening balances.
    A feature that moves almost identically to one already chosen is skipped, so
    the three entries describe three different behaviours.
    """
    order = sorted(range(len(columns)), key=lambda index: -abs(float(centroid[index])))
    chosen: list[int] = []
    for index in order:
        column = columns[index]
        if any(
            abs(float(correlation.at[column, columns[picked]])) >= DUPLICATE_FEATURE_CORRELATION
            for picked in chosen
        ):
            continue
        chosen.append(index)
        if len(chosen) == DISTINCTIVE_FEATURE_COUNT:
            break
    for index in order:
        if len(chosen) == DISTINCTIVE_FEATURE_COUNT:
            break
        if index not in chosen:
            chosen.append(index)
    return [
        _feature_delta(
            columns[index],
            float(frame[columns[index]].mean()),
            float(population_means[columns[index]]),
            float(centroid[index]),
        )
        for index in chosen
    ]


def _small_population_note(population_size: int) -> str:
    return (
        f"Clustering needs the full population. This dataset holds {population_size} "
        f"customer{'s' if population_size != 1 else ''}, below the "
        f"{MIN_POPULATION_FOR_CLUSTERING} needed for stable groups in this many dimensions, "
        "so no clusters are published and each customer is described by their recorded "
        "behaviour type instead."
    )


def _persona_segments(frame: pd.DataFrame, columns: list[str]) -> list[PopulationSegment]:
    """One stand-in segment for the whole population, from the recorded types.

    Deliberately a single segment rather than one per recorded behaviour type:
    a group of four customers is not a segment, and publishing eight of them
    would dress up a small dataset as a segmentation result. The note names the
    types on file so the reader can see what the stand-in is made of.
    """
    size = len(frame)
    by_user = _persona_by_user()
    if "user_id" in frame.columns:
        personas = frame["user_id"].astype(str).map(by_user).fillna("unknown")
    else:
        personas = pd.Series(["unknown"] * size, index=frame.index, dtype=str)
    mix = personas.value_counts()
    types = ", ".join(f"{name} ({count})" for name, count in mix.items())
    return [
        PopulationSegment(
            cluster_id=0,
            cluster_label=UNKNOWN_SEGMENT_LABEL.value,
            basis=SegmentBasis.PERSONA,
            size=int(size),
            share=1.0,
            mean_profile={column: _ratio(float(frame[column].mean())) for column in columns},
            distinctive_features=[],
            note=(
                f"{_small_population_note(size)} This single segment stands in for all "
                f"{size} of them. Recorded behaviour types on file: {types}. Each customer "
                "still sees the label for their own recorded type."
            ),
        )
    ]


def _unavailable_segments() -> list[PopulationSegment]:
    return [
        PopulationSegment(
            cluster_id=0,
            cluster_label=UNKNOWN_SEGMENT_LABEL.value,
            basis=SegmentBasis.UNAVAILABLE,
            size=0,
            share=0.0,
            mean_profile={},
            distinctive_features=[],
            note="No customer features are available from this dataset, so no segment can be assigned.",
        )
    ]


def _max_candidates(population_size: int) -> int:
    """The largest k worth trying, so no cluster is a handful of customers."""
    by_size = max(2, population_size // MIN_USERS_PER_CLUSTER)
    return max(2, min(by_size, max(SILHOUETTE_CANDIDATES)))


def _fit_clusters(
    scaled: np.ndarray, candidates: list[int]
) -> tuple[int, dict[int, float], dict[int, float]]:
    """Fit each candidate k and keep the best silhouette score.

    A k that collapses into one cluster, or a population too small for the
    metric, is dropped from the published curve rather than reported as zero:
    a zero would read as "these groups are identical" instead of "this number
    cannot be computed here".
    """
    silhouette_by_k: dict[int, float] = {}
    inertia_by_k: dict[int, float] = {}
    best_k = candidates[0]
    best_score = float("-inf")
    for k in candidates:
        model = KMeans(
            n_clusters=k,
            n_init=KMEANS_N_INIT,
            random_state=SEGMENT_RANDOM_STATE,
        )
        labels = model.fit_predict(scaled)
        inertia_by_k[k] = float(model.inertia_)
        score = float("-inf")
        if len(set(labels.tolist())) > 1:
            try:
                score = float(silhouette_score(scaled, labels))
            except ValueError:
                score = float("-inf")
        if score > best_score:
            best_score = score
            best_k = k
        if score > float("-inf"):
            silhouette_by_k[k] = _ratio(score)
    return best_k, silhouette_by_k, inertia_by_k


def _build_fit(
    frame: pd.DataFrame,
    columns: list[str],
    n_clusters: int | None,
) -> SegmentationFit:
    notes: list[str] = []
    population_size = len(frame)
    if population_size == 0 or not columns:
        return SegmentationFit(
            n_clusters=0,
            basis=SegmentBasis.UNAVAILABLE,
            population_size=population_size,
            feature_count=len(columns),
            features=columns,
            notes=["No usable customer features were found in this dataset."],
            segments=_unavailable_segments(),
            seed=SEGMENT_RANDOM_STATE,
        )

    if population_size < MIN_POPULATION_FOR_CLUSTERING:
        notes.append(_small_population_note(population_size))
        return SegmentationFit(
            n_clusters=0,
            basis=SegmentBasis.PERSONA,
            population_size=population_size,
            feature_count=len(columns),
            features=columns,
            segments=_persona_segments(frame, columns),
            notes=notes,
            chosen_by="persona_fallback",
            seed=SEGMENT_RANDOM_STATE,
        )

    matrix = _design_matrix(frame, columns)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)

    ceiling = _max_candidates(population_size)
    candidates = [k for k in SILHOUETTE_CANDIDATES if k <= ceiling]
    if n_clusters is not None:
        requested = int(n_clusters)
        if requested < 1:
            requested = 1
        if requested > population_size:
            notes.append(
                f"Requested {requested} clusters but there are only {population_size} customers, "
                f"so {population_size} was used."
            )
            requested = population_size
        candidates = [requested]
        chosen_by = "requested"
    else:
        chosen_by = "silhouette"

    best_k, silhouette_by_k, inertia_by_k = _fit_clusters(scaled, candidates)
    if n_clusters is None:
        notes.append(
            "Cluster count chosen by the highest silhouette score over k="
            f"{min(candidates)}..{max(candidates)}."
        )
        if best_k == max(candidates):
            notes.append(
                "The best score sits at the top of the range searched, so more clusters might "
                "still separate the population further."
            )

    model = KMeans(
        n_clusters=best_k,
        n_init=KMEANS_N_INIT,
        random_state=SEGMENT_RANDOM_STATE,
    )
    labels = model.fit_predict(scaled)
    centroids = model.cluster_centers_
    label_by_cluster, generic_named = _assign_labels(centroids, columns)
    if generic_named:
        notes.append(
            f"A cluster too close to the population average to match any behaviour "
            f"profile (best affinity below {MIN_ARCHETYPE_AFFINITY}) is named "
            f"'{UNKNOWN_SEGMENT_LABEL.value}' rather than given a name its features "
            "do not support."
        )
    population_means = frame[columns].mean()
    correlation = frame[columns].corr().abs().fillna(0.0)

    distances = np.linalg.norm(scaled - centroids[labels], axis=1)
    segments: list[PopulationSegment] = []
    for cluster_id in range(best_k):
        members = frame.iloc[np.flatnonzero(labels == cluster_id)]
        segment_labels = _distinctive_features(
            centroids[cluster_id], columns, members, population_means, correlation
        )
        segments.append(
            PopulationSegment(
                cluster_id=cluster_id,
                cluster_label=label_by_cluster[cluster_id].value,
                basis=SegmentBasis.KMEANS,
                size=int(len(members)),
                share=_ratio(len(members) / max(population_size, 1)),
                mean_profile={
                    column: _ratio(float(members[column].mean()))
                    for column in columns
                },
                distinctive_features=segment_labels,
                note=None,
            )
        )

    fit = SegmentationFit(
        n_clusters=best_k,
        silhouette=silhouette_by_k.get(best_k),
        inertia=_money(inertia_by_k.get(best_k, 0.0)),
        silhouette_by_k=silhouette_by_k,
        inertia_by_k={key: _money(value) for key, value in inertia_by_k.items()},
        chosen_by=chosen_by,
        population_size=population_size,
        feature_count=len(columns),
        features=columns,
        basis=SegmentBasis.KMEANS,
        segments=segments,
        notes=notes,
        seed=SEGMENT_RANDOM_STATE,
    )
    _CACHE["fit"] = fit
    _CACHE["scaler"] = scaler
    _CACHE["model"] = model
    _CACHE["labels"] = labels
    _CACHE["distances"] = distances
    _CACHE["columns"] = columns
    return fit


def fit_segmentation(n_clusters: int | None = None) -> dict:
    """Fit the segments, choosing k by silhouette unless ``n_clusters`` is given.

    The fitted scaler and model stay in a module-level cache so
    :func:`describe_user` and :func:`population_segments` can read them without
    refitting, and so every customer in one process is scored against exactly the
    same model.
    """
    frame = population_features()
    columns = _feature_columns(frame)
    return _build_fit(frame, columns, n_clusters).model_dump(mode="json")


def _current_fit() -> tuple[SegmentationFit, pd.DataFrame, list[str]]:
    frame = population_features()
    columns = _feature_columns(frame)
    fit = _CACHE.get("fit")
    if not isinstance(fit, SegmentationFit):
        fit = _build_fit(frame, columns, None)
    return fit, frame, columns


def _population_profile(user_id: str, frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    match = frame[frame["user_id"] == user_id] if "user_id" in frame.columns else frame.iloc[0:0]
    if not match.empty:
        return _design_matrix(match, columns)[0]
    context = get_context(user_id)
    values = [float(context.feature(column, 0.0) or 0.0) for column in columns]
    return np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)


def describe_user(user_id: str) -> dict:
    """Which group this customer sits in, and how typical they are inside it."""
    fit, frame, columns = _current_fit()
    context = get_context(user_id)
    row = _population_profile(user_id, frame, columns)

    if fit.basis is not SegmentBasis.KMEANS:
        persona = context.persona
        stand_in = fit.segments[0] if fit.segments else None
        label = PERSONA_SEGMENT_LABELS.get(persona, UNKNOWN_SEGMENT_LABEL).value
        guard = fit.notes[0] if fit.notes else None
        return UserSegmentProfile(
            user_id=user_id,
            cluster_id=0,
            cluster_label=label,
            basis=fit.basis,
            cluster_size=stand_in.size if stand_in else 0,
            distinctive_features=[],
            distance_to_centroid=0.0,
            cluster_average_distance=0.0,
            population_distance_ratio=0.0,
            mean_profile=stand_in.mean_profile if stand_in else {},
            note=f"Recorded behaviour type '{persona}'. {guard}" if guard else None,
        ).model_dump(mode="json")

    scaler = _CACHE["scaler"]
    model = _CACHE["model"]
    labels = _CACHE["labels"]
    distances = _CACHE["distances"]
    centroids = model.cluster_centers_

    scaled_row = scaler.transform(row.reshape(1, -1))[0]
    cluster_id = int(model.predict(scaled_row.reshape(1, -1))[0])
    distance = float(np.linalg.norm(scaled_row - centroids[cluster_id]))
    segment = next(item for item in fit.segments if item.cluster_id == cluster_id)
    member_mask = labels == cluster_id
    cluster_average = float(np.mean(distances[member_mask])) if member_mask.any() else 0.0
    population_average = float(np.mean(distances)) if len(distances) else 0.0

    return UserSegmentProfile(
        user_id=user_id,
        cluster_id=cluster_id,
        cluster_label=segment.cluster_label,
        basis=SegmentBasis.KMEANS,
        cluster_size=segment.size,
        distinctive_features=segment.distinctive_features,
        distance_to_centroid=_money(distance),
        cluster_average_distance=_money(cluster_average),
        population_distance_ratio=_ratio(distance / population_average)
        if population_average > 0
        else 0.0,
        mean_profile=segment.mean_profile,
        note=(
            f"{distance:.2f} standard deviations from the group centre, against a group average "
            f"of {cluster_average:.2f} and a population average of {population_average:.2f}."
        ),
    ).model_dump(mode="json")


def population_segments() -> list[dict]:
    """Every segment with its label, size and mean profile."""
    fit, _, _ = _current_fit()
    return [item.model_dump(mode="json") for item in fit.segments]
