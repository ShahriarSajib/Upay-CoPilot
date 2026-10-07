"""Synthetic provider events: a deterministic fault source for rehearsals.

Production calls go to real vendors. Failover, retry and circuit breaking are
exactly the code you cannot exercise that way: it needs a network that times
out on demand, and a 503 that arrives on the second attempt rather than the
first. This module supplies those outcomes as *events* so the same provider
chain can be driven through them in milliseconds, offline, and byte-for-byte
identically on every run.

Two ways to produce events:

* :class:`EventTimeline` — a scripted list. Use this when a test or a demo has
  a specific story to tell ("primary times out, fallback answers").
* :class:`EventSimulator` — a seeded random stream with named failure rates.
  Use this when you want a distribution of faults rather than one story.

Neither touches the network, sleeps, or reads the clock unless asked to.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol

EventKind = Literal[
    "ok",
    "timeout",
    "server_error",
    "rate_limit",
    "malformed",
    "network",
]

#: Kinds the caller is expected to retry rather than treat as terminal.
RETRYABLE_KINDS: frozenset[str] = frozenset({"timeout", "server_error", "rate_limit", "network"})

KIND_DETAIL: dict[str, str] = {
    "ok": "call succeeded",
    "timeout": "deadline exceeded",
    "server_error": "upstream returned 5xx",
    "rate_limit": "upstream returned 429",
    "malformed": "response body was not the expected JSON shape",
    "network": "connection could not be established",
}


class FaultError(Exception):
    """A fault raised by an injector before or instead of a real HTTP call.

    Kept separate from the provider's own error type so that this module has no
    knowledge of providers; the provider layer translates it.
    """

    def __init__(self, kind: EventKind, detail: str = "") -> None:
        super().__init__(detail or KIND_DETAIL.get(kind, kind))
        self.kind = kind
        self.detail = detail or KIND_DETAIL.get(kind, kind)


@dataclass(frozen=True)
class Event:
    """One provider outcome."""

    provider: str
    kind: EventKind
    latency_ms: int = 0
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.kind == "ok"

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_KINDS

    def describe(self) -> str:
        return self.detail or KIND_DETAIL.get(self.kind, self.kind)


@dataclass
class EventTimeline:
    """A scripted sequence of outcomes, consumed one per call.

    Events are matched to the provider that is calling; a provider with no
    scripted event left receives ``ok``. That keeps a scenario readable: you
    write down only the things you want to go wrong.
    """

    events: list[Event] = field(default_factory=list)

    def next(self, provider: str) -> Event:
        for index, event in enumerate(self.events):
            if event.provider == provider:
                return self.events.pop(index)
        return Event(provider=provider, kind="ok")

    def remaining(self) -> list[Event]:
        return list(self.events)


@dataclass
class FaultProfile:
    """Failure rates for :class:`EventSimulator`, per call and per provider."""

    timeout_rate: float = 0.0
    server_error_rate: float = 0.0
    rate_limit_rate: float = 0.0
    malformed_rate: float = 0.0
    latency_ms: tuple[int, int] = (60, 400)

    def validate(self) -> None:
        total = (
            self.timeout_rate
            + self.server_error_rate
            + self.rate_limit_rate
            + self.malformed_rate
        )
        if total > 1.0:
            raise ValueError(f"failure rates sum to {total:.2f}, which exceeds 1.0")
        low, high = self.latency_ms
        if low < 0 or high < low:
            raise ValueError(f"latency_ms must be a non-negative range, got {self.latency_ms}")


class Clock(Protocol):
    """Injectable time source: tests pass a fake so nothing really sleeps."""

    def __call__(self) -> float: ...


class EventSimulator:
    """Seeded stream of provider outcomes.

    The seed is part of the interface: two runs with the same seed and profile
    produce the same event sequence, which is what makes a failover rehearsal
    reproducible.
    """

    def __init__(
        self,
        profile: FaultProfile | None = None,
        seed: int = 42,
        timeline: EventTimeline | None = None,
    ) -> None:
        self.profile = profile or FaultProfile()
        self.profile.validate()
        self.seed = seed
        self._rng = random.Random(seed)
        self._timeline = timeline
        self.log: list[Event] = []

    def next_event(self, provider: str) -> Event:
        if self._timeline is not None:
            event = self._timeline.next(provider)
        else:
            event = self._draw(provider)
        self.log.append(event)
        return event

    def _draw(self, provider: str) -> Event:
        profile = self.profile
        roll = self._rng.random()
        low, high = profile.latency_ms
        latency = self._rng.randint(low, high)
        if roll < profile.timeout_rate:
            return Event(provider, "timeout", latency, "simulated deadline")
        cumulative = profile.timeout_rate + profile.server_error_rate
        if roll < cumulative:
            return Event(provider, "server_error", latency, "simulated 503")
        cumulative += profile.rate_limit_rate
        if roll < cumulative:
            return Event(provider, "rate_limit", latency, "simulated 429")
        cumulative += profile.malformed_rate
        if roll < cumulative:
            return Event(provider, "malformed", latency, "simulated truncated body")
        return Event(provider, "ok", latency)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.log:
            counts[event.kind] = counts.get(event.kind, 0) + 1
        return counts


class FaultInjector(Protocol):
    """Hook the provider chain calls around every attempt."""

    def before_call(self, provider: str) -> None: ...

    def after_call(self, provider: str, succeeded: bool) -> None: ...


class NullInjector:
    """Production default: no injected faults, no recorded calls."""

    def before_call(self, provider: str) -> None:
        return None

    def after_call(self, provider: str, succeeded: bool) -> None:
        return None


class SimulatedFaults:
    """Injector that turns a simulator's events into raised faults.

    The three cases are kept apart on purpose, because they exercise different
    parts of the chain:

    * ``ok`` — ``before_call`` lets the transport run and ``after_call`` is a
      no-op.
    * ``malformed`` — the transport runs (so response handling is exercised)
      and ``after_call`` rejects the body afterwards.
    * everything else — ``before_call`` raises, so the call is never dialled.

    ``sleep`` is injectable so latency can be spent for real in a demo or
    elided in a test.
    """

    def __init__(
        self,
        simulator: EventSimulator,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.simulator = simulator
        self._sleep = sleep
        self._pending: Event | None = None

    def before_call(self, provider: str) -> None:
        event = self.simulator.next_event(provider)
        self._pending = event
        if self._sleep is not None and event.latency_ms:
            self._sleep(event.latency_ms / 1000.0)
        if event.kind != "malformed" and not event.ok:
            raise FaultError(event.kind, event.describe())

    def after_call(self, provider: str, succeeded: bool) -> None:
        event = self._pending
        self._pending = None
        if event is not None and event.kind == "malformed" and succeeded:
            raise FaultError("malformed", event.describe())


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


def failover_scenario() -> EventTimeline:
    """Primary times out, then 500s; the fallback answers on the first try.

    This is the runbook case the chain exists for, written as data.
    """
    return EventTimeline(
        [
            Event("gemini", "timeout", 10_000, "primary exceeded its deadline"),
            Event("gemini", "server_error", 820, "upstream 503 during retry"),
            Event("groq", "ok", 340, "fallback answered"),
        ]
    )


def breaker_scenario() -> EventTimeline:
    """Primary fails repeatedly, the breaker opens, then a trial call succeeds.

    Consumed in order: three failing gemini calls open the breaker, a fourth is
    rejected without dialling, and the fifth (half-open trial) recovers it.
    """
    return EventTimeline(
        [
            Event("gemini", "server_error", 400, "first outage"),
            Event("gemini", "server_error", 400, "second outage"),
            Event("gemini", "timeout", 9_000, "third outage"),
            Event("gemini", "ok", 260, "half-open trial recovered"),
        ]
    )


def degraded_scenario(profile: FaultProfile | None = None, seed: int = 42) -> EventSimulator:
    """A noisy-but-alive provider mix for a longer rehearsal."""
    return EventSimulator(
        profile=profile
        or FaultProfile(
            timeout_rate=0.15,
            server_error_rate=0.2,
            rate_limit_rate=0.1,
            latency_ms=(80, 600),
        ),
        seed=seed,
    )
