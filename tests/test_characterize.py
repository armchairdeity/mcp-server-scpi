"""Flagship characterize_signal is a structured stub in Part 1."""

from __future__ import annotations

import pytest

from scpi_mcp.config import PermissionDenied, Session
from scpi_mcp.tools import characterize


def test_characterize_is_stubbed(read_config_session: Session) -> None:
    result = characterize.characterize_signal_impl(read_config_session, 1)
    assert result["ok"] is True
    assert result["implemented"] is False
    # Names the loop stages and the settle-and-verify contract for Part 3.
    assert result["stages"] == [
        "probe",
        "vertical_fit",
        "horizontal_fit",
        "trigger_hunt",
        "characterize",
    ]
    assert "contract" in result["settle_and_verify"]


def test_characterize_validates_channel(read_config_session: Session) -> None:
    with pytest.raises(ValueError):
        characterize.characterize_signal_impl(read_config_session, 99)


def test_characterize_requires_read_config(read_only_session: Session) -> None:
    with pytest.raises(PermissionDenied):
        characterize.characterize_signal_impl(read_only_session, 1)
