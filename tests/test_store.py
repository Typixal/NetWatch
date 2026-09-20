import json
from datetime import date, datetime, timedelta

from netwatch.core.store import Connection, ConnectionStore, ProcessGroup
from netwatch.utils import paths


def conn(port=443, **kw) -> Connection:
    base = dict(
        pid=100,
        process_name="chrome.exe",
        remote_ip="93.184.216.34",
        remote_port=port,
        status="ESTABLISHED",
    )
    base.update(kw)
    return Connection(**base)


def group(*conns) -> ProcessGroup:
    return ProcessGroup(name="chrome.exe", pids={100}, connections=list(conns))


class FakeFirewall:
    def __init__(self, blocked=()):
        self.blocked = set(blocked)

    def is_blocked(self, name):
        return name in self.blocked


def test_first_seen_survives_a_refresh():
    store = ConnectionStore()
    earlier = datetime.now() - timedelta(minutes=5)
    first = conn()
    first.first_seen = earlier
    store.update([group(first)])

    again = conn()  # fresh object, same identity, new default timestamp
    store.update([group(again)])
    assert again.first_seen == earlier


def test_last_seen_advances():
    store = ConnectionStore()
    c = conn()
    c.last_seen = datetime.now() - timedelta(minutes=5)
    store.update([group(c)])
    assert datetime.now() - c.last_seen < timedelta(seconds=5)


def test_a_connection_that_went_away_does_not_resurrect_its_age():
    store = ConnectionStore()
    old = conn()
    old.first_seen = datetime.now() - timedelta(hours=1)
    store.update([group(old)])
    store.update([])  # connection closed

    reopened = conn()
    store.update([group(reopened)])
    assert datetime.now() - reopened.first_seen < timedelta(seconds=5)


def test_blocked_state_comes_from_the_firewall():
    store = ConnectionStore(FakeFirewall({"chrome.exe"}))
    g = group(conn())
    store.update([g])
    assert g.blocked is True


def test_only_flagged_connections_are_logged():
    store = ConnectionStore()
    plain = conn(port=443)
    bad = conn(port=6667, flagged=True, flag_reason="suspicious port 6667")
    store.update([group(plain, bad)])
    store.close()

    lines = paths.today_log_path().read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["port"] == 6667
    assert entry["reason"] == "suspicious port 6667"
    assert entry["process"] == "chrome.exe"


def test_no_log_file_is_created_when_nothing_is_flagged():
    store = ConnectionStore()
    store.update([group(conn())])
    store.close()
    assert not paths.today_log_path().exists()


def test_log_appends_across_polls_on_one_handle():
    store = ConnectionStore()
    for _ in range(3):
        store.update([group(conn(port=6667, flagged=True, flag_reason="r"))])
    store.close()
    lines = paths.today_log_path().read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_log_rolls_over_to_a_new_file_at_midnight():
    store = ConnectionStore()
    flagged = conn(port=6667, flagged=True, flag_reason="r")
    store._log([group(flagged)], datetime(2026, 1, 9, 23, 59, 59))
    store._log([group(flagged)], datetime(2026, 1, 10, 0, 0, 1))
    store.close()

    assert paths.log_path_for(date(2026, 1, 9)).exists()
    assert paths.log_path_for(date(2026, 1, 10)).exists()


def test_close_is_safe_to_call_twice():
    store = ConnectionStore()
    store.update([group(conn(port=6667, flagged=True, flag_reason="r"))])
    store.close()
    store.close()


def test_group_flagged_and_pid_helpers():
    g = ProcessGroup(name="a.exe", pids={40, 12}, connections=[conn()])
    assert g.flagged is False
    assert g.pid == 12
    g.connections.append(conn(port=6667, flagged=True))
    assert g.flagged is True
    assert ProcessGroup(name="b.exe").pid is None
