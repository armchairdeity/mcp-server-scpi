"""Transport cascade — monkeypatched pyvisa seams, no live VISA calls."""

from __future__ import annotations

import pytest

from scpi_mcp.instruments.mock import MockInstrument
from scpi_mcp.transport import connect, discover
from scpi_mcp.transport.discover import DiscoverySource

_RIGOL_IDN = "RIGOL TECHNOLOGIES,DS1104Z,SN,fw"


@pytest.fixture(autouse=True)
def _clear_cache():
    connect.clear_cache()
    yield
    connect.clear_cache()


def test_discover_usb_matches_rigol(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRM:
        def list_resources(self):
            return ("USB0::0x1AB1::0x04CE::DS1ZA::INSTR", "ASRL1::INSTR")

    monkeypatch.setattr(discover, "_resource_manager", lambda: FakeRM())
    monkeypatch.setattr(
        discover,
        "_probe_idn",
        lambda res, timeout_ms=2000: _RIGOL_IDN if "USB" in res else None,
    )
    result = discover.discover_usb()
    assert result is not None
    assert result.source is DiscoverySource.USB
    assert result.reliable is True


def test_discover_usb_none_when_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRM:
        def list_resources(self):
            return ("USB0::0x0000::0x0000::XYZ::INSTR",)

    monkeypatch.setattr(discover, "_resource_manager", lambda: FakeRM())
    monkeypatch.setattr(
        discover, "_probe_idn", lambda res, timeout_ms=2000: "ACME,SOMETHING"
    )
    assert discover.discover_usb() is None


def test_lan_discovery_none_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Probe fails (nothing answers) → None. No live network I/O in the test.
    monkeypatch.setattr(discover, "_probe_idn", lambda res, timeout_ms=2000: None)
    assert discover.discover_lan() is None


def test_lan_discovery_finds_known_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        discover, "_probe_idn", lambda res, timeout_ms=2000: _RIGOL_IDN
    )
    result = discover.discover_lan()
    assert result is not None
    assert result.resource == discover.KNOWN_LAN_RESOURCE
    assert result.source is DiscoverySource.LAN
    assert result.reliable is False  # direct-probe LAN is best-effort


def test_manual_builds_tcpip_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        discover, "_probe_idn", lambda res, timeout_ms=2000: _RIGOL_IDN
    )
    result = discover.discover_manual("192.168.2.2")
    assert result is not None
    assert result.resource == "TCPIP0::192.168.2.2::5555::SOCKET"
    assert result.source is DiscoverySource.MANUAL


def test_cascade_prefers_usb(monkeypatch: pytest.MonkeyPatch) -> None:
    usb = discover.DiscoveryResult(
        resource="USB::DS1ZA::INSTR",
        source=DiscoverySource.USB,
        idn="RIGOL...",
        reliable=True,
    )
    monkeypatch.setattr(discover, "discover_usb", lambda: usb)
    assert discover.cascade().source is DiscoverySource.USB


def test_cascade_falls_through_to_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discover, "discover_usb", lambda: None)
    monkeypatch.setattr(discover, "discover_lan", lambda *a, **k: None)
    monkeypatch.setattr(
        discover,
        "discover_manual",
        lambda host: discover.DiscoveryResult(
            resource=f"TCPIP::{host}::INSTR",
            source=DiscoverySource.MANUAL,
            reliable=True,
        ),
    )
    result = discover.cascade(host="192.168.2.2")
    assert result is not None
    assert result.resource == "TCPIP::192.168.2.2::INSTR"


def test_cascade_returns_none_with_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discover, "discover_usb", lambda: None)
    monkeypatch.setattr(discover, "discover_lan", lambda *a, **k: None)
    assert discover.cascade() is None


def test_resolve_resource_raises_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discover, "discover_usb", lambda: None)
    monkeypatch.setattr(discover, "discover_lan", lambda *a, **k: None)
    with pytest.raises(connect.InstrumentConnectionError):
        connect.resolve_resource()


def test_autoconnect_resolves_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit mock backend_factory keeps this hermetic (no hardware import).
    usb = discover.DiscoveryResult(
        resource="USB::DS1ZA::INSTR", source=DiscoverySource.USB, reliable=True
    )
    monkeypatch.setattr(discover, "discover_usb", lambda: usb)
    inst = connect.autoconnect(backend_factory=lambda resource: MockInstrument())
    assert isinstance(inst, MockInstrument)
    assert connect.cached_resource() == "USB::DS1ZA::INSTR"


def test_default_factory_routes_mock_resources() -> None:
    # None / MOCK-prefixed resources select the mock with no hardware needed.
    assert isinstance(connect._default_backend_factory(None), MockInstrument)
    assert isinstance(connect._default_backend_factory("MOCK::DS1ZA"), MockInstrument)


def test_default_factory_builds_live_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    # Without SCPI_MCP_MOCK the factory builds the live backend, opening a socket
    # device from the resolved resource. Both seams are stubbed to stay hermetic.
    monkeypatch.delenv("SCPI_MCP_MOCK", raising=False)
    import scpi_mcp.instruments.rigol_ds1000z as rigol

    captured: dict = {}

    def fake_open(resource: str) -> str:
        captured["resource"] = resource
        return "DEVICE"

    monkeypatch.setattr(connect, "_open_socket_device", fake_open)

    class FakeBackend:
        def __init__(self, device) -> None:
            captured["device"] = device

    monkeypatch.setattr(rigol, "RigolDS1000Z", FakeBackend)
    backend = connect._default_backend_factory("TCPIP0::192.168.2.2::5555::SOCKET")
    assert isinstance(backend, FakeBackend)
    assert captured["resource"] == "TCPIP0::192.168.2.2::5555::SOCKET"
    assert captured["device"] == "DEVICE"


def test_socket_resource_normalization() -> None:
    assert (
        connect._socket_resource("192.168.2.2") == "TCPIP0::192.168.2.2::5555::SOCKET"
    )
    assert (
        connect._socket_resource("TCPIP::192.168.2.2::INSTR")
        == "TCPIP0::192.168.2.2::5555::SOCKET"
    )
    already = "TCPIP0::192.168.2.2::5555::SOCKET"
    assert connect._socket_resource(already) == already


def test_connect_to_passes_resource_to_factory() -> None:
    captured = {}

    def factory(resource: str) -> MockInstrument:
        captured["resource"] = resource
        return MockInstrument()

    connect.connect_to("TCPIP::192.168.2.2::INSTR", backend_factory=factory)
    assert captured["resource"] == "TCPIP::192.168.2.2::INSTR"
