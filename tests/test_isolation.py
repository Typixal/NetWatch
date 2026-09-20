"""Tests for the safety net in conftest.py.

If these ever go quiet, the rest of the suite could start writing to the
real registry or firewall without anyone noticing.
"""

import subprocess
import winreg

import pytest
from _pytest.outcomes import Failed

from netwatch.utils import paths


def test_app_data_is_redirected_away_from_localappdata(tmp_path):
    assert paths.app_dir() == tmp_path / "NetWatch"
    assert "AppData\\Local\\NetWatch" not in str(paths.app_dir())


def test_writing_the_real_run_key_is_blocked():
    with pytest.raises(Failed, match="outside"):
        winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )


def test_reading_the_real_run_key_is_blocked():
    with pytest.raises(Failed, match="outside"):
        winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        )


def test_the_test_subtree_is_allowed():
    winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, r"Software\NetWatchTests\Probe", 0, winreg.KEY_WRITE
    ).Close()


def test_adding_a_firewall_rule_is_blocked():
    with pytest.raises(Failed, match="firewall"):
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule", "name=NetWatch_probe"],
            capture_output=True,
        )


def test_deleting_a_firewall_rule_is_blocked():
    with pytest.raises(Failed, match="firewall"):
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", "name=NetWatch_probe"],
            capture_output=True,
        )


def test_read_only_commands_still_run():
    r = subprocess.run(["cmd", "/c", "echo", "ok"], capture_output=True, text=True)
    assert r.returncode == 0
