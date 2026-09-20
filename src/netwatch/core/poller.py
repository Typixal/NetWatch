"""The polling loop: psutil snapshot -> enriched connections grouped by process."""

from __future__ import annotations

import ipaddress

import psutil
from PyQt6.QtCore import QMutex, QThread, QWaitCondition, pyqtSignal

from netwatch.core.dns_resolver import DNSResolver
from netwatch.core.flags import FlagEngine
from netwatch.core.store import Connection, ProcessGroup

DEFAULT_INTERVAL_MS = 2000


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def snapshot(
    dns: DNSResolver | None = None,
    flags: FlagEngine | None = None,
    include_loopback: bool = False,
) -> list[ProcessGroup]:
    """One poll, grouped by process name. Importable without Qt running.

    Loopback connections are local IPC, not network egress — a firewall rule
    wouldn't meaningfully apply to them — so they're left out by default.
    """
    groups: dict[str, ProcessGroup] = {}

    try:
        raw = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        return []

    for conn in raw:
        # No remote address means a listener; no PID means we lack the rights
        # to attribute it (common for system processes without admin).
        if not conn.raddr or not conn.pid:
            continue
        if not include_loopback and _is_loopback(conn.raddr.ip):
            continue

        try:
            proc = psutil.Process(conn.pid)
            name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue

        try:
            exe = proc.exe() or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            exe = ""  # denied for most system processes even when elevated

        domain = None
        pending = True
        if dns is not None:
            domain = dns.resolve_cached(conn.raddr.ip)
            pending = not dns.is_known(conn.raddr.ip)
            if pending:
                dns.enqueue(conn.raddr.ip)

        c = Connection(
            pid=conn.pid,
            process_name=name,
            remote_ip=conn.raddr.ip,
            remote_port=conn.raddr.port,
            status=conn.status or "UNKNOWN",
            domain=domain,
            dns_pending=pending,
        )
        if flags is not None:
            flags.evaluate(c)

        group = groups.get(name)
        if group is None:
            group = groups[name] = ProcessGroup(name=name)
        group.pids.add(conn.pid)
        if exe and not group.exe:
            group.exe = exe
        group.connections.append(c)

    return sorted(groups.values(), key=lambda g: (-len(g.connections), g.name.lower()))


class NetworkPoller(QThread):
    connections_updated = pyqtSignal(list)  # list[ProcessGroup]

    def __init__(
        self,
        dns_resolver: DNSResolver,
        interval_ms: int = DEFAULT_INTERVAL_MS,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._dns = dns_resolver
        self._flags = FlagEngine()
        self._interval_ms = interval_ms
        self._running = False
        self._mutex = QMutex()
        self._wake = QWaitCondition()

    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    def set_interval(self, interval_ms: int) -> None:
        self._mutex.lock()
        self._interval_ms = interval_ms
        self._wake.wakeAll()
        self._mutex.unlock()

    def run(self) -> None:
        self._running = True
        while True:
            self.connections_updated.emit(snapshot(self._dns, self._flags))

            # Sleep on a condition rather than msleep, so stop() returns at
            # once instead of blocking for up to a full interval.
            self._mutex.lock()
            try:
                if not self._running:
                    return
                self._wake.wait(self._mutex, self._interval_ms)
                if not self._running:
                    return
            finally:
                self._mutex.unlock()

    def stop(self) -> None:
        self._mutex.lock()
        self._running = False
        self._wake.wakeAll()
        self._mutex.unlock()


def _cli() -> int:
    """Terminal harness: uv run python -m netwatch.core.poller"""
    import time

    from netwatch.core.history import HistoryTracker

    dns = DNSResolver()
    flags = FlagEngine()
    history = HistoryTracker()
    print("polling every 2s - ctrl-c to stop\n")
    try:
        while True:
            groups = snapshot(dns, flags)
            history.record(groups)
            total = sum(len(g.connections) for g in groups)
            print(f"=== {total} connections across {len(groups)} processes ===")
            for g in groups:
                peak, avg, now = history.stats(g.name)
                mark = "!" if g.flagged else " "
                print(
                    f"{mark} {g.name:<32} {len(g.connections):>3} conns  "
                    f"pid {g.pid}  peak {peak} avg {avg} now {now}"
                )
                for c in g.connections[:4]:
                    dom = c.domain or ("resolving..." if c.dns_pending else "unresolved")
                    reason = f"  <- {c.flag_reason}" if c.flagged else ""
                    endpoint = f"{c.remote_ip}:{c.remote_port}"
                    print(f"      {endpoint:<44} {c.status:<12} {dom}{reason}")
            print()
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        dns.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
