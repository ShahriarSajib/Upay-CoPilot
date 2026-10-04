"""Response contracts for financial literacy and credit readiness.

Both features are deliberately shaped so a language model can *only* narrate
them. Every number arrives pre-computed with its evidence attached, and the
credit payload carries its own refusal text so the boundary travels with the
data rather than living in a prompt.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import (
    Assumption,
    Confidence,
    Evidence,
    Explanation,
    Insight,
    Metric,
)

__all__ = [
    "ReadinessOverall",
    "LiteracyConcept",
    "LiteracyLesson",
    "LiteracyResponse",
    "ReadinessComponent",
    "ReadinessAction",
    "CreditReadinessResponse",
]


class ReadinessOverall(BaseModel):
    """The composite readiness figure.

    Deliberately *not* :class:`app.schemas.common.Score`: that model is built
    for banded financial-health scores and would imply this is the same kind of
    number. It is not, and sharing the type would quietly make it look like one.
    """

    value: float = Field(ge=0, le=100)
    label: str
    band_index: int = 0
    strengths: list[str] = Field(default_factory=list)
    attention_areas: list[str] = Field(default_factory=list)
    disclaimer: str
    confidence: Confidence = Confidence.MEDIUM


class LiteracyConcept(BaseModel):
    """One money skill, scored from what the customer actually does.

    ``mastery`` is behaviour, not a self-assessment: there is no quiz answer to
    guess at, so the number cannot flatter someone who does not know the
    concept but feels confident.
    """

    key: str
    label: str
    mastery: float = Field(ge=0, le=100)
    band: str
    what_it_means: str
    why_it_matters: str
    evidence: list[Evidence] = Field(default_factory=list)
    verdict_confidence: Confidence = Confidence.MEDIUM


class LiteracyLesson(BaseModel):
    """A short explainer anchored to one of the customer's own numbers."""

    key: str
    title: str
    body: str
    their_number: float | None = None
    unit: str = "bdt"
    action: str
    evidence: list[Evidence] = Field(default_factory=list)


class LiteracyResponse(BaseModel):
    user_id: str
    as_of: str
    overall: ReadinessOverall
    concepts: list[LiteracyConcept] = Field(default_factory=list)
    lessons: list[LiteracyLesson] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    explanation: Explanation | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)


class ReadinessComponent(BaseModel):
    """One weighted pillar of the readiness score."""

    key: str
    label: str
    score: float = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=100)
    band: str
    detail: str
    blocking: bool = False
    evidence: list[Evidence] = Field(default_factory=list)


class ReadinessAction(BaseModel):
    """A concrete next step.

    ``projected_overall`` is produced by *re-running the whole scorer against a
    modified copy of this customer's own features*, so it is a real
    recalculation rather than a marketing estimate. When a step cannot move the
    score the field is ``None`` and the action says why.
    """

    key: str
    title: str
    action: str
    reason: str
    effort: Literal["low", "medium", "high"] = "medium"
    monthly_bdt: float | None = None
    component: str | None = None
    projected_overall: float | None = None
    projected_band: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class CreditReadinessResponse(BaseModel):
    user_id: str
    as_of: str
    overall: ReadinessOverall
    components: list[ReadinessComponent] = Field(default_factory=list)
    actions: list[ReadinessAction] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    months_to_next_band: float | None = None
    timeline: list[dict] = Field(default_factory=list)
    disclaimer: str
    excluded_attributes: list[str] = Field(default_factory=list)
    explanation: Explanation | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)