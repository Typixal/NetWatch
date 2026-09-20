import json

import pytest

from netwatch.core import firewall as fw
from netwatch.core.firewall import FirewallManager, rule_name
from netwatch.utils import paths


class FakeBackend:
    """Stands in for netsh. Records calls so tests can assert on them."""

    def __init__(self, rules=(), fail_add=False, fail_delete=False):
        self.rules = set(rules)
        self.fail_add = fail_add
        self.fail_delete = fail_delete
        self.calls = []

    def add_rule(self, name, exe_path):
        self.calls.append(("add", name, exe_path))
        if self.fail_add:
            return False
        self.rules.add(name)
        return True

    def delete_rule(self, name):
        self.calls.append(("delete", name))
        if self.fail_delete:
            return False
        self.rules.discard(name)
        return True

    def list_rules(self):
        return sorted(self.rules)


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def manager(backend):
    return FirewallManager(backend)


def test_block_writes_a_prefixed_rule(manager, backend):
    assert manager.block("spotify.exe", r"C:\Apps\spotify.exe") is True
    assert backend.calls == [("add", "NetWatch_block_spotify.exe", r"C:\Apps\spotify.exe")]
    assert manager.is_blocked("spotify.exe") is True


def test_block_without_an_exe_path_fails_cleanly(manager, backend, monkeypatch):
    monkeypatch.setattr(fw, "find_exe", lambda name: None)
    assert manager.block("ghost.exe") is False
    assert backend.calls == []
    assert manager.is_blocked("ghost.exe") is False


def test_a_failed_netsh_call_does_not_mark_it_blocked():
    """The toggle must never show a state the firewall doesn't actually have."""
    m = FirewallManager(FakeBackend(fail_add=True))
    assert m.block("spotify.exe", r"C:\x.exe") is False
    assert m.is_blocked("spotify.exe") is False


def test_unblock_removes_the_rule_and_the_state(manager, backend):
    manager.block("spotify.exe", r"C:\x.exe")
    assert manager.unblock("spotify.exe") is True
    assert backend.rules == set()
    assert manager.is_blocked("spotify.exe") is False


def test_a_failed_delete_keeps_it_marked_blocked():
    m = FirewallManager(FakeBackend(fail_delete=True))
    m.block("spotify.exe", r"C:\x.exe")
    assert m.unblock("spotify.exe") is False
    assert m.is_blocked("spotify.exe") is True


def test_blocklist_persists_across_instances(backend):
    m = FirewallManager(backend)
    m.block("spotify.exe", r"C:\Apps\spotify.exe")

    again = FirewallManager(backend)
    assert again.is_blocked("spotify.exe") is True
    assert json.loads(paths.blocklist_path().read_text(encoding="utf-8")) == {
        "spotify.exe": r"C:\Apps\spotify.exe"
    }


def test_sync_drops_state_for_rules_that_vanished(backend):
    """The app crashed mid-block, or a user deleted the rule by hand."""
    m = FirewallManager(backend)
    m.block("spotify.exe", r"C:\x.exe")
    backend.rules.clear()

    assert m.sync_with_firewall() == ["spotify.exe"]
    assert m.is_blocked("spotify.exe") is False


def test_sync_keeps_state_that_still_has_a_rule(manager):
    manager.block("spotify.exe", r"C:\x.exe")
    assert manager.sync_with_firewall() == []
    assert manager.is_blocked("spotify.exe") is True


def test_cleanup_removes_only_netwatch_rules():
    backend = FakeBackend(rules={"NetWatch_block_a.exe", "NetWatch_block_b.exe"})
    m = FirewallManager(backend)
    assert m.cleanup_all_rules() == 2
    assert backend.rules == set()
    assert m.blocked_processes() == []


def test_corrupt_blocklist_is_ignored(backend):
    paths.blocklist_path().write_text("{not json", encoding="utf-8")
    assert FirewallManager(backend).blocked_processes() == []


def test_rule_name_uses_the_prefix():
    assert rule_name("chrome.exe") == "NetWatch_block_chrome.exe"


def test_rules_are_parsed_out_of_netsh_output_regardless_of_locale(monkeypatch):
    """Field labels are localized; the rule names themselves are not."""
    german = (
        "Regelname:                            NetWatch_block_spotify.exe\r\n"
        "Aktiviert:                            Ja\r\n"
        "Regelname:                            Some Other Rule\r\n"
        "Regelname:                            NetWatch_block_chrome.exe\r\n"
    )

    class R:
        returncode = 0
        stdout = german

    monkeypatch.setattr(fw, "_netsh", lambda *a: R())
    assert fw.DirectBackend().list_rules() == [
        "NetWatch_block_chrome.exe",
        "NetWatch_block_spotify.exe",
    ]


def test_deleting_an_absent_rule_counts_as_success(monkeypatch):
    class R:
        returncode = 1
        stdout = "No rules match the specified criteria."

    monkeypatch.setattr(fw, "_netsh", lambda *a: R())
    assert fw.DirectBackend().delete_rule("NetWatch_block_gone.exe") is True
