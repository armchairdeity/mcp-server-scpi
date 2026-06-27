"""scpictl — command-line control for SCPI instruments (oscilloscopes).

Shares the Session / transport / instrument stack with the MCP server — no
duplicated logic. Designed for two use cases:

  1. **Interactive bench use** — identify, measure, snapshot, characterize.
  2. **Scheduled capture** — ``scpictl capture`` fires from launchd at an
     interval, takes a measurement snapshot for each active channel, and
     appends a CSV row to a log file. This is the atomic unit the
     ``scope-monitor`` slash command's launchd plists fire.

Every subcommand is self-contained: auto-connects, does the work, exits.

Measurement sentinel
---------------------
Instruments return 9.9e37 when a measurement is unavailable (e.g. no signal,
display gating, or the quantity doesn't apply to the current waveform). The CLI
maps any value with abs() >= 9e37 to ``null`` / empty in CSV output.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from ..capabilities import detect_capabilities
from ..config import PermissionTier, Session
from ..instruments.base import MeasurementKind
from ..instruments.mock import MockInstrument
from ..tools.characterize import characterize_signal_impl
from ..tools.connection import capability_report_impl, identify_impl, self_config_impl
from ..tools.measure import measure_impl, snapshot_impl

# ---------------------------------------------------------------------------
# Sentinel handling
# ---------------------------------------------------------------------------

_SENTINEL_THRESHOLD = 9e37  # abs(value) >= this -> "no measurement available"


def _null_sentinel(value: float | None) -> float | None:
    """Replace the instrument's 9.9e37 'unavailable' sentinel with None."""
    if value is None:
        return None
    return None if abs(value) >= _SENTINEL_THRESHOLD else value


# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------


def _connect(
    host: str | None,
    tier: str = "read_only",
    *,
    mock: bool = False,
) -> Session:
    """Build and return a connected Session, exiting on failure.

    Pass ``mock=True`` to skip discovery and use a MockInstrument — useful for
    development and CI where no real scope is present.  The ``SCPI_MCP_MOCK``
    environment variable also activates mock mode (set to any non-empty value).
    """
    import os

    session = Session(tier=PermissionTier.from_str(tier))

    if mock or os.environ.get("SCPI_MCP_MOCK"):
        session.instrument = MockInstrument()
        session.resource = "MOCK::0"
        return session

    result = self_config_impl(session, host)
    if not result.get("ok"):
        typer.echo(f"Connection failed: {result}", err=True)
        raise typer.Exit(1)
    return session


# ---------------------------------------------------------------------------
# App + default measurement set
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="scpictl",
    help="Command-line control for SCPI instruments.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

# Module-level mock flag — set by the --mock option in the app callback so
# every subcommand can read it without repeating the option everywhere.
_use_mock: bool = False


@app.callback()
def _global_options(
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Use MockInstrument (no real scope needed)"),
    ] = False,
) -> None:
    """Global options applied before any subcommand."""
    global _use_mock
    _use_mock = mock


# Ordered list used by `capture` and `snapshot` — matches scope-monitor spec.
_CAPTURE_KINDS: list[MeasurementKind] = [
    MeasurementKind.FREQUENCY,
    MeasurementKind.PERIOD,
    MeasurementKind.VPP,
    MeasurementKind.VRMS,
    MeasurementKind.DUTY,
]

_CSV_HEADER = (
    ["timestamp", "session_id", "channel"] + [k.value for k in _CAPTURE_KINDS]
)


# ---------------------------------------------------------------------------
# Rows formatter — clean, SI-scaled, aligned columns
# ---------------------------------------------------------------------------


def _si(value: float | None, unit: str) -> str:
    """Format a value with SI prefix scaling. Returns '--' for None."""
    if value is None:
        return "--"
    abs_v = abs(value)
    if unit == "Hz":
        if abs_v >= 1e6:
            return f"{value/1e6:.3f}MHz"
        if abs_v >= 1e3:
            return f"{value/1e3:.3f}kHz"
        return f"{value:.3f}Hz"
    if unit == "s":
        if abs_v >= 1:
            return f"{value:.4f}s"
        if abs_v >= 1e-3:
            return f"{value*1e3:.3f}ms"
        if abs_v >= 1e-6:
            return f"{value*1e6:.3f}us"
        return f"{value*1e9:.3f}ns"
    if unit == "V":
        if abs_v >= 1:
            return f"{value:.3f}V"
        return f"{value*1e3:.1f}mV"
    if unit == "%":
        return f"{value:.1f}%"
    return f"{value:.4g} {unit}"


_ROW_HEADER = (
    f"{'timestamp':<24}  {'ch':>3}  "
    f"{'freq':>10}  {'period':>10}  {'vpp':>8}  {'vrms':>8}  {'duty':>7}"
)


def _row_line(ts_short: str, ch: int, row: dict) -> str:
    freq   = _si(_null_sentinel(row.get("frequency")), "Hz")
    period = _si(_null_sentinel(row.get("period")),    "s")
    vpp    = _si(_null_sentinel(row.get("vpp")),       "V")
    vrms   = _si(_null_sentinel(row.get("vrms")),      "V")
    duty   = _si(_null_sentinel(row.get("duty")),      "%")
    return (
        f"{ts_short:<24}  ch{ch}  "
        f"{freq:>10}  {period:>10}  {vpp:>8}  {vrms:>8}  {duty:>7}"
    )


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@app.command()
def connect(
    host: Annotated[
        str | None, typer.Option("--host", "-h", help="IP or hostname")
    ] = None,
) -> None:
    """Connect to an instrument and report its identity and resource string."""
    session = _connect(host, mock=_use_mock)
    result = identify_impl(session)
    typer.echo(
        f"{result['vendor']} {result['model']}  "
        f"SN:{result['serial']}  fw:{result['firmware']}"
    )
    typer.echo(f"Resource: {session.resource}")


@app.command()
def identify(
    host: Annotated[str | None, typer.Option("--host", "-h")] = None,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="Output: text|json")
    ] = "text",
) -> None:
    """Identify the connected instrument (vendor, model, serial, firmware)."""
    session = _connect(host, mock=_use_mock)
    result = identify_impl(session)
    if fmt == "json":
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(
            f"{result['vendor']} {result['model']}  "
            f"SN:{result['serial']}  fw:{result['firmware']}"
        )


@app.command()
def caps(
    host: Annotated[str | None, typer.Option("--host", "-h")] = None,
) -> None:
    """Report instrument capabilities: channels, bandwidth, options."""
    session = _connect(host, mock=_use_mock)
    result = capability_report_impl(session)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def capture(
    channels: Annotated[
        list[int] | None,
        typer.Argument(help="Channels to capture (default: all detected)"),
    ] = None,
    host: Annotated[str | None, typer.Option("--host", "-h")] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o",
            help="CSV file path (appends; writes header if new)",
        ),
    ] = None,
    session_id: Annotated[
        str | None,
        typer.Option(
            "--session-id", "-s",
            help="Session ID tag; defaults to YYYYMMDD-HHMMSS",
        ),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option(
            "--format", "-f",
            help="Output format: rows|csv|json (stdout default: rows)",
        ),
    ] = "",
    header: Annotated[
        bool,
        typer.Option(
            "--header/--no-header",
            help="Print column header row (rows format)",
        ),
    ] = False,
) -> None:
    """Capture a measurement snapshot for one or more channels.

    This is the primary launchd target for scope-monitor. Each invocation:
      1. Connects to the instrument.
      2. Takes a snapshot (freq, period, vpp, vrms, duty) per channel.
      3. Appends one row per channel to --output (CSV) or prints to stdout.
      4. Exits.

    Default stdout format is 'rows' (SI-scaled, aligned). File output
    via --output defaults to 'csv' (machine-readable, full precision).

      scpictl capture              # all channels -> neat rows to stdout
      scpictl capture 1 2          # channels 1 and 2
      scpictl capture -f json | jq '.[].frequency'
      scpictl capture -o log.csv   # append CSV rows to file

    Unavailable measurements (sentinel 9.9e37) -> '--' in rows,
    empty in csv, null in json.
    """
    session = _connect(host, mock=_use_mock)

    # Resolve channels: explicit list or all that the instrument knows about
    if not channels:
        instrument_caps = detect_capabilities(session.instrument)
        channels = list(instrument_caps.channel_ids())

    sid = session_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    rows: list[dict] = []
    for ch in channels:
        result = snapshot_impl(session, ch, kinds=[k.value for k in _CAPTURE_KINDS])
        measurements = result.get("measurements", {})
        row: dict = {"timestamp": ts, "session_id": sid, "channel": ch}
        for kind in _CAPTURE_KINDS:
            raw = measurements.get(kind.value, {}).get("value")
            row[kind.value] = _null_sentinel(float(raw)) if raw is not None else None
        rows.append(row)

    # Resolve default format: rows for stdout, csv for file
    effective_fmt = fmt or ("csv" if output else "rows")

    if effective_fmt == "json":
        typer.echo(json.dumps(rows, indent=2, default=str))
        return

    if effective_fmt == "rows":
        if header:
            typer.echo(_ROW_HEADER)
        for row in rows:
            ts_short = row["timestamp"][:19] + "Z"
            typer.echo(_row_line(ts_short, row["channel"], row))
        return

    # CSV — append to file or print to stdout
    if output:
        file_exists = output.exists() and output.stat().st_size > 0
        with open(output, "a", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=_CSV_HEADER, extrasaction="ignore"
            )
            if not file_exists:
                writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(
            sys.stdout, fieldnames=_CSV_HEADER, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


@app.command()
def measure(
    channel: Annotated[int, typer.Argument(help="Channel number (1-4)")],
    kind: Annotated[
        str,
        typer.Argument(
            help=(
                "Measurement type: "
                "vpp|vrms|frequency|period|duty|rise_time|fall_time"
            )
        ),
    ],
    host: Annotated[str | None, typer.Option("--host", "-h")] = None,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="Output: text|json")
    ] = "text",
) -> None:
    """Take a single measurement on one channel."""
    session = _connect(host, mock=_use_mock)
    result = measure_impl(session, channel, kind)
    value = _null_sentinel(result["value"])
    if fmt == "json":
        typer.echo(json.dumps({**result, "value": value}, indent=2))
    else:
        unit = result["unit"]
        typer.echo(f"ch{channel}  {result['kind']}: {value} {unit}")


@app.command()
def snapshot(
    channel: Annotated[int, typer.Argument(help="Channel number (1-4)")],
    host: Annotated[str | None, typer.Option("--host", "-h")] = None,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="Output: text|json")
    ] = "text",
) -> None:
    """Take a measurement snapshot (freq, period, vpp, vrms, duty) on one channel."""
    session = _connect(host, mock=_use_mock)
    result = snapshot_impl(session, channel, kinds=[k.value for k in _CAPTURE_KINDS])
    measurements = result.get("measurements", {})

    if fmt == "json":
        cleaned = {
            k: {"value": _null_sentinel(v["value"]), "unit": v["unit"]}
            for k, v in measurements.items()
        }
        typer.echo(
            json.dumps({"channel": channel, "measurements": cleaned}, indent=2)
        )
    else:
        typer.echo(f"Channel {channel}:")
        for name, data in measurements.items():
            value = _null_sentinel(data["value"])
            unit = data["unit"]
            typer.echo(f"  {name:<14} {value}  {unit}")


@app.command()
def characterize(
    channel: Annotated[int, typer.Argument(help="Channel number (1-4)")],
    host: Annotated[str | None, typer.Option("--host", "-h")] = None,
) -> None:
    """Full signal characterization: probe, vertical fit, trigger hunt, measure.

    Note: characterize_signal is stubbed in Part 1 and fully implemented in
    Part 3 once the rigol-ds1000z hardware backend is wired up.
    """
    session = _connect(host, tier="read_config", mock=_use_mock)
    result = characterize_signal_impl(session, channel)
    typer.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()
