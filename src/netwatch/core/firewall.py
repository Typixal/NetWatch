"""Outbound blocking through Windows Firewall.

Every rule NetWatch writes is named ``NetWatch_block_<process>``, so the app
can always find its own rules again and remove exactly those — nothing else
in the firewall is ever touched.

Writing rules needs admin. The manager itself does not: it talks to a
``Backend``, which is either direct netsh (when already elevated) or the
elevated broker (see ``elevation.py``).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Protocol

import psutil

from netwatch.utils.paths import blocklist_path

RULE_PREFIX = "NetWatch_block_"

#: Rule names appear verbatim in netsh output regardless of Windows display
#: language, so match on the name rather than on localized field labels.
_RULE_RE = re.compile(re.escape(RULE_PREFIX) + r"(\S+)")

# Keep console windows from flashing when the GUI shells out.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def rule_name(process_name: str) -> str:
    return f"{RULE_PREFIX}{process_name}"


def _netsh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["netsh", "advfirewall", "firewall", *args],
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )


class Backend(Protocol):
    def add_rule(self, name: str, exe_path: str) -> bool: ...
    def delete_rule(self, name: str) -> bool: ...
    def list_rules(self) -> list[str]: ...


class DirectBackend:
    """Runs netsh in this process. Only works when already elevated."""

    def add_rule(self, name: str, exe_path: str) -> bool:
        r = _netsh(
            "add", "rule",
            f"name={name}",
            "dir=out",
            "action=block",
            f"program={exe_path}",
            "enable=yes",
        )
        return r.returncode == 0

    def delete_rule(self, name: str) -> bool:
        r = _netsh("delete", "rule", f"name={name}")
        # A rule that isn't there is the state we wanted, not a failure.
        return r.returncode == 0 or "No rules match" in (r.stdout or "")

    def list_rules(self) -> list[str]:
        r = _netsh("show", "rule", "name=all")
        if r.returncode != 0:
            return []
        return sorted({m.group(0) for m in _RULE_RE.finditer(r.stdout or "")})


class FirewallManager:
    """Which processes are blocked, and the rules backing that."""

    def __init__(self, backend: Backend | None = None) -> None:
        self._backend: Backend = backend or DirectBackend()
        self._blocklist: dict[str, str] = {}  # process name -> exe path
        self._load()

    # — state —

    def is_blocked(self, process_name: str) -> bool:
        return process_name in self._blocklist

    def blocked_processes(self) -> list[str]:
        return sorted(self._blocklist)

    def set_backend(self, backend: Backend) -> None:
        self._backend = backend

    # — actions —

    def block(self, process_name: str, exe_path: str | None = None) -> bool:
        exe = exe_path or self._blocklist.get(process_name) or find_exe(process_name)
        if not exe:
            return False  # can't write a program-scoped rule without a path
        if not self._backend.add_rule(rule_name(process_name), exe):
            return False
        self._blocklist[process_name] = exe
        self._save()
        return True

    def unblock(self, process_name: str) -> bool:
        if not self._backend.delete_rule(rule_name(process_name)):
            return False
        self._blocklist.pop(process_name, None)
        self._save()
        return True

    def sync_with_firewall(self) -> list[str]:
        """Reconcile blocklist.json against the rules actually present.

        The two drift apart whenever the app dies between writing a rule and
        saving its state. Returns the process names that were dropped.
        """
        try:
            live = set(self._backend.list_rules())
        except OSError:
            return []
        if not live and not self._blocklist:
            return []

        dropped = [name for name in self._blocklist if rule_name(name) not in live]
        for name in dropped:
            self._blocklist.pop(name, None)
        if dropped:
            self._save()
        return dropped

    def cleanup_all_rules(self) -> int:
        """Remove every rule NetWatch ever wrote. Returns how many went."""
        removed = 0
        for name in self._backend.list_rules():
            if self._backend.delete_rule(name):
                removed += 1
        self._blocklist.clear()
        self._save()
        return removed

    # — persistence —

    def _load(self) -> None:
        p = blocklist_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self._blocklist = {k: str(v) for k, v in data.items()}

    def _save(self) -> None:
        try:
            blocklist_path().write_text(
                json.dumps(self._blocklist, indent=2), encoding="utf-8"
            )
        except OSError:
            pass


def find_exe(process_name: str) -> str | None:
    """Full path of a running process with this name, if we're allowed to see it."""
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            if proc.info["name"] == process_name and proc.info["exe"]:
                return proc.info["exe"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None
