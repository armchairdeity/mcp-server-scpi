"""MockInstrument implements the full interface with no hardware."""

from __future__ import annotations

import math

import pytest

from scpi_mcp.instruments.base import Instrument, MeasurementKind, TriggerConfig
from scpi_mcp.instruments.mock import MockInstrument


def test_mock_is_an_instrument(mock_instrument: MockInstrument) -> None:
    assert isinstance(mock_instrument, Instrument)


def test_identify(mock_instrument: MockInstrument) -> None:
    idn = mock_instrument.identify()
    assert idn.vendor.startswith("RIGOL")
    assert idn.model == "DS1104Z"


def test_four_channels(mock_instrument: MockInstrument) -> None:
    assert mock_instrument.capabilities.channel_ids() == (1, 2, 3, 4)


def test_measure_vpp_matches_amplitude(mock_instrument: MockInstrument) -> None:
    m = mock_instrument.measure(1, MeasurementKind.VPP)
    # Default channel amplitude is 1.0 Vp → Vpp = 2.0.
    assert m.value == pytest.approx(2.0)
    assert m.unit == "V"


def test_measure_vrms(mock_instrument: MockInstrument) -> None:
    m = mock_instrument.measure(1, MeasurementKind.VRMS)
    assert m.value == pytest.approx(1.0 / math.sqrt(2.0))


def test_capture_screen_shape(mock_instrument: MockInstrument) -> None:
    wf = mock_instrument.capture_screen(1)
    assert wf.source == "screen"
    assert wf.n_points == 1200
    assert len(wf.time) == len(wf.volts) == 1200


def test_capture_memory_is_deep(mock_instrument: MockInstrument) -> None:
    wf = mock_instrument.capture_memory(1, points=20000)
    assert wf.source == "memory"
    assert wf.n_points == 20000


def test_set_channel_changes_offset(mock_instrument: MockInstrument) -> None:
    mock_instrument.set_channel(1, offset=0.5)
    wf = mock_instrument.capture_screen(1)
    # Mean of an offset sine ≈ the offset.
    assert sum(wf.volts) / len(wf.volts) == pytest.approx(0.5, abs=0.05)


def test_invalid_channel_raises(mock_instrument: MockInstrument) -> None:
    with pytest.raises(ValueError):
        mock_instrument.measure(9, MeasurementKind.VPP)


def test_trigger_and_acquisition_state(mock_instrument: MockInstrument) -> None:
    mock_instrument.set_trigger(TriggerConfig(source=2, level=0.0, slope="rising"))
    mock_instrument.stop()
    assert mock_instrument._running is False
    mock_instrument.run()
    assert mock_instrument._running is True


def test_settle_is_recorded_not_slept(mock_instrument: MockInstrument) -> None:
    mock_instrument.settle(0.2)
    assert mock_instrument.settle_calls == [0.2]
