import winreg
from pathlib import Path

import pytest

from netwatch import uninstall
from netwatch.utils import paths, startup

SCRATCH_KEY = r"Software\NetWatchTests\UninstallRun"


@pytest.fixture(autouse=True)
def scratch_registry(monkeypatch):
    monkeypatch.setattr(startup, "_key_path", SCRATCH_KEY)
    monkeypatch.setattr(startup, "_value_name", "NetWatchTest")
    winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, SCRATCH_KEY, 0, winreg.KEY_WRITE).Close()
    yield
    # Clear the value between tests, or "clean machine" cases inherit the
    # startup entry a previous test wrote.
    startup.disable_startup()


@pytest.fixture(autouse=True)
def no_real_firewall(monkeypatch):
    """Default: no rules present. Individual tests override."""
    monkeypatch.setattr(uninstall, "_list_rules", lambda: [])


@pytest.fixture(autouse=True)
def empty_startup_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(uninstall, "startup_folder", lambda: tmp_path / "Startup")


# ── the bug that deleted the working directory ─────────────────────────────
#
# resolve_data_dir() used `Path(os.environ.get(...) or "")` and then tested
# the Path for truthiness. Path("") is Path("."), which is truthy, so an
# unset override resolved to the current directory — and uninstall rmtree'd
# the project. These tests pin every part of that down.


def test_unset_override_never_resolves_to_the_working_directory(monkeypatch):
    monkeypatch.delenv("NETWATCH_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\somebody\AppData\Local")
    resolved = uninstall.resolve_data_dir()
    assert resolved != Path.cwd()
    assert resolved.name == "NetWatch"


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_blank_override_is_treated_as_absent(monkeypatch, value):
    monkeypatch.setenv("NETWATCH_DATA_DIR", value)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\somebody\AppData\Local")
    assert uninstall.resolve_data_dir() != Path.cwd()


def test_the_working_directory_is_never_safe_to_delete():
    safe, why = uninstall.is_safe_to_delete(Path.cwd())
    assert safe is False
    assert why


def test_a_directory_holding_a_project_is_refused(tmp_path):
    target = tmp_path / "NetWatch"
    (target / "src").mkdir(parents=True)
    (target / "pyproject.toml").write_text("", encoding="utf-8")

    safe, why = uninstall.is_safe_to_delete(target)
    assert safe is False
    assert "src" in why or "pyproject.toml" in why


def test_a_directory_with_a_git_repo_is_refused(tmp_path):
    target = tmp_path / "NetWatch"
    (target / ".git").mkdir(parents=True)
    safe, why = uninstall.is_safe_to_delete(target)
    assert safe is False
    assert ".git" in why


def test_a_wrongly_named_directory_is_refused(tmp_path):
    target = tmp_path / "SomethingElse"
    target.mkdir()
    safe, why = uninstall.is_safe_to_delete(target)
    assert safe is False
    assert "named" in why


def test_a_filesystem_root_is_refused():
    safe, why = uninstall.is_safe_to_delete(Path("C:\\"))
    assert safe is False


def test_a_relative_path_is_refused():
    safe, why = uninstall.is_safe_to_delete(Path("NetWatch"))
    assert safe is False
    assert "absolute" in why


def test_a_genuine_data_dir_is_accepted(tmp_path):
    target = tmp_path / "NetWatch"
    (target / "logs").mkdir(parents=True)
    (target / "cache").mkdir()
    (target / "config.json").write_text("{}", encoding="utf-8")

    safe, why = uninstall.is_safe_to_delete(target)
    assert safe is True, why


def test_an_empty_data_dir_is_accepted(tmp_path):
    target = tmp_path / "NetWatch"
    target.mkdir()
    assert uninstall.is_safe_to_delete(target)[0] is True


def test_uninstall_refuses_and_reports_an_unsafe_target(tmp_path, monkeypatch):
    target = tmp_path / "NetWatch"
    (target / "src").mkdir(parents=True)
    keep = target / "src" / "keep.py"
    keep.write_text("precious", encoding="utf-8")
    monkeypatch.setenv("NETWATCH_DATA_DIR", str(target))

    r = uninstall.uninstall()

    assert keep.exists(), "refused target must survive untouched"
    assert any("refused" in s for s in r.skipped)


# ── ordinary behaviour ─────────────────────────────────────────────────────


def test_clean_machine_reports_nothing(monkeypatch):
    monkeypatch.setattr(uninstall, "app_dir_if_exists", lambda: None)
    assert uninstall.survey().found == []


def test_survey_does_not_create_the_app_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NETWATCH_DATA_DIR", str(tmp_path / "NetWatch"))
    uninstall.survey()
    assert not (tmp_path / "NetWatch").exists()


def test_survey_finds_each_kind_of_trace(monkeypatch, tmp_path):
    monkeypatch.setattr(uninstall, "_list_rules", lambda: ["NetWatch_block_spotify.exe"])
    startup.enable_startup()
    paths.app_dir()

    folder = tmp_path / "Startup"
    folder.mkdir()
    (folder / "NetWatch.lnk").write_text("", encoding="utf-8")

    found = "\n".join(uninstall.survey().found)
    assert "firewall rule" in found
    assert "registry" in found
    assert "startup link" in found
    assert "app data" in found


def test_dry_run_changes_nothing():
    startup.enable_startup()
    paths.app_dir()

    r = uninstall.uninstall(dry_run=True)
    assert r.removed == []
    assert startup.is_startup_enabled() is True
    assert paths.app_dir().exists()
    assert r.anything_found is True


def test_uninstall_removes_registry_and_app_data():
    startup.enable_startup()
    data = paths.app_dir()
    (data / "config.json").write_text("{}", encoding="utf-8")

    r = uninstall.uninstall()

    assert startup.is_startup_enabled() is False
    assert not data.exists()
    assert any("run-on-startup" in x for x in r.removed)
    assert any("app data" in x for x in r.removed)
    assert r.failed == []


def test_uninstall_removes_startup_shortcuts(tmp_path):
    folder = tmp_path / "Startup"
    folder.mkdir()
    link = folder / "NetWatch.lnk"
    link.write_text("", encoding="utf-8")
    unrelated = folder / "OtherApp.lnk"
    unrelated.write_text("", encoding="utf-8")

    uninstall.uninstall()

    assert not link.exists()
    assert unrelated.exists(), "must not touch shortcuts it didn't create"


def test_firewall_rules_are_skipped_not_failed_without_admin(monkeypatch):
    monkeypatch.setattr(uninstall, "_list_rules", lambda: ["NetWatch_block_a.exe"])
    monkeypatch.setattr(uninstall, "is_admin", lambda: False)

    r = uninstall.uninstall()
    assert any("needs admin" in x for x in r.skipped)
    assert r.failed == []


def test_firewall_rules_are_deleted_when_elevated(monkeypatch):
    deleted = []

    class Backend:
        def delete_rule(self, name):
            deleted.append(name)
            return True

    monkeypatch.setattr(uninstall, "_list_rules", lambda: ["NetWatch_block_a.exe"])
    monkeypatch.setattr(uninstall, "is_admin", lambda: True)
    monkeypatch.setattr(uninstall, "DirectBackend", Backend)

    r = uninstall.uninstall()
    assert deleted == ["NetWatch_block_a.exe"]
    assert any("firewall rule" in x for x in r.removed)


def test_uninstall_is_idempotent():
    startup.enable_startup()
    paths.app_dir()
    uninstall.uninstall()

    second = uninstall.uninstall()
    assert second.found == []
    assert second.failed == []


def test_main_dry_run_exits_zero(capsys):
    startup.enable_startup()
    paths.app_dir()
    assert uninstall.main(["--dry-run"]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert startup.is_startup_enabled() is True


def test_main_declining_the_prompt_changes_nothing(monkeypatch, capsys):
    startup.enable_startup()
    paths.app_dir()
    monkeypatch.setattr("builtins.input", lambda _: "n")

    assert uninstall.main([]) == 1
    assert "Cancelled" in capsys.readouterr().out
    assert startup.is_startup_enabled() is True


def test_main_on_a_clean_machine(monkeypatch, capsys):
    monkeypatch.setattr(uninstall, "app_dir_if_exists", lambda: None)
    assert uninstall.main([]) == 0
    assert "Nothing to remove" in capsys.readouterr().out
