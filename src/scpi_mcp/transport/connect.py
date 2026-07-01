"""Connection resolution + the resource-string cache.

Turns "I want a scope" into a concrete :class:`~scpi_mcp.instruments.base.Instrument`,
using the discovery cascade to resolve a VISA resource string and the instrument
layer to construct the backend. Caches the resolved resource so subsequent calls
skip discovery.

Backend selection is a transport concern only insofar as Part 1 defaults to the
mock; the real backend (``RigolDS1000Z``) is constructed from the resolved
resource string and never sees discovery.
"""

from __future__ import annotations

from collections.abc import Callable

from ..instruments.base import Instrument
from ..instruments.mock import MockInstrument
from .discover import DiscoveryResult, cascade, discover_manual

# Factory that builds a backend from a resolved resource string. Swappable so
# Part 1 can default to the mock and Part 3 can point at the real backend.
BackendFactory = Callable[[str], Instrument]


class InstrumentConnectionError(RuntimeError):
    """Raised when no instrument could be resolved/connected."""


# Module-level cache of the last resolved resource string.
_cached_resource: str | None = None


def cached_resource() -> str | None:
    return _cached_resource


def clear_cache() -> None:
    global _cached_resource
    _cached_resource = None


def resolve_resource(host: str | None = None, *, use_cache: bool = True) -> str:
    """Resolve a VISA resource string via cache → discovery cascade.

    Raises :class:`InstrumentConnectionError` if nothing is found (the connection tool
    turns that into an IP prompt).
    """
    global _cached_resource
    if use_cache and _cached_resource is not None:
        return _cached_resource

    result: DiscoveryResult | None
    if host:
        result = discover_manual(host) or cascade(host=host)
    else:
        result = cascade()

    if result is None:
        raise InstrumentConnectionError(
            "no instrument found via USB or LAN. Provide an IP/hostname to "
            "build a TCPIP::<ip>::INSTR resource."
        )
    _cached_resource = result.resource
    return result.resource


def _socket_resource(resource_or_ip: str) -> str:
    """Normalize a host or VISA resource to a raw-socket resource on port 5555.

    On the bench link VXI-11/``INSTR`` stalls, so we always talk over the raw
    SCPI socket (``TCPIP0::<host>::5555::SOCKET``), which is fast and stable.
    """
    text = resource_or_ip
    if "SOCKET" in text.upper():
        return text
    if text.upper().startswith("TCPIP"):
        parts = text.split("::")
        host = parts[1] if len(parts) > 1 else text
    else:
        host = text
    return f"TCPIP0::{host}::5555::SOCKET"


def _open_socket_device(resource: str):
    """Open a raw-socket pyvisa resource, wrapped for the library subsystems."""
    import pyvisa

    from ..instruments.rigol_ds1000z import _SocketOscope

    rm = pyvisa.ResourceManager("@py")
    rsrc = rm.open_resource(_socket_resource(resource))
    rsrc.read_termination = "\n"
    rsrc.write_termination = "\n"
    rsrc.timeout = 15000
    return _SocketOscope(rsrc)


def _default_backend_factory(resource: str) -> Instrument:
    """Build the backend for a resolved resource.

    Defaults to the live :class:`RigolDS1000Z` over a raw socket. Set the
    ``SCPI_MCP_MOCK`` environment variable to force the mock backend (used by CI
    and by the server when no bench scope is attached).
    """
    import os

    if os.environ.get("SCPI_MCP_MOCK"):
        return MockInstrument()
    from ..instruments.rigol_ds1000z import RigolDS1000Z

    return RigolDS1000Z(_open_socket_device(resource))


def connect_to(
    resource_or_ip: str,
    *,
    backend_factory: BackendFactory = _default_backend_factory,
) -> Instrument:
    """Connect to an explicit resource string or IP/hostname.

    Accepts either a full VISA resource (``TCPIP::...::INSTR``, ``USB::...``) or
    a bare IP/hostname, which is resolved through :func:`discover_manual`.
    """
    global _cached_resource
    if "::" in resource_or_ip:
        resource = resource_or_ip  # already a VISA resource string
    else:
        result = discover_manual(resource_or_ip)
        if result is None:
            raise InstrumentConnectionError(
                f"could not reach an instrument at {resource_or_ip!r}."
            )
        resource = result.resource
    _cached_resource = resource
    return backend_factory(resource)


def autoconnect(
    host: str | None = None,
    *,
    backend_factory: BackendFactory = _default_backend_factory,
) -> Instrument:
    """Resolve a resource via the cascade and construct a backend.

    This is what the connection tool calls. In Part 1 the default factory
    returns a :class:`MockInstrument`, so it succeeds with zero hardware.
    """
    resource = resolve_resource(host)
    return backend_factory(resource)
