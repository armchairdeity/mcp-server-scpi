"""Export formats produce valid output from mock waveforms."""

from __future__ import annotations

import json
from pathlib import Path

from scpi_mcp.export import to_csv, to_json, to_png, to_xlsx
from scpi_mcp.instruments.mock import MockInstrument


def _waveform():
    return MockInstrument().capture_screen(1)


def test_json_roundtrip(tmp_path: Path) -> None:
    wf = _waveform()
    out = to_json(wf, tmp_path / "wf.json")
    data = json.loads(out.read_text())
    assert data["n_points"] == wf.n_points
    assert len(data["volts"]) == wf.n_points


def test_csv_has_header_and_rows(tmp_path: Path) -> None:
    wf = _waveform()
    out = to_csv(wf, tmp_path / "wf.csv")
    lines = out.read_text().splitlines()
    assert lines[0] == "time_s,volts"
    assert len(lines) == wf.n_points + 1


def test_xlsx_written(tmp_path: Path) -> None:
    out = to_xlsx(_waveform(), tmp_path / "wf.xlsx", chart=True)
    assert out.exists() and out.stat().st_size > 0


def test_png_is_valid_stub(tmp_path: Path) -> None:
    out = to_png(_waveform(), tmp_path / "wf.png")
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
