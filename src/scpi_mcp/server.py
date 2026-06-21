"""MCP wiring only.

Creates the FastMCP instance and a :class:`~scpi_mcp.config.Session`, then asks
each tool module to register its tools against them. No tool logic, no SCPI, no
instrument access lives here — this file is the seam between the MCP runtime and
the instrument-agnostic ``tools`` package.

The permission tier is read from the ``SCPI_MCP_TIER`` environment variable
(default ``read_only``) so an operator decides how much the agent may do; the
server enforces it (see ``config.requires``).
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .config import PermissionTier, Session
from .tools import (
    acquisition,
    capture,
    characterize,
    config_tools,
    connection,
    measure,
)


def build_server(session: Session | None = None) -> FastMCP:
    """Construct and wire the FastMCP server.

    Exposed separately from :func:`main` so tests can build the server (and
    inspect registered tools) without running a transport.
    """
    if session is None:
        tier = PermissionTier.from_str(os.environ.get("SCPI_MCP_TIER", "read_only"))
        session = Session(tier=tier)

    mcp = FastMCP("scpi-mcp")

    # Each module owns its own registration; adding tools is local to a module.
    connection.register(mcp, session)
    capture.register(mcp, session)
    measure.register(mcp, session)
    config_tools.register(mcp, session)
    acquisition.register(mcp, session)
    characterize.register(mcp, session)

    return mcp


def main() -> None:
    """Console-script entry point (`scpi-mcp`). Runs over stdio."""
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
