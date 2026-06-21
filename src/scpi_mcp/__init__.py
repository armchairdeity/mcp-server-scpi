"""scpi-mcp — oscilloscope expertise for agents over MCP.

All vendor SCPI lives in the instrument library; this package is a thin,
uniform wrapper with no raw-SCPI escape hatch. See ``server.py`` for the MCP
wiring and ``instruments/base.py`` for the abstract interface every backend
implements.
"""

__version__ = "0.1.0"
