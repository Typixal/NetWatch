"""Exercises the real registry, but under a scratch subkey.

The machine's actual Run key is never written to — if any of these tests
touched ``Software\\Microsoft\\Windows\\CurrentVersion\\Run`` a failed run
would leave a stray logon entry behind.
"""

import subprocess
import sys
import winreg

import pytest

from netwatch.utils import startup

SCRATCH_KEY = r"Software\NetWatchTests\Run"


@pytest.fixture(autouse=True)
def scratch_registry(monkeypatch):
    monkeypatch.setattr(startup, "_key_path", SCRATCH_KEY)
    monkeypatch.setattr(startup, "_value_name", "NetWatchTest")
    winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, SCRATCH_KEY, 0, winreg.KEY_WRITE).Close()
    yield
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCRATCH_KEY)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\NetWatchTests")
    except OSError:
        pass


def test_disabled_on_a_clean_key():
    assert startup.is_startup_enabled() is False
    assert startup.registered_command() is None


def test_enable_then_disable_round_trips():
    assert startup.toggle_startup() is True
    assert startup.is_startup_enabled() is True

    assert startup.toggle_startup() is False
    assert startup.is_startup_enabled() is False
    assert startup.registered_command() is None


def test_enabled_value_matches_startup_command():
    startup.enable_startup()
    assert startup.registered_command() == startup.startup_command()


def test_reg_exe_agrees_that_the_value_exists():
    """Read it back through a second implementation, not just our own API."""
    startup.enable_startup()
    r = subprocess.run(
        ["reg", "query", rf"HKCU\{SCRATCH_KEY}", "/v", "NetWatchTest"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "NetWatchTest" in r.stdout


def test_disable_when_already_disabled_is_a_no_op():
    startup.disable_startup()
    startup.disable_startup()  # must not raise
    assert startup.is_startup_enabled() is False


def test_enable_is_idempotent():
    startup.enable_startup()
    startup.enable_startup()
    assert startup.is_startup_enabled() is True
    assert startup.toggle_startup() is False


def test_missing_key_reads_as_disabled(monkeypatch):
    monkeypatch.setattr(startup, "_key_path", r"Software\NetWatchTests\NoSuchKey")
    assert startup.is_startup_enabled() is False
    assert startup.registered_command() is None


def test_command_quotes_the_interpreter_path():
    cmd = startup.startup_command()
    assert cmd.startswith('"')
    assert cmd.split('"')[1].lower().endswith(".exe")


def test_source_mode_command_points_at_this_package():
    """Dev-mode entry must reach netwatch, not a stale script path."""
    assert not getattr(sys, "frozen", False)
    cmd = startup.startup_command()
    assert cmd.endswith("-m netwatch")
    # The interpreter must be the project venv's, not system Python.
    assert ".venv" in cmd.lower()
