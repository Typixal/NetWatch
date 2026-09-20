"""Per-process connection-count history, for the sparklines and the 60s chart.

psutil exposes no per-PID byte counters on Windows, so the design's traffic
graphs plot connection count over time instead. One sample per poll.
"""

from __future__ import annotations

import time
from collections import deque

from netwatch.core.store import ProcessGroup

#: 30 samples at the default 2s poll = a 60s window.
SAMPLES = 30
#: The sidebar sparkline is narrower than the detail chart.
SPARK_SAMPLES = 24
#: Forget a process that hasn't been seen for this long.
STALE_AFTER_S = 300.0


class HistoryTracker:
    def __init__(self, samples: int = SAMPLES) -> None:
        self._samples = samples
        self._series: dict[str, deque[int]] = {}
        self._last_seen: dict[str, float] = {}

    def record(self, groups: list[ProcessGroup]) -> None:
        """Append one sample per known process. Absent processes record a 0."""
        now = time.monotonic()
        counts = {g.name: len(g.connections) for g in groups}

        for name in counts:
            if name not in self._series:
                # Backfill so a new process starts flat rather than spiking.
                self._series[name] = deque([0] * self._samples, maxlen=self._samples)

        for name, series in self._series.items():
            series.append(counts.get(name, 0))
            if name in counts:
                self._last_seen[name] = now

        self._prune(now)

    def _prune(self, now: float) -> None:
        stale = [
            name
            for name, seen in self._last_seen.items()
            if now - seen > STALE_AFTER_S and not any(self._series.get(name, ()))
        ]
        for name in stale:
            self._series.pop(name, None)
            self._last_seen.pop(name, None)

    def series(self, name: str, samples: int | None = None) -> list[int]:
        """Counts oldest-first, always exactly ``samples`` long."""
        want = samples or self._samples
        data = list(self._series.get(name, ()))
        if len(data) < want:
            return [0] * (want - len(data)) + data
        return data[-want:]

    def spark(self, name: str) -> list[int]:
        return self.series(name, SPARK_SAMPLES)

    def stats(self, name: str) -> tuple[int, int, int]:
        """(peak, avg, now) over the full window."""
        data = self.series(name)
        if not data:
            return (0, 0, 0)
        return (max(data), round(sum(data) / len(data)), data[-1])

    def forget(self, name: str) -> None:
        self._series.pop(name, None)
        self._last_seen.pop(name, None)
