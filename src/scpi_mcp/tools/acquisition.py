"""Acquisition tools: run / stop / single / force, acq type, memory depth.

These are the disruptive operations. They require the ``full`` tier *and* are
flagged confirmation-required: each takes ``confirm`` and is refused unless the
caller passes ``confirm=True``. Enforcement is in :func:`scpi_mcp.config.requires`.
"""

from __future__ import annotations

from typing import Any, Optional

from ..config import PermissionTier, Session, requires
from . import guarded


@requires(PermissionTier.FULL, confirmation=True)
def run_impl(session: Session, *, confirm: bool = False) -> dict[str, Any]:
    """Start continuous acquisition (disruptive)."""
    session.require_instrument().run()
    return {"ok": True, "state": "running"}


@requires(PermissionTier.FULL, confirmation=True)
def stop_impl(session: Session, *, confirm: bool = False) -> dict[str, Any]:
    """Stop acquisition (disruptive)."""
    session.require_instrument().stop()
    return {"ok": True, "state": "stopped"}


@requires(PermissionTier.FULL, confirmation=True)
def single_impl(session: Session, *, confirm: bool = False) -> dict[str, Any]:
    """Arm a single acquisition (disruptive)."""
    session.require_instrument().single()
    return {"ok": True, "state": "single"}


@requires(PermissionTier.FULL, confirmation=True)
def force_trigger_impl(session: Session, *, confirm: bool = False) -> dict[str, Any]:
    """Force a trigger event (disruptive)."""
    session.require_instrument().force_trigger()
    return {"ok": True, "forced": True}


@requires(PermissionTier.FULL, confirmation=True)
def set_acquisition_impl(
    session: Session,
    *,
    acq_type: Optional[str] = None,
    memory_depth: Optional[int] = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Set acquisition type and/or memory depth (disruptive)."""
    session.require_instrument().set_acquisition(
        acq_type=acq_type, memory_depth=memory_depth
    )
    return {"ok": True, "acq_type": acq_type, "memory_depth": memory_depth}


def register(mcp: Any, session: Session) -> None:
    mcp.tool(name="acq_run")(guarded(session, run_impl))
    mcp.tool(name="acq_stop")(guarded(session, stop_impl))
    mcp.tool(name="acq_single")(guarded(session, single_impl))
    mcp.tool(name="acq_force")(guarded(session, force_trigger_impl))
    mcp.tool(name="acq_configure")(guarded(session, set_acquisition_impl))
