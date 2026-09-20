"""Reverse DNS with an on-disk cache, resolved off the UI and poller threads.

``socket.gethostbyaddr`` can block for 5-30s on a cold lookup, so every
resolution goes through a small thread pool and results arrive later via the
``dns_resolved`` signal.

Two things the cache has to get right:

* A failed lookup is remembered as a *failure*, not as "the domain is the IP
  string". Storing the IP would make ``resolve_cached`` always truthy and the
  flag engine's "unresolved destination" rule would never fire.
* The cache is capped and its disk writes are debounced. Otherwise a busy
  machine rewrites the whole JSON file once per resolution.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QObject, pyqtSignal

from netwatch.utils.paths import dns_cache_path

MAX_ENTRIES = 5000
SAVE_INTERVAL_S = 5.0
MAX_WORKERS = 8

#: Marker for "we looked this IP up and it has no reverse record".
FAILED = None


class DNSResolver(QObject):
    """Owns the IP -> hostname cache. Lives on the main thread; never moved."""

    dns_resolved = pyqtSignal(str, str)  # (ip, domain) — domain "" means failed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # ip -> hostname, or FAILED. Ordered so we can evict least-recent.
        self._cache: OrderedDict[str, str | None] = OrderedDict()
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(
            max_workers=MAX_WORKERS, thread_name_prefix="dns"
        )
        self._dirty = False
        self._last_save = 0.0
        self._closed = False
        self._load_cache()

    # — lookups —

    def resolve_cached(self, ip: str) -> str | None:
        """The hostname for ``ip``, or None if unknown, pending, or unresolvable."""
        with self._lock:
            host = self._cache.get(ip, FAILED)
            if host is not FAILED:
                self._cache.move_to_end(ip)
            return host

    def is_known(self, ip: str) -> bool:
        """True once we've tried this IP, whether or not it resolved.

        Distinct from ``resolve_cached`` returning None, which conflates
        "never tried" with "tried and failed".
        """
        with self._lock:
            return ip in self._cache

    def enqueue(self, ip: str) -> None:
        with self._lock:
            if self._closed or ip in self._cache or ip in self._pending:
                return
            self._pending.add(ip)
        self._pool.submit(self._resolve, ip)

    def enqueue_bulk(self, ips) -> None:
        for ip in ips:
            self.enqueue(ip)

    # — worker —

    def _resolve(self, ip: str) -> None:
        try:
            host: str | None = socket.gethostbyaddr(ip)[0]
        except (socket.herror, socket.gaierror, OSError):
            host = FAILED  # remembered as a failure, so we don't retry forever

        with self._lock:
            self._cache[ip] = host
            self._cache.move_to_end(ip)
            self._pending.discard(ip)
            self._evict_locked()
            self._dirty = True

        self.dns_resolved.emit(ip, host or "")
        self._save_if_due()

    def _evict_locked(self) -> None:
        while len(self._cache) > MAX_ENTRIES:
            self._cache.popitem(last=False)  # least recently used

    # — persistence —

    def _load_cache(self) -> None:
        p = dns_cache_path()
        if not p.exists():
            return
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        with self._lock:
            for ip, host in raw.items():
                # null on disk means a remembered failure
                self._cache[ip] = host if isinstance(host, str) else FAILED
            self._evict_locked()

    def _save_if_due(self, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            if not self._dirty:
                return
            if not force and now - self._last_save < SAVE_INTERVAL_S:
                return
            data = dict(self._cache)
            self._last_save = now
            self._dirty = False

        p = dns_cache_path()
        tmp = p.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(p)  # atomic swap, so a crash can't truncate the cache
        except OSError:
            with self._lock:
                self._dirty = True  # try again on the next resolution

    def flush(self) -> None:
        """Write pending changes now. Called on shutdown."""
        self._save_if_due(force=True)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.flush()
