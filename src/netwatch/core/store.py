"""The data model, and the store that merges each poll into the last one."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, TextIO

from netwatch.utils.paths import log_path_for

if TYPE_CHECKING:
    from netwatch.core.firewall import FirewallManager


@dataclass
class Connection:
    pid: int
    process_name: str
    remote_ip: str
    remote_port: int
    status: str  # ESTABLISHED | TIME_WAIT | CLOSE_WAIT | SYN_SENT | ...
    domain: str | None = None  # None = lookup pending, or no reverse record
    #: True until the reverse lookup has finished. Distinguishes "we don't know
    #: yet" from "we looked and there is no record" — only the latter is worth
    #: flagging, or the first few polls would flag everything.
    dns_pending: bool = True
    flagged: bool = False
    flag_reason: str = ""
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)

    @property
    def key(self) -> tuple[int, str, int]:
        """Identity across polls, for preserving first_seen."""
        return (self.pid, self.remote_ip, self.remote_port)


@dataclass
class ProcessGroup:
    name: str
    pids: set[int] = field(default_factory=set)
    exe: str = ""
    connections: list[Connection] = field(default_factory=list)
    blocked: bool = False

    @property
    def flagged(self) -> bool:
        return any(c.flagged for c in self.connections)

    @property
    def pid(self) -> int | None:
        """Lowest PID, for display. Processes often have several."""
        return min(self.pids) if self.pids else None


class ConnectionStore:
    """Merges each poll with the previous one and logs flagged connections.

    Holds the append-only log handle open rather than reopening it per poll,
    and rolls over at midnight.
    """

    def __init__(self, firewall: FirewallManager | None = None) -> None:
        self._firewall = firewall
        self._prev: dict[tuple[int, str, int], Connection] = {}
        self._log_file: TextIO | None = None
        self._log_day: date | None = None

    def update(self, groups: list[ProcessGroup]) -> list[ProcessGroup]:
        now = datetime.now()
        merged: dict[tuple[int, str, int], Connection] = {}

        for group in groups:
            if self._firewall is not None:
                group.blocked = self._firewall.is_blocked(group.name)
            for conn in group.connections:
                prev = self._prev.get(conn.key)
                if prev is not None:
                    conn.first_seen = prev.first_seen  # preserve age
                conn.last_seen = now
                merged[conn.key] = conn

        self._prev = merged
        self._log(groups, now)
        return groups

    # — flagged-connection log —

    def _log(self, groups: list[ProcessGroup], now: datetime) -> None:
        entries = [
            {
                "ts": now.isoformat(timespec="seconds"),
                "process": c.process_name,
                "pid": c.pid,
                "ip": c.remote_ip,
                "domain": c.domain,
                "port": c.remote_port,
                "status": c.status,
                "reason": c.flag_reason,
            }
            for g in groups
            for c in g.connections
            if c.flagged
        ]
        if not entries:
            return

        handle = self._handle_for(now.date())
        if handle is None:
            return
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
        handle.flush()

    def _handle_for(self, day: date):
        if self._log_file is not None and self._log_day == day:
            return self._log_file
        self.close()
        try:
            self._log_file = log_path_for(day).open("a", encoding="utf-8")
        except OSError:
            self._log_file = None
            return None
        self._log_day = day
        return self._log_file

    def close(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
        self._log_file = None
        self._log_day = None
