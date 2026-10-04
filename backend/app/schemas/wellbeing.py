"""Response contracts for the wellbeing engines: health, resilience, segments.

Why these models exist
----------------------
``app.schemas.common`` defines the envelope every engine returns, and it
deliberately stops there: a metric, an evidence item and a band carry no opinion
about *what is being measured*. These three engines measure something different
from each other -- a weighted composite of controllable behaviours, a stress
test against a one-off shock, and an unsupervised cluster -- so each needs a
vocabulary of its own (component keys, dimension keys, human segment labels)
that the shared envelope has no way to express.

Two design rules are encoded in the shapes below.

* **A component is a first-class object, not two loose numbers.** ``Band`` can
  express "score 62, weight 0.2, contribution 12.4", but not *how* 62 was
  reached. :class:`ComponentResult` adds the named sub-scores and a
  ``held_neutral`` flag, because a customer with no savings goal must not be
  shown a low "goal progress" band as if it were a finding. Holding a component
  at the midpoint, and saying so, is the honest alternative to both rewarding
  and punishing an absence.
* **The disclaimer travels with the number it qualifies.** A composite score
  that looks like a credit score is a compliance problem no matter how it is
  phrased downstream, so :class:`ResilienceResponse` fixes its disclaimer as a
  class default: the wording cannot drift per endpoint or per call site.

``HealthResponse`` and ``ResilienceResponse`` subclass :class:`EngineResponse`,
so anything typed against the envelope keeps working unchanged.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import Band, Confidence, Direction, EngineResponse

RESILIENCE_DISCLAIMER = (
    "Planning indicator only - this is not a credit score and does not "
    "determine any lending or eligibility decision."
)

HEALTH_DISCLAIMER = (
    "Reflects your own transaction history only. It is a planning indicator, not "
    "a credit score, and it is not shared with any lender."
)


class HealthComponent(str, Enum):
    """The six behaviours the financial-health total is built from."""

    SAVINGS_BEHAVIOUR = "savings_behaviour"
    EXPENSE_CONTROL = "expense_control"
    INCOME_STABILITY = "income_stability"
    LIQUIDITY_BUFFER = "liquidity_buffer"
    GOAL_PROGRESS = "goal_progress"
    CASH_DEPENDENCY = "cash_dependency"


class ResilienceDimension(str, Enum):
    """The seven dimensions the resilience total is built from.

    Deliberately a different cut from :class:`HealthComponent`: health asks
    "how well are the habits running", resilience asks "what happens when
    something breaks". Two dimensions read the same underlying history (income
    variation, buffer size) but weight it differently, because a habit that is
    *consistently mediocre* and a buffer that is *small enough to be consumed by
    one bill* are different risks.
    """

    INCOME_STABILITY = "income_stability"
    EXPENSE_STABILITY = "expense_stability"
    LIQUIDITY_BUFFER = "liquidity_buffer"
    SAVINGS_CONSISTENCY = "savings_consistency"
    GOAL_PROGRESS = "goal_progress"
    CASH_OUT_DEPENDENCY = "cash_out_dependency"
    UNEXPECTED_EXPENSE_TOLERANCE = "unexpected_expense_tolerance"


class ComponentBand(str, Enum):
    """Band wording shown next to a component score."""

    STRONG = "strong"
    MODERATE = "moderate"
    WATCH = "watch"
    NEEDS_ATTENTION = "needs attention"


class HealthGrade(str, Enum):
    """Top-level wording for the health total.

    All four describe a position, not a person: none of them implies the
    customer did something wrong.
    """

    STRONG = "strong footing"
    STEADY = "steady footing"
    STRAINED = "strained footing"
    TIGHT = "tight footing"


class ResilienceGrade(str, Enum):
    """Top-level wording for the resilience total."""

    STRONG = "well cushioned"
    STEADY = "cushioned"
    THIN = "thin cushion"
    FRAGILE = "very thin cushion"


class SegmentLabel(str, Enum):
    """Human names for a behavioural segment.

    Chosen to describe a *pattern of timing or reliance* that the customer can
    recognise themselves in. Deliberately not names like "savers" or
    "spenders": a segment label that reads as a character judgement is the same
    tone failure as a shaming insight, one level up.
    """

    STEADY_BUILDERS = "steady builders"
    GOAL_DRIVEN_PLANNERS = "goal-driven planners"
    MONTH_END_STRETCHERS = "month-end stretchers"
    VOLATILE_IRREGULAR_EARNERS = "volatile irregular earners"
    CASH_LEANING_SPENDERS = "cash-leaning spenders"
    SEASONAL_SPENDERS = "seasonal spenders"
    SHOCK_PRONE_SPENDERS = "shock-prone spenders"
    SPENDING_AHEAD_OF_EARNINGS = "spending ahead of earnings"
    BALANCED_REGULARS = "balanced regulars"


class SegmentBasis(str, Enum):
    """How a segment was arrived at, so the UI can be honest about it."""

    KMEANS = "kmeans"
    PERSONA = "persona"
    UNAVAILABLE = "unavailable"


class ComponentResult(Band):
    """A scored component plus the sub-scores that produced it.

    ``sub_scores`` are named rather than anonymous so the explanation layer can
    say which half of a component is weak ("the buffer is fine, but the balance
    dips under the minimum often") instead of restating the composite.
    """

    held_neutral: bool = Field(
        default=False,
        description="True when the component is not measurable for this customer.",
    )
    sub_scores: dict[str, float] = Field(default_factory=dict)


class HealthMeasurements(BaseModel):
    """Everything the health and resilience components are allowed to read.

    One flat, fully-populated record rather than a frame reference, for two
    reasons: the same record can be built from the user-level feature row (for
    the current score) or from a truncated monthly history (for the causal
    trend), and the scoring code cannot accidentally reach a feature that only
    exists on one of those two paths.
    """

    months_observed: int = 0
    window: str = ""
    savings_rate: float = 0.0
    funding_consistency: float = 0.0
    goal_count: int = 0
    goal_progress: float = 0.0
    expense_income_ratio: float = 0.0
    expense_ratio_cv: float = 0.0
    negative_surplus_share: float = 0.0
    late_month_share: float = 0.0
    income_cv: float = 0.0
    income_consistency: float = 0.0
    emergency_buffer_months: float = 0.0
    low_balance_frequency: float = 0.0
    days_below_buffer: float = 0.0
    cash_dependency: float = 0.0
    monthly_income: float = 0.0
    monthly_expense: float = 0.0
    monthly_surplus: float = 0.0
    ending_balance: float = 0.0
    lowest_balance: float = 0.0
    recurring_amount_mean: float = 0.0
    mandatory_obligation_amount: float = 0.0
    spend_cv: float = 0.0
    surplus_dispersion: float = 0.0
    surprise_events: float = 0.0
    months_short_after_shock: float = 0.0
    has_cash_wallet: bool = False


class HealthAssessment(BaseModel):
    """The scored health result before it is wrapped for the API."""

    user_id: str
    as_of: str
    total_score: float
    label: str
    components: list[ComponentResult] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    attention_areas: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    months_observed: int = 0
    window: str = ""


class HealthTrendPoint(BaseModel):
    """One causal re-scoring, as of a single past period."""

    period: str
    health_score: float
    label: str
    confidence: Confidence = Confidence.MEDIUM
    months_observed: int = 0
    strengths: list[str] = Field(default_factory=list)
    attention_areas: list[str] = Field(default_factory=list)
    note: str | None = None


class ShockSimulation(BaseModel):
    """A one-off cost the size of a month's essentials, absorbed by the buffer.

    "Essential spend" is the customer's own recurring obligations rather than a
    fixed percentage of income, because the household bill is already in their
    history. What the product needs to show is not "is this affordable" but "how
    much of the cushion does it eat, and is anything left".
    """

    essential_monthly_spend: float
    months_of_spending_absorbed: float
    buffer_before: float
    buffer_after: float
    buffer_months_remaining: float
    reserve_share_consumed: float
    shocks_absorbed_by_buffer: float
    shortfall: float = 0.0
    months_short_after_shock: float = 0.0
    affordable: bool = True
    basis: str = "recurring_obligations"
    note: str | None = None


class ResilienceAssessment(BaseModel):
    """The scored resilience result before it is wrapped for the API."""

    user_id: str
    as_of: str
    total_score: float
    label: str
    dimensions: list[ComponentResult] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    attention_areas: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    months_observed: int = 0
    shock: ShockSimulation
    disclaimer: str = RESILIENCE_DISCLAIMER


class FeatureDelta(BaseModel):
    """How far one cluster sits from the population, in standard deviations.

    ``standardised_difference`` is the centroid's z-score, so it is directly
    comparable across features: 0.8 means "clearly more than most customers"
    whether the feature is taka or a ratio.
    """

    feature: str
    label: str
    cluster_mean: float
    population_mean: float
    standardised_difference: float
    direction: Direction = Direction.FLAT


class UserSegmentProfile(BaseModel):
    """Where one customer sits, and how typical they are inside their group."""

    user_id: str
    cluster_id: int
    cluster_label: str
    basis: SegmentBasis = SegmentBasis.KMEANS
    cluster_size: int = 0
    distinctive_features: list[FeatureDelta] = Field(default_factory=list)
    distance_to_centroid: float = 0.0
    cluster_average_distance: float = 0.0
    population_distance_ratio: float = 0.0
    mean_profile: dict[str, float] = Field(default_factory=dict)
    note: str | None = None


class PopulationSegment(BaseModel):
    """One cluster as the whole population sees it."""

    cluster_id: int
    cluster_label: str
    basis: SegmentBasis = SegmentBasis.KMEANS
    size: int = 0
    share: float = 0.0
    mean_profile: dict[str, float] = Field(default_factory=dict)
    distinctive_features: list[FeatureDelta] = Field(default_factory=list)
    note: str | None = None


class SegmentationFit(BaseModel):
    """Everything :func:`app.engines.segmentation.fit_segmentation` found.

    ``silhouette_by_k`` is kept rather than only the winner: a single chosen k
    is a claim, the curve behind it is the evidence, and on a small population
    the flatness of that curve is the honest answer to "why k?".
    """

    n_clusters: int = 0
    silhouette: float | None = None
    inertia: float | None = None
    silhouette_by_k: dict[int, float] = Field(default_factory=dict)
    inertia_by_k: dict[int, float] = Field(default_factory=dict)
    chosen_by: str = "silhouette"
    population_size: int = 0
    feature_count: int = 0
    features: list[str] = Field(default_factory=list)
    basis: SegmentBasis = SegmentBasis.KMEANS
    segments: list[PopulationSegment] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    seed: int = 0


class HealthResponse(EngineResponse):
    """Health envelope: the shared one plus the explainable breakdown."""

    disclaimer: str = HEALTH_DISCLAIMER
    label: str = ""
    window: str = ""
    months_observed: int = 0
    components: list[ComponentResult] = Field(default_factory=list)
    bands: list[Band] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    attention_areas: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class ResilienceResponse(EngineResponse):
    """Resilience envelope, with the non-lending wording fixed in place."""

    disclaimer: str = RESILIENCE_DISCLAIMER
    label: str = ""
    window: str = ""
    months_observed: int = 0
    dimensions: list[ComponentResult] = Field(default_factory=list)
    bands: list[Band] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    attention_areas: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    shock: ShockSimulation