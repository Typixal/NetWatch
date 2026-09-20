"""Global test isolation.

No test may touch the real ``%LOCALAPPDATA%\\NetWatch``, the real Run key,
the Startup folder, or Windows Firewall. These fixtures are autouse and
apply to every test in the suite, so an individually-written test can't opt
out by forgetting to patch something.
"""

from __future__ import annotations

import subprocess
import winreg

import pytest

# Registry subtree the suite is allowed to write. Cleaned up after the run.
TEST_REG_ROOT = r"Software\NetWatchTests"


@pytest.fixture(autouse=True)
def isolate_app_data(tmp_path, monkeypatch):
    """Every path helper points into a per-test temp dir."""
    monkeypatch.setenv("NETWATCH_DATA_DIR", str(tmp_path / "NetWatch"))


@pytest.fixture(autouse=True)
def forbid_real_registry_writes(monkeypatch):
    """Fail loudly if a test opens a registry key outside the test subtree.

    Cheap insurance: a typo'd key path would otherwise write a real logon
    entry, and a failed test run would leave it behind.
    """
    real_create = winreg.CreateKeyEx
    real_open = winreg.OpenKey

    def guard(name: str, sub_key) -> None:
        if sub_key and not str(sub_key).startswith(TEST_REG_ROOT):
            pytest.fail(
                f"test tried to {name} registry key outside {TEST_REG_ROOT!r}: "
                f"{sub_key!r}"
            )

    def create(key, sub_key, *a, **kw):
        guard("create", sub_key)
        return real_create(key, sub_key, *a, **kw)

    def open_(key, sub_key, *a, **kw):
        guard("open", sub_key)
        return real_open(key, sub_key, *a, **kw)

    monkeypatch.setattr(winreg, "CreateKeyEx", create)
    monkeypatch.setattr(winreg, "OpenKey", open_)


@pytest.fixture(autouse=True)
def forbid_firewall_changes(monkeypatch):
    """Block any netsh invocation that would mutate the real firewall.

    Read-only netsh and other commands (reg query, etc.) still run, so tests
    can cross-check themselves against a second implementation.
    """
    real_run = subprocess.run

    def guarded_run(args, *a, **kw):
        argv = args if isinstance(args, (list, tuple)) else [str(args)]
        lowered = [str(x).lower() for x in argv]
        if lowered and "netsh" in lowered[0]:
            if {"add", "delete", "set"} & set(lowered):
                pytest.fail(f"test tried to modify the real firewall: {argv!r}")
        return real_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", guarded_run)


@pytest.fixture(scope="session", autouse=True)
def purge_test_registry_subtree():
    """Delete the whole test subtree once the run ends, pass or fail."""
    yield
    _delete_tree(winreg.HKEY_CURRENT_USER, TEST_REG_ROOT)


def _delete_tree(root, path: str) -> None:
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS)
    except OSError:
        return
    with key:
        while True:
            try:
                child = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_tree(root, f"{path}\\{child}")
    try:
        winreg.DeleteKey(root, path)
    except OSError:
        pass
