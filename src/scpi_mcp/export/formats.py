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


# Time-axis unit scaling: (threshold in seconds, divisor, label).
_TIME_UNITS = (
    (1e-6, 1e-9, "ns"),
    (1e-3, 1e-6, "µs"),
    (1.0, 1e-3, "ms"),
)


def _time_scale(max_abs_t: float) -> tuple[float, str]:
    """Pick a human time unit (ns/µs/ms/s) from the largest |t| in the trace."""
    for threshold, divisor, label in _TIME_UNITS:
        if max_abs_t < threshold:
            return divisor, label
    return 1.0, "s"


def to_png(waveform: Waveform, path: PathLike) -> Path:
    """Render the waveform to a PNG plot (matplotlib, Agg backend).

    Plots volts vs. time with an auto-scaled time axis (ns/µs/ms/s), axis
    labels, and a channel/source title. Requires matplotlib (the ``plot`` or
    ``hardware`` extra); raises a clear :class:`ImportError` if it's missing.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless: no display needed
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised only without matplotlib
        raise ImportError(
            "PNG export needs matplotlib. Install the 'plot' extra: "
            '`uv pip install -e ".[plot]"`.'
        ) from exc

    out = Path(path)
    max_abs_t = max((abs(t) for t in waveform.time), default=0.0)
    divisor, unit = _time_scale(max_abs_t)
    times = [t / divisor for t in waveform.time]

    fig, ax = plt.subplots(figsize=(10, 5))
    try:
        ax.plot(times, waveform.volts, linewidth=0.8, color="#e8b923")
        ax.set_xlabel(f"Time ({unit})")
        ax.set_ylabel("Voltage (V)")
        ax.set_title(f"CH{waveform.channel} · {waveform.source}")
        ax.grid(True, which="both", alpha=0.3)
        fig.tight_layout()
        fig.savefig(out, dpi=100)
    finally:
        plt.close(fig)
    return out
