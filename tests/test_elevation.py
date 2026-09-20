import pytest

from netwatch.core import elevation as el
from netwatch.core.elevation import ElevatingBackend, ElevationCancelled


class FakeReader:
    def __init__(self):
        self.calls = []
        self.rules = ["NetWatch_block_a.exe"]

    def add_rule(self, name, exe_path):
        self.calls.append(("add", name, exe_path))
        return True

    def delete_rule(self, name):
        self.calls.append(("delete", name))
        return True

    def list_rules(self):
        self.calls.append(("list",))
        return list(self.rules)


@pytest.fixture
def reader():
    return FakeReader()


@pytest.fixture
def unelevated(monkeypatch):
    monkeypatch.setattr(el, "is_admin", lambda: False)


def test_listing_rules_never_prompts(reader, unelevated, monkeypatch):
    """The common case — showing what's blocked — must not hit UAC."""
    monkeypatch.setattr(
        el, "run_elevated", lambda *a, **kw: pytest.fail("should not elevate")
    )
    assert ElevatingBackend(reader).list_rules() == ["NetWatch_block_a.exe"]


def test_block_elevates_when_not_admin(reader, unelevated, monkeypatch):
    seen = {}

    def fake_run(exe, params, **kw):
        seen["exe"] = exe
        seen["params"] = params
        return 0

    monkeypatch.setattr(el, "run_elevated", fake_run)

    assert ElevatingBackend(reader).add_rule("NetWatch_block_x.exe", r"C:\x.exe") is True
    assert seen["exe"] == "netsh.exe"
    assert "advfirewall firewall add rule" in seen["params"]
    assert "NetWatch_block_x.exe" in seen["params"]
    assert "action=block" in seen["params"]
    assert "dir=out" in seen["params"]
    assert reader.calls == [], "must not also run netsh unelevated"


def test_unblock_elevates_when_not_admin(reader, unelevated, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        el, "run_elevated", lambda exe, params, **kw: (seen.update(params=params), 0)[1]
    )
    assert ElevatingBackend(reader).delete_rule("NetWatch_block_x.exe") is True
    assert "delete rule" in seen["params"]


def test_already_elevated_skips_the_prompt(reader, monkeypatch):
    monkeypatch.setattr(el, "is_admin", lambda: True)
    monkeypatch.setattr(
        el, "run_elevated", lambda *a, **kw: pytest.fail("should not elevate")
    )
    ElevatingBackend(reader).add_rule("NetWatch_block_x.exe", r"C:\x.exe")
    assert reader.calls == [("add", "NetWatch_block_x.exe", r"C:\x.exe")]


def test_a_nonzero_exit_code_is_a_failure(reader, unelevated, monkeypatch):
    monkeypatch.setattr(el, "run_elevated", lambda *a, **kw: 1)
    assert ElevatingBackend(reader).add_rule("NetWatch_block_x.exe", r"C:\x.exe") is False


def test_cancelling_uac_propagates(reader, unelevated, monkeypatch):
    """The caller must be able to tell 'cancelled' from 'failed', so the UI
    can revert the toggle rather than showing an error."""

    def cancel(*a, **kw):
        raise ElevationCancelled("dismissed")

    monkeypatch.setattr(el, "run_elevated", cancel)
    with pytest.raises(ElevationCancelled):
        ElevatingBackend(reader).add_rule("NetWatch_block_x.exe", r"C:\x.exe")


def test_paths_with_spaces_are_quoted_for_netsh():
    quoted = el._quote(r"program=C:\Program Files\App\app.exe")
    assert quoted == r'program="C:\Program Files\App\app.exe"'


def test_values_without_spaces_are_left_alone():
    assert el._quote("dir=out") == "dir=out"
    assert el._quote("add") == "add"


def test_rule_names_with_spaces_survive_quoting(reader, unelevated, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        el, "run_elevated", lambda exe, params, **kw: (seen.update(p=params), 0)[1]
    )
    ElevatingBackend(reader).add_rule(
        "NetWatch_block_My App.exe", r"C:\Program Files\My App\app.exe"
    )
    assert 'name="NetWatch_block_My App.exe"' in seen["p"]
    assert 'program="C:\\Program Files\\My App\\app.exe"' in seen["p"]
