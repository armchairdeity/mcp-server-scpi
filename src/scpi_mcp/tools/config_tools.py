"""Configuration tools: channel / timebase / trigger (read_config tier).

Non-destructive writes — they change how the scope is set up but don't start or
stop acquisition or reset state. Gated at ``read_config``.
"""

from __future__ import annotations

from typing import Any

from ..config import PermissionTier, Session, requires
from ..instruments.base import TriggerConfig
from . import guarded


@requires(PermissionTier.READ_CONFIG)
def set_channel_impl(
    session: Session,
    channel: int,
    *,
    enabled: bool | None = None,
    scale: float | None = None,
    offset: float | None = None,
    coupling: str | None = None,
) -> dict[str, Any]:
    """Set vertical config for a channel (enable, V/div, offset, coupling)."""
    session.require_instrument().set_channel(
        channel, enabled=enabled, scale=scale, offset=offset, coupling=coupling
    )
    return {"ok": True, "channel": channel}


@requires(PermissionTier.READ_CONFIG)
def set_timebase_impl(
    session: Session,
    *,
    scale: float | None = None,
    offset: float | None = None,
) -> dict[str, Any]:
    """Set horizontal time base (s/div and offset)."""
    session.require_instrument().set_timebase(scale=scale, offset=offset)
    return {"ok": True, "scale": scale, "offset": offset}


@requires(PermissionTier.READ_CONFIG)
def set_trigger_impl(
    session: Session,
    source: int,
    level: float,
    slope: str = "rising",
) -> dict[str, Any]:
    """Configure the edge trigger (source channel, level, slope)."""
    config = TriggerConfig(source=source, level=level, slope=slope)
    session.require_instrument().set_trigger(config)
    return {"ok": True, "source": source, "level": level, "slope": slope}


def register(mcp: Any, session: Session) -> None:
    mcp.tool(name="set_channel")(guarded(session, set_channel_impl))
    mcp.tool(name="set_timebase")(guarded(session, set_timebase_impl))
    mcp.tool(name="set_trigger")(guarded(session, set_trigger_impl))
