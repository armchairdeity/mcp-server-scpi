"""Connection tools: autoconnect / self-config, identify, capability report.

These bridge the transport layer (discovery → resource string → backend) into
the session, then report identity and capabilities. Nothing here knows about
SCPI or a specific vendor.
"""

from __future__ import annotations

from typing import Any

from .. import transport
from ..capabilities import detect_capabilities
from ..config import PermissionTier, Session, requires
from . import guarded


@requires(PermissionTier.READ_ONLY)
def self_config_impl(session: Session, host: str | None = None) -> dict[str, Any]:
    """Discover/connect an instrument and attach it to the session.

    Runs the transport cascade (USB → LAN → manual host). In Part 1 the backend
    factory yields a ``MockInstrument``, so this succeeds with zero hardware.
    """
    instrument = transport.autoconnect(host)
    session.instrument = instrument
    session.resource = transport.connect.cached_resource()
    idn = instrument.identify()
    return {
        "ok": True,
        "connected": True,
        "resource": session.resource,
        "identity": str(idn),
    }


@requires(PermissionTier.READ_ONLY)
def identify_impl(session: Session) -> dict[str, Any]:
    """Return the connected instrument's parsed identity."""
    idn = session.require_instrument().identify()
    return {
        "ok": True,
        "vendor": idn.vendor,
        "model": idn.model,
        "serial": idn.serial,
        "firmware": idn.firmware,
    }


@requires(PermissionTier.READ_ONLY)
def capability_report_impl(session: Session) -> dict[str, Any]:
    """Report detected capabilities (channels, bandwidth, options)."""
    caps = detect_capabilities(session.require_instrument())
    return {
        "ok": True,
        "model": caps.model,
        "analog_channels": caps.analog_channels,
        "channels": list(caps.channel_ids()),
        "bandwidth_mhz": caps.bandwidth_mhz,
        "has_source": caps.has_source,
        "has_logic": caps.has_logic,
        "max_memory_depth": caps.max_memory_depth,
        "options": list(caps.options),
    }


def register(mcp: Any, session: Session) -> None:
    mcp.tool(name="self_config")(guarded(session, self_config_impl))
    mcp.tool(name="identify")(guarded(session, identify_impl))
    mcp.tool(name="capability_report")(guarded(session, capability_report_impl))
