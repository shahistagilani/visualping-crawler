"""The crawl frontier: a FIFO queue plus every enqueue-time guard.

Responsibilities:
  * never enqueue the same canonical URL twice,
  * enforce the depth and frontier-size budgets,
  * reject spider-trap URL shapes,
  * cap the number of distinct values seen for any one query parameter on a
    given path (this is what stops ``/report/?page=N`` running forever).
"""

from __future__ import annotations

from collections import defaultdict, deque
from urllib.parse import parse_qsl, urlsplit

from .config import Limits
from .urlnorm import is_trap_shape


class Frontier:
    def __init__(self, limits: Limits) -> None:
        self._limits = limits
        self._queue: deque[tuple[str, int]] = deque()
        self._seen: set[str] = set()
        self._param_values: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.rejected: dict[str, int] = defaultdict(int)
        self.rejected_urls: dict[str, list[str]] = defaultdict(list)

    def add(self, canonical_url: str, depth: int) -> bool:
        """Enqueue ``canonical_url`` if every guard passes. Return whether added."""
        if canonical_url in self._seen:
            return False
        if depth > self._limits.max_depth:
            self.rejected["depth"] += 1
            self.rejected_urls["depth"].append(canonical_url)
            return False
        if len(self._seen) >= self._limits.max_frontier:
            self.rejected["frontier_full"] += 1
            return False
        if is_trap_shape(canonical_url, self._limits):
            self.rejected["trap_shape"] += 1
            self.rejected_urls["trap_shape"].append(canonical_url)
            return False
        if not self._within_param_budget(canonical_url):
            self.rejected["param_budget"] += 1
            self.rejected_urls["param_budget"].append(canonical_url)
            return False

        self._seen.add(canonical_url)
        self._register_params(canonical_url)
        self._queue.append((canonical_url, depth))
        return True

    def pop(self) -> tuple[str, int]:
        return self._queue.popleft()

    def __bool__(self) -> bool:
        return bool(self._queue)

    def __len__(self) -> int:
        return len(self._queue)

    @property
    def discovered(self) -> int:
        return len(self._seen)

    def _within_param_budget(self, url: str) -> bool:
        parts = urlsplit(url)
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            known = self._param_values[(parts.path, key)]
            if value not in known and len(known) >= self._limits.max_values_per_param:
                return False
        return True

    def _register_params(self, url: str) -> None:
        parts = urlsplit(url)
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            self._param_values[(parts.path, key)].add(value)
