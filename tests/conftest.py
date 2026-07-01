"""Shared fixtures — all against the mock, zero hardware."""

from __future__ import annotations

import pytest

from scpi_mcp.config import PermissionTier, Session
from scpi_mcp.instruments.mock import MockInstrument


@pytest.fixture(autouse=True)
def _force_mock_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hardware safety net: no test may touch a real scope.

    The transport default backend factory now builds a live ``RigolDS1000Z``
    unless ``SCPI_MCP_MOCK`` is set, so force it on for the whole suite. Tests
    that exercise the live backend do so directly with a fake device.
    """
    monkeypatch.setenv("SCPI_MCP_MOCK", "1")


@pytest.fixture
def mock_instrument() -> MockInstrument:
    return MockInstrument()


@pytest.fixture
def read_only_session(mock_instrument: MockInstrument) -> Session:
    return Session(tier=PermissionTier.READ_ONLY, instrument=mock_instrument)


@pytest.fixture
def read_config_session(mock_instrument: MockInstrument) -> Session:
    return Session(tier=PermissionTier.READ_CONFIG, instrument=mock_instrument)


@pytest.fixture
def full_session(mock_instrument: MockInstrument) -> Session:
    return Session(tier=PermissionTier.FULL, instrument=mock_instrument)
