# NetWatch — Developer Handoff for Claude Code

## What This Is

A desktop app that shows which processes on the machine are making network
connections, where they're connecting to, and lets the user block them via
Windows Firewall. No cloud, no account, no installer bloat.

Built with Python + PyQt6. All user data lives in `%LOCALAPPDATA%\NetWatch\`
— nothing touches `C:\` root, no registry spam beyond what netsh writes for
firewall rules.

---

## Tech Stack

| Layer | Library | Version |
|---|---|---|
| UI | PyQt6 | `>=6.6.0` |
| Process/network data | psutil | `>=5.9.8` |
| Packaging | PyInstaller | `>=6.4.0` |
| DNS (stdlib) | socket | built-in |
| Firewall | subprocess (netsh) | built-in |
| Config/state | json | built-in |
| Concurrency | QThread + ThreadPoolExecutor | built-in |

Python minimum: **3.11**

No external HTTP calls. No telemetry. No cloud SDK.

---

## Directory Structure

### Source tree
```
netwatch/
├── main.py                  # entry point, bootstraps QApplication
├── core/
│   ├── __init__.py
│   ├── poller.py            # NetworkPoller QThread — psutil polling loop
│   ├── dns_resolver.py      # cached reverse DNS, non-blocking
│   ├── firewall.py          # netsh wrapper for block/unblock
│   ├── store.py             # ConnectionStore — holds live + history state
│   └── flags.py             # FlagEngine — heuristics for suspicious connections
├── ui/
│   ├── __init__.py
│   ├── main_window.py       # QMainWindow, wires everything together
│   ├── table.py             # connection table widget (grouped by process)
│   ├── summary_bar.py       # four stat cards at the top
│   └── tray.py              # system tray icon + context menu
└── utils/
    ├── __init__.py
    └── paths.py             # all %LOCALAPPDATA% path resolution lives here
```

### Runtime data tree (never touches C:\ root)
```
%LOCALAPPDATA%\NetWatch\
├── config.json              # user prefs (refresh interval, theme, etc.)
├── blocklist.json           # persisted blocked process names + firewall rule names
├── logs\
│   └── YYYY-MM-DD.jsonl     # append-only connection log, one JSON object per line
└── cache\
    └── dns_cache.json       # persisted DNS cache so cold starts resolve faster
```

All path resolution goes through `utils/paths.py`. Nothing else should
construct paths — this keeps the C-drive discipline enforced in one place.

---

## utils/paths.py

```python
import os
from pathlib import Path

_BASE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "NetWatch"

def app_dir() -> Path:
    _BASE.mkdir(parents=True, exist_ok=True)
    return _BASE

def config_path() -> Path:
    return app_dir() / "config.json"

def blocklist_path() -> Path:
    return app_dir() / "blocklist.json"

def log_dir() -> Path:
    d = app_dir() / "logs"
    d.mkdir(exist_ok=True)
    return d

def today_log_path() -> Path:
    from datetime import date
    return log_dir() / f"{date.today().isoformat()}.jsonl"

def cache_dir() -> Path:
    d = app_dir() / "cache"
    d.mkdir(exist_ok=True)
    return d

def dns_cache_path() -> Path:
    return cache_dir() / "dns_cache.json"
```

---

## Data Model

```python
# core/store.py  — dataclasses used everywhere

from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Connection:
    pid: int
    process_name: str          # e.g. "chrome.exe"
    remote_ip: str             # e.g. "142.250.80.46"
    remote_port: int           # e.g. 443
    status: str                # ESTABLISHED | TIME_WAIT | CLOSE_WAIT | SYN_SENT
    domain: str | None         # None = DNS resolution pending
    flagged: bool = False      # FlagEngine output
    flag_reason: str = ""      # human-readable reason if flagged
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)

    @property
    def key(self) -> tuple:
        """Unique identity for deduplication across polls."""
        return (self.pid, self.remote_ip, self.remote_port)

@dataclass
class ProcessGroup:
    name: str                              # process name
    pids: set[int] = field(default_factory=set)
    connections: list[Connection] = field(default_factory=list)
    blocked: bool = False

    @property
    def flagged(self) -> bool:
        return any(c.flagged for c in self.connections)
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Main Thread (UI)                                                │
│                                                                  │
│  QMainWindow                                                     │
│    ├── SummaryBar (4 stat cards)                                 │
│    ├── SearchBar + StatusFilter                                  │
│    └── ConnectionTable (grouped QTableWidget)                    │
│         └── per-row: Block / Unblock button                      │
└───────────────────┬──────────────────────────────────────────────┘
                    │  Qt signals (thread-safe, queued connection)
                    │  connections_updated(list[ProcessGroup])
┌───────────────────▼──────────────────────────────────────────────┐
│  NetworkPoller (QThread)                                         │
│                                                                  │
│  loop every N seconds:                                           │
│    raw = psutil.net_connections(kind="inet")                     │
│    enriched = [build Connection from each raw conn]              │
│    grouped = group by process name                               │
│    dns_resolver.enqueue_bulk(all unseen IPs)                     │
│    emit connections_updated(grouped)                             │
└───────────────────┬──────────────────────────────────────────────┘
                    │  enqueue / resolve_cached
┌───────────────────▼──────────────────────────────────────────────┐
│  DNSResolver                                                     │
│                                                                  │
│  cache: dict[str, str]   (ip → domain, loaded from disk)        │
│  pending: set[str]       (IPs currently being resolved)          │
│  ThreadPoolExecutor(max_workers=8)                               │
│                                                                  │
│  enqueue(ip): if not cached and not pending → submit to pool     │
│  resolve_cached(ip) → str | None                                 │
│  on resolution: cache[ip] = domain, emit dns_resolved(ip,domain) │
└──────────────────────────────────────────────────────────────────┘
                    │  (separate, called on user action only)
┌───────────────────▼──────────────────────────────────────────────┐
│  FirewallManager                                                 │
│                                                                  │
│  block(process_name, exe_path=None)                              │
│    → netsh advfirewall firewall add rule                         │
│         name="NetWatch_block_{process_name}"                     │
│         program="{exe_path}"                                     │
│         action=block dir=out                                     │
│                                                                  │
│  unblock(process_name)                                           │
│    → netsh advfirewall firewall delete rule                      │
│         name="NetWatch_block_{process_name}"                     │
│                                                                  │
│  list_netwatch_rules() → list[str]   (for startup cleanup)       │
└──────────────────────────────────────────────────────────────────┘
```

---

## core/poller.py

```python
import psutil
from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime
from .store import Connection, ProcessGroup
from .dns_resolver import DNSResolver
from .flags import FlagEngine


class NetworkPoller(QThread):
    connections_updated = pyqtSignal(list)   # list[ProcessGroup]

    def __init__(self, dns_resolver: DNSResolver, interval_ms: int = 2000):
        super().__init__()
        self._interval_ms = interval_ms
        self._dns = dns_resolver
        self._flag_engine = FlagEngine()
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            groups = self._poll()
            self.connections_updated.emit(groups)
            self.msleep(self._interval_ms)

    def stop(self):
        self._running = False

    def _poll(self) -> list[ProcessGroup]:
        raw = psutil.net_connections(kind="inet")
        groups: dict[str, ProcessGroup] = {}

        for conn in raw:
            if not conn.raddr or not conn.pid:
                continue
            try:
                proc = psutil.Process(conn.pid)
                name = proc.name()
                exe = proc.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

            domain = self._dns.resolve_cached(conn.raddr.ip)
            if domain is None:
                self._dns.enqueue(conn.raddr.ip)

            c = Connection(
                pid=conn.pid,
                process_name=name,
                remote_ip=conn.raddr.ip,
                remote_port=conn.raddr.port,
                status=conn.status or "UNKNOWN",
                domain=domain,
            )
            self._flag_engine.evaluate(c)

            if name not in groups:
                groups[name] = ProcessGroup(name=name)
            groups[name].pids.add(conn.pid)
            groups[name].connections.append(c)

        return list(groups.values())
```

---

## core/dns_resolver.py

```python
import socket
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import QObject, pyqtSignal
from utils.paths import dns_cache_path


class DNSResolver(QObject):
    dns_resolved = pyqtSignal(str, str)   # (ip, domain)

    def __init__(self):
        super().__init__()
        self._cache: dict[str, str] = {}
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dns")
        self._load_cache()

    def resolve_cached(self, ip: str) -> str | None:
        return self._cache.get(ip)

    def enqueue(self, ip: str):
        with self._lock:
            if ip in self._cache or ip in self._pending:
                return
            self._pending.add(ip)
        self._pool.submit(self._resolve, ip)

    def enqueue_bulk(self, ips: list[str]):
        for ip in ips:
            self.enqueue(ip)

    def _resolve(self, ip: str):
        try:
            host = socket.gethostbyaddr(ip)[0]
        except (socket.herror, socket.gaierror, OSError):
            host = ip   # fall back to raw IP, don't retry
        with self._lock:
            self._cache[ip] = host
            self._pending.discard(ip)
        self.dns_resolved.emit(ip, host)
        self._save_cache()

    def _load_cache(self):
        p = dns_cache_path()
        if p.exists():
            try:
                self._cache = json.loads(p.read_text())
            except Exception:
                self._cache = {}

    def _save_cache(self):
        # write from background thread — use a temp file + rename for atomicity
        p = dns_cache_path()
        tmp = p.with_suffix(".tmp")
        with self._lock:
            data = dict(self._cache)
        tmp.write_text(json.dumps(data))
        tmp.replace(p)

    def shutdown(self):
        self._pool.shutdown(wait=False)
```

---

## core/flags.py

```python
import ipaddress
from .store import Connection

# Known safe CIDR ranges — connections to these are never flagged
KNOWN_SAFE_CIDRS = [
    "8.8.8.0/24",       # Google DNS
    "1.1.1.0/24",       # Cloudflare DNS
    "17.0.0.0/8",       # Apple
    "13.0.0.0/8",       # Amazon AWS
    "142.250.0.0/15",   # Google
    "104.16.0.0/12",    # Cloudflare
    "20.0.0.0/8",       # Microsoft Azure
    "52.0.0.0/6",       # Amazon
    "162.158.0.0/15",   # Cloudflare
]

_SAFE_NETS = [ipaddress.ip_network(c) for c in KNOWN_SAFE_CIDRS]

# Ports that are suspicious on non-standard processes
_SUSPICIOUS_PORTS = {6666, 6667, 6668, 6669, 1337, 31337, 4444, 9001, 9030}

# Standard system processes that should never connect externally
_SYSTEM_ONLY = {"Registry", "System", "smss.exe", "csrss.exe", "wininit.exe"}


class FlagEngine:
    def evaluate(self, conn: Connection):
        try:
            addr = ipaddress.ip_address(conn.remote_ip)
        except ValueError:
            return

        # Flag 1: unresolvable IP not in known ranges
        if conn.domain is None:
            safe = any(addr in net for net in _SAFE_NETS)
            if not safe:
                conn.flagged = True
                conn.flag_reason = "unresolved IP outside known CDN/cloud ranges"
                return

        # Flag 2: suspicious port
        if conn.remote_port in _SUSPICIOUS_PORTS:
            conn.flagged = True
            conn.flag_reason = f"suspicious port {conn.remote_port}"
            return

        # Flag 3: system process making outbound connection
        if conn.process_name in _SYSTEM_ONLY and not addr.is_private:
            conn.flagged = True
            conn.flag_reason = f"system process {conn.process_name} connecting externally"
```

---

## core/firewall.py

```python
import subprocess
import json
import psutil
from utils.paths import blocklist_path

RULE_PREFIX = "NetWatch_block_"


class FirewallManager:
    def __init__(self):
        self._blocklist: dict[str, str] = {}   # process_name → exe_path
        self._load()

    def block(self, process_name: str) -> bool:
        """Block all outbound traffic from this process name. Returns True on success."""
        exe_path = self._find_exe(process_name)
        if not exe_path:
            return False

        rule_name = f"{RULE_PREFIX}{process_name}"
        result = subprocess.run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name}",
            "dir=out",
            "action=block",
            f"program={exe_path}",
            "enable=yes",
        ], capture_output=True, text=True)

        if result.returncode == 0:
            self._blocklist[process_name] = exe_path
            self._save()
            return True
        return False

    def unblock(self, process_name: str) -> bool:
        rule_name = f"{RULE_PREFIX}{process_name}"
        result = subprocess.run([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={rule_name}",
        ], capture_output=True, text=True)

        if result.returncode == 0:
            self._blocklist.pop(process_name, None)
            self._save()
            return True
        return False

    def is_blocked(self, process_name: str) -> bool:
        return process_name in self._blocklist

    def cleanup_all_rules(self):
        """Remove every rule this app ever wrote — call on uninstall."""
        subprocess.run([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={RULE_PREFIX}*",
        ], capture_output=True)
        self._blocklist.clear()
        self._save()

    def _find_exe(self, process_name: str) -> str | None:
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                if proc.info["name"] == process_name:
                    return proc.info["exe"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _load(self):
        p = blocklist_path()
        if p.exists():
            try:
                self._blocklist = json.loads(p.read_text())
            except Exception:
                self._blocklist = {}

    def _save(self):
        blocklist_path().write_text(json.dumps(self._blocklist, indent=2))
```

---

## core/store.py (ConnectionStore)

```python
from .store import Connection, ProcessGroup   # dataclasses defined above
from .firewall import FirewallManager
import json
from datetime import datetime
from utils.paths import today_log_path


class ConnectionStore:
    """
    Holds the live state from the last poll and merges with previous state
    to preserve first_seen timestamps across refreshes.
    """

    def __init__(self, firewall: FirewallManager):
        self._firewall = firewall
        self._prev: dict[tuple, Connection] = {}   # key → Connection

    def update(self, groups: list[ProcessGroup]) -> list[ProcessGroup]:
        now = datetime.now()
        new_prev: dict[tuple, Connection] = {}

        for group in groups:
            group.blocked = self._firewall.is_blocked(group.name)
            for conn in group.connections:
                prev = self._prev.get(conn.key)
                if prev:
                    conn.first_seen = prev.first_seen   # preserve age
                conn.last_seen = now
                new_prev[conn.key] = conn

        self._prev = new_prev
        self._log(groups)
        return groups

    def _log(self, groups: list[ProcessGroup]):
        flagged = [
            {
                "ts": datetime.now().isoformat(),
                "process": c.process_name,
                "ip": c.remote_ip,
                "domain": c.domain,
                "port": c.remote_port,
                "reason": c.flag_reason,
            }
            for g in groups for c in g.connections if c.flagged
        ]
        if flagged:
            with open(today_log_path(), "a") as f:
                for entry in flagged:
                    f.write(json.dumps(entry) + "\n")
```

---

## ui/main_window.py (skeleton)

```python
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QHBoxLayout
from PyQt6.QtCore import Qt
from core.poller import NetworkPoller
from core.dns_resolver import DNSResolver
from core.firewall import FirewallManager
from core.store import ConnectionStore
from ui.summary_bar import SummaryBar
from ui.table import ConnectionTable
from ui.tray import TrayIcon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetWatch")
        self.setMinimumSize(900, 600)

        # Core components
        self._dns = DNSResolver()
        self._firewall = FirewallManager()
        self._store = ConnectionStore(self._firewall)

        # UI components
        self._summary = SummaryBar()
        self._table = ConnectionTable(self._firewall)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._summary)
        layout.addWidget(self._table)
        self.setCentralWidget(central)

        # System tray
        self._tray = TrayIcon(self)
        self._tray.show()

        # Poller thread
        self._poller = NetworkPoller(self._dns, interval_ms=2000)
        self._poller.connections_updated.connect(self._on_update)

        # DNS resolution triggers a lightweight table refresh for domain column
        self._dns.dns_resolved.connect(self._table.refresh_domain)

        self._poller.start()

    def _on_update(self, groups):
        enriched = self._store.update(groups)
        self._summary.update(enriched)
        self._table.update(enriched)

    def closeEvent(self, event):
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()

    def quit(self):
        self._poller.stop()
        self._poller.wait()
        self._dns.shutdown()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
```

---

## ui/table.py — Key Implementation Notes

The table uses a **custom grouped layout**, not a standard QTableWidget.
Implementation approach:

- Use `QTreeWidget` with two levels: process (parent row) and connection (child row)
- Parent row: process name, connection count, "block all" button
- Child row: pid, remote ip, domain, port, status badge, block button
- Flagged process groups get a red background on the parent row (`setBackground`)
- Blocked processes get strikethrough on the process name (`setFont` with strikethrough)

Status badge colors:
```python
STATUS_COLORS = {
    "ESTABLISHED":  ("#d1fae5", "#065f46"),   # (bg, text) green
    "TIME_WAIT":    ("#fef3c7", "#92400e"),   # amber
    "CLOSE_WAIT":   ("#f3f4f6", "#374151"),   # gray
    "SYN_SENT":     ("#dbeafe", "#1e40af"),   # blue
    "UNKNOWN":      ("#f3f4f6", "#374151"),   # gray
}
```

Use `QStyledItemDelegate` to render badge pills, not plain text.

Search/filter: connect `textChanged` on the search input to a filter method
that calls `setHidden(True/False)` on each row — do not re-query psutil.

---

## main.py

```python
import sys
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from ui.main_window import MainWindow


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def main():
    # Firewall rules require admin. Prompt if not elevated.
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("NetWatch")
    app.setOrganizationName("NetWatch")
    app.setQuitOnLastWindowClosed(False)   # keep alive in tray

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

---

## requirements.txt

```
PyQt6>=6.6.0
psutil>=5.9.8
pyinstaller>=6.4.0
```

---

## Build (PyInstaller — single exe, no installer)

```
pyinstaller \
  --onefile \
  --windowed \
  --name NetWatch \
  --icon assets/icon.ico \
  --add-data "assets;assets" \
  main.py
```

Output goes to `dist/NetWatch.exe`. User can put it wherever they want.
No installer, no registry entries beyond the firewall rules (and those
are cleaned up by the app's own cleanup method).

---

## UAC Note

Blocking via `netsh advfirewall` requires administrator privileges.
`main.py` re-launches itself elevated via `ShellExecuteW runas` if not
already admin. This is the correct Windows pattern — do not use
`manifest` embedding to always require admin, as that breaks drag-and-drop.

---

## Known Gotchas for Claude Code

1. **`psutil.net_connections()` requires admin on Windows** for full results.
   Without admin, connections from system processes (PID 4, svchost, etc.)
   return with `pid=None` and should be skipped silently.

2. **DNS resolution is slow** — `socket.gethostbyaddr` can block for 5–30s on
   cold lookups. Never call it on the main thread or the poller thread.
   Always via the ThreadPoolExecutor in DNSResolver.

3. **`psutil.Process(pid).exe()` raises `AccessDenied`** for many system
   processes even as admin. Always wrap in try/except and fall back to
   `process_name` only if exe path is unavailable.

4. **netsh rule names must be unique** — use the `NetWatch_block_` prefix
   consistently. On startup, call `list_netwatch_rules()` to sync the
   in-memory blocklist with what's actually in the firewall
   (they can get out of sync if the app crashes mid-block).

5. **QTreeWidget update flicker** — don't `clear()` and rebuild on every poll.
   Instead diff the incoming groups against current tree items and only
   add/remove/update changed rows. Use `process_name` as the stable key.

6. **DNS cache size** — the cache JSON will grow indefinitely. Cap it at 5000
   entries (evict LRU) before writing to disk.

7. **`app.setQuitOnLastWindowClosed(False)`** is required for tray-only mode.
   Without it, hiding the window quits the app.

---

## MVP Checklist (implement in this order)

- [ ] `utils/paths.py` — path resolution, verify %LOCALAPPDATA% writes work
- [ ] `core/dns_resolver.py` — cached resolver with ThreadPoolExecutor
- [ ] `core/poller.py` — polling loop, verify data comes through in terminal
- [ ] `core/flags.py` — flag engine, unit-testable with mock connections
- [ ] `core/firewall.py` — block/unblock, test with a real process
- [ ] `core/store.py` — merge/log logic
- [ ] `ui/summary_bar.py` — four stat cards
- [ ] `ui/table.py` — grouped tree widget with live updates
- [ ] `ui/main_window.py` — wire everything together
- [ ] `ui/tray.py` — system tray with show/quit menu
- [ ] `main.py` — UAC elevation + QApplication bootstrap
- [ ] PyInstaller build — single exe, test on a clean user account

---

## Dev Environment Setup (Keep C Drive Clean)

Use `uv` — it manages Python itself and all packages locally inside the
project folder. Nothing goes into system Python, no global pip installs,
no `C:\Users\<you>\AppData\Roaming\pip` accumulation.

### One-time setup

```powershell
# Install uv itself (goes to %LOCALAPPDATA%\uv\ — isolated, one binary)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone / create your project folder, then inside it:
uv init         # creates pyproject.toml
uv venv         # creates .venv\ inside the project folder

# Install deps into the local venv, never system Python
uv pip install pyqt6 psutil pyinstaller
```

### Daily use

```powershell
# Run the app (uv activates .venv automatically)
uv run python main.py

# Add a new package
uv pip install <package>

# Build the exe
uv run pyinstaller --onefile --windowed --name NetWatch main.py
```

### What stays inside the project folder

```
netwatch/
├── .venv\               # all packages live here — add to .gitignore
├── pyproject.toml       # uv project file
├── requirements.txt     # keep for reference / CI
├── dist\                # PyInstaller output (the final .exe)
├── build\               # PyInstaller temp — safe to delete after build
└── *.spec               # PyInstaller spec file
```

### .gitignore entries to add

```
.venv/
dist/
build/
*.spec
__pycache__/
*.pyc
```

### Nothing this project writes to C:\ root or system dirs

| What | Where |
|---|---|
| Python interpreter | `%LOCALAPPDATA%\uv\python\` (uv managed) |
| Packages | `<project>\.venv\` |
| App runtime data | `%LOCALAPPDATA%\NetWatch\` |
| Firewall rules | Windows Firewall (via netsh, cleaned up by app) |
| Startup registry key | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\NetWatch` |
| Built exe | `<project>\dist\NetWatch.exe` — user moves wherever they want |

---

## Run on Startup Toggle

### utils/startup.py

```python
import sys
import winreg
from pathlib import Path

_REG_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "NetWatch"


def _exe_path() -> str:
    """Returns the path to the running exe (works both frozen and dev)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller exe
        return sys.executable
    else:
        # Running as script during development — point to main.py
        return f'"{sys.executable}" "{Path(__file__).parent.parent / "main.py"}"'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False


def enable_startup():
    """Add NetWatch to HKCU Run — no admin required."""
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _REG_KEY,
        access=winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _exe_path())


def disable_startup():
    """Remove NetWatch from HKCU Run."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY,
            access=winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
    except FileNotFoundError:
        pass   # already not set, fine


def toggle_startup() -> bool:
    """Flip startup state. Returns new state (True = enabled)."""
    if is_startup_enabled():
        disable_startup()
        return False
    else:
        enable_startup()
        return True
```

`HKCU` (current user) requires no admin rights — distinct from the
firewall block which needs elevation. Keep them separate.

---

## ui/tray.py — Updated with Startup Toggle

```python
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from utils.startup import is_startup_enabled, toggle_startup


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self.setIcon(QIcon("assets/icon.ico"))
        self.setToolTip("NetWatch")

        menu = QMenu()

        show_action = QAction("Show NetWatch", menu)
        show_action.triggered.connect(self._show)
        menu.addAction(show_action)

        menu.addSeparator()

        # Startup toggle — checkmark reflects current state
        self._startup_action = QAction("Run on startup", menu)
        self._startup_action.setCheckable(True)
        self._startup_action.setChecked(is_startup_enabled())
        self._startup_action.triggered.connect(self._toggle_startup)
        menu.addAction(self._startup_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._window.quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activate)

    def _show(self):
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _toggle_startup(self):
        new_state = toggle_startup()
        self._startup_action.setChecked(new_state)

    def _on_activate(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show()
```

---

## Updated MVP Checklist

- [ ] `uv init` + `uv venv` — confirm packages install into `.venv\` not system
- [ ] `utils/paths.py` — %LOCALAPPDATA% path resolution
- [ ] `utils/startup.py` — registry read/write, test toggle works
- [ ] `core/dns_resolver.py`
- [ ] `core/poller.py` — verify data in terminal before touching UI
- [ ] `core/flags.py`
- [ ] `core/firewall.py`
- [ ] `core/store.py`
- [ ] `ui/summary_bar.py`
- [ ] `ui/table.py`
- [ ] `ui/tray.py` — includes startup toggle
- [ ] `ui/main_window.py`
- [ ] `main.py`
- [ ] PyInstaller build via `uv run pyinstaller ...`
- [ ] Test startup toggle works from both the built exe and dev mode
