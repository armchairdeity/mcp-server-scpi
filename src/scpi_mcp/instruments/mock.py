"""MockInstrument — the full interface, zero hardware.

Synthesizes deterministic waveforms (a per-channel sine by default) and derives
measurements from them, so the entire Part 1 scaffold — tools, exports, the
characterize stub — can run and be tested with no instrument and no VISA.

The synthesis is intentionally simple and reproducible: no randomness, so tests
can assert exact-ish values. This is *not* a hardware emulator; it just needs to
return interface-shaped data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..capabilities import DS1104Z_BASE, Capabilities
from .base import (
    Instrument,
    InstrumentIdentity,
    Measurement,
    MeasurementKind,
    TriggerConfig,
    Waveform,
)


@dataclass
class _ChannelModel:
    """The synthetic signal present on a channel."""

    enabled: bool = True
    amplitude: float = 1.0  # volts (peak)
    frequency: float = 1_000.0  # Hz
    offset: float = 0.0  # volts
    scale: float = 0.5  # volts/div (vertical)
    coupling: str = "DC"


class MockInstrument(Instrument):
    """An in-memory oscilloscope. Default: 1 kHz, 1 Vp sine on every channel."""

    def __init__(self, capabilities: Capabilities = DS1104Z_BASE) -> None:
        self.capabilities = capabilities
        self._channels: dict[int, _ChannelModel] = {
            ch: _ChannelModel(frequency=1_000.0 * ch) for ch in capabilities.channel_ids()
        }
        self._timebase_scale = 1e-3  # s/div
        self._timebase_offset = 0.0
        self._trigger: Optional[TriggerConfig] = None
        self._acq_type = "normal"
        self._memory_depth = 12_000
        self._running = True
        self._closed = False
        self.settle_calls: list[float] = []  # recorded for tests

    # -- identity ----------------------------------------------------------
    def identify(self) -> InstrumentIdentity:
        return InstrumentIdentity(
            vendor="RIGOL TECHNOLOGIES",
            model=self.capabilities.model,
            serial="MOCK0000000000",
            firmware="00.04.04.mock",
        )

    def close(self) -> None:
        self._closed = True

    # -- helpers -----------------------------------------------------------
    def _require_channel(self, channel: int) -> _ChannelModel:
        if channel not in self._channels:
            raise ValueError(
                f"channel {channel} out of range "
                f"(1..{self.capabilities.analog_channels})"
            )
        return self._channels[channel]

    def _synthesize(self, channel: int, n_points: int) -> Waveform:
        model = self._require_channel(channel)
        # Span ~10 horizontal divisions, centered on the trigger offset.
        span = self._timebase_scale * 10.0
        start = self._timebase_offset - span / 2.0
        dt = span / max(n_points - 1, 1)
        sample_rate = 1.0 / dt if dt else 0.0
        time: list[float] = []
        volts: list[float] = []
        omega = 2.0 * math.pi * model.frequency
        for i in range(n_points):
            t = start + i * dt
            time.append(t)
            volts.append(model.offset + model.amplitude * math.sin(omega * t))
        source = "memory" if n_points > 1500 else "screen"
        return Waveform(
            channel=channel,
            time=time,
            volts=volts,
            sample_rate=sample_rate,
            source=source,
        )

    # -- measurement -------------------------------------------------------
    def measure(self, channel: int, kind: MeasurementKind) -> Measurement:
        model = self._require_channel(channel)
        amp, freq = model.amplitude, model.frequency
        period = 1.0 / freq if freq else float("inf")
        values: dict[MeasurementKind, tuple[float, str]] = {
            MeasurementKind.VPP: (2.0 * amp, "V"),
            MeasurementKind.VRMS: (amp / math.sqrt(2.0), "V"),
            MeasurementKind.FREQUENCY: (freq, "Hz"),
            MeasurementKind.PERIOD: (period, "s"),
            MeasurementKind.DUTY: (50.0, "%"),
            # Idealized edges for a clean sine: ~10% of a period.
            MeasurementKind.RISE_TIME: (0.1 * period, "s"),
            MeasurementKind.FALL_TIME: (0.1 * period, "s"),
        }
        value, unit = values[kind]
        return Measurement(channel=channel, kind=kind, value=value, unit=unit)

    # -- capture -----------------------------------------------------------
    def capture_screen(self, channel: int) -> Waveform:
        return self._synthesize(channel, n_points=1200)

    def capture_memory(self, channel: int, points: Optional[int] = None) -> Waveform:
        n = points or self._memory_depth
        return self._synthesize(channel, n_points=n)

    # -- channel / timebase / trigger -------------------------------------
    def set_channel(
        self,
        channel: int,
        *,
        enabled: Optional[bool] = None,
        scale: Optional[float] = None,
        offset: Optional[float] = None,
        coupling: Optional[str] = None,
    ) -> None:
        model = self._require_channel(channel)
        if enabled is not None:
            model.enabled = enabled
        if scale is not None:
            model.scale = scale
        if offset is not None:
            model.offset = offset
        if coupling is not None:
            model.coupling = coupling

    def set_timebase(
        self,
        *,
        scale: Optional[float] = None,
        offset: Optional[float] = None,
    ) -> None:
        if scale is not None:
            self._timebase_scale = scale
        if offset is not None:
            self._timebase_offset = offset

    def set_trigger(self, config: TriggerConfig) -> None:
        self._require_channel(config.source)
        self._trigger = config

    # -- acquisition control ----------------------------------------------
    def run(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def single(self) -> None:
        self._running = False

    def force_trigger(self) -> None:
        pass  # synthetic data is always "triggered"

    def set_acquisition(
        self,
        *,
        acq_type: Optional[str] = None,
        memory_depth: Optional[int] = None,
    ) -> None:
        if acq_type is not None:
            self._acq_type = acq_type
        if memory_depth is not None:
            self._memory_depth = memory_depth

    # -- settle ------------------------------------------------------------
    def settle(self, seconds: float) -> None:
        # Record instead of sleeping so the settle-and-verify intent is testable
        # without wall-clock cost. Real backends actually wait. (Part 3.)
        self.settle_calls.append(seconds)
