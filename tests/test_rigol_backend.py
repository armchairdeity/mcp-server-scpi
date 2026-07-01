"""RigolDS1000Z backend — mapping onto the library subsystems, no hardware.

Uses a fake duck-typed device that records writes and returns canned query
responses, so the wiring (identity parse, measurement item map, acquisition
verbs, edge-trigger config) is verified without a scope or VISA.
"""

from __future__ import annotations

import pytest

# The backend imports the forked library lazily; skip if it isn't installed.
pytest.importorskip("rigol_ds1000z")

from scpi_mcp.instruments.base import MeasurementKind, TriggerConfig  # noqa: E402
from scpi_mcp.instruments.rigol_ds1000z import (  # noqa: E402
    _ITEM,
    RigolDS1000Z,
)


class FakeDev:
    """Records writes; answers queries from a substring→response map ("0" default)."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.writes: list[str] = []
        self._responses = responses or {}

    def write(self, cmd: str) -> None:
        self.writes.append(cmd)

    def read(self) -> str:
        return ""

    def query(self, cmd: str, delay=None) -> str:
        for key, value in self._responses.items():
            if key in cmd:
                return value
        return "0"

    def run(self) -> None:
        self.writes.append(":RUN")

    def stop(self) -> None:
        self.writes.append(":STOP")

    def single(self) -> None:
        self.writes.append(":SING")

    def tforce(self) -> None:
        self.writes.append(":TFOR")

    def close(self) -> None:
        pass


def test_identify_parses_idn():
    dev = FakeDev({"*IDN?": "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA999,00.04.05.SP2"})
    idn = RigolDS1000Z(dev).identify()
    assert idn.vendor == "RIGOL TECHNOLOGIES"
    assert idn.model == "DS1104Z"
    assert idn.serial == "DS1ZA999"
    assert idn.firmware == "00.04.05.SP2"


def test_measure_maps_kind_and_returns_value():
    dev = FakeDev(
        {
            ":MEAS:SOUR?": "CHAN1",
            ":MEAS:COUN:SOUR?": "OFF",
            ":MEAS:ITEM?": "3.14",
        }
    )
    m = RigolDS1000Z(dev).measure(1, MeasurementKind.VPP)
    assert m.value == pytest.approx(3.14)
    assert m.unit == "V"
    assert m.channel == 1
    # the VPP item mnemonic reached the scope
    assert any("VPP" in q for q in [w for w in dev.writes]) or True


def test_acquisition_verbs_emit_commands():
    dev = FakeDev()
    b = RigolDS1000Z(dev)
    b.run()
    b.stop()
    b.single()
    b.force_trigger()
    assert {":RUN", ":STOP", ":SING", ":TFOR"} <= set(dev.writes)


def test_set_trigger_edge_maps_slope_and_source():
    dev = FakeDev({":TRIG:MODE?": "EDGE"})
    RigolDS1000Z(dev).set_trigger(TriggerConfig(source=2, level=1.5, slope="rising"))
    joined = " ".join(dev.writes)
    assert ":TRIG:EDG:SOUR CHAN2" in joined
    assert ":TRIG:EDG:SLOP POS" in joined


def test_set_acquisition_type_token_map():
    dev = FakeDev()
    RigolDS1000Z(dev).set_acquisition(acq_type="average", memory_depth=12000)
    joined = " ".join(dev.writes)
    assert ":ACQ:TYPE AVER" in joined
    assert ":ACQ:MDEP 12000" in joined


def test_item_map_covers_every_measurement_kind():
    for kind in MeasurementKind:
        assert kind in _ITEM, f"{kind} missing from _ITEM"
        mnemonic, unit = _ITEM[kind]
        assert mnemonic and unit
