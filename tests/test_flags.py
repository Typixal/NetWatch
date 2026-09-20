import pytest

from netwatch.core.flags import FlagEngine
from netwatch.core.store import Connection


def conn(**kw) -> Connection:
    base = dict(
        pid=1234,
        process_name="chrome.exe",
        remote_ip="93.184.216.34",
        remote_port=443,
        status="ESTABLISHED",
        domain="example.com",
        dns_pending=False,
    )
    base.update(kw)
    return Connection(**base)


@pytest.fixture
def engine():
    return FlagEngine()


def test_ordinary_resolved_connection_is_not_flagged(engine):
    assert engine.evaluate(conn()) is False


def test_unresolved_public_ip_is_flagged(engine):
    c = conn(domain=None, dns_pending=False)
    assert engine.evaluate(c) is True
    assert "unresolved" in c.flag_reason


def test_pending_lookup_is_not_flagged_yet(engine):
    """The first polls have every domain still pending — flagging them all
    would make the whole list red on startup."""
    assert engine.evaluate(conn(domain=None, dns_pending=True)) is False


def test_unresolved_ip_in_a_known_cloud_range_is_not_flagged(engine):
    for ip in ("8.8.8.8", "142.250.80.46"):
        assert engine.evaluate(conn(remote_ip=ip, domain=None, dns_pending=False)) is False


@pytest.mark.parametrize("port", [6667, 1337, 31337, 4444, 9001, 9030])
def test_suspicious_ports_are_flagged(engine, port):
    c = conn(remote_port=port)
    assert engine.evaluate(c) is True
    assert str(port) in c.flag_reason


def test_system_process_talking_externally_is_flagged(engine):
    c = conn(process_name="csrss.exe")
    assert engine.evaluate(c) is True
    assert "csrss.exe" in c.flag_reason


@pytest.mark.parametrize("ip", ["192.168.1.10", "10.0.0.5", "127.0.0.1", "169.254.1.1"])
def test_lan_and_loopback_are_never_flagged(engine, ip):
    c = conn(remote_ip=ip, remote_port=4444, domain=None, dns_pending=False)
    assert engine.evaluate(c) is False


def test_system_process_on_the_lan_is_not_flagged(engine):
    assert engine.evaluate(conn(process_name="System", remote_ip="192.168.1.5")) is False


def test_malformed_ip_is_ignored(engine):
    assert engine.evaluate(conn(remote_ip="not-an-ip")) is False


def test_evaluate_clears_a_previous_flag(engine):
    c = conn(remote_port=6667)
    assert engine.evaluate(c) is True
    c.remote_port = 443
    assert engine.evaluate(c) is False
    assert c.flag_reason == ""
