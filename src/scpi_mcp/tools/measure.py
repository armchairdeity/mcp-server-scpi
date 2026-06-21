"""Measurement tools: snapshot of multiple quantities + a polled series.

Vpp, Vrms, frequency, period, duty, rise/fall — requested by vendor-neutral
:class:`MeasurementKind` and routed through the abstract interface.
"""

from __future__ import annotations

from typing import Any

from ..config import PermissionTier, Session, requires
from ..instruments.base import MeasurementKind
from . import guarded

_DEFAULT_SNAPSHOT = [
    MeasurementKind.VPP,
    MeasurementKind.VRMS,
    MeasurementKind.FREQUENCY,
    MeasurementKind.PERIOD,
    MeasurementKind.DUTY,
]


def _coerce_kind(kind: str | MeasurementKind) -> MeasurementKind:
    if isinstance(kind, MeasurementKind):
        return kind
    return MeasurementKind(kind.lower())


@requires(PermissionTier.READ_ONLY)
def measure_impl(session: Session, channel: int, kind: str) -> dict[str, Any]:
    """Take a single measurement of one quantity on one channel."""
    m = session.require_instrument().measure(channel, _coerce_kind(kind))
    return {
        "ok": True,
        "channel": m.channel,
        "kind": m.kind.value,
        "value": m.value,
        "unit": m.unit,
    }


@requires(PermissionTier.READ_ONLY)
def snapshot_impl(
    session: Session, channel: int, kinds: list[str] | None = None
) -> dict[str, Any]:
    """Take a snapshot of several measurements at once for one channel."""
    inst = session.require_instrument()
    selected = [_coerce_kind(k) for k in kinds] if kinds else _DEFAULT_SNAPSHOT
    results = {}
    for k in selected:
        m = inst.measure(channel, k)
        results[k.value] = {"value": m.value, "unit": m.unit}
    return {"ok": True, "channel": channel, "measurements": results}


@requires(PermissionTier.READ_ONLY)
def polled_series_impl(
    session: Session,
    channel: int,
    kind: str,
    samples: int = 5,
    interval_s: float = 0.0,
) -> dict[str, Any]:
    """Poll one measurement repeatedly, returning a short time series.

    ``interval_s`` is honored via the instrument's settle hook so the mock stays
    instant in tests while real hardware actually waits between reads.
    """
    inst = session.require_instrument()
    k = _coerce_kind(kind)
    series = []
    for _ in range(max(samples, 1)):
        m = inst.measure(channel, k)
        series.append(m.value)
        if interval_s:
            inst.settle(interval_s)
    return {
        "ok": True,
        "channel": channel,
        "kind": k.value,
        "samples": len(series),
        "series": series,
    }


def register(mcp: Any, session: Session) -> None:
    mcp.tool(name="measure")(guarded(session, measure_impl))
    mcp.tool(name="measure_snapshot")(guarded(session, snapshot_impl))
    mcp.tool(name="measure_series")(guarded(session, polled_series_impl))
