"""Input and output guardrails.

Two failure modes this module exists to stop:

* **Prompt injection via customer data.** Transaction descriptions, goal names
  and merchant strings are attacker-controlled text that ends up in the model's
  context. Anything resembling instructions ("ignore previous", "you are now",
  "system:") is neutralised before it reaches a provider.
* **PII and secrets leaving the building.** Account numbers, long digit runs
  and phone numbers are redacted on the way in; the model never needs them,
  because it works from engine outputs that are already aggregated.

There is also a *scope* filter: the assistant only discusses this product's
documented capabilities. It is not a general chatbot, and treating it as one is
how off-topic answers get attributed to the brand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Phrases that look like an attempt to override the system contract.
INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"^\s*system\s*:", re.I | re.M),
    re.compile(r"\bact\s+as\s+(a|an)\b", re.I),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.I),
    re.compile(r"reveal\s+(your\s+)?(prompt|instructions|system)", re.I),
    re.compile(r"\bjailbreak\b", re.I),
)

# Secrets and identifiers the model must never receive.
REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"), "[account]"),
    (re.compile(r"\b(?:\+?880|0)1[3-9]\d{8}\b"), "[phone]"),
    (re.compile(r"\b\d{13,19}\b"), "[number]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[email]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"), "[secret]"),
)

# Scope terms. Substring match against the lowercased message, so stems like
# "categor" cover "category"/"categories". Two of the product's own most
# natural questions -- "will I run short before payday" and "which categories
# grew fastest" -- were being refused until these were added; see
# app.evaluation.llm_eval.run_guards, which measures the false-positive rate
# on 40 legitimate questions so a regression here is visible.
TOPIC_TERMS: tuple[str, ...] = (
    "money", "taka", "bdt", "spend", "spent", "spending", "budget", "save", "saving",
    "goal", "emergency", "buffer", "balance", "income", "salary", "cash", "bill",
    "bills", "loan", "credit", "health", "forecast", "overspend", "overspending",
    "rent", "food", "transport", "utilities", "wallet", "upay", "literacy",
    "literate", "financial", "finance", "simulate", "simulation", "resilience",
    "recurring", "monthly", "risk", "ready", "readiness", "deposit", "expense",
    # Question stems that only sound general-purpose.
    "short", "shortage", "payday", "run short", "categor", "trend", "fastest",
    "slowest", "grew", "grow", "growing", "increase", "decrease", "afford",
    "week", "month", "due", "left", "top", "compare", "higher", "lowest",
    "highest", "retire", "retirement", "fund",
)


@dataclass
class GuardResult:
    text: str
    blocked: bool = False
    reasons: list[str] = field(default_factory=list)
    redactions: int = 0

    @property
    def clean(self) -> bool:
        return not self.blocked


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern, replacement in REDACTION_PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


def is_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in INJECTION_PATTERNS)


def is_on_topic(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in TOPIC_TERMS)


def sanitize_input(text: str, *, require_topic: bool = False) -> GuardResult:
    """Redact identifiers and neutralise injection attempts.

    Injection is not just dropped: the span is replaced with a neutral marker so
    the surrounding, legitimate question stays answerable. Blocking the whole
    message would punish a customer whose goal name happens to contain the word
    "system".
    """
    result = GuardResult(text=text)
    result.text, result.redactions = redact(result.text)
    for pattern in INJECTION_PATTERNS:
        if pattern.search(result.text):
            result.reasons.append("prompt_injection")
            result.text = pattern.sub("[removed-instruction]", result.text)
    if require_topic and result.text.strip() and not is_on_topic(result.text):
        result.reasons.append("off_topic")
        result.blocked = True
    return result


def guard_output(text: str) -> GuardResult:
    """A final filter on model output before it is shown to a customer."""
    result = GuardResult(text=text)
    result.text, result.redactions = redact(result.text)
    lowered = result.text.lower()
    banned = (
        "ignore previous",
        "as an ai language model",
        "i cannot access your",
        "guaranteed returns",
    )
    for phrase in banned:
        if phrase in lowered:
            result.reasons.append(f"output:{phrase.replace(' ', '_')}")
    if any(reason.startswith("output:") for reason in result.reasons):
        result.blocked = True
    return result


__all__ = [
    "GuardResult",
    "sanitize_input",
    "guard_output",
    "is_injection",
    "is_on_topic",
    "redact",
]