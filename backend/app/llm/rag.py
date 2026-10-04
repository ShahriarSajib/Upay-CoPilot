"""Grounded knowledge base for the assistant.

Scope, stated honestly: this dataset ships no upay service catalogue, no fee
schedule and no product terms. So this module does **not** invent any. It
contains only facts that are documented in this repository -- the product's own
capabilities (README) and the meaning of its own outputs (data dictionary).
Anything a customer asks about real upay products must be answered from a
sourced document; until that document exists, the assistant says so rather than
guessing.

Retrieval is lexical (token overlap) on purpose: with a knowledge base this
small, embeddings would add a dependency and a failure mode without adding
accuracy, and a lexical match is auditable by eye.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class KnowledgeItem:
    key: str
    title: str
    body: str
    source: str
    tags: tuple[str, ...] = ()


# Only repo-documented facts. Each item names where it comes from.
KNOWLEDGE_BASE: tuple[KnowledgeItem, ...] = (
    KnowledgeItem(
        key="capabilities",
        title="What this assistant can do",
        body=(
            "It provides a financial health score, spending intelligence, "
            "cash-flow forecasting, goal and savings planning, what-if "
            "simulation, emergency-fund planning, cash-out dependency analysis, "
            "financial literacy guidance and credit readiness. Every number is "
            "computed by a deterministic engine; the assistant only explains it."
        ),
        source="README.md#core-capabilities",
        tags=("capability", "feature", "what", "can", "do", "help"),
    ),
    KnowledgeItem(
        key="health_score",
        title="How the health score works",
        body=(
            "The health score is an explainable composite built from banded "
            "components. Each component reports its own band, weight and "
            "evidence, so the score can be argued with instead of trusted. It "
            "is not a credit score and it does not decide anything."
        ),
        source="app/engines/health.py",
        tags=("health", "score", "component", "band"),
    ),
    KnowledgeItem(
        key="forecast",
        title="How cash-flow forecasting works",
        body=(
            "Bills are treated as fixed because they are contractual, with known "
            "due dates and amounts. Only discretionary spending varies, and it "
            "is perturbed using the customer's own volatility history in a Monte "
            "Carlo simulation. The result is a balance path and a probability of "
            "running short, not a promise."
        ),
        source="app/engines/forecasting.py",
        tags=("forecast", "cashflow", "probability", "shortage", "monte", "carlo"),
    ),
    KnowledgeItem(
        key="emergency_buffer",
        title="How the emergency buffer is sized",
        body=(
            "The effective floor is the larger of the configured minimum balance "
            "buffer and one month of the customer's own recent spending. The "
            "target is three months of essentials. Both are declared assumptions, "
            "shown with every number that depends on them."
        ),
        source="app/core/config.py, app/engines/forecasting.py",
        tags=("emergency", "buffer", "floor", "target", "three", "months"),
    ),
    KnowledgeItem(
        key="credit_readiness",
        title="What credit readiness is not",
        body=(
            "Credit readiness is not a credit score, not a bureau report and not "
            "a lending decision. upay does not lend here. It is a readiness view "
            "from the customer's own transaction patterns. It estimates no "
            "repayment capacity and no loan amount, because this dataset has no "
            "debt or loan history. Age, occupation, location and name are never "
            "inputs."
        ),
        source="app/engines/credit.py",
        tags=("credit", "loan", "readiness", "score", "bureau", "eligible", "eligibility"),
    ),
    KnowledgeItem(
        key="literacy",
        title="How money skills are measured",
        body=(
            "Money skills are inferred from measured behaviour, not from a quiz. "
            "Someone who does not know what an emergency fund is but has six "
            "months of one is scored as strong, because that behaviour is what "
            "protects them. Where there is no data -- taxes, insurance, debt "
            "knowledge -- the result is 'unknown' rather than a guess."
        ),
        source="app/engines/literacy.py",
        tags=("literacy", "skill", "learn", "quiz", "behaviour", "budgeting"),
    ),
    KnowledgeItem(
        key="cash_out",
        title="Cash-out dependency",
        body=(
            "Cash-out dependency measures how much a customer relies on "
            "withdrawing cash rather than transacting digitally. High dependence "
            "makes spending harder to see and harder to budget."
        ),
        source="app/engines/cashout.py",
        tags=("cashout", "cash", "out", "agent", "withdrawal", "dependency"),
    ),
    KnowledgeItem(
        key="data_scope",
        title="What data this uses",
        body=(
            "This build runs on a synthetic development dataset of 50 active "
            "users over nine months (January to September 2026), with temporal "
            "train/validation/test windows. No real customer data is present."
        ),
        source="docs/dataset_split.md",
        tags=("data", "dataset", "synthetic", "users", "months"),
    ),
)


def _tokens(text: str) -> set[str]:
    return {token for token in _WORD.findall(text.lower()) if len(token) > 2}


def retrieve(query: str, limit: int = 3) -> list[KnowledgeItem]:
    """Lexical retrieval, best overlap first. Deterministic and auditable."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    scored: list[tuple[float, KnowledgeItem]] = []
    for item in KNOWLEDGE_BASE:
        item_tokens = _tokens(item.title + " " + item.body + " " + " ".join(item.tags))
        overlap = len(query_tokens & item_tokens)
        if overlap:
            # Normalise by the item's size so a long article does not always win.
            scored.append((overlap / (len(item_tokens) ** 0.5), item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].key))
    return [item for _, item in scored[:limit]]


def render_context(items: list[KnowledgeItem]) -> str:
    if not items:
        return ""
    blocks = [
        f"[{item.key}] {item.title} (source: {item.source})\n{item.body}"
        for item in items
    ]
    return "\n\n".join(blocks)


__all__ = ["KnowledgeItem", "KNOWLEDGE_BASE", "retrieve", "render_context"]