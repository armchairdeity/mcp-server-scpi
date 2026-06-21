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


def _default_backend_factory(resource: str) -> Instrument:
    """Part 1 default: ignore the resource and return a mock.

    TODO: Part 3 — return ``RigolDS1000Z(resource)`` here (or select by IDN),
    swapping the mock for the live scope.
    """
    return MockInstrument()


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
