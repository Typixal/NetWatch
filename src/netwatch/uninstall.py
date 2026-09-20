"""Remove every trace NetWatch leaves on the machine.

NetWatch has no installer, so this is the counterpart to simply running the
exe. It removes, in order:

1. Firewall rules named ``NetWatch_block_*`` (needs admin — will elevate)
2. The ``HKCU`` run-on-startup value
3. Any NetWatch shortcut in the user's Startup folder
4. ``%LOCALAPPDATA%\\NetWatch\\`` — config, blocklist, logs, DNS cache

It never touches anything it didn't create. Run with ``--dry-run`` first to
see the list; ``--yes`` skips the confirmation prompt.

    uv run python -m netwatch.uninstall --dry-run
    uv run python -m netwatch.uninstall

Safety: this module deletes a directory tree, so ``resolve_data_dir`` and
``is_safe_to_delete`` are deliberately paranoid. An earlier version resolved
an unset ``NETWATCH_DATA_DIR`` to ``Path("")``, which is ``Path(".")`` and
therefore *truthy* — it began deleting the working directory. Every check
below exists because of that.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from netwatch.core.firewall import DirectBackend
from netwatch.utils import startup
from netwatch.utils.paths import APP_NAME

#: Only these may exist inside the data dir. Anything else and we refuse to
#: delete it — the directory isn't what we think it is.
KNOWN_ENTRIES = {"config.json", "blocklist.json", "logs", "cache"}

#: Presence of any of these means we are pointed at something that is very
#: much not an app-data directory.
NEVER_DELETE_MARKERS = {
    ".git", ".venv", ".uv-cache", "src", "tests", "pyproject.toml",
    "node_modules", "Windows", "System32", "Program Files",
}


class UnsafeTarget(RuntimeError):
    """The resolved data directory failed its safety checks."""


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def resolve_data_dir() -> Path:
    """Where the app data lives — without creating it, and never the cwd.

    An empty or whitespace-only override is treated as absent. ``Path("")``
    is ``Path(".")``, so checking the *string* before building the Path is
    the part that matters here.
    """
    override = (os.environ.get("NETWATCH_DATA_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()

    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    root = Path(local) if local else Path.home() / "AppData" / "Local"
    return (root / APP_NAME).resolve()


def is_safe_to_delete(path: Path) -> tuple[bool, str]:
    """Whether ``path`` is plausibly a NetWatch data dir and nothing else."""
    if not path.is_absolute():
        return False, "path is not absolute"
    if path == Path(path.anchor):
        return False, "path is a filesystem root"
    if len(path.parts) < 3:
        return False, "path is too close to the filesystem root"
    if path.name != APP_NAME:
        return False, f"directory is not named {APP_NAME!r}"

    cwd = Path.cwd().resolve()
    if path == cwd or path in cwd.parents:
        return False, "path is the working directory or a parent of it"

    try:
        entries = {p.name for p in path.iterdir()}
    except OSError as exc:
        return False, f"cannot read directory ({exc})"

    unexpected = entries - KNOWN_ENTRIES
    if unexpected & NEVER_DELETE_MARKERS:
        return False, f"contains {sorted(unexpected & NEVER_DELETE_MARKERS)}"
    if unexpected:
        return False, f"contains unexpected entries {sorted(unexpected)[:5]}"

    return True, ""


def app_dir_if_exists() -> Path | None:
    path = resolve_data_dir()
    return path if path.is_dir() else None


@dataclass
class Report:
    found: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def anything_found(self) -> bool:
        return bool(self.found)


def survey() -> Report:
    """What's on the machine right now, without changing anything."""
    r = Report()

    for rule in _list_rules():
        r.found.append(f"firewall rule  {rule}")

    cmd = startup.registered_command()
    if cmd is not None:
        r.found.append(f"registry       HKCU\\...\\Run\\{startup.APP_NAME} = {cmd}")

    for link in _startup_links():
        r.found.append(f"startup link   {link}")

    data = app_dir_if_exists()
    if data is not None:
        safe, why = is_safe_to_delete(data)
        size = _dir_size(data) / 1024
        if safe:
            r.found.append(f"app data       {data}  ({size:.1f} KB)")
        else:
            r.skipped.append(f"app data       {data}  (refused: {why})")

    return r


def uninstall(dry_run: bool = False) -> Report:
    r = survey()
    if dry_run or not r.anything_found:
        return r

    # 1. Firewall rules — the only step that needs admin.
    rules = _list_rules()
    if rules:
        if is_admin():
            backend = DirectBackend()
            for rule in rules:
                target = f"firewall rule  {rule}"
                if backend.delete_rule(rule):
                    r.removed.append(target)
                else:
                    r.failed.append(target)
        else:
            for rule in rules:
                r.skipped.append(f"firewall rule  {rule}  (needs admin)")

    # 2. Run-on-startup registry value.
    if startup.registered_command() is not None:
        startup.disable_startup()
        if startup.registered_command() is None:
            r.removed.append("registry       run-on-startup value")
        else:
            r.failed.append("registry       run-on-startup value")

    # 3. Startup folder shortcuts.
    for link in _startup_links():
        try:
            link.unlink()
            r.removed.append(f"startup link   {link}")
        except OSError as exc:
            r.failed.append(f"startup link   {link}  ({exc})")

    # 4. App data — re-checked immediately before the delete, not just in
    #    the survey, so nothing can change underneath us in between.
    data = app_dir_if_exists()
    if data is not None:
        safe, why = is_safe_to_delete(data)
        if not safe:
            r.skipped.append(f"app data       {data}  (refused: {why})")
        else:
            try:
                shutil.rmtree(data)
                r.removed.append(f"app data       {data}")
            except OSError as exc:
                r.failed.append(f"app data       {data}  ({exc})")

    return r


# — helpers —


def _list_rules() -> list[str]:
    try:
        return DirectBackend().list_rules()
    except OSError:
        return []


def _startup_links() -> list[Path]:
    folder = startup_folder()
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.stem.lower().startswith("netwatch"))


def _dir_size(path: Path) -> int:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return 0


def _relaunch_elevated() -> int:
    """Re-run this uninstaller as admin so firewall rules can be deleted."""
    params = " ".join(f'"{a}"' for a in [*sys.argv[1:], "--yes"])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f"-m netwatch.uninstall {params}", None, 1
    )
    return 0 if rc > 32 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="netwatch-uninstall",
        description="Remove NetWatch's firewall rules, startup entry, and app data.",
    )
    ap.add_argument("--dry-run", action="store_true", help="list, change nothing")
    ap.add_argument("-y", "--yes", action="store_true", help="skip the prompt")
    ap.add_argument(
        "--no-elevate",
        action="store_true",
        help="don't ask for admin; skip firewall rules instead",
    )
    args = ap.parse_args(argv)

    found = survey()

    for item in found.skipped:
        print(f"  skipped  {item}")
    if found.skipped:
        print()

    if not found.anything_found:
        print("Nothing to remove — NetWatch has left no traces on this machine.")
        return 0

    print("NetWatch will remove:\n")
    for item in found.found:
        print(f"  {item}")
    print()

    if args.dry_run:
        print("Dry run — nothing was changed.")
        return 0

    needs_admin = any(f.startswith("firewall rule") for f in found.found)
    if needs_admin and not is_admin() and not args.no_elevate:
        print("Firewall rules need administrator rights. Requesting elevation...")
        return _relaunch_elevated()

    if not args.yes:
        answer = input("Remove all of the above? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled. Nothing was changed.")
            return 1

    r = uninstall()

    print()
    for item in r.removed:
        print(f"  removed  {item}")
    for item in r.skipped:
        print(f"  skipped  {item}")
    for item in r.failed:
        print(f"  FAILED   {item}")

    print()
    if r.failed:
        print(f"{len(r.removed)} removed, {len(r.failed)} failed.")
        return 1
    if r.skipped:
        print(
            f"{len(r.removed)} removed, {len(r.skipped)} skipped. "
            "Re-run as administrator to finish."
        )
        return 1
    print(f"NetWatch fully removed ({len(r.removed)} items).")
    print("The exe itself is yours to delete — it was never installed anywhere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
