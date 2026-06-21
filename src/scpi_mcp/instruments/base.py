"""The abstract instrument interface.

This is the *only* surface the ``tools`` layer is allowed to touch. It is
deliberately vendor-neutral and SCPI-free: methods describe oscilloscope
*intent* (set a channel scale, measure Vpp, capture a waveform), not wire
commands. Each concrete backend (``rigol_ds1000z``, ``mock``) maps these onto
its own library calls.

Adding a new instrument = implement this interface in a new file. No changes to
``tools/`` are needed or permitted.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..capabilities import Capabilities


# --- Value types passed across the interface --------------------------------


@dataclass(frozen=True)
class InstrumentIdentity:
    """Parsed ``*IDN?`` response."""

    vendor: str
    model: str
    serial: str
    firmware: str

    def __str__(self) -> str:
        return f"{self.vendor} {self.model} (SN {self.serial}, fw {self.firmware})"


class MeasurementKind(str, Enum):
    """Automatic-measurement quantities the tools layer can request.

    Vendor-neutral names; each backend maps them to its library's measurement
    enum. Intentionally limited to the set the flagship loop needs.
    """

    VPP = "vpp"
    VRMS = "vrms"
    FREQUENCY = "frequency"
    PERIOD = "period"
    DUTY = "duty"
    RISE_TIME = "rise_time"
    FALL_TIME = "fall_time"


@dataclass(frozen=True)
class Measurement:
    """A single automatic-measurement reading."""

    channel: int
    kind: MeasurementKind
    value: float
    unit: str


@dataclass(frozen=True)
class Waveform:
    """A captured waveform for one channel, on a shared time base.

    ``time`` and ``volts`` are equal-length sequences. ``source`` distinguishes
    a quick screen capture from a deep-memory read.
    """

    channel: int
    time: list[float]
    volts: list[float]
    sample_rate: float
    source: str  # "screen" | "memory"

    @property
    def n_points(self) -> int:
        return len(self.volts)


@dataclass
class TriggerConfig:
    """Edge-trigger configuration (the only mode the flagship loop drives)."""

    source: int  # channel number
    level: float
    slope: str = "rising"  # "rising" | "falling"
    mode: str = "edge"


# --- The interface ----------------------------------------------------------


class Instrument(abc.ABC):
    """Abstract base every SCPI instrument backend implements.

    Method groups map to the tool modules: identity/capabilities (connection),
    measurement (measure), capture (capture), channel/timebase/trigger
    (config_tools), acquisition control (acquisition).
    """

    # Backends set this; the capabilities module reads it. See capabilities.py.
    capabilities: "Capabilities"

    # -- identity ----------------------------------------------------------
    @abc.abstractmethod
    def identify(self) -> InstrumentIdentity:
        """Return parsed identity (``*IDN?``)."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release the underlying connection."""

    # -- measurement (read_only) ------------------------------------------
    @abc.abstractmethod
    def measure(self, channel: int, kind: MeasurementKind) -> Measurement:
        """Take a single automatic measurement on ``channel``."""

    # -- capture (read_only) ----------------------------------------------
    @abc.abstractmethod
    def capture_screen(self, channel: int) -> Waveform:
        """Capture the on-screen (≈1200-point) waveform for ``channel``."""

    @abc.abstractmethod
    def capture_memory(self, channel: int, points: Optional[int] = None) -> Waveform:
        """Capture the deep-memory waveform for ``channel``.

        ``points`` of ``None`` means "as many as the current memory depth".
        """

    # -- channel / timebase / trigger (read_config) -----------------------
    @abc.abstractmethod
    def set_channel(
        self,
        channel: int,
        *,
        enabled: Optional[bool] = None,
        scale: Optional[float] = None,
        offset: Optional[float] = None,
        coupling: Optional[str] = None,
    ) -> None:
        """Non-destructive vertical configuration for one channel."""

    @abc.abstractmethod
    def set_timebase(
        self,
        *,
        scale: Optional[float] = None,
        offset: Optional[float] = None,
    ) -> None:
        """Horizontal (time base) configuration."""

    @abc.abstractmethod
    def set_trigger(self, config: TriggerConfig) -> None:
        """Configure the (edge) trigger."""

    # -- acquisition control (full, disruptive) ---------------------------
    @abc.abstractmethod
    def run(self) -> None:
        """Start continuous acquisition."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop acquisition."""

    @abc.abstractmethod
    def single(self) -> None:
        """Arm a single acquisition."""

    @abc.abstractmethod
    def force_trigger(self) -> None:
        """Force a trigger event."""

    @abc.abstractmethod
    def set_acquisition(
        self,
        *,
        acq_type: Optional[str] = None,
        memory_depth: Optional[int] = None,
    ) -> None:
        """Acquisition type (normal/average/peak) and memory depth."""

    # -- settle ------------------------------------------------------------
    def settle(self, seconds: float) -> None:
        """Wait for the instrument to settle after a configuration change.

        Real backends and the underlying library insert sleeps on some commands
        (reset, autoscale); the flagship ``characterize_signal`` loop also needs
        explicit settle time after config changes before measurements are valid.
        Default is a no-op so the mock stays instant; overridden where it
        matters. (Exercised against hardware in Part 3.)
        """
