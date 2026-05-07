"""BudgetController — mandatory rate limits and stop conditions.

SafetyGate promoted from optional helper to governing enforcement.
Every request, navigation, replay, and crawl step must check budget.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BudgetConfig:
    max_requests_per_origin: int = 100
    max_concurrent_per_origin: int = 3
    request_interval_seconds: float = 0.5
    max_total_requests: int = 1000
    circuit_breaker_threshold: int = 3
    circuit_breaker_window_seconds: float = 60.0
    circuit_breaker_cooldown_seconds: float = 120.0


@dataclass
class OriginBudget:
    origin: str
    requests: int = 0
    last_request_at: float = 0.0
    failures: list[float] = field(default_factory=list)
    circuit_open: bool = False
    circuit_opened_at: float = 0.0


class BudgetController:
    """Enforce request budgets, rate limits, and circuit breakers."""

    def __init__(self, config: BudgetConfig | None = None):
        self.config = config or BudgetConfig()
        self._origins: dict[str, OriginBudget] = {}
        self._total_requests = 0
        self._writer_locks: dict[str, str] = {}  # profile_id -> lock_holder

    def ok(self, origin: str) -> tuple[bool, str]:
        """Check if a request to origin is allowed."""
        self._maybe_reset_circuit(origin)

        budget = self._get_budget(origin)

        if budget.circuit_open:
            return False, f"circuit breaker open for {origin}"

        if budget.requests >= self.config.max_requests_per_origin:
            return False, f"origin budget exhausted: {origin}"

        if self._total_requests >= self.config.max_total_requests:
            return False, "total request budget exhausted"

        elapsed = time.time() - budget.last_request_at
        if elapsed < self.config.request_interval_seconds:
            return False, f"rate limited: wait {self.config.request_interval_seconds - elapsed:.1f}s"

        return True, "ok"

    def record(self, origin: str, status: int | None = None, block: bool = False) -> None:
        """Record a request result."""
        budget = self._get_budget(origin)
        budget.requests += 1
        budget.last_request_at = time.time()
        self._total_requests += 1

        if block or (status is not None and status >= 400):
            budget.failures.append(time.time())
            self._check_circuit_breaker(origin)

    def claim_writer(self, profile_id: str, holder: str) -> bool:
        """Claim exclusive write access to a profile. Returns False if already held."""
        if profile_id in self._writer_locks:
            return False
        self._writer_locks[profile_id] = holder
        return True

    def release_writer(self, profile_id: str, holder: str) -> bool:
        if self._writer_locks.get(profile_id) == holder:
            del self._writer_locks[profile_id]
            return True
        return False

    def writer_holder(self, profile_id: str) -> str | None:
        return self._writer_locks.get(profile_id)

    def _get_budget(self, origin: str) -> OriginBudget:
        if origin not in self._origins:
            self._origins[origin] = OriginBudget(origin=origin)
        return self._origins[origin]

    def _check_circuit_breaker(self, origin: str) -> None:
        budget = self._get_budget(origin)
        now = time.time()
        window = self.config.circuit_breaker_window_seconds
        recent = [t for t in budget.failures if now - t < window]
        budget.failures = recent

        if len(recent) >= self.config.circuit_breaker_threshold:
            budget.circuit_open = True
            budget.circuit_opened_at = now

    def _maybe_reset_circuit(self, origin: str) -> None:
        budget = self._get_budget(origin)
        if not budget.circuit_open:
            return
        if time.time() - budget.circuit_opened_at > self.config.circuit_breaker_cooldown_seconds:
            budget.circuit_open = False
            budget.failures.clear()

    @property
    def total_requests(self) -> int:
        return self._total_requests
