import json

import pytest

from netwatch.core import dns_resolver as dns
from netwatch.utils import paths


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NETWATCH_DATA_DIR", str(tmp_path / "NetWatch"))
    return tmp_path / "NetWatch"


@pytest.fixture
def resolver(monkeypatch):
    """A resolver whose lookups are driven by a fake hosts table, run inline."""
    table: dict[str, str] = {}

    def fake_gethostbyaddr(ip):
        if ip in table:
            return (table[ip], [], [ip])
        raise OSError("no reverse record")

    monkeypatch.setattr(dns.socket, "gethostbyaddr", fake_gethostbyaddr)

    r = dns.DNSResolver()
    # Run submitted work immediately so tests stay deterministic.
    monkeypatch.setattr(r._pool, "submit", lambda fn, *a: fn(*a))
    r.hosts = table
    yield r
    r.shutdown()


def test_unknown_ip_resolves_to_none_before_lookup(resolver):
    assert resolver.resolve_cached("1.2.3.4") is None
    assert resolver.is_known("1.2.3.4") is False


def test_successful_lookup_is_cached(resolver):
    resolver.hosts["142.250.80.46"] = "lga25s71.1e100.net"
    resolver.enqueue("142.250.80.46")
    assert resolver.resolve_cached("142.250.80.46") == "lga25s71.1e100.net"


def test_failed_lookup_stays_unresolved(resolver):
    """The bug this guards: caching the IP string would make every IP 'resolved'."""
    resolver.enqueue("45.33.32.156")
    assert resolver.resolve_cached("45.33.32.156") is None
    assert resolver.is_known("45.33.32.156") is True


def test_failed_lookup_is_not_retried(resolver):
    calls = []
    original = dns.socket.gethostbyaddr

    def counting(ip):
        calls.append(ip)
        return original(ip)

    dns.socket.gethostbyaddr = counting
    try:
        resolver.enqueue("45.33.32.156")
        resolver.enqueue("45.33.32.156")
        resolver.enqueue("45.33.32.156")
    finally:
        dns.socket.gethostbyaddr = original
    assert calls == ["45.33.32.156"]


def test_signal_carries_empty_string_for_failures(resolver):
    seen = []
    resolver.dns_resolved.connect(lambda ip, dom: seen.append((ip, dom)))
    resolver.hosts["8.8.8.8"] = "dns.google"
    resolver.enqueue("8.8.8.8")
    resolver.enqueue("45.33.32.156")
    assert seen == [("8.8.8.8", "dns.google"), ("45.33.32.156", "")]


def test_cache_is_capped_and_evicts_least_recently_used(resolver, monkeypatch):
    monkeypatch.setattr(dns, "MAX_ENTRIES", 3)
    for i in range(3):
        ip = f"10.0.0.{i}"
        resolver.hosts[ip] = f"host{i}"
        resolver.enqueue(ip)

    resolver.resolve_cached("10.0.0.0")  # touch it, so 10.0.0.1 is now oldest

    resolver.hosts["10.0.0.9"] = "host9"
    resolver.enqueue("10.0.0.9")

    assert resolver.is_known("10.0.0.1") is False
    assert resolver.resolve_cached("10.0.0.0") == "host0"
    assert resolver.resolve_cached("10.0.0.9") == "host9"


def test_disk_writes_are_debounced(resolver):
    resolver.hosts.update({f"10.1.0.{i}": f"h{i}" for i in range(5)})
    for i in range(5):
        resolver.enqueue(f"10.1.0.{i}")

    # First resolution writes; the rest fall inside the debounce window.
    on_disk = json.loads(paths.dns_cache_path().read_text(encoding="utf-8"))
    assert len(on_disk) == 1

    resolver.flush()
    on_disk = json.loads(paths.dns_cache_path().read_text(encoding="utf-8"))
    assert len(on_disk) == 5


def test_failures_persist_as_null_and_reload_as_failures(resolver):
    resolver.hosts["8.8.8.8"] = "dns.google"
    resolver.enqueue("8.8.8.8")
    resolver.enqueue("45.33.32.156")
    resolver.flush()

    raw = json.loads(paths.dns_cache_path().read_text(encoding="utf-8"))
    assert raw == {"8.8.8.8": "dns.google", "45.33.32.156": None}

    reloaded = dns.DNSResolver()
    try:
        assert reloaded.resolve_cached("8.8.8.8") == "dns.google"
        assert reloaded.resolve_cached("45.33.32.156") is None
        assert reloaded.is_known("45.33.32.156") is True
    finally:
        reloaded.shutdown()


def test_corrupt_cache_file_is_ignored(data_dir):
    paths.cache_dir()
    paths.dns_cache_path().write_text("{not json", encoding="utf-8")
    r = dns.DNSResolver()
    try:
        assert r.resolve_cached("1.2.3.4") is None
    finally:
        r.shutdown()


def test_enqueue_after_shutdown_is_ignored(resolver):
    resolver.hosts["8.8.4.4"] = "dns.google"
    resolver.shutdown()
    resolver.enqueue("8.8.4.4")
    assert resolver.is_known("8.8.4.4") is False
