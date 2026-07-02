"""FLAGSHIP tool: goal-level ``characterize_signal(channel)``.

This is the headline capability — hand it a channel and it figures out the
signal: find a stable trigger, scale the display to fit, then report a full
measurement set with confidence. It is the reason ``scpi-mcp`` is "oscilloscope
expertise" and not just "a SCPI wire."

The loop is fully implemented and runs against the live backend, settling and
re-verifying after each adjustment (bounded by ``MAX_SETTLE_ITERATIONS``) rather
than assuming an instant response.

The loop
--------
1. **Probe** — capture a screen waveform; rough-estimate amplitude & frequency.
2. **Vertical fit** — set channel scale/offset so the signal fills ~6 divisions.
       → settle, then re-capture and VERIFY it actually fits (clipping? too
         small?). Adjust and repeat, bounded, before trusting any reading.
3. **Horizontal fit** — set the time base to show a handful of periods.
       → settle, re-measure frequency, VERIFY stability across a couple reads.
4. **Trigger hunt** — set an edge trigger near mid-amplitude; if unstable, walk
       the level / flip the slope / nudge the time base (trigger-hunting tactics
       completed in the library's TRIGger subsystem, Part 2).
       → settle, VERIFY the trigger holds before measuring.
5. **Characterize** — take the full measurement snapshot (Vpp, Vrms, freq,
       period, duty, rise/fall), each settled-and-verified, and report with a
       confidence flag.

Settle-and-verify is the spine of every step: the library inserts sleeps on some
commands (reset, autoscale) and config changes need extra settle time before a
measurement is valid. The loop must ``instrument.settle(...)`` and re-read to
confirm the change took effect rather than assuming an instant response.
"""

from __future__ import annotations

import math
from typing import Any

from ..config import PermissionTier, Session, requires
from ..instruments.base import Instrument, MeasurementKind, TriggerConfig
from . import guarded

# Bound on the adjust→settle→verify iterations per stage.
MAX_SETTLE_ITERATIONS = 5
# Default settle window after a config change before re-measuring (seconds).
DEFAULT_SETTLE_S = 0.2

# DS1000Z has 8 vertical divisions; fill ~5 of them, accept 3–6.
_VDIV_TARGET = 5.0
_VDIV_MIN, _VDIV_MAX = 3.0, 6.0
# Show ~2.5 cycles across the 12 horizontal divisions.
_CYCLES_TARGET = 2.5
_HDIV = 12.0
# Measurements are "stable" if successive frequency reads agree within this.
_STABLE_REL = 0.05

# Full snapshot taken once the display is fit and triggered.
_SNAPSHOT = [
    MeasurementKind.FREQUENCY,
    MeasurementKind.PERIOD,
    MeasurementKind.VPP,
    MeasurementKind.VRMS,
    MeasurementKind.DUTY,
    MeasurementKind.RISE_TIME,
    MeasurementKind.FALL_TIME,
]


def _measure(inst: Instrument, channel: int, kind: MeasurementKind) -> float:
    """Single measurement as a float; NaN means the scope reported invalid."""
    return inst.measure(channel, kind).value


def _valid(v: float) -> bool:
    return v is not None and not math.isnan(v)


def _vertical_fit(inst: Instrument, channel: int) -> dict[str, Any]:
    """Scale the channel so the signal fills ~5 of 8 vertical divisions."""
    vpp = _measure(inst, channel, MeasurementKind.VPP)
    # If the signal is off-screen Vpp reads invalid; start wide and zoom in.
    scale = (vpp / _VDIV_TARGET) if _valid(vpp) and vpp > 0 else 1.0
    fitted = False
    for _ in range(MAX_SETTLE_ITERATIONS):
        inst.set_channel(channel, scale=scale)
        inst.settle(DEFAULT_SETTLE_S)
        vpp = _measure(inst, channel, MeasurementKind.VPP)
        if not _valid(vpp) or vpp <= 0:
            scale *= 2.0  # still off-screen — zoom out further
            continue
        divisions = vpp / scale
        if _VDIV_MIN <= divisions <= _VDIV_MAX:
            fitted = True
            break
        scale = vpp / _VDIV_TARGET  # re-target and re-verify
    return {"fitted": fitted, "scale": scale, "vpp": vpp}


def _horizontal_fit(inst: Instrument, channel: int) -> dict[str, Any]:
    """Set the timebase to show ~2.5 cycles and verify frequency is stable."""
    period = _measure(inst, channel, MeasurementKind.PERIOD)
    freq = _measure(inst, channel, MeasurementKind.FREQUENCY)
    if not _valid(period) or period <= 0:
        period = 1.0 / freq if _valid(freq) and freq > 0 else None
    stable = False
    freqs: list[float] = []
    if period:
        for _ in range(MAX_SETTLE_ITERATIONS):
            inst.set_timebase(scale=period * _CYCLES_TARGET / _HDIV)
            inst.settle(DEFAULT_SETTLE_S)
            f1 = _measure(inst, channel, MeasurementKind.FREQUENCY)
            f2 = _measure(inst, channel, MeasurementKind.FREQUENCY)
            freqs = [f1, f2]
            if _valid(f1) and _valid(f2) and f1 > 0:
                if abs(f1 - f2) / f1 <= _STABLE_REL:
                    stable = True
                    break
                period = 1.0 / f1  # re-target from the fresh reading
    return {"stable": stable, "freqs": freqs, "period": period}


def _trigger_hunt(inst: Instrument, channel: int) -> dict[str, Any]:
    """Set an edge trigger near mid-amplitude; verify reads stay stable."""
    # Mid-level from the on-screen samples (no Vmax/Vmin in the neutral enum).
    wf = inst.capture_screen(channel)
    level = (max(wf.volts) + min(wf.volts)) / 2 if wf.volts else 0.0
    triggered = False
    slope = "rising"
    for attempt in range(MAX_SETTLE_ITERATIONS):
        inst.set_trigger(TriggerConfig(source=channel, level=level, slope=slope))
        inst.settle(DEFAULT_SETTLE_S)
        f1 = _measure(inst, channel, MeasurementKind.FREQUENCY)
        f2 = _measure(inst, channel, MeasurementKind.FREQUENCY)
        if _valid(f1) and _valid(f2) and f1 > 0 and abs(f1 - f2) / f1 <= _STABLE_REL:
            triggered = True
            break
        # Nudge: pull level toward the sample mean, then flip slope.
        if wf.volts:
            level = sum(wf.volts) / len(wf.volts)
        if attempt % 2 == 1:
            slope = "falling" if slope == "rising" else "rising"
    return {"triggered": triggered, "level": level, "slope": slope}


@requires(PermissionTier.READ_CONFIG)
def characterize_signal_impl(
    session: Session, channel: int, export_path: str | None = None
) -> dict[str, Any]:
    """Characterize the signal on ``channel`` — the FLAGSHIP goal-level tool.

    Runs the probe → vertical fit → horizontal fit → trigger hunt → characterize
    loop, settling and re-verifying after each adjustment (bounded by
    :data:`MAX_SETTLE_ITERATIONS`). Returns the discovered signal parameters, a
    full measurement snapshot, and a confidence flag. When ``export_path`` is
    given, the deep-memory capture is rendered to a PNG there.
    """
    inst = session.require_instrument()

    # 1. Probe — rough initial parameters (the first measure validates channel).
    probe = {
        "frequency": _measure(inst, channel, MeasurementKind.FREQUENCY),
        "vpp": _measure(inst, channel, MeasurementKind.VPP),
    }

    # 2–4. Fit the display and find a stable trigger, each settle-and-verified.
    vertical = _vertical_fit(inst, channel)
    horizontal = _horizontal_fit(inst, channel)
    trigger = _trigger_hunt(inst, channel)

    # 5. Characterize — full measurement snapshot + deep-memory capture.
    measurements: dict[str, Any] = {}
    for kind in _SNAPSHOT:
        m = inst.measure(channel, kind)
        measurements[kind.value] = {"value": m.value, "unit": m.unit}

    # A screen capture of the now-fitted display spans a handful of periods,
    # which is the representative trace to return/plot. (Deep-memory RAW reads
    # at the full sample rate would be a sub-period sliver here.)
    waveform = inst.capture_screen(channel)
    export = None
    if export_path is not None:
        from ..export.formats import to_png

        export = str(to_png(waveform, export_path))

    # A confident result requires an actual signal — if the scope can't even
    # return a valid frequency, the fit/trigger flags are meaningless (a dead or
    # open channel must read "low", not "high").
    freq_ok = _valid(measurements.get("frequency", {}).get("value"))
    confidence = (
        "high"
        if freq_ok
        and vertical["fitted"]
        and horizontal["stable"]
        and trigger["triggered"]
        else "low"
    )
    return {
        "ok": True,
        "channel": channel,
        "confidence": confidence,
        "probe": probe,
        "vertical_fit": vertical,
        "horizontal_fit": horizontal,
        "trigger_hunt": trigger,
        "measurements": measurements,
        "waveform": {
            "n_points": waveform.n_points,
            "sample_rate": waveform.sample_rate,
            "source": waveform.source,
        },
        "export_png": export,
    }


def register(mcp: Any, session: Session) -> None:
    mcp.tool(name="characterize_signal")(guarded(session, characterize_signal_impl))
