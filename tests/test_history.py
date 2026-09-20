from netwatch.core import history as hist
from netwatch.core.history import HistoryTracker
from netwatch.core.store import Connection, ProcessGroup


def group(name: str, count: int) -> ProcessGroup:
    conns = [
        Connection(
            pid=1,
            process_name=name,
            remote_ip=f"93.184.216.{i}",
            remote_port=443,
            status="ESTABLISHED",
        )
        for i in range(count)
    ]
    return ProcessGroup(name=name, pids={1}, connections=conns)


def test_new_process_starts_flat_not_spiking():
    t = HistoryTracker(samples=5)
    t.record([group("chrome.exe", 3)])
    assert t.series("chrome.exe") == [0, 0, 0, 0, 3]


def test_series_is_always_the_window_length():
    t = HistoryTracker(samples=5)
    for _ in range(20):
        t.record([group("chrome.exe", 2)])
    assert t.series("chrome.exe") == [2] * 5


def test_window_slides_and_keeps_the_newest_samples():
    t = HistoryTracker(samples=3)
    for n in (1, 2, 3, 4):
        t.record([group("a.exe", n)])
    assert t.series("a.exe") == [2, 3, 4]


def test_a_process_that_stops_connecting_records_zeroes():
    t = HistoryTracker(samples=4)
    t.record([group("a.exe", 5)])
    t.record([])
    t.record([])
    assert t.series("a.exe") == [0, 5, 0, 0]


def test_unknown_process_reads_as_all_zero():
    t = HistoryTracker(samples=4)
    assert t.series("nope.exe") == [0, 0, 0, 0]
    assert t.stats("nope.exe") == (0, 0, 0)


def test_stats_are_peak_avg_now():
    t = HistoryTracker(samples=4)
    for n in (2, 8, 4, 2):
        t.record([group("a.exe", n)])
    assert t.stats("a.exe") == (8, 4, 2)  # peak 8, mean 4.0, latest 2


def test_spark_returns_the_narrower_sidebar_window():
    t = HistoryTracker()
    t.record([group("a.exe", 1)])
    assert len(t.spark("a.exe")) == hist.SPARK_SAMPLES


def test_idle_process_is_dropped_once_stale(monkeypatch):
    t = HistoryTracker(samples=2)
    t.record([group("gone.exe", 3)])

    monkeypatch.setattr(hist, "STALE_AFTER_S", -1.0)  # everything is stale now
    t.record([])  # series still holds the 3
    assert "gone.exe" in t._series
    t.record([])  # now fully zeroed, safe to drop
    assert "gone.exe" not in t._series


def test_active_process_is_never_dropped(monkeypatch):
    t = HistoryTracker(samples=2)
    monkeypatch.setattr(hist, "STALE_AFTER_S", -1.0)
    for _ in range(5):
        t.record([group("busy.exe", 4)])
    assert t.series("busy.exe") == [4, 4]


def test_forget_removes_a_process():
    t = HistoryTracker(samples=2)
    t.record([group("a.exe", 1)])
    t.forget("a.exe")
    assert t.series("a.exe") == [0, 0]
