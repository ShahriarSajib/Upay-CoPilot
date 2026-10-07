"""Provider abstraction: one interface, ordered failover, observable faults.

``router.py`` used to own vendor payloads, timeouts, retries and failover order
in a single loop. That made two questions unanswerable after a failure — *was
this a timeout or a 429?* and *would failover have worked?* — and it made
failover untestable without a live network that misbehaves on demand.

This module owns the attempt; the router owns the answer. The layering is:

* ``events.py`` — what can go wrong. Pure data, no I/O.
* ``providers.py`` (here) — how a call is attempted: one vendor behind one
  interface, a bounded retry, a circuit breaker, then the next vendor in
  priority order.
* ``router.py`` — what the copilot does with the answer: guards, tool
  allowlisting, grounding.

Everything the chain cannot see on its own — the clock, the sleep, the fault
stream — is injected, which is why the failover rehearsal in
``backend/tests/test_providers.py`` finishes in microseconds and still runs the
real retry and breaker code.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

import httpx

from app.core.config import Settings, settings as default_settings
from app.llm.events import (
    RETRYABLE_KINDS,
    EventKind,
    FaultInjector,
    FaultError,
    NullInjector,
)

#: Failure classes the chain gives up on a provider for, without retrying it:
#: the next call would fail the same way. They still fail over to the next
#: vendor, because "vendor A cannot answer" is not "nobody can answer".
TERMINAL_KINDS: frozenset[str] = frozenset({"not_configured", "rejected", "malformed"})


class ProviderError(Exception):
    """A single attempt failed, with a machine-readable reason."""

    def __init__(self, kind: EventKind | str, provider: str = "", message: str = "") -> None:
        super().__init__(message or f"{provider or 'provider'}: {kind}")
        self.kind = kind
        self.provider = provider
        self.message = message or kind

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_KINDS


@dataclass(frozen=True)
class ProviderRequest:
    """A provider-agnostic chat request."""

    messages: list[dict]
    tools_schema: list[dict] | None = None
    timeout_seconds: float | None = None
    max_attempts: int | None = None


@dataclass
class Attempt:
    """One recorded dial, whether it answered or not."""

    provider: str
    attempt: int
    outcome: str
    latency_ms: int
    detail: str = ""


@dataclass
class RouteResult:
    """The answer the chain got, plus the path it took to get it."""

    provider: str
    raw: dict
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def dials(self) -> int:
        return sum(1 for a in self.attempts if a.attempt > 0)

    @property
    def total_latency_ms(self) -> int:
        return sum(a.latency_ms for a in self.attempts)


class Provider(Protocol):
    """What every vendor must provide."""

    name: str
    priority: int

    def configured(self) -> bool: ...

    def complete(self, request: ProviderRequest) -> dict: ...


# --------------------------------------------------------------------------
# Transports
# --------------------------------------------------------------------------


def _http_error_to_provider_error(provider: str, exc: Exception) -> ProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return ProviderError("rate_limit", provider, f"{provider} returned 429")
        if status >= 500:
            return ProviderError("server_error", provider, f"{provider} returned {status}")
        return ProviderError("rejected", provider, f"{provider} returned {status}")
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError("timeout", provider, f"{provider} exceeded its deadline")
    if isinstance(exc, httpx.HTTPError):
        return ProviderError("network", provider, f"{provider} connection failed: {exc}")
    return ProviderError("network", provider, str(exc))


class _HttpProvider:
    """Shared plumbing: a configured check, a timed POST, mapped errors."""

    name: str
    priority: int

    def configured(self) -> bool:
        raise NotImplementedError

    def _url(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict:
        raise NotImplementedError

    def _payload(self, request: ProviderRequest) -> dict:
        raise NotImplementedError

    def complete(self, request: ProviderRequest) -> dict:
        if not self.configured():
            raise ProviderError("not_configured", self.name, f"{self.name} is not configured")
        try:
            with httpx.Client(timeout=request.timeout_seconds or default_settings.llm_timeout_seconds) as client:
                response = client.post(
                    self._url(),
                    json=self._payload(request),
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("malformed", self.name, f"{self.name} returned non-JSON") from exc
        except httpx.HTTPError as exc:
            raise _http_error_to_provider_error(self.name, exc) from exc
        if not isinstance(body, dict):
            raise ProviderError("malformed", self.name, f"{self.name} returned a non-object body")
        return body


class GeminiProvider(_HttpProvider):
    name = "gemini"
    priority = 10

    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or default_settings

    def configured(self) -> bool:
        return bool(self.cfg.gemini_api_key and self.cfg.gemini_base_url)

    def _url(self) -> str:
        return (
            f"{self.cfg.gemini_base_url.rstrip('/')}"
            f"/v1beta/models/{self.cfg.gemini_model}:generateContent"
        )

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.cfg.gemini_api_key,
        }

    def _payload(self, request: ProviderRequest) -> dict:
        payload: dict = {
            "contents": request.messages,
            "generationConfig": {
                "temperature": 0.1,
                "topK": 1,
                "topP": 0.95,
                "maxOutputTokens": 256,
                "responseMimeType": "application/json",
            },
        }
        if request.tools_schema:
            payload["tools"] = [{"functionDeclarations": request.tools_schema}]
        return payload


class GroqProvider(_HttpProvider):
    name = "groq"
    priority = 20

    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or default_settings

    def configured(self) -> bool:
        return bool(self.cfg.groq_api_key and self.cfg.groq_base_url)

    def _url(self) -> str:
        return f"{self.cfg.groq_base_url.rstrip('/')}/openai/v1/chat/completions"

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.groq_api_key}",
        }

    def _payload(self, request: ProviderRequest) -> dict:
        payload: dict = {
            "model": self.cfg.groq_model,
            "messages": request.messages,
            "temperature": 0.1,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }
        if request.tools_schema:
            payload["tools"] = [{"type": "function", "function": t} for t in request.tools_schema]
        return payload


# --------------------------------------------------------------------------
# Circuit breaker
# --------------------------------------------------------------------------


class CircuitBreaker:
    """Stops dialling a provider that has just failed ``threshold`` times.

    After ``reset_seconds`` it lets exactly one trial call through; a success
    closes it, a failure reopens it. Without this, a vendor outage turns every
    request into a serial wait across both providers.
    """

    def __init__(
        self,
        threshold: int,
        reset_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._clock = clock
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if self._clock() - self.opened_at >= self.reset_seconds:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def on_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def on_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self._clock()

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "consecutive_failures": self.failures,
            "threshold": self.threshold,
            "reset_seconds": self.reset_seconds,
        }


# --------------------------------------------------------------------------
# Chain
# --------------------------------------------------------------------------


class ProviderChain:
    """Tries providers in priority order, retrying within and failing across."""

    def __init__(
        self,
        providers: list[Provider],
        *,
        max_attempts: int | None = None,
        backoff_seconds: float | None = None,
        breaker_threshold: int | None = None,
        breaker_reset_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        cfg: Settings | None = None,
    ) -> None:
        cfg = cfg or default_settings
        self.providers = sorted(providers, key=lambda p: p.priority)
        self.max_attempts = max_attempts if max_attempts is not None else cfg.llm_max_attempts
        self.backoff_seconds = (
            backoff_seconds if backoff_seconds is not None else cfg.llm_backoff_seconds
        )
        self._clock = clock
        self._sleep = sleep
        self.history: list[Attempt] = []
        self.breakers: dict[str, CircuitBreaker] = {
            p.name: CircuitBreaker(
                breaker_threshold if breaker_threshold is not None else cfg.llm_breaker_threshold,
                breaker_reset_seconds
                if breaker_reset_seconds is not None
                else cfg.llm_breaker_reset_seconds,
                clock=clock,
            )
            for p in self.providers
        }

    def ordered(self) -> list[Provider]:
        return list(self.providers)

    def call(
        self,
        request: ProviderRequest,
        injector: FaultInjector | None = None,
    ) -> RouteResult:
        injector = injector or NullInjector()
        attempts: list[Attempt] = []

        for provider in self.providers:
            breaker = self.breakers[provider.name]

            if not provider.configured():
                attempts.append(
                    Attempt(provider.name, 0, "not_configured", 0, "no credentials in settings")
                )
                continue
            if not breaker.allow():
                attempts.append(
                    Attempt(
                        provider.name,
                        0,
                        "circuit_open",
                        0,
                        f"circuit {breaker.state} after {breaker.failures} failures",
                    )
                )
                continue

            limit = request.max_attempts if request.max_attempts is not None else self.max_attempts
            failed = False
            for index in range(1, limit + 1):
                started = self._clock()
                try:
                    injector.before_call(provider.name)
                    raw = provider.complete(request)
                    injector.after_call(provider.name, True)
                except FaultError as exc:
                    error = ProviderError(exc.kind, provider.name, exc.detail)
                except ProviderError as exc:
                    error = exc
                else:
                    latency = int((self._clock() - started) * 1000)
                    breaker.on_success()
                    attempt = Attempt(provider.name, index, "ok", latency, "answered")
                    attempts.append(attempt)
                    self.history.append(attempt)
                    return RouteResult(provider=provider.name, raw=raw, attempts=attempts)

                latency = int((self._clock() - started) * 1000)
                attempt = Attempt(provider.name, index, error.kind, latency, error.message)
                attempts.append(attempt)
                self.history.append(attempt)
                failed = True

                if error.kind in TERMINAL_KINDS or not error.retryable:
                    break
                if index < limit and self.backoff_seconds:
                    self._sleep(self.backoff_seconds * (2 ** (index - 1)))

            if failed:
                breaker.on_failure()

        raise ProviderError(
            "exhausted",
            "",
            "all providers unavailable: "
            + "; ".join(f"{a.provider}={a.outcome}" for a in attempts),
        )

    def status(self) -> dict:
        per_provider: dict[str, dict] = {}
        for provider in self.providers:
            recent = [a for a in self.history if a.provider == provider.name][-20:]
            successes = sum(1 for a in recent if a.outcome == "ok")
            per_provider[provider.name] = {
                "name": provider.name,
                "priority": provider.priority,
                "configured": provider.configured(),
                "breaker": self.breakers[provider.name].snapshot(),
                "recent_calls": len(recent),
                "recent_successes": successes,
                "recent_failures": len(recent) - successes,
                "last_outcome": recent[-1].outcome if recent else None,
            }
        return {
            "order": [p.name for p in self.providers],
            "policy": {
                "max_attempts": self.max_attempts,
                "backoff_seconds": self.backoff_seconds,
                "timeout_seconds": default_settings.llm_timeout_seconds,
            },
            "providers": per_provider,
        }


# --------------------------------------------------------------------------
# Process-wide chain
# --------------------------------------------------------------------------

_chain: ProviderChain | None = None


def build_chain(cfg: Settings | None = None, **kwargs) -> ProviderChain:
    cfg = cfg or default_settings
    return ProviderChain([GeminiProvider(cfg), GroqProvider(cfg)], cfg=cfg, **kwargs)


def get_chain() -> ProviderChain:
    global _chain
    if _chain is None:
        _chain = build_chain()
    return _chain


def reset_chain() -> None:
    """Drop the memoised chain (used by tests that mutate settings)."""
    global _chain
    _chain = None
