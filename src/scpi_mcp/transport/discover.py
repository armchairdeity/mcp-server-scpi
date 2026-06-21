"""Instrument discovery — the cascade that resolves a VISA resource string.

Order (per spec):

1. **USB enumerate** — list VISA resources, probe each with ``*IDN?``, match
   RIGOL / DS1 models. Reliable.
2. **LAN auto-discovery** — best-effort LXI/VXI-11 broadcast, short timeout.
   *Not reliable on all networks* and clearly flagged as such.
3. **IP prompt** — caller supplies an IP/hostname; we build
   ``TCPIP::<ip>::INSTR`` and confirm via ``*IDN?``.

This module owns all pyvisa usage. It is imported lazily so the package loads
with no VISA backend present, and **no live calls happen in Part 1** — the
``_resource_manager`` and ``_probe_idn`` seams are monkeypatched in tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Models we recognize as "ours". DS1054Z reports as DS1104Z once unlocked.
_RIGOL_IDN_RE = re.compile(r"RIGOL.*DS1\d{3}Z", re.IGNORECASE)

# Short timeout for the best-effort LAN broadcast (seconds).
LAN_DISCOVERY_TIMEOUT = 2.0


class DiscoverySource(str, Enum):
    USB = "usb"
    LAN = "lan"
    MANUAL = "manual"


@dataclass(frozen=True)
class DiscoveryResult:
    """A resolved candidate plus how we found it."""

    resource: str
    source: DiscoverySource
    idn: Optional[str] = None
    # True only for sources we trust; LAN broadcast is best-effort.
    reliable: bool = True


# --- pyvisa seams (lazy + monkeypatchable) ----------------------------------


def _resource_manager():
    """Return a pyvisa ResourceManager. Imported lazily; patched out in tests.

    Part 1 never calls this for real — it exists so transport *can* talk to VISA
    in Part 3 without the rest of the codebase importing pyvisa.
    """
    import pyvisa  # local import: no hard dependency at module load

    return pyvisa.ResourceManager()


def _probe_idn(resource: str, timeout_ms: int = 2000) -> Optional[str]:
    """Open ``resource``, query ``*IDN?``, return the response (or None).

    The single point where transport actually touches an instrument to identify
    it. Monkeypatched in tests; live only in Part 3.
    """
    rm = _resource_manager()
    try:
        dev = rm.open_resource(resource)
        dev.timeout = timeout_ms
        try:
            return str(dev.query("*IDN?")).strip()
        finally:
            dev.close()
    except Exception:
        return None


# --- the three discovery stages ---------------------------------------------


def discover_usb() -> Optional[DiscoveryResult]:
    """Enumerate USB resources and return the first Rigol DS1000Z found."""
    rm = _resource_manager()
    try:
        resources = rm.list_resources()
    except Exception:
        return None
    for resource in resources:
        if "USB" not in resource.upper():
            continue
        idn = _probe_idn(resource)
        if idn and _RIGOL_IDN_RE.search(idn):
            return DiscoveryResult(
                resource=resource,
                source=DiscoverySource.USB,
                idn=idn,
                reliable=True,
            )
    return None


def discover_lan(timeout: float = LAN_DISCOVERY_TIMEOUT) -> Optional[DiscoveryResult]:
    """Best-effort LAN auto-discovery via LXI/VXI-11 broadcast.

    Returns ``None`` if nothing answers within ``timeout``. This is explicitly
    *not reliable* on all networks (broadcasts get dropped, VLANs, firewalls) —
    a ``None`` here does not mean "no instrument", just "not found this way".

    TODO: Part 3 — implement the actual VXI-11 / mDNS broadcast against the unit
    at 192.168.2.2 and verify. Part 1 returns None (no live network I/O).
    """
    return None


def discover_manual(host: str) -> Optional[DiscoveryResult]:
    """Build ``TCPIP::<host>::INSTR`` and confirm it answers ``*IDN?``."""
    resource = f"TCPIP::{host}::INSTR"
    idn = _probe_idn(resource)
    if idn and _RIGOL_IDN_RE.search(idn):
        return DiscoveryResult(
            resource=resource,
            source=DiscoverySource.MANUAL,
            idn=idn,
            reliable=True,
        )
    # Even if the IDN doesn't match our pattern, the user asked for this host;
    # hand it back as a manual (lower-trust) candidate so connect_to can decide.
    if idn is not None:
        return DiscoveryResult(
            resource=resource,
            source=DiscoverySource.MANUAL,
            idn=idn,
            reliable=False,
        )
    return None


def cascade(host: Optional[str] = None) -> Optional[DiscoveryResult]:
    """Run the full discovery cascade, returning the first success.

    USB → LAN (best-effort) → manual (only if ``host`` is supplied). Returns
    ``None`` if every stage comes up empty; the caller (``connect``/the
    connection tool) then prompts the user for an IP.
    """
    result = discover_usb()
    if result is not None:
        return result
    result = discover_lan()
    if result is not None:
        return result
    if host:
        return discover_manual(host)
    return None
