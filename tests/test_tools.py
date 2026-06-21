"""Tools call only the abstract interface; refusals are structured; the server
wires every module."""

from __future__ import annotations

from scpi_mcp.config import PermissionTier, Session
from scpi_mcp.instruments.mock import MockInstrument
from scpi_mcp.tools import capture, connection, guarded, measure
from scpi_mcp.tools.config_tools import set_timebase_impl


def test_self_config_connects_mock(monkeypatch) -> None:
    from scpi_mcp import transport

    monkeypatch.setattr(transport, "autoconnect", lambda host=None: MockInstrument())
    monkeypatch.setattr(transport.connect, "cached_resource", lambda: "USB::MOCK::INSTR")
    session = Session(tier=PermissionTier.READ_ONLY)
    result = connection.self_config_impl(session)
    assert result["connected"] is True
    assert session.instrument is not None


def test_capability_report(read_only_session: Session) -> None:
    report = connection.capability_report_impl(read_only_session)
    assert report["analog_channels"] == 4
    assert report["bandwidth_mhz"] == 100
    assert report["has_source"] is False
    assert report["has_logic"] is False


def test_capture_aligned_multichannel(read_only_session: Session) -> None:
    result = capture.capture_aligned_impl(read_only_session, [1, 2, 3])
    assert len(result["waveforms"]) == 3
    assert {w["channel"] for w in result["waveforms"]} == {1, 2, 3}


def test_capture_omits_samples_by_default(read_only_session: Session) -> None:
    result = capture.capture_screen_impl(read_only_session, 1)
    assert "volts" not in result["waveform"]
    full = capture.capture_screen_impl(read_only_session, 1, include_samples=True)
    assert len(full["waveform"]["volts"]) == 1200


def test_measure_snapshot(read_only_session: Session) -> None:
    snap = measure.snapshot_impl(read_only_session, 1)
    assert "vpp" in snap["measurements"]
    assert "frequency" in snap["measurements"]


def test_measure_series_uses_settle(read_only_session: Session) -> None:
    inst = read_only_session.instrument
    measure.polled_series_impl(read_only_session, 1, "vpp", samples=3, interval_s=0.1)
    assert inst.settle_calls == [0.1, 0.1, 0.1]


def test_guarded_translates_refusal_to_payload() -> None:
    session = Session(tier=PermissionTier.READ_ONLY, instrument=MockInstrument())
    tool = guarded(session, set_timebase_impl)
    result = tool(scale=1e-3)  # needs read_config → refused, not raised
    assert result["refused"] is True
    assert result["ok"] is False


def test_server_registers_all_tools() -> None:
    import asyncio

    from scpi_mcp.server import build_server

    mcp = build_server(Session(tier=PermissionTier.FULL, instrument=MockInstrument()))
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    expected = {
        "self_config",
        "identify",
        "capability_report",
        "capture_screen",
        "capture_memory",
        "capture_aligned",
        "measure",
        "measure_snapshot",
        "measure_series",
        "set_channel",
        "set_timebase",
        "set_trigger",
        "acq_run",
        "acq_stop",
        "acq_single",
        "acq_force",
        "acq_configure",
        "characterize_signal",
    }
    assert expected <= names
