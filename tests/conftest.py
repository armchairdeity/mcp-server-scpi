"""Shared fixtures — all against the mock, zero hardware."""

from __future__ import annotations

import pytest

from scpi_mcp.config import PermissionTier, Session
from scpi_mcp.instruments.mock import MockInstrument


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
