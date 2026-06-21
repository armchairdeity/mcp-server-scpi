"""Permission tiers, session state, and the tool-layer permission guard.

The whole point of this module: **the server refuses, not the model.** Every
tool declares the tier it needs (and whether it's a disruptive op that needs
explicit confirmation). The guard here enforces it before the tool body runs,
regardless of what the model "decided" to call.

Tiers (monotonically increasing capability):

- ``read_only``   — capture / measure / query
- ``read_config`` — the above + non-destructive channel / timebase / trigger writes
- ``full``        — the above + run/stop/single, autoscale, recall, ``*RST``
                    (each of these is additionally flagged confirmation-required)
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

if TYPE_CHECKING:  # avoid importing the instrument layer at module load
    from .instruments.base import Instrument


class PermissionTier(IntEnum):
    """Capability tiers, ordered so that ``>=`` means "at least as privileged"."""

    READ_ONLY = 0
    READ_CONFIG = 1
    FULL = 2

    @classmethod
    def from_str(cls, value: str) -> "PermissionTier":
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:  # pragma: no cover - defensive
            valid = ", ".join(t.name.lower() for t in cls)
            raise ValueError(
                f"unknown permission tier {value!r}; expected one of: {valid}"
            ) from exc


class PermissionError(RuntimeError):
    """Raised when a tool is invoked beyond the session's granted tier, or a
    confirmation-required op is invoked without explicit confirmation.

    Tools surface this as a refusal to the caller rather than letting it crash
    the server — see ``tools`` package for the pattern.
    """


@dataclass
class Session:
    """Mutable per-connection state shared across the registered tools.

    Holds the active instrument backend and the granted permission tier. Created
    by ``server.py`` and captured by each tool at registration time, which keeps
    ``tools/`` free of any global/singleton coupling and makes every tool unit
    testable with a hand-built session.
    """

    tier: PermissionTier = PermissionTier.READ_ONLY
    instrument: Optional["Instrument"] = None
    # Resolved VISA resource string for the active connection, if any. Owned by
    # the transport layer; cached here purely for reporting/reconnect.
    resource: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def require_instrument(self) -> "Instrument":
        if self.instrument is None:
            raise RuntimeError(
                "no instrument connected — run the autoconnect/self_config tool first"
            )
        return self.instrument


# --- The tool-layer guard ---------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


def requires(tier: PermissionTier, *, confirmation: bool = False) -> Callable[[F], F]:
    """Decorate a tool implementation with its required tier.

    The wrapped function must take the :class:`Session` as its first positional
    argument. If ``confirmation`` is true the op is disruptive (run/stop, reset,
    autoscale, recall): it additionally requires the caller to pass
    ``confirm=True``.

    Enforcement happens here, before the body runs. A denied call raises
    :class:`PermissionError`; tools translate that into a structured refusal.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(session: Session, *args: Any, **kwargs: Any) -> Any:
            if session.tier < tier:
                raise PermissionError(
                    f"'{func.__name__}' requires the '{tier.name.lower()}' "
                    f"permission tier, but this session is "
                    f"'{session.tier.name.lower()}'. Refusing."
                )
            if confirmation and not kwargs.get("confirm", False):
                raise PermissionError(
                    f"'{func.__name__}' is a disruptive operation and requires "
                    f"explicit confirmation. Re-invoke with confirm=true."
                )
            return func(session, *args, **kwargs)

        # Expose the requirement for introspection (used by capability reports
        # and tests) without re-parsing the decorator.
        wrapper.__scpi_required_tier__ = tier  # type: ignore[attr-defined]
        wrapper.__scpi_confirmation_required__ = confirmation  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
