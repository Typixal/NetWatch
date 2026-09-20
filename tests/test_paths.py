from datetime import date

import pytest

from netwatch.utils import paths


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Point every path helper at a temp dir so tests never touch real app data."""
    monkeypatch.setenv("NETWATCH_DATA_DIR", str(tmp_path / "NetWatch"))
    return tmp_path / "NetWatch"


def test_app_dir_is_created_on_demand(data_dir):
    assert not data_dir.exists()
    assert paths.app_dir() == data_dir
    assert data_dir.is_dir()


def test_app_dir_is_writable(data_dir):
    probe = paths.app_dir() / "probe.txt"
    probe.write_text("ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok"


def test_subdirs_are_created(data_dir):
    assert paths.log_dir().is_dir()
    assert paths.cache_dir().is_dir()


def test_every_path_stays_under_app_dir(data_dir):
    candidates = [
        paths.config_path(),
        paths.blocklist_path(),
        paths.today_log_path(),
        paths.dns_cache_path(),
    ]
    for p in candidates:
        assert data_dir in p.parents, f"{p} escaped the app dir"


def test_log_path_is_named_for_its_day(data_dir):
    assert paths.log_path_for(date(2026, 1, 9)).name == "2026-01-09.jsonl"


def test_falls_back_to_localappdata_when_no_override(monkeypatch, tmp_path):
    monkeypatch.delenv("NETWATCH_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.app_dir() == tmp_path / "NetWatch"
