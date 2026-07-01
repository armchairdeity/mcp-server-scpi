"""CLI `waveform` command — captures to file(s) via the export formatters.

Runs against the mock backend (the autouse fixture forces SCPI_MCP_MOCK), so no
hardware is touched.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from scpi_mcp.cli.main import app

runner = CliRunner()


def test_waveform_writes_requested_formats(tmp_path):
    base = tmp_path / "cap"
    result = runner.invoke(
        app, ["--mock", "waveform", "1", "-f", "json,csv", "-o", str(base)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "cap.json").exists()
    assert (tmp_path / "cap.csv").exists()
    # JSON is a real waveform payload
    payload = json.loads((tmp_path / "cap.json").read_text())
    assert payload["channel"] == 1
    assert payload["n_points"] > 0
    # CSV has a header + one row per sample
    lines = (tmp_path / "cap.csv").read_text().splitlines()
    assert lines[0] == "time_s,volts"
    assert len(lines) == payload["n_points"] + 1


def test_waveform_rejects_unknown_format(tmp_path):
    result = runner.invoke(
        app, ["--mock", "waveform", "1", "-f", "bogus", "-o", str(tmp_path / "x")]
    )
    assert result.exit_code == 2
    assert "Unknown format" in result.output
