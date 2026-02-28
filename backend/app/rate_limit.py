from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import time


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, max_events: int, period_seconds: int) -> bool:
        now = time.time()
        window_start = now - period_seconds
        events = self._events[key]
        while events and events[0] < window_start:
            events.popleft()

        if len(events) >= max_events:
            return False

        events.append(now)
        return True


@dataclass
class ViolationRecord:
    key: str
    count: int


class ViolationTracker:
    """Counts suspicious actions in a rolling window."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def record(self, key: str, period_seconds: int) -> ViolationRecord:
        now = time.time()
        events = self._events[key]
        window_start = now - period_seconds

        while events and events[0] < window_start:
            events.popleft()

        events.append(now)
        return ViolationRecord(key=key, count=len(events))
