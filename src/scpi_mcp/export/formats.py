"""Export captured data to JSON / CSV / XLSX / PNG.

Part 1: these accept a :class:`~scpi_mcp.instruments.base.Waveform` (or the mock
data the tools produce) and emit real, valid files in each format — JSON, CSV,
and XLSX are fully functional against mock data; PNG is a stub that writes a
minimal valid file (real plotting is wired up alongside hardware in Part 3).

Each function takes an output ``path`` and returns it, so tools can hand back a
location. They are deliberately format-only: no instrument access here.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ..instruments.base import Waveform

PathLike = str | Path


def to_json(waveform: Waveform, path: PathLike) -> Path:
    """Write a waveform to JSON (samples + metadata)."""
    out = Path(path)
    payload = {
        "channel": waveform.channel,
        "source": waveform.source,
        "sample_rate": waveform.sample_rate,
        "n_points": waveform.n_points,
        "time": waveform.time,
        "volts": waveform.volts,
    }
    out.write_text(json.dumps(payload, indent=2))
    return out


def to_csv(waveform: Waveform, path: PathLike) -> Path:
    """Write a waveform to CSV with ``time_s,volts`` columns."""
    out = Path(path)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time_s", "volts"])
        writer.writerows(zip(waveform.time, waveform.volts, strict=True))
    return out


def to_xlsx(waveform: Waveform, path: PathLike, *, chart: bool = False) -> Path:
    """Write a waveform to XLSX. Optionally embed a line chart.

    The chart is optional (off by default); when requested it plots volts vs.
    sample index using openpyxl's native chart support.
    """
    from openpyxl import Workbook

    out = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = f"CH{waveform.channel}"
    ws.append(["time_s", "volts"])
    for t, v in zip(waveform.time, waveform.volts, strict=True):
        ws.append([t, v])

    if chart and waveform.n_points:
        from openpyxl.chart import LineChart, Reference

        line = LineChart()
        line.title = f"CH{waveform.channel} waveform"
        data = Reference(ws, min_col=2, min_row=1, max_row=waveform.n_points + 1)
        line.add_data(data, titles_from_data=True)
        ws.add_chart(line, "D2")

    wb.save(out)
    return out


def to_png(waveform: Waveform, path: PathLike) -> Path:
    """Write a PNG of the waveform.

    Part 1 stub: emits a minimal valid (1x1) PNG so the export path is testable
    without a plotting backend.

    TODO: Part 3 — render an actual plot (matplotlib or the scope's own screen
    grab) instead of the placeholder.
    """
    out = Path(path)
    # Smallest valid 1x1 transparent PNG.
    _PNG_1X1 = bytes(
        [
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
            0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
            0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
            0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
        ]
    )
    out.write_bytes(_PNG_1X1)
    return out
