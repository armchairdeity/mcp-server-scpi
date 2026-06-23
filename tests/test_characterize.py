"""Flagship characterize_signal runs the full fit→trigger→measure loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from scpi_mcp.config import PermissionDenied, Session
from scpi_mcp.tools import characterize


def test_characterize_runs_full_loop(read_config_session: Session) -> None:
    result = characterize.characterize_signal_impl(read_config_session, 1)
    assert result["ok"] is True
    assert result["channel"] == 1
    # The mock is a clean, stable signal so every stage should fit.
    assert result["confidence"] == "high"
    assert result["vertical_fit"]["fitted"] is True
    assert result["horizontal_fit"]["stable"] is True
    assert result["trigger_hunt"]["triggered"] is True
    # Full measurement snapshot is present.
    for kind in ("frequency", "period", "vpp", "vrms", "duty"):
        assert kind in result["measurements"]
    assert result["waveform"]["n_points"] > 0


def test_characterize_exports_png(
    read_config_session: Session, tmp_path: Path
) -> None:
    out = tmp_path / "wf.png"
    result = characterize.characterize_signal_impl(
        read_config_session, 1, export_path=str(out)
    )
    assert result["export_png"] == str(out)
    assert out.exists() and out.stat().st_size > 1024


def test_characterize_validates_channel(read_config_session: Session) -> None:
    with pytest.raises(ValueError):
        characterize.characterize_signal_impl(read_config_session, 99)


def test_characterize_requires_read_config(read_only_session: Session) -> None:
    with pytest.raises(PermissionDenied):
        characterize.characterize_signal_impl(read_only_session, 1)
