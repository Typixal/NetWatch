"""Heuristics for connections worth a second look.

Deliberately conservative: a flag means "show this to the user", not "this is
malicious". False positives cost the user attention, so each rule is narrow.
"""

from __future__ import annotations

import ipaddress

from netwatch.core.store import Connection

#: Destinations common enough that an unresolvable reverse record is unremarkable.
KNOWN_SAFE_CIDRS = [
    "8.8.8.0/24",      # Google DNS
    "1.1.1.0/24",      # Cloudflare DNS
    "17.0.0.0/8",      # Apple
    "13.0.0.0/8",      # Amazon AWS
    "142.250.0.0/15",  # Google
    "104.16.0.0/12",   # Cloudflare
    "20.0.0.0/8",      # Microsoft Azure
    "52.0.0.0/6",      # Amazon
    "162.158.0.0/15",  # Cloudflare
]

_SAFE_NETS = [ipaddress.ip_network(c) for c in KNOWN_SAFE_CIDRS]

#: IRC/Tor/common RAT ports — unusual for a normal desktop app.
SUSPICIOUS_PORTS = {6666, 6667, 6668, 6669, 1337, 31337, 4444, 9001, 9030}

#: Windows processes that have no business talking to the internet.
SYSTEM_ONLY = {"Registry", "System", "smss.exe", "csrss.exe", "wininit.exe"}


class FlagEngine:
    def evaluate(self, conn: Connection) -> bool:
        """Set ``flagged``/``flag_reason`` on the connection. Returns flagged."""
        conn.flagged = False
        conn.flag_reason = ""

        try:
            addr = ipaddress.ip_address(conn.remote_ip)
        except ValueError:
            return False

        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return False  # LAN traffic isn't what this tool is watching for

        if conn.process_name in SYSTEM_ONLY:
            return self._flag(
                conn, f"system process {conn.process_name} connecting externally"
            )

        if conn.remote_port in SUSPICIOUS_PORTS:
            return self._flag(conn, f"suspicious port {conn.remote_port}")

        if (
            conn.domain is None
            and not conn.dns_pending
            and not any(addr in net for net in _SAFE_NETS)
        ):
            return self._flag(conn, "unresolved IP outside known CDN/cloud ranges")

        return False

    @staticmethod
    def _flag(conn: Connection, reason: str) -> bool:
        conn.flagged = True
        conn.flag_reason = reason
        return True
