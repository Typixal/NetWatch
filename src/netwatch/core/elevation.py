"""Running a single netsh command as administrator.

NetWatch itself runs unelevated. Only firewall writes need admin, so only
those elevate — one UAC prompt per block or unblock.

There is deliberately no long-lived elevated helper. A helper would mean one
prompt per session instead of one per action, but it would also leave an
elevated command channel open for as long as NetWatch runs, and any process
running as the same user could drive it. Restricting the channel's ACL to
the current user does not help: the threat is unelevated code running as
that very user. A prompt per action keeps the elevated window as short as
the command itself.

``ShellExecuteW`` cannot redirect stdio, so the elevated child's result
comes back as its exit code, which is all we need.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from netwatch.core.firewall import Backend, rule_name

SW_HIDE = 0
#: ShellExecuteW returns a value > 32 on success. 1223 is ERROR_CANCELLED.
_SHELL_SUCCESS = 32
ERROR_CANCELLED = 1223

#: How long to wait for the elevated netsh to finish before giving up.
WAIT_TIMEOUT_S = 30.0

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SEE_MASK_NO_UI = 0x00000400
_WAIT_OBJECT_0 = 0x0
_INFINITE = 0xFFFFFFFF


class ElevationCancelled(RuntimeError):
    """The user dismissed the UAC prompt."""


class ElevationFailed(RuntimeError):
    """The elevated process could not be started, or reported failure."""


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_elevated(executable: str, params: str, timeout_s: float = WAIT_TIMEOUT_S) -> int:
    """Run one command elevated and wait for it. Returns its exit code.

    Raises ``ElevationCancelled`` if the user dismissed the prompt.
    """
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NO_UI
    info.hwnd = None
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = params
    info.lpDirectory = None
    info.nShow = SW_HIDE

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error() or ctypes.GetLastError()
        if err == ERROR_CANCELLED:
            raise ElevationCancelled("the administrator prompt was dismissed")
        raise ElevationFailed(f"ShellExecuteExW failed (error {err})")

    handle = info.hProcess
    if not handle:
        raise ElevationFailed("elevated process did not start")

    try:
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            result = ctypes.windll.kernel32.WaitForSingleObject(handle, remaining)
            if result == _WAIT_OBJECT_0:
                break
            raise ElevationFailed("elevated command timed out")

        code = wintypes.DWORD()
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ElevationFailed("could not read the elevated exit code")
        return int(code.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _netsh_elevated(args: list[str]) -> bool:
    """Run one netsh firewall command as admin. True on success."""
    params = " ".join(_quote(a) for a in ["advfirewall", "firewall", *args])
    return run_elevated("netsh.exe", params) == 0


def _quote(arg: str) -> str:
    # netsh takes name=value pairs; quote the value, not the whole token, or
    # netsh treats the quotes as part of the name.
    if "=" in arg:
        key, _, value = arg.partition("=")
        return f'{key}="{value}"' if " " in value else arg
    return f'"{arg}"' if " " in arg else arg


class ElevatingBackend:
    """Firewall backend that elevates each write, and reads without elevating.

    Listing rules works unelevated, so the common path — showing what's
    blocked — never prompts.
    """

    def __init__(self, direct_backend: Backend | None = None) -> None:
        from netwatch.core.firewall import DirectBackend

        self._reader: Backend = direct_backend or DirectBackend()

    def add_rule(self, name: str, exe_path: str) -> bool:
        if is_admin():
            return self._reader.add_rule(name, exe_path)
        return _netsh_elevated([
            "add", "rule",
            f"name={name}",
            "dir=out",
            "action=block",
            f"program={exe_path}",
            "enable=yes",
        ])

    def delete_rule(self, name: str) -> bool:
        if is_admin():
            return self._reader.delete_rule(name)
        return _netsh_elevated(["delete", "rule", f"name={name}"])

    def list_rules(self) -> list[str]:
        return self._reader.list_rules()  # reads need no admin


def _cli() -> int:
    """Manual check: python -m netwatch.core.elevation block <exe path>"""
    if len(sys.argv) < 2:
        print(f"admin: {is_admin()}")
        print("usage: -m netwatch.core.elevation block|unblock <exe path>")
        return 0

    op = sys.argv[1]
    backend = ElevatingBackend()
    target = sys.argv[2] if len(sys.argv) > 2 else sys.executable
    name = rule_name("netwatch_selftest")

    try:
        if op == "block":
            ok = backend.add_rule(name, target)
        elif op == "unblock":
            ok = backend.delete_rule(name)
        else:
            print(f"unknown op {op!r}")
            return 2
    except ElevationCancelled:
        print("cancelled at the UAC prompt — nothing changed")
        return 1

    print(f"{op}: {'ok' if ok else 'failed'}")
    print("rules now:", backend.list_rules())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
