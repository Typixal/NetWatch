"""Run-on-startup toggle, via the per-user Run key.

``HKCU`` needs no admin rights — deliberately separate from the firewall
blocking, which does. Nothing here should ever prompt for elevation.

The subkey is overridable so tests can exercise the real registry without
touching the machine's actual startup entries.
"""

from __future__ import annotations

import subprocess
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "NetWatch"

# Rebound by tests; production code never changes these.
_key_path = RUN_KEY
_value_name = APP_NAME


def _quote(s: str) -> str:
    return f'"{s}"'


def startup_command() -> str:
    """The command Windows should run at logon.

    Frozen: the exe alone. From source: the interpreter plus ``-m netwatch``,
    using ``pythonw.exe`` so logon doesn't flash a console window.
    """
    if getattr(sys, "frozen", False):
        return _quote(sys.executable)

    exe = Path(sys.executable)
    windowed = exe.with_name("pythonw.exe")
    interpreter = windowed if windowed.exists() else exe
    # netwatch is installed into the venv, so -m resolves without a path hack.
    return f"{_quote(str(interpreter))} -m netwatch"


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _key_path) as key:
            winreg.QueryValueEx(key, _value_name)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def registered_command() -> str | None:
    """What's actually in the registry right now, or None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _key_path) as key:
            value, _ = winreg.QueryValueEx(key, _value_name)
            return value
    except (FileNotFoundError, OSError):
        return None


def enable_startup() -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, _key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, _value_name, 0, winreg.REG_SZ, startup_command())


def disable_startup() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _value_name)
    except FileNotFoundError:
        pass  # already gone — that's the state we wanted


def toggle_startup() -> bool:
    """Flip the setting. Returns the new state (True = runs at logon)."""
    if is_startup_enabled():
        disable_startup()
        return False
    enable_startup()
    return True


def _cli() -> int:
    """Manual verification harness: python -m netwatch.utils.startup [on|off]."""
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "on":
        enable_startup()
    elif arg == "off":
        disable_startup()
    elif arg == "toggle":
        toggle_startup()
    elif arg != "status":
        print(f"usage: {sys.argv[0]} [status|on|off|toggle]", file=sys.stderr)
        return 2

    print(f"enabled : {is_startup_enabled()}")
    print(f"command : {registered_command()}")
    print(f"would be: {startup_command()}")
    # Cross-check through reg.exe, so we're not just reading back our own API.
    r = subprocess.run(
        ["reg", "query", rf"HKCU\{_key_path}", "/v", _value_name],
        capture_output=True,
        text=True,
    )
    print(f"reg.exe : rc={r.returncode} {r.stdout.strip() or r.stderr.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
