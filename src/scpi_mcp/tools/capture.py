"""Capture tools: screen and deep-memory waveforms, multi-channel aligned.

All reads go through the abstract interface. Returns waveform data in a
JSON-friendly shape; large memory captures are summarized by default to avoid
flooding the model, with an opt-in to include the full sample array.
"""

from __future__ import annotations

from typing import Any

from ..config import PermissionTier, Session, requires
from ..instruments.base import Waveform
from . import guarded


def _serialize(wf: Waveform, *, include_samples: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "channel": wf.channel,
        "source": wf.source,
        "n_points": wf.n_points,
        "sample_rate": wf.sample_rate,
        "t_start": wf.time[0] if wf.time else None,
        "t_end": wf.time[-1] if wf.time else None,
    }
    if include_samples:
        payload["time"] = wf.time
        payload["volts"] = wf.volts
    return payload


@requires(PermissionTier.READ_ONLY)
def capture_screen_impl(
    session: Session, channel: int, *, include_samples: bool = False
) -> dict[str, Any]:
    """Capture the on-screen waveform for one channel."""
    wf = session.require_instrument().capture_screen(channel)
    return {"ok": True, "waveform": _serialize(wf, include_samples=include_samples)}


@requires(PermissionTier.READ_ONLY)
def capture_memory_impl(
    session: Session,
    channel: int,
    points: int | None = None,
    *,
    include_samples: bool = False,
) -> dict[str, Any]:
    """Capture the deep-memory waveform for one channel."""
    wf = session.require_instrument().capture_memory(channel, points)
    return {"ok": True, "waveform": _serialize(wf, include_samples=include_samples)}


@requires(PermissionTier.READ_ONLY)
def capture_aligned_impl(
    session: Session,
    channels: list[int],
    *,
    deep: bool = False,
    include_samples: bool = False,
) -> dict[str, Any]:
    """Capture multiple channels on the same time base, aligned.

    The instrument shares one time base across channels, so a sequence of reads
    is already time-aligned. (Real hardware reads them back-to-back; the mock is
    instantaneous.)
    """
    inst = session.require_instrument()
    waveforms = []
    for ch in channels:
        wf = inst.capture_memory(ch) if deep else inst.capture_screen(ch)
        waveforms.append(_serialize(wf, include_samples=include_samples))
    return {"ok": True, "channels": channels, "waveforms": waveforms}


def register(mcp: Any, session: Session) -> None:
    mcp.tool(name="capture_screen")(guarded(session, capture_screen_impl))
    mcp.tool(name="capture_memory")(guarded(session, capture_memory_impl))
    mcp.tool(name="capture_aligned")(guarded(session, capture_aligned_impl))
