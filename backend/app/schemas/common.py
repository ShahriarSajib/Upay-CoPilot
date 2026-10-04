"""Shared response contracts.

Every engine in this system returns **numbers plus the reasons for those
numbers**. The rule the whole codebase follows:

* An engine computes. It never asks a language model for a number.
* Every computed figure carries an :class:`Evidence` item naming the source
  columns, the window it was measured over, and how confident we are.
* Assumptions that are *chosen* rather than *measured* (3-month emergency fund,
  minimum balance buffer) are declared in :class:`Assumption` and surfaced to
  the customer, never buried in the code.

This is what makes the LLM safe to put in front of the product: it only ever
rewrites prose around values that were already computed and evidenced here.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_serializer


class Confidence(str, Enum):
    """How much weight a figure deserves, derived from sample size and spread."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Direction(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    FLAT = "flat"


class Severity(str, Enum):
    INFO = "info"
    ATTENTION = "attention"
    WARNING = "warning"


class Evidence(BaseModel):
    """One measured fact, with its provenance."""

    label: str
    value: float
    unit: str = "bdt"
    source: str = Field(description="Table or engine the number came from.")
    window: str | None = Field(
        default=None, description="Period the measurement covers, e.g. '2026-09'."
    )
    comparison: str | None = Field(
        default=None, description="What it is being compared against, in plain words."
    )
    confidence: Confidence = Confidence.MEDIUM

    @field_serializer("confidence")
    def _ser_confidence(self, value: Confidence) -> str:
        return value.value


class Assumption(BaseModel):
    """A planning choice, not a measurement. Always shown to the customer."""

    key: str
    value: float
    rationale: str
    configurable: bool = True


class Metric(BaseModel):
    """A single headline figure for a dashboard tile."""

    key: str
    label: str
    value: float
    unit: str = "bdt"
    previous_value: float | None = None
    change_percent: float | None = None
    direction: Direction = Direction.FLAT
    confidence: Confidence = Confidence.MEDIUM
    evidence: list[Evidence] = Field(default_factory=list)


class Insight(BaseModel):
    """One prioritised, actionable observation.

    The contract is deliberately ``why / what / action``: an insight that cannot
    name all three is not ready to show a customer.
    """

    key: str
    title: str
    observation: str
    why: str
    action: str
    severity: Severity = Severity.INFO
    impact_bdt: float | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)


class Band(BaseModel):
    """A scored component with its band label, for explainable score displays."""

    key: str
    label: str
    score: float = Field(ge=0, le=100)
    band: str
    weight: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=100)
    detail: str
    evidence: list[Evidence] = Field(default_factory=list)


class Score(BaseModel):
    """An explainable composite score. Never a lending decision."""

    value: float = Field(ge=0, le=100)
    label: str
    bands: list[Band] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    attention_areas: list[str] = Field(default_factory=list)
    disclaimer: str | None = None
    confidence: Confidence = Confidence.MEDIUM


class PlanOption(BaseModel):
    """One option in a savings/goal plan. The customer chooses, we do not."""

    key: str
    name: str
    monthly_contribution: float
    feasible: bool
    projected_completion: str | None = None
    months_to_completion: float | None = None
    shortfall: float = 0.0
    trade_offs: list[str] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class ForecastPoint(BaseModel):
    date: str
    income: float
    spend: float
    net: float
    balance: float
    recurring: float = 0.0
    discretionary: float = 0.0


class Explanation(BaseModel):
    """A short, deterministic, customer-readable narrative.

    Produced without any language model so the product works with no API key.
    """

    headline: str
    detail: list[str] = Field(default_factory=list)
    language: str = "en"


class EngineResponse(BaseModel):
    """Common envelope so the API and the LLM tool layer stay uniform."""

    user_id: str
    as_of: str
    explanation: Explanation | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)

    def evidence_for(self, key: str) -> list[Evidence]:
        return [item for item in self.evidence if item.label == key]

    def metric(self, key: str) -> Metric | None:
        for item in self.metrics:
            if item.key == key:
                return item
        return None