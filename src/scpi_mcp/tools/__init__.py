"""MCP tools — instrument-agnostic.

Every tool here calls only the abstract :class:`~scpi_mcp.instruments.base.Instrument`
interface. No vendor names, no SCPI strings, no imports from a concrete backend.
Adding a new instrument is zero changes to this package.

Registration pattern
---------------------
Each module exposes:

- plain ``*_impl(session, ...)`` functions decorated with
  :func:`~scpi_mcp.config.requires` — directly unit-testable with a hand-built
  :class:`~scpi_mcp.config.Session`; permission enforcement lives here.
- a ``register(mcp, session)`` function that wraps each impl as a FastMCP tool,
  capturing the session and translating refusals into structured results.

``server.py`` creates the FastMCP instance + session and calls every module's
``register``. This keeps ``tools/`` free of global state and circular imports.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..config import PermissionDenied, Session


def refusal(message: str) -> dict[str, Any]:
    """Structured refusal payload returned to the model on a denied call."""
    return {"ok": False, "refused": True, "error": message}


def guarded(session: Session, impl: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap an ``*_impl`` as a FastMCP-facing callable.

    Binds the session and converts :class:`PermissionDenied` (tier/confirmation
    denials) into a refusal payload instead of an exception, so the model sees a
    clean "the server refused" result.
    """

    def tool(*args: Any, **kwargs: Any) -> Any:
        try:
            return impl(session, *args, **kwargs)
        except PermissionDenied as exc:
            return refusal(str(exc))

    tool.__name__ = getattr(impl, "__name__", "tool")
    tool.__doc__ = impl.__doc__
    return tool
