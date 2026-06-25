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

import functools
import inspect
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

    Uses ``functools.wraps`` AND rebuilds the signature without the leading
    ``session`` parameter so FastMCP introspects the real tool parameters and
    generates a correct JSON schema (instead of the useless ``*args/**kwargs``
    schema produced when the signature is opaque).
    """

    @functools.wraps(impl)
    def tool(**kwargs: Any) -> Any:
        try:
            return impl(session, **kwargs)
        except PermissionDenied as exc:
            return refusal(str(exc))

    # Remove the 'session' parameter from the visible signature so FastMCP
    # doesn't expect callers to supply it.
    original_sig = inspect.signature(impl)
    params = [
        p for name, p in original_sig.parameters.items()
        if name != "session"
    ]
    tool.__signature__ = original_sig.replace(parameters=params)  # type: ignore[attr-defined]

    return tool
