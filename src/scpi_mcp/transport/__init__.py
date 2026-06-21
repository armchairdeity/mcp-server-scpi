"""Transport / connectivity layer.

Owns discovery and resolves a single VISA *resource string*. Nothing above this
layer (instruments, tools) sees pyvisa, broadcast packets, or SCPI — they get a
resource string and, from the instrument layer, a connected backend.
"""

from .connect import (
    InstrumentConnectionError,
    autoconnect,
    connect_to,
    resolve_resource,
)
from .discover import DiscoveryResult, cascade, discover_lan, discover_usb

__all__ = [
    "InstrumentConnectionError",
    "DiscoveryResult",
    "autoconnect",
    "cascade",
    "connect_to",
    "discover_lan",
    "discover_usb",
    "resolve_resource",
]
