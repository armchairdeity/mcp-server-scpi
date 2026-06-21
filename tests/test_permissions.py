"""The server refuses, not the model: tier + confirmation enforcement."""

from __future__ import annotations

import pytest

from scpi_mcp.config import PermissionError, PermissionTier, Session
from scpi_mcp.tools import acquisition, config_tools, measure


def test_read_only_can_measure(read_only_session: Session) -> None:
    result = measure.measure_impl(read_only_session, 1, "vpp")
    assert result["ok"] is True


def test_read_only_cannot_configure(read_only_session: Session) -> None:
    with pytest.raises(PermissionError):
        config_tools.set_timebase_impl(read_only_session, scale=1e-3)


def test_read_config_can_configure(read_config_session: Session) -> None:
    result = config_tools.set_timebase_impl(read_config_session, scale=1e-3)
    assert result["ok"] is True


def test_read_config_cannot_run_acquisition(read_config_session: Session) -> None:
    with pytest.raises(PermissionError):
        acquisition.run_impl(read_config_session, confirm=True)


def test_full_requires_confirmation(full_session: Session) -> None:
    # Right tier, but no confirmation → refused.
    with pytest.raises(PermissionError):
        acquisition.run_impl(full_session)


def test_full_with_confirmation_runs(full_session: Session) -> None:
    result = acquisition.run_impl(full_session, confirm=True)
    assert result == {"ok": True, "state": "running"}


def test_decorator_exposes_requirements() -> None:
    assert acquisition.run_impl.__scpi_required_tier__ is PermissionTier.FULL
    assert acquisition.run_impl.__scpi_confirmation_required__ is True
    assert measure.measure_impl.__scpi_required_tier__ is PermissionTier.READ_ONLY


def test_tier_ordering() -> None:
    assert PermissionTier.READ_ONLY < PermissionTier.READ_CONFIG < PermissionTier.FULL
    assert PermissionTier.from_str("full") is PermissionTier.FULL
