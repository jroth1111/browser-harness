"""Standalone CrawlState and SafetyGate — no CDP dependency.

Ported from browser-harness helpers.py for use in food-delivery scripts."""
import json, time
from collections import deque
from pathlib import Path


class CrawlState:
    """In-memory dedup/accumulator for crawls. Save/load to JSON for resumption."""

    def __init__(self, key_field, marginal_window=5):
        self.key_field = key_field
        self._occurrences = {}
        self._records = []
        self._dup_attempts = 0
        self._blocked = []
        self._scope_totals = {}
        self._marginal = deque(maxlen=marginal_window)

    def add(self, record):
        key = record.get(self.key_field)
        if key is None:
            return False
        if key in self._occurrences:
            self._occurrences[key] += 1
            self._dup_attempts += 1
            return False
        self._occurrences[key] = 1
        self._records.append(record)
        return True

    def record_blocked(self, url, reason=""):
        self._blocked.append({"url": url, "reason": reason})

    def record_scope_total(self, scope, expected):
        self._scope_totals[scope] = self._scope_totals.get(scope, 0) + expected

    def page_done(self, new_count):
        self._marginal.append(new_count)

    def saturation_reached(self, k=3):
        if len(self._marginal) < k:
            return False
        return all(c == 0 for c in list(self._marginal)[-k:])

    def estimated_unseen(self):
        f1 = sum(1 for c in self._occurrences.values() if c == 1)
        f2 = sum(1 for c in self._occurrences.values() if c == 2)
        if f1 == 0:
            return 0
        if f2 == 0:
            return f1 * (f1 - 1) // 2
        return f1 * f1 // (2 * f2)

    def summary(self):
        return {
            "records": len(self._records),
            "deduped": self._dup_attempts,
            "blocked": len(self._blocked),
            "scope_totals": dict(self._scope_totals),
            "saturated": self.saturation_reached(),
            "estimated_unseen": self.estimated_unseen(),
        }

    def save(self, path):
        data = {
            "key_field": self.key_field,
            "marginal_window": self._marginal.maxlen,
            "occurrences": self._occurrences,
            "records": self._records,
            "dup_attempts": self._dup_attempts,
            "blocked": self._blocked,
            "scope_totals": self._scope_totals,
            "marginal": list(self._marginal),
        }
        Path(path).write_text(json.dumps(data, default=str))
        return path

    @staticmethod
    def load(path):
        data = json.loads(Path(path).read_text())
        CrawlState._validate_checkpoint(data, path)
        cs = CrawlState(data["key_field"], marginal_window=data.get("marginal_window", 5))
        cs._occurrences = data.get("occurrences", {})
        cs._records = data.get("records", [])
        cs._dup_attempts = data.get("dup_attempts", 0)
        cs._blocked = data.get("blocked", [])
        cs._scope_totals = data.get("scope_totals", {})
        cs._marginal = deque(data.get("marginal", []), maxlen=cs._marginal.maxlen)
        return cs

    @staticmethod
    def _validate_checkpoint(data, path):
        if not isinstance(data, dict):
            raise ValueError(f"{path}: crawl checkpoint must be a JSON object")
        if not isinstance(data.get("key_field"), str) or not data["key_field"]:
            raise ValueError(f"{path}: crawl checkpoint field 'key_field' must be a non-empty string")
        expected_shapes = {
            "occurrences": dict,
            "records": list,
            "blocked": list,
            "scope_totals": dict,
            "marginal": list,
        }
        for field, expected_type in expected_shapes.items():
            if field in data and not isinstance(data[field], expected_type):
                raise ValueError(f"{path}: crawl checkpoint field '{field}' must be {expected_type.__name__}")
        for field in ("dup_attempts", "marginal_window"):
            if field in data and not isinstance(data[field], int):
                raise ValueError(f"{path}: crawl checkpoint field '{field}' must be int")


class SafetyGate:
    """Configurable safety limits for crawl sessions."""

    def __init__(self, max_requests=None, max_seconds=None,
                 consecutive_block_threshold=None, backoff_on_429=True,
                 raise_on_fail=False):
        self._max_requests = max_requests
        self._max_seconds = max_seconds
        self._block_threshold = consecutive_block_threshold
        self._backoff_on_429 = backoff_on_429
        self._raise = raise_on_fail
        self._count = 0
        self._start = time.time()
        self._consecutive_blocks = 0
        self._count_429 = 0
        self._backoff_until = 0.0
        self._backoff_dur = 1.0

    def ok(self):
        if self._max_requests is not None and self._count >= self._max_requests:
            return self._fail("max_requests")
        if self._max_seconds is not None and time.time() - self._start >= self._max_seconds:
            return self._fail("max_seconds")
        if self._block_threshold is not None and self._consecutive_blocks >= self._block_threshold:
            return self._fail("consecutive_blocks")
        if time.time() < self._backoff_until:
            return self._fail("backoff")
        self._count += 1
        return True

    def record(self, status_code, blocked=False):
        if blocked:
            self._consecutive_blocks += 1
        else:
            self._consecutive_blocks = 0
        if status_code == 429 and self._backoff_on_429:
            self._count_429 += 1
            self._backoff_until = time.time() + self._backoff_dur
            self._backoff_dur = min(self._backoff_dur * 2, 60.0)

    def summary(self):
        return {
            "requests": self._count,
            "elapsed_seconds": round(time.time() - self._start, 1),
            "consecutive_blocks": self._consecutive_blocks,
            "429_count": self._count_429,
            "limits_reached": self._limits_reached(),
            "backoff_until": self._backoff_until if self._backoff_until > time.time() else None,
        }

    def reset(self):
        self._count = 0
        self._start = time.time()
        self._consecutive_blocks = 0
        self._count_429 = 0
        self._backoff_until = 0.0
        self._backoff_dur = 1.0

    def _fail(self, reason):
        if self._raise:
            raise RuntimeError(f"SafetyGate limit: {reason}")
        return False

    def _limits_reached(self):
        hit = []
        if self._max_requests is not None and self._count >= self._max_requests:
            hit.append("max_requests")
        if self._max_seconds is not None and time.time() - self._start >= self._max_seconds:
            hit.append("max_seconds")
        if self._block_threshold is not None and self._consecutive_blocks >= self._block_threshold:
            hit.append("consecutive_blocks")
        return hit
