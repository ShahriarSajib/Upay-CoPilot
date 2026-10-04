"""BDT amount parsing, formatting and normalisation.

Every user-visible number in this project passes through here so that the
assistant, the API and the evaluation harness all agree on one representation.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Scale words that Bangla/Banglish speakers use for money. Longest first so
# "lak" is not consumed by "l".
_SCALE_WORDS: list[tuple[str, int]] = [
    ("kuti", 1_000_000_000),
    ("koti", 100_000_000),
    ("lakh", 100_000),
    ("lac", 100_000),
    ("lak", 100_000),
    ("million", 1_000_000),
    ("crore", 10_000_000),
    ("k", 1_000),
    ("thousand", 1_000),
    ("hazaar", 1_000),
    ("hazar", 1_000),
    ("sho", 100),
]

_NUMBER_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)*)\s*(?P<scale>kuti|koti|lakh|lac|lak|million|crore|thousand|hazaar|hazar|sho|k)?",
    re.IGNORECASE,
)


def to_bangla_digits(text: str) -> str:
    return text.translate(BANGLA_DIGITS)


def round_money(value: float) -> float:
    """Round to 2dp using banker's-free half-up, then normalise -0.0."""
    quantised = float(Decimal(str(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return 0.0 if quantised == 0 else quantised


def format_bdt(value: float, decimals: bool = False) -> str:
    """Render a number the way a Bangladeshi customer expects: ৳1,23,456."""
    amount = round_money(value)
    sign = "-" if amount < 0 else ""
    whole = int(abs(amount))
    grouped = f"{whole:,}"
    # Indian digit grouping (lakh/crore) rather than Western.
    if whole >= 100000:
        head, tail = str(whole)[:-5], str(whole)[-5:]
        head = f"{int(head):,}" if head else ""
        grouped = f"{head}{tail}"
    out = f"{sign}৳{grouped}"
    if decimals and abs(amount - whole) > 0.004:
        out += f"{abs(amount) - whole:.2f}"
    return out


def format_bdt_compact(value: float) -> str:
    """Short form for dense UI: ৳1.23L / ৳12.5k / ৳800."""
    amount = round_money(value)
    sign = "-" if amount < 0 else ""
    magnitude = abs(amount)
    if magnitude >= 100_000:
        return f"{sign}৳{magnitude / 100_000:.2f}L"
    if magnitude >= 1_000:
        return f"{sign}৳{magnitude / 1_000:.1f}k"
    return f"{sign}৳{magnitude:,.0f}"


def parse_amount(text: str) -> float | None:
    """Pull money amounts out of free text.

    Handles English digits, Bangla digits, ``30,000``/``30.000`` grouping,
    the Bangladeshi taka sign, and scale words ("3 lakh", "30 hazar", "5k").
    The single largest match wins, which is what users mean when they say
    "save 30 thousand" alongside other numbers in the sentence.
    """
    if not text:
        return None
    cleaned = to_bangla_digits(str(text)).replace("৳", " ").replace("tk", " ").replace("taka", " ")
    best: float | None = None
    for match in _NUMBER_RE.finditer(cleaned):
        raw = match.group("num").replace(",", "")
        # "30.000" in Bangla prose is thirty thousand, not thirty.
        if "." in raw:
            head, _, tail = raw.partition(".")
            raw = head + tail if len(tail) == 3 and len(head) <= 3 else raw
        try:
            value = float(raw)
        except ValueError:
            continue
        scale_word = match.group("scale")
        if scale_word:
            scale_word = scale_word.lower()
            scale = next((mult for word, mult in _SCALE_WORDS if word == scale_word), 1)
            value *= scale
        if best is None or value > best:
            best = value
    return round_money(best) if best is not None else None


def parse_integer(text: str) -> int | None:
    amount = parse_amount(text)
    return int(round(amount)) if amount is not None else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that never raises and never returns inf/NaN."""
    if denominator is None or denominator == 0 or not np_is_finite(numerator):
        return default
    return numerator / denominator


def np_is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
